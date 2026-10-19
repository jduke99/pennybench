"""Arm and experiment specs, and the one-variable check between two arms."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pennybench.datasets import ensure_dataset
from pennybench.digest import content_sha256
from pennybench.metrics import METRICS

HARNESSES = ("claude-code",)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
STAGES = ("audit", "smoke", "smoke-k3", "full")
TASK_SKILLS = ("with", "without")
# trial: append a line unique to the run and trial to every task instruction, so no trial can
# read prompt cache left by an identical request in an earlier run or another rep.
CACHE_ISOLATION = ("none", "trial")
# append_system_prompt_file: text appended to Claude Code's system prompt.
# instruction_append_file: text appended after the task instruction, separated by a blank line.
# settings_file: a Claude Code settings JSON layer.
# skills_dir: one skill directory installed for the agent.
INJECT_KEYS = ("append_system_prompt_file", "instruction_append_file", "settings_file",
               "skills_dir")


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class Arm:
    id: str
    harness: str
    harness_version: str
    model: str
    effort: str | None
    auth: str
    route: str
    inject: dict[str, str] = field(default_factory=dict)
    adoption_marker: str | None = None
    source: Path | None = None

    @property
    def endpoint_name(self) -> str | None:
        return self.route.removeprefix("endpoint:") if self.route != "native" else None

    def comparable(self, base_dir: Path) -> dict[str, Any]:
        """Every field that must match across arms, with injected files reduced to hashes."""
        return {
            "harness": self.harness,
            "harness_version": self.harness_version,
            "model": self.model,
            "effort": self.effort,
            "auth": self.auth,
            "route": self.route,
            "inject": {k: injected_sha256(base_dir / v) for k, v in sorted(self.inject.items())},
        }


@dataclass(frozen=True)
class Exclusion:
    task: str
    reason: str


@dataclass(frozen=True)
class Experiment:
    id: str
    # Arms by role: "baseline" and "treatment" for a paired experiment, or one "solo" arm.
    arms: dict[str, Arm]
    variable: str | None
    tasks: Path
    tasks_source: dict[str, str]
    include: tuple[str, ...]
    task_skills: str
    cache_isolation: str
    sample: int | None
    exclude: tuple[Exclusion, ...]
    stage: str
    k: int
    seed: int
    endpoints: dict[str, list[str]]
    quality: dict[str, Any]
    source: Path
    root: Path

    @property
    def paired(self) -> bool:
        return len(self.arms) == 2

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(self.arms)

    @property
    def baseline(self) -> Arm | None:
        return self.arms.get("baseline")

    @property
    def treatment(self) -> Arm | None:
        return self.arms.get("treatment")

    def task_dirs(self) -> list[Path]:
        """Harbor task directories in the task set, minus exclusions, in name order."""
        if (self.tasks / "task.toml").exists():
            found = [self.tasks]
        else:
            found = sorted(p.parent for p in self.tasks.glob("*/task.toml"))
        if not found:
            raise SpecError(f"no Harbor tasks under {self.tasks}")
        excluded = {e.task for e in self.exclude}
        unknown = (excluded | set(self.include)) - {p.name for p in found}
        if unknown:
            raise SpecError(f"exclusions or includes name unknown tasks: {sorted(unknown)}")
        kept = [p for p in found if p.name not in excluded
                and (not self.include or p.name in self.include)]
        if self.sample is None:
            return kept
        if self.sample > len(kept):
            raise SpecError(f"sample {self.sample} exceeds the {len(kept)} available tasks")
        # Depends only on the task set and seed, so stages sharing both share a sample.
        return sorted(random.Random(self.seed).sample(kept, self.sample))


def task_skill_dirs(task_dir: Path) -> list[Path]:
    """The task's own skills: each folder under environment/skills that holds a SKILL.md.
    Loose files beside them (READMEs, licenses) are not skills and are not installed."""
    root = task_dir / "environment" / "skills"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def injected_sha256(path: Path) -> str:
    if not path.exists():
        raise SpecError(f"injected path not found: {path}")
    return content_sha256(path)


def _require(raw: dict, key: str, where: Path) -> Any:
    if key not in raw or raw[key] in (None, ""):
        raise SpecError(f"{where}: missing required field {key!r}")
    return raw[key]


def load_arm(path: Path) -> Arm:
    raw = yaml.safe_load(path.read_text()) or {}
    harness = _require(raw, "harness", path)
    if harness not in HARNESSES:
        raise SpecError(f"{path}: harness must be one of {HARNESSES}")
    effort = raw.get("effort")
    if effort is not None and effort not in EFFORTS:
        raise SpecError(f"{path}: effort must be one of {EFFORTS} or null")
    route = _require(raw, "route", path)
    if route != "native" and not route.startswith("endpoint:"):
        raise SpecError(f"{path}: route must be 'native' or 'endpoint:<name>'")
    inject = raw.get("inject") or {}
    unknown = set(inject) - set(INJECT_KEYS)
    if unknown:
        raise SpecError(f"{path}: unknown inject keys {sorted(unknown)}; allowed {INJECT_KEYS}")
    arm = Arm(
        id=_require(raw, "id", path),
        harness=harness,
        harness_version=str(_require(raw, "harness_version", path)),
        model=_require(raw, "model", path),
        effort=effort,
        auth=_require(raw, "auth", path),
        route=route,
        inject={k: str(v) for k, v in inject.items()},
        adoption_marker=raw.get("adoption_marker"),
        source=path,
    )
    if arm.id != path.stem:
        raise SpecError(f"{path}: id {arm.id!r} must match the file name")
    return arm


def find_arm(arm_id: str, arm_dirs: list[Path]) -> Arm:
    matches = [d / f"{arm_id}.yaml" for d in arm_dirs if (d / f"{arm_id}.yaml").exists()]
    if not matches:
        raise SpecError(f"arm {arm_id!r} not found in {[str(d) for d in arm_dirs]}")
    if len(matches) > 1:
        raise SpecError(f"arm {arm_id!r} is defined more than once: {matches}")
    return load_arm(matches[0])


def arm_differences(a: Arm, b: Arm, base_dir: Path) -> set[str]:
    ca, cb = a.comparable(base_dir), b.comparable(base_dir)
    return {k for k in ca if ca[k] != cb[k]}


def check_one_variable(baseline: Arm, treatment: Arm, variable: str, base_dir: Path) -> None:
    allowed = set(baseline.comparable(base_dir))
    if variable not in allowed:
        raise SpecError(f"variable must be one of {sorted(allowed)}")
    diff = arm_differences(baseline, treatment, base_dir)
    if variable not in diff:
        raise SpecError(f"arms do not differ in the declared variable {variable!r}")
    extra = diff - {variable}
    if extra:
        raise SpecError(
            f"arms differ in {sorted(extra)} besides the declared variable {variable!r}"
        )


def resolve_tasks(raw_tasks: Any, root: Path, dataset_store: Path | None,
                  where: Path) -> tuple[Path, dict[str, str]]:
    """`tasks` is a repo-relative path, or {dataset: org/name@ref, sha256: <tree hash>}."""
    if isinstance(raw_tasks, str):
        return root / raw_tasks, {"path": raw_tasks}
    if isinstance(raw_tasks, dict) and raw_tasks.get("dataset") and raw_tasks.get("sha256"):
        if dataset_store is None:
            raise SpecError(f"{where}: a dataset task set needs the artifact store")
        source = {"dataset": raw_tasks["dataset"], "sha256": raw_tasks["sha256"]}
        return ensure_dataset(source["dataset"], source["sha256"], dataset_store), source
    raise SpecError(f"{where}: tasks must be a path or {{dataset, sha256}}")


def load_experiment(path: Path, root: Path, extra_arm_dirs: list[Path] = (),
                    dataset_store: Path | None = None) -> Experiment:
    raw = yaml.safe_load(path.read_text()) or {}
    arm_ids = _require(raw, "arms", path)
    if not isinstance(arm_ids, list) or len(arm_ids) not in (1, 2):
        raise SpecError(f"{path}: arms must list [baseline, treatment], or one arm to run alone")
    arm_dirs = [root / "arms", *extra_arm_dirs]
    found = [find_arm(a, arm_dirs) for a in arm_ids]
    if len(found) == 2:
        arms = {"baseline": found[0], "treatment": found[1]}
        variable = _require(raw, "variable", path)
        check_one_variable(found[0], found[1], variable, root)
    else:
        # One arm run alone, for debugging and investigation: no pairing, no comparison.
        if raw.get("variable"):
            raise SpecError(f"{path}: a single-arm experiment compares nothing, so it has no variable")
        arms, variable = {"solo": found[0]}, None

    stage = _require(raw, "stage", path)
    if stage not in STAGES:
        raise SpecError(f"{path}: stage must be one of {STAGES}")
    k = int(raw.get("k", 1))
    if k < 1:
        raise SpecError(f"{path}: k must be at least 1")

    tasks, tasks_source = resolve_tasks(_require(raw, "tasks", path), root, dataset_store, path)
    task_skills = _require(raw, "task_skills", path)
    if task_skills not in TASK_SKILLS:
        raise SpecError(f"{path}: task_skills must be one of {TASK_SKILLS}")
    cache_isolation = raw.get("cache_isolation", "none")
    if cache_isolation not in CACHE_ISOLATION:
        raise SpecError(f"{path}: cache_isolation must be one of {CACHE_ISOLATION}")
    sample = raw.get("sample")
    if sample is not None and int(sample) < 1:
        raise SpecError(f"{path}: sample must be a positive number of tasks")
    sample = int(sample) if sample is not None else None

    endpoints = raw.get("endpoints") or {}
    named = [m for group in endpoints.values() for m in group]
    unknown = sorted(set(named) - set(METRICS))
    if unknown:
        raise SpecError(f"{path}: unknown endpoints {unknown}; known: {list(METRICS)}")

    exclude = []
    for item in raw.get("exclude") or []:
        if not isinstance(item, dict) or not item.get("task") or not item.get("reason"):
            raise SpecError(f"{path}: every exclusion needs a task and a reason")
        exclude.append(Exclusion(task=item["task"], reason=item["reason"]))

    experiment = Experiment(
        id=_require(raw, "id", path),
        arms=arms,
        variable=variable,
        tasks=tasks,
        tasks_source=tasks_source,
        include=tuple(raw.get("include") or ()),
        task_skills=task_skills,
        cache_isolation=cache_isolation,
        sample=sample,
        exclude=tuple(exclude),
        stage=stage,
        k=k,
        seed=int(_require(raw, "seed", path)),
        endpoints=endpoints,
        quality=raw.get("quality") or {},
        source=path,
        root=root,
    )
    if experiment.id != path.stem:
        raise SpecError(f"{path}: id {experiment.id!r} must match the file name")
    experiment.task_dirs()
    return experiment
