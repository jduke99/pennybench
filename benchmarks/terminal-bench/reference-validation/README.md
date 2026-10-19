# Reference-only compatibility checks

Reference failures are investigated before any model evaluation. A failure in the
supplied reference implementation need not mean the task's instructions or grader
are invalid. A task may remain eligible when a documented correction to the
reference solution passes its unchanged grader, without changing the environment
or instructions given to either model arm. Preserve the original failed verdict,
the correction, and the supplemental verification result. Decide eligibility
before inspecting model outcomes.

## build-cython-ext

The unmodified reference failed twice: its unpinned `planarity` dependency resolved
to 1.0.0, which renamed the graph node attributes that pyknotid 0.5.3 expects.
The inner suite had 17 passes and one `KeyError: 'pos'`; the outer task verifier
had 10 passes and one failure. This reproduces
[upstream issue #75](https://github.com/harbor-framework/terminal-bench-2/issues/75).

A supplemental reference-only check installed `planarity` 0.6 after the original
solution. All 11 unchanged task-verifier checks then passed. The executed check
used `planarity<1`, which resolved to 0.6; the checked-in reproduction script pins
that exact resolved version. The original reward-zero verdicts remain intact.

The model arms receive the original pinned task environment and instructions.
They receive neither this dependency pin nor the reference repair. A valid agent
solution can select this dependency itself within the original task constraints.
No verifier, reward file, instruction, or source task tree was edited.

To reproduce, mount the original task's `solution/` at `/reference`, its unchanged
`tests/` at `/tests`, this script at `/validate.sh`, and a fresh output directory at
`/logs/verifier` in `alexgshaw/build-cython-ext:20251031`; run `bash /validate.sh`.
Use the task's declared one CPU and 2 GB RAM limits.

## protein-assembly

The unmodified reference failed twice after public PDB metadata changed. Its
parser relied on `modified_monomer` features to expand mature fluorophore
chromophores; those entries are absent in the current response, leaving `X` in
the canonical sequence and causing the DNA translation constraint to fail.

The reference-only repair reads the PDB sequence's explicit parenthesized
chemical-component codes and resolves their canonical amino acids through the
public RCSB chemical-component endpoint. For example, CR2 expands to GYG and CH6
to MYG. The repaired reference passed the one unchanged task-verifier test. The
original two reward-zero verdicts are preserved. Neither model arm receives this
parser repair, and no task source, instruction, environment, or grader is changed.

To reproduce, mount the original task's `solution/` at `/reference`, its unchanged
`tests/` at `/tests`, this script at `/validate.sh`, and a fresh output directory at
`/logs/verifier` in `alexgshaw/protein-assembly:20260403`; run `bash /validate.sh`.
Use the task's declared one CPU and 4 GB RAM limits. Public PDB, PubChem, and other
network dependencies remain mutable upstream dependencies of this task.

## mcmc-sampling-stan (not qualified)

`mcmc-sampling-stan.sh` installs cmake and then runs the unchanged reference
solution and verifier. The first failure (missing cmake for RcppParallel) goes
away, but the run still stops in the task's own Stan model: the pinned
rstan 2.32.7 `stanc` rejects its old `int n[num_obs]` array syntax. Qualifying
the task would need a change to the solution or an older Stan toolchain, so it
has no proof file and is excluded symmetrically before model trials.
