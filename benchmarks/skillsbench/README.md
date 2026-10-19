# SkillsBench

**60 tasks evaluated using Harbor and SkillsBench task-provided verifiers.**
PennyRouter reduced median model-call cost by 34.0% across 57 comparable pairs;
summed cost was 30.1% lower. Official rewards were higher on 6 projects, lower on 4,
and equal on 47. The methodology documents the 2 environment omissions and 1
incomplete pair; they remain visible in the task register.

- [HTML report](../../output/skillsbench-60/index.html)
- [PDF report](../../output/pdf/pennybench-skillsbench-60.pdf)
- [Markdown report](../../REPORT.md)
- [Results and publication status](results/README.md)

## Source and configuration

Dataset: `benchflow/skillsbench@v1.1`, with provenance pinned in [source.toml](source.toml).
Task-tree SHA256: `ef264365bf7b0efd05b7c270a668e08f545779b597a2aedc6711ce2674abea0d`.
Task-local skills are installed. Claude Code 2.1.302, Sonnet 5.5, medium effort,
signed-in Claude subscription, and per-trial cache isolation are shared by both arms.
Routing is the comparison variable.

The original full experiment selected 72 tasks after 15 reference-solution
exclusions. The published 60-task report covers the first 60 scheduled tasks, with
57 pairs contributing to statistics. Running `proxy-full.yaml` schedules its
original **72-task** plan, not a newly registered 60-task plan. The report's stopping
point and environment omissions were post-hoc; see its methodology.

## Reproduce the setup

Start with [installation and your own credentials](../../README.md), then:

```sh
.venv/bin/python benchmarks/skillsbench/prepare.py
.venv/bin/pennybench check benchmarks/skillsbench/experiments/proxy-smoke.yaml
```

`prepare.py` downloads the pinned registry dataset if missing and verifies the task
hash. It does not run containers, reference solutions, or models. To verify a
previous download without network access, use `prepare.py --verify-only`.

Review the source and resource requirements. A reference check uses no LLM, but
does execute supplied task code in Docker:

```sh
.venv/bin/pennybench oracle benchmarks/skillsbench/experiments/proxy-smoke.yaml --workers 1
```

Review failures before deciding exclusions for a new study; some original
exclusions were specific to Apple Silicon or dependency versions on the original
machine. Do not change graders, rewards, or resource limits to obtain passes.

Model trials consume your subscription/API usage:

```sh
.venv/bin/pennybench run benchmarks/skillsbench/experiments/proxy-smoke.yaml --stop-at-utilization 0.90
# After auditing smoke evidence, repeat or advance deliberately:
.venv/bin/pennybench run benchmarks/skillsbench/experiments/proxy-smoke-k3.yaml --stop-at-utilization 0.90
.venv/bin/pennybench run benchmarks/skillsbench/experiments/proxy-full.yaml --stop-at-utilization 0.90
```

Each command starts a different study stage; do not launch all stages at once.
Audit and report the exact run directory printed by each command before advancing.
Use `--resume` with the same experiment to continue after a usage-window stop.

## Licensing of the dataset

SkillsBench is Apache-2.0, but some task-local skills carry their own terms. About 30 of
the 232 bundled skills (Anthropic's docx, pdf, pptx and xlsx skills, among others) are
proprietary and must not be copied or redistributed. This repository ships no dataset
files; `prepare.py` downloads them into the ignored `runs/` directory. Do not commit
`runs/`, task directories or raw trial artifacts. See [THIRD_PARTY.md](../../THIRD_PARTY.md).

## Historical paths

The [root experiment files](../../experiments/proxy-full.yaml) remain intact for
existing manifests and commands. Suite experiment copies are byte-identical during
this migration. Raw evidence and downloaded datasets remain under ignored `runs/`.
Published results are not a guarantee that a later live model or package environment
will reproduce the same score.
