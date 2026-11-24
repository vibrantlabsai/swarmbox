---
title: Python SDK
description: Every class and method of swarmbox_sdk, the async Python client for swarmbox.
group: API reference
weight: 3
url: /api/python/
---

# Python SDK

Every class and method of `swarmbox_sdk`, the async Python client for swarmbox. For a walk through the same calls, see [Use the Python SDK](sdk-guide.md).

```python
import asyncio

import swarmbox_sdk


async def main():
    async with swarmbox_sdk.Client() as client:
        world = await client.create_world(
            [swarmbox_sdk.Sandbox(name="main", image="docker.io/library/python:3.12-slim",
                                  command=["sleep", "infinity"])],
            ttl="5m",
        )
        result = await world.exec("main", "echo hello")
        await world.stop()


asyncio.run(main())
```

Install it with `pip install swarmbox-sdk`. It needs Python 3.12 or later. The Harbor provider is the `harbor` extra, described in [Run a Harbor job](run-a-harbor-job.md).

## Client

```python
swarmbox_sdk.Client(url=None, token=None, timeout=600, max_connections=100)
```

| Argument | Default | Meaning |
|---|---|---|
| `url` | `SWARMBOX_URL`, else `http://localhost:7700` | The API server |
| `token` | `SWARMBOX_TOKEN` | Your API token. With none, the constructor raises `SwarmboxError` |
| `timeout` | `600` | Seconds the client waits for one request before it raises `httpx.ReadTimeout`. A create or an exec lasts as long as the work it waits for, so set this above your longest command |
| `max_connections` | `100` | Connections kept open. Each create or exec in flight holds one, so more than this many at once wait in the client |

Use it as `async with Client() as client:`, or call `await client.close()` when you are done.

