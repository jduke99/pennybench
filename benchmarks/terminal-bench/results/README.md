# PennyRouter / Terminal-Bench 2.1 / pooled 2026-10-19 + 2026-10-20

Read the [HTML](https://jduke99.github.io/pennybench/pennyrouter-tb21-20261019-20261020/),
[PDF](../../../output/pdf/pennyrouter-tb21-20261019-20261020.pdf), or
[full Markdown report](pennyrouter-tb21-20261019-20261020/REPORT.md).

Two independent k=1 runs cover the same 68 selected tasks: 272 finished trials.
This is a post-hoc pooled analysis, not a preregistered k=2 experiment.
Both source runs passed their full evidence audits. 


## Result overview

- Median per-task model-call cost: **31.1% lower** (95% interval 25.5%-35.2% lower).
- Actual spending across 116 eligible repetitions: **12.1% lower**.
- Sum of per-task median costs: **10.4% lower**; this uses different task weights.
- Mean task reward: native **84.1%**, PennyRouter **88.1%** (sign-test p=0.332).
- All-attempt passes: native **103/136 (75.7%)**, PennyRouter **104/136 (76.5%)**.

Within each task, each arm's value is its median over eligible repetitions.
Ratios and tests are then computed across tasks, using the existing runner's
pooling rules. The task is the statistical unit; the 272 trials are not treated
as 272 independent tasks. With two binary rewards, a task value may be 0.5.
Mean task rewards are therefore distinct from all-attempt pass rates.

Table sums add the 63 per-task arm medians, giving each task one contribution.
Actual eligible spending adds all 116 eligible task-repetitions per arm, so
some tasks contribute twice and others once. These different weights explain
why the table's cost change is -10.4% while actual eligible spending fell 12.1%.
First-page cost bars in the HTML and PDF show actual eligible spending.

Costs are notional model-call USD from captured token usage and pinned rates,
not subscription charges. Gateway overhead is unavailable. Cost is primary;
other endpoints are secondary and their p-values are unadjusted. Confidence
intervals bootstrap task-level median changes with seed 20261020 and 10,000
resamples. Wilcoxon tests use paired task-level log ratios. Reward uses a sign
test. No non-inferiority margin was declared; a nonsignificant difference does
not establish equivalent quality or non-inferiority.

## Files in [pennyrouter-tb21-20261019-20261020/](pennyrouter-tb21-20261019-20261020/)

| File | Contents |
| --- | --- |
| `REPORT.md`, `stats.json` | Full methods, task-level statistics and 20 excluded task-repetitions |
| `outcomes.json` | All-attempt scores, classified failures and actual eligible spending |
| `metrics.json`, `trials.json` | All 272 outcomes, with namespaced IDs and original source trial IDs |
| `run.json`, `sources.json` | Post-hoc analysis description, source IDs, source hashes and pooling rules |
| `audit.json` | Both full source-run audits; no new pooled audit is claimed |
| `both-repetitions-only.json` | Sensitivity analysis restricted to 53 tasks with two eligible repetitions |
| `source-runs/` | Sanitized manifests, audits, statistics, metrics and trial records for each source run |

## Reproduce the report

```sh
.venv/bin/python benchmarks/terminal-bench/export_results.py \
  runs/proxy-tb21-bounded/<first-run-id> \
  runs/proxy-tb21-repeat-20261020/<second-run-id> \
  --out benchmarks/terminal-bench/results/pennyrouter-tb21-20261019-20261020
.venv/bin/python benchmarks/terminal-bench/build_report_page.py
```

To reproduce the model trials, follow [HOW_TO_RUN.md](../HOW_TO_RUN.md) with
your own linked account and the hosted default `https://api.pennyrouter.com`.
The measured source runs used a configured local PennyRouter endpoint; its
address is redacted. The hosted default is the recommended reproduction route.

The [source manifest](../source.toml) and
[reference qualifications](../reference-validation/README.md) document task
provenance and machine compatibility. Source experiment IDs remain unchanged.
The former single-run report is archived privately under gitignored drafts.
Raw captures, sessions, credentials, account metadata, provider message IDs,
and local endpoint addresses are not public exports.
