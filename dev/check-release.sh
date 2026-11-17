#!/usr/bin/env bash
# Before a release is built: every package is at VERSION, and each package
# that depends on another of ours pins it to VERSION's minor series. PyPI
# never lets a version be reused, so a mismatch must stop the release here.
#
#   dev/check-release.sh VERSION      e.g. 0.4.0
#
# ROOT is the tree to check (tests); the repo by default.
set -euo pipefail
root=${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
want=${1:?usage: $0 VERSION}
[[ $want =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "::error::$want is not a version like 0.4.0" >&2; exit 2; }
minor=${want%.*}
range=">=$minor,<${minor%%.*}.$((${minor#*.} + 1))"
# Read as TOML, not as text: the version is [project]'s, and a pin counts only
# as one of [project]'s dependencies, the ones an install follows.
ROOT=$root WANT=$want RANGE=$range python3 - <<'PY'
import os
import sys
import tomllib
from pathlib import Path

root, want, pin = Path(os.environ["ROOT"]), os.environ["WANT"], os.environ["RANGE"]
# package directory, then every package of ours it must pin
packages = {
    ".": [],
    "compat/opendsec": ["swarmbox-sdk"],
    "compat/opendsec-harbor": ["swarmbox-sdk[harbor]", "opendsec"],
}
failed = False
for directory, needs in packages.items():
    file = "pyproject.toml" if directory == "." else f"{directory}/pyproject.toml"
    try:
        project = tomllib.loads((root / file).read_text()).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"::error::{file}: {e}", file=sys.stderr)
        failed = True
        continue
    got = project.get("version")
    if got != want:
        print(f"::error::{file} is {got or 'missing a version'}, but the release is {want}", file=sys.stderr)
        failed = True
    requires = ["".join(d.split()) for d in project.get("dependencies", [])]
    for need in needs:
        # Every requirement on the package, extras or not, so a second one
        # cannot contradict it.
        name = need.partition("[")[0]
        ours = [d for d in requires if d.removeprefix(name)[:1] in ("", "<", ">", "=", "!", "~", "[", ";")]
        if ours != [need + pin]:
            print(f'::error::{file} must require "{need}{pin}" and nothing else of {need}', file=sys.stderr)
            failed = True
sys.exit(failed)
PY
