# Terminal-Bench 2.1: k=1 repeat run plan

## Recorded results (do not change)

- Original run: `proxy-tb21-bounded.yaml`, 136 finished trials.
- Reported: aggregate cost −9.8%, median −31.7%.
- Exploratory rerun (`runs/proxy-tb21-rerun-cost-outliers/20261020T123845Z-5df0cc67`):
  4 pairs (`gpt2-codegolf`, `largest-eigenval`, `path-tracing`, `path-tracing-reverse`),
  cost +77.8% -> −29.6%, all 8 trials passed. These pairs were picked because they
  looked bad, so this is reported separately and never merged into the aggregate.

## Constraints

- Do not edit `proxy-tb21-bounded.yaml` or the original `run.json`. `check_resumable`
  rejects a changed experiment-file hash, and the plan reshuffles with the seed and
  renumbers pairs, so existing trial IDs (`0041-...-r0-treatment`) would not match.
- Do not patch the runner to allow k changes.
- The repeat is a new experiment file with a fresh seed, run as its own run directory.
- Hold the launch until weekly usage resets.

## Plan

1. Copy `proxy-tb21-bounded.yaml` to a new experiment file; set a new seed and a new run name.
   Keep k=1 (one rep per task and arm).
2. Dry-run the plan and confirm the task set matches the original.
3. Launch after the usage reset.
4. Report it as an independent replicate. If pooled with the original, use a separate
   pooling script that reads both run directories. Do not extend either in place.

## Open items from the original run

- `agent_error` trials: `0003-git-multibranch-r0-treatment`, `0004-build-pmars-r0-treatment`,
  `0007-make-doom-for-mips-r0-treatment` (and the `0007` baseline). Disposition not decided.
- Pair 41 unresolved.
- Decide whether to also run a fresh-seed k=2 follow-up.

## Completed independent replicate (2026-10-20)

- Experiment: `benchmarks/terminal-bench/experiments/proxy-tb21-repeat-20261020.yaml`;
  seed 20261020, k=1, the same 68 selected tasks and both arms.
- Artifacts: `runs/proxy-tb21-repeat-20261020/20261020T160701Z-2ac877c9`.
- All 136 trials finished; the full audit passed.
- This run started with `--allow-dirty`, before its experiment file was committed.
  It is an unregistered replicate; a later commit does not change that status.
  The original run and this replicate remain separate.
- Across 59 pairs with both statuses `complete`: total cost -14.4%, median
  per-task cost -31.9% (95% CI -34.4% to -20.7%); mean reward 84.7% in
  both arms (5 proxy wins, 5 losses, 49 ties); total wall clock +17.7%.
- Across all 68 tasks, preserving errors as scored failures: native 50/68
  successes, proxy 53/68. Classified failures: 8 native agent timeouts;
  1 proxy agent timeout and 3 proxy provider safeguard refusals.
- Nine pairs are excluded from paired statistics due to non-complete statuses.
- The usage guard changed from 90% to 98% after pair 55 finished. Account
  changes and laptop pauses occurred between trials, preserving saved results.

For future registered runs, commit the experiment and all outstanding repository
changes before launching, and do not pass `--allow-dirty`. Confirm the runner's
recorded `preregistered` flag before continuing beyond the initial trials.
