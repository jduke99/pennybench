import json
import math

import numpy as np
import pytest

from pennybench.metrics import (MetricsError, call_cost, code_lines, heredoc_file_lines,
                                rate_table, tool_use_lines)
from pennybench.stats import StatsError, compute_stats, paired_tasks
from pennybench.wire import ModelCall, response_tool_uses


def call(model="claude-sonnet-5-5", **usage):
    return ModelCall(seq=1, host="h", path="/v1/messages", status=200,
                     requested_model=model, responded_model=model, usage=usage)


# Cost

def test_cost_uses_pinned_rates_and_splits_write_tiers():
    inp, rd, w5, w1, out = rate_table()["models"]["claude-sonnet-5-5"]["rates"]
    c = call(input_tokens=10, cache_read_input_tokens=1000, cache_creation_input_tokens=300,
             ephemeral_1h_input_tokens=100, output_tokens=50)
    assert call_cost(c) == pytest.approx(10 * inp + 1000 * rd + 200 * w5 + 100 * w1 + 50 * out)


def test_cost_switches_to_long_context_rates_above_threshold():
    entry = rate_table()["models"]["claude-haiku-5-5"]
    over = entry["above"]["threshold"] + 1
    assert call_cost(call("claude-haiku-5-5", cache_read_input_tokens=over)) == pytest.approx(
        over * entry["above"]["rates"][1])


def test_unknown_model_is_an_error_not_zero():
    with pytest.raises(MetricsError, match="no pinned rate"):
        call_cost(call("claude-imaginary-9", input_tokens=1))


# Lines of code

def test_code_lines_skip_blank_and_comment_lines():
    assert code_lines("# header\n\nimport os\n  // c\nx = 1\n") == 2


def test_heredoc_to_file_counts_but_heredoc_to_interpreter_does_not():
    to_file = "cat > /app/a.py <<'EOF'\nimport sys\nprint(1)\nEOF\n"
    to_python = "python3 - <<'EOF'\nimport sys\nprint(1)\nEOF\n"
    via_tee = "tee /app/b.sh <<EOF\necho hi\nEOF"
    assert heredoc_file_lines(to_file) == 2
    assert heredoc_file_lines(to_python) == 0
    assert heredoc_file_lines(via_tee) == 1


def test_tool_use_lines_by_tool():
    assert tool_use_lines({"name": "Write", "input": {"content": "a\nb\n"}}) == 2
    assert tool_use_lines({"name": "Edit", "input": {"old_string": "x", "new_string": "y\nz"}}) == 2
    assert tool_use_lines({"name": "MultiEdit",
                           "input": {"edits": [{"new_string": "a"}, {"new_string": "b\nc"}]}}) == 3
    assert tool_use_lines({"name": "Read", "input": {"file_path": "/x"}}) == 0


def test_streamed_tool_input_is_reassembled():
    events = [
        {"type": "content_block_start", "index": 1,
         "content_block": {"type": "tool_use", "name": "Write", "input": {}}},
        {"type": "content_block_delta", "index": 1,
         "delta": {"type": "input_json_delta", "partial_json": '{"content": "a\\n'}},
        {"type": "content_block_delta", "index": 1,
         "delta": {"type": "input_json_delta", "partial_json": 'b"}'}},
    ]
    sse = "\n".join(f"data: {json.dumps(e)}" for e in events)
    assert response_tool_uses(sse) == [{"name": "Write", "input": {"content": "a\nb"}}]


# Stats

MANIFEST = {"experiment": "x", "stage": "full", "preregistered": True, "seed": 1,
            "endpoints": {"primary": ["cost"], "secondary": ["reward"]}, "quality": {}}


def trial(task, role, rep=0, status="complete", **metrics):
    base = {m: 1.0 for m in ("cost", "total_tokens", "output_tokens", "fresh_input_tokens",
                              "cache_read_tokens", "cache_write_tokens", "loc_written",
                              "turns", "wall_clock")}
    return {"task": task, "rep": rep, "role": role, "status": status,
            "metrics": {**base, "reward": 1.0, **metrics}}


def synthetic(effect: float, n=60, seed=0):
    rng = np.random.default_rng(seed)
    trials = []
    for i in range(n):
        b = float(rng.lognormal(0, 1.0))
        t = b * effect * float(rng.lognormal(0, 0.15))
        trials += [trial(f"t{i}", "baseline", cost=b), trial(f"t{i}", "treatment", cost=t)]
    return trials


