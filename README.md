# PennyBench

Paired A/B benchmarking for coding-agent setups: skills, plugins, proxies, and context
policies. PennyBench runs the same tasks under two configurations that differ in exactly one
variable, proves from the captured traffic that the treatment reached the model, and reports
per-task paired effects on cost, tokens, code written, time, and verified task quality.

The method follows JetBrains' token-saver series ([ponytail, part 3][ponytail]).
[DESIGN.md](DESIGN.md) explains the architecture and the reasoning behind each rule.

[ponytail]: https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/

## How a measurement works

| Term | Meaning |
|---|---|
| **Arm** | One agent configuration: harness and version, model, effort, auth, route, injected files (`arms/*.yaml`). |
| **Experiment** | Two arms, the one variable they differ in, a task set, the endpoints to report, a stage, `k`, and a seed (`experiments/*.yaml`). |
| **Pair** | One task run once under each arm, back to back, in alternating order. |
| **Run** | One execution of an experiment, saved under the artifact store with everything needed to recompute its results. |
| **Stage** | Step on the escalation ladder: `audit` → `smoke` (10 tasks) → `smoke-k3` (same 10, 3 reps) → `full`. Only `full` can be a claim. |

Every run goes through the same pipeline:

```
pennybench run  →  pennybench audit  →  pennybench report
   trials           7 checks on the       metrics + paired stats,
   (Harbor +        raw artifacts;        refused if the audit
   wire capture)    fail = no stats       failed
```

A result is labeled a **claim** only if the stage is `full`, the run started from a committed
tree (so the experiment was fixed before any data existed), and the audit passed. Anything
else is printed as **NOT A CLAIM** with the reasons.

## One-time setup

