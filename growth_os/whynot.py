"""Why-not-buy engine: where visitors who came did not buy, why, and what it costs, from every behaviour source.

Four sources, each telling part of the story:
  funnel     (product analytics) which step loses people, per market and device, against the same step elsewhere
  behaviour  (session recordings) rage and dead clicks per page: friction people hit
  survey     (exit survey) what non-buyers say stopped them, against what everyone else says
  capacity   (stock) products that sold out before their end date while people still wanted them

A cause is reported when it is significant after correcting for the number of cells scanned, and sized in money where
the data allows (funnel leaks and sell-outs). Causes only the survey shows are ranked by evidence, not given a fake
euro figure. More sources agreeing means more confidence.
"""
from __future__ import annotations

import sqlite3
from statistics import median

from .agents.analyst.stats import compare_rates

STEPS = ["view_product", "add_to_cart", "begin_checkout", "add_payment", "purchase"]
CAUSE = {("begin_checkout", "add_payment"): "checkout_friction", ("add_payment", "purchase"): "payment_failure",
         ("view_product", "add_to_cart"): "product_page", ("add_to_cart", "begin_checkout"): "cart"}
SURVEY_CAUSE = {"price": "price", "sold_out": "capacity", "trust": "trust", "payment_failed": "payment_failure",
                "delivery_or_date": "delivery_or_date"}
PAGE = {"payment_failure": "/payment", "checkout_friction": "/checkout", "product_page": "/product", "cart": "/cart"}


def _window(db) -> tuple[str, str]:
    d = db.execute("SELECT MAX(day) FROM events_daily").fetchone()[0]
    return db.execute("SELECT date(?, '-27 days')", (d,)).fetchone()[0], d


def funnel_leaks(db: sqlite3.Connection) -> list[dict]:
    s, u = _window(db)
    cells, last_year = {}, {}
    for m, dev, step, n in db.execute("SELECT market, device, step, SUM(users) FROM events_daily WHERE day BETWEEN ? AND ? GROUP BY 1, 2, 3", (s, u)):
        cells.setdefault((m, dev), {})[step] = n or 0
    for m, dev, step, n in db.execute("""SELECT market, device, step, SUM(users) FROM events_daily WHERE day BETWEEN date(?, '-364 days') AND date(?, '-364 days')
                                         GROUP BY 1, 2, 3""", (s, u)):
        last_year.setdefault((m, dev), {})[step] = n or 0
    aov = {r[0]: r[1] for r in db.execute("SELECT market, SUM(revenue) / NULLIF(SUM(orders), 0) FROM sales_daily WHERE day BETWEEN ? AND ? GROUP BY 1", (s, u))}
    out = []
    pairs = list(zip(STEPS, STEPS[1:]))
    scanned = len(cells) * len(pairs)
    for a, b in pairs:
        for dev in {k[1] for k in cells}:
            rates = [c[b] / c[a] for (m, d), c in cells.items() if d == dev and c.get(a)]
            if not rates:
                continue
            med = median(rates)
            for (m, d), c in cells.items():
                if d != dev or not c.get(a):
                    continue
                rate = c[b] / c[a]
                if rate >= med:
                    continue
                ly = last_year.get((m, d), {})
                if ly.get(a) and rate >= 0.95 * ly.get(b, 0) / ly[a]:
                    continue  # this market converts like this every year at this time: seasonal, not a leak
                # the rest of the market's own funnel after this step, to turn lost people at this step into lost orders
                after = c["purchase"] / c[b] if c.get(b) else 0.0
                lost_orders = c[a] * (med - rate) * (after if b != "purchase" else 1.0)
                exp_n = round(c[a] * med)
                v = compare_rates(exp_n, c[a], c[b], c[a], scanned)
                if "different" not in v["verdict"] or lost_orders < 20:
                    continue
                out.append({"market": m, "device": d, "step": f"{a} → {b}", "cause": CAUSE.get((a, b), "funnel"), "rate_pct": round(100 * rate, 1),
                            "typical_pct": round(100 * med, 1), "users": c[a], "lost_orders_28d": round(lost_orders),
                            "lost_revenue_28d": round(lost_orders * (aov.get(m) or 62)), "p_value": v["p_value"]})
    return sorted(out, key=lambda x: -x["lost_revenue_28d"])


def friction(db: sqlite3.Connection) -> dict[tuple[str, str, str], dict]:
    s, u = _window(db)
    rows = db.execute("""SELECT market, device, page, SUM(sessions), SUM(rage_clicks), SUM(dead_clicks) FROM ux_daily WHERE day BETWEEN ? AND ?
                         GROUP BY 1, 2, 3""", (s, u)).fetchall()
    meds = {}
    for _, dev, page, n, rage, _dead in rows:
        meds.setdefault((dev, page), []).append(rage / n if n else 0)
    return {(m, dev, page): {"sessions": n, "rage_per_1000": round(1000 * rage / n, 1) if n else 0,
                             "typical_rage_per_1000": round(1000 * median(meds[(dev, page)]), 1)} for m, dev, page, n, rage, _ in rows}


