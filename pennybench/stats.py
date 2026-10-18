"""Paired statistics over a run's per-trial metrics.

The unit of analysis is the task. A (task, rep) pair counts only if both arms completed;
otherwise it is dropped from both and listed. With k > 1, each arm's value for a task is the
median over its counted reps. Ratio endpoints are compared as per-task log ratios, so one
expensive session cannot dominate; reward uses a sign test.
"""

from __future__ import annotations

import math
from statistics import median

import numpy as np
from scipy import stats as sps

from pennybench.metrics import METRICS

RATIO_METRICS = tuple(m for m in METRICS if m != "reward")
BOOTSTRAP_RESAMPLES = 10_000
Z_ALPHA, Z_POWER = 1.959964, 0.841621  # two-sided 5%, 80% power


class StatsError(ValueError):
    pass


def paired_tasks(trials: list[dict]) -> tuple[dict[str, dict[str, dict]], list[dict]]:
    """Per task, each arm's median metric values over counted reps; plus the dropped pairs."""
    by_pair: dict[tuple[str, int], dict[str, dict]] = {}
    for t in trials:
        by_pair.setdefault((t["task"], t["rep"]), {})[t["role"]] = t
    kept: dict[str, dict[str, list[dict]]] = {}
    dropped = []
    for (task, rep), arms in sorted(by_pair.items()):
        statuses = {role: arms[role]["status"] if role in arms else "missing"
                    for role in ("baseline", "treatment")}
        if set(statuses.values()) != {"complete"}:
            dropped.append({"task": task, "rep": rep, **statuses})
            continue
        for role in ("baseline", "treatment"):
            kept.setdefault(task, {}).setdefault(role, []).append(arms[role]["metrics"])
    tasks = {}
    for task, arms in kept.items():
        tasks[task] = {}
        for role, reps in arms.items():
            tasks[task][role] = {
                m: median(vals) if (vals := [r[m] for r in reps if r[m] is not None]) else None
                for m in METRICS
            }
    return tasks, dropped


def hodges_lehmann(x: np.ndarray) -> float:
    i, j = np.triu_indices(len(x))
    return float(np.median((x[i] + x[j]) / 2))


def _pct(log_ratio: float) -> float:
    return math.expm1(log_ratio) * 100


def ratio_summary(tasks: dict, metric: str, rng: np.random.Generator) -> dict:
    logs, one_sided_zero, missing = [], [], []
    better = worse = same = 0
    total_b = total_t = 0.0
    for task, arms in sorted(tasks.items()):
        b, t = arms["baseline"][metric], arms["treatment"][metric]
        if b is None or t is None:
            missing.append(task)
            continue
        total_b += b
        total_t += t
        better += t < b
        worse += t > b
        same += t == b
        if b == 0 and t == 0:
            logs.append(0.0)
        elif b == 0 or t == 0:
            one_sided_zero.append(task)
        else:
            logs.append(math.log(t / b))
    x = np.array(logs)
    out = {
        "n_tasks": len(x),
        "excluded_zero_in_one_arm": one_sided_zero,
        "missing": missing,
        "treatment_lower": int(better),
        "treatment_higher": int(worse),
        "equal": int(same),
        "total_baseline": total_b,
        "total_treatment": total_t,
        "total_pct": (total_t / total_b - 1) * 100 if total_b else None,
        "median_pct": None, "hodges_lehmann_pct": None, "ci95_median_pct": None,
        "wilcoxon_p": None, "log_ratio_sd": None, "mde_pct": None,
    }
    if len(x) == 0:
        return out
    out["median_pct"] = _pct(float(np.median(x)))
    out["hodges_lehmann_pct"] = _pct(hodges_lehmann(x))
    boots = np.median(rng.choice(x, size=(BOOTSTRAP_RESAMPLES, len(x)), replace=True), axis=1)
    out["ci95_median_pct"] = [_pct(float(np.percentile(boots, 2.5))),
                              _pct(float(np.percentile(boots, 97.5)))]
    if np.any(x != 0):
        out["wilcoxon_p"] = float(sps.wilcoxon(x, zero_method="wilcox").pvalue)
    if len(x) > 1:
        sd = float(np.std(x, ddof=1))
        out["log_ratio_sd"] = sd
        out["mde_pct"] = _pct((Z_ALPHA + Z_POWER) * sd / math.sqrt(len(x)))
    return out


def reward_summary(tasks: dict, margin: float | None, rng: np.random.Generator) -> dict:
    pairs = [(a["baseline"]["reward"], a["treatment"]["reward"]) for a in tasks.values()
             if a["baseline"]["reward"] is not None and a["treatment"]["reward"] is not None]
    better = sum(t > b for b, t in pairs)
    worse = sum(t < b for b, t in pairs)
    out = {
        "n_tasks": len(pairs),
        "treatment_better": better,
        "treatment_worse": worse,
        "equal": len(pairs) - better - worse,
        "mean_baseline": float(np.mean([b for b, _ in pairs])) if pairs else None,
        "mean_treatment": float(np.mean([t for _, t in pairs])) if pairs else None,
        "sign_test_p": float(sps.binomtest(better, better + worse).pvalue)
        if better + worse else None,
        "non_inferiority": None,
    }
    if margin is not None and pairs:
        diffs = np.array([t - b for b, t in pairs])
        boots = rng.choice(diffs, size=(BOOTSTRAP_RESAMPLES, len(diffs)), replace=True).mean(axis=1)
        lower = float(np.percentile(boots, 5))
        out["non_inferiority"] = {"margin": margin, "mean_diff": float(diffs.mean()),
                                  "one_sided_95_lower": lower, "passed": lower > -margin}
    return out


def claim_status(manifest: dict, audit_passed: bool, partial: bool = False) -> list[str]:
    reasons = []
    if partial:
        reasons.append("run was stopped before its plan finished")
    if manifest["stage"] != "full":
        reasons.append(f"stage is {manifest['stage']!r}, not 'full'")
    if not manifest.get("preregistered"):
        reasons.append("run was started from an uncommitted tree")
    if not audit_passed:
        reasons.append("audit did not pass")
    return reasons


def compute_stats(manifest: dict, trials: list[dict], audit_passed: bool,
                  partial: bool = False) -> dict:
    if not audit_passed:
        raise StatsError("audit failed; fix the run before computing stats")
    rng = np.random.default_rng(manifest["seed"])
    tasks, dropped = paired_tasks(trials)
    endpoints = manifest.get("endpoints") or {}
    named = [*endpoints.get("primary", []), *endpoints.get("secondary", [])]
    unknown = sorted(set(named) - set(METRICS))
    if unknown:
        raise StatsError(f"experiment names unknown endpoints {unknown}; known: {METRICS}")
    quality = manifest.get("quality") or {}
    results = {}
    for metric in METRICS:
        if metric == "reward":
            results[metric] = reward_summary(tasks, quality.get("non_inferiority_margin"), rng)
        else:
            results[metric] = ratio_summary(tasks, metric, rng)
        results[metric]["role"] = ("primary" if metric in endpoints.get("primary", [])
                                   else "secondary" if metric in named else "exploratory")
    reasons = claim_status(manifest, audit_passed, partial)
    return {
        "experiment": manifest["experiment"],
        "stage": manifest["stage"],
        "claim": not reasons,
        "not_a_claim_because": reasons,
        "n_tasks": len(tasks),
        "dropped_pairs": dropped,
        "endpoints": results,
    }
