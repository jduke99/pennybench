# PennyBench

Reproducible, paired evaluations of native Claude Code and Claude Code with [PennyRouter](https://pennyrouter.com) using the [Harbor
harness](https://github.com/harbor-framework/harbor) framework including task verifiers.

This work was inspired by and adapted from the [evaluation series](https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/) conducted by JetBrains' [Denis Shiryaev](https://blog.jetbrains.com/author/denis-shiryaev-jetbrains-com) on RTK, Caveman, and Ponytail.

##  SkillsBench
Includes [SkillsBench](https://www.skillsbench.ai/blogs/introducing-skillsbench) Core and Extended tasks (n=60), excludes Extreme tasks (>4hr timeout, n=26). 

See **[Results Report](https://jduke99.github.io/pennybench/pennyrouter-skillsbench-20261019/) and [Data Files](benchmarks/skillsbench/README.md)**.


**Result Overview**
| Endpoint | Median change | 95% CI, median % | Sum change | P-value |
| --- | ---: | ---: | ---: | ---: |
| Total cost | −34.0% | [−37.2, −28.4] | −30.1% | 4.13e−10 |
| Total tokens | −18.0% | [−21.1, −14.7] | −18.6% | 4.82e−05 |
| Output tokens | +4.3% | [−7.5, +7.3] | −0.7% | 0.877 |
| Fresh input tokens | +25.0% | [+14.3, +33.3] | +24.1% | 3.72e−05 |
| Cache-read tokens | −17.7% | [−23.0, −14.4] | −19.0% | 1.18e−04 |
| Cache-write tokens | −20.6% | [−28.1, −13.2] | −19.0% | 3.76e−07 |
| Model calls | +0.0% | [+0.0, +0.0] | +1.0% | 0.912 |
| Agent execution time | −13.4% | [−19.8, +9.3] | −20.2% | 0.244 |
| Task reward | +8.9% | 6 higher, 4 lower, 47 tied | +8.9% | 0.754 |


## Terminal-Bench 2.1
Includes [Terminal Bench](https://www.tbench.ai/?agents=Terminus%202&version=2.1) tasks with agent timeout ≤30 minutes (n=72), with 4 excluded due to reference failure, making final task set n=68. Two independent runs conducted.

See **[Results Report](https://jduke99.github.io/pennybench/pennyrouter-tb21-20261019-20261020/) and [Data Files](benchmarks/terminal-bench/results/README.md)**.

**Result Overview**
| Endpoint | Median change | 95% CI, median % | Sum of task medians | P-value |
| --- | ---: | ---: | ---: | ---: |
| Total cost | -31.1% | [-35.2, -25.5] | -10.4% | 5.05e-08 |
| Total tokens | -20.9% | [-23.0, -9.8] | +7.7% | 8.99e-04 |
| Output tokens | +0.9% | [-2.3, +13.7] | +25.1% | 0.056 |
| Fresh input tokens | +16.7% | [+0.0, +25.0] | -81.4% | 1.25e-04 |
| Cache-read tokens | -19.6% | [-21.6, -7.8] | +8.8% | 0.002 |
| Cache-write tokens | -24.4% | [-34.4, -14.4] | -7.2% | 1.83e-06 |
| Model calls | +0.0% | [+0.0, +16.7] | +15.9% | 0.050 |
| Agent execution time | +12.9% | [+4.9, +21.5] | -25.3% | 0.011 |
| Task reward | +4.0% | 11 higher, 6 lower, 46 tied | +4.0% | 0.332 |

## Install

Work from a clone of this repository. Requirements: Python 3.12, uv, Docker, Claude Code,
and the PennyRouter CLI (`penny`). You also need a Claude account and a free PennyRouter
account. Task containers and their dependencies may be substantial; consult the suite's
architecture, RAM and timing notes before starting.

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e ".[dev]"
cp config.example.toml pennybench.local.toml
.venv/bin/python -m pytest tests -q
```

The example config targets `https://api.pennyrouter.com`. For a private PennyRouter server,
follow the instructions in `pennybench.local.toml`.

## Use your own subscription

The published SkillsBench comparison used the author's own Claude subscription.
Reproductions use **your** account; PennyBench distributes no credentials, shared
account or subscription access.

1. Sign into Claude Code with `claude auth login`.
2. Install PennyRouter with `npx pennyrouter install` and select the Anthropic subscription.
   Confirm that `penny claude` starts normally; that links the same Claude account to
   PennyRouter.

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

Claude Code executions receive a five-second cleanup grace period after a terminal
CLI result. If execution remains open, PennyBench sends TERM, then KILL, to its
isolated process group while leaving the container available for verification.
`agent/claude-cleanup.json` records whether a terminal result was seen and whether
cleanup exceeded the grace period. A completed CLI result does not set the reward;
the verifier still determines task success.

Reports rebuild failure labels from existing artifacts, including historical runs.
Each metrics entry has a `failure` field with a category, evidence, the original
exception type, and a provider message ID when available. Explicit provider
refusals, authentication/billing/rate limits, environment setup failures, agent
timeouts, and verifier timeouts are distinguished; unproven causes stay unknown.
`outcomes.json` and the text report separate scored outcomes from error categories
and show spending on failed or unscored trials. Rewards and statistical pair
eligibility remain unchanged. Cost reductions can include failed or unstarted runs.

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

`runs/`, `.env`, personal configuration, downloaded task sets and caches stay private.
Only reviewed results should be published. 


## License

PennyBench is released under the [Apache License 2.0](LICENSE). Third-party components
keep their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
