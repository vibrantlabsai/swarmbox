"""Harbor environment provider backed by swarmbox.

    harbor run -e swarmbox_sdk.harbor:SwarmboxEnvironment --ek url=http://localhost:7700 ...

Each Harbor trial is one World; each compose service is one Sandbox in it.
Each service's image is built on the platform from the task's files, or,
with a registry configured, built here with Docker and pushed there
(images.py).

Works with upstream Harbor (0.22) and Marin's fork (0.8.1); the two differ in
how they express network policy, handled in `_egress`.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx
from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities
from harbor.environments.definition import require_agent_environment_definition

import swarmbox_sdk
from swarmbox_sdk.client import env
from swarmbox_sdk.harbor.compose import MAIN, plan_services
from swarmbox_sdk.harbor.images import platform_image, resolve_image


class SwarmboxEnvironment(BaseEnvironment):
    def __init__(self, *args, **kwargs):
        self._url = kwargs.pop("url", None) or env("URL", "http://localhost:7700")
        self._token = kwargs.pop("token", None) or env("TOKEN")
        # With a registry, images are built here and pushed to it; without,
        # the platform builds them. Nodes may reach the registry by another
        # name (local dev: Docker Desktop's localhost is the Lima VM's
        # host.lima.internal).
        self._registry = kwargs.pop("registry", None) or env("REGISTRY")
        self._pull_registry = (
            kwargs.pop("pull_registry", None)
            or env("PULL_REGISTRY")
            or ("host.lima.internal:5001" if self._registry == "localhost:5001" else self._registry)
        )
        self._ttl = kwargs.pop("ttl", "3h")
        self._platform = kwargs.pop("platform", None)
        self._metrics: dict = {}
        self._started_at: float | None = None
        self._client: swarmbox_sdk.Client | None = None
        self._world: swarmbox_sdk.World | None = None
        super().__init__(*args, **kwargs)

    @staticmethod
    def type() -> str:
        return "swarmbox"

    @property
    def capabilities(self) -> EnvironmentCapabilities:
        # Egress is all-or-nothing for now: no allowlists, and no switching
        # policy mid-trial. Harbor rejects tasks that need either rather than
        # run them with the wrong network.
        return EnvironmentCapabilities(docker_compose=True, disable_internet=True)

    def _egress(self) -> str:
        policy = getattr(self, "_network_policy", None)
        if policy is not None:  # upstream Harbor
            mode = str(getattr(policy.network_mode, "value", policy.network_mode))
            if mode == "public":
                return "public"
            if mode == "no-network":
                return "none"
            raise NotImplementedError(f"swarmbox: network mode {mode!r} is not supported yet")
        # Marin's fork: a boolean on the task's environment config.
        return "public" if getattr(self.task_env_config, "allow_internet", True) else "none"

    def _node_ref(self, ref: str) -> str:
        """An image as the nodes name it: an image this machine pushed is in
        a registry they may reach by another name."""
        if self._registry and ref.startswith(self._registry):
            return self._pull_registry + ref.removeprefix(self._registry)
        return ref

    def _validate_definition(self):
        require_agent_environment_definition(
            self.environment_dir, docker_image=self.task_env_config.docker_image
        )

    async def start(self, force_build: bool) -> None:
        t0 = time.monotonic()
        plans = plan_services(
            self.environment_dir, self.task_env_config.docker_image, prefer_prebuilt=not force_build
        )
        self._client = swarmbox_sdk.Client(self._url, self._token)
        if self._registry:
            reports = await asyncio.gather(
                *(resolve_image(p, self._registry, force_build=force_build, platform=self._platform) for p in plans)
            )
        else:
            reports = await asyncio.gather(*(platform_image(self._client, p, force_build) for p in plans))
        t_images = time.monotonic()
        cpus, memory_mb = self._effective_cpus or 1, self._effective_memory_mb or 2048
        egress = self._egress()
        sandboxes = []
        for p, rep in zip(plans, reports):
            env = dict(p.env)
            if p.name == MAIN:
                env.update(self.task_env_config.env or {})
            sandboxes.append(
                swarmbox_sdk.Sandbox(
                    name=p.name,
                    image=self._node_ref(rep.ref),
                    cpus=cpus,
                    memory_mb=memory_mb,
                    command=p.command,
                    env=env,
                    aliases=p.aliases,
                    egress=egress,
                    readiness=swarmbox_sdk.Readiness(
                        command=p.readiness,
                        interval=f"{p.readiness_interval_s}s",
                        timeout=f"{p.readiness_timeout_s}s",
                    )
                    if p.readiness
                    else None,
                )
            )
        self.logger.debug(f"creating world with sandboxes {[sb.name for sb in sandboxes]}")
        try:
            self._world, retries = await create_world_retrying(self._client, sandboxes, self._ttl)
        finally:
            self._metrics = {
                "egress": egress,
                "images": [vars(r) for r in reports],
                "images_s": round(t_images - t0, 3),
                "create_s": round(time.monotonic() - t_images, 3),
            }
        self._metrics["create_retries"] = retries
        self._metrics |= {
            "world_id": self._world.id,
            "node_timings_ms": self._world.timings,
            # How the node loaded each Sandbox's image: lazily from the image
            # store, or pulled whole.
            "node_images": self._world.info.get("images", {}),
        }
        self.logger.debug(f"world {self._world.id} ready")
        # Harbor's /logs/* mounts become plain directories it copies back.
        await self.ensure_dirs(self._mount_targets(writable_only=True))
        await self._upload_environment_dir_after_start()
        self._metrics["start_s"] = round(time.monotonic() - t0, 3)
        self._started_at = time.monotonic()

    async def stop(self, delete: bool):
        try:
            if self._started_at is not None:
                self._metrics["in_world_s"] = round(time.monotonic() - self._started_at, 3)
            if self._world:
                await self._world.stop()
        finally:
            self._write_metrics()
            if self._client:
                await self._client.close()
            self._world = self._client = None

    def _write_metrics(self) -> None:
        if not self._metrics:
            return
        role = "verifier" if "__verifier__" in self.session_id else "agent"
        try:
            path = Path(str(self.trial_paths.trial_dir)) / f"swarmbox-{role}.json"
            path.write_text(json.dumps(self._metrics, indent=2) + "\n")
        except OSError as e:
            self.logger.warning(f"swarmbox: could not write metrics: {e}")

    @property
    def world(self) -> swarmbox_sdk.World:
        if not self._world:
            raise RuntimeError("environment not started")
        return self._world

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None) -> ExecResult:
        return await self.service_exec(
            command, service=MAIN, cwd=cwd, env=env, timeout_sec=timeout_sec, user=user
        )

    async def service_exec(
        self, command, *, service=None, cwd=None, env=None, timeout_sec=None, user=None
    ) -> ExecResult:
        sandbox = service or MAIN
        user = self._resolve_user(user)
        if user not in (None, 0, "0", "root"):
            raise NotImplementedError(f"swarmbox: exec as user {user!r} is not supported yet")
        if sandbox == MAIN:
            # Harbor builds main and it always has bash; sidecars may not.
            argv = ["bash", "-c", command]
            cwd = cwd or self.task_env_config.workdir
            env = self._merge_env(env)
        else:
            argv = ["sh", "-c", command]
        res = await self.world.exec(sandbox, argv, env=env, workdir=cwd, timeout=timeout_sec)
        if res.timed_out:
            raise RuntimeError(f"Command timed out after {timeout_sec} seconds")
        return ExecResult(stdout=res.stdout, stderr=res.stderr, return_code=res.exit_code)

    async def upload_file(self, source_path, target_path):
        await self.world.upload(MAIN, source_path, target_path)

    async def upload_dir(self, source_dir, target_dir):
        await self.world.upload(MAIN, source_dir, target_dir)

    async def download_file(self, source_path, target_path):
        await self.world.download(MAIN, source_path, Path(target_path))

    async def download_dir(self, source_dir, target_dir):
        await self.world.download(MAIN, source_dir, Path(target_dir))

    async def service_download_file(self, source_path, target_path, *, service=None):
        await self.world.download(service or MAIN, source_path, Path(target_path))

    async def service_download_dir(self, source_dir, target_dir, *, service=None):
        await self.world.download(service or MAIN, source_dir, Path(target_dir))

    async def stop_service(self, service: str) -> None:
        # Stopping one Sandbox would fail the whole World (a World is placed
        # and destroyed as a unit), taking the service holding the evidence
        # with it. Recorded as a divergent-lifecycle case for the World-model
        # experiment (docs/plan.md, M2); main is left running.
        self.logger.warning(
            f"swarmbox: stop_service({service!r}) is a no-op; Sandboxes cannot stop independently"
        )


# How long a create refused for capacity (or never connected) is retried,
# attempts included: well inside Harbor's default start timeout (600 s), so
# a trial still fails if the platform stays full.
CAPACITY_RETRY_WINDOW_S = 300.0


async def create_world_retrying(
    client, sandboxes, ttl, *, window_s=CAPACITY_RETRY_WINDOW_S, sleep=asyncio.sleep, clock=time.monotonic
):
    """Create a World, retrying while the platform refuses for capacity or
    can't be reached.

    A 503 means the platform was busy and created nothing; a connection that
    never opened (refused or timed out, e.g. to a control VM the load
    balancer hasn't yet noticed is down) sent nothing. Both are safe to
    retry. Other errors, including a connection lost mid-request, are not:
    the World may exist. Waits 2, 4, 8 ... seconds (at most 30) as long as
    the next attempt starts within window_s of the first, counting the time
    attempts take (a connection to a dead VM can hang for minutes), then lets
    the error fail the trial. Returns the World and how many times it
    retried.
    """
    deadline = clock() + window_s
    backoff, retries = 2.0, 0
    while True:
        try:
            return await client.create_world(sandboxes, ttl=ttl), retries
        except (swarmbox_sdk.SwarmboxError, httpx.ConnectError, httpx.ConnectTimeout) as e:
            retryable = not isinstance(e, swarmbox_sdk.SwarmboxError) or e.status == 503
            if not retryable or clock() + backoff > deadline:
                raise
        await sleep(backoff)
        retries += 1
        backoff = min(backoff * 2, 30.0)
