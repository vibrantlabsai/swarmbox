"""Build and push the images for many Harbor tasks ahead of a run.

    uv run python -m swarmbox_sdk.harbor.prebuild --registry myacr.azurecr.io -j 8 \\
        --out prebuild.jsonl tasks/*

Uses the provider's own content-addressed path, so anything built here is a
cache hit at trial start. Writes one JSON line per image, failures included.

With --lazy-store, each image is also converted into the lazy image store
(a read-write mount of it, on the machine that builds), so nodes can start it
without pulling it whole. Conversion is idempotent; a rerun only checks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import tomllib
from pathlib import Path

from swarmbox_sdk.harbor.compose import plan_services
from swarmbox_sdk.harbor.images import compressed_size, convert_lazy, default_platform, resolve_image


def task_environments(task: Path) -> list[tuple[str, Path, str | None]]:
    """(role, environment dir, prebuilt docker_image) for each environment a
    trial of this task starts: the agent's, and a separate verifier's."""
    cfg = tomllib.loads((task / "task.toml").read_text())
    envs = [("agent", task / "environment", cfg.get("environment", {}).get("docker_image"))]
    verifier = cfg.get("verifier", {})
    if verifier.get("environment_mode") == "separate":
        envs.append(("verifier", task / "tests", verifier.get("environment", {}).get("docker_image")))
    return envs


async def prebuild_task(
    task: Path,
    registry: str,
    platform: str,
    sem: asyncio.Semaphore,
    lazy_store: Path | None = None,
    convert_bin: str = "swarmbox-convert",
) -> list[dict]:
    rows = []
    async with sem:
        for role, env_dir, docker_image in task_environments(task):
            try:
                plans = plan_services(env_dir, docker_image, prefer_prebuilt=True)
            except Exception as e:  # noqa: BLE001 - report every failure, keep going
                rows.append({"task": task.name, "role": role, "error": f"plan: {e}"})
                continue
            for plan in plans:
                row = {"task": task.name, "role": role, "service": plan.name}
                start = time.monotonic()
                try:
                    rep = await resolve_image(plan, registry, platform=platform)
                    row |= {
                        "status": rep.status,
                        "seconds": round(rep.seconds, 2),
                        "ref": rep.ref,
                        "compressed_bytes": await compressed_size(rep.ref, platform),
                    }
                    if lazy_store is not None:
                        lazy = await convert_lazy(rep.ref, lazy_store, platform, convert_bin)
                        row["lazy"] = {k: lazy.get(k) for k in ("existing", "layers", "layers_built", "bytes", "seconds")}
                except Exception as e:  # noqa: BLE001
                    row |= {"error": str(e)[-1000:], "seconds": round(time.monotonic() - start, 2)}
                rows.append(row)
    return rows


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks", nargs="+", type=Path, help="Harbor task directories")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--platform", default=default_platform())
    ap.add_argument("-j", "--jobs", type=int, default=4, help="tasks built concurrently")
    ap.add_argument("--out", type=Path, default=Path("prebuild.jsonl"))
    ap.add_argument("--lazy-store", type=Path, help="also convert each image into this image store (read-write mount)")
    ap.add_argument("--convert", default="swarmbox-convert", help="the swarmbox-convert binary, for --lazy-store")
    args = ap.parse_args()

    sem = asyncio.Semaphore(args.jobs)
    tasks = [t for t in args.tasks if (t / "task.toml").exists()]
    failures = built = cached = 0
    with args.out.open("w") as out:
        jobs = [prebuild_task(t, args.registry, args.platform, sem, args.lazy_store, args.convert) for t in tasks]
        for coro in asyncio.as_completed(jobs):
            for row in await coro:
                out.write(json.dumps(row) + "\n")
                out.flush()
                if "error" in row:
                    failures += 1
                    print(f"FAIL {row['task']}/{row.get('service', '?')}: {row['error'][:200]}", file=sys.stderr)
                elif row["status"] == "built":
                    built += 1
                else:
                    cached += 1
    print(f"{len(tasks)} tasks: {built} built, {cached} cached, {failures} failed -> {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
