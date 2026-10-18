"""`pennybench report`: audit, then metrics and paired stats, all rebuilt from artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from pennybench.audit import write_audit
from pennybench.metrics import METRICS, run_metrics
from pennybench.stats import compute_stats


def build_report(run_dir: Path, partial: bool = False) -> dict:
    audit_passed, audit_path = write_audit(run_dir, partial)
    report = {"run_dir": str(run_dir), "audit_passed": audit_passed, "audit": str(audit_path)}
    if not audit_passed:
        return report
    manifest = json.loads((run_dir / "run.json").read_text())
    trials = run_metrics(run_dir)
    (run_dir / "metrics.json").write_text(json.dumps(trials, indent=2) + "\n")
    stats = compute_stats(manifest, trials, audit_passed, partial)
    (run_dir / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    report["stats"] = stats
    return report


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def _fmt_p(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def format_report(report: dict) -> str:
    if not report["audit_passed"]:
        return f"audit FAILED; no stats computed. See {report['audit']}"
    stats = report["stats"]
    lines = [f"{stats['experiment']}  stage={stats['stage']}  tasks={stats['n_tasks']}"]
    if stats["claim"]:
        lines.append("status: claim (full stage, pre-registered, audit passed)")
    else:
        lines.append("status: NOT A CLAIM — " + "; ".join(stats["not_a_claim_because"]))
    if stats["dropped_pairs"]:
        lines.append(f"dropped pairs: {len(stats['dropped_pairs'])} "
                     "(a pair counts only if both arms completed)")
    lines.append("")
    lines.append(f"{'endpoint':<20}{'role':<12}{'median':>9}{'95% CI':>20}{'H-L':>9}"
                 f"{'p':>8}{'lower/higher/eq':>17}{'total':>9}")
    for metric in METRICS:
        s = stats["endpoints"][metric]
        if metric == "reward":
            continue
        ci = s["ci95_median_pct"]
        ci_text = "—" if ci is None else f"[{ci[0]:+.1f}, {ci[1]:+.1f}]"
        lines.append(
            f"{metric:<20}{s['role']:<12}{_fmt_pct(s['median_pct']):>9}{ci_text:>20}"
            f"{_fmt_pct(s['hodges_lehmann_pct']):>9}{_fmt_p(s['wilcoxon_p']):>8}"
            f"{s['treatment_lower']:>7}/{s['treatment_higher']}/{s['equal']:<6}"
            f"{_fmt_pct(s['total_pct']):>9}")
    r = stats["endpoints"]["reward"]
    lines.append("")
    lines.append(
        f"reward ({r['role']}): better {r['treatment_better']}, worse {r['treatment_worse']}, "
        f"equal {r['equal']}; mean {r['mean_baseline']} -> {r['mean_treatment']}; "
        f"sign test p={_fmt_p(r['sign_test_p'])}")
    if r["non_inferiority"]:
        ni = r["non_inferiority"]
        lines.append(f"  non-inferiority at margin {ni['margin']}: "
                     f"{'passed' if ni['passed'] else 'not shown'} "
                     f"(one-sided 95% lower bound {ni['one_sided_95_lower']:+.3f})")
    else:
        lines.append("  no non-inferiority margin declared: 'no difference detected' is not "
                     "evidence of equal quality")
    lines.append("")
    lines.append("median = per-task median change, treatment vs baseline. H-L = Hodges-Lehmann. "
                 "p = Wilcoxon signed-rank on per-task log ratios. total = change in summed values.")
    return "\n".join(lines)
