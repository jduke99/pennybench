# PennyBench

Reproducible, paired evaluations of coding-agent configurations using the **Harbor
harness and benchmark-provided task verifiers**. Run the same task natively and
through PennyRouter, then audit the recorded evidence and compare model-call cost,
tokens, execution time, and official task rewards.

The shared runner lives in `pennybench/`. Dataset pins, experiment definitions and
documentation live under [benchmarks/](benchmarks/README.md).

| Suite | Start here |
| --- | --- |
| SkillsBench | [60-task results and reproduction](benchmarks/skillsbench/README.md) · [HTML report](https://jduke99.github.io/pennybench/skillsbench-60/) |
| Terminal-Bench 2.1 | In progress; not part of this release |

## Install

Work from a clone of this repository. Requirements: Python 3.12, uv, Docker, and
Claude Code and the PennyRouter CLI (`penny`) for the signed-in subscription workflow.
Use your own PennyRouter account and its normal onboarding. No local PennyRouter gateway
is required. Task containers and their dependencies may be substantial; consult the
suite's architecture, RAM and timing notes before starting.

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e ".[dev]"
cp config.example.toml pennybench.local.toml
.venv/bin/python -m pytest tests -q
```

`pennybench.local.toml` means **your private runner settings**, not a local gateway.
The example targets `https://api.pennyrouter.com`. To evaluate a private server,
change `[endpoints.proxy].base_url` to its HTTPS endpoint reachable from Docker.
Do not commit your personal configuration.

## Use your own subscription

The published SkillsBench comparison used the author's own Claude subscription.
Reproductions use **your** account; PennyBench distributes no credentials, shared
account or subscription access.

1. Sign into Claude Code with `claude auth login`.
2. Install PennyRouter with `npx pennyrouter install` and select the Anthropic subscription.
   Confirm that `penny claude` starts normally; that links the same Claude account to
   PennyRouter.
3. Keep the example's `claude-login` profile. Each arm uses a private staged copy
   of your login; both arms of a pair use the same account plan.

See [credentials and supported auth modes](docs/CREDENTIALS.md) for token and API-key
profiles, limitations, credential cleanup, and task-container exposure.

## Check the wiring first

```sh
.venv/bin/pennybench check benchmarks/smoke-login.yaml
```

This validates a tiny, suite-independent fixture. It does not run a model. When
you are ready to spend subscription usage, run the two-arm wiring check:

```sh
.venv/bin/pennybench run benchmarks/smoke-login.yaml
```

Use a clean, committed checkout for runs. Deliberate development experiments may
use `--allow-dirty`; the runner records that they were not pre-registered.

## Run a suite

Follow the suite-specific instructions before launching model trials:

- [SkillsBench](benchmarks/skillsbench/README.md): registry download, pinned task
  hash, task-local skills, and historical exclusions.

Reference checks use the supplied solutions, not an LLM. Model trials consume your
subscription or API usage. Do not launch multiple runs sharing the same artifact
store, credential source, or gateway. The runner enforces one run per store.

Each model run prints its artifact directory. Audit and report that exact path:

```sh
.venv/bin/pennybench audit runs/<experiment>/<run-directory>
.venv/bin/pennybench report runs/<experiment>/<run-directory>
```

For subscription evaluations, `--stop-at-utilization 0.90` checks usage between
pairs. Resume a stopped run with the same experiment and `--resume <run-directory>`.
Use `audit --partial` and `report --partial` when reporting a bounded set of
finished pairs from a longer plan; these retain the runner's provenance labels.

## What is measured

- A/B arms must differ in their declared variable only. Shared model, harness and
  effort settings are pinned in [arms/](arms/).
- Wire records, task rewards, package inventories, and hashes support an evidence
  audit. An audit pass is not a substitute for inspecting task verification.
- Cost is notional USD: reported token usage multiplied by the pinned pricing table.
  It is not a Claude subscription bill. Task rewards retain each task's own grading
  rules, including partial credit where provided.
- A result belongs to its named dataset, task selection and configuration. Keep
  exclusions, incomplete trials and run provenance in its methodology.

## Repository guide

- [Runner reference](RUNNER.md): specification format, audits, statistics and resume behavior.
- [Architecture](DESIGN.md): the shared measurement design.
- [Contributing](CONTRIBUTING.md): tests and experiment changes.
- [Privacy and credentials](SECURITY.md): what must remain private.
- [Publication checklist](docs/PUBLICATION.md): staged public-repository preparation.

`runs/`, `.env`, personal configuration, downloaded task sets and caches stay private.
Only reviewed results should be published. 

PennyBench is released under the [Apache License 2.0](LICENSE). Third-party components
keep their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
