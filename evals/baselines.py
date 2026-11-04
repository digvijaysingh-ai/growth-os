"""Two baselines for the agent team, on the same held-out businesses, graded by the same grader and priced by the same simulator.

  single_prompt  One Claude call, no tools. It gets everything the specialists' engines return (each one run over every market),
                 plus the two tables the specialists pulled with SQL (ad fatigue, sell-outs), in one data pack, with the growth
                 lead's rules. It answers with the same submit_decisions schema; like the lead, it may fix actions that fail
                 the catalogue check twice.
  playbook       No model. A fixed weekly checklist over the same engines: device checkout against peers, sell-outs, customer
                 comment themes, organic search, ad fatigue, channel returns, demand capture, weather. Written and tuned on the
                 development business (seed 7) only, then frozen. Its author knows which kinds of problem the generator plants,
                 so it is a strong rules baseline, not a naive one.

The team's saved runs are graded again in the same pass, so all three arms meet the same grader at the same time.

    python evals/baselines.py --seeds 301 302 303          # about $1.50 per seed (prompt + three gradings); simulation is local
    python evals/baselines.py --seeds 7 --arms playbook --no-grade --no-sim     # print the playbook's decisions on the dev business
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from growth_os.actions import catalog  # noqa: E402
from growth_os.enterprise import benchmarks, outcomes, team, tools  # noqa: E402
from growth_os.enterprise.profile import LINES, MARKETS  # noqa: E402

PROMPT_SYSTEM = """You are the growth lead of a multi-market consumer brand. Each week you decide what the business should do, and every
decision you propose is executed automatically once the right person approves it. You have no team and no tools this week: the
data pack in the message holds every analysis your specialists' tools would return, run over every market.

How you work:
1. Read the whole pack. Find what changed and why: check each departure against last year, peers and noise. Markets with only
   noise, and dips that happen every year, are not problems; say so.
2. Join evidence from different sections that describes the same situation into one decision, drop what is noise or seasonal,
   and rank by money at stake per month.
""" + team.LEAD_SYSTEM[team.LEAD_SYSTEM.index("4. Budget principles"):team.LEAD_SYSTEM.index("6. Every recommendation")].replace("4. ", "3. ").replace("5. ", "4. ") + \
"""5. Every recommendation needs metric_sql: one read-only SELECT over the hub returning one row with a numeric column named value,
   over a rolling window ending at the latest day in the data, so the outcome can be checked later.

Roles that approve: Leadership, Growth manager, Paid media manager, CRM manager, Product owner, Finance. Never write "director".
Never invent a number: every figure comes from the pack. The data is synthetic; the weather and holidays are real.

""" + catalog.prompt_text()

FATIGUE_SQL = """WITH x AS (SELECT MAX(day) d FROM ad_daily),
w AS (SELECT ad_id, market, line, CASE WHEN day > date(d, '-7 days') THEN 'now' WHEN day > date(d, '-35 days') AND day <= date(d, '-28 days') THEN 'then' END AS wk,
             AVG(frequency) f, SUM(link_clicks) c, SUM(impressions) i, SUM(spend) s
      FROM ad_daily, x WHERE creative = 'meta_prospecting' AND day > date(d, '-35 days') GROUP BY 1, 2, 3, 4)
SELECT a.ad_id, a.market, a.line, ROUND(b.f, 2) AS frequency_5_weeks_ago, ROUND(a.f, 2) AS frequency_last_week,
       ROUND(1000.0 * b.c / b.i, 2) AS clicks_per_1000_then, ROUND(1000.0 * a.c / a.i, 2) AS clicks_per_1000_now, ROUND(a.s) AS spend_last_week
