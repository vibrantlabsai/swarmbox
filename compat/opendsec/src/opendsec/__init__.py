"""The name swarmbox-sdk had before the project was renamed.

Everything here is swarmbox_sdk's; import that instead.
"""

import re
import sys
import warnings
from importlib.metadata import version


def _require_before_0_5(package: str, old: str) -> None:
    """The old name stops at 0.4: from 0.5.0 the new package no longer has
    what this one forwards to. pip upgrades the new package past this one's
    pin with only a warning, so say so here, not as an AttributeError later."""
    # Leading digits only: "5rc1" is minor 5.
    major, minor = (int(re.match(r"\d+", part).group()) for part in version(package).split(".")[:2])
    if (major, minor) >= (0, 5):
        raise ImportError(
            f"{old} ends at 0.4, but {package} {version(package)} is installed: "
            f"import {package.replace('-', '_')} instead and uninstall {old}, "
            f"or install '{package}<0.5'"
        )


_require_before_0_5("swarmbox-sdk", "opendsec")

from swarmbox_sdk import *  # noqa: E402, F403
from swarmbox_sdk import __all__, client  # noqa: E402, F401

# opendsec.client is swarmbox_sdk.client itself, so every name it had
# resolves. client.pyi says the same to type checkers.
sys.modules[f"{__name__}.client"] = client

# FutureWarning: shown to whoever runs the program, not only to its author.
warnings.warn(
    "opendsec is renamed: install swarmbox-sdk and import swarmbox_sdk",
    FutureWarning,
    stacklevel=2,
)
