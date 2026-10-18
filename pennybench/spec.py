"""Arm and experiment specs, and the one-variable check between two arms."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

HARNESSES = ("claude-code",)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
STAGES = ("audit", "smoke", "smoke-k3", "full")
INJECT_KEYS = ("append_system_prompt_file", "settings_file")

# Fields that may legitimately differ between arms without being the experiment's variable.
_IDENTITY_FIELDS = ("id", "adoption_marker")


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
            "inject": {k: file_sha256(base_dir / v) for k, v in sorted(self.inject.items())},
        }


@dataclass(frozen=True)
class Exclusion:
    task: str
    reason: str


@dataclass(frozen=True)
class Experiment:
    id: str
    baseline: Arm
    treatment: Arm
    variable: str
    tasks: Path
    exclude: tuple[Exclusion, ...]
    stage: str
    k: int
    seed: int
    endpoints: dict[str, list[str]]
    quality: dict[str, Any]
    source: Path
    root: Path

    def task_dirs(self) -> list[Path]:
        """Harbor task directories in the task set, minus exclusions, in name order."""
        if (self.tasks / "task.toml").exists():
            found = [self.tasks]
        else:
            found = sorted(p.parent for p in self.tasks.glob("*/task.toml"))
        if not found:
            raise SpecError(f"no Harbor tasks under {self.tasks}")
        excluded = {e.task for e in self.exclude}
        unknown = excluded - {p.name for p in found}
        if unknown:
            raise SpecError(f"exclusions name unknown tasks: {sorted(unknown)}")
        return [p for p in found if p.name not in excluded]


def file_sha256(path: Path) -> str:
    if not path.is_file():
        raise SpecError(f"injected file not found: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def load_experiment(path: Path, root: Path, extra_arm_dirs: list[Path] = ()) -> Experiment:
    raw = yaml.safe_load(path.read_text()) or {}
    arm_ids = _require(raw, "arms", path)
    if not isinstance(arm_ids, list) or len(arm_ids) != 2:
        raise SpecError(f"{path}: arms must list exactly [baseline, treatment]")
    arm_dirs = [root / "arms", *extra_arm_dirs]
    baseline, treatment = (find_arm(a, arm_dirs) for a in arm_ids)

    variable = _require(raw, "variable", path)
    check_one_variable(baseline, treatment, variable, root)

    stage = _require(raw, "stage", path)
    if stage not in STAGES:
        raise SpecError(f"{path}: stage must be one of {STAGES}")
    k = int(raw.get("k", 1))
    if k < 1:
        raise SpecError(f"{path}: k must be at least 1")

    exclude = []
    for item in raw.get("exclude") or []:
        if not isinstance(item, dict) or not item.get("task") or not item.get("reason"):
            raise SpecError(f"{path}: every exclusion needs a task and a reason")
        exclude.append(Exclusion(task=item["task"], reason=item["reason"]))

    experiment = Experiment(
        id=_require(raw, "id", path),
        baseline=baseline,
        treatment=treatment,
        variable=variable,
        tasks=root / _require(raw, "tasks", path),
        exclude=tuple(exclude),
        stage=stage,
        k=k,
        seed=int(_require(raw, "seed", path)),
        endpoints=raw.get("endpoints") or {},
        quality=raw.get("quality") or {},
        source=path,
        root=root,
    )
    if experiment.id != path.stem:
        raise SpecError(f"{path}: id {experiment.id!r} must match the file name")
    experiment.task_dirs()
    return experiment
