"""The name the Harbor provider had before the project was renamed.

Harbor loads `opendsec_harbor:OpenDSecEnvironment` from here; it is
swarmbox_sdk.harbor's SwarmboxEnvironment (swarmbox-sdk[harbor]).
"""

import re
import sys
import warnings
from importlib.metadata import version


def _require_before_0_5(package: str, old: str, module: str, install: str) -> None:
    """The old name stops at 0.4: from 0.5.0 the new package no longer has
    what this one forwards to. pip upgrades the new package past this one's
    pin with only a warning, so say so here, not as an AttributeError later."""
    # Leading digits only: "5rc1" is minor 5.
    major, minor = (int(re.match(r"\d+", part).group()) for part in version(package).split(".")[:2])
    if (major, minor) >= (0, 5):
        raise ImportError(
            f"{old} ends at 0.4, but {package} {version(package)} is installed: "
            f"import {module} instead and uninstall {old}, "
            f"or install '{install}<0.5'"
        )


_require_before_0_5("swarmbox-sdk", "opendsec-harbor", "swarmbox_sdk.harbor", "swarmbox-sdk[harbor]")

from swarmbox_sdk.harbor import SwarmboxEnvironment  # noqa: E402
from swarmbox_sdk.harbor import compose as compose  # noqa: E402
from swarmbox_sdk.harbor import environment as environment  # noqa: E402
from swarmbox_sdk.harbor import images as images  # noqa: E402

# The modules that existed under the old name are the new ones themselves, so
# every name they had resolves (the .pyi files say the same to type
# checkers). prebuild is a file of its own, for `python -m`.
for _module in (compose, environment, images):
    sys.modules[f"{__name__}.{_module.__name__.rpartition('.')[2]}"] = _module

# FutureWarning: shown to whoever runs Harbor, not only to its authors.
warnings.warn(
    "opendsec-harbor is renamed: install 'swarmbox-sdk[harbor]' and pass Harbor "
    "--environment-import-path swarmbox_sdk.harbor:SwarmboxEnvironment",
    FutureWarning,
    stacklevel=2,
)

# The same class, not a subclass, so type() and isinstance() agree with new
# code. Also where it was defined, opendsec_harbor.environment: that module
# is swarmbox_sdk.harbor's, so the old class name is added to it.
OpenDSecEnvironment = SwarmboxEnvironment
environment.OpenDSecEnvironment = SwarmboxEnvironment  # type: ignore[attr-defined]

__all__ = ["OpenDSecEnvironment"]
