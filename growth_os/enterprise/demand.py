"""Demand engine: how much demand a market has, how much of it the brand captures, and what the weather will do to it.

  potential(db)     captured share = brand orders / category search interest (people looking for the category, from
                    anyone). Each market × line is compared with the median of its peers for the same line, adjusted for
                    affluence and competition (macro). The gap, in orders and revenue, is demand the brand is not
                    reaching: an awareness or budget problem, not a conversion problem.
  sensitivity(db)   per market × line, how daily orders move with rain, heat and public holidays (real weather and
                    holidays), from a regression with week fixed effects, so season and spend do not leak in.
  outlook(db, fc)   the next 14 days from the real weather forecast: expected uplift per market × line against a normal
                    day, and where a weather-triggered budget rule would pay.
  accuracy(db)      fits on all but the last 8 weeks and predicts those 8 from search interest: the error is reported,
                    so nobody trusts the engine more than it deserves.
"""
from __future__ import annotations

import math
import sqlite3
from statistics import median

from .mix import _solve


def potential(db: sqlite3.Connection, weeks: int = 8) -> list[dict]:
    asof = db.execute("SELECT MAX(week) FROM search_interest").fetchone()[0]
    rows = db.execute(f"""WITH s AS (SELECT market, line, SUM(searches) AS searches FROM search_interest WHERE week > date(?, '-{7 * weeks} days') GROUP BY 1, 2),
                               o AS (SELECT market, line, SUM(orders) AS orders, SUM(revenue) AS revenue FROM sales_daily
                                     WHERE day > date(?, '-{7 * weeks} days') AND day <= date(?, '+6 days') GROUP BY 1, 2)
                          SELECT s.market, s.line, s.searches, o.orders, o.revenue, p.affluence, p.competition, p.launched_on
                          FROM s JOIN o USING (market, line) JOIN market_profile p USING (market)""", (asof, asof, asof)).fetchall()
    by_line: dict[str, list] = {}
    for m, l, srch, orders, rev, aff, comp, launched in rows:
        rate = orders / srch if srch else 0
        adj = rate / (aff ** 0.3) * (comp ** 0.3)  # what this market would capture with a typical profile
        by_line.setdefault(l, []).append((m, l, srch, orders, rev, rate, adj, aff, comp, launched))
    out = []
    for l, cells in by_line.items():
        peer = median(c[6] for c in cells)
        for m, _l, srch, orders, rev, rate, adj, aff, comp, launched in cells:
            expected = peer * (aff ** 0.3) / (comp ** 0.3) * srch
            gap = expected - orders
            aov = rev / orders if orders else 0
            out.append({"market": m, "line": l, "category_searches": srch, "orders": orders, "capture_per_1000_searches": round(1000 * rate, 2),
                        "peer_capture_per_1000": round(1000 * peer * (aff ** 0.3) / (comp ** 0.3), 2),
                        "captured_share_of_potential_pct": round(100 * orders / expected, 0) if expected else None,
                        "gap_orders": round(gap), "gap_revenue": round(gap * aov), "weeks": weeks, "new_market": bool(launched)})
    return sorted(out, key=lambda r: -r["gap_revenue"])


def _daily(db, market: str, line: str):
    return db.execute("""SELECT s.day, SUM(s.orders) AS orders, w.temp_c, w.precip_mm,
                                EXISTS(SELECT 1 FROM holidays h JOIN market_profile p ON h.country = p.country WHERE p.market = s.market AND h.day = s.day) AS hol,
                                date(s.day, 'weekday 0', '-6 days') AS week, CAST(strftime('%w', s.day) AS INTEGER) AS dow
                         FROM sales_daily s JOIN weather_daily w ON w.day = s.day AND w.market = s.market
                         WHERE s.market = ? AND s.line = ? GROUP BY s.day ORDER BY s.day""", (market, line)).fetchall()