def test_recovers_a_real_twenty_percent_saving():
    s = compute_stats(MANIFEST, synthetic(0.8), True)["endpoints"]["cost"]
    assert s["wilcoxon_p"] < 0.001
    lo, hi = s["ci95_median_pct"]
    assert lo < -20 < hi
    assert -25 < s["hodges_lehmann_pct"] < -15


def test_null_effect_is_not_significant():
    s = compute_stats(MANIFEST, synthetic(1.0, seed=3), True)["endpoints"]["cost"]
    assert s["wilcoxon_p"] > 0.05
    lo, hi = s["ci95_median_pct"]
    assert lo < 0 < hi


def test_heavy_outlier_moves_total_but_not_median():
    trials = synthetic(0.8, n=20)
    trials += [trial("whale", "baseline", cost=1.0), trial("whale", "treatment", cost=1000.0)]
    s = compute_stats(MANIFEST, trials, True)["endpoints"]["cost"]
    assert s["total_pct"] > 100
    assert s["median_pct"] < -10


def test_pair_with_an_error_in_either_arm_is_dropped_from_both():
    trials = [trial("a", "baseline"), trial("a", "treatment", status="agent_error"),
              trial("b", "baseline"), trial("b", "treatment")]
    tasks, dropped = paired_tasks(trials)
    assert list(tasks) == ["b"]
    assert dropped == [{"task": "a", "rep": 0, "baseline": "complete", "treatment": "agent_error"}]


def test_reps_are_reduced_to_a_per_task_median():
    trials = [trial("a", "baseline", rep=r, cost=c) for r, c in enumerate([1, 2, 9])]
    trials += [trial("a", "treatment", rep=r, cost=c) for r, c in enumerate([1, 1, 1])]
    tasks, _ = paired_tasks(trials)
    assert tasks["a"]["baseline"]["cost"] == 2


def test_zero_in_one_arm_is_excluded_from_ratios_but_kept_in_totals():
    trials = [trial("a", "baseline", loc_written=0), trial("a", "treatment", loc_written=50),
              trial("b", "baseline", loc_written=0), trial("b", "treatment", loc_written=0),
              trial("c", "baseline", loc_written=10), trial("c", "treatment", loc_written=5)]
    s = compute_stats(MANIFEST, trials, True)["endpoints"]["loc_written"]
    assert s["excluded_zero_in_one_arm"] == ["a"]
    assert s["n_tasks"] == 2
    assert s["total_baseline"] == 10 and s["total_treatment"] == 55


def test_reward_sign_test_counts():
    trials = []
    for i, (b, t) in enumerate([(1, 0), (1, 0), (0, 1), (1, 1), (0.5, 0.5)]):
        trials += [trial(f"t{i}", "baseline", reward=b), trial(f"t{i}", "treatment", reward=t)]
    r = compute_stats(MANIFEST, trials, True)["endpoints"]["reward"]
    assert (r["treatment_better"], r["treatment_worse"], r["equal"]) == (1, 2, 2)
    assert r["sign_test_p"] == pytest.approx(1.0)
    assert r["non_inferiority"] is None


def test_non_inferiority_needs_the_bound_above_minus_margin():
    trials = []
    for i in range(200):
        trials += [trial(f"t{i}", "baseline", reward=1.0), trial(f"t{i}", "treatment", reward=1.0)]
    manifest = {**MANIFEST, "quality": {"non_inferiority_margin": 0.05}}
    ni = compute_stats(manifest, trials, True)["endpoints"]["reward"]["non_inferiority"]
    assert ni["passed"]


def test_stats_refuse_a_failed_audit():
    with pytest.raises(StatsError, match="audit"):
        compute_stats(MANIFEST, synthetic(0.8), False)


def test_smoke_or_dirty_runs_are_labeled_not_a_claim():
    out = compute_stats({**MANIFEST, "stage": "smoke", "preregistered": False}, synthetic(0.8), True)
    assert not out["claim"]
    assert len(out["not_a_claim_because"]) == 2


def test_mde_shrinks_with_more_tasks():
    small = compute_stats(MANIFEST, synthetic(1.0, n=10), True)["endpoints"]["cost"]["mde_pct"]
    large = compute_stats(MANIFEST, synthetic(1.0, n=160), True)["endpoints"]["cost"]["mde_pct"]
    assert large < small
    assert math.isfinite(large)