| Method | Returns | Does |
|---|---|---|
| `await create_world(sandboxes, ttl="1h")` | [`World`](#world) | Creates a World from a list of [`Sandbox`](#sandbox) and waits until every one is ready. Raises `WorldFailed` if the platform could not deliver it |
| `await list_worlds()` | `list[dict]` | Your Worlds, on every node, each as the [World object](world-spec.md#what-comes-back) |
| `await get_world(world_id)` | [`World`](#world) | One World by ID |
| `await get_image(tag)` | [`Image`](#image) or `None` | Your image with this tag, or `None` if there is none |
| `await build_image(context, dockerfile="Dockerfile", *, force=False, poll=1.0, timeout=1800)` | [`Image`](#image) | Builds an image on the platform from a local directory, and returns once it is ready |

`build_image` hashes the directory's files into a tag. If the platform already has that image, the call is a lookup and the result has `cached=True`. Otherwise it uploads the files, waits for the build and returns the image; `force=True` rebuilds without the build cache. If too many of your builds are queued, it waits its turn. It raises `BuildFailed` if the build fails, and `SwarmboxError` if it is still building after `timeout` seconds.

Every file under the directory is uploaded and hashed, except anything named `.git`, `__pycache__` or `.DS_Store`. A `.dockerignore` is not read. Links are sent as the files they point to.

## Sandbox

One container of a World, as you ask for it. The fields are those of the [World spec](world-spec.md#sandbox), with two differences: `cpus` and `memory_mb` are fields of the Sandbox itself, not of a `resources` object, and there is no `image_mode`.

```python
swarmbox_sdk.Sandbox(name, image, cpus=1, memory_mb=1024, command=None, env={},
                     workdir=None, aliases=[], readiness=None, egress="none")
```

| Field | Default | Meaning |
|---|---|---|
| `name` | required | The Sandbox's name and hostname |
| `image` | required | An image reference the node can pull, or the `ref` of an image you built |
| `cpus` | `1` | CPU limit, in cores |
| `memory_mb` | `1024` | Memory limit, in MiB |
| `command` | the image's | The process to run, as a list |
| `env` | none | Extra environment variables |
| `workdir` | the image's | Working directory |
| `aliases` | none | Extra hostnames the other Sandboxes can use for this one |
| `readiness` | none | A [`Readiness`](#readiness) probe that must pass before the World is ready |
| `egress` | `"none"` | `"none"`: only its own World. `"public"`: the internet as well |

## Readiness

A command run inside the Sandbox until it exits 0.

```python
swarmbox_sdk.Readiness(command, interval="1s", timeout="60s")
```

| Field | Default | Meaning |
|---|---|---|
| `command` | required | The probe, as a list |
| `interval` | `"1s"` | Time between attempts |
| `timeout` | `"60s"` | How long to keep trying before the World fails |

## World

A live World, returned by `create_world` and `get_world`. Its methods take the name of the Sandbox to act in.

| Attribute | Meaning |
|---|---|
| `id` | The World's ID |
| `state` | `creating`, `ready`, `running`, `stopped` or `failed`, as of the last call. `refresh()` updates it |
| `timings` | Milliseconds spent creating it, by step |
| `info` | The whole [World object](world-spec.md#what-comes-back), as a dict |

| Method | Returns | Does |
|---|---|---|
| `await exec(sandbox, command, *, env=None, workdir=None, timeout=None)` | [`ExecResult`](#execresult) | Runs a command. A string runs under `bash -lc`; a list runs as it is. `timeout` is in seconds, and the platform kills the command after it (10 minutes if unset) |
| `await upload(sandbox, local, remote)` | `None` | Copies a local file or directory to `remote` inside the Sandbox. A directory's contents land in `remote` |
| `await download(sandbox, remote, local)` | `None` | Copies the file or directory at `remote` inside the Sandbox to `local`. At most 16 MiB in one call |
| `await refresh()` | `World` | Reads the World's state again |
| `await stop()` | `None` | Stops the World |

If `exec` fails because the World has failed, it raises `WorldFailed` with the reason, not the bare request error.

In 0.4.0 the client's own `timeout` (600 seconds) ends an `exec` with `httpx.ReadTimeout` at the moment the platform's default would kill the command, and before any longer `timeout=` you pass. For a command that may run longer than a few minutes, pass `timeout=` here and a larger `timeout` to [`Client`](#client).

`upload` and `download` need `sh` and `tar` in the Sandbox's image.

## ExecResult

| Field | Meaning |
|---|---|
| `exit_code` | The command's exit code |
| `stdout`, `stderr` | What it wrote |
| `timed_out` | `True` if it was killed for outliving its timeout |
| `truncated` | `True` if its output passed the platform's cap and the rest was dropped |

## Image

An image the platform built for you, returned by `build_image` and `get_image`.

| Field | Meaning |
|---|---|
| `tag` | The hash of the build context |
| `ref` | What to pass as a Sandbox's `image`, once the image is ready |
| `state` | `"building"`, `"ready"` or `"failed"` |
| `error`, `log` | Why a build failed, and the end of its output |
| `build_ms` | How long the build took, in milliseconds |
| `cached` | `True` if `build_image` found the image already built |

`swarmbox_sdk.context_tag(context, dockerfile="Dockerfile")` returns the tag a directory would get, without building it.

## Errors

| Exception | Raised when | Carries |
|---|---|---|
| `SwarmboxError` | The API answered with an error, or the SDK refused the call itself (no token, no Dockerfile, a build still running at its deadline) | `status`: the HTTP status when the API answered, else `None` (a failed `download` has it in the message only). `503` means no capacity, and retrying shortly is safe |
| `WorldFailed` | The World ended for an infrastructure reason. A subclass of `SwarmboxError` | `world_id`, `reason` |
| `BuildFailed` | An image could not be built. A subclass of `SwarmboxError` | `tag`, `error`, `log` |

A request the API never answered raises the `httpx` error as it is, not a `SwarmboxError`: `httpx.ConnectError` when the connection fails, `httpx.ReadTimeout` when a request outlasts the client's `timeout`.

The SDK does not retry. `OpendsecError`, the name `SwarmboxError` had before the rename, still works until 0.5.0.

## Settings

| Variable | Used for |
|---|---|
| `SWARMBOX_URL` | The API server, when `Client` is given no `url` |
| `SWARMBOX_TOKEN` | Your API token, when `Client` is given no `token` |

Until 0.5.0 the earlier names, `OPENDSEC_URL` and `OPENDSEC_TOKEN`, are read when the new ones are unset, with a `FutureWarning`.
