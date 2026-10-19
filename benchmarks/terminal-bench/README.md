# Terminal Bench

The next suite is Terminal-Bench 2.1, pinned by [source.toml](source.toml).
The 89-task source is downloaded locally under
`runs/terminal-bench-prep/source/`; it is not vendored into the public repo.

The comparison uses the same Claude Code native and PennyRouter proxy arms as
SkillsBench, varying only the route. There are no task-local skills in this suite.

Current gate: validate the runner and task reference solutions before registering
model experiments. No Terminal Bench model results are available yet.

[Timing budgets for every task](TIMING.md) distinguish published timeouts from
measured local reference runtimes and model-run scheduling scenarios.
[Initial budget estimate](BUDGET.md) uses published medium-effort Sonnet 5.5
measurements as a provisional planning anchor. Those measurements are from 4.0,
not a direct forecast for the selected 2.1 tasks.

The user selected Terminal-Bench 2.1 for this first bounded cost study.
The [selection rule and task list](scope.json)
keeps tasks with published agent and verifier limits of at most 30 minutes each,
and task RAM at most 8 GB. This leaves 72 candidates before oracle exclusions;
17 longer tasks are outside the initial scope. The selected run covers all 72
tasks once under each arm (144 trials), using the user's Claude subscription login.
The [experiment definition](experiments/proxy-tb21-bounded72.yaml) pins the source
task tree and schedules ascending agent time limits, then verifier limits, with
seeded ties. Native/proxy trials stay adjacent and their order alternates.
Results will describe this selected subset, not the entire suite. Reference
failures must be investigated before launching the model evaluation.

The 30-minute cutoff selects tasks; it does not change their declared limits or
guarantee a 30-minute total runtime. Setup and verification add time. The 8 GB
per-task ceiling is separate from Docker's total allocation; tasks that cannot
fit alongside Docker overhead remain on resource hold.

Preflight sequence:

1. Verify the task-tree hash and inventory image architectures without pulling all
   images. Inventory complete: 85 images are x86-only and four also support arm64.
   The x86-only tasks require emulation on the current arm64 Mac.
2. Collect package inventories from declared prebuilt images, preserving those
   shared images. Derive the outer process timeout from task phase limits.
3. Validate one reference solution, then run eligible reference solutions with
   resource and disk checks. Docker was increased to a 16 GB total allocation on
   2026-10-19 to accommodate the selected tasks' unchanged limits of up to 8 GB.
4. Investigate failures and record any symmetric exclusions with reasons. Do not
   change graders, rewards, or task resource limits to obtain passes.
5. Finalize and commit the 72-task definition after investigating reference
   failures. Audit the initial completed pairs as a wiring check before continuing.
   A failed reference check or missing RAM is not silently converted to an agent
   failure or removed from the selected task count.

The local draft `runs/terminal-bench-prep/terminal-bench-preflight.yaml` is for
reference-solution checks, not a registered model evaluation. Oracle verdicts
and logs are saved under `runs/oracle/`.

Initial validation on 2026-10-19: `adaptive-rejection-sampler` completed under
x86 emulation with reward 1.0 (all nine verifier checks passed), and its package
inventory was captured successfully. The serial reference pass is in progress;
this first pass does not establish compatibility for the remaining tasks.

Local progress: `runs/terminal-bench-prep/reference-pass.log`. Tasks that exceed
available RAM are held in `resource-holds.json`, rather than excluded or run with
reduced limits. Images fetched by this pass are removed after each task so the
full suite does not need to fit on disk at once.
The model experiment also removes each prebuilt task image after both arms finish,
using a non-forced removal. It retains the image between the arms of a pair.

Public reproduction instructions and reviewed results will live here as the
[suite layout](../README.md) is completed.
