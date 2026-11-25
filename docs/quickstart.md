---
title: Quickstart
description: From an API token to 16 Harbor rollouts running at once on the hosted swarmbox test bed.
group: Get started
weight: 1
steps: true
---

# Run your Harbor tasks on hosted swarmbox

This page takes you from Harbor tasks on your own disk to 16 rollouts running at once on the hosted swarmbox test bed: 8 with Harbor's no-op agent and 8 with its oracle, on tasks from [FWeindel/validated-tasks](https://huggingface.co/datasets/FWeindel/validated-tasks). swarmbox builds each task's image from its Dockerfile, so a token is all you need: no Docker, and no registry to push to. Setup takes about ten minutes, and the first run about three more while 8 images build.

> **First, you need an API token.** The test bed is invite-only: [join the waitlist](https://swarmbox.vibrantlabs.com/#waitlist) with what you plan to run. We'll email you when there's room, then send you a personal API token. Keep it out of shared channels and repositories. If it leaks, tell us and we'll replace it.

## Install the tools

You need a Mac or Linux machine with [uv](https://docs.astral.sh/uv/getting-started/installation/) and [jq](https://jqlang.org/download/). On a Mac, with Homebrew:

```sh
brew install uv jq
```

On Debian or Ubuntu:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt-get install -y jq
```

Then create a project with Harbor and the swarmbox provider for it. This walkthrough uses the Marin project's fork of Harbor (`marin-community/harbor`), the version these commands were run with:

```sh
mkdir swarmbox-trial && cd swarmbox-trial
uv init --bare --python 3.12
uv add "harbor @ git+https://github.com/marin-community/harbor@e96b6dcca1513e97e43523eaa971a85c68fcedae" \
  "swarmbox-sdk[harbor]==0.4.1" huggingface-hub pyarrow
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

`200` means your token works. `401` means swarmbox does not know it: check that you exported the whole token, with no quotes or spaces around it.

## Get the tasks

Each row of the dataset is a whole Harbor task, packed as a tar. Save this script as `get_tasks.py`. It unpacks the first few tasks of one of the datasets. It defaults to EndlessTerminals; any `*_v1` dataset with reference solutions works, such as `nl2bash_v1` or `crosscodeeval_v1`.

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

It prints the directory of each task it unpacked:

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

Both jobs run in the background and write to `nop.log` and `oracle.log`, so the terminal shows nothing until `wait` returns, when both have ended. To watch one, run `tail -f oracle.log` in another terminal.

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

Each run adds a job directory, so clear `jobs/` (`rm -rf jobs`) before running again, or the summary includes earlier runs. That's a working setup. A failure on our side, such as a Sandbox that won't start, shows up under `errors` and never as a reward. To browse the trials, run `uv run harbor view jobs/oracle`. Each trial's `swarmbox-agent.json` has its World's ID, whether its image was `built` or `cached`, and how long each step took.

Your own tasks work the same way: point `-p` at a directory of Harbor tasks. To go bigger, fetch more tasks (`uv run python get_tasks.py endless_v1 100`) and raise `-n`. One Harbor process handles about 64 trials at once. The test bed is shared by every User, so tell us before you run more than about 100 at once.

## Where to go next

- [Limits of the hosted test bed](limits.md): what the test bed caps, and what it does when it is busy.
- [If something fails](troubleshooting.md): the errors you may see, their cause and the fix.
- [Run a Harbor job](run-a-harbor-job.md): the provider's options, and building images ahead of a large run.
- [Use the Python SDK](sdk-guide.md): create Worlds from your own loop, without Harbor.
- [Moving from opendsec](migrate-from-opendsec.md): what to change if you used swarmbox under its earlier name.