def sensitivity(db: sqlite3.Connection, market: str, line: str) -> dict | None:
    rows = [r for r in _daily(db, market, line) if r[1] > 0]
    if len(rows) < 120:
        return None
    weeks: dict[str, list] = {}
    for r in rows:
        weeks.setdefault(r[5], []).append(r)
    x, y = [], []
    for wk in weeks.values():
        if len(wk) < 5:
            continue
        feats = [[1.0 if (r[3] or 0) >= 2 else (r[3] or 0) / 2, max(0.0, ((r[2] or 15) - 24) / 8), float(r[4]), 1.0 if r[6] in (0, 6) else 0.0] for r in wk]
        ys = [math.log(r[1]) for r in wk]
        mf = [sum(c) / len(c) for c in zip(*feats)]
        my = sum(ys) / len(ys)
        x += [[0.0] + [f - m for f, m in zip(row, mf)] for row in feats]
        y += [v - my for v in ys]
    b = _solve(x, y)[1:]
    resid = [yy - sum(a * c for a, c in zip(row[1:], b)) for row, yy in zip(x, y)]
    sd = math.sqrt(sum(e * e for e in resid) / max(1, len(resid) - 5))
    n_rain = sum(1 for r in x if r[1] > 0.3)
    se_rain = sd / math.sqrt(max(1, n_rain) * 0.5)
    return {"market": market, "line": line, "days": len(y), "rain_effect_pct": round(100 * (math.exp(b[0]) - 1), 1),
            "rain_effect_range_pct": [round(100 * (math.exp(b[0] - 1.96 * se_rain) - 1), 1), round(100 * (math.exp(b[0] + 1.96 * se_rain) - 1), 1)],
            "heat_effect_pct_per_8c": round(100 * (math.exp(b[1]) - 1), 1), "holiday_effect_pct": round(100 * (math.exp(b[2]) - 1), 1),
            "weekend_effect_pct": round(100 * (math.exp(b[3]) - 1), 1)}


def outlook(db: sqlite3.Connection, forecast: dict, sens: list[dict], days: int = 14) -> list[dict]:
    """Expected weather uplift over the next `days` per market × line, from the forecast and fitted sensitivity."""
    asof = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
    base = {(r[0], r[1]): r[2] for r in db.execute("""SELECT market, line, SUM(revenue) / 28.0 FROM sales_daily WHERE day > date(?, '-28 days')
                                                       GROUP BY 1, 2""", (asof,))}
    out = []
    for s in sens:
        fc = sorted((d, v) for d, v in forecast.get(s["market"], {}).items() if d > asof)[:days]
        if not fc:
            continue
        rainy = sum(1 for _, (_t, p) in fc if p >= 2.0)
        lift = sum((s["rain_effect_pct"] / 100) * (1.0 if p >= 2 else p / 2) + (s["heat_effect_pct_per_8c"] / 100) * max(0.0, (t - 24) / 8) for _, (t, p) in fc) / len(fc)
        out.append({"market": s["market"], "line": s["line"], "forecast_days": len(fc), "rainy_days": rainy, "first_day": fc[0][0], "last_day": fc[-1][0],
                    "expected_uplift_pct": round(100 * lift, 1), "expected_extra_revenue": round(lift * base.get((s["market"], s["line"]), 0) * len(fc)),
                    "rain_sensitive": s["rain_effect_range_pct"][0] > 5})
    return sorted(out, key=lambda r: -r["expected_extra_revenue"])


def accuracy(db: sqlite3.Connection, holdout_weeks: int = 8) -> dict:
    """Weekly orders per market × line predicted from category search interest, trained on earlier weeks only."""
    rows = db.execute("""SELECT q.week, q.market, q.line, q.searches, SUM(s.orders) FROM search_interest q JOIN sales_daily s
                         ON s.market = q.market AND s.line = q.line AND date(s.day, 'weekday 0', '-6 days') = q.week
                         GROUP BY 1, 2, 3 HAVING COUNT(DISTINCT s.day) = 7 ORDER BY q.week""").fetchall()
    weeks = sorted({r[0] for r in rows})
    cut = weeks[-holdout_weeks]
    errs = []
    cells: dict = {}
    for w, m, l, srch, o in rows:
        cells.setdefault((m, l), []).append((w, srch, o))
    for data in cells.values():
        train = [(math.log(s), math.log(o)) for w, s, o in data if w < cut and o > 0 and s > 0]
        test = [(s, o) for w, s, o in data if w >= cut and o > 0 and s > 0]
        if len(train) < 10 or not test:
            continue
        b = _solve([[1.0, x] for x, _ in train], [y for _, y in train])
        errs += [abs(math.exp(b[0] + b[1] * math.log(s)) - o) / o for s, o in test]
    return {"holdout_weeks": holdout_weeks, "cells": len(cells), "predictions": len(errs),
            "mape_pct": round(100 * sum(errs) / len(errs), 1) if errs else None,
            "within_10pct_share": round(100 * sum(e <= 0.10 for e in errs) / len(errs), 0) if errs else None}
