# Contributing

The runner is shared under `pennybench/`; suite-specific files belong under
`benchmarks/<suite>/`. Keep model execution, task verification, audits and statistics
separate. Do not duplicate the runner per suite.

## Development checks

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest tests -q
```

Unit tests use fixtures and mocks. A normal test run should not require personal
credentials, model calls, or Docker task execution. Keep secrets out of tests and
examples; synthetic tokens must be unmistakably fake.

## New experiments and suites

- Pin model, harness, effort, source revision/hash, seed, task selection and rates.
- Change only the declared A/B variable. Label auth and resource-policy differences.
- Validate reference solutions and document symmetric exclusions before model runs.
- Put source provenance, setup instructions, experiments and result interpretation
  under the suite directory. Downloaded datasets belong in ignored `runs/`.
- Preserve existing experiment bytes and paths when a running job or recorded manifest
  depends on them. Review any migration before changing a reproduction command.
- Do not change graders, task instructions or resource limits to get a pass.
- Do not publish raw credentials, account metadata or unreviewed transcripts.

Building or testing code is not permission to start/stop a user's gateway, Docker
daemon, or active jobs. Public release and license selection require maintainer approval.