FROM w a JOIN w b USING (ad_id) WHERE a.wk = 'now' AND b.wk = 'then' ORDER BY a.f / b.f DESC LIMIT 15"""
SELLOUT_SQL = """SELECT p.product_id, p.market, p.line, p.name, s.day AS sold_out_on, p.end_day AS edition_ends, p.capacity
FROM stock_events s JOIN products p USING (product_id), (SELECT MAX(day) d FROM sales_daily) x
WHERE s.event = 'sold_out' AND s.day > date(x.d, '-30 days') AND p.end_day > x.d ORDER BY s.day"""


def _ro(hub: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{hub}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def _sql(db, q: str) -> list[dict]:
    return [dict(r) for r in db.execute(q)]


def data_pack(db) -> str:
    """Everything the four specialists' engines return, each run over every market, plus the two tables they pulled with SQL.
    Each section is the tool's JSON text exactly as an agent receives it, truncation included."""
    t = lambda name, **a: tools.call(db, name, a)  # noqa: E731
    pack = {f"scan_benchmarks:{m}": t("scan_benchmarks", metric=m, days=28) for m in benchmarks.METRICS}
    pack |= {"demand_potential": t("demand_potential"), "weather_sensitivity": t("weather_sensitivity", market="all", line="all"),
             "demand_outlook": t("demand_outlook"), "demand_model_accuracy": t("demand_model_accuracy"), "voc_gaps": t("voc_gaps"),
             "nps_by_market": t("nps_by_market"), "line_marginal_returns": t("line_marginal_returns"), "reallocation_plan": t("reallocation_plan", limit=20),
             "organic_vs_paid": t("organic_vs_paid"), "platform_vs_first_party": t("platform_vs_first_party"), "budget_pacing": t("budget_pacing")}
    pack |= {f"channel_response:{m}": t("channel_response", market=m, line="all") for m in MARKETS}
    pack |= {"meta_prospecting_fatigue (SQL)": json.dumps(_sql(db, FATIGUE_SQL), default=str),
             "sold_out_editions (SQL)": json.dumps(_sql(db, SELLOUT_SQL), default=str)}
    return "\n\n".join(f"## {k}\n{v}" for k, v in pack.items())


def _submit_tool() -> dict:
    from growth_os.agents.analyst.analyst import TOOLS
    memo = next(x for x in TOOLS if x["name"] == "submit_memo")
    return {**memo, "name": "submit_decisions", "description": "Hand in the week's decisions. Call once. Each recommendation carries one executable action (execution)."}


def single_prompt(client, hub: Path) -> dict:
    db = _ro(hub)
    t0, run = time.time(), team.AgentRun("single_prompt")
    asof = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
    first = (f"A consumer brand selling time-limited editions online in 12 cities and 4 product lines, about €3.3M of marketing a month. "
             f"Leadership wants more revenue and gross profit from the same budget, and the problems fixed that cost the most. The data runs to {asof}.\n\n"
             f"Data pack (one section per analysis, JSON):\n\n{data_pack(db)}")
    messages = [{"role": "user", "content": first}]
    for _ in range(4):  # one answer, a nudge if it forgets to submit, and up to two fixes for actions the catalogue refuses
        # one answer carries all the reasoning the team spreads over many turns, so it gets more output room than one lead turn
        with client.beta.messages.stream(model=team.MODEL, max_tokens=48000, system=PROMPT_SYSTEM, tools=[_submit_tool()], messages=messages,
                                         output_config={"effort": "high"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default") as s:
            resp = s.get_final_message()
        run.turns += 1
        u = resp.usage
        for k, v in (("input", u.input_tokens), ("output", u.output_tokens), ("cache_read", u.cache_read_input_tokens or 0),
                     ("cache_write", u.cache_creation_input_tokens or 0)):
            run.usage[k] += v
        if resp.stop_reason in ("refusal", "max_tokens"):  # a cut-off tool call is a failed answer, never a short one
            run.error = resp.stop_reason
            break
        messages.append({"role": "assistant", "content": resp.content})
        call = next((b for b in resp.content if b.type == "tool_use"), None)
        if not call:
            messages.append({"role": "user", "content": "Please call submit_decisions now."})
            continue
        errs = [f"recommendation {i}: {e}" for i, r in enumerate(call.input.get("recommendations", []), 1)
                for e in catalog.check(db, r.get("execution", {})).errors]
        if errs and run.turns < 4:
            messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": call.id, "is_error": True,
                                                          "content": "Not accepted. Fix these actions and call submit_decisions again:\n" + "\n".join(errs)}]})
            continue
        run.output = dict(call.input)
        break
    return _result(db, run.output or {}, run.cost(), time.time() - t0, team.MODEL) | {"error": run.error, "turns": run.turns}


# ---- the playbook: thresholds set on seed 7, never changed after looking at a held-out business

