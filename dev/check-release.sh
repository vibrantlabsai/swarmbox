#!/usr/bin/env bash
# Before a release is built: the package is at VERSION. PyPI never lets a
# version be reused, so a mismatch must stop the release here.
#
#   dev/check-release.sh VERSION      e.g. 0.4.0
#
# ROOT is the tree to check (tests); the repo by default.
set -euo pipefail
root=${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
want=${1:?usage: $0 VERSION}
[[ $want =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "::error::$want is not a version like 0.4.0" >&2; exit 2; }
# Read as TOML, not as text: the version is [project]'s.
ROOT=$root WANT=$want python3 - <<'PY'
import os
import sys
import tomllib
from pathlib import Path

root, want = Path(os.environ["ROOT"]), os.environ["WANT"]
try:
    project = tomllib.loads((root / "pyproject.toml").read_text()).get("project", {})
except (OSError, tomllib.TOMLDecodeError) as e:
    sys.exit(f"::error::pyproject.toml: {e}")
got = project.get("version")
if got != want:
    sys.exit(f"::error::pyproject.toml is {got or 'missing a version'}, but the release is {want}")
PY
