# Running Terminal-Bench with PennyBench

Use the shared [runner installation and hosted setup](../../README.md). No local
PennyRouter gateway is required; a private server may be selected with a custom
HTTPS endpoint. Each runner supplies their own linked Claude subscription or a
supported [auth configuration](../../docs/CREDENTIALS.md).

This guide is separate from the live [study notes](README.md) so packaging does not
change active experiment definitions, source trees, reference checks, or job paths.

## Acquire the pinned source

```sh
.venv/bin/python benchmarks/terminal-bench/prepare.py
```

The [source manifest](source.toml) pins the upstream repository revision and task
tree. Downloaded source stays in ignored `runs/`; it is not vendored into this repo.
`prepare.py --verify-only` verifies an existing checkout without downloading it.
Preparation acquires files and verifies hashes; it does not launch an LLM.

## Review scope and machine resources

Read the [selected task scope](scope.json), [timing budgets](TIMING.md),
[budget notes](BUDGET.md), [reference qualifications](reference-validation/README.md)
and current [study notes](README.md). The experiment's task selection is not the
entire upstream dataset. Published timeouts are limits, not runtime forecasts.

Match task CPU/RAM needs and allow room for Docker overhead. Most images in the
pinned source are x86-only; Apple Silicon runs those through emulation and may have
machine-specific incompatibilities. Never lower task limits or alter graders to
manufacture passes. Do not restart Docker or prune images belonging to active jobs.

## Validate before model trials

```sh
.venv/bin/pennybench check benchmarks/terminal-bench/experiments/proxy-tb21-bounded.yaml
```

Review reference results and exclusions before registering a new experiment.
Reference checks execute supplied solutions, not model calls, but still run task code
and can consume significant Docker resources:

```sh
.venv/bin/pennybench oracle benchmarks/terminal-bench/experiments/proxy-tb21-bounded.yaml --workers 1
```

The reference-only compatibility notes document any original-machine qualifications;
they are not automatic modifications to either model arm's environment.

## Run with your own account

Only after completing those checks and fixing the study configuration in a clean
commit, run the model experiment:

```sh
.venv/bin/pennybench run benchmarks/terminal-bench/experiments/proxy-tb21-bounded.yaml --stop-at-utilization 0.90
```

This consumes subscription usage and runs both arms. To bound an initial diagnostic,
`--limit 2` runs at most two whole pairs; audit/report that bounded run with `--partial`.
Continue the same plan with `--resume <printed-run-directory>` after usage resets.
Do not start another run while one shares its artifact store or credential source.

The runner's `audit` and `report` commands take the printed run directory, not the
experiment file. Never mix reference results with model rewards, or claim results
for tasks outside the selected experiment. The current live study status remains
in [README.md](README.md); this packaging guide publishes no new results.
