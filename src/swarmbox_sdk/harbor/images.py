"""Images for a task's services: built by the platform, or pushed to a registry from here.

Every compose service runs an image the platform's nodes can pull. Files a
compose service bind-mounts are baked into its image, because a remote World
cannot see this machine's files. There are two ways to get the image there:

**The platform builds it** (`platform_image`, the default; ADR 0009). The
service's build context is uploaded and built by `swarmbox_sdk.Client.build_image`,
tagged by a hash of its files, so a task whose files haven't changed is a
lookup, never a rebuild. Nothing is built on this machine: no Docker, no
registry access. A service that names an image and needs nothing added runs
that image as-is.

**This machine builds it** (`resolve_image`, when a registry is configured;
ADR 0008). The image is built with Docker and pushed to the registry, tagged
by a hash of everything that determines it: the build context's files, the
Dockerfile name, any files baked in, and the platform. If the registry
already holds that tag, nothing is built, so `prebuild` (run ahead of a
batch) and the provider (at trial start) share one cache: the registry.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform as host_platform
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import swarmbox_sdk
from swarmbox_sdk.client import env
from swarmbox_sdk.harbor.compose import ServicePlan

REPO = "swarmbox/task-images"
_IGNORE = {".DS_Store", ".git", "__pycache__"}
_locks: dict[str, asyncio.Lock] = {}
_cache: dict[str, str] = {}
_platform_cache: dict[str, str] = {}


@dataclass
class ImageReport:
    service: str
    ref: str  # what the Sandbox runs: registry/repo@sha256:..., or the image as named
    status: str  # "cached" (already built), "built", or "public" (run as named)
    seconds: float


def default_platform() -> str:
    """SWARMBOX_PLATFORM, else this machine's architecture.

    Images must match the nodes'; this default suits a driver that shares
    the nodes' architecture (an amd64 VM next to amd64 nodes, or a Mac next
    to its arm64 Lima VM).
    """
    if p := env("PLATFORM"):
        return p
    arch = host_platform.machine().lower()
    return "linux/arm64" if arch in ("arm64", "aarch64") else "linux/amd64"


def content_hash(plan: ServicePlan, platform: str) -> str:
    """Hash of every input that determines the service's image."""
    h = hashlib.sha256()

    def add(*parts: str | bytes) -> None:
        for p in parts:
            b = p.encode() if isinstance(p, str) else p
            h.update(len(b).to_bytes(8, "big") + b)

    add("v1", platform, plan.dockerfile or "Dockerfile")
    if plan.build_context:
        add("context")
        _add_tree(add, plan.build_context)
    else:
        add("image", plan.image or "")
    for f in plan.files:
        add("file", f.target)
        _add_tree(add, f.source)
    return h.hexdigest()[:24]


def _add_tree(add, root: Path) -> None:
    if root.is_file():
        add(root.read_bytes())
        return
    for p in sorted(root.rglob("*")):
        if any(part in _IGNORE for part in p.relative_to(root).parts) or not p.is_file():
            continue
        add(p.relative_to(root).as_posix(), oct(p.stat().st_mode & 0o111), p.read_bytes())


async def resolve_image(
    plan: ServicePlan, registry: str, *, force_build: bool = False, platform: str | None = None
) -> ImageReport:
    """Ensure the service's image is in the registry; return it by digest."""
    platform = platform or default_platform()
    tag = f"{registry}/{REPO}:{content_hash(plan, platform)}"
    lock = _locks.setdefault(tag, asyncio.Lock())
    async with lock:
        start = time.monotonic()
        if tag in _cache and not force_build:
            return ImageReport(plan.name, _cache[tag], "cached", 0.0)
        if not force_build and (digest := await _digest(tag)):
            ref = _by_digest(tag, digest)
            status = "cached"
        else:
            await _build(plan, tag, platform, no_cache=force_build)
            await _docker("push", "-q", tag)
            digest = await _digest(tag)
            if not digest:
                raise RuntimeError(f"pushed {tag} but the registry does not report a digest")
            ref = _by_digest(tag, digest)
            status = "built"
        _cache[tag] = ref
        return ImageReport(plan.name, ref, status, time.monotonic() - start)


# Where baked-in files go inside a generated build context.
_BAKED = ".opendsec-files"


async def platform_image(client: swarmbox_sdk.Client, plan: ServicePlan, force_build: bool = False) -> ImageReport:
    """The image a service's Sandbox runs, built on the platform if needed.
    force_build rebuilds it without cache, once per process."""
    start = time.monotonic()
    if not plan.build_context and not plan.files:
        assert plan.image
        return ImageReport(plan.name, plan.image, "public", 0.0)
    with build_context(plan) as (context, dockerfile):
        tag = await asyncio.to_thread(swarmbox_sdk.context_tag, context, dockerfile)
        # Trials of one task start together; one of them builds, the rest wait.
        async with _locks.setdefault("platform:" + tag, asyncio.Lock()):
            if tag in _platform_cache:
                return ImageReport(plan.name, _platform_cache[tag], "cached", 0.0)
            img = await client.build_image(context, dockerfile, force=force_build)
            _platform_cache[tag] = img.ref
    return ImageReport(plan.name, img.ref, "cached" if img.cached else "built", time.monotonic() - start)


