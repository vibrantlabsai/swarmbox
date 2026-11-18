"""Images the platform builds (ADR 0009): the provider's build contexts, and
the SDK's build_image against a fake API."""

import asyncio
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import swarmbox_sdk
from swarmbox_sdk import context_tag
from swarmbox_sdk.harbor import images
from swarmbox_sdk.harbor.compose import FileMount, plan_services
from swarmbox_sdk.harbor.environment import SwarmboxEnvironment
from swarmbox_sdk.harbor.images import build_context, platform_image

REF = "myacr.azurecr.io/swarmbox/builds/alice@sha256:" + "c" * 64


def make_env(tmp_path: Path, dockerfile: bool = True) -> Path:
    env = tmp_path / "environment"
    env.mkdir()
    if dockerfile:
        (env / "Dockerfile").write_text("FROM python:3.12-slim\n")
    return env


def test_context_tag_tracks_inputs(tmp_path):
    env = make_env(tmp_path)
    base = context_tag(env)

    assert context_tag(env) == base, "deterministic"
    assert context_tag(env, "other.Dockerfile") != base, "the Dockerfile's name matters"

    (env / "extra.txt").write_text("x")
    assert context_tag(env) != base, "context files matter"

    (env / ".DS_Store").write_text("junk")
    with_junk = context_tag(env)
    (env / ".DS_Store").unlink()
    assert context_tag(env) == with_junk, "ignored files do not matter"

    script = env / "run.sh"
    script.write_text("echo hi")
    before = context_tag(env)
    script.chmod(0o755)
    assert context_tag(env) != before, "exec bit matters"


def test_build_context_is_the_task_dir_when_nothing_is_baked(tmp_path):
    env = make_env(tmp_path)
    (main,) = plan_services(env, None, prefer_prebuilt=True)
    with build_context(main) as (ctx, dockerfile):
        assert (ctx, dockerfile) == (env, "Dockerfile")


def test_build_context_bakes_mounted_files(tmp_path):
    env = make_env(tmp_path)
    (env / "seed.json").write_text("{}")
    (env / "fixtures").mkdir()
    (env / "fixtures" / "a.txt").write_text("a")
    (main,) = plan_services(env, None, prefer_prebuilt=True)
    main.files = [FileMount(env / "seed.json", "/task/seed.json"), FileMount(env / "fixtures", "/task/fixtures")]

    with build_context(main) as (ctx, dockerfile):
        assert ctx != env, "the task's own directory is never modified"
        assert (ctx / "seed.json").exists(), "the original context is kept"
        lines = (ctx / dockerfile).read_text().splitlines()
        assert lines[0] == "FROM python:3.12-slim", "the original Dockerfile comes first"
        assert lines[1:] == ["COPY .opendsec-files/f0 /task/seed.json", "COPY .opendsec-files/f1 /task/fixtures"]
        assert (ctx / ".opendsec-files/f1/a.txt").read_text() == "a"
        tag = context_tag(ctx, dockerfile)
    assert not ctx.exists(), "the generated context is temporary"
    with build_context(main) as (ctx, dockerfile):
        assert context_tag(ctx, dockerfile) == tag, "the same files give the same tag"


def test_image_only_service_with_files_builds_on_top(tmp_path):
    env = make_env(tmp_path, dockerfile=False)
    (env / "seed.json").write_text("{}")
    (main,) = plan_services(env, "img:1", prefer_prebuilt=True)
    main.files = [FileMount(env / "seed.json", "/seed.json")]
    with build_context(main) as (ctx, dockerfile):
        assert (ctx / dockerfile).read_text() == "FROM img:1\nCOPY .opendsec-files/f0 /seed.json\n"


class FakeClient:
    """Stands in for swarmbox_sdk.Client.build_image."""

    def __init__(self, cached: bool = False):
        self.cached = cached
        self.calls: list[tuple[Path, str, bool]] = []

    async def build_image(self, context, dockerfile="Dockerfile", *, force=False):
        self.calls.append((Path(context), dockerfile, force))
        await asyncio.sleep(0.01)  # trials that start together overlap here
        return swarmbox_sdk.Image(tag="0" * 32, ref=REF, state="ready", cached=self.cached)


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    monkeypatch.setattr(images, "_platform_cache", {})
    monkeypatch.setattr(images, "_locks", {})


def test_platform_image_runs_a_named_image_as_is(tmp_path):
    env = make_env(tmp_path, dockerfile=False)
    (main,) = plan_services(env, "docker.io/library/alpine:3.20", prefer_prebuilt=True)
    client = FakeClient()
    rep = asyncio.run(platform_image(client, main))
    assert (rep.ref, rep.status) == ("docker.io/library/alpine:3.20", "public")
    assert client.calls == [], "nothing to build: the node pulls it"


def test_platform_image_builds_once_for_trials_that_start_together(tmp_path):
    env = make_env(tmp_path)
    (main,) = plan_services(env, None, prefer_prebuilt=True)
    client = FakeClient()

    async def trials():
        return await asyncio.gather(*(platform_image(client, main) for _ in range(8)))

    reports = asyncio.run(trials())
    assert [c[:2] for c in client.calls] == [(env, "Dockerfile")], "one upload for eight trials"
    assert {r.ref for r in reports} == {REF}
    assert sorted(r.status for r in reports) == ["built"] + ["cached"] * 7


def test_platform_image_reports_an_image_the_platform_already_had(tmp_path):
    env = make_env(tmp_path)
    (main,) = plan_services(env, None, prefer_prebuilt=True)
    rep = asyncio.run(platform_image(FakeClient(cached=True), main))
    assert (rep.ref, rep.status) == (REF, "cached")


