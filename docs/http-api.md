---
title: HTTP API
description: Every call of the swarmbox HTTP API, what it takes and what it returns.
group: API reference
weight: 1
url: /api/http/
aliases: [/api/]
---

# HTTP API

Every call of the swarmbox API: what it takes and what it returns. The [Python SDK](python-sdk.md) and the Harbor provider are built on these calls.

```sh
curl -s -H "Authorization: Bearer $SWARMBOX_TOKEN" $SWARMBOX_URL/v1/worlds
```

```json
{"worlds":[]}
```

| Call | Does |
|---|---|
| [`POST /v1/worlds`](#create-a-world) | Creates a World and waits until it is ready |
| [`GET /v1/worlds`](#list-your-worlds) | Lists your Worlds |
| [`GET /v1/worlds/{id}`](#get-a-world) | Returns one World |
| [`DELETE /v1/worlds/{id}`](#stop-a-world) | Stops a World |
| [`POST /v1/worlds/{id}/sandboxes/{name}/exec`](#run-a-command) | Runs a command in a Sandbox |
| [`PUT /v1/worlds/{id}/sandboxes/{name}/archive`](#upload-files) | Uploads files into a Sandbox |
| [`GET /v1/worlds/{id}/sandboxes/{name}/archive`](#download-files) | Downloads files from a Sandbox |
| [`GET /v1/images/{tag}`](#images) | Returns an image you built |
| [`PUT /v1/images/{tag}`](#images) | Builds an image from a Dockerfile |

## Requests and errors

- **Address.** The hosted test bed is `https://api.swarmbox.vibrantlabs.com`.
- **Token.** Every call carries `Authorization: Bearer <token>`. Without a valid one the answer is `401` with `{"error": "missing or invalid API token"}`.
- **Bodies.** Requests and responses are JSON, except the two `archive` calls and the image upload, which carry a tar.
- **Errors.** An error is a status code and `{"error": "<what went wrong>"}`.
- **Ownership.** A World or image belongs to the User whose token created it. Any call on another User's World returns the same `404` as one that does not exist.

| Status | Means |
|---|---|
| `400` | The request is wrong, such as an invalid World spec. The message names every problem |
| `401` | The token is missing or wrong |
| `404` | No such World, Sandbox or image, or it is not yours |
| `409` | The World is not `ready` or `running`, so nothing can run in it |
| `413` | The body is too large: a World spec over 8 MiB, or a build context over 1 GiB |
| `429` | A limit was reached: a [per-User limit](world-spec.md#limits) where any is set, or too many image builds queued. Nothing was created |
| `500` | The platform could not do what was asked: a command that could not start, or a file transfer that failed. Each call below says when |
| `501` | Image builds are not enabled on this deployment |
| `502` | `node <name> unreachable`: the API server could not reach the node. If this answers a create, the World may exist all the same: [list your Worlds](#list-your-worlds) before you retry. Also returned when the image builder cannot be reached |
| `503` | No node can take the World right now: every one is busy, is being drained for maintenance, or lacks the runtime your User runs on. Nothing was created, and retrying shortly is safe |

## Create a World

`POST /v1/worlds`

The body is a [World spec](world-spec.md): the Sandboxes to run together, and a `ttl`.

```sh
curl -s -X POST $SWARMBOX_URL/v1/worlds \
  -H "Authorization: Bearer $SWARMBOX_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "ttl": "5m",
    "sandboxes": [{
      "name": "main",
      "image": "docker.io/library/python:3.12-slim",
      "command": ["sleep", "infinity"],
      "resources": {"cpus": 1, "memory_mb": 1024}
    }]
  }'
```

The call returns once every Sandbox is ready, or the World has failed. The response is the [World object](world-spec.md#what-comes-back). Check its `state`: a World the platform could not deliver comes back as `failed`, with a `reason`.

The examples below use the World's ID as `$WORLD`. Set it from the response:

```sh
WORLD=...   # the "id" in the response
```

## List your Worlds

`GET /v1/worlds`

Returns `{"worlds": [...]}`, each entry a [World object](world-spec.md#what-comes-back). Only your Worlds are listed. If a node could not be asked, its name is in `unreachable_nodes`, so a partial list is never mistaken for a full one.

## Get a World

`GET /v1/worlds/{id}`

Returns the [World object](world-spec.md#what-comes-back). A World that has ended stays readable for 5 minutes; after that the answer is `404`.

## Stop a World

`DELETE /v1/worlds/{id}`

Stops every Sandbox of the World and returns the World object, now `stopped`. Its files and output go with it.

## Run a command

`POST /v1/worlds/{id}/sandboxes/{name}/exec`

```sh
curl -s -X POST $SWARMBOX_URL/v1/worlds/$WORLD/sandboxes/main/exec \
  -H "Authorization: Bearer $SWARMBOX_TOKEN" -H "Content-Type: application/json" \
  -d '{"command": ["echo", "hello"]}'
```

```json
{"exit_code":0,"stdout":"hello\n","stderr":""}
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `command` | array of strings | yes | The process to run and its arguments. No shell is added: to use one, run `["bash", "-lc", "…"]` |
| `env` | object of strings | no | Extra environment variables, added to the Sandbox's |
| `workdir` | string | no | Working directory. Defaults to the Sandbox's |
| `timeout` | [duration](world-spec.md#durations) | no, default `10m` | How long the command may run before it is killed. There is no maximum, but the World's `ttl` still ends it |

The call returns when the command ends:

| Field | Meaning |
|---|---|
| `exit_code` | The command's exit code. A command that runs and exits non-zero is still a `200`: the failure is here |
| `stdout`, `stderr` | What it wrote |
| `timed_out` | `true` if it was killed for outliving its `timeout`. Left out otherwise |
| `truncated` | `true` if either output passed 16 MiB and the rest was dropped. Left out otherwise |

A command that cannot start is a `500`, not an exit code: a program the image does not have, a `workdir` that does not exist, or an empty `command`.

The request stays open for as long as the command runs, so give your HTTP client a read timeout longer than the command's; the SDK's `World.exec` does. If the request is closed first, the command is killed.

The first command run in a World moves it from `ready` to `running`.

## Upload files

`PUT /v1/worlds/{id}/sandboxes/{name}/archive?path=<directory>`

The body is a tar. It is unpacked into the directory `path` inside the Sandbox, which is created if it is missing. Returns `{}`. The Sandbox's image must have `sh` and `tar`. An empty `path`, or an archive that cannot be unpacked, is a `500`.

This example uploads a local directory, `solution/`:

```sh
tar -cf - -C solution . | curl -s -X PUT --data-binary @- \
  -H "Authorization: Bearer $SWARMBOX_TOKEN" \
  "$SWARMBOX_URL/v1/worlds/$WORLD/sandboxes/main/archive?path=/app/solution"
```

## Download files

`GET /v1/worlds/{id}/sandboxes/{name}/archive?path=<file or directory>`

Returns a tar (`application/x-tar`) of the file or directory at `path`, with its base name as the root of the archive. The Sandbox's image must have `sh` and `tar`. A `path` that is empty or does not exist, or an archive over 16 MiB, is a `500`.

This example unpacks `/app/results` into the current directory, as `results/`:

```sh
curl -s -H "Authorization: Bearer $SWARMBOX_TOKEN" \
  "$SWARMBOX_URL/v1/worlds/$WORLD/sandboxes/main/archive?path=/app/results" | tar -xf -
```

## Images

`GET /v1/images/{tag}` and `PUT /v1/images/{tag}?dockerfile=Dockerfile`

The platform builds an image from a tar of a Dockerfile and its files, so you need no Docker and no registry. `PUT` starts the build (`202` while it builds, `200` if it is already built) and `GET` returns its state. [Built images](world-spec.md#built-images) describes the tag, the response and the limits.