@contextmanager
def build_context(plan: ServicePlan) -> Iterator[tuple[Path, str]]:
    """The directory and Dockerfile to build a service from.

    That is its own build context, unless it needs files baked in: then a
    temporary copy of the context, with the files and a Dockerfile that adds
    them after the original's last stage.
    """
    dockerfile = plan.dockerfile or "Dockerfile"
    if plan.build_context and not plan.files:
        yield plan.build_context, dockerfile
        return
    with tempfile.TemporaryDirectory(prefix="swarmbox-context-") as tmp:
        ctx = Path(tmp) / "context"
        if plan.build_context:
            shutil.copytree(plan.build_context, ctx, symlinks=True)
            lines = [(plan.build_context / dockerfile).read_text().rstrip("\n")]
        else:
            ctx.mkdir()
            lines = [f"FROM {plan.image}"]
        for i, f in enumerate(plan.files):
            name = f"{_BAKED}/f{i}"
            if f.source.is_dir():
                shutil.copytree(f.source, ctx / name)
            else:
                (ctx / _BAKED).mkdir(exist_ok=True)
                shutil.copy2(f.source, ctx / name)
            lines.append(f"COPY {name} {f.target}")
        generated = ".opendsec.Dockerfile"
        (ctx / generated).write_text("\n".join(lines) + "\n")
        yield ctx, generated


async def convert_lazy(ref: str, store: Path, platform: str, binary: str = "swarmbox-convert") -> dict:
    """Convert an image, by digest, into the lazy image store mounted at store.

    Runs swarmbox-convert, which is idempotent: an image already converted is
    only checked. Returns its JSON report (layers, layers_built, existing,
    bytes, seconds); raises if the conversion failed.
    """
    argv = [binary, "-store", str(store), "-platform", platform]
    if _insecure(ref):
        argv.append("-insecure")
    code, out = await _run(*argv, ref, check=False, stderr_on_error=True)
    lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    report = json.loads(lines[-1]) if lines else {}
    if code != 0 or not report.get("ok"):
        raise RuntimeError(f"convert {ref}: {report.get('error') or out.strip()[-500:]}")
    return report


async def compressed_size(ref: str, plat: str | None = None) -> int:
    """Total compressed layer bytes of an image, as a node would pull it."""
    _, out = await _crane("manifest", "--platform", plat or default_platform(), ref)
    return sum(layer["size"] for layer in json.loads(out).get("layers", []))


async def _build(plan: ServicePlan, tag: str, platform: str, no_cache: bool) -> None:
    if plan.build_context:
        args = ["build", "-q", "--platform", platform, "-t", tag]
        if plan.dockerfile:
            args += ["-f", str(plan.build_context / plan.dockerfile)]
        if no_cache:
            args.append("--no-cache")
        await _docker(*args, str(plan.build_context))
    else:
        assert plan.image
        # Prefer a local image (e.g. one built by the environment's own
        # tooling) when it matches the platform; otherwise pull.
        code, local = await _docker(
            "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", plan.image, check=False
        )
        if code != 0 or local.strip() != platform:
            await _docker("pull", "-q", "--platform", platform, plan.image)
        await _docker("tag", plan.image, tag)
    if plan.files:
        # A remote World cannot see this machine's files: bake them in.
        with tempfile.TemporaryDirectory() as ctx:
            lines = [f"FROM {tag}"]
            for i, f in enumerate(plan.files):
                name = f"f{i}"
                if f.source.is_dir():
                    shutil.copytree(f.source, Path(ctx) / name)
                else:
                    shutil.copy2(f.source, Path(ctx) / name)
                lines.append(f"COPY {name} {f.target}")
            (Path(ctx) / "Dockerfile").write_text("\n".join(lines) + "\n")
            await _docker("build", "-q", "--platform", platform, "-t", tag, ctx)


_NOT_FOUND = ("MANIFEST_UNKNOWN", "NAME_UNKNOWN", "NOT_FOUND", "404 Not Found")


async def _digest(tag: str) -> str | None:
    """The tag's digest, or None if the registry does not have it.

    Only a definite "not found" is a cache miss. Any other failure (expired
    credentials, network) raises: treating it as a miss would rebuild and
    push an image that already exists, and fail confusingly at the push.
    """
    code, out = await _crane("digest", tag, check=False)
    if code == 0 and out.startswith("sha256:"):
        return out.strip()
    if any(marker in out for marker in _NOT_FOUND):
        return None
    raise RuntimeError(f"cannot query registry for {tag} (credentials expired?):\n{out.strip()[-500:]}")


def _by_digest(tag: str, digest: str) -> str:
    return tag.rsplit(":", 1)[0] + "@" + digest


def _insecure(ref: str) -> bool:
    host = ref.split("/", 1)[0].split(":", 1)[0]
    return host in ("localhost", "127.0.0.1")


async def _crane(*args: str, check: bool = True) -> tuple[int, str]:
    """Run crane; on failure the returned text includes stderr."""
    ref = args[-1]
    extra = ["--insecure"] if _insecure(ref) else []
    return await _run("crane", *args[:-1], *extra, ref, check=check, stderr_on_error=True)


async def _docker(*args: str, check: bool = True) -> tuple[int, str]:
    return await _run("docker", *args, check=check)


async def _run(*argv: str, check: bool = True, stderr_on_error: bool = False) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"{' '.join(argv[:3])} failed ({proc.returncode}):\n{(out + err).decode(errors='replace')[-2000:]}"
        )
    text = out if proc.returncode == 0 or not stderr_on_error else out + err
    return proc.returncode or 0, text.decode(errors="replace")