def _rec(action, why, impact, money, ex, metric_sql, direction="up", confidence="medium") -> dict:
    return {"action": action, "why": why, "expected_impact": impact, "effort": "S", "confidence": confidence, "how_to_measure": "the metric_sql value",
            "metric_sql": metric_sql, "check_after_days": 14, "direction": direction, "execution": {"to_target": "", "amount_pct": 0, **ex},
            "_money": money}


def _rev_sql(market: str, line: str | None = None) -> str:
    return (f"SELECT SUM(revenue) AS value FROM sales_daily WHERE market = '{market}'" + (f" AND line = '{line}'" if line else "") +
            " AND day > date((SELECT MAX(day) FROM sales_daily), '-14 days')")


def playbook(hub: Path) -> dict:
    db, t0 = _ro(hub), time.time()
    f = lambda name, **a: tools.REGISTRY[name].fn(db, a)  # noqa: E731
    findings, recs, quiet = [], [], []
    rev_day = {r["market"]: r["value"] for r in (benchmarks.benchmark(db, m, "revenue_per_day", None, 28) for m in MARKETS)}

    # 1. checkout by device against peers: a step far below every peer is a fault, not marketing
    for dev in ("ios", "android", "desktop"):
        rows = [r for r in f("scan_benchmarks", metric=f"checkout_to_order_{dev}_pct", days=28)
                if r.get("outside_peer_range") and r["value"] < 0.8 * r["peer_range"][0]]
        if not rows:
            continue
        share = {m: db.execute(f"SELECT 1.0 * SUM({dev}_orders) / NULLIF(SUM(orders), 0) FROM v_bench_daily WHERE market = ?", (m,)).fetchone()[0] or 0
                 for m in [r["market"] for r in rows]}
        money = sum(rev_day[r["market"]] * 30 * share[r["market"]] * (r["peer_median"] / r["value"] - 1) for r in rows)
        where = " and ".join(r["market"] for r in rows)
        ev = "; ".join(f"{r['market']} {r['value']}% vs peers {r['peer_range'][0]}–{r['peer_range'][1]}% (last year {r['same_period_last_year']}%)" for r in rows)
        findings.append({"title": f"{dev} checkout-to-order collapsed in {where}", "evidence": ev, "confidence": "high"})
        recs.append(_rec(f"Engineering to fix the {dev} checkout/payment step in {where}", ev, f"about €{money:,.0f} a month of revenue", money,
                         {"type": "open_ticket", "target": "engineering", "note": f"{dev} checkout/payment failing in {where}: {ev}"}, _rev_sql(rows[0]["market"])))

    # 2. editions sold out with weeks left to run
    for r in _sql(db, SELLOUT_SQL):
        daily = db.execute("SELECT AVG(revenue) FROM sales_daily WHERE market = ? AND line = ? AND day > date(?, '-28 days') AND day <= ?",
                           (r["market"], r["line"], r["sold_out_on"], r["sold_out_on"])).fetchone()[0] or 0
        money = daily * 30 * 0.5
        ev = f"{r['product_id']} ({r['name']}) sold out on {r['sold_out_on']}, edition runs to {r['edition_ends']}, capacity {r['capacity']}"
        findings.append({"title": f"{r['market']} {r['line']} edition sold out early", "evidence": ev, "confidence": "high"})
        recs.append(_rec(f"Ops to restock {r['market']} {r['line']} ({r['product_id']})", ev, f"about €{money:,.0f} a month", money,
                         {"type": "open_ticket", "target": "ops", "note": f"Sold out with weeks left: restock {r['market']} {r['line']} edition. {ev}"},
                         _rev_sql(r["market"], r["line"])))

    # 3. customer comments: a theme new and far more frequent in one market
    gaps = [g for g in f("voc_gaps") if g["line"] == "all lines" and g["new"] and g["share_pct"] >= 3 * max(1, g["elsewhere_pct"])]
    for g in gaps:
        ev = f"{g['theme']} {g['share_pct']}% of {g['of']} comments vs {g['elsewhere_pct']}% elsewhere (was {g['before_pct']}%), NPS {g['nps']}"
        if g["theme"] == "delivery_late":
            owned = next((o for o in f("organic_vs_paid") if o["market"] == g["market"]), {})
            money = owned.get("revenue", 0) * owned.get("owned_pct", 0) / 100 * 0.3
            findings.append({"title": f"Late deliveries in {g['market']}", "evidence": ev, "confidence": "high"})
            recs.append(_rec(f"Logistics to fix late deliveries in {g['market']}", ev, f"about €{money:,.0f} a month of repeat revenue", money,
                             {"type": "open_ticket", "target": "logistics", "note": f"Late deliveries in {g['market']}: {ev}"}, _rev_sql(g["market"])))
        elif g["theme"] == "trust_brand":
            findings.append({"title": f"Visitors in {g['market']} do not know or trust the brand", "evidence": ev, "confidence": "medium"})
        elif g["theme"] != "payment_problem":  # payment faults are already caught by the checkout check
            findings.append({"title": f"{g['theme'].replace('_', ' ')} complaints up in {g['market']}", "evidence": ev, "confidence": "low"})

    # 4. organic search falling against last year while paid holds up (when everything falls together, the cause is elsewhere)
    for o in f("organic_vs_paid"):
        if (o.get("organic_vs_last_year_pct") or 0) <= -15 and (o.get("organic_change_pct") or 0) - (o.get("paid_change_pct") or 0) <= -10:
            money = o["revenue"] * o["organic_pct"] / 100 * 0.25
            ev = (f"organic revenue {o['organic_change_pct']}% vs the period before and {o['organic_vs_last_year_pct']}% vs last year, "
                  f"paid spend {o['spend_change_pct']:+}%, MER {o['mer']}")
            findings.append({"title": f"Organic search falling in {o['market']}", "evidence": ev, "confidence": "medium"})
            recs.append(_rec(f"SEO to find why organic search fell in {o['market']}", ev, f"about €{money:,.0f} a month", money,
                             {"type": "open_ticket", "target": "seo", "note": f"Organic search sessions and revenue down in {o['market']} (site change?): {ev}"},
                             _rev_sql(o["market"])))

    # 5. Meta prospecting ads worn out: frequency doubled and click rate down a third or more
    for a in _sql(db, FATIGUE_SQL):
        if a["frequency_last_week"] >= 2 * a["frequency_5_weeks_ago"] and a["clicks_per_1000_now"] <= 0.67 * a["clicks_per_1000_then"]:
            money = a["spend_last_week"] * 4.3 * 0.5
            ev = f"{a['ad_id']}: frequency {a['frequency_5_weeks_ago']} → {a['frequency_last_week']}, clicks per 1,000 views {a['clicks_per_1000_then']} → {a['clicks_per_1000_now']}"
            findings.append({"title": f"Creative fatigue on Meta prospecting, {a['market']} {a['line']}", "evidence": ev, "confidence": "high"})
            recs.append(_rec(f"Creative team to refresh the Meta prospecting creative in {a['market']} {a['line']}", ev, f"about €{money:,.0f} a month of wasted spend",
                             money, {"type": "open_ticket", "target": "creative", "note": f"Creative fatigue, {a['market']} {a['line']} Meta prospecting ad: {ev}"},
                             _rev_sql(a["market"], a["line"])))

    # 6. channel returns: saturated and over-claimed channels; apply the model's split where it fits
    fits = f("channel_response", market="all", line="all")
    good = [x for x in fits if x["r2"] >= 0.6]
    by_ch: dict[str, list] = {}
    for x in good:
        for ch, v in x["channels"].items():
            by_ch.setdefault(ch, []).append((x["market"], x["line"], v["marginal_roas"]))
    sat = sorted({m for m, _, r in by_ch.get("meta_prospecting", []) if r < 1})
    if sat:
        findings.append({"title": "Meta prospecting past diminishing returns in " + ", ".join(sat),
                         "evidence": "marginal ROAS below 1 where the mix model fits (r2 ≥ 0.6): " +
                                     "; ".join(f"{m} {l} {r}" for m, l, r in by_ch["meta_prospecting"] if r < 1)[:600], "confidence": "medium"})
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None  # noqa: E731
    for p in f("platform_vs_first_party"):
        m_roas = med([r for _, _, r in by_ch.get(p["channel"], [])])
        if p["first_party_roas"] and p["platform_roas"] / p["first_party_roas"] >= 1.8 and m_roas is not None and m_roas < 1:
            findings.append({"title": f"{p['channel']} claims far more than it adds", "evidence": f"platform ROAS {p['platform_roas']} vs first-party "
                             f"{p['first_party_roas']}, model marginal ROAS median {m_roas}", "confidence": "medium"})
        elif p["first_party_roas"] >= 5 and m_roas is not None and m_roas < 1:
            findings.append({"title": f"{p['channel']} mostly collects buyers who would come anyway", "evidence": f"last-click ROAS {p['first_party_roas']} "
                             f"but model marginal ROAS median {m_roas}", "confidence": "medium"})
    if len(good) >= len(fits) / 2:
        gain = sum(x["expected_weekly_revenue_gain"] for x in f("reallocation_plan", limit=200))
        recs.append(_rec("Apply the mix model's channel split across the portfolio (max ±25% per channel)",
                         f"the model fits well on {len(good)} of {len(fits)} market-lines", f"about €{gain * 4.3:,.0f} a month of revenue at the same spend",
                         gain * 4.3 * 0.4, {"type": "apply_mix_plan", "target": "all", "amount_pct": 25,
                                            "note": "Move spend toward channels with higher marginal ROAS; each line's total unchanged."},
                         "SELECT SUM(revenue) AS value FROM sales_daily WHERE day > date((SELECT MAX(day) FROM sales_daily), '-14 days')"))

    # 7. demand left on the table where the next euro still earns well
    ret = {(r["market"], r["line"]): r["blended_marginal_roas"] for r in f("line_marginal_returns")}
    gap = [d for d in f("demand_potential") if not d["new_market"] and d["captured_share_of_potential_pct"] < 80 and ret.get((d["market"], d["line"]), 0) >= 2]
    for d in sorted(gap, key=lambda d: -d["gap_revenue"])[:1]:
        ev = (f"captures {d['captured_share_of_potential_pct']}% of its potential ({d['capture_per_1000_searches']} vs peers {d['peer_capture_per_1000']} "
              f"orders per 1,000 searches), next-euro return {ret[(d['market'], d['line'])]}")
        findings.append({"title": f"{d['market']} {d['line']} leaves demand uncaptured", "evidence": ev, "confidence": "medium"})
        recs.append(_rec(f"Raise {d['market']} {d['line']} budget by 15%", ev, f"gap of about €{d['gap_revenue'] / 2:,.0f} a month", d["gap_revenue"] / 2 * 0.2,
                         {"type": "change_line_budget", "target": f"{d['market']}|{d['line']}", "amount_pct": 15,
                          "note": "Fund from lines with low marginal returns."}, _rev_sql(d["market"], d["line"])))

    # 8. rain lifts sales clearly: spend more on rainy days
    wet = sorted([s for s in f("weather_sensitivity", market="all", line="all") if s["rain_effect_range_pct"][0] >= 15], key=lambda s: -s["rain_effect_pct"])[:3]
    for s in wet:
        ev = f"rain lifts orders {s['rain_effect_pct']}% (95% range {s['rain_effect_range_pct'][0]}–{s['rain_effect_range_pct'][1]}%)"
        findings.append({"title": f"{s['market']} {s['line']} sells more when it rains", "evidence": ev, "confidence": "high"})
        recs.append(_rec(f"Weather rule: +20% upper-funnel spend on rainy days for {s['market']} {s['line']}", ev, "more orders on rainy days", 0,
                         {"type": "weather_rule", "target": f"{s['market']}|{s['line']}", "amount_pct": 20, "note": ""}, _rev_sql(s["market"], s["line"])))

    # 9. launches behind earlier ones, and dips that happen every year
    for r in (benchmarks.benchmark(db, m, "revenue_per_day", None, 28) for m in MARKETS):
        if (l := r.get("launch")) and (l.get("share_of_earlier_median_pct") or 100) < 50:
            ev = f"{l['weeks_since_launch']} weeks in: €{l['revenue_per_day_now']:,}/day vs earlier launches {l['earlier_launches_same_age']}"
            findings.append({"title": f"{r['market']} launch far behind earlier launches", "evidence": ev, "confidence": "high"})
            recs.append(_rec(f"Tell leadership the {r['market']} launch is behind and needs a trust plan", ev, "not sized", 0,
                             {"type": "notify", "target": "leadership", "note": f"{r['market']} launch at {l['share_of_earlier_median_pct']}% of earlier launches"},
                             _rev_sql(r["market"])))
        elif r.get("same_period_last_year") and r["value"] < 0.9 * r["previous_period"] and abs(r["value"] / r["same_period_last_year"] - 1) < 0.1:
            quiet.append(f"{r['market']}: revenue down vs the previous 4 weeks but flat year over year (seasonal)")

    recs.sort(key=lambda r: -r.pop("_money"))
    memo = {"headline": recs[0]["action"] if recs else "Nothing crossed a playbook threshold this week.",
            "data_sufficiency": {"verdict": "solid", "explanation": "Fixed thresholds over the hub's engines."}, "kpis": [],
            "findings": findings + [{"title": "Not a problem: " + q, "evidence": q, "confidence": "medium"} for q in quiet],
            "recommendations": recs, "experiments": [], "questions_for_owner": []}
    return _result(db, memo, 0.0, time.time() - t0, "none (rules)")


