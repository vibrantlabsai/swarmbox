# swarmbox (SDK and docs)

The public half of swarmbox, open-source Sandboxes for agentic RL rollouts and evals: the `swarmbox-sdk` Python package (the async client, and the Harbor environment provider as its `harbor` extra), the docs site at https://swarmbox.vibrantlabs.com, and the developer docs. The platform itself (API server, node agent, deploy) is in a separate repo. Use the terms in `docs/glossary.md`.

## Layout

- `src/swarmbox_sdk/`: the client (`client.py`). `harbor/` is the Harbor provider, `swarmbox_sdk.harbor:SwarmboxEnvironment`; it imports Harbor and PyYAML, so nothing outside `harbor/` may import it.
- `tests/`: the provider's tests (they run with the `harbor` extra).
- `compat/opendsec`, `compat/opendsec-harbor`: the package names from before the rename; each installs `swarmbox-sdk` (with `[harbor]`) and is it under the old import name, with a warning. 0.4.x is their last series.
- `site/`: the Hugo site, one page (`site/content/_index.md`).
- `docs/`: developer docs, Markdown not built into the site, linked by relative `.md` path.
- `dev/`: `check-release.sh`, `check-doc-links.py`, `install-hugo.sh` (CI).

## Working here

- Tools: uv, just and Hugo 0.167 extended. `nix develop` (or direnv with `use flake`) provides all three; nothing requires Nix, and CI runs without it.
- `just check` runs every check and test: ruff, the SDK importing without the extra, the tests, the forwarders' tests, the strict site build and the relative-link check. CI runs the same.
- `uv run --extra harbor pytest` for the tests alone; `just docs` serves the site locally.
- The platform repo installs this one as a uv git source pinned to a commit, for its API contract suite and experiments, and its spec test reads `docs/world-spec.md` at that commit. A change to the client, the provider or the World spec lands here first; the platform then bumps its pin. Keep `docs/world-spec.md`'s tables in the shape that test parses.
- This repo is public: no internal hostnames, IPs, infrastructure details or links to private repos.

## Docs

Two tracks. **API users** (people given a token for the hosted test bed) get one page, `site/content/_index.md`: a walkthrough from token to rollouts, every command run against the test bed before it's published. **Developers** get `docs/`. A change to what a User sees (SDK, provider options, World spec) updates its page in the same change: the site page if the walkthrough touches it, and `docs/`. The site page and the walkthrough and reference pages in `docs/` open with one sentence on what the reader gets, and real code within the first screen; explanation pages and indexes are exempt.

## Releases

`swarmbox-sdk`, `opendsec` and `opendsec-harbor` ship together at one version. Bump the three `pyproject.toml` files and each pin (`dev/check-release.sh VERSION` checks them), merge, then push tag `vX.Y.Z`; `.github/workflows/release.yml` publishes to PyPI through trusted publishing, one job and GitHub environment per package (`pypi-swarmbox-sdk`, `pypi-opendsec`, `pypi-opendsec-harbor`; each allows only tags `v*`, and a new package needs its environment and its PyPI publisher, naming this repo and `release.yml`, created before the first tag). `README.md` is also the PyPI page, so its links stay absolute. A version can never be reused there, so `just dist` first. Breaking the API bumps the minor version.
