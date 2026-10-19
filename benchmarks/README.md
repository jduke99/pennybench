# Benchmark suites

`pennybench/` is the shared runner. Each suite owns its provenance, experiment
definitions, compatibility notes, and results documentation. No suite forks the runner.

| Suite | Entry point |
| --- | --- |
| SkillsBench | [60-task report, provenance and reproduction](skillsbench/README.md) |
| Terminal-Bench 2.1 | [Reproduction guide](terminal-bench/HOW_TO_RUN.md) and [current study](terminal-bench/README.md) |

```text
pennybench/                    shared runner, capture, audit, metrics and statistics
arms/                          shared pinned agent configurations
benchmarks/
  smoke-login.yaml             tiny shared subscription wiring check
  skillsbench/
    README.md
    source.toml
    prepare.py
    experiments/               suite-specific experiment definitions
    results/                   reviewed-result index
  terminal-bench/
    README.md
    HOW_TO_RUN.md
    source.toml
    prepare.py
    experiments/
tests/                         shared runner and packaging tests
runs/                          ignored private evidence, downloaded tasks and caches
```

## Incremental migration

Historical files under root `experiments/`, `REPORT.md` and `output/` retain their
paths. Saved manifests and active jobs must continue to work. SkillsBench's suite
copies initially preserve the original experiment bytes and names; suite docs use
the new paths. Terminal-Bench's live definitions are managed separately and are not
moved by this packaging increment.

The checked-in configuration example uses hosted PennyRouter. A custom HTTPS
endpoint can be configured for a private server. Each reader supplies their own
subscription or API credentials; see [the auth guide](../docs/CREDENTIALS.md).

Before public release, follow the [publication checklist](../docs/PUBLICATION.md).
Raw captures and agent transcripts are private by default. Packaging does not change
remote visibility, run any experiments, or decide licensing.
