from datetime import date

import pytest

from growth_os import attribution, showcase, whynot, world
from growth_os.hub import store


@pytest.fixture(scope="module")
def hub(tmp_path_factory):
    return showcase.prepare(tmp_path_factory.mktemp("sc") / "hub.sqlite", seed=3, until=date(2026, 10, 25))


def test_why_not_buy_finds_planted_causes_across_sources(hub):
    with store.connect(hub, read_only=True) as db:
        causes = {(c["market"], c["cause"]): c for c in whynot.engine(db)}
    for m in ("Berlin", "Amsterdam"):
        c = causes[(m, "payment_failure")]
        assert {"funnel", "behaviour", "survey"} <= set(c["sources"]) and c["lost_revenue_28d"] > 0
    assert "capacity" in causes[("London", "capacity")]["sources"]
    assert ("Mexico City", "trust") in causes
    assert not any(m in ("São Paulo", "Miami") and c["confidence"] == "high" for (m, _), c in causes.items())


def test_attribution_lenses_disagree_the_way_the_ground_truth_says(hub):
    with store.connect(hub, read_only=True) as db:
        rows = {r["channel"]: r for r in attribution.compare(db)}
        plan = attribution.holdout_plan(db)
    brand, meta = rows["paid:google_brand"], rows["paid:meta"]
    assert brand["journeys_last_touch_pct"] > brand["data_driven_pct"]     # last touch over-credits the closer
    assert meta["data_driven_pct"] > meta["journeys_last_touch_pct"]       # and under-credits prospecting
    assert meta["platform_overclaim_x"] > 1.2
    assert plan["weeks"] >= 1 and "Mexico City" not in plan["switch_off_in"] + plan["keep_on_in"]


def test_economics_views_and_targets(hub):
    with store.connect(hub, read_only=True) as db:
        m = {r["market"]: dict(r) for r in db.execute("SELECT * FROM v_market_economics_28d")}
        assert db.execute("SELECT COUNT(*) FROM targets").fetchone()[0] == len(showcase.TARGETS)
    assert m["Mexico City"]["blended_cac"] > m["Madrid"]["blended_cac"]
    assert all(r["mer"] and r["spend_pct_of_revenue"] for r in m.values())


def test_world_step_keeps_behaviour_in_sync(hub):
    h = world.fork(hub, "bh")
    world.step(h, 3, seed=3)
    with store.connect(h, read_only=True) as db:
        assert db.execute("SELECT MAX(day) FROM events_daily").fetchone()[0] == db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]


def test_briefs_and_escalation(hub):
    from datetime import datetime, timedelta

    from growth_os import stakeholders, tracker
    h = world.fork(hub, "st")
    sql = "SELECT SUM(revenue) AS value FROM sales_daily WHERE day > date((SELECT MAX(day) FROM sales_daily), '-7 days')"
    rec = {"action": "pause it", "why": "", "expected_impact": "", "effort": "S", "confidence": "high", "how_to_measure": "", "metric_sql": sql,
           "check_after_days": 14, "direction": "up", "execution": {"type": "pause_ad", "target": "PAR-META-1", "to_target": "", "amount_pct": 0, "note": ""}}
    tracker.record(h, {"recommendations": [rec]}, "2026-10-25")
    b = stakeholders.briefs(h)
    assert set(b["roles"]) == {"leadership", "growth_manager", "channel_manager", "crm_manager", "product_owner", "finance"}
    assert len(b["roles"]["channel_manager"]["needs_your_decision"]) == 1
    r1 = stakeholders.reminders(h, datetime.now() + timedelta(hours=30))
    r2 = stakeholders.reminders(h, datetime.now() + timedelta(hours=60))
    assert r1[0]["kind"] == "reminder" and r1[0]["to"] == "channel_manager"
    assert r2[0]["kind"] == "escalation" and r2[0]["to"] == "leadership"
