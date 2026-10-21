# PennyRouter / Terminal-Bench 2.1 / pooled 2026-10-19 + 2026-10-20

Two independent k=1 runs cover the same 68 selected tasks: 272 finished trials.
This is a post-hoc pooled analysis, not a preregistered k=2 experiment.
Both source runs passed their full evidence audits. 

## Results

| Endpoint | Median change | 95% CI, median % | Sum of task medians | P-value |
| --- | ---: | ---: | ---: | ---: |
| Model-call cost | -31.1% | [-35.2, -25.5] | -10.4% | 5.05e-08 |
| Total tokens | -20.9% | [-23.0, -9.8] | +7.7% | 8.99e-04 |
| Output tokens | +0.9% | [-2.3, +13.7] | +25.1% | 0.056 |
| Fresh input tokens | +16.7% | [+0.0, +25.0] | -81.4% | 1.25e-04 |
| Cache-read tokens | -19.6% | [-21.6, -7.8] | +8.8% | 0.002 |
| Cache-write tokens | -24.4% | [-34.4, -14.4] | -7.2% | 1.83e-06 |
| Model calls | +0.0% | [+0.0, +16.7] | +15.9% | 0.050 |
| Agent execution time | +12.9% | [+4.9, +21.5] | -25.3% | 0.011 |

- Median task cost: -31.1% (95% interval -35.2% to -25.5%); 51/63 tasks cost less.
- Sum of per-task median costs: $5.459867 native vs. $4.892701 PennyRouter (-10.4%).
- Actual eligible spending: $9.698115 native vs. $8.527709 PennyRouter (-12.1%).
- Mean task reward: 84.1% native vs. 88.1% PennyRouter; 11 higher, 6 lower,
  46 tied; sign-test p=0.332.
- All-attempt passes: native 103/136 (75.7%), PennyRouter 104/136 (76.5%),
  preserving recorded errors as scored failures.

## Pooling method and interpretation

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

## Sensitivity: require both eligible repetitions

Restricting to 53 tasks with two eligible repetitions gives median task cost
-30.2%, summed per-task cost -14.2%, and mean task reward 81.1% native vs.
85.8% PennyRouter (sign-test p=0.332). See `both-repetitions-only.json`.

## Setup and source provenance

Both arms used Claude Code 2.1.302, Sonnet 5.5, medium effort, signed-in Claude
Pro subscriptions, no task-local skills, and per-trial cache isolation. Source
seeds are 20261019 and 20261020. Scope: agent and verifier limits of at most
30 minutes each and RAM at most 8 GB. Of 89 source tasks, 17 exceeded the
scope and four reference failures were excluded symmetrically, leaving 68.
Machine and reference qualifications are in [source.toml](../../source.toml)
and [reference-validation](../../reference-validation/README.md).

Source IDs `proxy-tb21-bounded` and `proxy-tb21-repeat-20261020` and original
manifest/metrics hashes are retained in `sources.json`. Public pooled trial IDs
are namespaced by source run; `source_trial_id` preserves each original ID.
Source exports in `source-runs/` retain their original experiment IDs and values.
Original trials, rewards, graders, manifests, and source runs are unchanged.

Both measured runs used the configured local PennyRouter endpoint. Follow
[HOW_TO_RUN.md](../../HOW_TO_RUN.md) using the hosted default
`https://api.pennyrouter.com` and your own linked account to reproduce.

## Evidence and public files

`audit.json` contains the two full passing source audits, explicitly identified
as source evidence. `run.json` describes the post-hoc analysis. `metrics.json`
and `trials.json` contain all 272 outcomes. `stats.json` includes the 20 dropped
task-repetitions; `outcomes.json` includes scores and failure labels over all
attempts. Raw captures, transcripts, credentials, account metadata, provider
message IDs, and local endpoint addresses are excluded from public exports.
