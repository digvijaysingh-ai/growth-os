"""Budget and channel-mix engine: what each channel adds, where the next euro earns most, and a better split.

For every market × product line it fits a log-log marketing-mix model on weekly data:

    log(revenue) = a + Σ_c b_c · log(spend_c + 1) + g · log(category search interest) + seasonality

b_c is the revenue elasticity of channel c; its marginal ROAS at current spend is b_c · revenue / spend_c. Because
budgets moved week to week, the fit can separate channels. Search interest absorbs demand that comes from the market
itself (season, weather, holidays), so paid channels are not credited with it.

The reallocation keeps each line's total budget and moves money toward higher marginal ROAS: under this model the
best split puts spend in proportion to b_c, and each move is capped (±50% of a channel per quarter) so nothing is
changed blindly. A second pass ranks market × line budgets by marginal return for leadership-level moves.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict

from .profile import PAID

MAX_MOVE = 0.5


def _solve(x: list[list[float]], y: list[float], ridge: float = 1e-3) -> list[float]:
    """Least squares with a little ridge, by normal equations and Gaussian elimination (no numpy needed)."""
    k = len(x[0])
    a = [[sum(r[i] * r[j] for r in x) + (ridge if i == j and i > 0 else 0.0) for j in range(k)] for i in range(k)]
    b = [sum(r[i] * yy for r, yy in zip(x, y)) for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(a[r][i]))
        a[i], a[p], b[i], b[p] = a[p], a[i], b[p], b[i]
        if abs(a[i][i]) < 1e-12:
            continue
        for r in range(i + 1, k):
            f = a[r][i] / a[i][i]
            for c in range(i, k):
                a[r][c] -= f * a[i][c]
            b[r] -= f * b[i]
    sol = [0.0] * k
    for i in range(k - 1, -1, -1):
        sol[i] = (b[i] - sum(a[i][c] * sol[c] for c in range(i + 1, k))) / a[i][i] if abs(a[i][i]) > 1e-12 else 0.0
    return sol


def _weekly(db: sqlite3.Connection, market: str, line: str, weeks: int = 60) -> list[dict]:
    rows = db.execute("""WITH s AS (SELECT date(day, 'weekday 0', '-6 days') AS week, SUM(revenue) AS revenue, COUNT(DISTINCT day) AS days FROM sales_daily
                                    WHERE market = ? AND line = ? GROUP BY 1),
                              a AS (SELECT date(day, 'weekday 0', '-6 days') AS week, creative AS channel, SUM(spend) AS spend FROM ad_daily
                                    WHERE market = ? AND line = ? GROUP BY 1, 2),
                              q AS (SELECT week, searches FROM search_interest WHERE market = ? AND line = ?)
                         SELECT s.week, s.revenue, s.days, a.channel, a.spend, q.searches FROM s JOIN a USING (week) LEFT JOIN q USING (week)
                         ORDER BY s.week""", (market, line, market, line, market, line)).fetchall()
    by: dict[str, dict] = {}
    for w, rev, days, ch, sp, srch in rows:
        if days < 7:
            continue
        r = by.setdefault(w, {"week": w, "revenue": rev, "searches": srch or 0, "spend": {}})
        r["spend"][ch] = sp
    return list(by.values())[-weeks:]


def _design(data: list[dict], chans: list[str]) -> tuple[list[list[float]], list[float]]:
    x = [[math.log(r["searches"])] + [math.log(r["spend"].get(c, 0) + 1) for c in chans] for r in data]
    y = [math.log(r["revenue"]) for r in data]
    return x, y


def _demean(x, y):
    mx = [sum(col) / len(col) for col in zip(*x)]
    my = sum(y) / len(y)
    return [[v - m for v, m in zip(row, mx)] for row in x], [v - my for v in y]


def fit_all(db: sqlite3.Connection, markets: list[str], lines: list[str], shrink: float = 25.0) -> list[dict]:
    """Two stages. (1) Pooled: one elasticity per channel across every market and line, with fixed effects per market
    × line. (2) Per market × line: its own elasticities, pulled toward the pooled ones (ridge toward the prior), so a
    market's own data moves the estimate only as far as it can support."""
    cells = {}
    for m in markets:
        for l in lines:
            data = [r for r in _weekly(db, m, l) if r["searches"] and r["revenue"] > 0]
            if len(data) >= 16:
                cells[(m, l)] = data
    chans = list(PAID)
    X, Y = [], []
    for data in cells.values():
        x, y = _design(data, chans)
        x, y = _demean(x, y)
        X += x
        Y += y
    pooled = _solve([[0.0] + r for r in X], Y)[1:]  # leading zero column keeps _solve's no-ridge intercept slot unused
    out = []
    for (m, l), data in cells.items():
        x, y = _design(data, chans)
        x, y = _demean(x, y)
        lam = math.sqrt(shrink)
        xa = [[0.0] + r for r in x] + [[0.0] + [lam if j == i else 0.0 for j in range(len(pooled))] for i in range(len(pooled))]
        ya = y + [lam * b for b in pooled]
        coef = _solve(xa, ya, ridge=0.0)[1:]
        pred = [sum(a * b for a, b in zip(row, coef)) for row in x]
        ss = sum((a - b) ** 2 for a, b in zip(y, pred))
        r2 = 1 - ss / max(1e-9, sum(v * v for v in y))
        recent = data[-4:]
        rev = sum(r["revenue"] for r in recent) / len(recent)
        f = {"market": m, "line": l, "weeks": len(data), "r2": round(r2, 3), "weekly_revenue": round(rev), "search_elasticity": round(coef[0], 3), "channels": {}}
        for c, b in zip(chans, coef[1:]):
            sp = sum(r["spend"].get(c, 0) for r in recent) / len(recent)
            b = max(0.0, b)  # a negative fit means "no measurable effect", not that the channel destroys revenue
            f["channels"][c] = {"elasticity": round(b, 4), "pooled_elasticity": round(max(0.0, pooled[chans.index(c)]), 4), "weekly_spend": round(sp),
                                "marginal_roas": round(b * rev / sp, 2) if sp > 0 else None}
        out.append(f)
    return out


