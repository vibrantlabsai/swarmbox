#!/usr/bin/env bash
# Tests of dev/check-release.sh against throwaway trees (run by `just check`).
set -uo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
rel=$(mktemp -d)
trap 'rm -rf "$rel"' EXIT
fails=0
check() { # check DESCRIPTION CONDITION...
  local what=$1
  shift
  if "$@"; then echo "ok   $what"; else echo "FAIL $what" >&2; fails=$((fails + 1)); fi
}
release() { ROOT=$rel "$REPO_ROOT/dev/check-release.sh" "$@" 2>/dev/null; }
refused() { ! release "$@"; }

printf '[project]\nversion = "0.4.0"\n' >"$rel/pyproject.toml"
check "the package at the version" release 0.4.0
check "the repo itself is releasable at its version" "$REPO_ROOT/dev/check-release.sh" "$(sed -n 's/^version = "\(.*\)"$/\1/p' "$REPO_ROOT/pyproject.toml")"
check "another version is refused" refused 0.4.1
check "a version that is not X.Y.Z is refused" refused 0.4.0.post1
printf '[project]\nversion = "0.3.0"\n[tool.other]\nversion = "0.4.0"\n' >"$rel/pyproject.toml"
check "the version is the project's, not another table's" refused 0.4.0
printf '[project]\nname = "x"\n' >"$rel/pyproject.toml"
check "a project without a version is refused" refused 0.4.0

[ "$fails" = 0 ] || { echo "$fails failed" >&2; exit 1; }
