"""Settings come from SWARMBOX_*; the names from before the rename are a fallback."""

import subprocess
import sys
import warnings

import pytest
import swarmbox_sdk
from swarmbox_sdk.harbor import images
from swarmbox_sdk import client

NAMES = ["URL", "TOKEN", "REGISTRY", "PULL_REGISTRY", "PLATFORM"]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(f"SWARMBOX_{name}", raising=False)
        monkeypatch.delenv(f"OPENDSEC_{name}", raising=False)
    monkeypatch.setattr(client, "_warned", set())  # each test is a new process, as far as warnings go


@pytest.mark.parametrize("name", NAMES)
def test_new_name_is_read_without_a_warning(monkeypatch, name):
    monkeypatch.setenv(f"SWARMBOX_{name}", "new")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert client.env(name) == "new"


@pytest.mark.parametrize("name", NAMES)
def test_old_name_is_read_with_a_warning(monkeypatch, name):
    monkeypatch.setenv(f"OPENDSEC_{name}", "old")
    with pytest.warns(FutureWarning, match=f"set SWARMBOX_{name}"):
        assert client.env(name) == "old"


def test_an_old_name_warns_once_however_often_it_is_read(monkeypatch):
    monkeypatch.setenv("OPENDSEC_URL", "old")
    monkeypatch.setenv("OPENDSEC_TOKEN", "t")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")  # as a program that resets the filters would see it
        for _ in range(50):
            assert client.env("URL") == "old"
            swarmbox_sdk.Client()
    assert sorted(str(w.message).split()[0] for w in caught) == ["OPENDSEC_TOKEN", "OPENDSEC_URL"]


@pytest.mark.parametrize("name", NAMES)
def test_new_name_wins_when_both_are_set(monkeypatch, name):
    monkeypatch.setenv(f"SWARMBOX_{name}", "new")
    monkeypatch.setenv(f"OPENDSEC_{name}", "old")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert client.env(name) == "new"


@pytest.mark.parametrize("name", NAMES)
def test_an_empty_new_name_does_not_hide_the_old_one(monkeypatch, name):
    monkeypatch.setenv(f"SWARMBOX_{name}", "")
    monkeypatch.setenv(f"OPENDSEC_{name}", "old")
    with pytest.warns(FutureWarning):
        assert client.env(name) == "old"


def test_unset_gives_the_default_and_empty_stays_empty(monkeypatch):
    assert client.env("URL", "http://localhost:7700") == "http://localhost:7700"
    assert client.env("TOKEN") is None
    # As before the rename: a setting that is set but empty is not the default.
    monkeypatch.setenv("SWARMBOX_REGISTRY", "")
    assert client.env("REGISTRY", "default") == ""
    monkeypatch.delenv("SWARMBOX_REGISTRY")
    monkeypatch.setenv("OPENDSEC_REGISTRY", "")
    with pytest.warns(FutureWarning):
        assert client.env("REGISTRY", "default") == ""


def test_client_takes_its_token_from_either_name(monkeypatch):
    with pytest.raises(swarmbox_sdk.SwarmboxError, match="SWARMBOX_TOKEN"):
        swarmbox_sdk.Client()
    monkeypatch.setenv("OPENDSEC_TOKEN", "t")
    with pytest.warns(FutureWarning):
        swarmbox_sdk.Client()


def test_platform_setting_is_read_under_either_name(monkeypatch):
    monkeypatch.setenv("OPENDSEC_PLATFORM", "linux/amd64")
    with pytest.warns(FutureWarning):
        assert images.default_platform() == "linux/amd64"
    monkeypatch.setenv("SWARMBOX_PLATFORM", "linux/arm64")
    assert images.default_platform() == "linux/arm64"


def test_the_warning_reaches_someone_running_a_program(monkeypatch):
    """Python hides DeprecationWarning raised inside libraries, which is where
    a Harbor user's settings are read. This one must show with no -W flag."""
    monkeypatch.setenv("OPENDSEC_TOKEN", "t")
    code = "import swarmbox_sdk.harbor.images, swarmbox_sdk; swarmbox_sdk.Client()"
    run = subprocess.run([sys.executable, "-c", f"exec({code!r}, {{'__name__': 'a_library'}})"],
                         capture_output=True, text=True, check=True)
    assert "set SWARMBOX_TOKEN instead" in run.stderr


def test_old_error_name_is_the_same_class():
    assert swarmbox_sdk.OpendsecError is swarmbox_sdk.SwarmboxError
