from pennybench.artifacts import trial_records


def test_attempt_text_inside_a_task_name_is_not_an_archive(tmp_path):
    name = "0000-fix.attempt-1-r0-baseline"
    for directory in [name, name + ".attempt-123"]:
        path = tmp_path / "trials" / directory / "trial.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}")
    assert [p.parent.name for p in trial_records(tmp_path)] == [name]
