"""Translate the subset of docker-compose Harbor tasks use into a World's Sandboxes.

Anything outside the subset is rejected, never approximated: a silently
dropped key (a missing alias, a missing mount) produces a degraded task setup that
can still score, which is worse than a trial that refuses to start.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

import yaml

MAIN = "main"

SUPPORTED_KEYS = {
    "image",
    "build",
    "command",
    "environment",
    "volumes",
    "expose",
    "networks",
    "healthcheck",
    "depends_on",
}


class UnsupportedCompose(ValueError):
    pass


@dataclass
class FileMount:
    source: Path  # on the host, resolved against the compose file's directory
    target: str  # inside the Sandbox


@dataclass
class ServicePlan:
    """One compose service, before images are built and pushed."""

    name: str
    image: str | None = None
    build_context: Path | None = None
    dockerfile: str | None = None
    command: list[str] | None = None
    env: dict[str, str] = field(default_factory=dict)
    files: list[FileMount] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    readiness: list[str] | None = None
    readiness_interval_s: float = 1.0
    readiness_timeout_s: float = 60.0


def plan_services(
    environment_dir: Path, docker_image: str | None, prefer_prebuilt: bool
) -> list[ServicePlan]:
    """Harbor's base `main` service merged with the task's compose file."""
    main = ServicePlan(name=MAIN, command=["sh", "-c", "sleep infinity"])
    dockerfile = environment_dir / "Dockerfile"
    if docker_image and (prefer_prebuilt or not dockerfile.exists()):
        main.image = docker_image
    elif dockerfile.exists():
        main.build_context = environment_dir
    plans = {MAIN: main}

    compose_path = environment_dir / "docker-compose.yaml"
    if compose_path.exists():
        doc = yaml.safe_load(compose_path.read_text()) or {}
        if extra := set(doc) - {"services"}:
            raise UnsupportedCompose(f"top-level keys not supported: {sorted(extra)}")
        for name, svc in (doc.get("services") or {}).items():
            plans[name] = _merge(plans.get(name) or ServicePlan(name=name), svc or {}, environment_dir)

    for p in plans.values():
        if not p.image and not p.build_context:
            raise UnsupportedCompose(f"service {p.name!r} has neither image nor build")
    return list(plans.values())


def _merge(p: ServicePlan, svc: dict, base: Path) -> ServicePlan:
    if extra := set(svc) - SUPPORTED_KEYS:
        raise UnsupportedCompose(f"service {p.name!r}: keys not supported: {sorted(extra)}")
    if "image" in svc:
        p.image = svc["image"]
    if "build" in svc:
        b = svc["build"]
        if isinstance(b, str):
            b = {"context": b}
        if extra := set(b) - {"context", "dockerfile"}:
            raise UnsupportedCompose(f"service {p.name!r}: build keys not supported: {sorted(extra)}")
        p.build_context = (base / b.get("context", ".")).resolve()
        p.dockerfile = b.get("dockerfile")
        p.image = None
    if "command" in svc:
        c = svc["command"]
        p.command = shlex.split(c) if isinstance(c, str) else [str(x) for x in c]
    if "environment" in svc:
        env = svc["environment"]
        if isinstance(env, list):
            env = dict(e.split("=", 1) for e in env)
        p.env.update({k: str(v) for k, v in env.items()})
    for v in svc.get("volumes", []):
        p.files.append(_file_mount(p.name, v, base))
    p.aliases += _aliases(p.name, svc.get("networks"))
    if "healthcheck" in svc:
        _readiness(p, svc["healthcheck"])
    # depends_on is satisfied by construction: a World is ready only when
    # every Sandbox's readiness probe passes, and nothing runs before that.
    for dep, cond in _depends_on(svc.get("depends_on")).items():
        if cond not in ("service_started", "service_healthy"):
            raise UnsupportedCompose(f"service {p.name!r}: depends_on {dep} condition {cond!r}")
    return p


def _file_mount(service: str, v, base: Path) -> FileMount:
    if not isinstance(v, str):
        raise UnsupportedCompose(f"service {service!r}: long-form volumes not supported")
    parts = v.split(":")
    if len(parts) not in (2, 3) or not parts[0].startswith("."):
        raise UnsupportedCompose(
            f"service {service!r}: only read-only binds of task files are supported, got {v!r}"
        )
    if len(parts) == 3 and parts[2] != "ro":
        raise UnsupportedCompose(f"service {service!r}: volume {v!r} must be :ro")
    src = (base / parts[0]).resolve()
    if not src.exists():
        raise UnsupportedCompose(f"service {service!r}: volume source {src} does not exist")
    return FileMount(source=src, target=parts[1])


def _aliases(service: str, networks) -> list[str]:
    if networks is None or isinstance(networks, list):
        if networks and networks != ["default"]:
            raise UnsupportedCompose(f"service {service!r}: only the default network is supported")
        return []
    out = []
    for net, cfg in networks.items():
        if net != "default":
            raise UnsupportedCompose(f"service {service!r}: only the default network is supported")
        cfg = cfg or {}
        if extra := set(cfg) - {"aliases"}:
            raise UnsupportedCompose(f"service {service!r}: network keys not supported: {sorted(extra)}")
        out += cfg.get("aliases", [])
    return out


def _readiness(p: ServicePlan, hc: dict) -> None:
    if extra := set(hc) - {"test", "interval", "timeout", "retries", "start_period"}:
        raise UnsupportedCompose(f"service {p.name!r}: healthcheck keys not supported: {sorted(extra)}")
    test = hc["test"]
    if isinstance(test, str):
        p.readiness = ["sh", "-c", test]
    elif test[0] == "CMD":
        p.readiness = [str(x) for x in test[1:]]
    elif test[0] == "CMD-SHELL":
        p.readiness = ["sh", "-c", test[1]]
    else:
        raise UnsupportedCompose(f"service {p.name!r}: healthcheck test {test[0]!r}")
    interval = _seconds(hc.get("interval", "30s"))
    p.readiness_interval_s = interval
    p.readiness_timeout_s = _seconds(hc.get("start_period", "0s")) + interval * hc.get("retries", 3)


def _depends_on(d) -> dict[str, str]:
    if d is None:
        return {}
    if isinstance(d, list):
        return {k: "service_started" for k in d}
    return {k: (v or {}).get("condition", "service_started") for k, v in d.items()}


def _seconds(s) -> float:
    if isinstance(s, (int, float)):
        return float(s)
    units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
    for u in ("ms", "s", "m", "h"):
        if s.endswith(u) and s[: -len(u)].replace(".", "", 1).isdigit():
            return float(s[: -len(u)]) * units[u]
    raise UnsupportedCompose(f"duration {s!r}")
