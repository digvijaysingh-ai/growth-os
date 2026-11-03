"""Turns approved actions into the enterprise world's spending policy, and measures a quarter with vs without them.

EnterpriseSandbox  executor adapter: budget actions change the sandbox account (policy_state, weather_rules); tickets,
                   email flows and notifications become work items, as in the B2C sandbox
to_policy(hub)     reads what was executed and builds the world Policy for the next quarter. Work done by people is
                   given a stated delay before it takes effect (ASSUMPTIONS)
impact(...)        the same business run for a quarter twice from the same day, with and without the policy: revenue,
                   gross profit after marketing, MER, spend, by market and in total
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

from ..actions.executor import Refused
from ..config import ROOT
from ..hub import store
from .profile import LINES, MARKETS, PAID, UPPER_FUNNEL
from .world import Policy, UNTIL, build

# Without the system, a team still notices problems, just later. The as-is baseline fixes each one after a typical
# delay counted from the decision day; the system gets credit only for acting sooner. (Stated assumptions.)
BAU_DELAY = {"payment_fix": 10, "delivery_fix": 21, "seo_fix": 35, "restock": 14, "new_creative": 21}
FIX_DELAY = {"payment_fix": 3, "delivery_fix": 7, "seo_fix": 10, "restock": 3, "new_creative": 7}
ASSUMPTIONS = [
    "Baseline (no system): the team still catches each problem, later. Counting from the decision day, a payment fault is fixed after 10 days, "
    "late deliveries after 21, a search-traffic drop after 35, a sell-out restocked after 14, a worn-out creative replaced after 21.",
    "With the system, the approved ticket fixes it sooner: payment 3 days, deliveries 7, search traffic 10, restock 3, creative 7. A ticket only "
    "counts if it goes to a team that can fix it and names the right market and the right kind of problem.",
    "Budget changes take effect the day after approval and stay for the quarter.",
    "Weather after the 16-day forecast is taken from the same calendar day last year.",
    "A/B tests, notifications, email flows and other tickets are executed and tracked; their effects are not simulated.",
]
# (fix, teams that can fix it, words that describe the problem, scenario key naming where it is)
FIX_RULES = [
    ("payment_fix", ("engineering", "product"), r"payment|checkout|apple pay|google pay|card|ios|android", "payment_markets"),
    ("delivery_fix", ("ops", "logistics"), r"deliver|carrier|late|shipping|tracking", "delivery_market"),
    ("seo_fix", ("seo", "engineering", "product"), r"seo|organic|redirect|search|site change|migration|404|url", "seo_market"),
    ("restock", ("ops", "logistics", "product"), r"restock|capacity|stock|sold out|sold-out|edition", "sellout"),
    ("new_creative", ("creative",), r"creative|video|ad|fatigue", "fatigue"),
]


def _sim_root() -> Path:
    root = ROOT / "state" / "sim"
    root.mkdir(parents=True, exist_ok=True)
    return root


def baseline(start: date) -> Policy:
    """The as-is business: no budget changes, problems fixed after the usual delay."""
    return Policy(start=start, fixes={k: (start + timedelta(days=v)).isoformat() for k, v in BAU_DELAY.items()}, note="as-is, problems found later")


def _key(m, l, c):
    return f"{m}|{l}|{c}"


def _state(db, keys):
    have = {r[0]: (r[1], r[2]) for r in db.execute("SELECT key, mult, paused FROM policy_state")}
    return {k: {"mult": have.get(k, (1.0, 0))[0], "paused": have.get(k, (1.0, 0))[1]} for k in keys}


def _set(db, key, mult=None, paused=None):
    cur = _state(db, [key])[key]
    db.execute("INSERT OR REPLACE INTO policy_state (key, mult, paused) VALUES (?, ?, ?)",
               (key, round(cur["mult"] if mult is None else mult, 4), cur["paused"] if paused is None else int(paused)))


class EnterpriseSandbox:
    name = "sandbox"

    def apply(self, db, ex: dict, rec_id: int, today: str):
        kind, t, to, pct = ex["type"], ex["target"], ex.get("to_target", ""), float(ex.get("amount_pct") or 0)
        if kind == "reallocate_channel":
            before = _state(db, [t, to])
            plan = {r[0]: r[1] for r in db.execute("""SELECT market || '|' || line || '|' || channel, budget FROM budget_plan
                                                      WHERE month = (SELECT MAX(month) FROM budget_plan) AND market || '|' || line || '|' || channel IN (?, ?)""", (t, to))}
            moved = plan[t] * before[t]["mult"] * pct / 100
            _set(db, t, mult=before[t]["mult"] * (1 - pct / 100))
            _set(db, to, mult=before[to]["mult"] + moved / plan[to])
            return before, _state(db, [t, to]), f"moved {pct:g}% of {t} (about €{moved:,.0f} a month) to {to}"
        if kind in ("change_line_budget", "change_budget"):
            m, l = (t.split("|") + [None])[:2]
            keys = [_key(m, ln, c) for ln in ([l] if l else list(LINES)) for c in PAID]
            before = _state(db, keys)
            for k in keys:
                _set(db, k, mult=before[k]["mult"] * (1 + pct / 100))
            return before, _state(db, keys), f"{t}: paid budget {pct:+g}%"
        if kind == "pause_channel":
            before = _state(db, [t])
            _set(db, t, paused=1)
            return before, _state(db, [t]), f"{t} paused"
        if kind == "apply_mix_plan":
            from . import mix
            from .profile import LINES as _L, MARKETS as _M
            parts = t.split("|")
            mk = list(_M) if t == "all" else [parts[0]]
            ln = list(_L) if len(parts) < 2 else [parts[1]]
            old_move = mix.MAX_MOVE
            mix.MAX_MOVE = pct / 100
            try:
                plans = mix.plan(db, [f for f in mix.fit_all(db, list(_M), list(_L)) if f["market"] in mk and f["line"] in ln])
            finally:
                mix.MAX_MOVE = old_move
            keys = [_key(p["market"], p["line"], mv["channel"]) for p in plans for mv in p["moves"]]
            before = _state(db, keys)
            for p in plans:
                for mv in p["moves"]:
                    if mv["from"]:
                        k = _key(p["market"], p["line"], mv["channel"])
                        _set(db, k, mult=before[k]["mult"] * mv["to"] / mv["from"])
            gain = sum(p["expected_weekly_revenue_gain"] for p in plans)
            return before, _state(db, keys), f"{t}: channel split applied on {len(plans)} market-lines (max ±{pct:g}% per channel); model expects +€{gain:,.0f} revenue a week"
        if kind == "weather_rule":
            db.execute("INSERT OR REPLACE INTO weather_rules (key, boost_pct) VALUES (?, ?)", (t, pct))
            return {}, {"weather_rule": t}, f"{t}: upper-funnel spend +{pct:g}% on rainy days"
        work = {"launch_ab_test": "ab_test", "trigger_email_flow": "email_flow", "open_ticket": "ticket", "notify": "notification"}
        if kind in work:
            cur = db.execute("INSERT INTO work_items (rec_id, kind, target, note, status, opened_on) VALUES (?, ?, ?, ?, ?, ?)",
                             (rec_id, work[kind], t, ex.get("note", ""), "sent" if kind == "notify" else "open", today))
            return {}, {"work_item": cur.lastrowid}, f"{work[kind].replace('_', ' ')} for {t} (sandbox #{cur.lastrowid})"
        raise Refused(f"the enterprise sandbox cannot run {kind}")

    def undo(self, db, ex: dict, before: dict, rec_id: int) -> str:
        if ex["type"] == "weather_rule":
            db.execute("DELETE FROM weather_rules WHERE key = ?", (ex["target"],))
            return "rule removed"
        if not before or "work_item" in json.dumps(before):
            db.execute("UPDATE work_items SET status = 'cancelled' WHERE rec_id = ?", (rec_id,))
            return "work item cancelled"
        for k, v in before.items():
            _set(db, k, mult=v["mult"], paused=v["paused"])
        return f"restored {len(before)} channel budget(s)"


def to_policy(db: sqlite3.Connection, start: date, seed: int) -> Policy:
    from .world import scenario
    sc = scenario(seed)
    pol = baseline(start)
    pol.note = "approved decisions"
    for k, mult, paused in db.execute("SELECT key, mult, paused FROM policy_state"):
        m, l, c = k.split("|")
        if paused:
            pol.paused.add((m, l, c))
        elif abs(mult - 1) > 1e-6:
            pol.mult[(m, l, c)] = mult
    for k, boost in db.execute("SELECT key, boost_pct FROM weather_rules"):
        m, l = k.split("|")
        pol.weather_boost[(m, l)] = 1 + boost / 100
    for team, note, opened in db.execute("SELECT target, note, opened_on FROM work_items WHERE kind = 'ticket' AND status != 'cancelled'"):
        for name, teams, words, where in FIX_RULES:
            v = sc[where]
            places = [v[0]] if where in ("sellout", "fatigue") else (list(v) if isinstance(v, list) else [v])
            if team in teams and re.search(words, note, re.I) and any(p.lower() in note.lower() for p in places):
                day = (date.fromisoformat(opened) + timedelta(days=FIX_DELAY[name])).isoformat()
                pol.fixes[name] = min(pol.fixes.get(name, day), day)
    return pol


def _measure(hub: Path, since: str) -> dict:
    margin = {l: v["margin"] for l, v in LINES.items()}
    with store.connect(hub, read_only=True) as db:
        rev = {(r[0], r[1]): r[2] for r in db.execute("SELECT market, line, SUM(revenue) FROM sales_daily WHERE day >= ? GROUP BY 1, 2", (since,))}
        spend = {(r[0], r[1]): r[2] for r in db.execute("SELECT market, line, SUM(spend) FROM ad_daily WHERE day >= ? GROUP BY 1, 2", (since,))}
        orders = db.execute("SELECT SUM(orders), SUM(new_customers) FROM sales_daily WHERE day >= ?", (since,)).fetchone()
    by_m = {}
    for (m, l), r in rev.items():
        x = by_m.setdefault(m, {"revenue": 0.0, "spend": 0.0, "gross_profit": 0.0})
        x["revenue"] += r
        x["spend"] += spend.get((m, l), 0)
        x["gross_profit"] += r * margin[l] - spend.get((m, l), 0)
    tot = {k: round(sum(v[k] for v in by_m.values())) for k in ("revenue", "spend", "gross_profit")}
    tot["mer"] = round(tot["revenue"] / tot["spend"], 2) if tot["spend"] else None
    tot["orders"], tot["new_customers"] = orders
    tot["cac"] = round(tot["spend"] / tot["new_customers"], 2) if tot["new_customers"] else None
    return {"total": tot, "by_market": {m: {k: round(v) for k, v in x.items()} for m, x in by_m.items()}}


def impact(policy: Policy, seed: int = 7, days: int = 91, until: date = UNTIL, label: str = "decisions", sim_dir: Path | None = None) -> dict:
    """`sim_dir` is the caller's own scratch directory (one per run): the as-is run is cached there, keyed by seed, start
    and horizon, so it is reused within a run and never picked up by another. Without it, nothing is cached."""
    own = sim_dir is None
    sim = Path(tempfile.mkdtemp(prefix="impact-", dir=_sim_root())) if own else sim_dir
    try:
        a, b = sim / f"impact-{seed}-{until.isoformat()}-{days}-asis.sqlite", sim / f"impact-{seed}-{label}.sqlite"
        if not a.is_file():
            build(a, seed, until=until, horizon=days, policy=baseline(until + timedelta(days=1)))
        build(b, seed, until=until, horizon=days, policy=policy)
        since = (until + timedelta(days=1)).isoformat()
        base, new = _measure(a, since), _measure(b, since)
    finally:
        for f in (sim / f"impact-{seed}-{label}.sqlite", sim / f"impact-{seed}-{label}.truth.json"):
            f.unlink(missing_ok=True)  # each scenario is measured once; only the as-is run is kept, within this run
        if own:
            shutil.rmtree(sim, ignore_errors=True)
    d = {k: round(new["total"][k] - base["total"][k], 2) for k in ("revenue", "spend", "gross_profit", "orders", "new_customers")}
    pct = {k: round(100 * d[k] / base["total"][k], 1) for k in ("revenue", "spend", "gross_profit") if base["total"][k]}
    return {"days": days, "from": since, "as_is": base["total"], "with_decisions": new["total"], "change": d, "change_pct": pct,
            "by_market": {m: {k: new["by_market"][m][k] - base["by_market"][m][k] for k in ("revenue", "spend", "gross_profit")} for m in base["by_market"]},
            "assumptions": ASSUMPTIONS, "policy": {"mult": {"|".join(k): v for k, v in policy.mult.items()}, "paused": ["|".join(k) for k in policy.paused],
                                                   "weather_boost": {"|".join(k): v for k, v in policy.weather_boost.items()}, "fixes": policy.fixes},
            "baseline": "as-is budgets; each problem still fixed by the team, later (see assumptions)",
            "note": "SIMULATED: synthetic business; both runs share every random draw, so the difference is the decisions."}
