"""Outcomes runs work in private scratch directories: nothing is left in state/sim after an error, two runs never share
files, a short disk fails early, and a failed leave-one-out run writes a log but never a report (GOS-104/105/107)."""
import json
from collections import namedtuple
from datetime import date

import pytest

from growth_os.enterprise import outcomes, policy
from growth_os.enterprise.world import Policy


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(outcomes, "ROOT", tmp_path)
    monkeypatch.setattr(policy, "ROOT", tmp_path)
    (tmp_path / "reports").mkdir()
    hub = tmp_path / "hub.sqlite"
    hub.write_bytes(b"x" * 1000)
    return tmp_path, hub


def test_scratch_is_removed_after_an_error(root):
    tmp, hub = root
    with pytest.raises(RuntimeError):
        with outcomes._scratch(None, hub) as d:
            (d / "work.sqlite").write_text("partial")
            raise RuntimeError("simulation broke")
    assert list((tmp / "state" / "sim").iterdir()) == []  # no run directory, no lock


def test_a_second_run_is_refused_while_one_holds_the_lock(root):
    _, hub = root
    with outcomes._scratch(None, hub):
        with pytest.raises(outcomes.Failed) as e:
            with outcomes._scratch(None, hub):
                pass
    assert e.value.code == "GOS-107"


def test_short_disk_fails_before_any_work(root, monkeypatch):
    _, hub = root
    monkeypatch.setattr(outcomes.shutil, "disk_usage", lambda p: namedtuple("U", "total used free")(0, 0, 10))
    with pytest.raises(outcomes.Failed) as e:
        with outcomes._scratch(None, hub):
            pass
    assert e.value.code == "GOS-105" and "GB needed" in str(e.value)


def test_impact_without_a_run_directory_caches_nothing(root, monkeypatch):
    tmp, _ = root

    def broken_build(path, *a, **k):
        path.write_text("half-built")
        raise RuntimeError("build failed")
    monkeypatch.setattr(policy, "build", broken_build)
    with pytest.raises(RuntimeError):
        policy.impact(Policy(), seed=7, days=7, until=date(2026, 11, 1))
    assert list((tmp / "state" / "sim").iterdir()) == []


def test_failed_leave_one_out_writes_a_log_and_no_report(root, monkeypatch, capsys):
    tmp, _ = root
    (tmp / "state").mkdir(exist_ok=True)
    (tmp / "state" / "enterprise-7.sqlite").write_bytes(b"x")
    for f in ("team-enterprise-7.json", "outcomes-enterprise-7.json"):
        (tmp / "reports" / f).write_text("{}")

    def boom(*a, **k):
        e = RuntimeError("scenario diverged")
        e.decision_id = 5
        raise e
    monkeypatch.setattr(outcomes, "leave_one_out", boom)
    assert outcomes.main(["--leave-one-out", "--seed", "7"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("GOS-104") and "--only 5" in err
    assert not (tmp / "reports" / "outcomes-loo-enterprise-7.json").exists()
    logs = list((tmp / "reports").glob("loo-failure-*.log"))
    assert len(logs) == 1 and "decision left out: 5" in logs[0].read_text()


def test_missing_inputs_are_gos_101(root, capsys):
    assert outcomes.main(["--leave-one-out", "--seed", "9"]) == 1
    assert capsys.readouterr().err.startswith("GOS-101")


def test_partial_run_merges_only_with_matching_inputs(tmp_path):
    full = {"inputs": {"priced_ids": [1, 2], "team_sha256": "a"}, "baseline_gross_profit": 10, "complete": True,
            "runs": [{"left_out": 1, "change": {"gross_profit": 1}}, {"left_out": 2, "change": {"gross_profit": 2}}]}
    path = tmp_path / "loo.json"
    path.write_text(json.dumps(full))
    same = {**full, "complete": False, "runs": [{"left_out": 2, "change": {"gross_profit": 9}}]}
    merged = outcomes._merge(path, same)
    assert merged["complete"] and [r["change"]["gross_profit"] for r in merged["runs"]] == [1, 9]
    other = {**same, "inputs": {"priced_ids": [1, 2], "team_sha256": "b"}}
    assert outcomes._merge(path, other)["complete"] is False
