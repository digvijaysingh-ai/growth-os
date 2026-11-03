import sqlite3
from datetime import date

import pytest

from growth_os import tracker
from growth_os.actions import catalog, executor
from growth_os.enterprise import benchmarks, demand, mix, policy, voc, world
from growth_os.enterprise.profile import LINES, MARKETS
from growth_os.hub import store

SEED = 3
SC = world.scenario(SEED)


@pytest.fixture(scope="module")
def hub(tmp_path_factory):
    p = tmp_path_factory.mktemp("ent") / "hub.sqlite"
    world.build(p, seed=SEED)
    voc.generate(p, seed=SEED)
    with store.connect(p) as db:  # label by the theme each template came from (no API call in tests)
        rows = db.execute("SELECT item_id, text FROM voc_items").fetchall()
        lookup = {phr.format(p=l.lower()): th for th, langs in voc.T.items() for ps in langs.values() for phr in ps for l in LINES}
        db.executemany("INSERT INTO voc_labels (item_id, theme, sentiment, summary, model) VALUES (?, ?, 'negative', '', 'template')",
                       [(i, lookup.get(t, "other")) for i, t in rows])
        db.commit()
    return p


def test_scenarios_differ_by_seed():
    a, b = world.scenario(301), world.scenario(302)
    assert (a["payment_markets"], a["demand_gap"], a["sellout"]) != (b["payment_markets"], b["demand_gap"], b["sellout"])


def test_history_is_the_same_whatever_the_future_policy(tmp_path):
    a, b = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
    world.build(a, seed=5)
    world.build(b, seed=5, horizon=14, policy=world.Policy(mult={("Madrid", "Home", "tiktok"): 2.0}))
    q = "SELECT ROUND(SUM(revenue)) FROM sales_daily WHERE day <= '2026-11-01'"
    assert sqlite3.connect(a).execute(q).fetchone() == sqlite3.connect(b).execute(q).fetchone()


def test_engines_find_planted_situations(hub):
    db = sqlite3.connect(hub)
    worst = min((p for p in demand.potential(db) if not p["new_market"]), key=lambda p: p["captured_share_of_potential_pct"])
    assert (worst["market"], worst["line"]) == tuple(SC["demand_gap"])
    rain = demand.sensitivity(db, SC["weather_strong"][0], SC["weather_line"])
    assert rain["rain_effect_range_pct"][0] > 15
    pay = benchmarks.benchmark(db, SC["payment_markets"][0], f"checkout_to_order_{SC['payment_device']}_pct", None, 14)
    assert pay["value"] < 30 and pay["same_period_last_year"] > 50
    trap = benchmarks.benchmark(db, SC["seasonal_market"], "revenue_per_day", None, 28)
    assert abs(trap["value"] / trap["same_period_last_year"] - 1) < 0.1
    fits = {(f["market"], f["line"]): f for f in mix.fit_all(db, list(MARKETS), list(LINES))}
    sat = fits[(SC["saturated_meta"][0], "Home")]["channels"]
    assert sat["tiktok"]["marginal_roas"] > sat["meta_prospecting"]["marginal_roas"]
    gaps = {(g["market"], g["theme"]) for g in voc.gaps(db)}
    assert (SC["delivery_market"], "delivery_late") in gaps and (SC["slow_launch"], "trust_brand") in gaps


def test_actions_become_a_policy(hub, tmp_path):
    h = tmp_path / "p.sqlite"
    h.write_bytes(hub.read_bytes())
    sql = "SELECT SUM(revenue) AS value FROM sales_daily WHERE day > date((SELECT MAX(day) FROM sales_daily), '-7 days')"
    def rec(kind, t, to="", pct=0.0, note="x"):
        return {"action": kind, "why": "", "expected_impact": "", "effort": "S", "confidence": "high", "how_to_measure": "", "metric_sql": sql,
                "check_after_days": 14, "direction": "up", "execution": {"type": kind, "target": t, "to_target": to, "amount_pct": pct, "note": note}}
    with store.connect(h, read_only=True) as db:
        assert not catalog.check(db, {"type": "reallocate_channel", "target": "Madrid|Home|meta_prospecting", "to_target": "Paris|Home|tiktok", "amount_pct": 20}).ok
    pm = SC["payment_markets"]
    tracker.record(h, {"recommendations": [rec("reallocate_channel", "Madrid|Home|meta_prospecting", "Madrid|Home|tiktok", 40),
                                           rec("weather_rule", "London|Home", pct=25),
                                           rec("open_ticket", "engineering", note=f"Payments failing at checkout in {pm[0]} and {pm[1]}"),
                                           rec("open_ticket", "engineering", note="Payments failing at checkout in a market with no problem: Lisbonia")]}, "2026-11-01")
    with store.connect(h) as db:
        db.executemany("INSERT INTO team (person, role) VALUES (?, ?)", [("Sam", "growth_manager"), ("Alex", "channel_manager"), ("Lee", "product_owner")])
        db.commit()
    who = {"growth_manager": "Sam", "channel_manager": "Alex", "product_owner": "Lee"}
    for r in executor.inbox(h):
        executor.decide(h, r["id"], True, who[r["approver_role"]], r["approver_role"])
    out = executor.run_approved(h, policy.EnterpriseSandbox(), today="2026-11-02")
    assert all(o["status"] == "executed" for o in out)
    with store.connect(h, read_only=True) as db:
        pol = policy.to_policy(db, date(2026, 11, 2), SEED)
    assert round(pol.mult[("Madrid", "Home", "meta_prospecting")], 2) == 0.6 and pol.mult[("Madrid", "Home", "tiktok")] > 1.5
    assert pol.weather_boost[("London", "Home")] == 1.25 and pol.fixes["payment_fix"] == "2026-11-05"
    assert pol.fixes["delivery_fix"] == policy.baseline(date(2026, 11, 2)).fixes["delivery_fix"]   # untouched: found later, as usual
