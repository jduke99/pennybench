"""Trial plan: which task runs under which arm, in what order."""

from __future__ import annotations

import random
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
    """Pairs in a seeded random order; within pairs, arm order alternates (ABBA) so drift,
    throttling, and cache warmth fall evenly on both arms. The two trials of a pair run
    back to back. A single-arm experiment has one trial per (task, rep)."""
    pairs = [(task.name, rep) for rep in range(experiment.k) for task in experiment.task_dirs()]
    random.Random(experiment.seed).shuffle(pairs)
    trials = []
    for pair, (task, rep) in enumerate(pairs):
        roles = experiment.roles if pair % 2 == 0 else experiment.roles[::-1]
        trials.extend(
            PlannedTrial(pair=pair, position=pos, task=task, rep=rep, role=role)
            for pos, role in enumerate(roles)
        )
    return trials
