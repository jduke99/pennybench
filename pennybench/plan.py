"""Trial plan: which task runs under which arm, in what order."""

from __future__ import annotations

import random
import tomllib
from dataclasses import asdict, dataclass

from pennybench.spec import Experiment


@dataclass(frozen=True)
class PlannedTrial:
    pair: int
    position: int
    task: str
    rep: int
    role: str

    @property
    def trial_id(self) -> str:
        return f"{self.pair:04d}-{self.task}-r{self.rep}-{self.role}"

    def to_json(self) -> dict:
        return {**asdict(self), "trial_id": self.trial_id}


def plan_trials(experiment: Experiment) -> list[PlannedTrial]:
    """Pairs in the declared task order; within pairs, arm order alternates (ABBA) so drift,
    throttling, and cache warmth fall evenly on both arms. The two trials of a pair run
    back to back. A single-arm experiment has one trial per (task, rep)."""
    tasks = experiment.task_dirs()
    pairs = [(task.name, rep) for rep in range(experiment.k) for task in tasks]
    random.Random(experiment.seed).shuffle(pairs)
    if experiment.task_order == "agent_timeout":
        limits = {}
        for task in tasks:
            spec = tomllib.loads((task / "task.toml").read_text())
            # A missing agent limit means unlimited; schedule those last.
            limits[task.name] = (spec.get("agent", {}).get("timeout_sec", float("inf")),
                                 spec.get("verifier", {}).get("timeout_sec", 600))
        # Stable sorting preserves the seeded shuffle for ties.
        pairs.sort(key=lambda pair: limits[pair[0]])
    trials = []
    for pair, (task, rep) in enumerate(pairs):
        roles = experiment.roles if pair % 2 == 0 else experiment.roles[::-1]
        trials.extend(
            PlannedTrial(pair=pair, position=pos, task=task, rep=rep, role=role)
            for pos, role in enumerate(roles)
        )
    return trials
