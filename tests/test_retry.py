import asyncio

import httpx
import swarmbox_sdk
import pytest

from swarmbox_sdk.harbor.environment import create_world_retrying


class FakeClient:
    """Fails the first `refusals` creates, with `status` or with `error` if
    given, then succeeds."""

    def __init__(self, refusals: int, status: int = 503, error: Exception | None = None, attempt_s: float = 0):
        self.refusals, self.status, self.error, self.calls = refusals, status, error, 0
        self.attempt_s, self.now = attempt_s, [0.0]  # each attempt takes attempt_s of the fake clock

    async def create_world(self, sandboxes, ttl):
        self.calls += 1
        self.now[0] += self.attempt_s
        if self.calls <= self.refusals:
            if self.error:
                raise self.error
            raise swarmbox_sdk.SwarmboxError(f"POST /v1/worlds: {self.status} no capacity", status=self.status)
        return "world"


def run(client, window_s=300.0):
    slept = []

    async def sleep(s):
        slept.append(s)
        client.now[0] += s

    world, retries = asyncio.run(
        create_world_retrying(client, [], "1h", window_s=window_s, sleep=sleep, clock=lambda: client.now[0])
    )
    return world, retries, slept


def test_capacity_refusals_are_retried_with_backoff():
    world, retries, slept = run(FakeClient(refusals=3))
    assert world == "world" and retries == 3
    assert slept == [2.0, 4.0, 8.0]


def test_backoff_is_capped():
    _, _, slept = run(FakeClient(refusals=6))
    assert slept == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


def test_gives_up_after_the_window():
    # 2 + 4 = 6 s fit in a 7 s window; the next wait (8 s) does not.
    client = FakeClient(refusals=100)
    with pytest.raises(swarmbox_sdk.SwarmboxError) as e:
        run(client, window_s=7)
    assert e.value.status == 503 and client.calls == 3


@pytest.mark.parametrize("status", [400, 404, 429, 500])
def test_other_errors_are_not_retried(status):
    client = FakeClient(refusals=1, status=status)
    with pytest.raises(swarmbox_sdk.SwarmboxError):
        run(client)
    assert client.calls == 1


@pytest.mark.parametrize("error", [httpx.ConnectError("All connection attempts failed"), httpx.ConnectTimeout("timed out")])
def test_connections_that_never_opened_are_retried(error):
    world, retries, slept = run(FakeClient(refusals=2, error=error))
    assert world == "world" and retries == 2
    assert slept == [2.0, 4.0]


def test_the_window_counts_the_time_attempts_take():
    # Each attempt hangs 127 s (a connect to a dead VM): the third would
    # start at 127 + 2 + 127 + 4 = 260 s, the fourth past 300 s.
    client = FakeClient(refusals=100, error=httpx.ConnectError("timed out"), attempt_s=127)
    with pytest.raises(httpx.ConnectError):
        run(client, window_s=300)
    assert client.calls == 3


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("timed out"), httpx.RemoteProtocolError("Server disconnected without sending a response.")],
)
def test_requests_that_may_have_arrived_are_not_retried(error):
    client = FakeClient(refusals=1, error=error)
    with pytest.raises(type(error)):
        run(client)
    assert client.calls == 1
