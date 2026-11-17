import asyncio

import pytest

from swarmbox_sdk.harbor import images

TAG = "myacr.azurecr.io/swarmbox/task-images:0123456789abcdef01234567"
DIGEST = "sha256:" + "b" * 64


def crane_says(monkeypatch, code: int, out: str) -> None:
    async def fake_crane(*args, check=True):
        return code, out

    monkeypatch.setattr(images, "_crane", fake_crane)


def test_digest_found(monkeypatch):
    crane_says(monkeypatch, 0, DIGEST + "\n")
    assert asyncio.run(images._digest(TAG)) == DIGEST


@pytest.mark.parametrize(
    "out",
    [
        "MANIFEST_UNKNOWN: manifest unknown",
        "NAME_UNKNOWN: repository name not known to registry",
        "GET https://myacr.azurecr.io/v2/...: 404 Not Found",
    ],
)
def test_digest_not_found_is_a_miss(monkeypatch, out):
    crane_says(monkeypatch, 1, out)
    assert asyncio.run(images._digest(TAG)) is None


@pytest.mark.parametrize(
    "out",
    [
        "UNAUTHORIZED: authentication required",
        "dial tcp: lookup myacr.azurecr.io: no such host",
    ],
)
def test_digest_other_failures_raise(monkeypatch, out):
    """Treating them as a miss would rebuild and push an image that exists."""
    crane_says(monkeypatch, 1, out)
    with pytest.raises(RuntimeError, match="cannot query registry"):
        asyncio.run(images._digest(TAG))
