# PennyBench design

PennyBench measures whether a change to a coding agent's setup, such as a skill, a plugin, a
proxy, or a context policy, saves tokens, cost, or time without hurting task quality. It runs
the same tasks under two configurations, pairs them task by task, and reports only what the
paired data supports.

The method follows JetBrains' "token saver" series ([ponytail, part 3][ponytail]). PennyBench
adds ways for a third party to check every number.

[ponytail]: https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/

## Principles

1. **One variable.** Two arms differ in exactly the declared variable. The harness version,
   model, reasoning effort, task images, and auth mode are pinned and identical. The
   experiment loader diffs the arm specs and refuses to run if anything else differs.
2. **Pre-registration in git.** An experiment file declares arms, task set, endpoints, stage,
   k, and seed. The runner refuses a dirty tree and records the commit sha, so git history
   shows the endpoints were fixed before any paid trial ran.
3. **No stats before the audit passes.** The treatment must reach the model in every
   treatment trial and in no baseline trial, as shown by the request bytes, not by the
   configuration.
4. **Paired analysis only.** Per-task deltas, medians, and rank tests. A task that errors in
   either arm is dropped from both. Means are never a headline, because one long session can
   cost 25× a normal one.
5. **Escalation ladder.** Transcript audit → 10-task smoke → same 10 at k=3 → full set. Smoke
   and k=3 results are labeled as not a claim.
6. **Reproducible from artifacts.** Every reported number is a pure function of stored trial
   artifacts. `pennybench report <run>` rebuilds the full report from them.
7. **Systems under test are black boxes.** A proxy under test is only ever a base URL.
   PennyBench imports no code from any system it evaluates.

## Runtime: Harbor

[Harbor](https://github.com/laude-institute/harbor) supplies the Docker sandboxes, task
format, verifiers, and installed-agent adapters. PennyBench orchestrates on top of it.

From reading Harbor 0.24.0's `agents/installed/claude_code.py`:

- The Claude Code adapter installs a pinned version (`npm install -g
  @anthropic-ai/claude-code@<version>`) and checks `claude --version` after install.
- Its credentials are `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`, and its endpoint is
  `ANTHROPIC_BASE_URL`. That is how a proxy arm is routed.
- It sets `CLAUDE_CONFIG_DIR` to a per-trial directory, so the host's `~/.claude` (CLAUDE.md,
  memory, hooks) does not leak into trials.
- It supports skills, MCP servers, a settings JSON layer, and a memory directory, which are
  the injection points arms need.
- `--ae KEY=VALUE` passes arbitrary env vars to the agent.

Verified in phase 0:

- Subscription auth works by passing `CLAUDE_CODE_OAUTH_TOKEN` through `--ae`. A keyed proxy
  takes the token as `ANTHROPIC_AUTH_TOKEN` and its own key as `ANTHROPIC_API_KEY`.
- Harbor forwards host `ANTHROPIC_*` variables, so it runs under a minimal environment.
- Harbor keeps the `anthropic/` model prefix only when a base URL is set, so PennyBench passes
  the bare model id to keep request bytes identical across routes.
- Wire capture runs as a host-side mitmdump per trial. The container reaches it through
  `HTTPS_PROXY=http://host.docker.internal:<port>` and trusts its CA via a read-only mount and
  `NODE_EXTRA_CA_CERTS`. Wire usage matches Claude Code's own reported usage exactly.

Still unverified: Codex's ChatGPT-login auth through Harbor's `codex.py`.

## Layout

```
pennybench/
  pennybench/            Python package and `pennybench` CLI
    spec/                arm + experiment schemas, one-variable diff check
    runner/              pair scheduling, ABBA ordering, quota-aware resume, trial manifests
    capture/             wire capture (mitmproxy), transcripts, workspace diff snapshot
    audit/               adoption, contamination, pin, and exclusion-symmetry checks
    metrics/             endpoint extractors: tokens, cost, LOC, turns, wall-clock, reward
    stats/               paired tests, bootstrap, MDE/power, non-inferiority
    report/              HTML report built from artifacts only
    pricing/             pinned rate tables, versioned with the benchmark
  arms/                  public arm specs (stock, third-party tools)
  experiments/           pre-registered experiment files
  tasks/                 own task suites in Harbor format; vendored suites pinned by digest
  config.example.toml    template for local config
  tests/
```

Gitignored and outside the public surface:

- `pennybench.local.toml`: endpoints, credentials references, private arm specs, artifact
  store path.
- `runs/` (default artifact store) or any path the local config names.

## Local config

All deployment-specific details live in `pennybench.local.toml`, never in tracked files.
Tracked arm specs refer to them by name.

```toml
[artifacts]
store = "~/pennybench-runs"

[endpoints.penny]            # an arm uses route = "endpoint:penny"
base_url = "https://..."
auth_env = "PENNY_API_KEY"   # name of the env var, never the secret

[auth.claude-subscription]
token_env = "CLAUDE_CODE_OAUTH_TOKEN"

[arms_dir]
private = "~/pennybench-private/arms"
```

