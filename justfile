# swarmbox SDK and docs tasks. Needs uv, just and Hugo (0.167, extended):
# `nix develop` provides all three, or install them any other way.

# Every static check and test; CI runs this.
check: py-lint py-test docs-check

# Ruff lint over the package, its tests and the forwarders.
py-lint:
    uvx ruff@0.14.3 check .

# The SDK imports without the harbor extra; the tests run with it; the
# forwarders (compat/) still are the new package under the old names.
py-test:
    uv run --frozen --exact --no-dev python -c "import swarmbox_sdk"
    uv run --frozen --extra harbor pytest -q
    cd compat/opendsec-harbor && uv run --frozen pytest -q

# Serve the docs site at http://localhost:1313, rebuilding on change.
docs:
    hugo server -s site --renderToMemory

# Strict docs build: a broken link, a template error or any warning fails;
# then every relative link in the repo's Markdown (docs/ isn't built).
docs-check:
    hugo -s site --panicOnWarning --renderToMemory
    uv run --no-project python dev/check-doc-links.py

# Build the packages into dist/<package>/, as the release workflow publishes
# them (one PyPI upload per package): the SDK, and the two packages that keep
# the names they had before the rename.
dist:
    rm -rf dist
    uv build --out-dir dist/swarmbox-sdk
    cd compat/opendsec && uv build --out-dir ../../dist/opendsec
    cd compat/opendsec-harbor && uv build --out-dir ../../dist/opendsec-harbor
    find dist -name .gitignore -delete # uv build drops one per dir; only packages get uploaded
    uvx twine@7.0.0 check --strict dist/*/*