Requirements: macOS or Linux, Docker running, [uv](https://docs.astral.sh/uv/), Python 3.12.

1. **Install.**

   ```sh
   uv venv .venv --python 3.12
   uv pip install --python .venv/bin/python -e ".[dev]"
   .venv/bin/python -m pytest tests -q        # should all pass
   ```

2. **Local config.** Copy `config.example.toml` to `pennybench.local.toml` (gitignored) and
   set:
   - `[artifacts] store`: where runs, datasets, and caches go (default `runs/`, gitignored).
   - `[auth.<name>]`: one entry per credential. `kind = "oauth"` for a Claude subscription,
     `kind = "api_key"` for an API key. `token_env` names the variable that holds it.
   - `[endpoints.<name>]`: only for proxy arms (see below).
   - `[docker]`: `builder = "pennybench"` and `build_cache_cap_gb = 40` keep task images on a
     dedicated build cache capped at 40 GB, separate from your other projects' cache.

3. **Secrets.** Put them in `.env` (gitignored), never in tracked files:

   ```sh
   CLAUDE_CODE_OAUTH_TOKEN=...   # from `claude setup-token`, for kind = "oauth"
   PENNY_API_KEY=pr-...          # only if a proxy endpoint needs its own key
   ```

   PennyBench reads `.env` itself and passes secrets to Harbor under private names. They never
   appear in argv, Harbor's saved config, or any artifact; every trial is scanned for them and
   a hit aborts the run.

## Running an experiment

The ponytail calibration (`experiments/ponytail-*.yaml`) is the worked example. Each step
below is a command plus what to look at before moving on.

### 0. Validate

```sh
.venv/bin/pennybench check experiments/ponytail-full.yaml
```

This loads both arms and fails if they differ in anything besides the declared variable.
Injected files and skill directories are compared by content hash. It also downloads and
verifies a pinned dataset on first use and prints the task and trial counts.

### 1. Oracle pass (once per task set, free)

```sh
.venv/bin/pennybench oracle experiments/ponytail-full.yaml --workers 3
```

This runs every task's own reference solution with no model calls. A task that fails it is
broken on this machine and cannot measure an agent. Add each one to `exclude:` in **every**
experiment that uses the task set, with a reason, and commit. Results are saved under
`<store>/oracle/`, and rerunning the command skips tasks that already have a result. The
first pass builds every task image, so expect it to take a while.

### 2. Wiring check (two short trials)

```sh
.venv/bin/pennybench run experiments/smoke-ponytail-wiring.yaml --allow-dirty
.venv/bin/pennybench audit runs/smoke-ponytail-wiring/<run-dir>
```

This runs one trivial task per arm. The audit must pass, which proves both arms
authenticate, route where declared, and that the treatment marker reaches the model in the
treatment arm and never in the baseline. Do this whenever an arm or the harness version
changes.

### 3. Commit, then run each stage in order

Runs refuse to start from an uncommitted tree; that is what makes the experiment
pre-registered. Commit any experiment edits first.

```sh
git commit -am "Pre-register ponytail stages"

.venv/bin/pennybench run experiments/ponytail-smoke.yaml
.venv/bin/pennybench report runs/ponytail-smoke/<run-dir>

.venv/bin/pennybench run experiments/ponytail-smoke-k3.yaml
.venv/bin/pennybench report runs/ponytail-smoke-k3/<run-dir>

.venv/bin/pennybench run experiments/ponytail-full.yaml
.venv/bin/pennybench report runs/ponytail-full/<run-dir>
```

- **smoke** catches setup problems at small cost. Its numbers are not results: JetBrains'
  10-task smoke pointed the wrong way on both cost and quality.
- **smoke-k3** measures run-to-run noise. Its report includes `mde_pct`, the smallest effect
  the current sample could detect. Use it to judge whether the full set is large enough.
- **full** is the only stage that can produce a claim.

Do not edit an experiment after its run starts. `--resume` refuses if the experiment file,
the commit, or the trial plan has changed.

### Long runs: limits and resuming

```sh
.venv/bin/pennybench run experiments/ponytail-full.yaml --limit 10          # first 10 pairs
.venv/bin/pennybench run experiments/ponytail-full.yaml --resume runs/ponytail-full/<run-dir>
```

`--limit` counts whole pairs, so a stopped run never leaves one arm ahead of the other.
`--resume` skips finished trials and retries unfinished ones.

## Reading the results

`pennybench audit <run-dir>` writes `audit.json` and checks:

| Check | Fails when |
|---|---|
| complete | a planned trial did not finish |
| capture | a completed trial has no model calls on the wire, or a body could not be decoded |
| route | a model call went to a host other than the one its arm declares |
| pins | the agent version or model differs from the arm spec |
| adoption | the treatment marker is missing from a treatment trial, or present in a baseline trial |
| isolation | your home-directory path appears in a request (host config leaked in) |
| pairing | a pair has only one arm, or an excluded task ran |

`pennybench report <run-dir>` writes `metrics.json` and `stats.json` and prints one row per
endpoint:

| Column | Meaning |
|---|---|
| median | per-task median change, treatment vs baseline, from per-task log ratios |
| 95% CI | bootstrap interval on that median |
| H-L | Hodges-Lehmann estimate of the shift |
| p | Wilcoxon signed-rank test |
| lower/higher/eq | tasks where the treatment was lower, higher, equal |
| total | change in the summed values, which one expensive task can dominate |

Reward uses a sign test. "No difference detected" is not evidence of equal quality; that
needs `non_inferiority_margin` set in the experiment before the run.

Cost is **notional**: captured tokens × the pinned rates in `pennybench/rates.json`. A
subscription run has no bill, so the report never presents it as one.

## Adding your own experiment

**An arm** (`arms/<id>.yaml`, file name = id):

```yaml
id: cc-sonnet-mytool
harness: claude-code
harness_version: "2.1.302"          # exact release; the binary is fetched and verified
model: claude-sonnet-5-5            # must exist in pennybench/rates.json
effort: medium                      # low | medium | high | xhigh | max | null
auth: claude-subscription           # a profile in pennybench.local.toml
route: native                       # or endpoint:<name>
inject:                             # optional, any of:
  instruction_append_file: arms/mytool/rules.txt   # appended after the task text
  append_system_prompt_file: arms/mytool/sys.txt   # appended to the system prompt
  skills_dir: arms/mytool/skills/mytool            # one skill directory to install
  settings_file: arms/mytool/settings.json         # Claude Code settings layer
adoption_marker: "MYTOOL ACTIVE"    # exact text that must appear in treatment requests
```

**An experiment** (`experiments/<id>.yaml`, file name = id):

```yaml
id: mytool-full
arms: [cc-sonnet-stock, cc-sonnet-mytool]   # [baseline, treatment]
variable: inject                            # the only field allowed to differ
tasks:                                      # a repo path, or a pinned registry dataset
  dataset: benchflow/skillsbench@v1.1
  sha256: ef264365bf7b0efd05b7c270a668e08f545779b597a2aedc6711ce2674abea0d
sample: 10                                  # optional seeded subset, after exclusions
exclude:
  - task: bike-rebalance
    reason: requires no-network mode, unsupported by Harbor's Docker environment
stage: full                                 # audit | smoke | smoke-k3 | full
k: 1
seed: 20261018
endpoints:
  primary: [cost]
  secondary: [reward, loc_written, output_tokens, fresh_input_tokens, total_tokens, turns, wall_clock]
quality: { test: sign, non_inferiority_margin: null }
```

To pin a new dataset, download it once and record its content hash:

```sh
.venv/bin/harbor download org/name@<ref> -o /tmp/ds
.venv/bin/python -c "from pathlib import Path; from pennybench.digest import tree_sha256; print(tree_sha256(Path('/tmp/ds/<name>')))"
```

Refs must be fixed tags; `@latest` is rejected.

## Proxy arms (for example, PennyRouter)

A proxy is only ever a base URL. PennyBench imports no code from anything it measures.

```toml
# pennybench.local.toml
[endpoints.proxy]
base_url = "http://host.docker.internal:8400"   # a proxy on this machine, seen from Docker
key_env = "PENNY_API_KEY"                       # the proxy's own key, if it needs one
env = { ENABLE_TOOL_SEARCH = "true" }           # extra agent env the proxy needs
```

An arm with `route: endpoint:proxy` then sends the subscription token as the bearer and the
proxy key as `x-api-key`. To point the same arms at a hosted proxy, change `base_url` only.
Start and stop the proxy yourself; PennyBench never does.

## Where things are saved

```
<store>/
  <experiment>/<UTC time>-<commit>/   one run
    run.json                          commit, experiment hash, arms, pins, builds, full plan
    trials/<pair>-<task>-r<rep>-<role>/
      trial.json                      status, reward, versions, sha256 of every artifact
      wire/wire.jsonl                 every model request and response (credentials hashed)
      harbor/                         Harbor's own trial output and transcripts
    audit.json  metrics.json  stats.json
  oracle/<dataset>/                   oracle verdicts per task
  .datasets/                          pinned task sets
  .agents/claude-code/<version>/      verified Claude Code binaries mounted into trials
```

`pennybench report` recomputes everything from these files, so anyone with a run directory can
check every number.

## Known gaps

- **Rate limits.** Nothing yet pauses for a subscription's usage window. A trial that runs
  out of retries against the limit should end as an agent error, and its pair is dropped. Watch the first stages and keep
  `--limit` batches small on a single subscription.
- **Lines of code** are counted from what the agent wrote through its tools, not from a final
  workspace diff, so a line rewritten twice counts twice. Subagent calls go through the same
  capture, so their writes count; files a script writes at runtime are not seen, in either
  arm.
- **Harnesses.** Claude Code only. The Codex harness is planned.
- **Report format.** Text and JSON only; an HTML report is planned.
