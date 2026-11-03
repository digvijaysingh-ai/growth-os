from datetime import date
from pathlib import Path

import pytest

from growth_os import demo_b2c, tracker, world
from growth_os.actions import catalog, executor
from growth_os.actions.adapters import MetaAdapter, SandboxAdapter
from growth_os.hub import store

SQL = "SELECT SUM(revenue) AS value FROM sales_daily WHERE day > date((SELECT MAX(day) FROM sales_daily), '-7 days')"


def rec(kind, target="", to="", pct=0.0, note="x"):
    return {"action": f"do {kind}", "why": "", "expected_impact": "", "effort": "S", "confidence": "high", "how_to_measure": "",
            "metric_sql": SQL, "check_after_days": 14, "direction": "up",
            "execution": {"type": kind, "target": target, "to_target": to, "amount_pct": pct, "note": note}}


@pytest.fixture(scope="module")
def hub(tmp_path_factory):
    return demo_b2c.build(tmp_path_factory.mktemp("b2c") / "hub.sqlite", until=date(2026, 10, 25), weeks=10, seed=3)


def test_catalog_checks_targets_and_limits(hub):
    with store.connect(hub, read_only=True) as db:
        assert catalog.check(db, {"type": "pause_ad", "target": "PAR-META-1"}).ok
        assert not catalog.check(db, {"type": "pause_ad", "target": "NOPE"}).ok
        assert not catalog.check(db, {"type": "change_budget", "target": "Barcelona", "amount_pct": 80}).ok
        c = catalog.check(db, {"type": "change_budget", "target": "Barcelona", "amount_pct": 20})
        assert c.ok and c.risk == "high" and c.approver == "leadership"
        assert not catalog.check(db, {"type": "shift_budget", "target": "PAR-META-1", "to_target": "MAD-META-2", "amount_pct": 20}).ok
        assert not catalog.check(db, {"type": "open_ticket", "target": "engineering", "note": ""}).ok


def test_decide_enforces_roles_reasons_and_kill_switch(hub, monkeypatch):
    h = world.fork(hub, "t1")
    tracker.record(h, {"recommendations": [rec("pause_ad", "PAR-META-1"), rec("change_budget", "Barcelona", pct=-15)]}, "2026-10-25")
    ids = [r["id"] for r in executor.inbox(h)]
    with pytest.raises(executor.Refused):
        executor.decide(h, ids[1], True, "Alex", "channel_manager")       # wrong role for a budget change
    with pytest.raises(executor.Refused):
        executor.decide(h, ids[0], False, "Alex", "channel_manager")       # rejection without a reason
    executor.decide(h, ids[0], True, "Alex", "channel_manager")
    executor.decide(h, ids[1], False, "Sam", "growth_manager", reason="Q4 promo starts Monday")
    monkeypatch.setenv("GROWTH_OS_KILL", "1")
    assert executor.run_approved(h, SandboxAdapter())[0]["status"] == "blocked"
    monkeypatch.delenv("GROWTH_OS_KILL")
    with store.connect(h) as db:
        db.execute("DELETE FROM action_runs")
        db.commit()
    out = executor.run_approved(h, SandboxAdapter())
    assert [o["status"] for o in out] == ["executed"]
    with store.connect(h, read_only=True) as db:
        assert db.execute("SELECT status FROM account_state WHERE ad_id = 'PAR-META-1'").fetchone()[0] == "PAUSED"
        assert db.execute("SELECT reject_reason FROM recommendations WHERE id = ?", (ids[1],)).fetchone()[0] == "Q4 promo starts Monday"
    run_id = 1
    with store.connect(h, read_only=True) as db:
        run_id = db.execute("SELECT id FROM action_runs WHERE status = 'executed'").fetchone()[0]
    executor.rollback(h, run_id, SandboxAdapter())
    with store.connect(h, read_only=True) as db:
        assert db.execute("SELECT status FROM account_state WHERE ad_id = 'PAR-META-1'").fetchone()[0] == "ACTIVE"


