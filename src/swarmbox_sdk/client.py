from __future__ import annotations

import asyncio
import hashlib
import io
import os
import tarfile
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

import httpx


# Old setting names already warned about in this process.
_warned: set[str] = set()


def env(name: str, default: str | None = None) -> str | None:
    """The setting SWARMBOX_<name> from the environment.

    Until 0.5.0 the name it had before the project was renamed,
    OPENDSEC_<name>, is used when SWARMBOX_<name> is unset or empty, with a
    FutureWarning: the kind Python shows to someone running a program, not
    only to whoever wrote the calling code. Once per setting in a process:
    a run of hundreds of trials reads each of them hundreds of times.
    """
    new, old = os.environ.get(f"SWARMBOX_{name}"), os.environ.get(f"OPENDSEC_{name}")
    if new or old is None:
        return default if new is None else new
    if name in _warned:
        return old
    _warned.add(name)
    warnings.warn(
        f"OPENDSEC_{name} is used for now, but the project is renamed: set SWARMBOX_{name} instead",
        FutureWarning,
        stacklevel=2,
    )
    return old


class SwarmboxError(Exception):
    """A request failed. `status` is the HTTP status when the API answered
    with an error (503 means the platform had no capacity: retrying shortly
    is safe), else None."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# The name this class had before the project was renamed; kept until 0.5.0 so
# that existing `except OpendsecError` clauses still catch.
OpendsecError = SwarmboxError


class WorldFailed(SwarmboxError):
    """The World ended for an infra reason (not an agent failure); retry it."""

    def __init__(self, world_id: str, reason: str):
        super().__init__(f"world {world_id} failed: {reason}")
        self.world_id = world_id
        self.reason = reason


class BuildFailed(SwarmboxError):
    """The platform could not build an image from its build context: the
    Dockerfile failed, or the build timed out. `log` is the tail of the build's
    output, where a failing step shows."""

    def __init__(self, tag: str, error: str, log: str):
        super().__init__(f"image build {tag} failed: {error}\n{log}")
        self.tag = tag
        self.error = error
        self.log = log


@dataclass
class Image:
    """An image the platform built for you. Pass `ref`, the image by digest
    in the platform's registry, as a Sandbox's image."""

    tag: str
    #: The image by digest once it is ready; until then, the tag being built.
    ref: str = ""
    state: str = ""  # "building", "ready" or "failed"
    error: str = ""
    log: str = ""
    build_ms: int = 0
    #: True if this call found the image already built.
    cached: bool = False


# Never part of a build context: editor and OS clutter, and VCS metadata.
IGNORED_NAMES = frozenset({".DS_Store", ".git", "__pycache__"})


def _context_files(context: Path) -> list[Path]:
    return [
        p
        for p in sorted(context.rglob("*"))
        if p.is_file() and not any(part in IGNORED_NAMES for part in p.relative_to(context).parts)
    ]


def context_tag(context: str | Path, dockerfile: str = "Dockerfile") -> str:
    """The tag an image built from this context gets: a hash of every file's
    path, exec bit and contents, and of the Dockerfile's name. Unchanged files
    give the same tag, so a rebuild of them is a lookup."""
    context = Path(context)
    h = hashlib.sha256()

    def add(*parts: str | bytes) -> None:
        for p in parts:
            b = p.encode() if isinstance(p, str) else p
            h.update(len(b).to_bytes(8, "big") + b)

    add("opendsec-context-v1", dockerfile)
    for p in _context_files(context):
        add(p.relative_to(context).as_posix(), oct(p.stat().st_mode & 0o111), p.read_bytes())
    return h.hexdigest()[:32]


def _image(d: dict) -> Image:
    known = Image.__dataclass_fields__.keys() - {"cached"}
    return Image(**{k: v for k, v in d.items() if k in known})


def _context_tar(context: Path) -> bytes:
    buf = io.BytesIO()
    # Links are sent as the files they point to, which is what context_tag
    # hashed: a link out of the context would dangle on the platform.
    with tarfile.open(fileobj=buf, mode="w", dereference=True) as tar:
        for p in _context_files(context):
            tar.add(p, arcname=p.relative_to(context).as_posix(), recursive=False)
    return buf.getvalue()


@dataclass
class Readiness:
    command: list[str]
    interval: str = "1s"
    timeout: str = "60s"


@dataclass
class Sandbox:
    """One container of a World."""

    name: str
    image: str
    cpus: float = 1
    memory_mb: int = 1024
    command: list[str] | None = None
    env: dict[str, str] = field(default_factory=dict)
    workdir: str | None = None
    aliases: list[str] = field(default_factory=list)
    readiness: Readiness | None = None
    egress: str = "none"  # "none" or "public"

    def to_json(self) -> dict:
        d = {
            "name": self.name,
            "image": self.image,
            "resources": {"cpus": self.cpus, "memory_mb": self.memory_mb},
            "env": self.env,
            "aliases": self.aliases,
            "egress": self.egress,
        }
        if self.command:
            d["command"] = self.command
        if self.workdir:
            d["workdir"] = self.workdir
        if self.readiness:
            d["readiness"] = asdict(self.readiness)
        return d


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False


class Client:
    """Talks to a swarmbox apiserver.

    Defaults come from SWARMBOX_URL and SWARMBOX_TOKEN.
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        timeout: float = 600,
        max_connections: int = 100,
    ):
        url = url or env("URL", "http://localhost:7700")
        token = token or env("TOKEN")
        if not token:
            raise SwarmboxError("no API token: pass token= or set SWARMBOX_TOKEN")
        # Each in-flight create or exec holds a connection for its whole
        # duration, so concurrency above max_connections queues client-side.
        self._http = httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections),
        )

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    async def create_world(self, sandboxes: list[Sandbox], ttl: str = "1h") -> World:
        """Create a World and wait until every Sandbox in it is ready."""
        info = await self._request(
            "POST", "/v1/worlds", json={"ttl": ttl, "sandboxes": [sb.to_json() for sb in sandboxes]}
        )
        if info["state"] == "failed":
            raise WorldFailed(info["id"], info.get("reason", ""))
        return World(self, info)

    async def list_worlds(self) -> list[dict]:
        """Your Worlds, on every node (the apiserver fans out). Other Users' are never listed."""
        return (await self._request("GET", "/v1/worlds"))["worlds"]

    async def get_world(self, world_id: str) -> World:
        return World(self, await self._request("GET", f"/v1/worlds/{world_id}"))

    async def get_image(self, tag: str) -> Image | None:
        """Your image with this tag, or None if the platform has none."""
        r = await self._http.get(f"/v1/images/{tag}")
        if r.status_code == 404:
            return None
        return _image(self._json(r, "GET", f"/v1/images/{tag}"))

    async def build_image(
        self,
        context: str | Path,
        dockerfile: str = "Dockerfile",
        *,
        force: bool = False,
        poll: float = 1.0,
        timeout: float = 1800,
    ) -> Image:
        """The image built from a Dockerfile and its build context (a local
        directory), building it on the platform first unless it already has
        it (or `force`, which rebuilds without the platform's build cache).
        Returns once it is ready; raises BuildFailed if it can't be built.
        If too many of your builds are already queued, it waits its turn.

        Images are built for the platform's nodes, so this works from any
        machine, with no Docker. The image's `ref` runs on every node; a
        tag is yours alone, so no other User's upload can replace it.
        """
        context = Path(context)
        if not (context / dockerfile).is_file():
            raise SwarmboxError(f"no {dockerfile} in the build context {context}")
        tag = await asyncio.to_thread(context_tag, context, dockerfile)
        img = await self.get_image(tag)
        cached = img is not None and img.state == "ready"
        deadline = asyncio.get_running_loop().time() + timeout
        if img is None or img.state == "failed" or (force and img.state == "ready"):
            body = await asyncio.to_thread(_context_tar, context)
            params = {"dockerfile": dockerfile} | ({"force": "1"} if force else {})
            backoff = poll
            while True:
                r = await self._http.put(f"/v1/images/{tag}", params=params, content=body)
                # 429: too many of your builds are queued; wait for some to end.
                if r.status_code != 429 or asyncio.get_running_loop().time() > deadline:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            img = _image(self._json(r, "PUT", f"/v1/images/{tag}"))
        while img.state == "building":
            if asyncio.get_running_loop().time() > deadline:
                raise SwarmboxError(f"image build {tag} still running after {timeout:.0f}s")
            await asyncio.sleep(poll)
            got = await self.get_image(tag)
            if got is None:
                raise SwarmboxError(f"image build {tag} disappeared (the builder restarted?); retry")
            img = got
        if img.state == "failed":
            raise BuildFailed(tag, img.error, img.log)
        img.cached = cached and not force
        return img

    async def _request(self, method: str, path: str, **kw) -> dict:
        return self._json(await self._http.request(method, path, **kw), method, path)

    @staticmethod
    def _json(r: httpx.Response, method: str, path: str) -> dict:
        if r.is_error:
            try:
                msg = r.json().get("error", r.text)
            except ValueError:
                msg = r.text
            raise SwarmboxError(f"{method} {path}: {r.status_code} {msg}", status=r.status_code)
        return r.json()


