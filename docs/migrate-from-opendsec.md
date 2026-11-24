---
title: Moving from opendsec
description: What to change if you used swarmbox under its earlier name, opendsec.
group: Hosted test bed
weight: 3
---

# Moving from opendsec

swarmbox is the new name of opendsec, and it runs on a new platform at a new address. The earlier platform is gone: `api.opendsec.vibrantlabs.com` was shut down on 23 November 2026 and the address no longer exists, so anything that still points at it fails. Your token is the same on the new platform.

| You have | Change it to |
|---|---|
| `https://api.opendsec.vibrantlabs.com` | `https://api.swarmbox.vibrantlabs.com` |
| `opendsec-harbor==0.3.0` in your project | `swarmbox-sdk[harbor]==0.4.0` |
| `--environment-import-path opendsec_harbor:OpenDSecEnvironment` | `--environment-import-path swarmbox_sdk.harbor:SwarmboxEnvironment` |
| `OPENDSEC_URL`, `OPENDSEC_TOKEN` | `SWARMBOX_URL`, `SWARMBOX_TOKEN` |
| `import opendsec` | `import swarmbox_sdk` |

Things to know when you move:

- **The first run on the new platform builds your images again.** It starts with none; a second run is fast.
- **If you push to a registry of your own** (`OPENDSEC_REGISTRY`), images now go to the repository `swarmbox/task-images`, not `opendsec/task-images`: they are pushed once more, and credentials scoped to the old repository need the new one.
- **Restart Harbor jobs.** Harbor will not resume a job whose import path changed.
- **Each trial's metrics file is now `swarmbox-agent.json`.** Earlier job directories keep `opendsec-agent.json`.
- **The import names change at once; the settings can wait.** `opendsec` and `opendsec-harbor` stay at 0.3.0 and do not install swarmbox, so `import opendsec` and the old import path stop working as soon as you install `swarmbox-sdk` in their place: change them in the same step. The `OPENDSEC_*` settings and `except OpendsecError` keep working in `swarmbox-sdk` 0.4, each with a `FutureWarning`, and stop at 0.5.0. If both a new and an old setting are set, the new one wins.
