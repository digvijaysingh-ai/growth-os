import json
import sqlite3
from types import SimpleNamespace

from growth_os import demo_enterprise
from growth_os.hub import store
from growth_os.listening.classify import THEMES, _parse


def _period(db, market, col, recent):
    op = ">=" if recent else "<"
    return db.execute(f"SELECT SUM({col}) FROM v_market_daily WHERE market = ? AND day {op} '2026-09-20' AND day >= '2026-08-16'", (market,)).fetchone()[0]


def test_enterprise_needles_are_where_planted_and_nowhere_else(tmp_path):
    hub = demo_enterprise.build(tmp_path / "e.sqlite", seed=7)
    with store.connect(hub, read_only=True) as db:
        # France: mobile form errors jump after the break
        assert _period(db, "FR", "form_errors", True) > 1.6 * _period(db, "FR", "form_errors", False)
        # noise-only markets: no jump in errors or drop in qualified leads of that size
        for m in demo_enterprise.NOISE_ONLY:
            assert _period(db, m, "form_errors", True) < 1.6 * _period(db, m, "form_errors", False) + 10
        # Italy: contact got slow
        slow = db.execute("SELECT AVG(hours_to_contact > 24) FROM leads WHERE market = 'IT' AND day >= '2026-09-20'").fetchone()[0]
        assert slow > 0.7
        assert db.execute("SELECT COUNT(DISTINCT market) FROM leads").fetchone()[0] == 10


def test_old_hub_files_gain_new_columns(tmp_path):
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE leads (day TEXT NOT NULL, origin TEXT NOT NULL, stage TEXT NOT NULL)")
    db.commit()
    db.close()
    with store.connect(path) as db:
        cols = {r[1] for r in db.execute("PRAGMA table_info(leads)")}
        assert {"market", "landing", "value_after_90d"} <= cols
        db.execute("SELECT * FROM v_market_daily").fetchall()


def _msg(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


def test_listening_parser_keeps_only_known_themes():
    out = _parse(_msg(json.dumps({"sentiment": "negative", "themes": ["late_delivery", "made_up", "late_delivery", "poor_quality", "other", "price_value"],
                                  "pain_point": "late", "summary": "Arrived late."})))
    assert out["themes"] == ["late_delivery", "poor_quality", "other"] and set(out["themes"]) <= set(THEMES)
    assert _parse(_msg("not json")) is None
    assert _parse(_msg("{}", stop="refusal")) is None


def test_ai_visibility_matching_is_exact_and_ranked():
    from pathlib import Path

    from growth_os.visibility.track import load_config, score
    brands = load_config(Path(__file__).resolve().parent.parent / "cases" / "olist.visibility.toml")["brands"]
    out = {r["brand"]: r for r in score("Primeiro o Bling, depois a Olist. O link tinyurl.com/x não conta.", ["blog.bling.com.br", "olist.com.evil.net"], brands)}
    assert out["Bling"]["rank"] == 1 and out["Olist"]["rank"] == 2
    assert not out["Tiny ERP"]["mentioned"]                      # 'tinyurl' is not the brand Tiny
    assert out["Bling"]["cited"] and not out["Olist"]["cited"]   # subdomain counts, look-alike domain does not


def test_tracker_records_baseline_and_judges_outcome(tmp_path):
    from datetime import date

    from growth_os import demo_enterprise, tracker
    hub = demo_enterprise.build(tmp_path / "e.sqlite", seed=7)
    sql = "SELECT SUM(form_submits) * 1.0 / SUM(form_starts) AS value FROM web_sessions WHERE market = 'FR' AND day > date((SELECT MAX(day) FROM web_sessions), '-14 days')"
    memo = {"recommendations": [{"action": "Fix the French mobile form", "confidence": "high", "expected_impact": "x", "metric_sql": sql,
                                 "direction": "up", "check_after_days": 14},
                                {"action": "Broken metric", "confidence": "low", "expected_impact": "x", "metric_sql": "DELETE FROM leads",
                                 "direction": "up", "check_after_days": 14}]}
    recs = tracker.record(hub, memo, "2026-10-25")
    assert recs[0]["metric_ok"] and recs[0]["baseline"] < 0.7 and not recs[1]["metric_ok"]
    tracker.decide(hub, 1, True, "growth lead")
    with store.connect(hub) as db:  # simulate the fix: the old window's rate goes back up
        db.execute("UPDATE recommendations SET baseline = baseline * 0.5 WHERE id = 1")
        db.commit()
    assert tracker.followup(hub, date(2026, 11, 10))[0]["verdict"] == "moved as hoped"
    s = tracker.summary(hub)
    assert s["accepted"] == 1 and s["worked"] == 1


def test_mcp_server_is_read_only(tmp_path, monkeypatch):
    import asyncio

    import pytest
    pytest.importorskip("mcp")
    from growth_os import demo_enterprise, mcp_server
    monkeypatch.setattr(mcp_server, "HUB", demo_enterprise.build(tmp_path / "e.sqlite", seed=7))

    async def go():
        tools = await mcp_server.server.list_tools()
        assert tools and all(t.annotations.read_only_hint for t in tools)
        ok = await mcp_server.server.call_tool("query", {"sql": "SELECT COUNT(*) AS n FROM leads"})
        bad = await mcp_server.server.call_tool("query", {"sql": "DELETE FROM leads"})
        return str(ok), str(bad)
    ok, bad = asyncio.run(go())
    assert '"rows"' in ok and "only one read-only SELECT" in bad
