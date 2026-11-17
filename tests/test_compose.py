from pathlib import Path

import pytest

from swarmbox_sdk.harbor.compose import MAIN, UnsupportedCompose, plan_services
from swarmbox_sdk.harbor.images import content_hash


def make_env(tmp_path: Path, compose: str | None = None, dockerfile: bool = True) -> Path:
    env = tmp_path / "environment"
    env.mkdir()
    if dockerfile:
        (env / "Dockerfile").write_text("FROM python:3.12-slim\n")
    if compose is not None:
        (env / "docker-compose.yaml").write_text(compose)
    return env


def by_name(plans):
    return {p.name: p for p in plans}


def test_dockerfile_only_builds_main(tmp_path):
    env = make_env(tmp_path)
    (main,) = plan_services(env, None, prefer_prebuilt=True)
    assert main.name == MAIN
    assert main.build_context == env
    assert main.command == ["sh", "-c", "sleep infinity"]


def test_prebuilt_image_preferred_unless_forced(tmp_path):
    env = make_env(tmp_path)
    assert plan_services(env, "img:1", prefer_prebuilt=True)[0].image == "img:1"
    assert plan_services(env, "img:1", prefer_prebuilt=False)[0].build_context == env


def test_prebuilt_image_used_without_dockerfile(tmp_path):
    env = make_env(tmp_path, dockerfile=False)
    assert plan_services(env, "img:1", prefer_prebuilt=False)[0].image == "img:1"


def test_sidecar_translation(tmp_path):
    env = make_env(
        tmp_path,
        """
services:
  main:
    depends_on:
      api: {condition: service_healthy}
  api:
    image: api:latest
    command: ["serve", "--port", "8080"]
    environment:
      MODE: test
      RETRIES: 3
    volumes: ["./seed.json:/task/seed.json:ro"]
    networks:
      default:
        aliases: [api.internal, search.internal]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080"]
      interval: 2s
      retries: 20
      start_period: 3s
""",
    )
    (env / "seed.json").write_text("{}")
    plans = by_name(plan_services(env, None, prefer_prebuilt=True))
    api = plans["api"]
    assert api.image == "api:latest"
    assert api.command == ["serve", "--port", "8080"]
    assert api.env == {"MODE": "test", "RETRIES": "3"}
    assert [(f.source.name, f.target) for f in api.files] == [("seed.json", "/task/seed.json")]
    assert api.aliases == ["api.internal", "search.internal"]
    assert api.readiness == ["curl", "-f", "http://localhost:8080"]
    assert api.readiness_interval_s == 2
    assert api.readiness_timeout_s == 3 + 2 * 20


@pytest.mark.parametrize(
    "service, match",
    [
        ("image: x\n    ports: ['8080:8080']", "keys not supported"),
        ("image: x\n    volumes: ['/etc:/etc']", "read-only binds"),
        ("image: x\n    volumes: ['./missing:/m:ro']", "does not exist"),
        ("image: x\n    networks: [backend]", "default network"),
        ("image: x\n    depends_on: {main: {condition: service_completed_successfully}}", "condition"),
        ("image: x\n    healthcheck: {test: ['NONE']}", "healthcheck test"),
        ("command: ['x']", "neither image nor build"),
    ],
)
def test_unsupported_compose_fails_loudly(tmp_path, service, match):
    env = make_env(tmp_path, f"services:\n  side:\n    {service}\n")
    with pytest.raises(UnsupportedCompose, match=match):
        plan_services(env, None, prefer_prebuilt=True)


def test_unknown_top_level_key_rejected(tmp_path):
    env = make_env(tmp_path, "services: {}\nvolumes: {data: {}}\n")
    with pytest.raises(UnsupportedCompose, match="top-level"):
        plan_services(env, None, prefer_prebuilt=True)


def test_content_hash_tracks_inputs(tmp_path):
    env = make_env(tmp_path)
    (main,) = plan_services(env, None, prefer_prebuilt=True)
    base = content_hash(main, "linux/amd64")

    assert content_hash(main, "linux/amd64") == base, "deterministic"
    assert content_hash(main, "linux/arm64") != base, "platform matters"

    (env / "extra.txt").write_text("x")
    assert content_hash(main, "linux/amd64") != base, "context files matter"

    (env / ".DS_Store").write_text("junk")
    with_junk = content_hash(main, "linux/amd64")
    (env / ".DS_Store").unlink()
    assert content_hash(main, "linux/amd64") == with_junk, "ignored files do not matter"

    script = env / "run.sh"
    script.write_text("echo hi")
    before = content_hash(main, "linux/amd64")
    script.chmod(0o755)
    assert content_hash(main, "linux/amd64") != before, "exec bit matters"
