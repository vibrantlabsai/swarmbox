# swarmbox SDK and docs tasks. Needs uv, just and Hugo (0.167, extended):
# `nix develop` provides all three, or install them any other way.

# Every static check and test; CI runs this.
check: py-lint py-test docs-check release-check-test

# Ruff lint over the package and its tests.
py-lint:
    uvx ruff@0.14.3 check .

# The SDK imports without the harbor extra; the tests run with it.
py-test:
    uv run --frozen --exact --no-dev python -c "import swarmbox_sdk"
    uv run --frozen --extra harbor pytest -q

# Serve the docs site at http://localhost:1313, rebuilding on change.
docs:
    hugo server -s site --renderToMemory

# Strict docs build: a broken link, a template error or any warning fails;
# then every relative link in the repo's Markdown, #fragments included.
docs-check:
    hugo -s site --panicOnWarning --renderToMemory
    uv run --no-project python dev/check-doc-links.py

# Build the package into dist/, as the release workflow publishes it.
dist:
    rm -rf dist
    uv build --out-dir dist
    rm -f dist/.gitignore # uv build drops one; only packages get uploaded
    uvx twine@7.0.0 check --strict dist/*

# dev/check-release.sh against throwaway trees: what it must accept and refuse.
release-check-test:
    ./dev/test-check-release.sh
