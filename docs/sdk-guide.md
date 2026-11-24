---
title: Use the Python SDK
description: Create a World from your own code, run commands in its Sandboxes and move files in and out, without Harbor.
group: Guides
weight: 2
---

# Use the Python SDK

Create a World from your own code, run commands in its Sandboxes and move files in and out, without Harbor. This World has two Sandboxes: one serves HTTP, and the other finds it by name.

```python
import asyncio

import swarmbox_sdk


async def main():
    # Reads SWARMBOX_URL and SWARMBOX_TOKEN.
    async with swarmbox_sdk.Client() as client:
        world = await client.create_world(
            [
                swarmbox_sdk.Sandbox(
                    name="env",
                    image="docker.io/library/python:3.12-slim",
                    command=["python", "-m", "http.server", "8080"],
                    aliases=["svc.internal"],
                ),
                swarmbox_sdk.Sandbox(
                    name="main",
                    image="docker.io/library/python:3.12-slim",
                    command=["sleep", "infinity"],
                ),
            ],
            ttl="5m",
        )
        try:
            result = await world.exec("main", "getent hosts svc.internal")
            print(result.exit_code, result.stdout)
        finally:
            await world.stop()


asyncio.run(main())
```

## Before you start

- A swarmbox API server and a token for it, exported as `SWARMBOX_URL` and `SWARMBOX_TOKEN`. For the hosted test bed, the [quickstart](quickstart.md) says how to get one.
- The SDK installed, on Python 3.12 or later: `uv add swarmbox-sdk`, or `pip install swarmbox-sdk`.

The client is async. One `Client` holds a pool of connections, so create one and share it across your rollouts.

## Create a World

`create_world` takes the Sandboxes to run together and how long the World may live. It returns once every Sandbox is ready, so there is no polling to write. If the platform could not deliver the World, it raises `WorldFailed`.

Each `Sandbox` needs a `name` and an `image`. The name is also its hostname: the other Sandboxes of the World reach it by that name, and by any of its `aliases`. The [World spec](world-spec.md) describes every field.

A Sandbox reaches only its own World unless you give it `egress="public"`:

```python
swarmbox_sdk.Sandbox(name="main", image="docker.io/library/python:3.12-slim",
                     command=["sleep", "infinity"], egress="public")
```

## Run commands

`world.exec` runs a command in one Sandbox, by name, and returns its exit code and output. A string runs under `bash -lc`; a list runs as it is, which is what you want in an image without bash.

```python
result = await world.exec("main", "python --version")
result = await world.exec("env", ["ls", "/"], workdir="/tmp", timeout=30)
if result.exit_code != 0:
    print(result.stderr)
```

A command that runs and fails is not an error: you get its exit code. A command that cannot start at all, such as a program the image does not have, raises `SwarmboxError`.

A command that outlives its `timeout` (10 minutes unless you set one) is killed, and the result has `timed_out` set. In 0.4.0 the client has a limit of its own: it stops waiting for any request after 600 seconds and raises `httpx.ReadTimeout`. That is the same 10 minutes, so a command near the limit can end either way, and a longer `timeout=` alone is cut off by the client. For a long command, raise both:

```python
# Seconds one request may take: longer than your longest command.
async with swarmbox_sdk.Client(timeout=3700) as client:
    ...
    result = await world.exec("main", "make test", timeout=3600)
```

## Move files

```python
await world.upload("main", "solution/", "/app/solution")      # a directory
await world.upload("main", "config.json", "/app/config.json") # one file
await world.download("main", "/app/results", "results/")
```

A World's files go with it when it stops, so download what you need first. Both calls need `sh` and `tar` in the Sandbox's image, and one download carries at most 16 MiB.

## Use your own image

`build_image` builds an image on the platform from a directory with a Dockerfile, so you need no Docker and no registry. Here `my-image/` is a directory of yours with a `Dockerfile` and the files it copies. Pass the result's `ref` as a Sandbox's image:

```python
image = await client.build_image("my-image/")
world = await client.create_world(
    [swarmbox_sdk.Sandbox(name="main", image=image.ref, command=["sleep", "infinity"])],
    ttl="10m",
)
```

The image is tagged by a hash of the directory's files. If they haven't changed since the last build, the call is a lookup and returns at once. A build that fails raises `BuildFailed`, whose `log` has the end of the build's output.

## Stop it, and handle failures

Stop a World when you are done with it: `await world.stop()`. If your code crashes first, the World is stopped when its `ttl` runs out, so set the `ttl` close to how long a rollout really takes.

| You get | It means | Do |
|---|---|---|
| `WorldFailed` | The platform could not deliver the World, or a Sandbox in it exited. Never a task outcome | Retry the rollout in a new World |
| `SwarmboxError` with `status == 503` | The platform is busy and created nothing | Wait a few seconds and retry. The SDK does not retry for you |
| `SwarmboxError` with `status == 429` | A limit was reached, and nothing was created | Stop Worlds you are done with, or create more slowly |
| `httpx.ConnectError`, `httpx.ReadTimeout` or another `httpx` error | The API never answered: the connection failed, or the request outlasted the client's `timeout`. These are not `SwarmboxError` | Retry a create or a lookup. After a timed-out `exec`, the command may still be running |
| `BuildFailed` | The Dockerfile failed, or the build timed out | Read its `log` |

The [Python SDK reference](python-sdk.md) lists every method and field.