def fit(db: sqlite3.Connection, market: str, line: str) -> dict | None:
    from .profile import LINES, MARKETS
    return next((f for f in fit_all(db, list(MARKETS), list(LINES)) if f["market"] == market and f["line"] == line), None)


def plan(db: sqlite3.Connection, fits: list[dict]) -> list[dict]:
    """Within-line reallocation: same total, spend toward elasticity, each channel moved at most ±50%."""
    out = []
    for f in fits:
        ch = f["channels"]
        total = sum(v["weekly_spend"] for v in ch.values())
        wsum = sum(v["elasticity"] for v in ch.values())
        if not total or not wsum:
            continue
        target = {c: total * v["elasticity"] / wsum for c, v in ch.items()}
        new = {c: min(v["weekly_spend"] * (1 + MAX_MOVE), max(v["weekly_spend"] * (1 - MAX_MOVE), target[c])) for c, v in ch.items()}
        scale = total / sum(new.values())  # keep the total exactly
        new = {c: s * scale for c, s in new.items()}
        gain = sum(v["elasticity"] * math.log((new[c] + 1) / (v["weekly_spend"] + 1)) for c, v in ch.items())
        moves = sorted(({"channel": c, "from": v["weekly_spend"], "to": round(new[c]), "change_pct": round(100 * (new[c] / v["weekly_spend"] - 1), 0) if v["weekly_spend"] else None,
                         "marginal_roas": v["marginal_roas"]} for c, v in ch.items()), key=lambda m: m["change_pct"] or 0)
        out.append({"market": f["market"], "line": f["line"], "weekly_budget": round(total), "model_r2": f["r2"],
                    "expected_revenue_change_pct": round(100 * (math.exp(gain) - 1), 1),
                    "expected_weekly_revenue_gain": round(f["weekly_revenue"] * (math.exp(gain) - 1)), "moves": moves})
    return sorted(out, key=lambda p: -p["expected_weekly_revenue_gain"])


def line_returns(fits: list[dict]) -> list[dict]:
    """Marginal return of one more euro in each market × line (spend-weighted across its channels): where leadership
    should add or take budget."""
    out = []
    for f in fits:
        ch = [v for v in f["channels"].values() if v["marginal_roas"] is not None]
        sp = sum(v["weekly_spend"] for v in ch)
        if not sp:
            continue
        best = max(ch, key=lambda v: v["marginal_roas"])
        out.append({"market": f["market"], "line": f["line"], "weekly_spend": sp,
                    "blended_marginal_roas": round(sum(v["marginal_roas"] * v["weekly_spend"] for v in ch) / sp, 2),
                    "best_channel": next(c for c, v in f["channels"].items() if v is best), "best_marginal_roas": best["marginal_roas"]})
    return sorted(out, key=lambda r: -r["blended_marginal_roas"])


def organic_vs_paid(db: sqlite3.Connection, days: int = 28) -> list[dict]:
    """Revenue by organic, owned and paid per market, last `days` vs the same days before and last year."""
    asof = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
    q = """SELECT market, CASE WHEN channel LIKE 'paid:%' THEN 'paid' WHEN channel IN ('email', 'sms') THEN 'owned' ELSE 'organic' END AS kind,
                  SUM(revenue) FROM sales_daily WHERE day > date(?, ?) AND day <= date(?, ?) GROUP BY 1, 2"""
    def grab(lo, hi):
        d = defaultdict(dict)
        for m, k, v in db.execute(q, (asof, f"-{lo} days", asof, f"-{hi} days")):
            d[m][k] = v
        return d
    now, before, ly = grab(days, 0), grab(2 * days, days), grab(364 + days, 364)
    spend = {r[0]: r[1] for r in db.execute("SELECT market, SUM(spend) FROM ad_daily WHERE day > date(?, ?) GROUP BY 1", (asof, f"-{days} days"))}
    spend_b = {r[0]: r[1] for r in db.execute("SELECT market, SUM(spend) FROM ad_daily WHERE day > date(?, ?) AND day <= date(?, ?) GROUP BY 1",
                                               (asof, f"-{2 * days} days", asof, f"-{days} days"))}
    out = []
    for m, k in now.items():
        tot = sum(k.values())
        b = before.get(m, {})
        out.append({"market": m, "revenue": round(tot), "organic_pct": round(100 * k.get("organic", 0) / tot, 1), "owned_pct": round(100 * k.get("owned", 0) / tot, 1),
                    "paid_pct": round(100 * k.get("paid", 0) / tot, 1),
                    "organic_change_pct": round(100 * (k.get("organic", 0) / b["organic"] - 1), 1) if b.get("organic") else None,
                    "paid_change_pct": round(100 * (k.get("paid", 0) / b["paid"] - 1), 1) if b.get("paid") else None,
                    "spend_change_pct": round(100 * (spend.get(m, 0) / spend_b[m] - 1), 1) if spend_b.get(m) else None,
                    "organic_vs_last_year_pct": round(100 * (k.get("organic", 0) / ly[m]["organic"] - 1), 1) if ly.get(m, {}).get("organic") else None,
                    "mer": round(tot / spend[m], 2) if spend.get(m) else None})
    return sorted(out, key=lambda r: r["organic_change_pct"] or 0)