class World:
    """A live World. Methods take the name of the Sandbox to act in."""

    def __init__(self, client: Client, info: dict):
        self._client = client
        self.info = info

    @property
    def id(self) -> str:
        return self.info["id"]

    @property
    def state(self) -> str:
        return self.info["state"]

    @property
    def timings(self) -> dict[str, int]:
        """Where create time went on the node, in milliseconds."""
        return self.info.get("timings", {})

    def _path(self, sandbox: str, op: str) -> str:
        return f"/v1/worlds/{self.id}/sandboxes/{sandbox}/{op}"

    async def exec(
        self,
        sandbox: str,
        command: str | list[str],
        *,
        env: dict[str, str] | None = None,
        workdir: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        """Run a command in a Sandbox. A string is run with `bash -lc`."""
        if isinstance(command, str):
            command = ["bash", "-lc", command]
        body: dict = {"command": command, "env": env or {}}
        if workdir:
            body["workdir"] = workdir
        if timeout:
            body["timeout"] = timeout
        try:
            res = await self._client._request("POST", self._path(sandbox, "exec"), json=body)
        except SwarmboxError:
            await self._raise_if_failed()
            raise
        return ExecResult(**res)

    async def upload(self, sandbox: str, local: str | Path, remote: str) -> None:
        """Copy a local file or directory to `remote` inside a Sandbox."""
        local = Path(local)
        remote_p = PurePosixPath(remote)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            if local.is_dir():
                for child in sorted(local.iterdir()):
                    tar.add(child, arcname=child.name)
                target_dir = str(remote_p)
            else:
                tar.add(local, arcname=remote_p.name)
                target_dir = str(remote_p.parent)
        await self._client._request(
            "PUT", self._path(sandbox, "archive"), params={"path": target_dir}, content=buf.getvalue()
        )

    async def download(self, sandbox: str, remote: str, local: str | Path) -> None:
        """Copy a file or directory at `remote` inside a Sandbox to `local`."""
        r = await self._client._http.get(self._path(sandbox, "archive"), params={"path": remote})
        if r.is_error:
            raise SwarmboxError(f"download {remote}: {r.status_code} {r.text}")
        local = Path(local)
        name = PurePosixPath(remote).name
        with tarfile.open(fileobj=io.BytesIO(r.content), mode="r") as tar:
            if tar.getmember(name).isdir():
                local.mkdir(parents=True, exist_ok=True)
                for m in tar.getmembers():
                    if m.name == name:
                        continue
                    m.name = m.name[len(name) + 1 :]
                    tar.extract(m, local, filter="data")
            else:
                local.parent.mkdir(parents=True, exist_ok=True)
                f = tar.extractfile(name)
                assert f is not None
                local.write_bytes(f.read())

    async def refresh(self) -> World:
        self.info = await self._client._request("GET", f"/v1/worlds/{self.id}")
        return self

    async def stop(self) -> None:
        self.info = await self._client._request("DELETE", f"/v1/worlds/{self.id}")

    async def _raise_if_failed(self) -> None:
        try:
            await self.refresh()
        except SwarmboxError:
            return
        if self.state == "failed":
            raise WorldFailed(self.id, self.info.get("reason", ""))
