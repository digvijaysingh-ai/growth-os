"""Stakeholder layer: the same week, told to each role in the terms they manage, and nudges so decisions do not stall.

    briefs(hub)            one brief per role, every number computed from the hub (no model writes numbers here)
    reminders(hub, now)    approvals waiting longer than their service level go back to the approver; twice as long
                           goes to leadership as an escalation

Roles and what each brief answers:
  leadership         Are we on plan? MER and marketing as a share of revenue, CAC payback, the biggest money at stake,
                   decisions only leadership can take, and what last decisions achieved.
  growth_manager   What needs deciding now? The full inbox by role, overdue items, and what was executed.
  channel_manager  Which of my ads miss target (CPA, ROAS, CPM, fatigue), and what is waiting for me.
  crm_manager      Which products need a push before they end, and email flows running.
  product_owner    Where the site loses buyers (why-not-buy causes outside marketing) and tickets open.
  finance          Spend against budget per market, MER, CAC and payback, and budget changes approved.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .actions import catalog
from .hub import store

SLA_HOURS = {"low": 24, "medium": 48, "high": 72}


def _rows(db, sql, *p):
    try:
        return [dict(r) for r in db.execute(sql, p).fetchall()]
    except sqlite3.Error:
        return []


def _target(db, metric):
    r = _rows(db, "SELECT target, direction FROM targets WHERE scope = 'all' AND metric = ?", metric)
    return (r[0]["target"], r[0]["direction"]) if r else (None, None)


def _misses(value, target, direction):
    if value is None or target is None:
        return False
    return value < target if direction == "min" else value > target


def briefs(hub: Path) -> dict:
    with store.connect(hub, read_only=True) as db:
        asof = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
        econ = _rows(db, "SELECT * FROM v_market_economics_28d ORDER BY gross_revenue DESC")
        tot_rev = sum(r["gross_revenue"] or 0 for r in econ)
        tot_spend = sum(r["marketing_spend"] or 0 for r in econ)
        tot_new = sum(r["new_customers"] or 0 for r in econ)
        mer_t, mer_d = _target(db, "mer")
        cac_t, cac_d = _target(db, "blended_cac")
        inbox = _rows(db, """SELECT id, action, exec_type, exec_target, risk, approver_role, expected_impact, baseline_at FROM recommendations
                             WHERE status = 'proposed' ORDER BY memo_date DESC, rank""")
        done = _rows(db, """SELECT r.id, r.action, r.exec_type, r.exec_target, r.status, r.decided_by, r.reject_reason, r.verdict, a.detail, a.ts
                            FROM recommendations r LEFT JOIN action_runs a ON a.rec_id = r.id AND a.status = 'executed'
                            WHERE r.status != 'proposed' ORDER BY r.decided_at DESC LIMIT 20""")
        whynot = []
        if db.execute("SELECT EXISTS(SELECT 1 FROM events_daily)").fetchone()[0]:
            from .whynot import engine
            whynot = engine(db)
        pacing = _rows(db, "SELECT * FROM v_budget_pacing")
        products = _rows(db, """SELECT product_id, market, name, sold_pct, window_elapsed_pct, days_left, unsold_value FROM v_product_pacing
                                WHERE sold_pct < window_elapsed_pct - 20 ORDER BY unsold_value DESC LIMIT 8""")
        cpa_t, _ = _target(db, "cpa")
        roas_t, _ = _target(db, "roas")
        cpm_t, _ = _target(db, "cpm")
        ads = _rows(db, """SELECT ad_id, market, platform, creative, spend, cpm, ctr_pct, cpa, roas, platform_roas FROM v_ad_economics_28d
                           WHERE spend > 500 ORDER BY spend DESC""")
        fatigue = _rows(db, """SELECT ad_id, market, creative, ROUND(AVG(frequency), 2) AS frequency FROM ad_daily
                               WHERE day > date(?, '-7 days') AND frequency IS NOT NULL GROUP BY ad_id HAVING AVG(frequency) > 3.5""", asof)
        work = _rows(db, "SELECT kind, target, note, status, opened_on, closed_on, result FROM work_items ORDER BY id DESC")

    def mine(role):
        return [r for r in inbox if r["approver_role"] == role]

    money = [c for c in whynot if c.get("lost_revenue_28d")]
    mer = round(tot_rev / tot_spend, 2) if tot_spend else None
    out = {"as_of": asof, "note": "Every number is computed from the hub. SYNTHETIC data in the demo.", "roles": {}}
    out["roles"]["leadership"] = {
        "role": catalog.ROLES["leadership"],
        "headline": f"MER {mer} against a target of {mer_t:g} ({'on plan' if not _misses(mer, mer_t, mer_d) else 'below plan'}); "
                    f"marketing is {round(100 * tot_spend / tot_rev, 1) if tot_rev else '–'}% of gross revenue over 28 days." if mer_t else "",
        "kpis": {"gross_revenue_28d": round(tot_rev), "marketing_spend_28d": round(tot_spend), "mer": mer,
                 "spend_pct_of_revenue": round(100 * tot_spend / tot_rev, 1) if tot_rev else None,
                 "blended_cac": round(tot_spend / tot_new, 2) if tot_new else None, "cac_target": cac_t},
        "markets_below_mer_target": [{"market": r["market"], "mer": r["mer"]} for r in econ if _misses(r["mer"], mer_t, mer_d)],
        "biggest_money_at_stake": [{"market": c["market"], "cause": c["cause"], "lost_revenue_28d": c["lost_revenue_28d"]} for c in money[:3]],
        "needs_your_decision": mine("leadership"),
        "last_decisions": done[:5],
    }
    out["roles"]["growth_manager"] = {
        "role": catalog.ROLES["growth_manager"],
        "headline": f"{len(inbox)} decision(s) waiting: " + ", ".join(f"{sum(r['approver_role'] == k for r in inbox)} for {catalog.ROLES[k].lower()}"
                                                                     for k in catalog.ROLES if any(r['approver_role'] == k for r in inbox)),
        "needs_your_decision": mine("growth_manager"),
        "waiting_on_others": [r for r in inbox if r["approver_role"] != "growth_manager"],
        "executed_recently": [d for d in done if d.get("detail")],
    }
    miss = [a for a in ads if _misses(a["cpa"], cpa_t, "max") or _misses(a["roas"], roas_t, "min") or
            (a["platform"] in ("meta", "tiktok") and _misses(a["cpm"], cpm_t, "max"))]
    out["roles"]["channel_manager"] = {
        "role": catalog.ROLES["channel_manager"],
        "headline": f"{len(miss)} of {len(ads)} ads miss a target (CPA ≤ {cpa_t:g}, ROAS ≥ {roas_t:g}, CPM ≤ {cpm_t:g}); {len(fatigue)} show fatigue."
        if cpa_t else "",
        "ads_missing_target": miss[:12], "fatigued_ads": fatigue, "needs_your_decision": mine("channel_manager"),
    }
    out["roles"]["crm_manager"] = {
        "role": catalog.ROLES["crm_manager"],
        "headline": f"{len(products)} product(s) selling well behind their window." if products else "No product is behind its window.",
        "products_behind": products, "email_flows": [w for w in work if w["kind"] == "email_flow"], "needs_your_decision": mine("crm_manager"),
    }
    site = [c for c in whynot if c["cause"] in ("payment_failure", "checkout_friction", "product_page", "cart", "capacity")]
    out["roles"]["product_owner"] = {
        "role": catalog.ROLES["product_owner"],
        "headline": f"{len(site)} site or capacity problem(s) losing buyers; {sum(c.get('lost_revenue_28d') or 0 for c in site):,.0f} revenue at stake over 28 days."
        if site else "No site problem found.",
        "problems": [{k: c[k] for k in ("market", "cause", "lost_revenue_28d", "sources", "evidence")} for c in site],
        "tickets": [w for w in work if w["kind"] == "ticket"], "needs_your_decision": mine("product_owner"),
    }
    for p in pacing:  # straight-line projection to month end
        p["projected_pct"] = round(p["spent_pct"] * 100 / p["month_elapsed_pct"], 1) if p.get("month_elapsed_pct") else None
    over = [p for p in pacing if (p.get("projected_pct") or 0) > 100]
    out["roles"]["finance"] = {
        "role": catalog.ROLES["finance"],
        "headline": f"Spend {round(tot_spend):,} over 28 days at MER {mer}; {len(over)} market(s) projected over budget this month.",
        "budget_pacing": pacing, "market_economics": econ,
        "budget_changes": [d for d in done if d["exec_type"] in ("change_budget", "shift_budget")],
    }
    return out


def reminders(hub: Path, now: datetime | None = None) -> list[dict]:
    """Approvals past their service level: remind the approver; past twice the level, escalate to leadership."""
    now = now or datetime.now()
    out = []
    with store.connect(hub, read_only=True) as db:
        for r in db.execute("SELECT id, action, risk, approver_role, baseline_at FROM recommendations WHERE status = 'proposed'"):
            if not r["baseline_at"]:
                continue
            age = (now - datetime.fromisoformat(r["baseline_at"])) / timedelta(hours=1)
            sla = SLA_HOURS.get(r["risk"], 48)
            if age < sla:
                continue
            esc = age >= 2 * sla and r["approver_role"] != "leadership"
            out.append({"id": r["id"], "action": r["action"], "waiting_hours": round(age), "sla_hours": sla,
                        "to": "leadership" if esc else r["approver_role"], "kind": "escalation" if esc else "reminder"})
    return out


def markdown(b: dict) -> str:
    lines = [f"# Stakeholder briefs · as of {b['as_of']}", "", f"_{b['note']}_", ""]
    for key, r in b["roles"].items():
        lines += [f"## {r['role']}", "", f"**{r.get('headline', '')}**", ""]
        waiting = r.get("needs_your_decision") or []
        if waiting:
            lines.append(f"Waiting for you ({len(waiting)}):")
            lines += [f"- #{w['id']} [{w['risk']}] {w['action']}" for w in waiting]
            lines.append("")
    return "\n".join(lines)
