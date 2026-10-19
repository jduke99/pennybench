# 60-task report

Scope: the first 60 projects scheduled in the original 72-project evaluation. The user requested stopping further work and reporting these 60 tasks.

**57 comparable pairs** contribute to paired statistics. One project (paratransit-routing) has a native timeout. Two projects (fix-visual-stability and drone-planning-control) are omitted from audited evidence because both arms lack package inventories. The omissions are explicitly post-hoc; this is not a claim from a completed, pre-registered 60-project experiment. No grader, trial reward, original manifest, or original artifact was changed.

Trial directories here are links to the original preserved artifacts. Audit PASS means the included evidence passed the checks, not that missing evidence was recovered. Execution beyond the first 60 projects is outside this report.

## Report

```text
proxy-full-60-project-partial  stage=full  tasks=57
status: NOT A CLAIM — evaluation stopped after the first 60 scheduled projects; subset and environment omissions were selected post-hoc, not pre-registered
dropped pairs: 1 (a pair counts only if both arms completed)

endpoint            role           median              95% CI      H-L       p  lower/higher/eq    total
cost                primary        -34.0%      [-37.2, -28.4]   -32.5%   0.000     53/4/0        -30.1%
total_tokens        secondary      -18.0%      [-21.1, -14.7]   -18.3%   0.000     42/15/0        -18.6%
output_tokens       secondary       +4.3%        [-7.5, +7.3]    -0.7%   0.877     24/33/0         -0.7%
fresh_input_tokens  secondary      +25.0%      [+14.3, +33.3]   +25.1%   0.000      9/41/7        +24.1%
cache_read_tokens   secondary      -17.7%      [-23.0, -14.4]   -18.4%   0.000     43/14/0        -19.0%
cache_write_tokens  secondary      -20.6%      [-28.1, -13.2]   -21.3%   0.000     48/9/0        -19.0%
loc_written         exploratory     +0.0%        [+0.0, +8.3]    +2.8%   0.258     24/23/10        -4.8%
turns               secondary       +0.0%        [+0.0, +0.0]    +0.0%   0.912     19/17/21        +1.0%
wall_clock          secondary      -13.4%       [-19.8, +9.3]    -6.9%   0.244     34/23/0        -20.2%

reward (secondary): better 6, worse 4, equal 47; mean 0.5704035087719298 -> 0.6210526315789473; sign test p=0.754
  no non-inferiority margin declared: 'no difference detected' is not evidence of equal quality

median = per-task median change, treatment vs baseline. H-L = Hodges-Lehmann. p = Wilcoxon signed-rank on per-task log ratios. total = change in summed values.
```
