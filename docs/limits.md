---
title: Limits
description: What the hosted swarmbox test bed caps, and what it does when it is busy.
group: Hosted test bed
weight: 1
---

# Limits of the hosted test bed

What the hosted test bed caps, and what it does when it is busy. A create it refuses makes nothing and says why:

```text
503 no capacity: …
```

`503` is the test bed being busy, and retrying shortly is safe.

- **One container per task, for now.** Tasks whose compose file starts extra services may work, but multi-container tasks aren't what this beta is testing yet.
- **Builds have limits.** Builds can reach the internet, for `apt-get` and `pip`, and nothing else. Your build cache is yours alone, and nobody else's upload can replace an image of yours.
  - 1 GiB of task files per image, in at most 100,000 files.
  - 20 minutes per build.
  - 4 of your builds run at once, and 8 across all Users. More wait their turn.
  - 16 of your builds may be running or waiting, and 64 across all Users. Past that, a new build gets `429 too many image builds queued`.
- **A trial has 10 minutes to start.** That is Harbor's limit. A build that takes longer, waiting included, fails that trial; the build carries on, and the next run finds the image.
- **Shared and small.** Two nodes serve every User. A trial's World stops when the trial ends. If Harbor is killed, its Worlds are stopped when their time limit runs out (3 hours by default).
- **No limits of your own today.** The platform can cap the Worlds a User holds, the CPUs they declare and how fast they create, but the test bed sets no such cap. What holds a run back is the test bed being busy (`503`) and the build limits above.
- **Busy means no, not slow.** When the test bed is busy it refuses new Worlds with `503 no capacity: …` rather than slow down running ones. Retrying after a short wait is safe, and the Harbor provider does it for you for up to 5 minutes. It does the same when a create can't connect at all, which can happen for a few seconds if one of the API servers goes down.
- **Download results before a World stops.** Its files and output go with it; Harbor downloads what it needs for you. Its record is readable for 5 minutes after it ends. A usage summary (images, run time, CPU, memory and network use, how it ended) is kept 13 months for accounting, with environment variables by name only, never their values.
- **A test bed.** We redeploy it as swarmbox changes. Running Worlds survive a redeploy, but not a reboot of the node they run on; a build in progress is lost and is built again on the next run. Built images are kept.
