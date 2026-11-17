#!/usr/bin/env bash
# Tests of dev/check-release.sh against throwaway trees (run by `just check`).
set -uo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
fails=0
check() { # check DESCRIPTION CONDITION...
  local what=$1
  shift
  if "$@"; then echo "ok   $what"; else echo "FAIL $what" >&2; fails=$((fails + 1)); fi
}

rel=$work/rel
release_tree() { # release_tree VERSION: the three packages at VERSION, pinned right
  local minor=${1%.*}
  local range=">=$minor,<${minor%%.*}.$((${minor#*.} + 1))"
  rm -rf "$rel"
  mkdir -p "$rel"/{compat/opendsec,compat/opendsec-harbor}
  printf '[project]\nversion = "%s"\n' "$1" >"$rel/pyproject.toml"
  printf '[project]\nversion = "%s"\ndependencies = [\n    "swarmbox-sdk%s",\n]\n' "$1" "$range" >"$rel/compat/opendsec/pyproject.toml"
  printf '[project]\nversion = "%s"\ndependencies = [\n    "swarmbox-sdk[harbor]%s",\n    "opendsec%s",\n]\n' "$1" "$range" "$range" >"$rel/compat/opendsec-harbor/pyproject.toml"
}
release() { ROOT=$rel "$REPO_ROOT/dev/check-release.sh" "$@" 2>/dev/null; }
refused() { ! release "$@"; }

release_tree 0.4.0
check "three packages at the version, each pinned to its minor series" release 0.4.0
check "the repo itself is releasable at the SDK's version" "$REPO_ROOT/dev/check-release.sh" "$(sed -n 's/^version = "\(.*\)"$/\1/p' "$REPO_ROOT/pyproject.toml")"
check "another version is refused" refused 0.4.1
sed -i.bak 's/"opendsec>=0.4,<0.5"/"opendsec>=0.3,<0.4"/' "$rel/compat/opendsec-harbor/pyproject.toml"
check "a package's second pin is checked too" refused 0.4.0
release_tree 0.4.0
sed -i.bak 's/"swarmbox-sdk\[harbor\]>=0.4,<0.5"/"swarmbox-sdk>=0.4,<0.5"/' "$rel/compat/opendsec-harbor/pyproject.toml"
check "the harbor extra is part of the pin: without it the provider is missing" refused 0.4.0
release_tree 0.4.0
sed -i.bak 's/^    "swarmbox-sdk>=0.4,<0.5",$/    # "swarmbox-sdk>=0.4,<0.5",/' "$rel/compat/opendsec/pyproject.toml"
check "a pin that is only in a comment does not count" refused 0.4.0
printf '[project]\nversion = "0.4.0"\n[project.optional-dependencies]\nx = ["swarmbox-sdk>=0.4,<0.5"]\n' >"$rel/compat/opendsec/pyproject.toml"
check "nor one that is only an optional dependency" refused 0.4.0
printf '[project]\nversion = "0.4.0"\ndependencies = ["swarmbox-sdk>=0.4,<0.5", "swarmbox-sdk>=0.5"]\n' >"$rel/compat/opendsec/pyproject.toml"
check "nor one that a second requirement contradicts" refused 0.4.0
printf "[project]\nversion = '0.4.0'\ndependencies = [ 'swarmbox-sdk >= 0.4, < 0.5', 'swarmbox-sdk-extras' ]\n" >"$rel/compat/opendsec/pyproject.toml"
check "quotes, spacing and a package with a longer name do not matter" release 0.4.0
printf '[project]\nversion = "0.3.0"\n[tool.other]\nversion = "0.4.0"\n' >"$rel/pyproject.toml"
check "the version is the project's, not another table's" refused 0.4.0
check "a version that is not X.Y.Z is refused" refused 0.4.0.post1

[ "$fails" = 0 ] || { echo "$fails failed" >&2; exit 1; }
