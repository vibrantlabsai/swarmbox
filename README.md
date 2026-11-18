# swarmbox

Async Python client for [swarmbox](https://swarmbox.vibrantlabs.com): open-source Sandboxes for RL rollouts, with a [Harbor](https://github.com/harbor-framework/harbor) environment provider.

Each trial gets a **World**: a **Sandbox** for the agent's workspace and one for every service the task needs, on one private network, started and torn down as one.

```sh
pip install swarmbox-sdk
```

```python
import asyncio

import swarmbox_sdk


async def main():
    # Reads SWARMBOX_URL (default http://localhost:7700) and SWARMBOX_TOKEN.
    async with swarmbox_sdk.Client() as client:
        world = await client.create_world(
            [
                swarmbox_sdk.Sandbox(name="env", image="docker.io/library/python:3.12-slim",
                                     command=["python", "-m", "http.server", "8080"],
                                     aliases=["svc.internal"]),
                swarmbox_sdk.Sandbox(name="main", image="docker.io/library/python:3.12-slim",
                                     command=["sleep", "infinity"]),
            ],
            ttl="5m",
        )
        result = await world.exec("main", "getent hosts svc.internal")
        print(result.exit_code, result.stdout)
        await world.stop()


asyncio.run(main())
```

- `Client.create_world(sandboxes, ttl)` returns once every Sandbox is ready, or raises `WorldFailed` if the platform couldn't deliver the World.
- `Client.build_image(dir)` builds an image on the platform from a Dockerfile and its build context, and returns once it is ready (a lookup if those files were built before). Use its `ref` as a Sandbox's `image`. No Docker and no registry access needed.
- `World.exec`, `upload` and `download` act in one Sandbox, by name.
- `get_world` and `list_worlds` look Worlds up.

## Harbor

Each Harbor trial runs as one World, and each service in the task's compose file as one Sandbox in it. The agent and the task stay the same; only the environment flag changes.

```sh
pip install 'swarmbox-sdk[harbor]'
export SWARMBOX_URL=https://your-apiserver SWARMBOX_TOKEN=...
harbor run -p path/to/task -a oracle -e swarmbox_sdk.harbor:SwarmboxEnvironment
```

A token is all the machine running Harbor needs: the provider uploads each task's files and swarmbox builds its image, tagged by a hash of those files, so a task whose files haven't changed is a lookup, not a rebuild.

To build on your own machine instead, set `SWARMBOX_REGISTRY` to a registry your swarmbox nodes pull from. The provider then builds each image with `docker` and pushes it there (it needs `docker`, [`crane`](https://github.com/google/go-containerregistry/tree/main/cmd/crane) and push access), which is how `python -m swarmbox_sdk.harbor.prebuild` loads a batch of tasks ahead of a run.

| Option (`--ek key=value`) | Variable | Default |
|---|---|---|
| `url` | `SWARMBOX_URL` | `http://localhost:7700` |
| `token` | `SWARMBOX_TOKEN` | none |
| `registry` | `SWARMBOX_REGISTRY` | none: swarmbox builds the images |
| `pull_registry` | `SWARMBOX_PULL_REGISTRY` | `registry`; `host.lima.internal:5001` when `registry` is `localhost:5001` |
| `platform` | `SWARMBOX_PLATFORM` | this machine's architecture (used only with `registry`) |
| `ttl` | | `3h` |

Tasks may use only the compose keys `image`, `build`, `command`, `environment`, `volumes`, `expose`, `networks`, `healthcheck` and `depends_on`; anything else fails the trial before it starts rather than running it wrong.

More: [Run a Harbor job](https://github.com/vibrantlabsai/swarmbox/blob/main/docs/run-a-harbor-job.md).

## Docs

- Hosted test bed walkthrough, from token to rollouts: https://swarmbox.vibrantlabs.com (source: [`site/`](https://github.com/vibrantlabsai/swarmbox/tree/main/site))
- [Developer docs](https://github.com/vibrantlabsai/swarmbox/blob/main/docs/README.md): the World spec, Worlds and Sandboxes, the Harbor provider.
- Renamed from opendsec: [`compat/`](https://github.com/vibrantlabsai/swarmbox/blob/main/compat/README.md) keeps the old package names working through 0.4.

## Contributing

See [AGENTS.md](https://github.com/vibrantlabsai/swarmbox/blob/main/AGENTS.md) for how the repo is laid out, how to run the checks, and how docs and releases work. It is written for people and coding agents alike.

Licensed under Apache-2.0.

<!-- This file is the PyPI page too: keep its links absolute. -->
