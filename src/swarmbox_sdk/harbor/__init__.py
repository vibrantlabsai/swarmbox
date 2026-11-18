"""Harbor environment provider for swarmbox: each Harbor trial runs as one World.

Needs the `harbor` extra: pip install 'swarmbox-sdk[harbor]'. Harbor loads it as
--environment-import-path swarmbox_sdk.harbor:SwarmboxEnvironment.
"""

try:
    from swarmbox_sdk.harbor.environment import SwarmboxEnvironment
except ModuleNotFoundError as e:  # Harbor or PyYAML missing: the extra isn't installed
    if e.name not in ("harbor", "yaml") and not (e.name or "").startswith("harbor."):
        raise
    raise ModuleNotFoundError(
        f"swarmbox_sdk.harbor needs the harbor extra ({e.name} is not installed): "
        "pip install 'swarmbox-sdk[harbor]'",
        name=e.name,
    ) from e

__all__ = ["SwarmboxEnvironment"]
