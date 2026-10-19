"""Public setup and suite packaging checks: no Docker, model calls or credentials."""
import importlib.util
import json
from pathlib import Path
import re
import sys
import tomllib

import pytest
import yaml

from pennybench.agent_env import build_trial_env
from pennybench.config import load_local_config
from pennybench.digest import tree_sha256
from pennybench.spec import load_arm

ROOT = Path(__file__).resolve().parents[1]


def test_public_config_targets_hosted_gateway_without_capture_or_personal_credentials():
    config = load_local_config(ROOT / "config.example.toml")
    endpoint = config.endpoint("proxy")
    assert endpoint.base_url == "https://api.pennyrouter.com"
    assert endpoint.key_env is None
    assert endpoint.egress_capture_port is None
    arm = load_arm(ROOT / "arms/cc-sonnet-proxy-login.yaml")
    env = build_trial_env(arm, config, {})
    assert env.agent_env["ANTHROPIC_BASE_URL"] == "https://api.pennyrouter.com"
    assert env.secrets == ()


@pytest.mark.parametrize("name", ["proxy-smoke", "proxy-smoke-k3", "proxy-full"])
def test_skillsbench_suite_copies_preserve_registered_experiment_bytes(name):
    legacy = ROOT / f"experiments/{name}.yaml"
    public = ROOT / f"benchmarks/skillsbench/experiments/{name}.yaml"
    assert public.read_bytes() == legacy.read_bytes()
    source = tomllib.loads((ROOT / "benchmarks/skillsbench/source.toml").read_text())
    experiment = yaml.safe_load(public.read_text())
    assert experiment["tasks"] == {
        "dataset": source["dataset"], "sha256": source["task_tree_sha256"]}


def test_shared_wiring_fixture_preserves_existing_paths():
    assert (ROOT / "benchmarks/smoke-login.yaml").read_bytes() == (
        ROOT / "experiments/smoke-login.yaml").read_bytes()


def test_pricing_table_is_declared_as_package_data():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "rates.json" in project["tool"]["setuptools"]["package-data"]["pennybench"]
    assert json.loads((ROOT / "pennybench/rates.json").read_text())["models"]


def test_public_documentation_relative_links_resolve():
    paths = ["README.md", "RUNNER.md", "CONTRIBUTING.md", "SECURITY.md",
             "docs/CREDENTIALS.md", "docs/PUBLICATION.md", "benchmarks/README.md",
             "benchmarks/skillsbench/README.md", "benchmarks/skillsbench/results/README.md",
             "benchmarks/terminal-bench/HOW_TO_RUN.md"]
    for name in paths:
        path = ROOT / name
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if target.startswith(("https://", "http://", "#", "mailto:")):
                continue
            assert (path.parent / target.split("#", 1)[0]).exists(), (name, target)


def _prepare_module():
    spec = importlib.util.spec_from_file_location(
        "skillsbench_prepare", ROOT / "benchmarks/skillsbench/prepare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skillsbench_verify_only_does_not_download(tmp_path, monkeypatch, capsys):
    module = _prepare_module()
    suite = tmp_path / "benchmarks/skillsbench"
    suite.mkdir(parents=True)
    tasks = tmp_path / "runs/.datasets/benchflow__skillsbench@v1.1"
    task = tasks / "example"
    task.mkdir(parents=True)
    (task / "task.toml").write_text('schema_version = "1.4"\n')
    digest = tree_sha256(tasks)
    (suite / "source.toml").write_text(
        'dataset = "benchflow/skillsbench@v1.1"\n'
        f'task_tree_sha256 = "{digest}"\ntask_count = 1\n')
    (tmp_path / "pennybench.local.toml").write_text('[artifacts]\nstore = "runs"\n')
    monkeypatch.setattr(module, "__file__", str(suite / "prepare.py"))
    monkeypatch.setattr(sys, "argv", ["prepare.py", "--verify-only"])
    monkeypatch.setattr(module, "ensure_dataset", lambda *a: pytest.fail("Unexpected download"))
    module.main()
    assert "Verified benchflow/skillsbench@v1.1: 1 tasks" in capsys.readouterr().out


def test_skillsbench_verify_only_rejects_missing_download(tmp_path, monkeypatch):
    module = _prepare_module()
    suite = tmp_path / "benchmarks/skillsbench"
    suite.mkdir(parents=True)
    (suite / "source.toml").write_text(
        'dataset = "benchflow/skillsbench@v1.1"\ntask_tree_sha256 = "unused"\ntask_count = 87\n')
    (tmp_path / "pennybench.local.toml").write_text('[artifacts]\nstore = "runs"\n')
    monkeypatch.setattr(module, "__file__", str(suite / "prepare.py"))
    monkeypatch.setattr(sys, "argv", ["prepare.py", "--verify-only"])
    monkeypatch.setattr(module, "ensure_dataset", lambda *a: pytest.fail("Unexpected download"))
    with pytest.raises(SystemExit, match="Pinned source is missing"):
        module.main()


def test_skillsbench_export_scrubs_private_values():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "benchmarks/skillsbench/export_results.py"
    spec = importlib.util.spec_from_file_location("export_results", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = "/Users/someone/x a@b.edu Bearer abc sk-ant-oat01-zzz benchflow/skillsbench@v1.1"
    out = module.scrub(text)
    assert "someone" not in out and "a@b.edu" not in out and "abc" not in out
    assert "zzz" not in out and "benchflow/skillsbench@v1.1" in out
