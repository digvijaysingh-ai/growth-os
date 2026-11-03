"""Benchmark engine: what "normal" looks like for a market, from the warehouse's own history.

For a market × line and a metric, three comparisons, each with a range:
  last_year   the same weeks a year earlier in the same market (is this seasonal?)
  peers       markets with a similar profile (population, affluence, competition), same line, same weeks
  launches    for a new market, earlier launches at the same number of weeks since opening
plus episodes(): earlier times the same metric moved this much anywhere, and how long it took to recover.

The gap is the market's value minus the benchmark median; it is flagged only when it falls outside the peers' range.
"""
from __future__ import annotations

import math
import sqlite3
from statistics import median

METRICS = {  # name: (SQL expression over the period's rows of v_bench_daily, higher is better)
    "revenue_per_day": ("SUM(revenue) / COUNT(DISTINCT day)", True),
    "mer": ("SUM(revenue) / NULLIF(SUM(spend), 0)", True),
    "cpa": ("SUM(spend) / NULLIF(SUM(paid_orders), 0)", False),
    "checkout_to_order_pct": ("100.0 * SUM(orders) / NULLIF(SUM(checkouts), 0)", True),
    "checkout_to_order_ios_pct": ("100.0 * SUM(ios_orders) / NULLIF(SUM(ios_checkouts), 0)", True),
    "checkout_to_order_android_pct": ("100.0 * SUM(android_orders) / NULLIF(SUM(android_checkouts), 0)", True),
    "checkout_to_order_desktop_pct": ("100.0 * SUM(desktop_orders) / NULLIF(SUM(desktop_checkouts), 0)", True),
    "organic_share_pct": ("100.0 * SUM(organic_revenue) / NULLIF(SUM(revenue), 0)", True),
    "repeat_share_pct": ("100.0 * SUM(owned_revenue) / NULLIF(SUM(revenue), 0)", True),
    "paid_share_pct": ("100.0 * SUM(paid_revenue) / NULLIF(SUM(revenue), 0)", False),
}
VIEW = """CREATE TEMP VIEW IF NOT EXISTS v_bench_daily AS
SELECT s.day, s.market, s.line, s.revenue, s.orders, s.checkouts, s.paid_orders, s.organic_revenue, s.owned_revenue, s.paid_revenue,
       s.ios_orders, s.ios_checkouts, s.android_orders, s.android_checkouts, s.desktop_orders, s.desktop_checkouts, COALESCE(a.spend, 0) AS spend
FROM (SELECT day, market, line, SUM(revenue) AS revenue, SUM(orders) AS orders, SUM(checkouts) AS checkouts,
             SUM(CASE WHEN channel LIKE 'paid:%' THEN orders ELSE 0 END) AS paid_orders,
             SUM(CASE WHEN channel IN ('organic_search', 'organic_social', 'direct', 'organic') THEN revenue ELSE 0 END) AS organic_revenue,
             SUM(CASE WHEN channel IN ('email', 'sms') THEN revenue ELSE 0 END) AS owned_revenue,
             SUM(CASE WHEN channel LIKE 'paid:%' THEN revenue ELSE 0 END) AS paid_revenue,
             SUM(CASE WHEN device = 'ios' THEN orders ELSE 0 END) AS ios_orders, SUM(CASE WHEN device = 'ios' THEN checkouts ELSE 0 END) AS ios_checkouts,
             SUM(CASE WHEN device = 'android' THEN orders ELSE 0 END) AS android_orders, SUM(CASE WHEN device = 'android' THEN checkouts ELSE 0 END) AS android_checkouts,
             SUM(CASE WHEN device = 'desktop' THEN orders ELSE 0 END) AS desktop_orders, SUM(CASE WHEN device = 'desktop' THEN checkouts ELSE 0 END) AS desktop_checkouts
      FROM sales_daily GROUP BY 1, 2, 3) s
LEFT JOIN (SELECT day, market, line, SUM(spend) AS spend FROM ad_daily GROUP BY 1, 2, 3) a USING (day, market, line)"""


def _val(db, metric: str, market: str, line: str | None, lo: str, hi: str) -> float | None:
    expr, _ = METRICS[metric]
    q = f"SELECT {expr} FROM v_bench_daily WHERE market = ? AND day BETWEEN ? AND ?" + (" AND line = ?" if line else "")
    r = db.execute(q, (market, lo, hi, *([line] if line else []))).fetchone()
    return round(r[0], 2) if r and r[0] is not None else None


