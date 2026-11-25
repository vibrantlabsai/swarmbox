"""Long execs: Harbor runs a whole agent as one exec with no timeout of its
own, and the platform's default (10 minutes) or the client's HTTP timeout
(600 s) must not end it first."""

import asyncio
import json

import httpx
import pytest
import swarmbox_sdk
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths

from swarmbox_sdk.client import EXEC_HTTP_MARGIN_S, PLATFORM_EXEC_TIMEOUT_S
from swarmbox_sdk.harbor.environment import SwarmboxEnvironment

RESULT = {"exit_code": 0, "stdout": "", "stderr": ""}


class FakeAPI:
    """Answers every exec with RESULT and keeps the requests."""

    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=RESULT)

    def world(self, **client_kw) -> swarmbox_sdk.World:
        c = swarmbox_sdk.Client("http://api.test", "token", **client_kw)
        c._http = httpx.AsyncClient(
            base_url="http://api.test", transport=httpx.MockTransport(self), timeout=c._http.timeout
        )
        return swarmbox_sdk.World(c, {"id": "node.w", "state": "ready"})

    def body(self) -> dict:
        return json.loads(self.requests[-1].content)

    def read_timeout(self) -> float | None:
        return self.requests[-1].extensions["timeout"]["read"]


def provider(tmp_path, api: FakeAPI, **kw) -> SwarmboxEnvironment:
    (tmp_path / "environment").mkdir()
    (tmp_path / "environment" / "Dockerfile").write_text("FROM alpine:3.20\n")
    env = SwarmboxEnvironment(
        environment_dir=tmp_path / "environment",
        environment_name="task",
        session_id="task__abc__env",
        trial_paths=TrialPaths(tmp_path / "trial"),
        task_env_config=EnvironmentConfig(),
        url="http://api.test",
        token="token",
        **kw,
    )
    env._world = api.world()
    return env


@pytest.mark.parametrize("ttl, seconds", [(None, 3 * 3600), ("90m", 5400), ("2h30m", 9000), ("7200", 7200)])
def test_provider_exec_without_a_timeout_may_run_as_long_as_the_world(tmp_path, ttl, seconds):
    api = FakeAPI()
    env = provider(tmp_path, api, **({"ttl": ttl} if ttl else {}))
    asyncio.run(env.exec("claude --print ...", timeout_sec=None))
    assert api.body()["timeout"] == seconds
    assert api.read_timeout() >= seconds


def test_provider_exec_passes_harbors_timeout_through(tmp_path):
    api = FakeAPI()
    env = provider(tmp_path, api)
    asyncio.run(env.exec("pytest", timeout_sec=1200))
    assert api.body()["timeout"] == 1200


def test_provider_refuses_a_ttl_it_cannot_read(tmp_path):
    with pytest.raises(ValueError, match="ttl"):
        provider(tmp_path, FakeAPI(), ttl="three hours")


@pytest.mark.parametrize("timeout", [900, 1800, 4 * 3600])
def test_client_exec_waits_for_the_response_at_least_as_long_as_the_exec_may_run(timeout):
    api = FakeAPI()
    asyncio.run(api.world().exec("main", "sleep 1", timeout=timeout))
    assert api.body()["timeout"] == timeout
    assert api.read_timeout() >= timeout + EXEC_HTTP_MARGIN_S


def test_client_exec_without_a_timeout_outwaits_the_platforms_default():
    # The platform kills it at its 10-minute default and answers just after;
    # a 600 s read timeout would race that answer.
    api = FakeAPI()
    asyncio.run(api.world().exec("main", "sleep 1"))
    assert "timeout" not in api.body()
    assert api.read_timeout() >= PLATFORM_EXEC_TIMEOUT_S + EXEC_HTTP_MARGIN_S


def test_client_exec_keeps_a_longer_client_timeout_and_no_timeout():
    api = FakeAPI()
    asyncio.run(api.world(timeout=7200).exec("main", "true", timeout=5))
    assert api.read_timeout() == 7200
    asyncio.run(api.world(timeout=None).exec("main", "true", timeout=5))
    assert api.read_timeout() is None
