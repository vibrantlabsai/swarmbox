# swarmbox (SDK and docs)

The public half of swarmbox, open-source Sandboxes for agentic RL rollouts and evals: the `swarmbox-sdk` Python package (the async client, and the Harbor environment provider as its `harbor` extra), the docs site at https://swarmbox.vibrantlabs.com, and the developer docs. The platform itself (API server, node agent, deploy) is in a separate repo. Use the terms in `docs/glossary.md`.

## Layout

- `src/swarmbox_sdk/`: the client (`client.py`). `harbor/` is the Harbor provider, `swarmbox_sdk.harbor:SwarmboxEnvironment`; it imports Harbor and PyYAML, so nothing outside `harbor/` may import it.
- `tests/`: the provider's tests (they run with the `harbor` extra).
- `site/`: the Hugo site, one page (`site/content/_index.md`).
- `docs/`: developer docs, Markdown not built into the site, linked by relative `.md` path.
- `dev/`: `check-release.sh`, `check-doc-links.py`, `install-hugo.sh` (CI).

## Working here

- Tools: uv, just and Hugo 0.167 extended. `nix develop` (or direnv with `use flake`) provides all three; nothing requires Nix, and CI runs without it.
- `just check` runs every check and test: ruff, the SDK importing without the extra, the tests, the strict site build and the relative-link check. CI runs the same.
- `uv run --extra harbor pytest` for the tests alone; `just docs` serves the site locally.
- The platform repo installs this one as a uv git source pinned to a commit, for its API contract suite and experiments, and its spec test reads `docs/world-spec.md` at that commit. A change to the client, the provider or the World spec lands here first; the platform then bumps its pin. Keep `docs/world-spec.md`'s tables in the shape that test parses.
- This repo is public: no internal hostnames, IPs, infrastructure details or links to private repos.

## Docs

Two tracks. **API users** (people given a token for the hosted test bed) get one page, `site/content/_index.md`: a walkthrough from token to rollouts, every command run against the test bed before it's published. **Developers** get `docs/`. A change to what a User sees (SDK, provider options, World spec) updates its page in the same change: the site page if the walkthrough touches it, and `docs/`. The site page and the walkthrough and reference pages in `docs/` open with one sentence on what the reader gets, and real code within the first screen; explanation pages and indexes are exempt.

## Releases

Bump the version in `pyproject.toml` (`dev/check-release.sh VERSION` checks it), merge, then push tag `vX.Y.Z`; `.github/workflows/release.yml` publishes `swarmbox-sdk` to PyPI through trusted publishing, from the GitHub environment `pypi-swarmbox-sdk` (it allows only tags `v*`; PyPI's publisher names this repo, `release.yml` and that environment). The packages from before the rename, `opendsec` and `opendsec-harbor`, stay at 0.3.0 on PyPI: nothing is released under those names. `README.md` is also the PyPI page, so its links stay absolute. A version can never be reused there, so `just dist` first. Breaking the API bumps the minor version.
