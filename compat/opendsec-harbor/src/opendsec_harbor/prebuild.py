"""python -m opendsec_harbor.prebuild, as before the rename: swarmbox_sdk.harbor.prebuild."""

import asyncio
import sys

from swarmbox_sdk.harbor.prebuild import *  # noqa: F403
from swarmbox_sdk.harbor.prebuild import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
