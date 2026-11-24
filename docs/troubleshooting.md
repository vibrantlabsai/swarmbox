---
title: If something fails
description: The errors you may see running Harbor tasks on the hosted swarmbox test bed, with the cause and the fix for each.
group: Hosted test bed
weight: 2
---

# If something fails

The errors you may see running Harbor tasks on the hosted test bed, with the cause and the fix for each.

| You see | Cause | Fix |
|---|---|---|
| `401` from `curl`, or `missing or invalid API token` | The token is wrong or was revoked | Export your current token, without stray spaces or quotes, or ask us for a new one |
| `no API token` | `SWARMBOX_TOKEN` is unset in this shell | Export it |
| `BuildFailed: image build … failed` | A step of the task's Dockerfile failed | The build's output follows the message; the failing step is at the end. If the step was a download that failed (a package mirror out of sync), run again: the next trial rebuilds it |
| `429 too many image builds queued` | More than 16 of your images, or 64 across all Users, were building or waiting, and stayed so | Run the first pass on fewer tasks at once, then the rest |
| A trial times out while its environment starts | Its image took more than 10 minutes to build, or waited that long behind other builds | Run again: the build carried on, so the image is there or nearly |
| `image build … disappeared (the builder restarted?)` | We redeployed while your image was building | Run again |
| `FileNotFoundError: … 'docker'` or `… 'crane'`, or `cannot query registry for …` | `SWARMBOX_REGISTRY` (or, from before the rename, `OPENDSEC_REGISTRY`) is set in this shell, so the provider builds on your machine and pushes there | `unset SWARMBOX_REGISTRY SWARMBOX_PLATFORM OPENDSEC_REGISTRY OPENDSEC_PLATFORM` |
| `503 no capacity: …` | The test bed stayed busy for 5 minutes of retries, so it refused new Worlds rather than slow down running ones | Run fewer trials at once (`-n`) |

Anything else: reply to the email your token came in, and attach your `nop.log` or `oracle.log`.
