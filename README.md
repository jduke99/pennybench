# PennyBench

Paired A/B benchmarking for coding-agent setups: skills, plugins, proxies, and context
policies. PennyBench runs the same tasks under two configurations that differ in one
variable, checks that the treatment actually reached the model, and reports per-task paired
effects on cost, tokens, code written, time, and verified task quality.

See [DESIGN.md](DESIGN.md) for the architecture and method.

## Local config

Copy `config.example.toml` to `pennybench.local.toml` (gitignored) and fill in your artifact
store, endpoints, and auth profiles. Tracked files never contain endpoints or secrets.
