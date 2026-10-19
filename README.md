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

| Endpoint | Median change | 95% CI, median % | Sum change | P-value |
| --- | ---: | ---: | ---: | ---: |
| Model-call cost | −34.0% | [−37.2, −28.4] | −30.1% | 4.13e−10 |
| Total tokens | −18.0% | [−21.1, −14.7] | −18.6% | 4.82e−05 |
| Output tokens | +4.3% | [−7.5, +7.3] | −0.7% | 0.877 |
| Fresh input tokens | +25.0% | [+14.3, +33.3] | +24.1% | 3.72e−05 |
| Cache-read tokens | −17.7% | [−23.0, −14.4] | −19.0% | 1.18e−04 |
| Cache-write tokens | −20.6% | [−28.1, −13.2] | −19.0% | 3.76e−07 |
| Model calls | +0.0% | [+0.0, +0.0] | +1.0% | 0.912 |
| Agent execution time | −13.4% | [−19.8, +9.3] | −20.2% | 0.244 |
| Official task reward (6 higher, 4 lower, 47 tied) | n/a | n/a | +8.9% (0.570 → 0.621) | 0.754 (sign test) |

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

## Acknowledgments

This work was inspired by and adapted from the evaluation series conducted by Denis Shiryaev at JetBrains covering [Caveman](https://blog.jetbrains.com/ai/2026/07/speak-to-ai-agents-like-cavemen-tosave-tokens/), [RTK](https://blog.jetbrains.com/ai/2026/07/rtk-claude-code-token-savings/), and [Ponytail](https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/).

## License

PennyBench is released under the [Apache License 2.0](LICENSE). Third-party components
keep their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