def test_counterfactual_is_exact_where_nothing_changed(hub):
    a, b = world.fork(hub, "a"), world.fork(hub, "b")
    world.step(a, 7, seed=5)
    world.step(b, 7, seed=5)
    assert world.money(a, date(2026, 10, 26)) == world.money(b, date(2026, 10, 26))


def test_ios_ticket_fixes_checkout_in_simulation(hub):
    h = world.fork(hub, "t2")
    tracker.record(h, {"recommendations": [rec("open_ticket", "engineering", note="iOS checkout broken in Berlin and Amsterdam")]}, "2026-10-25")
    rid = executor.inbox(h)[0]["id"]
    executor.decide(h, rid, True, "Lee", "product_owner")
    executor.run_approved(h, SandboxAdapter(), today="2026-10-26")
    cf = world.fork(hub, "t2cf")
    world.step(h, 14)
    world.step(cf, 14)
    q = "SELECT SUM(orders) * 1.0 / SUM(checkouts) FROM sales_daily WHERE market = 'Berlin' AND device = 'ios' AND day >= '2026-10-30'"
    with store.connect(h, read_only=True) as d1, store.connect(cf, read_only=True) as d2:
        assert d1.execute(q).fetchone()[0] > 0.5 > d2.execute(q).fetchone()[0]


def test_live_adapter_refuses_anything_but_pause_and_resume():
    class FakeMeta:
        calls = []

        def set_status(self, ad_id, status):
            self.calls.append((ad_id, status))

    m = FakeMeta()
    ad = MetaAdapter(m)
    with pytest.raises(executor.Refused):
        ad.apply(None, {"type": "change_budget", "target": "x", "amount_pct": 10}, rec_id=1, today="2026-11-02")
    before, after, _ = ad.apply(None, {"type": "pause_ad", "target": "123"}, rec_id=1, today="2026-11-02")
    ad.undo(None, {"type": "pause_ad", "target": "123"}, before, rec_id=1)
    assert m.calls == [("123", "PAUSED"), ("123", "ACTIVE")]


def test_team_table_and_slack_endpoint(hub):
    import hashlib
    import hmac
    import time

    from growth_os import server
    h = world.fork(hub, "slack")
    tracker.record(h, {"recommendations": [rec("pause_ad", "PAR-META-1"), rec("change_budget", "Barcelona", pct=-10)]}, "2026-10-25")
    with store.connect(h) as db:
        db.executemany("INSERT INTO team (person, role) VALUES (?, ?)", [("U_ALEX", "channel_manager"), ("U_SAM", "growth_manager")])
        db.commit()
    ids = [r["id"] for r in executor.inbox(h)]
    with pytest.raises(executor.Refused):
        executor.decide(h, ids[1], True, "U_ALEX", "growth_manager")          # claims a role Alex does not hold
    out = server.handle(h, {"user": {"id": "U_ALEX"}, "actions": [{"action_id": "approve", "value": str(ids[0])}]}, SandboxAdapter())
    assert "executed" in out
    out = server.handle(h, {"user": {"id": "U_ALEX"}, "actions": [{"action_id": "approve", "value": str(ids[1])}]}, SandboxAdapter())
    assert out.startswith("Not approved")                                     # budget change needs the growth manager
    out = server.handle(h, {"user": {"id": "U_SAM"}, "actions": [{"action_id": "reject", "selected_option": {"value": f"{ids[1]}|Too risky this week"}}]}, SandboxAdapter())
    assert "rejected" in out
    body, ts = b"payload=x", str(int(time.time()))
    sig = "v0=" + hmac.new(b"s3cret", f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    assert server.verify("s3cret", ts, body, sig) and not server.verify("s3cret", ts, body + b"y", sig)
    assert not server.verify("s3cret", str(int(time.time()) - 600), body, sig)
