"""One tool layer for every agent (and for any MCP client): read-only engines over the hub.

Each tool is a name, a description, a strict JSON schema and a function of (db, args) returning JSON-able data. The
agent team gets role-scoped subsets; growth_os.mcp_server serves the same registry over MCP.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Callable

from ..agents.analyst.analyst import run_sql as _run_sql
from ..agents.analyst.stats import compare_rates as _compare
from . import benchmarks, demand, external, mix, voc
from .profile import LINES, MARKETS

MAX_CHARS = 18000


@dataclass
class Tool:
    name: str
    description: str
    props: dict
    fn: Callable

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "strict": True,
                "input_schema": {"type": "object", "properties": self.props, "required": list(self.props), "additionalProperties": False}}


S = {"type": "string"}
I = {"type": "integer"}
MK = {"type": "string", "enum": list(MARKETS)}
LN = {"type": "string", "enum": list(LINES) + ["all"]}
_cache: dict = {}


def _fits(db):
    key = ("fits", id(db))
    if key not in _cache:
        _cache[key] = mix.fit_all(db, list(MARKETS), list(LINES))
    return _cache[key]


def _sens(db):
    key = ("sens", id(db))
    if key not in _cache:
        _cache[key] = [s for m in MARKETS for l in LINES if (s := demand.sensitivity(db, m, l))]
    return _cache[key]


def _line(a):
    return None if a.get("line") in (None, "", "all") else a["line"]


def _forecast(db):
    asof = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
    try:
        return external.forecast(date.fromisoformat(asof).fromordinal(date.fromisoformat(asof).toordinal() + 1))
    except Exception:
        return external.forecast(date.today())


REGISTRY: dict[str, Tool] = {t.name: t for t in [
    Tool("run_sql", "One read-only SQLite SELECT over the hub (tables: sales_daily, ad_daily, budget_plan, budgets, market_profile, weather_daily, "
                    "holidays, search_interest, products, product_daily, stock_events, voc_items, voc_labels, targets; views: v_channel_weekly, "
                    "v_market_weekly, v_budget_pacing, v_product_pacing). Up to 200 rows.",
         {"sql": S}, lambda db, a: json.loads(_run_sql(db, a["sql"]))),
    Tool("compare_rates", "Two-proportion z-test of rate B against baseline A, Bonferroni-corrected for `comparisons` segments scanned.",
         {"label": S, "a_successes": I, "a_n": I, "b_successes": I, "b_n": I, "comparisons": I},
         lambda db, a: {"label": a["label"], **_compare(a["a_successes"], a["a_n"], a["b_successes"], a["b_n"], max(1, a["comparisons"]))}),
    # benchmarks
    Tool("benchmark", "Compare a market's metric over the last `days` with the same period last year, the previous period, peer markets "
                      "of similar profile (with range) and, for new markets, earlier launches at the same age. Metrics: " + ", ".join(benchmarks.METRICS),
         {"market": MK, "metric": {"type": "string", "enum": list(benchmarks.METRICS)}, "line": LN, "days": I},
         lambda db, a: benchmarks.benchmark(db, a["market"], a["metric"], _line(a), max(7, a["days"]))),
    Tool("scan_benchmarks", "Run one metric for every market and return only those outside their peers' range or far from last year.",
         {"metric": {"type": "string", "enum": list(benchmarks.METRICS)}, "days": I},
         lambda db, a: [r for r in (benchmarks.benchmark(db, m, a["metric"], None, max(7, a["days"])) for m in MARKETS)
                        if r.get("outside_peer_range") or (r.get("same_period_last_year") and r.get("value") and
                                                           abs(r["value"] / r["same_period_last_year"] - 1) > 0.15)]),
    Tool("past_episodes", "Earlier weeks in any market where a metric fell by at least drop_pct against the 4 weeks before, and weeks to recover.",
         {"metric": {"type": "string", "enum": list(benchmarks.METRICS)}, "drop_pct": I},
         lambda db, a: benchmarks.episodes(db, a["metric"], a["drop_pct"])[:40]),
    # demand
    Tool("demand_potential", "Captured share of potential demand per market × line: brand orders against category search interest, vs peers "
                             "adjusted for affluence and competition; gap in orders and revenue over the last 8 weeks.",
         {}, lambda db, a: demand.potential(db)),
    Tool("weather_sensitivity", "How daily orders move with rain, heat, public holidays and weekends per market × line (real weather), with a "
                                "95% range for the rain effect. Filter by market and/or line ('all' for every).",
         {"market": {"type": "string", "enum": list(MARKETS) + ["all"]}, "line": LN},
         lambda db, a: [s for s in _sens(db) if a["market"] in ("all", s["market"]) and a["line"] in ("all", s["line"])]),
    Tool("demand_outlook", "Next 14 days from the real weather forecast: expected uplift and extra revenue per market × line.",
         {}, lambda db, a: demand.outlook(db, _forecast(db), _sens(db))[:24]),
    Tool("demand_model_accuracy", "Holdout accuracy of the demand model (MAPE on the last 8 weeks, never used for fitting).",
         {}, lambda db, a: demand.accuracy(db)),
    # voice of customer
    Tool("voc_gaps", "Customer-comment themes over-represented in a market or market × line in the last 28 days vs everywhere else "
                     "(significance corrected), whether new vs before, and the market's NPS.",
         {}, lambda db, a: voc.gaps(db)[:30]),
    Tool("voc_examples", "English summaries of customer comments (labelled by Claude) for a market, line and theme: what people actually say.",
         {"market": MK, "line": LN, "theme": {"type": "string", "enum": list(voc.THEMES)}},
         lambda db, a: [r[0] for r in db.execute(
             "SELECT l.summary FROM voc_items v JOIN voc_labels l USING (item_id) WHERE v.market = ? AND l.theme = ?" +
             (" AND v.line = ?" if _line(a) else "") + " ORDER BY v.day DESC LIMIT 12",
             (a["market"], a["theme"], *([a["line"]] if _line(a) else [])))]),
    Tool("nps_by_market", "NPS per market, last 28 days vs the 28 before.",
         {}, lambda db, a: [dict(zip(("market", "nps_now", "nps_before", "answers"), r)) for r in db.execute(
             """WITH x AS (SELECT MAX(day) d FROM voc_items) SELECT market,
                ROUND(100.0*(SUM(day > date(d,'-28 days') AND score >= 9) - SUM(day > date(d,'-28 days') AND score <= 6)) / NULLIF(SUM(day > date(d,'-28 days')),0)),
                ROUND(100.0*(SUM(day <= date(d,'-28 days') AND day > date(d,'-56 days') AND score >= 9) - SUM(day <= date(d,'-28 days') AND day > date(d,'-56 days') AND score <= 6))
                      / NULLIF(SUM(day <= date(d,'-28 days') AND day > date(d,'-56 days')),0)),
                SUM(day > date(d,'-28 days')) FROM voc_items, x WHERE source = 'nps' GROUP BY market ORDER BY 2""")]),
    # media and budget
    Tool("channel_response", "Marketing-mix model per market × line: each paid channel's revenue elasticity, weekly spend and marginal ROAS "
                             "(revenue from the next euro), plus model fit (r2). Filter by market and/or line.",
         {"market": {"type": "string", "enum": list(MARKETS) + ["all"]}, "line": LN},
         lambda db, a: [f for f in _fits(db) if a["market"] in ("all", f["market"]) and a["line"] in ("all", f["line"])]),
    Tool("reallocation_plan", "Within each market × line, a channel split that keeps the total and moves spend toward higher marginal ROAS "
                              "(each channel ±50% max), with the model's expected weekly revenue gain. Top `limit` by gain.",
         {"limit": I}, lambda db, a: mix.plan(db, _fits(db))[:max(1, a["limit"])]),
    Tool("line_marginal_returns", "Where one more euro earns most: blended marginal ROAS per market × line (for moving budget between lines/markets).",
         {}, lambda db, a: mix.line_returns(_fits(db))),
    Tool("organic_vs_paid", "Revenue split organic / owned (email, SMS) / paid per market, last 28 days vs before and last year, with spend change and MER.",
         {}, lambda db, a: mix.organic_vs_paid(db)),
    Tool("platform_vs_first_party", "Per channel, last 28 days: spend, first-party last-click revenue and orders, and what the platform claims.",
         {}, lambda db, a: [dict(zip(("channel", "spend", "first_party_revenue", "platform_claimed_revenue", "first_party_roas", "platform_roas"), r))
                            for r in db.execute("""WITH x AS (SELECT MAX(day) d FROM ad_daily),
                                a AS (SELECT creative c, SUM(spend) sp, SUM(platform_revenue) pr FROM ad_daily, x WHERE day > date(d, '-28 days') GROUP BY 1),
                                s AS (SELECT replace(channel, 'paid:', '') c, SUM(revenue) r FROM sales_daily, x WHERE day > date(d, '-28 days') AND channel LIKE 'paid:%' GROUP BY 1)
                                SELECT a.c, ROUND(sp), ROUND(r), ROUND(pr), ROUND(r / sp, 2), ROUND(pr / sp, 2) FROM a JOIN s USING (c) ORDER BY sp DESC""")]),
    Tool("budget_pacing", "This month's spend against budget per market, with straight-line projection to month end.",
         {}, lambda db, a: [dict(r) | {"projected_pct": round(r["spent_pct"] * 100 / r["month_elapsed_pct"], 1) if r["month_elapsed_pct"] else None}
                            for r in db.execute("SELECT * FROM v_budget_pacing")]),
]}

ROLES_TOOLS = {
    "benchmark_analyst": ["run_sql", "compare_rates", "benchmark", "scan_benchmarks", "past_episodes"],
    "demand_strategist": ["run_sql", "demand_potential", "weather_sensitivity", "demand_outlook", "demand_model_accuracy", "benchmark", "line_marginal_returns"],
    "customer_voice_analyst": ["run_sql", "compare_rates", "voc_gaps", "voc_examples", "nps_by_market", "benchmark"],
    "media_budget_planner": ["run_sql", "channel_response", "reallocation_plan", "line_marginal_returns", "organic_vs_paid", "platform_vs_first_party",
                             "budget_pacing"],
}


def call(db: sqlite3.Connection, name: str, args: dict) -> str:
    tool = REGISTRY.get(name)
    if not tool:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        db.row_factory = sqlite3.Row
        out = json.dumps(tool.fn(db, args), default=str, ensure_ascii=False)
    except Exception as e:  # tools never crash an agent; the error goes back to it
        out = json.dumps({"error": f"{type(e).__name__}: {e}"[:400]})
    return out if len(out) <= MAX_CHARS else out[:MAX_CHARS] + '..."TRUNCATED"'
