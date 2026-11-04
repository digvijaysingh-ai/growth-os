"""The person-vs-grader agreement on the team's held-out checks: counts, direction of each disagreement, and Cohen's kappa."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
import human_grading as H  # noqa: E402


def test_team_agreement(tmp_path, monkeypatch):
    run = {"runs": [{"seed": 1, "grades": [{"criterion": c, "pass": p} for c, p in (("a", True), ("b", False), ("c", True), ("d", False))]}]}
    (tmp_path / "run.json").write_text(json.dumps(run))
    (tmp_path / "team-heldout-grades.json").write_text(json.dumps({"source": "run.json", "grades": {"1:a": True, "1:b": True, "1:c": False, "1:d": False}}))
    monkeypatch.setattr(H, "OUT", tmp_path)
    monkeypatch.setattr(H, "ROOT", tmp_path)
    out = H.team()
    assert (out["agree"], out["human_pass"], out["ai_pass"]) == (2, 2, 2)
    assert out["ai_stricter"] == ["1:b"] and out["ai_more_lenient"] == ["1:c"]
    assert out["kappa"] == 0.0  # 50% agreement when chance alone gives 50%
