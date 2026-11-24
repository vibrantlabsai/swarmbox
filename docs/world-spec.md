---
title: World spec
description: Every field of the JSON that creates a swarmbox World, and what comes back.
group: API reference
weight: 2
url: /api/world-spec/
---

# World spec

The World spec is the JSON body of `POST /v1/worlds`: the Sandboxes to run together, and how long they may live. The platform checks every field on this page before it starts anything, and reports every problem in one error. A field it does not know is ignored without an error, so a misspelt optional field, such as `workingdir` for `workdir`, is silently dropped.

```json
{
  "ttl": "1h",
  "sandboxes": [
    {
      "name": "main",
      "image": "registry.example.com/task@sha256:…",
      "command": ["sleep", "infinity"],
      "env": {"TASK_ID": "42"},
      "workdir": "/app",
      "aliases": ["workspace.internal"],
      "resources": {"cpus": 2, "memory_mb": 4096},
      "readiness": {"command": ["test", "-f", "/tmp/ready"], "interval": "1s", "timeout": "60s"},
      "egress": "public"
    }
  ]
}
```

## World

| Field | Type | Required | Meaning |
|---|---|---|---|
| `sandboxes` | array of [Sandbox](#sandbox) | yes, at least one | The Sandboxes to place, start and destroy together. The set is fixed once the World exists |
| `ttl` | [duration](#durations) | yes | How long the World may live, from creation. Greater than zero and at most `24h`. When it runs out, the node agent stops the World |

## Sandbox

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | The Sandbox's name and hostname. A DNS label: lowercase letters, digits and `-`, 1–63 characters, starting and ending with a letter or digit |
| `image` | string | yes | An OCI image reference the node can pull anonymously (pin by digest, `…@sha256:…`, for reproducible trials), or the `ref` of an image the platform built for you ([Built images](#built-images)) |
| `command` | array of strings | no | The full process to run. It replaces the image's entrypoint and command, which are the default |
| `env` | object of strings | no | Extra environment variables, added to the image's |
| `workdir` | string | no | Working directory. Defaults to the image's |
| `aliases` | array of strings | no | Extra hostnames the other Sandboxes can use for this one |
| `resources` | [Resources](#resources) | yes | CPU and memory limits |
| `readiness` | [Readiness](#readiness) | no | A probe that must pass before the World is `ready`. Without one, a Sandbox counts as ready once it starts |
| `egress` | `"none"` or `"public"` | no, default `"none"` | What the Sandbox may reach outside its World, described below |
| `image_mode` | `"eager"`, `"lazy"` or `"auto"` | no, default: the node's | How the node loads the image, for A/B experiments. `eager` pulls it whole; `lazy` starts from converted EROFS layers and fails if the image is not converted; `auto` is lazy when converted, eager otherwise. Experimental. On the hosted test bed the default is `auto` |

Every name and alias must be unique across the whole World. Sandboxes of one World always reach each other by name and alias, whatever their `egress`.

### Egress

| Value | The Sandbox can reach |
|---|---|
| `none` | Only the other Sandboxes of its World. It has no external DNS either |
| `public` | The public internet as well. Never private networks, cloud metadata endpoints, other Worlds or the node itself |

## Resources

| Field | Type | Required | Meaning |
|---|---|---|---|
| `cpus` | number | yes, greater than 0 | CPU limit, in cores. Fractions are allowed |
| `memory_mb` | integer | yes, greater than 0 | Memory limit, in MiB |

Every Sandbox also runs with limits that are not part of the spec:

- **At most 4096 processes** (the node's default), so a runaway fork stays inside its Sandbox.
- **Docker's default seccomp profile and capability set.** What runs in a Docker container runs here. What a Docker container may not do, such as mounting filesystems or creating namespaces, fails here too.
- **Connections to the internet, for Sandboxes with `egress: public`:** at most 1024 open at once, and new ones at up to 100 a second after a burst of 200. Past either limit, new connections time out; those already open are unaffected. Connections between a World's Sandboxes are not limited, but those a Sandbox opens count towards its 1024.
- **20 GiB of disk per Sandbox** (the node's default), for whatever it writes over its image. Past that, writes fail with "no space left on device" in that Sandbox only. Files you delete free their space.
- **Root in a Sandbox is root only inside it.** On the node it is an unprivileged user, in a user namespace of its own. Inside, nothing changes: processes run as root, and the image's files belong to the users the image says.

## Readiness

A command run inside the Sandbox. Exit code 0 means ready.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `command` | array of strings | yes | The probe |
| `interval` | [duration](#durations) | yes | Time between attempts. Each attempt also times out after this long |
| `timeout` | [duration](#durations) | yes | How long to keep trying. If the probe never passes, the World is `failed` |

Probes of different Sandboxes run in parallel.

## Durations

A duration is a Go duration string (`"500ms"`, `"90s"`, `"1h30m"`) or a number of seconds (`90`).

## What comes back

`POST /v1/worlds` returns once every Sandbox is ready or the World has failed. `GET /v1/worlds/{id}` and `DELETE /v1/worlds/{id}` return the same object:

```json
{
  "id": "node-1.4ba267e85a471544",
  "state": "ready",
  "expires_at": "2026-10-31T16:03:45.150380912-07:00",
  "sandboxes": {"env": "10.200.0.2", "main": "10.200.0.3"},
  "timings": {"network_ms": 30, "images_ms": 0, "start_ms": 72, "ready_ms": 657, "total_ms": 760},
  "images": {"env": {"mode": "eager"}, "main": {"mode": "eager"}},
  "runtime": "runc"
}
```

| Field | Meaning |
|---|---|
| `id` | The World's ID, `<node>.<key>`. The API server routes every later call by the node part |
| `state` | `creating`, `ready`, `running`, `stopped` or `failed`. See [the lifecycle](worlds-and-sandboxes.md#a-world-lives-and-dies-as-one) |
| `reason` | Why the World ended, for example `stopped by user`, `ttl expired` or `sandbox env exited with code 1`. Present only once it has ended |
| `expires_at` | When the TTL runs out |
| `sandboxes` | Each Sandbox's IP address on the World's private network |
| `timings` | Milliseconds spent creating it: network setup, image pulls, starting Sandboxes, readiness probes, and the total |
| `images` | How each Sandbox's image was loaded: its `mode`, `eager` or `lazy`, and for a lazy image its `layers` and how many of them this create mounted, `layers_mounted`. Left out when there is nothing to report |
| `runtime` | How the World's Sandboxes run: `runc` (containers on the node's kernel), or a stronger runtime such as `gvisor` when your User is configured for one |

A World that has ended stays readable for 5 minutes, then `GET` returns `404`.

Commands run in one Sandbox at a time: `POST /v1/worlds/{id}/sandboxes/{name}/exec`. An unknown World or Sandbox name returns `404`.

A World belongs to the User who created it. `GET /v1/worlds` lists only your Worlds, and every call on another User's World returns the same `404` as a World that does not exist.

## Limits

A deployment can limit what each User holds and how fast they create. The hosted test bed sets no such limit today. Where one is set, a create over it returns `429` with the limit named, for example `{"error": "limit reached: 300 live Worlds for user <name>"}`, and nothing is created.

| Limit | Counts |
|---|---|
| Live Worlds | Your Worlds that are being created, ready or running, on every node. Ended Worlds don't count |
| CPUs | The `cpus` declared by every Sandbox of your live Worlds, plus the World you are creating |
| Creates per second | Your creates on one API server. Short bursts of twice the rate are allowed |

Under a limit, stop Worlds you are done with to make room. With Harbor, keep the number of concurrent trials (`-n`) below your live-World limit.

Whether or not limits are set, a node refuses new Worlds when it is busy (its CPUs under pressure, or memory short) or when the Worlds on it already declare far more than it has. Then a create returns `503` with `{"error": "no capacity: …"}` and the reason, nothing is created, and retrying shortly is safe. Worlds already running are never slowed down to make room.

## Built images

The platform builds an image from a Dockerfile and its build context, so you need no Docker and no registry. The SDK's `Client.build_image(dir)` and the Harbor provider do all of this; the API is:

| Call | Does |
|---|---|
| `GET /v1/images/{tag}` | Your image with this tag: `200` with its state, or `404` |
| `PUT /v1/images/{tag}?dockerfile=Dockerfile` | Starts building it from the request body, a tar of the build context. `202` while it builds, `200` if it is already built. `&force=1` rebuilds it without the build cache |

`{tag}` is 16 to 64 lower-case hex characters: the client's hash of the context (`swarmbox_sdk.context_tag`), so unchanged files map to the same image. Both return:

```json
{"tag": "e91cdc9b2c917d6668513c1437197a32", "ref": "registry.example.com/swarmbox/builds/<user>@sha256:639d117b…", "state": "ready", "build_ms": 57295}
```

| Field | Meaning |
|---|---|
| `ref` | What a Sandbox's `image` names to run it: the image by digest, in the platform's registry. Every node runs it. While `state` is not `ready` it is the tag being built, which nothing can pull yet |
| `state` | `building`, `ready` or `failed`. Poll `GET` until it is not `building` |
| `error`, `log` | Why a build failed, and the tail of its output (where a failing step shows) |
| `build_ms` | How long the build and the push took |

A failed build can be retried with another `PUT`. A deployment with no builder answers `501`.

- **Yours.** Tags are per User: another User's `GET` of your tag is `404`, and nothing they upload can replace your image. The image itself is in a registry the nodes pull from without logging in, so it is not secret.
- **Lazy, a little later.** An image is `ready` once pushed. The platform then converts it into the image store, after which Worlds start it without pulling; a World created before that pulls it.
- **Fenced.** Builds reach the internet, and no private network, cloud metadata or platform host; build steps cannot reach each other either, whoever's they are. They pull only what anyone may pull: the platform's registry login is never theirs to use. Each User's builds run in their own buildkitd, so caches (cache mounts included) are never shared between Users.
- **Limits.**
  - A build context of at most 1 GiB unpacked, in at most 100,000 files. A larger upload is refused with `413`.
  - 20 minutes per build.
  - 4 builds at once per User, and 8 across all Users. More wait their turn.
  - 16 builds running or waiting per User, and 64 across all Users. More get `429`: retry later.
- **User names.** A User whose name ends in a dash cannot own images (`400`): the name is part of the image's repository.