def peers_of(db, market: str, k: int = 4) -> list[str]:
    prof = {r[0]: r[1:] for r in db.execute("SELECT market, pop_m, affluence, competition, launched_on FROM market_profile")}
    if market not in prof:
        return []
    p = prof[market]
    dist = sorted((math.dist((math.log(p[0]), p[1] * 2, p[2] * 2), (math.log(q[0]), q[1] * 2, q[2] * 2)), m)
                  for m, q in prof.items() if m != market and not q[3])
    return [m for _, m in dist[:k]]


def benchmark(db: sqlite3.Connection, market: str, metric: str, line: str | None = None, days: int = 28) -> dict:
    db.execute(VIEW)
    asof = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
    lo = db.execute("SELECT date(?, ?)", (asof, f"-{days - 1} days")).fetchone()[0]
    ly_lo, ly_hi = (db.execute("SELECT date(?, '-364 days')", (x,)).fetchone()[0] for x in (lo, asof))
    prev_lo, prev_hi = (db.execute("SELECT date(?, ?)", (x, f"-{days} days")).fetchone()[0] for x in (lo, asof))
    now = _val(db, metric, market, line, lo, asof)
    out = {"market": market, "line": line or "all lines", "metric": metric, "period": [lo, asof], "value": now,
           "previous_period": _val(db, metric, market, line, prev_lo, prev_hi), "same_period_last_year": _val(db, metric, market, line, ly_lo, ly_hi)}
    peers = peers_of(db, market)
    pv = {m: _val(db, metric, m, line, lo, asof) for m in peers}
    pv = {m: v for m, v in pv.items() if v is not None}
    if pv:
        vals = sorted(pv.values())
        core = vals[1:-1] if len(vals) >= 4 else vals  # the middle peers: one broken or unusual peer does not stretch "normal"
        out["peers"] = pv
        out["peer_median"] = round(median(vals), 2)
        out["peer_range"] = [core[0], core[-1]]
        higher_better = METRICS[metric][1]
        if now is not None:
            out["gap_vs_peers"] = round(now - out["peer_median"], 2)
            out["outside_peer_range"] = (now < core[0] - 0.1 * abs(core[0])) if higher_better else (now > core[-1] + 0.1 * abs(core[-1]))
    launched = db.execute("SELECT launched_on FROM market_profile WHERE market = ?", (market,)).fetchone()
    if launched and launched[0]:
        out["launch"] = launches(db, market, line)
    return out


def launches(db: sqlite3.Connection, market: str, line: str | None = None) -> dict:
    """Revenue per day by week since opening, against earlier launches at the same age."""
    q = """SELECT p.market, CAST((julianday(s.day) - julianday(p.launched_on)) / 7 AS INTEGER) AS wk, SUM(s.revenue) / 7.0
           FROM sales_daily s JOIN market_profile p USING (market) WHERE p.launched_on IS NOT NULL AND s.day >= p.launched_on""" + \
        (" AND s.line = ?" if line else "") + " GROUP BY 1, 2"
    curves: dict = {}
    for m, wk, v in db.execute(q, (line,) if line else ()):
        curves.setdefault(m, {})[wk] = round(v)
    mine = curves.get(market, {})
    age = max(mine) if mine else 0
    others = {m: c.get(age) for m, c in curves.items() if m != market and c.get(age)}
    return {"weeks_since_launch": age, "revenue_per_day_now": mine.get(age), "earlier_launches_same_age": others,
            "share_of_earlier_median_pct": round(100 * mine.get(age, 0) / median(others.values()), 0) if others and mine.get(age) else None}


def episodes(db: sqlite3.Connection, metric: str, drop_pct: float = 15.0) -> list[dict]:
    """Earlier weeks, in any market, where the metric fell by at least `drop_pct` against the 4 weeks before, and how
    many weeks it took to get back: what history says about how long such a drop lasts."""
    db.execute(VIEW)
    expr, _ = METRICS[metric]
    rows = db.execute(f"""SELECT market, date(day, 'weekday 0', '-6 days') AS week, {expr} FROM v_bench_daily GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    series: dict = {}
    for m, w, v in rows:
        if v is not None:
            series.setdefault(m, []).append((w, v))
    out = []
    for m, s in series.items():
        i = 4
        while i < len(s) - 1:
            base = sum(v for _, v in s[i - 4:i]) / 4
            if base and (s[i][1] - base) / base * 100 <= -drop_pct:
                rec = next((j - i for j in range(i + 1, len(s)) if s[j][1] >= 0.95 * base), None)
                out.append({"market": m, "week": s[i][0], "drop_pct": round((s[i][1] - base) / base * 100, 1), "weeks_to_recover": rec})
                i += (rec or 1) + 1
            else:
                i += 1
    return out
