"""The console's decision deck: its build refuses missing, stale or unmapped inputs (GOS-101..103), decodes saved
agent text once, gates "beat the AI" on a measured, material gain, and renders from a snapshot without hubs."""
import hashlib
import json
from pathlib import Path

import pytest

from growth_os.console import build as B

ROOT = Path(__file__).resolve().parents[1]


def _g(x):
    return {"revenue": 2 * x, "spend": x / 10, "gross_profit": x}


def _reports(tmp: Path, loo_gain: float = 30_000, approver: str = "Growth manager"):
    """A three-decision team run, its outcomes report and a matching leave-one-out report."""
    team = tmp / "team.json"
    team.write_text(json.dumps({"decisions": {"recommendations": []}}))
    decisions = [
        {"id": 1, "rank": 1, "action": "Raise Paris budget by 15%", "type": "change_line_budget", "risk": "medium", "approver": approver,
         "simulated": True, "change": _g(900_000)},
        {"id": 2, "rank": 2, "action": "Bring London back to its \\u20ac360k budget (\\u221214%)", "type": "change_budget", "risk": "medium",
         "approver": "Leadership", "simulated": True, "change": _g(-20_000)},
        {"id": 3, "rank": 3, "action": "A/B test trust signals", "type": "launch_ab_test", "risk": "low", "approver": "Product / engineering owner",
         "simulated": False, "change": None},
    ]
    outcomes = tmp / "outcomes.json"
    outcomes.write_text(json.dumps({"decisions": decisions, "all_approved": {"as_is": {"revenue": 10e6, "spend": 1e6, "gross_profit": 4e6},
                                                                             "change": _g(1_000_000)}}))
    loo = tmp / "loo.json"
    loo.write_text(json.dumps({"inputs": {"team_sha256": hashlib.sha256(team.read_bytes()).hexdigest(),
                                          "outcomes_sha256": hashlib.sha256(outcomes.read_bytes()).hexdigest(), "priced_ids": [1, 2]},
                               "baseline_gross_profit": 4e6, "complete": True,
                               "runs": [{"left_out": 1, "change": _g(-30_000)}, {"left_out": 2, "change": _g(1_000_000 + loo_gain)}]}))
    return team, outcomes, loo


def test_deck_from_consistent_reports(tmp_path):
    d = B.deck_view(*_reports(tmp_path))
    assert d["priced"] == [1, 2] and d["beat_the_ai"] == [2] and not d["stale"]
    assert d["sum_singles"]["gross_profit"] == 880_000  # derived, never typed in
    assert d["share_of_gross_profit_pct"] == 25.0
    cards = {c["id"]: c for c in d["cards"]}
    assert cards[2]["action"] == "Bring London back to its €360k budget (−14%)"
    assert {c["role"] for c in d["cards"]} == {"Growth manager", "Leadership", "Product owner"}
    assert cards[3]["alone"] is None and not cards[3]["priced"]


@pytest.mark.parametrize("gain,expect", [(900, []), (1_001, [2]), (30_000, [2])])
def test_beat_the_ai_needs_a_material_measured_gain(tmp_path, gain, expect):
    assert B.deck_view(*_reports(tmp_path, loo_gain=gain))["beat_the_ai"] == expect


def test_missing_leave_one_out_report_is_gos_101(tmp_path):
    team, outcomes, loo = _reports(tmp_path)
    loo.unlink()
    with pytest.raises(B.BuildError) as e:
        B.deck_view(team, outcomes, loo)
    assert e.value.code == "GOS-101" and "--leave-one-out" in str(e.value)


def test_stale_leave_one_out_report_is_gos_102(tmp_path):
    team, outcomes, loo = _reports(tmp_path)
    team.write_text(json.dumps({"decisions": {"recommendations": [{"changed": True}]}}))
    with pytest.raises(B.BuildError) as e:
        B.deck_view(team, outcomes, loo)
    assert e.value.code == "GOS-102" and "team.json changed" in str(e.value)
    assert B.deck_view(team, outcomes, loo, allow_stale=True)["stale"] is True


def test_unknown_role_is_gos_103_and_names_no_persona(tmp_path):
    with pytest.raises(B.BuildError) as e:
        B.deck_view(*_reports(tmp_path, approver="Alex (marketing wizard) (wizard)"))
    assert e.value.code == "GOS-103" and "decision #1" in str(e.value) and "Alex" not in str(e.value)


def test_audit_roles_map_to_the_six_labels():
    assert B._role("Lee (product) (product_owner)", "audit") == "Product owner"
    assert B._role("Alex (paid media) (channel_manager)", "audit") == "Paid media manager"
    assert set(B.ROLE_LABELS.values()) == {"Leadership", "Growth manager", "Paid media manager", "CRM manager", "Product owner", "Finance"}


def test_text_decoding_is_idempotent():
    once = B._text("London \\u20ac360k (\\u221214%)")
    assert once == "London €360k (−14%)" and B._text(once) == once


def test_snapshot_renders_without_hubs_or_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    snap = tmp_path / "console-data.json"
    snap.write_text(json.dumps({"built": "2026-11-03", "evals": [], "views": [{"id": "x", "title": "X", "label": "", "blurb": "", "ent": {}}]}))
    html = B.render_snapshot(tmp_path / "dist", snap).read_text()
    assert 'id="gos-data"' in html and (tmp_path / "dist" / "app.js").is_file()
    with pytest.raises(B.BuildError) as e:
        B.render_snapshot(tmp_path / "dist", tmp_path / "missing.json")
    assert e.value.code == "GOS-101"


def test_same_input_gives_the_same_app_version(tmp_path):
    snap = tmp_path / "s.json"
    snap.write_text(json.dumps({"built": "2026-11-03", "evals": [], "views": []}))
    a = B.render_snapshot(tmp_path / "a", snap).read_text()
    b = B.render_snapshot(tmp_path / "b", snap).read_text()
    assert a == b


def test_app_js_carries_the_deck_rules():
    code = (ROOT / "growth_os" / "console" / "viz.js").read_text()
    assert "In the live loop a rejection needs a reason, and nothing runs." in code
    assert "Decision deck data missing" in code
    assert 'VZ.tipEl.innerHTML' not in code and "vzSafe(" in code  # tooltips are rebuilt from a tag allowlist, never raw HTML
    deck = code[code.index("// ---- Decision deck"):]
    for line in deck.splitlines():  # agent text reaches the page only through esc()
        if "c.action" in line or "c.role" in line:
            assert "esc(c.action)" in line or "esc(c.role)" in line or "esc(lab)" in line or "bar(" in line, line