def _result(db, decisions: dict, cost: float, seconds: float, model: str) -> dict:
    routed = []
    for i, r in enumerate(decisions.get("recommendations", []), 1):
        chk = catalog.check(db, r.get("execution", {}))
        routed.append({"rank": i, "action": r["action"], "approver": catalog.ROLES[chk.approver], "risk": chk.risk, "type": r["execution"]["type"]})
    return {"decisions": decisions, "routing": routed, "specialists": {}, "cost_usd": round(cost, 3), "seconds": round(seconds), "model": model}


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the single-prompt and playbook baselines and grade them with the team, on the same businesses.")
    ap.add_argument("--seeds", type=int, nargs="+", default=[301, 302, 303])
    ap.add_argument("--arms", nargs="+", default=["single_prompt", "playbook", "team"], choices=["single_prompt", "playbook", "team"])
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--no-sim", action="store_true")
    a = ap.parse_args()
    import anthropic
    from team_eval import criteria, grade
    client = anthropic.Anthropic(timeout=900, max_retries=3)
    rows = []
    for seed in a.seeds:
        hub = ROOT / "state" / ("enterprise-7.sqlite" if seed == 7 else f"team-eval-{seed}.sqlite")
        if not hub.is_file():
            print(f"GOS-101: {hub.relative_to(ROOT)} is missing. Fix: python -m growth_os.enterprise.prepare {hub.relative_to(ROOT)} {seed}", file=sys.stderr)
            return 1
        for arm in a.arms:
            path = ROOT / "reports" / (f"team-eval-{seed}.json" if arm == "team" else f"baseline-{arm}-{seed}.json")
            if arm == "team":
                res = json.loads(path.read_text())
            else:
                res = single_prompt(client, hub) if arm == "single_prompt" else playbook(hub)
                path.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
            recs = res["decisions"].get("recommendations", [])
            row = {"seed": seed, "arm": arm, "decisions": len(recs), "cost_usd": res["cost_usd"], "seconds": res["seconds"]}
            if a.no_grade and a.no_sim:
                print(json.dumps({**row, "headline": res["decisions"].get("headline"), "actions": [r["action"] for r in recs],
                                  "findings": [x["title"] for x in res["decisions"].get("findings", [])]}, ensure_ascii=False, indent=1))
            if not a.no_sim and recs:
                out = outcomes.run(hub, path, singles=False)["all_approved"]
                row |= {"revenue_pct": out["change_pct"].get("revenue"), "gross_profit_pct": out["change_pct"].get("gross_profit"),
                        "gross_profit_eur": out["change"]["gross_profit"]}
            if not a.no_grade:
                g = grade(client, res, seed) if recs else [{"criterion": c, "pass": False, "reason": "no decisions"} for c in criteria(seed)[0]]
                row |= {"passed": sum(x["pass"] for x in g), "checks": len(g), "grades": g}
            rows.append(row)
            print(f"seed {seed} {arm}: " + ", ".join(f"{k} {v}" for k, v in row.items() if k not in ("grades", "seed", "arm")), flush=True)
    if not (a.no_grade and a.no_sim):
        path = ROOT / "evals" / "results" / f"baselines-{'-'.join(map(str, a.seeds))}-{datetime.now():%Y%m%d-%H%M}.json"
        path.write_text(json.dumps({"when": datetime.now().isoformat(timespec="seconds"), "runs": rows,
                                    "note": "SIMULATED outcomes on SYNTHETIC businesses; same grader and simulator for every arm."}, ensure_ascii=False, indent=1))
        print(f"saved {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
