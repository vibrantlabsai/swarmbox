import asyncio
import json
import stat
from pathlib import Path

import pytest

from swarmbox_sdk.harbor import prebuild
from swarmbox_sdk.harbor.images import ImageReport, convert_lazy

REF = "myacr.azurecr.io/swarmbox/task-images@sha256:" + "a" * 64


def fake_convert(tmp_path: Path, report: dict, exit_code: int = 0) -> tuple[str, Path]:
    """A stand-in swarmbox-convert: records its arguments, prints report."""
    args_file = tmp_path / "args.json"
    script = tmp_path / "swarmbox-convert"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"json.dump(sys.argv[1:], open({str(args_file)!r}, 'w'))\n"
        "print('some log line')\n"
        f"print(json.dumps({report!r}))\n"
        f"sys.exit({exit_code})\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script), args_file


def test_convert_lazy_runs_the_converter_on_the_digest(tmp_path):
    report = {"ok": True, "existing": False, "layers": 4, "layers_built": 3, "bytes": 123, "seconds": 1.5}
    binary, args_file = fake_convert(tmp_path, report)
    got = asyncio.run(convert_lazy(REF, tmp_path / "store", "linux/amd64", binary))
    assert got["layers_built"] == 3
    assert json.loads(args_file.read_text()) == ["-store", str(tmp_path / "store"), "-platform", "linux/amd64", REF]


def test_convert_lazy_passes_insecure_for_local_registries(tmp_path):
    binary, args_file = fake_convert(tmp_path, {"ok": True})
    asyncio.run(convert_lazy("localhost:5001/x@sha256:" + "b" * 64, tmp_path, "linux/arm64", binary))
    assert "-insecure" in json.loads(args_file.read_text())


def test_convert_lazy_raises_with_the_converters_error(tmp_path):
    binary, _ = fake_convert(tmp_path, {"ok": False, "error": "mkfs.erofs not found"}, exit_code=1)
    with pytest.raises(RuntimeError, match="mkfs.erofs not found"):
        asyncio.run(convert_lazy(REF, tmp_path, "linux/amd64", binary))


def test_prebuild_converts_each_image_when_asked(tmp_path, monkeypatch):
    task = tmp_path / "task"
    (task / "environment").mkdir(parents=True)
    (task / "environment" / "Dockerfile").write_text("FROM python:3.12-slim\n")
    (task / "task.toml").write_text("")

    async def fake_resolve(plan, registry, *, platform):
        return ImageReport(plan.name, REF, "built", 2.0)

    async def fake_size(ref, plat):
        return 1000

    monkeypatch.setattr(prebuild, "resolve_image", fake_resolve)
    monkeypatch.setattr(prebuild, "compressed_size", fake_size)
    binary, _ = fake_convert(tmp_path, {"ok": True, "existing": True, "layers": 4, "layers_built": 0, "bytes": 9, "seconds": 0.1})

    sem = asyncio.Semaphore(1)
    (row,) = asyncio.run(prebuild.prebuild_task(task, "myacr.azurecr.io", "linux/amd64", sem, tmp_path / "store", binary))
    assert row["ref"] == REF
    assert row["lazy"] == {"existing": True, "layers": 4, "layers_built": 0, "bytes": 9, "seconds": 0.1}

    (plain,) = asyncio.run(prebuild.prebuild_task(task, "myacr.azurecr.io", "linux/amd64", sem))
    assert "lazy" not in plain, "no store, no conversion"


def test_a_failed_conversion_is_a_failed_row(tmp_path, monkeypatch):
    task = tmp_path / "task"
    (task / "environment").mkdir(parents=True)
    (task / "environment" / "Dockerfile").write_text("FROM python:3.12-slim\n")
    (task / "task.toml").write_text("")

    async def fake_resolve(plan, registry, *, platform):
        return ImageReport(plan.name, REF, "cached", 0.0)

    async def fake_size(ref, plat):
        return 1

    monkeypatch.setattr(prebuild, "resolve_image", fake_resolve)
    monkeypatch.setattr(prebuild, "compressed_size", fake_size)
    binary, _ = fake_convert(tmp_path, {"ok": False, "error": "registry 401"}, exit_code=1)
    (row,) = asyncio.run(prebuild.prebuild_task(task, "r", "linux/amd64", asyncio.Semaphore(1), tmp_path, binary))
    assert "registry 401" in row["error"]
