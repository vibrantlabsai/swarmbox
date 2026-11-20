# Run a Harbor job on swarmbox

Run a [Harbor](https://github.com/harbor-framework/harbor) eval on swarmbox, with each trial in its own World. The agent and the task stay the same; only the environment flag changes:

```sh
uv run harbor run -p <task> -a <agent> -e swarmbox_sdk.harbor:SwarmboxEnvironment
```

The provider, `swarmbox_sdk.harbor:SwarmboxEnvironment`, turns each trial into one World and each service in the task's compose file into one Sandbox in it.

This guide uses Harbor's own `hello-world` example. Any Harbor task directory or dataset works the same way.

## Before you start

- A swarmbox apiserver and a token for it, exported as `SWARMBOX_URL` and `SWARMBOX_TOKEN`. For the hosted test bed, the [walkthrough](https://swarmbox.vibrantlabs.com) says how to get one.
- The provider installed: `uv add 'swarmbox-sdk[harbor]'` in your project, or, in a checkout of this repo, `uv sync --extra harbor`.

## Run a task

Fetch the example task at the Harbor version the provider is tested with:

```sh
git clone --depth 1 --branch v0.22.0 --filter=blob:none --sparse \
  https://github.com/harbor-framework/harbor.git /tmp/harbor
git -C /tmp/harbor sparse-checkout set examples/tasks/hello-world
```

Run it with the oracle agent, which applies the task's reference solution:

```sh
uv run harbor run -p /tmp/harbor/examples/tasks/hello-world \
  -a oracle -e swarmbox_sdk.harbor:SwarmboxEnvironment -o jobs
```

The oracle scores 1.0. The job's results, logs and the provider's per-trial timings (`world_id`, image and create times) are under `jobs/`.

To run a real agent, swap `-a oracle` for any Harbor agent. To run a whole dataset, point `-p` at a directory of tasks and set the concurrency with `-n`. One World is created per trial, so `-n 32` means 32 Worlds at once.

## Point the provider somewhere else

Every option can be set with `--ek key=value` on the Harbor command line, or with the environment variable:

| `--ek` key | Variable | Default | What it is |
|---|---|---|---|
| `url` | `SWARMBOX_URL` | `http://localhost:7700` | The apiserver |
| `token` | `SWARMBOX_TOKEN` | — | Your API token |
| `registry` | `SWARMBOX_REGISTRY` | — (swarmbox builds the images) | A registry this machine builds images for and pushes them to, instead: see below |
| `pull_registry` | `SWARMBOX_PULL_REGISTRY` | `registry`; `host.lima.internal:5001` when `registry` is `localhost:5001` | The same registry, as the nodes reach it |
| `platform` | `SWARMBOX_PLATFORM` | This machine's architecture | With `registry`: the image platform, such as `linux/amd64`. It must match the nodes |
| `ttl` | — | `3h` | Each trial World's lifetime limit, at most `24h`. Also the longest a command may run when Harbor sets no timeout for it, such as an agent's run: see below |

For example, against a remote apiserver:

```sh
uv run harbor run -p tasks/ -a oracle -n 32 -e swarmbox_sdk.harbor:SwarmboxEnvironment \
  --ek url=http://swarmbox.example.com:7700 -o jobs
```

## Long agent runs

Harbor runs an installed agent, such as `claude-code`, as one command with no timeout of its own, and enforces the agent's timeout itself (the task's `[agent] timeout_sec`). The provider lets such a command run until the World's `ttl`, so the agent's timeout is the one that ends it; a command Harbor does give a timeout gets that one. An agent that may run longer than 3 hours needs a longer `ttl`. When Harbor cancels a command at its timeout, the request is closed and swarmbox kills the command.

## Where images are built

By default the provider uploads each service's build context and swarmbox builds it ([Built images](world-spec.md#built-images)): a token is all the machine running Harbor needs. An image is tagged by a hash of its files, so a task whose files haven't changed is a lookup. Files a compose service bind-mounts are baked into its image, since a remote World cannot see your disk.

With `registry` set, the provider builds on this machine with Docker instead and pushes to that registry, which needs `docker`, `crane` and push access. That is how a batch of images is loaded ahead of a run, below, and it shares one cache with it: the registry.

## Build images ahead of a large run

Building at trial start is fine for a handful of tasks. For a dataset, an operator with push access to the registry builds and pushes every image first, then runs the job with the same `registry`:

```sh
uv run python -m swarmbox_sdk.harbor.prebuild --registry myregistry.example.com -j 8 \
  --out prebuild.jsonl tasks/*
```

Images are keyed by a hash of everything that determines them, so each one built here is a cache hit when its trial starts. `prebuild.jsonl` has one line per image, failures included. With `--lazy-store DIR` (a read-write mount of the platform's image store, for its operators), it also converts each image so nodes can start it without pulling.

## Use Marin's Harbor fork

The provider also works with Marin's fork (`marin-community/harbor` 0.8.1). That fork names the flag differently:

```sh
uv run harbor run -p tasks/ -a oracle \
  --environment-import-path swarmbox_sdk.harbor:SwarmboxEnvironment -o jobs
```

## If a trial won't start

| Message | Cause | Fix |
|---|---|---|
| `no API token` | `SWARMBOX_TOKEN` is unset | Export it, or pass `--ek token=…` |
| `node … unreachable` | The apiserver can't reach a node | Try again shortly; if it persists, tell the platform's operators |
| `UnsupportedCompose` | The task's compose file uses a key outside the supported subset | See below |
| `network mode … is not supported yet` | The task asks for a network policy other than "no network" or "public" | Not supported yet |

The provider translates only the compose keys Harbor tasks use: `image`, `build`, `command`, `environment`, `volumes`, `expose`, `networks`, `healthcheck` and `depends_on`. Any other key fails the trial before it starts rather than being silently dropped. A dropped key would leave the agent in a degraded setup that can still score, which is worse than a trial that refuses to run.