def test_force_build_reaches_the_platform(tmp_path):
    env = make_env(tmp_path)
    (main,) = plan_services(env, None, prefer_prebuilt=False)
    client = FakeClient()
    asyncio.run(platform_image(client, main, force_build=True))
    assert client.calls[0][2] is True


def test_node_ref_renames_only_images_this_machine_pushed():
    dev = SimpleNamespace(_registry="localhost:5001", _pull_registry="host.lima.internal:5001")
    assert (
        SwarmboxEnvironment._node_ref(dev, "localhost:5001/swarmbox/task-images@sha256:abc")
        == "host.lima.internal:5001/swarmbox/task-images@sha256:abc"
    )
    assert SwarmboxEnvironment._node_ref(dev, "docker.io/library/alpine:3.20") == "docker.io/library/alpine:3.20"
    # Without a registry the platform built it: its ref is already the nodes'.
    platform = SimpleNamespace(_registry=None, _pull_registry=None)
    assert SwarmboxEnvironment._node_ref(platform, REF) == REF


class FakeAPI:
    """/v1/images/{tag} as the apiserver answers it, scripted per request."""

    def __init__(self, answers):
        self.answers = list(answers)  # (method, status, body)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        method, status, body = self.answers.pop(0)
        assert request.method == method, f"got {request.method} {request.url}, scripted {method}"
        return httpx.Response(status, json=body)

    def client(self) -> swarmbox_sdk.Client:
        c = swarmbox_sdk.Client("http://api.test", "token")
        c._http = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(self))
        return c


def image(state: str, **kw) -> dict:
    return {"tag": "t", "state": state} | kw


def build(api: FakeAPI, env: Path, **kw):
    async def run():
        async with api.client() as c:
            return await c.build_image(env, poll=0.001, **kw)

    return asyncio.run(run())


def test_build_image_uploads_the_context_and_waits(tmp_path):
    env = make_env(tmp_path)
    (env / "app.py").write_text("print('hi')\n")
    api = FakeAPI(
        [
            ("GET", 404, {"error": "image not found"}),
            ("PUT", 202, image("building")),
            ("GET", 200, image("building")),
            ("GET", 200, image("ready", ref=REF, build_ms=1200)),
        ]
    )
    img = build(api, env)
    assert (img.ref, img.state, img.cached, img.build_ms) == (REF, "ready", False, 1200)

    put = api.requests[1]
    tag = context_tag(env)
    assert put.url.path == f"/v1/images/{tag}" and put.url.params["dockerfile"] == "Dockerfile"
    with tarfile.open(fileobj=io.BytesIO(put.content)) as tar:
        assert sorted(tar.getnames()) == ["Dockerfile", "app.py"]


def test_a_link_out_of_the_context_is_uploaded_as_its_file(tmp_path):
    env = make_env(tmp_path)
    shared = tmp_path / "shared.txt"
    shared.write_text("shared across tasks\n")
    (env / "shared.txt").symlink_to(shared)
    api = FakeAPI([("GET", 404, {"error": "image not found"}), ("PUT", 200, image("ready", ref=REF))])
    build(api, env)
    with tarfile.open(fileobj=io.BytesIO(api.requests[1].content)) as tar:
        member = tar.getmember("shared.txt")
        assert member.isfile(), "the file, not a link that would dangle on the platform"
        assert tar.extractfile(member).read() == b"shared across tasks\n"


def test_image_keeps_its_0_2_0_field_order():
    img = swarmbox_sdk.Image("t", REF, "ready")
    assert (img.tag, img.ref, img.state) == ("t", REF, "ready")


def test_build_image_is_a_lookup_when_the_platform_has_it(tmp_path):
    api = FakeAPI([("GET", 200, image("ready", ref=REF))])
    img = build(api, make_env(tmp_path))
    assert (img.ref, img.cached) == (REF, True)
    assert [r.method for r in api.requests] == ["GET"], "nothing uploaded"


def test_build_image_raises_with_the_build_log(tmp_path):
    api = FakeAPI(
        [
            ("GET", 404, {"error": "image not found"}),
            ("PUT", 202, image("building")),
            ("GET", 200, image("failed", error="build failed (exit status 1); see log", log="RUN false\nexit code: 1")),
        ]
    )
    with pytest.raises(swarmbox_sdk.BuildFailed) as e:
        build(api, make_env(tmp_path))
    assert "RUN false" in e.value.log and "exit status 1" in e.value.error


def test_build_image_waits_its_turn_when_the_queue_is_full(tmp_path):
    api = FakeAPI(
        [
            ("GET", 404, {"error": "image not found"}),
            ("PUT", 429, {"error": "too many image builds queued"}),
            ("PUT", 200, image("ready", ref=REF)),
        ]
    )
    assert build(api, make_env(tmp_path)).ref == REF


def test_build_image_says_when_the_platform_builds_nothing(tmp_path):
    api = FakeAPI(
        [
            ("GET", 501, {"error": "image builds are not enabled here: give Sandboxes an image the nodes can pull"}),
        ]
    )
    with pytest.raises(swarmbox_sdk.SwarmboxError) as e:
        build(api, make_env(tmp_path))
    assert e.value.status == 501 and "not enabled" in str(e.value)
    assert len(api.requests) == 1, "nothing uploaded"


def test_build_image_refuses_a_context_without_its_dockerfile(tmp_path):
    api = FakeAPI([])
    with pytest.raises(swarmbox_sdk.SwarmboxError, match="no Dockerfile in the build context"):
        build(api, make_env(tmp_path, dockerfile=False))
    with pytest.raises(swarmbox_sdk.SwarmboxError, match="no Dockerfile"):
        build(api, tmp_path / "missing")
    assert api.requests == [], "nothing asked of the platform"