def survey_signals(db: sqlite3.Connection) -> list[dict]:
    s, u = _window(db)
    tot = {r[0]: r[1] for r in db.execute("SELECT reason, SUM(responses) FROM exit_survey WHERE day BETWEEN ? AND ? GROUP BY 1", (s, u))}
    all_n = sum(tot.values()) or 1
    by_m = {}
    for m, reason, n in db.execute("SELECT market, reason, SUM(responses) FROM exit_survey WHERE day BETWEEN ? AND ? GROUP BY 1, 2", (s, u)):
        by_m.setdefault(m, {})[reason] = n
    scanned = len(by_m) * len(SURVEY_CAUSE)
    out = []
    for m, rs in by_m.items():
        n_m = sum(rs.values())
        for reason in SURVEY_CAUSE:
            k = rs.get(reason, 0)
            base_k, base_n = tot.get(reason, 0) - k, all_n - n_m
            if not base_n or not n_m:
                continue
            v = compare_rates(base_k, base_n, k, n_m, scanned)
            if "different" in v["verdict"] and k / n_m > base_k / base_n:
                top = db.execute("""SELECT e.product_id, p.name, SUM(responses) AS n FROM exit_survey e LEFT JOIN products p USING (product_id)
                                    WHERE e.market = ? AND reason = ? AND day BETWEEN ? AND ? AND e.product_id != '' GROUP BY 1 ORDER BY n DESC LIMIT 1""",
                                 (m, reason, s, u)).fetchone()
                out.append({"market": m, "reason": reason, "cause": SURVEY_CAUSE[reason], "share_pct": round(100 * k / n_m, 1),
                            "elsewhere_pct": round(100 * base_k / base_n, 1), "responses": k, "of": n_m, "p_value": v["p_value"],
                            "top_product": {"product_id": top[0], "name": top[1], "responses": top[2]} if top else None})
    return sorted(out, key=lambda x: -(x["share_pct"] / max(0.1, x["elsewhere_pct"])))


def sellouts(db: sqlite3.Connection) -> list[dict]:
    asof = db.execute("SELECT MAX(day) FROM product_daily").fetchone()[0]
    out = []
    for pid, day in db.execute("SELECT product_id, day FROM stock_events WHERE event = 'sold_out'"):
        p = db.execute("SELECT market, name, end_day, price, capacity FROM products WHERE product_id = ?", (pid,)).fetchone()
        if not p:
            continue
        before = db.execute("""SELECT AVG(units) FROM product_daily WHERE product_id = ? AND day > date(?, '-14 days') AND day <= ?""", (pid, day, day)).fetchone()[0] or 0
        days_out = db.execute("SELECT julianday(MIN(?, ?)) - julianday(?)", (asof, p[2], day)).fetchone()[0]
        days_left = db.execute("SELECT julianday(?) - julianday(?)", (p[2], asof)).fetchone()[0]
        lost = before * days_out
        out.append({"market": p[0], "product_id": pid, "name": p[1], "sold_out_on": day, "end_day": p[2], "capacity": p[4],
                    "days_sold_out": int(days_out), "days_left_on_sale": max(0, int(days_left)), "daily_units_before": round(before, 1),
                    "lost_units_so_far": round(lost), "lost_revenue_so_far": round(lost * p[3]),
                    "at_risk_if_not_restocked": round(before * max(0, days_left) * p[3])})
    return out


def engine(db: sqlite3.Connection) -> list[dict]:
    """Ranked causes, each with the evidence from every source that supports it."""
    if not db.execute("SELECT EXISTS(SELECT 1 FROM events_daily)").fetchone()[0]:
        return []
    fr, sv = friction(db), survey_signals(db)
    causes: dict[tuple[str, str], dict] = {}

    def get(m, cause):
        return causes.setdefault((m, cause), {"market": m, "cause": cause, "evidence": [], "sources": set(), "lost_revenue_28d": None, "segments": []})

    for lk in funnel_leaks(db):
        c = get(lk["market"], lk["cause"])
        c["sources"].add("funnel")
        c["segments"].append(lk["device"])
        c["lost_revenue_28d"] = (c["lost_revenue_28d"] or 0) + lk["lost_revenue_28d"]
        c["evidence"].append(f"funnel: {lk['device']} {lk['step']} {lk['rate_pct']}% vs {lk['typical_pct']}% typical ({lk['users']} users, "
                             f"about {lk['lost_orders_28d']} orders lost in 28 days)")
        page = PAGE.get(lk["cause"])
        f = fr.get((lk["market"], lk["device"], page)) if page else None
        if f and f["rage_per_1000"] > 3 * max(1.0, f["typical_rage_per_1000"]):
            c["sources"].add("behaviour")
            c["evidence"].append(f"behaviour: {f['rage_per_1000']} rage clicks per 1,000 {lk['device']} sessions on {page} vs {f['typical_rage_per_1000']} typical")
    for s in sv:
        c = get(s["market"], s["cause"])
        c["sources"].add("survey")
        prod = f"; most about {s['top_product']['name']} ({s['top_product']['responses']})" if s.get("top_product") and s["cause"] in ("price", "capacity") else ""
        c["evidence"].append(f"survey: '{s['reason']}' {s['share_pct']}% of {s['of']} answers vs {s['elsewhere_pct']}% elsewhere{prod}")
    for so in sellouts(db):
        c = get(so["market"], "capacity")
        c["sources"].add("capacity")
        c["lost_revenue_28d"] = (c["lost_revenue_28d"] or 0) + so["lost_revenue_so_far"]
        c["evidence"].append(f"capacity: {so['name']} sold out on {so['sold_out_on']} with {so['days_left_on_sale']} days still to run; selling about "
                             f"{so['daily_units_before']} a day before, so about {so['lost_units_so_far']} units turned away so far, "
                             f"{so['at_risk_if_not_restocked']} more revenue at risk if not restocked")
    out = []
    for c in causes.values():
        c["sources"] = sorted(c["sources"])
        c["segments"] = sorted(set(c["segments"]))
        c["confidence"] = "high" if len(c["sources"]) >= 2 else "medium"
        out.append(c)
    return sorted(out, key=lambda c: (-(c["lost_revenue_28d"] or 0), -len(c["sources"])))
