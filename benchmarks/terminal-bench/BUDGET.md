# Initial cost-study budget estimate

Estimate date: 2026-10-19. No paid model run has started and no dollar spending cap
has been implemented by this document.

Sonnet 5.5 rates read from PennyRouter `apps/compare/rates.json`, generated
2026-10-15, in USD per million tokens:

| Fresh input | Cache read | 5-minute cache write | 1-hour cache write | Output |
| ---: | ---: | ---: | ---: | ---: |
| 2.00 | 0.10 | 2.50 | 4.00 | 10.00 |

The closest published medium-effort observation found is Artificial Analysis's
[Sonnet 5.5 medium model page](https://artificialanalysis.ai/models/claude-sonnet-5-5-medium).
Its embedded `intelligenceIndexEvaluations` data reports Terminal-Bench **4.0** at
51,617.79 output tokens per attempt and $1.57816 total per attempt. The page's
input, output, cache-read, and cache-write prices match the rates above. Generated
output therefore accounts for about $0.516 of that total; input/cache costs account
for about $1.062. The output figure includes reasoning and answer tokens.

This is a measured observation on another benchmark version and harness, not a
measured forecast for our Terminal-Bench 2.1 / Claude Code run. No direct Sonnet
5.5 medium Terminal-Bench 2.1 token measurement was found. The model page reports
that evaluation as null. Do not substitute Intelligence Index aggregate token
usage for Terminal Bench token usage.

Using $1.58 per trial as a provisional planning anchor:

| Stage or scope | Trials | Approximate API-equivalent cost |
| --- | ---: | ---: |
| Initial 10-task paired smoke | 20 | $32 |
| Selected study after four preflight exclusions, both arms, once | 136 | $215 |

A $1–$3-per-trial sensitivity range makes the selected study $136–$408. The
user selected all 72 tasks on 2026-10-19, with subscription authentication and
ascending published time limits. The 10-task row remains a sizing reference,
not an additional run or an approval requirement. Retries,
long tasks, cache-write TTL, and agent behavior can move the actual cost outside
that range. No proxy savings are assumed in this budget: estimating those savings
is the purpose of the experiment. Reference solutions use no model calls.

Replace the planning anchor with captured token counts as pairs complete.
Cost under subscription authentication is notional
API-equivalent usage rather than a separate bill for included subscription usage.