The run manifest records which named endpoint and auth profile a trial used, plus a hash of
the resolved, secret-free config. Secrets are never written to artifacts. The capture layer
redacts auth headers before storing.

## Arm spec

```yaml
id: claude-code-ponytail
harness: claude-code
harness_version: 2.1.201
model: claude-sonnet-5
effort: medium
auth: claude-subscription      # profile name from local config
route: native                  # or endpoint:<name>
inject:
  skills: []
  settings: {}
  hooks: []
  system_append_file: arms/ponytail/ruleset.txt   # sha256 recorded per trial
adoption_marker: "ponytail ladder"                 # string the audit expects in request bytes
```

An experiment names two arms and a declared variable, such as `inject` or `route`. The loader
fails if the arms differ anywhere else.

## Experiment file

```yaml
id: ponytail-replication-001
arms: [claude-code-stock, claude-code-ponytail]
variable: inject
tasks: skillsbench@<digest>
exclude: []                    # reasons are required
stage: full                    # audit | smoke | smoke-k3 | full
k: 1
seed: 20261018
endpoints:
  primary: [cost]
  secondary: [reward, loc_written, output_tokens, fresh_input_tokens, total_tokens, turns, wall_clock]
quality: { test: sign, non_inferiority_margin: null }
```

## Trial lifecycle

1. **Resolve** both arm specs with local config, check pins, and compute the injected-content
   hashes.
2. **Schedule** pairs. Arm order alternates (ABBA) across pairs so drift, throttling, and
   cache warmth fall evenly on both arms.
3. **Run** through Harbor with mitmproxy in the agent's egress path. Both arms go through the
   same capture point.
4. **Collect** the wire capture, harness transcript, Harbor verifier result, and a `git diff`
   of the final workspace.
5. **Seal** the trial: write a manifest with hashes of every artifact, the pins, the
   endpoint/auth profile names, and timings.

## Measurement

The wire capture is the canonical source for tokens. It is the one vantage point both arms
share, whatever proxy sits behind it. A proxy's self-reported usage is never used for a
comparison.

| Endpoint | Source |
|---|---|
| reward | Harbor verifier (0–1, partial credit) |
| fresh input / cache read / cache write / output tokens | `usage` blocks in captured responses |
| total tokens | sum of the above, reported separately from output-only |
| cost | tokens × pinned rate table; labeled notional when the trial ran on a subscription |
| LOC written | non-blank, non-comment added lines in the final workspace diff; tool-call emitted lines as a secondary measure |
| turns | captured request count to the model endpoint |
| wall-clock | trial start to agent exit |

## Audit gate

Each check writes to the run's audit report. Stats refuse to run if any check fails.

- **Adoption:** the adoption marker appears in the request bytes of 100% of treatment trials
  and 0% of baseline trials.
- **Pins:** the recorded harness version, model, and effort match the specs in every trial.
- **Isolation:** no host config paths and no unexpected injected content in the captures.
- **Route:** every trial's requests went to the endpoint its arm declares.
- **Exclusion symmetry:** every excluded task is excluded from both arms, with a reason.
- **Self-activation (optional stage):** for skill arms, whether the model invokes the skill
  when it is only installed.

## Statistics

- Per-task paired deltas. Cost and tokens are compared as log ratios.
- Wilcoxon signed-rank test, Hodges-Lehmann estimate, and a bootstrap CI on the median
  percent change.
- Sign test for reward. A non-inferiority test runs only when the experiment declares a
  margin.
- Before a full stage starts, the runner prints the minimum detectable effect for the planned
  n, using the k=3 stage's variance.
- Thresholds or splits chosen after seeing data (for example, by baseline output size) are
  labeled exploratory in the report.

## Known threats

- **Prompt cache cross-talk.** Arms that share a prefix warm each other's cache. Unless the
  experiment is about caching, an optional per-arm nonce at the start of the system prompt
  isolates them. Cache reads per arm are always reported.
- **Short tasks.** Public suites are mostly short. Interventions that act on long sessions
  (compaction, caching, tool pruning) are under-measured, so a long-horizon suite is planned.
- **Subscription quota.** Rate-limit windows cap throughput. The runner must pause and resume
  without breaking pairing or ordering.
- **Notional cost.** Subscription runs have no bill. Cost is computed from tokens and the
  pinned rates and labeled as such.

## Phases

0. **Feasibility.** Harbor runs one SkillsBench and one Terminal-Bench task with Claude Code on
   subscription auth. Wire capture works inside the sandbox egress. A proxy arm routes through
   `ANTHROPIC_BASE_URL`.
1. **Core.** Spec loader with the one-variable check, runner, capture, audit gate, metrics,
   stats, report.
2. **Calibration.** Replicate the ponytail experiment. The harness passes if it lands near the
   published −10.3% cost and −15% LOC, within our CIs.
3. **Own experiments.** Proxy-vs-native, single levers on/off, and other third-party tools.
4. **Long-horizon suite** and a Codex harness.
