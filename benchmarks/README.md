# Benchmark suites

PennyBench is the shared measurement runner. Each benchmark suite has its own
dataset provenance, experiment definitions, compatibility notes, and reports.

| Suite | Status |
| --- | --- |
| [SkillsBench](skillsbench/README.md) | Evaluation stopped after 60 scheduled tasks; report retained. |
| [Terminal Bench](terminal-bench/README.md) | Terminal-Bench 2.1 reference-solution preflight in progress. |

The public repository layout is planned as:

```text
pennybench/                    shared runner, audits, metrics, statistics
arms/                          shared agent configurations
benchmarks/
  skillsbench/
    README.md                  scope, provenance, reproduction instructions
    experiments/               suite-specific experiment definitions
    reports/                   reviewed, publishable results
  terminal-bench/
    README.md
    source.toml                pinned upstream source and task-tree hash
    experiments/
    reports/
tests/                         shared runner tests
runs/                          ignored local datasets, captures, trial artifacts
```

Existing experiment and report paths remain in place during migration so saved
run manifests and reproduction commands remain valid. The suite pages link to
them. Future suites should follow this structure without duplicating the runner.

Before publishing:

- Move suite-specific experiments and reviewed reports into their suite folders;
  update commands and preserve the original paths recorded in historical manifests.
- Make dataset acquisition reproducible from pinned upstream revisions and hashes.
  Keep downloaded task trees and Docker layers out of Git.
- Review tracked files and Git history for credentials, account identifiers, host
  paths, and private endpoint details. Ignoring local files does not clean history.
- Publish reviewed aggregate results and provenance. Raw wire captures and agent
  transcripts require a separate privacy review before distribution.
- Add a repository license, dependency and dataset attribution, and contribution
  instructions. Keep the stopped SkillsBench report's limitations visible.

Publication is a separate step; no remote visibility change is part of preflight.
