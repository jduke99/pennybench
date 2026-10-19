"""Reports for a single-arm run: what one arm did, task by task. There is nothing to pair, so
no test and no claim; an optional reference (another run's baseline arm) is shown beside it
for orientation only."""

from __future__ import annotations

from statistics import mean

SHOWN = ("cost", "cache_write_tokens", "output_tokens", "turns")


def _by_task(trials: list[dict], role: str | None) -> dict[str, list[dict]]:
    tasks: dict[str, list[dict]] = {}
    for t in trials:
        if t["status"] == "complete" and (role is None or t["role"] == role):
            tasks.setdefault(t["task"], []).append(t["metrics"])
    return tasks


def _row(runs: list[dict]) -> dict:
    return {
        "n": len(runs),
        "rewards": [r["reward"] for r in runs],
        "mean_reward": mean(r["reward"] for r in runs if r["reward"] is not None) if any(
            r["reward"] is not None for r in runs) else None,
        **{f"mean_{k}": mean(r[k] for r in runs if r[k] is not None) for k in SHOWN
           if any(r[k] is not None for r in runs)},
    }


def solo_summary(trials: list[dict], reference: list[dict] | None = None,
                 reference_role: str = "baseline") -> dict:
    ours = _by_task(trials, None)
    ref = _by_task(reference, reference_role) if reference is not None else {}
    not_complete: dict[str, int] = {}
    for t in trials:
        if t["status"] != "complete":
            not_complete[t["status"]] = not_complete.get(t["status"], 0) + 1
    tasks = {name: {**_row(runs), "reference": _row(ref[name]) if name in ref else None}
             for name, runs in sorted(ours.items())}
    rewards = [r for row in tasks.values() for r in row["rewards"] if r is not None]
    return {
        "n_trials": sum(row["n"] for row in tasks.values()),
        "not_complete": not_complete,
        "mean_reward": mean(rewards) if rewards else None,
        "pass_rate": sum(r >= 1 for r in rewards) / len(rewards) if rewards else None,
        "tasks": tasks,
        "reference_role": reference_role if reference is not None else None,
    }


def format_solo(summary: dict, experiment: str, stage: str, arm: str) -> str:
    lines = [f"{experiment}  stage={stage}  arm={arm}  trials={summary['n_trials']}",
             "status: NOT A CLAIM — a single arm run alone has nothing to compare against"]
    if summary["not_complete"]:
        lines.append(f"trials not complete: {summary['not_complete']}")
    has_ref = summary["reference_role"] is not None
    head = f"{'task':<36}{'n':>3}{'rewards':>14}{'cost':>9}{'c-write':>9}{'turns':>7}"
    if has_ref:
        head += f"  | reference: {'reward':>7}{'cost':>9}{'c-write':>9}"
    lines += ["", head]
    for name, row in summary["tasks"].items():
        rewards = " ".join(f"{r:g}" if r is not None else "-" for r in row["rewards"])
        line = (f"{name[:35]:<36}{row['n']:>3}{rewards:>14}{row.get('mean_cost', 0):>9.3f}"
                f"{row.get('mean_cache_write_tokens', 0) / 1000:>8.1f}k{row.get('mean_turns', 0):>7.1f}")
        ref = row["reference"]
        if has_ref:
            line += ("  |            " + (f"{ref['mean_reward']:>7.2f}{ref['mean_cost']:>9.3f}"
                                            f"{ref.get('mean_cache_write_tokens', 0) / 1000:>8.1f}k"
                                            if ref else "      -        -        -"))
        lines.append(line)
    if summary["mean_reward"] is not None:
        lines += ["", f"mean reward {summary['mean_reward']:.3f}; passed "
                      f"{summary['pass_rate']:.0%} of trials"]
    if has_ref:
        both = [(r["mean_reward"], r["reference"]["mean_reward"]) for r in summary["tasks"].values()
                if r["reference"] and r["mean_reward"] is not None]
        if both:
            lines.append(f"on the {len(both)} tasks with a reference: this arm {mean(a for a, _ in both):.3f}, "
                         f"reference ({summary['reference_role']}) {mean(b for _, b in both):.3f}")
    return "\n".join(lines)
