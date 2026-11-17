"""The names the project had before it was renamed still work, and warn."""

import importlib
import subprocess
import sys
import warnings

import pytest
import swarmbox_sdk
import swarmbox_sdk.harbor


def fresh(module: str):
    """Import module as if for the first time, so its warning fires again."""
    for name in [m for m in sys.modules if m == module or m.startswith(module + ".")]:
        del sys.modules[name]
    return importlib.import_module(module)


@pytest.fixture
def quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        yield


def test_import_opendsec_is_the_sdk_and_warns():
    with pytest.warns(FutureWarning, match="import swarmbox_sdk"):
        old = fresh("opendsec")
    for name in swarmbox_sdk.__all__:
        assert getattr(old, name) is getattr(swarmbox_sdk, name), name


def test_opendsec_client_is_the_sdk_client_module(quiet):
    import opendsec
    import opendsec.client

    assert opendsec.client is swarmbox_sdk.client
    assert opendsec.client.Client is swarmbox_sdk.Client  # as an attribute, without importing the submodule
    from opendsec.client import _context_tar, context_tag  # private names were importable too

    assert context_tag is swarmbox_sdk.context_tag and callable(_context_tar)


def test_old_error_name_catches_new_errors(quiet):
    import opendsec

    with pytest.raises(opendsec.OpendsecError):
        raise swarmbox_sdk.WorldFailed("node-1.abc", "it failed")


def test_harbor_import_path_is_the_same_class_and_warns():
    with pytest.warns(FutureWarning, match="swarmbox_sdk.harbor:SwarmboxEnvironment"):
        old = fresh("opendsec_harbor")
    assert old.OpenDSecEnvironment is swarmbox_sdk.harbor.SwarmboxEnvironment


def test_the_class_is_also_where_it_was_defined(quiet):
    from opendsec_harbor.environment import OpenDSecEnvironment

    assert OpenDSecEnvironment is swarmbox_sdk.harbor.SwarmboxEnvironment


@pytest.mark.parametrize(
    ("old", "package", "module"),
    [("opendsec", "swarmbox-sdk", "swarmbox_sdk"), ("opendsec_harbor", "swarmbox-sdk", "swarmbox_sdk.harbor")],
)
def test_past_0_4_the_old_name_says_what_to_do(quiet, monkeypatch, old, package, module):
    import importlib.metadata

    real = importlib.metadata.version
    for later in ("0.5.0", "0.5rc1"):  # a pre-release is refused too, not a ValueError
        monkeypatch.setattr(importlib.metadata, "version", lambda name, v=later: v if name == package else real(name))
        with pytest.raises(ImportError, match=f"import {module} instead"):
            fresh(old)
        monkeypatch.undo()
    fresh(old)  # and with the 0.4 series it imports


@pytest.mark.parametrize("module", ["compose", "environment", "images"])
def test_every_module_the_old_package_had_is_the_new_one(quiet, module):
    old = importlib.import_module(f"opendsec_harbor.{module}")
    assert old is importlib.import_module(f"swarmbox_sdk.harbor.{module}")


def test_prebuild_has_its_names_and_runs_as_a_module(quiet):
    from opendsec_harbor.prebuild import main, prebuild_task

    new = importlib.import_module("swarmbox_sdk.harbor.prebuild")
    assert main is new.main and prebuild_task is new.prebuild_task
    run = subprocess.run([sys.executable, "-W", "ignore", "-m", "opendsec_harbor.prebuild", "--help"],
                         capture_output=True, text=True)
    assert run.returncode == 0 and "--registry" in run.stdout


def test_the_warnings_reach_someone_running_harbor():
    """Harbor imports the class by its path, from inside a library. Python
    hides DeprecationWarning there; these must show with no -W flag."""
    code = "import importlib; importlib.import_module('opendsec_harbor'); import opendsec"
    run = subprocess.run([sys.executable, "-c", f"exec({code!r}, {{'__name__': 'harbor.loader'}})"],
                         capture_output=True, text=True, check=True)
    assert "opendsec-harbor is renamed" in run.stderr and "opendsec is renamed" in run.stderr
