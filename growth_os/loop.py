"""The closed loop on the SIMULATED B2C business: recommend -> approve or reject -> execute -> measure vs counterfactual.

For each recommendation in a memo, two copies of the hub run forward the same number of days with the same random
draws: one where the action was approved and executed, one where nothing was done. The difference is what the decision
was worth, in the recommendation's own metric and in revenue, spend and orders. Only a simulation can show this
exactly; in a real business the same comparison needs a holdout (see the attribution module).

    growth-os loop --hub state/eval-b2c-7.sqlite --memo reports/memo-b2c.json --out reports/loop-b2c.json
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from . import tracker, world
from .actions import catalog, executor
from .actions.adapters import SandboxAdapter
from .hub import store

ROLE_PEOPLE = {"leadership": "Dana (leadership)", "growth_manager": "Sam (growth manager)", "channel_manager": "Alex (paid media)",
               "crm_manager": "Kim (CRM)", "product_owner": "Lee (product)", "finance": "Robin (finance)"}  # fictional demo roles


def _last_day(hub: Path) -> date:
    with store.connect(hub, read_only=True) as db:
        return date.fromisoformat(db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0])


def _metric_at(hub: Path, sql: str) -> float | None:
    return world.metric(hub, sql)


def _scope(db, r: dict) -> list[str]:
    """The market(s) a recommendation acts on, for its before/after chart."""
    t, kind = r["exec_target"], r["exec_type"]
    if kind in ("pause_ad", "resume_ad", "rotate_creative", "shift_budget"):
        row = db.execute("SELECT market FROM ad_daily WHERE ad_id = ? LIMIT 1", (t,)).fetchone()
        return [row[0]] if row else []
    if kind == "change_budget":
        return [t]
    if kind == "trigger_email_flow":
        row = db.execute("SELECT market FROM products WHERE product_id = ?", (t,)).fetchone()
        return [row[0]] if row else []
    text = r["action"].lower()  # the title names where it acts; the note also cites comparison markets
    return [m for (m,) in db.execute("SELECT DISTINCT market FROM sales_daily") if m.lower() in text]


def _series(hub: Path, markets: list[str], since: date, days: int) -> list[dict]:
    q = "SELECT day, ROUND(SUM(revenue)) AS revenue FROM sales_daily WHERE day >= ? AND day < ?" + (
        f" AND market IN ({','.join('?' * len(markets))})" if markets else "") + " GROUP BY day ORDER BY day"
    with store.connect(hub, read_only=True) as db:
        return [dict(r) for r in db.execute(q, (since.isoformat(), (since + timedelta(days=days)).isoformat(), *markets))]


def evaluate(hub: Path, memo: dict, memo_date: str, seed: int = 7, horizon: int | None = None) -> dict:
    """Runs every recommendation through approve -> execute -> simulate, against doing nothing. Leaves `hub` untouched."""
    with store.connect(hub, read_only=True) as db:
        g = db.execute("SELECT gross_margin FROM unit_costs WHERE scope = 'all'").fetchone() if db.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'unit_costs'").fetchone() else None
    margin = g[0] if g else 0.45
    base = world.fork(hub, "base")
    recorded = tracker.record(base, memo, memo_date)
    with store.connect(base) as db:  # the fictional demo team: one person per role
        db.executemany("INSERT OR IGNORE INTO team (person, role) VALUES (?, ?)", [(p, r) for r, p in ROLE_PEOPLE.items()])
        db.commit()
    start = _last_day(base) + timedelta(days=1)
    with store.connect(base, read_only=True) as db:
        recs = [dict(r) for r in db.execute("SELECT * FROM recommendations WHERE memo_date = ? ORDER BY rank", (memo_date,))]
    days_needed = max([min(28, max(7, r["check_after_days"])) for r in recs] + [7]) if horizon is None else horizon
    nothing = world.fork(base, "nothing")
    world.step(nothing, days_needed, seed)
    results = []
    for r in recs:
        h = min(28, max(7, r["check_after_days"])) if horizon is None else horizon
        spec = catalog.CATALOG.get(r["exec_type"], catalog.CATALOG["manual"])
        item = {"id": r["id"], "rank": r["rank"], "action": r["action"], "execution": {k: r[k] for k in ("exec_type", "exec_target", "exec_to", "exec_pct", "exec_note")},
                "label": spec.label, "risk": r["risk"], "approver_role": r["approver_role"], "approver": catalog.ROLES[r["approver_role"]],
                "rollback": spec.rollback, "baseline": r["baseline"], "check_after_days": r["check_after_days"], "horizon_days": h, "direction": r["direction"]}
        with store.connect(base, read_only=True) as db:
            scope = _scope(db, r)
        item["markets"] = scope
        # without the action (rejected, or never decided): same world, nothing executed
        cf_hub = world.fork(base, f"cf{r['id']}")
        world.step(cf_hub, h, seed)
        item["series_without"] = _series(cf_hub, scope, start - timedelta(days=14), h + 14)
        item["without"] = {"metric": _metric_at(cf_hub, r["metric_sql"]), **world.money(cf_hub, start)}
        if spec.executes:
            act = world.fork(base, f"act{r['id']}")
            who = ROLE_PEOPLE[r["approver_role"]]
            executor.decide(act, r["id"], True, who, r["approver_role"])
            ran = executor.run_approved(act, SandboxAdapter(), today=start.isoformat())
            item["execution_log"] = ran
            world.step(act, h, seed)
            with store.connect(act, read_only=True) as db:
                item["audit"] = [dict(x) for x in db.execute("SELECT kind, target, adapter, status, detail, approved_by, ts FROM action_runs")]
                item["work_items"] = [dict(x) for x in db.execute("SELECT kind, target, status, opened_on, closed_on, result FROM work_items")]
            item["with"] = {"metric": _metric_at(act, r["metric_sql"]), **world.money(act, start)}
            item["series_with"] = _series(act, scope, start - timedelta(days=14), h + 14)
            w, wo = item["with"], item["without"]
            item["delta"] = {k: round((w[k] or 0) - (wo[k] or 0), 2) for k in ("revenue", "spend", "orders")}
            # gross profit after marketing: what the business keeps (revenue x margin - spend)
            item["delta"]["profit"] = round(item["delta"]["revenue"] * margin - item["delta"]["spend"], 2)
            if not world.simulated(item["execution"]):
                item["verdict"] = "executed; effect not simulated"
            elif w["metric"] is not None and wo["metric"] is not None:
                ch = w["metric"] - wo["metric"]
                item["delta"]["metric"] = round(ch, 4)
                good = ch if r["direction"] == "up" else -ch
                rel = good / abs(wo["metric"]) if wo["metric"] else (1.0 if good > 0 else -1.0 if good < 0 else 0.0)  # from zero: any move counts
                item["verdict"] = "worked" if rel >= tracker.MOVE else ("backfired" if rel <= -tracker.MOVE else "no clear effect")
                if item["verdict"] == "worked" and item["delta"]["profit"] < 0:
                    item["verdict"] = "met its metric, cost profit"
            else:
                item["verdict"] = "metric unavailable"
        else:
            item["execution_log"] = [{"status": "manual", "detail": "a person carries this out; the system only tracks it"}]
            item["verdict"] = "not simulated (manual)"
        results.append(item)
    out = {"memo_date": memo_date, "start": start.isoformat(), "gross_margin": margin, "seed": seed, "assumptions": world.ASSUMPTIONS, "recorded": recorded,
           "nothing_done": world.money(nothing, start), "horizon_days": days_needed, "recommendations": results,
           "note": "SIMULATED: synthetic business; outcomes come from the simulation's stated assumptions, not from a real market."}
    world.cleanup()
    return out


def main(hub: Path, memo_path: Path, out: Path, seed: int = 7) -> dict:
    memo_doc = json.loads(memo_path.read_text())
    memo = memo_doc.get("memo", memo_doc)
    with store.connect(hub, read_only=True) as db:
        until = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
    res = evaluate(hub, memo, until, seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    return res
