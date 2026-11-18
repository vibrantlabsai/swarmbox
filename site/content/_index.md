---
title: Run your Harbor tasks on hosted swarmbox
---

This page takes you from Harbor tasks on your own disk to 16 rollouts running at once on the hosted swarmbox test bed: 8 with Harbor's no-op agent and 8 with its oracle, on tasks from [FWeindel/validated-tasks](https://huggingface.co/datasets/FWeindel/validated-tasks). swarmbox builds each task's image from its Dockerfile, so a token is all you need: no Docker, and no registry to push to. Setup takes about ten minutes, and the first run about three more while 8 images build.

> **First, ask us for an API token.** The test bed is invite-only. Email [ankit@vibrantlabs.com](mailto:ankit@vibrantlabs.com,jithin@vibrantlabs.com?subject=swarmbox%20API%20token) and [jithin@vibrantlabs.com](mailto:ankit@vibrantlabs.com,jithin@vibrantlabs.com?subject=swarmbox%20API%20token) with your name and what you plan to run, and we'll send you a personal token over a private channel. Keep it out of shared channels and repositories. If it leaks, tell us and we'll replace it.

## Install the tools

You need a Mac or Linux machine with [uv](https://docs.astral.sh/uv/getting-started/installation/) and [jq](https://jqlang.org/download/).

```sh
brew install uv jq
```

Then create a project with Marin's Harbor fork and the swarmbox provider for it:

```sh
mkdir swarmbox-trial && cd swarmbox-trial
uv init --bare --python 3.12
uv add "harbor @ git+https://github.com/marin-community/harbor@e96b6dcca1513e97e43523eaa971a85c68fcedae" \
  "swarmbox-sdk[harbor]==0.4.0" huggingface-hub pyarrow
```

## Point it at the test bed

```sh
export SWARMBOX_URL=https://api.swarmbox.vibrantlabs.com
export SWARMBOX_TOKEN=...   # your token
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $SWARMBOX_TOKEN" $SWARMBOX_URL/v1/worlds
```

```text
200
```

`200` means your token works.

## Get the tasks

Each row of the dataset is a whole Harbor task, packed as a tar. Save this script, which unpacks the first few tasks of one of its datasets. It defaults to EndlessTerminals; any `*_v1` dataset with reference solutions works, such as `nl2bash_v1` or `crosscodeeval_v1`.

```python {filename="get_tasks.py"}
import io
import sys
import tarfile
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

dataset = sys.argv[1] if len(sys.argv) > 1 else "endless_v1"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
parquet = hf_hub_download("FWeindel/validated-tasks", f"{dataset}/tasks.parquet", repo_type="dataset",
                          revision="3b4a8c39dd283484ba53f5c97ddc098dd562686a")
rows = pq.read_table(parquet, columns=["path", "task_binary"]).slice(0, n).to_pylist()
for row in rows:
    with tarfile.open(fileobj=io.BytesIO(row["task_binary"])) as tar:
        tar.extractall(Path("tasks") / row["path"], filter="data")
    print("tasks/" + row["path"])
```

```sh
uv run python get_tasks.py endless_v1 8
```

```text
tasks/task_000000_0033979a
tasks/task_000000_003d339f
tasks/task_000000_0063591c
tasks/task_000000_009a1afa
tasks/task_000000_00e67104
tasks/task_000000_010b99da
tasks/task_000000_010d25ed
tasks/task_000000_010fa6d9
```

Each is an ordinary Harbor task directory, the same as one you'd write yourself:

```sh
find tasks/task_000000_0033979a -maxdepth 2 | sort
```

```text
tasks/task_000000_0033979a
tasks/task_000000_0033979a/environment
tasks/task_000000_0033979a/environment/Dockerfile
tasks/task_000000_0033979a/instruction.md
tasks/task_000000_0033979a/setup_files
tasks/task_000000_0033979a/setup_files/setup.sh
tasks/task_000000_0033979a/solution
tasks/task_000000_0033979a/solution/meta-llama_Llama-3.2-3B-Instruct_summary.json
tasks/task_000000_0033979a/solution/o3_summary.json
tasks/task_000000_0033979a/solution/solve.sh
tasks/task_000000_0033979a/source_metadata
tasks/task_000000_0033979a/source_metadata/environment
tasks/task_000000_0033979a/task.toml
tasks/task_000000_0033979a/tests
tasks/task_000000_0033979a/tests/test.sh
tasks/task_000000_0033979a/tests/test_final_state.py
```

`instruction.md` is what the agent is asked to do, `environment/Dockerfile` the machine it does it in, `tests/` how the result is scored, and `solution/solve.sh` the reference solution the oracle runs.

## Run 16 rollouts at once

Start both agents on the same 8 tasks, 8 trials at a time each:

```sh
uv run harbor run -p tasks -a nop -n 8 -o jobs/nop -y \
  --environment-import-path swarmbox_sdk.harbor:SwarmboxEnvironment > nop.log 2>&1 &
uv run harbor run -p tasks -a oracle -n 8 -o jobs/oracle -y \
  --environment-import-path swarmbox_sdk.harbor:SwarmboxEnvironment > oracle.log 2>&1 &
wait
```

For every trial, the provider asks swarmbox for the image of the task's `environment/` files, by a hash of them:

1. **If swarmbox has it**, the trial starts at once.
2. **If not**, the provider uploads the files and swarmbox builds the image. Trials of the same task wait for one build. EndlessTerminals tasks each have their own image, so the first run builds 8, which takes about three minutes.
3. **Then it runs**: each trial gets its own World on the test bed, so 16 are up at the same time, spread over its nodes.

Run it again and every image is already built, and starts without being downloaded first; the whole run takes under ten seconds.

- `nop` does nothing, so the task's verifier must score it **0**.
- `oracle` applies the task's reference solution, so the verifier must score it **1**.

## Check the results

```sh
jq -r '.stats.evals | to_entries[] | .key as $job | .value
  | "\($job)  trials=\(.n_trials)  errors=\(.n_errors)  mean_reward=\(.metrics[0].mean)"' \
  jobs/*/*/result.json
```

```text
nop__tasks  trials=8  errors=0  mean_reward=0.0
oracle__tasks  trials=8  errors=0  mean_reward=1.0
```

Each run adds a job directory, so clear `jobs/` (`rm -rf jobs`) before running again, or the summary includes earlier runs. That's a working setup. A failure on our side, such as a Sandbox that won't start, shows up under `errors` and never as a reward. To browse the trials, run `uv run harbor view jobs/oracle`. Each trial's `swarmbox-agent.json` has its World ID, whether its image was `built` or `cached`, and how long each step took.

Your own tasks work the same way: point `-p` at a directory of Harbor tasks. To go bigger, fetch more tasks (`uv run python get_tasks.py endless_v1 100`) and raise `-n`. One Harbor process handles about 64 trials at once. The test bed is shared by everyone testing, so tell us before you run more than about 100 at once.

## Know the limits

- **One container per task, for now.** Tasks whose compose file starts extra services may work, but multi-container tasks aren't what this beta is testing yet.
- **Builds have limits.** 1 GB of task files, 20 minutes per build, and 4 builds at once per person (more wait their turn). Harbor gives a trial 10 minutes to start, so a build that takes longer, waiting included, fails that trial; the build carries on, and the next run finds the image. Builds can reach the internet, for `apt-get` and `pip`, and nothing else. Your build cache is yours alone, and nobody else's upload can replace an image of yours.
- **Shared and small.** Two nodes serve every tester. A trial's World stops when the trial ends. If Harbor is killed, its Worlds are stopped when their time limit runs out (3 hours by default).
- **Your own limits.** Each person has a cap on Worlds alive at once, on the CPUs they declare, and on creates per second; we tell you yours. Past one, a create gets `429 limit reached: …` and nothing is made. Keep Harbor's `-n` below your World limit: Harbor counts a refused create as a failed trial.
- **Busy means no, not slow.** When the test bed is busy it refuses new Worlds with `503 no capacity: …` rather than slow down running ones. Retrying after a short wait is safe, and Harbor's provider does it for you for up to 5 minutes. It does the same when a create can't connect at all, which can happen for a few seconds if one of the API's servers goes down.
- **Download results before a World stops.** Its files and output go with it; Harbor downloads what it needs for you. Its record is readable for 5 minutes after it ends. A usage summary (images, run time, CPU, memory and network use, how it ended) is kept 13 months for accounting, with environment variables by name only, never their values.
- **A test bed.** We redeploy it as swarmbox changes. Running Worlds survive a redeploy, but not a reboot of the node they run on; a build in progress is lost and is built again on the next run. Built images are kept.

## If you used opendsec

swarmbox is the new name of opendsec, and it runs on a new platform at a new address. The earlier one, `api.opendsec.vibrantlabs.com`, keeps running for now, so what you run today keeps running; move when it suits you. Your token works on both. (They are separate from then on: a token replaced on one platform is not replaced on the other.)

| You have | Change it to |
|---|---|
| `https://api.opendsec.vibrantlabs.com` | `https://api.swarmbox.vibrantlabs.com` |
| `opendsec-harbor==0.3.0` in your project | `swarmbox-sdk[harbor]==0.4.0` |
| `--environment-import-path opendsec_harbor:OpenDSecEnvironment` | `swarmbox_sdk.harbor:SwarmboxEnvironment` |
| `OPENDSEC_URL`, `OPENDSEC_TOKEN` | `SWARMBOX_URL`, `SWARMBOX_TOKEN` |
| `import opendsec` | `import swarmbox_sdk` |

Things to know when you move:

- **The first run on the new platform builds your images again.** It starts with none; a second run is fast.
- **If you push to a registry of your own** (`OPENDSEC_REGISTRY`), images now go to the repository `swarmbox/task-images`, not `opendsec/task-images`: they are pushed once more, and credentials scoped to the old repository need the new one.
- **Finish or restart Harbor jobs first.** Harbor will not resume a job whose import path changed.
- **Each trial's metrics file is now `swarmbox-agent.json`.** Earlier job directories keep `opendsec-agent.json`.
- **You can move in two steps.** With 0.4.0 installed, the old import path and the `OPENDSEC_*` settings still work until 0.5.0, each with a `FutureWarning`; if both a new and an old setting are set, the new one wins. Do not upgrade `swarmbox-sdk` to 0.5 while your code still imports the old names: they stop at 0.4.

## If something fails

| You see | Cause | Fix |
|---|---|---|
| `401` from `curl`, or `missing or invalid API token` | The token is wrong or was revoked | Export your current token, or ask us for a new one |
| `no API token` | `SWARMBOX_TOKEN` is unset in this shell | Export it |
| `BuildFailed: image build … failed` | A step of the task's Dockerfile failed | The build's output follows the message; the failing step is at the end. If the step was a download that failed (a package mirror out of sync), run again: the next trial rebuilds it |
| `429 too many image builds queued` | More than 16 of your images, or 64 of everyone's, were building or waiting, and stayed so | Run the first pass on fewer tasks at once, then the rest |
| A trial times out while its environment starts | Its image took more than 10 minutes to build, or waited that long behind other builds | Run again: the build carried on, so the image is there or nearly |
| `image build … disappeared (the builder restarted?)` | We redeployed while your image was building | Run again |
| `FileNotFoundError: … 'docker'` or `… 'crane'`, or `cannot query registry for …` | `SWARMBOX_REGISTRY` (or, from before the rename, `OPENDSEC_REGISTRY`) is set in this shell, so the provider builds on your machine and pushes there | `unset SWARMBOX_REGISTRY SWARMBOX_PLATFORM OPENDSEC_REGISTRY OPENDSEC_PLATFORM` |
| `429 limit reached: …` | You hold as many Worlds or CPUs, or create as fast, as your limit allows | Let some trials finish, and keep Harbor's `-n` below your World limit |
| `503 no capacity: …` | The test bed stayed busy for 5 minutes of retries, so it refused new Worlds rather than slow down running ones | Run fewer trials at once (`-n`) |

Anything else: email [ankit@vibrantlabs.com](mailto:ankit@vibrantlabs.com) and [jithin@vibrantlabs.com](mailto:jithin@vibrantlabs.com) with your `nop.log` or `oracle.log`.
