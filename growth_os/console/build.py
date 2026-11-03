"""Builds the console: `growth-os console --out dist/console`.

Every number on the page is read from a hub or a saved memo at build time; significance flags use the analyst's own
compare_rates with the same correction for the number of markets scanned, so page and memo cannot disagree.
"""
from __future__ import annotations

import glob
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from ..agents.analyst.stats import compare_rates
from ..config import ROOT
from ..hub import store

TEMPLATE = Path(__file__).with_name("template.html")


def _rows(db, sql, *p):
    return [dict(r) for r in db.execute(sql, p).fetchall()]


def _has(db, table, where="1"):
    try:
        return db.execute(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {where})").fetchone()[0] == 1
    except Exception:
        return False


def _unlisted(db, day: str, tracked: list[str]) -> list[dict]:
    """Names the discovery step found in unbranded answers that match no tracked brand."""
    if not _has(db, "ai_discovered"):
        return []
    rows = _rows(db, """SELECT d.name, COUNT(DISTINCT d.answer_id) AS answers FROM ai_discovered d JOIN ai_answers a USING (answer_id)
                        WHERE a.day = ? AND a.branded = 0 GROUP BY lower(d.name) ORDER BY answers DESC""", day)
    low = [t.lower() for t in tracked]
    return [r for r in rows if not any(t in r["name"].lower() or r["name"].lower() in t for t in low)][:10]


def commerce_view(db, c: tuple, p: tuple) -> dict:
    from ..agents.analyst.analyst import commerce_brief, natural_experiments
    cb = commerce_brief(db, c, p)
    ly = lambda d: (date.fromisoformat(d) - timedelta(days=364)).isoformat()
    tot = lambda a: _rows(db, """SELECT ROUND(SUM(revenue)) AS revenue, ROUND(SUM(CASE WHEN channel LIKE 'paid:%' THEN revenue ELSE 0 END)) AS paid_revenue,
                                 SUM(orders) AS orders, SUM(new_customers) AS new_customers FROM sales_daily WHERE day BETWEEN ? AND ?""", *a)[0]
    sp = lambda a: db.execute("SELECT ROUND(SUM(spend)) FROM ad_daily WHERE day BETWEEN ? AND ?", a).fetchone()[0] or 0
    now, before, last_year = tot(c), tot(p), tot((ly(c[0]), ly(c[1])))
    for d, a in ((now, c), (before, p)):
        d["spend"] = sp(a)
        d["paid_roas"] = round(d["paid_revenue"] / d["spend"], 2) if d["spend"] else None
    # fatigue is creative-specific: compare each creative's ROAS change with its own city's paid ROAS change
    city = {m["market"]: (m["paid_roas_now"], m["paid_roas_before"]) for m in cb["markets"]}
    creatives = [r for r in cb["creatives_now_vs_before"] if r["platform"] in ("meta", "tiktok") and (r["spend_now"] or 0) >= 500 and r["roas_before"]]
    for r in creatives:
        r["roas_change_pct"] = round(100 * (r["roas_now"] - r["roas_before"]) / r["roas_before"], 1) if r["roas_now"] is not None else None
        cn, cbf = city.get(r["market"], (None, None))
        r["city_change_pct"] = round(100 * (cn - cbf) / cbf, 1) if cn and cbf else 0.0
        r["vs_city_pts"] = round(r["roas_change_pct"] - r["city_change_pct"], 1) if r["roas_change_pct"] is not None else None
    tracker = _rows(db, "SELECT id, rank, action, confidence, status, baseline, check_after_days, direction FROM recommendations ORDER BY id DESC LIMIT 8") if _has(db, "recommendations") else []
    return {
        "now": now, "before": before, "last_year": last_year,
        "weekly": _rows(db, """SELECT y.week, ROUND(SUM(y.revenue)) AS revenue, ROUND(SUM(y.revenue_last_year)) AS revenue_last_year, ROUND(SUM(w.spend)) AS spend
                               FROM v_market_yoy y JOIN v_market_weekly w USING (market, week) GROUP BY y.week HAVING COUNT(y.revenue_last_year) > 0 ORDER BY y.week"""),
        "markets": cb["markets"],
        "creatives_worst": sorted([r for r in creatives if r["vs_city_pts"] is not None], key=lambda r: r["vs_city_pts"])[:5],
        "budget": cb.get("budget_pacing_this_month", []),
        "products": [r for r in cb.get("products_on_sale", []) if r["window_elapsed_pct"] - r["sold_pct"] >= 20][:5],
        "platforms": cb["platform_vs_first_party"],
        "experiments": natural_experiments(db),
        "tracker": tracker,
    }


def hub_view(hub: Path, until: date | None, days: int) -> dict:
    store.connect(hub).close()
    db = store.connect(hub, read_only=True)
    out: dict = {}
    last = db.execute("SELECT MAX(day) FROM v_funnel_daily").fetchone()[0]
    if last:
        until = until or date.fromisoformat(last)
        c = ((until - timedelta(days=days - 1)).isoformat(), until.isoformat())
        p = ((until - timedelta(days=2 * days - 1)).isoformat(), (until - timedelta(days=days)).isoformat())
        tot = """SELECT ROUND(SUM(spend), 2) AS spend, SUM(sessions) AS sessions, SUM(form_starts) AS form_starts, SUM(form_submits) AS form_submits,
                 SUM(leads) AS leads, SUM(qualified) AS qualified, SUM(won) AS won FROM v_funnel_daily WHERE day BETWEEN ? AND ?"""
        out["period"] = {"since": c[0], "until": c[1], "days": days}
        out["now"], out["before"] = _rows(db, tot, *c)[0], _rows(db, tot, *p)[0]
        out["weekly"] = _rows(db, """SELECT MIN(day) AS week, ROUND(SUM(spend), 2) AS spend, SUM(sessions) AS sessions, SUM(leads) AS leads, SUM(qualified) AS qualified, SUM(won) AS won
                                     FROM v_funnel_daily GROUP BY strftime('%Y-%W', day) ORDER BY week""")
        markets = [r[0] for r in db.execute("SELECT DISTINCT market FROM v_market_daily WHERE market != '' ORDER BY market")]
        if len(markets) > 1 and not _has(db, "sales_daily"):  # lead-funnel markets; commerce hubs get their own view
            mk = """SELECT market, ROUND(SUM(spend), 2) AS spend, SUM(sessions) AS sessions, SUM(form_starts) AS form_starts, SUM(form_submits) AS form_submits,
                    SUM(leads) AS leads, SUM(qualified) AS qualified FROM v_market_daily WHERE day BETWEEN ? AND ? GROUP BY market"""
            now = {r["market"]: r for r in _rows(db, mk, *c)}
            before = {r["market"]: r for r in _rows(db, mk, *p)}
            rows = []
            for m in markets:
                a, b = before.get(m), now.get(m)
                if not a or not b:
                    continue
                q = compare_rates(a["qualified"], a["leads"], b["qualified"], b["leads"], comparisons=len(markets))
                f = compare_rates(a["form_submits"], a["form_starts"], b["form_submits"], b["form_starts"], comparisons=len(markets))
                rows.append({**b, "qualified_rate": q["b_rate"], "qualified_rate_before": q["a_rate"], "qualified_verdict": q["verdict"],
                             "form_rate": f["b_rate"], "form_rate_before": f["a_rate"], "form_verdict": f["verdict"]})
            out["markets"] = rows
    if _has(db, "sales_daily") and last:
        out["commerce"] = commerce_view(db, c, p)
    if _has(db, "ad_daily") and not _has(db, "sales_daily"):
        out["ads"] = _rows(db, """SELECT ad_name, campaign, ROUND(spend, 2) AS spend, link_clicks, sessions, leads, qualified, cost_per_lead, cost_per_qualified
                                  FROM v_ad_funnel ORDER BY spend DESC LIMIT 40""")
    if _has(db, "leads", "landing IS NOT NULL"):
        out["channels"] = _rows(db, "SELECT channel, leads, won, close_rate_pct, avg_days_to_win, avg_value_per_won_customer FROM v_lead_channels ORDER BY leads DESC")
        out["landing"] = _rows(db, "SELECT COUNT(*) AS pages, SUM(won = 0) AS pages_no_win, SUM(leads >= 30) AS pages_30 FROM v_lead_landing")[0]
        out["monthly"] = _rows(db, "SELECT substr(day, 1, 7) AS month, COUNT(*) AS leads, SUM(won) AS won FROM v_qualified GROUP BY month ORDER BY month")
    if _has(db, "voice_items"):
        out["voice_themes"] = _rows(db, "SELECT theme, items, share_pct, avg_rating FROM v_voice_themes ORDER BY items DESC")
        out["voice_segments"] = _rows(db, "SELECT segment, items, avg_rating, negative_pct FROM v_voice_by_segment WHERE items >= 30 ORDER BY negative_pct")
    if _has(db, "ai_answers"):
        from ..agents.analyst.stats import wilson
        day = db.execute("SELECT MAX(day) FROM ai_answers").fetchone()[0]
        sov = _rows(db, "SELECT brand, answers, mentioned, mention_rate_pct, mentioned_first, avg_rank_when_mentioned, own_site_cited FROM v_ai_share_of_voice WHERE day = ? ORDER BY mentioned DESC, brand", day)
        for r in sov:
            lo, hi = wilson(r["mentioned"], r["answers"])
            r["ci"] = [round(lo * 100, 1), round(hi * 100, 1)]
        out["ai"] = {"day": day, "assistant": db.execute("SELECT MAX(assistant) FROM ai_answers WHERE day = ?", (day,)).fetchone()[0],
                     "questions": db.execute("SELECT COUNT(DISTINCT question_id) FROM ai_answers WHERE day = ? AND branded = 0", (day,)).fetchone()[0],
                     "answers": db.execute("SELECT COUNT(*) FROM ai_answers WHERE day = ? AND branded = 0", (day,)).fetchone()[0],
                     "unlisted": _unlisted(db, day, [r["brand"] for r in sov]),
                     "sov": sov, "sites": _rows(db, "SELECT domain, answers_citing FROM v_ai_cited_sites WHERE day = ? ORDER BY answers_citing DESC LIMIT 8", day)}
    out["sources"] = _rows(db, "SELECT DISTINCT source, note FROM sync_log")
    db.close()
    return out


def loop_view(hub: Path, memo_path: Path, loop_path: Path) -> dict:
    """The decision loop on the showcase business: inbox with simulated outcomes, role briefs, why-not-buy, economics, attribution."""
    from .. import attribution, stakeholders, tracker, whynot, world
    from ..agents.analyst.analyst import natural_experiments
    from ..loop import ROLE_PEOPLE
    md = json.loads(memo_path.read_text())
    memo, lp = md["memo"], json.loads(loop_path.read_text())
    fork = world.fork(hub, "console")
    tracker.record(fork, memo, lp["memo_date"])
    with store.connect(fork, read_only=True) as db:
        target = lambda m: (db.execute("SELECT target FROM targets WHERE scope = 'all' AND metric = ?", (m,)).fetchone() or [None])[0]
        nat = natural_experiments(db)
        natural = [{"summary": f"{n['campaign']} was off {n['off_from']} to {n['off_to']}: it had brought €{n['campaign_revenue_before']:,.0f} the 14 days before; "
                               f"{n['market']}'s total revenue went from €{n['market_revenue_before']:,.0f} to €{n['market_revenue_during']:,.0f} while organic and direct "
                               f"rose from €{n['organic_direct_revenue_before']:,.0f} to €{n['organic_direct_revenue_during']:,.0f}."} for n in nat]
        out = {"memo": {k: memo[k] for k in ("headline", "data_sufficiency", "findings", "kpis")},
               "briefs": stakeholders.briefs(fork), "whynot": [{**c, "evidence": c["evidence"][:3]} for c in whynot.engine(db)],
               "economics": _rows(db, "SELECT * FROM v_market_economics_28d ORDER BY gross_revenue DESC"),
               "attribution": attribution.compare(db), "holdout": attribution.holdout_plan(db), "natural": natural,
               "mer_target": target("mer"), "cac_target": target("blended_cac")}
    recs = []
    for r in lp["recommendations"]:
        m = memo["recommendations"][r["rank"] - 1]
        recs.append({**{k: v for k, v in r.items() if k not in ("audit",)}, "why": m["why"], "confidence": m["confidence"], "expected_impact": m["expected_impact"]})
    world.cleanup()
    u = md.get("usage", {})
    cost = (u.get("input", 0) * 4 + u.get("output", 0) * 20 + u.get("cache_read", 0) * 0.2 + u.get("cache_write", 0) * 5) / 1e6
    return {**out, "recommendations": recs, "assumptions": lp["assumptions"], "note": lp["note"], "start": lp["start"], "people": ROLE_PEOPLE,
            "meta": f"Memo by {md.get('model', 'claude-opus-5-5')} in {md.get('turns')} turns, {len(md.get('queries', []))} queries, "
                    f"{len(md.get('comparisons', []))} statistical tests, about {cost:.2f} USD. Fictional team names."}


class BuildError(Exception):
    """A build that refuses to ship wrong numbers. `code` is documented in docs/errors.md; the message ends with the fix."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


# The six role names the case study and console use, from the catalogue's keys and labels.
ROLE_LABELS = {"leadership": "Leadership", "growth_manager": "Growth manager", "channel_manager": "Paid media manager",
               "crm_manager": "CRM manager", "product_owner": "Product owner", "finance": "Finance",
               "Leadership": "Leadership", "Growth manager": "Growth manager", "Paid media manager": "Paid media manager",
               "CRM / lifecycle manager": "CRM manager", "Product / engineering owner": "Product owner", "Finance partner": "Finance"}
# "You beat the AI here" needs a gain worth naming: more than this many euros and this share of the all-approved gain.
BEAT_MIN_EUR, BEAT_MIN_SHARE = 1000, 0.001
_ESCAPED = re.compile(r"\\u([0-9a-fA-F]{4})")


def _text(s: str) -> str:
    """Decode the \\uXXXX sequences some saved agent text carries as literal characters. Clean text passes unchanged."""
    return _ESCAPED.sub(lambda m: chr(int(m.group(1), 16)), s) if isinstance(s, str) else s


def _role(raw: str, where: str) -> str:
    """Map a report or audit role string to one of the six labels. Audit strings end with the role key in brackets."""
    key = raw.rsplit("(", 1)[-1].rstrip(")").strip() if raw.endswith(")") else raw
    if key not in ROLE_LABELS:
        raise BuildError("GOS-103", f"unknown role in {where}; allowed: {', '.join(sorted(set(ROLE_LABELS.values())))}. "
                                    f"Fix: add the role to ROLE_LABELS in growth_os/console/build.py.")
    return ROLE_LABELS[key]


def deck_view(team_path: Path, outcomes_path: Path, loo_path: Path, allow_stale: bool = False) -> dict:
    """The decision deck: each decision with its owner and money measured alone, plus every measured state the visitor can
    reach (all, none, one priced decision left out, one priced decision alone). Refuses to build on missing or stale
    leave-one-out runs, so the deck never shows a number no simulation produced."""
    outc = json.loads(outcomes_path.read_text())
    for key in ("decisions", "all_approved"):
        if key not in outc:
            raise BuildError("GOS-102", f"{outcomes_path} has no '{key}'. Fix: regenerate it with python -m growth_os.enterprise.outcomes "
                                        f"<hub> {team_path} {outcomes_path}")
    regen = "python -m growth_os.enterprise.outcomes --leave-one-out --seed <seed>"
    if not loo_path.is_file():
        raise BuildError("GOS-101", f"{loo_path} is missing; the deck needs the leave-one-out runs. Fix: {regen}")
    loo = json.loads(loo_path.read_text())
    priced = [d["id"] for d in outc["decisions"] if d["simulated"]]
    problems = []
    if loo["inputs"].get("team_sha256") != hashlib.sha256(team_path.read_bytes()).hexdigest():
        problems.append(f"{team_path.name} changed since the runs")
    if loo["inputs"].get("outcomes_sha256") != hashlib.sha256(outcomes_path.read_bytes()).hexdigest():
        problems.append(f"{outcomes_path.name} changed since the runs")
    if loo["inputs"].get("priced_ids") != priced or sorted(r["left_out"] for r in loo["runs"]) != sorted(priced) or not loo.get("complete"):
        problems.append(f"the runs cover {sorted(r['left_out'] for r in loo['runs'])}, the priced decisions are {priced}")
    if loo.get("baseline_gross_profit") != outc["all_approved"]["as_is"]["gross_profit"]:
        problems.append(f"baseline gross profit {loo.get('baseline_gross_profit')} vs {outc['all_approved']['as_is']['gross_profit']}")
    if problems and not allow_stale:
        raise BuildError("GOS-102", f"{loo_path} is stale ({'; '.join(problems)}; report written {datetime.fromtimestamp(loo_path.stat().st_mtime):%Y-%m-%d %H:%M}, "
                                    f"outcomes {datetime.fromtimestamp(outcomes_path.stat().st_mtime):%Y-%m-%d %H:%M}). Fix: {regen}")
    for d in outc["decisions"]:
        if not d["simulated"] and d["change"]:
            raise BuildError("GOS-102", f"decision #{d['id']} is unpriced but carries a change in {outcomes_path}. Fix: regenerate the outcomes report.")
    allin = outc["all_approved"]
    keys = ("revenue", "spend", "gross_profit")
    singles = {d["id"]: d["change"] for d in outc["decisions"] if d["simulated"]}
    sum_singles = {k: round(sum(c[k] for c in singles.values())) for k in keys}
    beat = [r["left_out"] for r in loo["runs"] if (gain := r["change"]["gross_profit"] - allin["change"]["gross_profit"]) > BEAT_MIN_EUR
            and gain > BEAT_MIN_SHARE * allin["change"]["gross_profit"]]
    cards = []
    for d in outc["decisions"]:
        cards.append({"id": d["id"], "rank": d["rank"], "action": _text(d["action"]), "type": d["type"], "risk": d["risk"],
                      "role": _role(d["approver"], f"decision #{d['id']} in {outcomes_path.name}"), "priced": d["simulated"],
                      "alone": {k: d["change"][k] for k in keys} if d["simulated"] else None})
    return {"cards": cards, "priced": priced, "as_is": {k: allin["as_is"][k] for k in keys},
            "all": {k: allin["change"][k] for k in keys}, "sum_singles": sum_singles,
            "leave_one_out": {str(r["left_out"]): {k: r["change"][k] for k in keys} for r in loo["runs"]},
            "beat_the_ai": beat, "beat_min_eur": BEAT_MIN_EUR,
            "share_of_gross_profit_pct": round(100 * allin["change"]["gross_profit"] / allin["as_is"]["gross_profit"], 1),
            "share_of_spend_pct": round(100 * allin["change"]["gross_profit"] / allin["as_is"]["spend"], 1),
            "approx_mode": "sum", "stale": bool(problems)}


def enterprise_view(hub: Path, team_path: Path, outcomes_path: Path) -> dict:
    """The enterprise showcase: the agent team's work, decisions with simulated quarterly impact, and each engine's view."""
    import sqlite3

    from ..enterprise import benchmarks, demand, external, mix, voc
    from ..enterprise.profile import LINES, MARKETS, PAID
    team, outc = json.loads(team_path.read_text()), json.loads(outcomes_path.read_text())
    db = sqlite3.connect(f"file:{hub}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    asof = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
    fits = mix.fit_all(db, list(MARKETS), list(LINES))
    sens = [s for m in MARKETS for l in LINES if (s := demand.sensitivity(db, m, l))]
    try:
        fc = external.forecast(date.fromisoformat(asof) + timedelta(days=1))
    except Exception:
        fc = {}
    mroas = {}
    for f in fits:
        for c, v in f["channels"].items():
            mroas.setdefault(f["market"], {}).setdefault(c, []).append((v["marginal_roas"] or 0, v["weekly_spend"]))
    mroas = {m: {c: round(sum(a * w for a, w in xs) / max(1, sum(w for _, w in xs)), 2) for c, xs in cs.items()} for m, cs in mroas.items()}
    monthly = _rows(db, """SELECT substr(day, 1, 7) AS month, ROUND(SUM(revenue)) AS revenue,
                           (SELECT ROUND(SUM(spend)) FROM ad_daily a WHERE substr(a.day, 1, 7) = substr(s.day, 1, 7)) AS spend
                           FROM sales_daily s GROUP BY 1 HAVING COUNT(DISTINCT day) > 20 ORDER BY 1""")
    decisions = []
    recs = team["decisions"].get("recommendations", [])
    for d in outc["decisions"]:
        r = recs[d["rank"] - 1] if d["rank"] - 1 < len(recs) else {}
        decisions.append({**d, "action": _text(d["action"]), "approver": _role(d["approver"], f"decision #{d['id']} in {outcomes_path.name}"),
                          "why": _text(r.get("why", "")), "expected_impact": _text(r.get("expected_impact", "")), "confidence": r.get("confidence", ""),
                          "note": _text(r.get("execution", {}).get("note", "")), "rollback": catalog_rollback(d["type"])})
    out = {
        "as_of": asof, "markets": len(MARKETS), "lines": list(LINES), "channels": PAID,
        "monthly": monthly, "headline": team["decisions"].get("headline", ""), "findings": team["decisions"].get("findings", [])[:8],
        "agents": team["agents"], "team_cost_usd": team["cost_usd"], "team_seconds": team["seconds"],
        "specialists": {k: [{"summary": (r["output"] or {}).get("summary", ""), "findings": (r["output"] or {}).get("findings", [])[:6],
                             "not_problems": (r["output"] or {}).get("not_problems", [])[:4], "tool_calls": [t["tool"] for t in r["tool_calls"]]}
                            for r in v] for k, v in team["specialists"].items()},
        "briefs": team.get("briefs", []), "decisions": decisions, "impact": outc["all_approved"], "time": outc["time_estimate"],
        "assumptions": outc["assumptions"],
        "audit": [{**a, "detail": _text(a["detail"]), "approved_by": _role(a["approved_by"], f"audit entry {i + 1} in {outcomes_path.name}")}
                  for i, a in enumerate(outc["audit"][:30])],
        "potential": demand.potential(db)[:14], "potential_all": demand.potential(db), "accuracy": demand.accuracy(db),
        "outlook": demand.outlook(db, fc, sens)[:10] if fc else [], "rain": sorted(sens, key=lambda s: -s["rain_effect_pct"])[:8],
        "bench": [r for m in MARKETS for metric in ("checkout_to_order_ios_pct", "checkout_to_order_android_pct", "organic_share_pct", "repeat_share_pct", "mer")
                  if (r := benchmarks.benchmark(db, m, metric, None, 28)).get("outside_peer_range")][:12],
        "seasonal": sorted([b for m in MARKETS if (b := benchmarks.benchmark(db, m, "revenue_per_day", None, 28)).get("previous_period")
                            and b.get("same_period_last_year") and b["value"] < 0.85 * b["previous_period"] and abs(b["value"] / b["same_period_last_year"] - 1) < 0.08],
                           key=lambda b: b["value"] / b["previous_period"])[:2],
        "launch": benchmarks.launches(db, db.execute("SELECT market FROM market_profile WHERE launched_on IS NOT NULL ORDER BY launched_on DESC LIMIT 1").fetchone()[0]),
        "launch_market": db.execute("SELECT market FROM market_profile WHERE launched_on IS NOT NULL ORDER BY launched_on DESC LIMIT 1").fetchone()[0],
        "voc": voc.gaps(db)[:12], "voc_count": db.execute("SELECT COUNT(*) FROM voc_items").fetchone()[0],
        "mroas": mroas, "organic": mix.organic_vs_paid(db),
        "platform": [dict(zip(("channel", "spend", "first_party", "claimed", "fp_roas", "platform_roas"), r)) for r in db.execute(
            """WITH x AS (SELECT MAX(day) d FROM ad_daily), a AS (SELECT creative c, SUM(spend) sp, SUM(platform_revenue) pr FROM ad_daily, x
               WHERE day > date(d, '-28 days') GROUP BY 1), s AS (SELECT replace(channel, 'paid:', '') c, SUM(revenue) r FROM sales_daily, x
               WHERE day > date(d, '-28 days') AND channel LIKE 'paid:%' GROUP BY 1)
               SELECT a.c, ROUND(sp), ROUND(r), ROUND(pr), ROUND(r / sp, 2), ROUND(pr / sp, 2) FROM a JOIN s USING (c) ORDER BY sp DESC""")],
        "sources": _rows(db, "SELECT DISTINCT source, note FROM sync_log"),
    }
    out.update(_enterprise_charts(db, hub, fits, sens, fc, outc, team))
    db.close()
    return out


def _enterprise_charts(db, hub: Path, fits: list, sens: list, fc: dict, outc: dict, team: dict) -> dict:
    """Series for the console's charts: weekly business, markets on a map, curves, engine validation, matrices."""
    from ..enterprise import benchmarks, voc
    from ..enterprise.profile import LINES, MARKETS, PAID
    margin = {l: v["margin"] for l, v in LINES.items()}
    kind = """CASE WHEN channel LIKE 'paid:%' THEN 'paid' WHEN channel IN ('email', 'sms') THEN 'owned' ELSE 'organic' END"""
    wk = {}
    for w, m, l, k, rev, orders, newc in db.execute(f"""SELECT date(day, 'weekday 0', '-6 days'), market, line, {kind}, SUM(revenue), SUM(orders), SUM(new_customers)
                                                        FROM sales_daily GROUP BY 1, 2, 3, 4 HAVING COUNT(DISTINCT day) = 7"""):
        for key in ("all", m):
            r = wk.setdefault((key, w), {"week": w, "market": key, "revenue": 0, "organic": 0, "owned": 0, "paid": 0, "orders": 0, "new_customers": 0,
                                         "gross_margin": 0, "spend": 0})
            r["revenue"] += rev
            r[k] += rev
            r["orders"] += orders
            r["new_customers"] += newc
            r["gross_margin"] += rev * margin[l]
    for w, m, sp in db.execute("SELECT date(day, 'weekday 0', '-6 days'), market, SUM(spend) FROM ad_daily GROUP BY 1, 2 HAVING COUNT(DISTINCT day) = 7"):
        for key in ("all", m):
            if (key, w) in wk:
                wk[(key, w)]["spend"] += sp
    weekly = {}
    for (key, w), r in sorted(wk.items(), key=lambda x: x[0][1]):
        r = {k: (round(v) if isinstance(v, float) else v) for k, v in r.items()}
        r["mer"] = round(r["revenue"] / r["spend"], 2) if r["spend"] else None
        r["cac"] = round(r["spend"] / r["new_customers"], 2) if r["new_customers"] else None
        r["profit"] = round(r["gross_margin"] - r["spend"])
        weekly.setdefault(key, []).append(r)
    asof = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
    mk = []
    for m, p in MARKETS.items():
        now = db.execute("SELECT SUM(revenue) FROM sales_daily WHERE market = ? AND day > date(?, '-28 days')", (m, asof)).fetchone()[0] or 0
        ly = db.execute("SELECT SUM(revenue) FROM sales_daily WHERE market = ? AND day > date(?, '-392 days') AND day <= date(?, '-364 days')", (m, asof, asof)).fetchone()[0]
        sp = db.execute("SELECT SUM(spend) FROM ad_daily WHERE market = ? AND day > date(?, '-28 days')", (m, asof)).fetchone()[0] or 0
        mk.append({"market": m, "lat": p["lat"], "lon": p["lon"], "revenue": round(now), "spend": round(sp), "mer": round(now / sp, 2) if sp else None,
                   "yoy_pct": round(100 * (now / ly - 1), 1) if ly else None, "new": bool(p["launched"])})
    # response curves: revenue change when a channel's spend is scaled by k, from the fitted elasticity
    curves = {f"{f['market']}|{f['line']}": {"r2": f["r2"], "revenue": f["weekly_revenue"], "channels": {
        c: {"spend": v["weekly_spend"], "e": v["elasticity"], "mroas": v["marginal_roas"],
            "pts": [[k, round(f["weekly_revenue"] * ((k ** v["elasticity"]) - 1))] for k in (0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2)]}
        for c, v in f["channels"].items()}} for f in fits}
    # engine validation against the simulation's hidden truth (possible only in a simulation)
    truth_path = hub.parent / f"{hub.stem}.truth.json"
    val = []
    if truth_path.is_file():
        t = json.loads(truth_path.read_text())
        for f in fits:
            aov = LINES[f["line"]]["aov"]
            for c, v in f["channels"].items():
                cv = t["curves"].get(f"{f['market']}|{f['line']}|{c}")
                if not cv or not v["weekly_spend"]:
                    continue
                s_ = v["weekly_spend"] / 7
                k, h, vm = cv["k"], cv["h"], cv["vmax"]
                true_m = vm * h * k ** h * s_ ** (h - 1) / (k ** h + s_ ** h) ** 2 * aov
                val.append({"market": f["market"], "line": f["line"], "channel": c, "est": v["marginal_roas"], "true": round(true_m, 2)})
    th = list(voc.THEMES)
    vm = {}
    for m, theme, n in db.execute("""SELECT v.market, l.theme, COUNT(*) FROM voc_items v JOIN voc_labels l USING (item_id)
                                     WHERE v.day > date((SELECT MAX(day) FROM voc_items), '-28 days') GROUP BY 1, 2"""):
        vm.setdefault(m, {})[theme] = n
    voc_matrix = {"themes": [x for x in th if not x.startswith("praise") and x != "other"],
                  "rows": [{"market": m, **{x: round(100 * vm[m].get(x, 0) / max(1, sum(vm[m].values())), 1) for x in th}} for m in vm]}
    bench_metrics = {}
    for metric in ("checkout_to_order_ios_pct", "checkout_to_order_android_pct", "mer", "organic_share_pct", "repeat_share_pct", "revenue_per_day"):
        rows = [benchmarks.benchmark(db, m, metric, None, 28) for m in MARKETS]
        bench_metrics[metric] = [{k: r.get(k) for k in ("market", "value", "same_period_last_year", "peer_range", "peer_median", "outside_peer_range")} for r in rows]
    rain = [{"market": m, "days": sorted([[d, v[1]] for d, v in fc.get(m, {}).items() if d > asof])[:14]} for m in MARKETS] if fc else []
    share = []
    for c in PAID:
        sp = db.execute("SELECT SUM(spend) FROM ad_daily WHERE creative = ? AND day > date(?, '-28 days')", (c, asof)).fetchone()[0] or 0
        rv = db.execute("SELECT SUM(revenue) FROM sales_daily WHERE channel = ? AND day > date(?, '-28 days')", ("paid:" + c, asof)).fetchone()[0] or 0
        share.append({"channel": c, "spend": round(sp), "revenue": round(rv)})
    # impact waterfall: each decision alone, then what combining them changes (interactions, guardrail deferrals)
    alone = [{"label": f"#{d['rank']} {d['type'].replace('_', ' ')}", "rank": d["rank"], "value": (d["change"] or {}).get("gross_profit", 0)}
             for d in outc["decisions"] if d.get("change") and abs((d["change"] or {}).get("gross_profit", 0)) > 0]
    total = outc["all_approved"]["change"]["gross_profit"]
    water = {"start": outc["all_approved"]["as_is"]["gross_profit"], "steps": sorted(alone, key=lambda x: -x["value"]),
             "combined_adjustment": round(total - sum(a["value"] for a in alone)), "end": outc["all_approved"]["with_decisions"]["gross_profit"]}
    routing = {}
    for r in team.get("routing", []):
        routing.setdefault(r["approver"], {"low": 0, "medium": 0, "high": 0})[r["risk"]] += 1
    return {"weekly": weekly, "market_map": mk, "curves": curves, "validation": val, "r2": [f["r2"] for f in fits], "voc_matrix": voc_matrix,
            "bench_metrics": bench_metrics, "rain_forecast": rain, "channel_share": share, "waterfall": water, "routing_by_role": routing,
            "targets": {r[0]: r[1] for r in db.execute("SELECT metric, target FROM targets")}}


def catalog_rollback(kind: str) -> str:
    from ..actions import catalog
    return catalog.CATALOG.get(kind, catalog.CATALOG["manual"]).rollback


def memo_view(path: Path | None, seed: int | None = None) -> dict | None:
    if not path or not path.is_file():
        return None
    d = json.loads(path.read_text())
    if "runs" in d:  # an eval result file: take the run for the seed
        run = next(r for r in d["runs"] if seed is None or r["seed"] == seed)
        return {**run["memo"], "_meta": {"turns": run["turns"], "comparisons": run["comparisons"], "cost_usd": run["cost_usd"]}}
    return {**d["memo"], "_meta": {"turns": d["turns"], "comparisons": len(d["comparisons"]), "model": d.get("model")}}


def evals() -> list[dict]:
    """Latest result per scenario, plus every earlier run, so improvements and regressions both show."""
    out = []
    for f in sorted(glob.glob(str(ROOT / "evals" / "results" / "analyst-*.json"))) + sorted(glob.glob(str(ROOT / "evals" / "results" / "team-*.json"))):
        d = json.loads(Path(f).read_text())
        crit = sum(len(r["grades"]) for r in d["runs"])
        out.append({"scenario": d.get("scenario", "small"), "split": d.get("split", "dev"), "when": d["when"], "seeds": [r["seed"] for r in d["runs"]],
                    "passed": sum(g["pass"] for r in d["runs"] for g in r["grades"]), "criteria": crit, "mean_cost_usd": d.get("mean_cost_usd"),
                    "gross_profit_pct": [r["hard"]["quarter_gross_profit_change_pct"] for r in d["runs"] if r.get("hard", {}).get("quarter_gross_profit_change_pct") is not None]})
    return out


def build(out_dir: Path, views: list[dict], allow_stale: bool = False, snapshot: Path | None = None) -> Path:
    """Builds every view from its hub. With `snapshot`, also saves the derived data there, so the console can be rebuilt
    from a clone that has the reports but not the hubs (render_snapshot)."""
    data = {"built": date.today().isoformat(), "evals": evals(), "views": []}
    for v in views:
        if v.get("team"):
            ent = enterprise_view(Path(v["hub"]), Path(v["team"]), Path(v["outcomes"]))
            ent["deck"] = deck_view(Path(v["team"]), Path(v["outcomes"]), Path(v["loo"]), allow_stale=allow_stale)
            data["views"].append({"id": v["id"], "title": v["title"], "label": v["label"], "blurb": v["blurb"], "ent": ent})
            continue
        if v.get("loop"):
            data["views"].append({"id": v["id"], "title": v["title"], "label": v["label"], "blurb": v["blurb"],
                                  "loop": loop_view(Path(v["hub"]), Path(v["memo"]), Path(v["loop"]))})
            continue
        data["views"].append({"id": v["id"], "title": v["title"], "label": v["label"], "blurb": v["blurb"],
                              "hub": hub_view(Path(v["hub"]), v.get("until"), v.get("days", 7)),
                              "memo": memo_view(Path(v["memo"]) if v.get("memo") else None, v.get("seed"))})
    if snapshot:
        snapshot.write_text(json.dumps(data, ensure_ascii=False, default=str, indent=0))
    return _render(out_dir, data)


def render_snapshot(out_dir: Path, snapshot: Path) -> Path:
    """The console from saved data only: no hubs, no API key, no model calls."""
    if not snapshot.is_file():
        raise BuildError("GOS-101", f"{snapshot} is missing and no hub is available to build from. Fix: in a full checkout run "
                                    f"growth-os console (it writes the snapshot), or restore the file from the repository.")
    return _render(out_dir, json.loads(snapshot.read_text()))


def _render(out_dir: Path, data: dict) -> Path:
    for v in data["views"]:
        if (v.get("ent") or {}).get("deck", {}).get("stale"):
            print("WARNING: built with --allow-stale-loo; the deck is stamped stale and must not be released.")
    out_dir.mkdir(parents=True, exist_ok=True)
    # CSP-clean: code in app.js (allowed by script-src 'self'), data in a non-executing JSON block, no inline script
    tpl = TEMPLATE.read_text()
    start, end = tpl.rindex("<script>"), tpl.rindex("</script>")
    code = TEMPLATE.with_name("deck.js").read_text() + "\n\n" + tpl[start + len("<script>"):end].strip() + "\n\n" + TEMPLATE.with_name("viz.js").read_text()
    (out_dir / "app.js").write_text(code)
    payload = json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")
    version = hashlib.sha256((payload + code + tpl).encode()).hexdigest()[:10]
    html = tpl[:start] + f'<script id="gos-data" type="application/json">{payload}</script>\n<script src="app.js?v={version}"></script>' + tpl[end + len("</script>"):]
    (out_dir / "index.html").write_text(html)
    return out_dir / "index.html"


DEFAULT_VIEWS = [
    {"id": "enterprise-team", "title": "Agent team · 12 markets", "label": "Synthetic business · real weather and holidays · simulated outcomes",
     "hub": "state/enterprise-7.sqlite", "team": "reports/team-enterprise-7.json", "outcomes": "reports/outcomes-enterprise-7.json",
     "loo": "reports/outcomes-loo-enterprise-7.json",
     "blurb": "A consumer brand in 12 cities and 4 product lines, about €3.3M of marketing a month across 8 paid channels plus email, SMS and "
              "organic. A team of AI agents read every source, the growth lead decided, and each decision was run forward a quarter against doing nothing."},
    {"id": "b2c", "title": "Consumer brand · 12 cities", "label": "Synthetic data", "hub": "LATEST_B2C_HUB", "days": 28,
     "memo": "LATEST_B2C_EVAL", "seed": None,
     "blurb": "A consumer brand selling time-limited products online in 12 cities: Meta, Google and TikTok plus email, organic and direct. 60 weeks of daily data. Situations a growth team meets are planted on purpose; two are traps where the right answer is to stay quiet."},
    {"id": "enterprise", "title": "Enterprise · 10 markets", "label": "Synthetic data", "hub": "state/eval-enterprise-7.sqlite", "days": 28,
     "memo": "LATEST_ENTERPRISE_EVAL", "seed": 7,
     "blurb": "A group running the same ads in 10 European markets: 26 weeks, ~196k sessions, ~13k leads. Problems are planted in three markets; six markets carry only noise."},
    {"id": "olist", "title": "B2B funnel + reviews", "label": "Real public data", "hub": "state/case-olist.sqlite", "days": 31, "until": date(2018, 5, 31),
     "memo": "reports/case-olist-voice.json",
     "blurb": "Olist's real marketing funnel (8,000 leads, 842 deals) joined to 3,000 classified customer reviews. Figures checked against the raw files."},
]


def default_views() -> list[dict]:
    latest = sorted(glob.glob(str(ROOT / "evals" / "results" / "analyst-enterprise-*.json")))
    out = []
    for v in DEFAULT_VIEWS:
        v = dict(v)
        if v.get("memo") == "LATEST_ENTERPRISE_EVAL":
            v["memo"] = latest[-1] if latest else None
        if v.get("memo") == "LATEST_B2C_EVAL":
            b2c = sorted(glob.glob(str(ROOT / "evals" / "results" / "analyst-b2c-heldout-*.json"))) or sorted(glob.glob(str(ROOT / "evals" / "results" / "analyst-b2c-dev-*.json")))
            v["memo"] = b2c[-1] if b2c else None
            if v["memo"]:
                v["seed"] = json.loads(Path(v["memo"]).read_text())["runs"][0]["seed"]
                v["hub"] = f"state/eval-b2c-{v['seed']}.sqlite"
        v["hub"] = str(ROOT / v["hub"])
        if v.get("team"):
            v["team"], v["outcomes"], v["loo"] = str(ROOT / v["team"]), str(ROOT / v["outcomes"]), str(ROOT / v["loo"])
            if not (Path(v["team"]).is_file() and Path(v["outcomes"]).is_file()):
                continue
        if v.get("loop"):
            v["loop"] = str(ROOT / v["loop"])
            if not Path(v["loop"]).is_file():
                continue
        if v.get("memo") and not Path(v["memo"]).is_absolute():
            v["memo"] = str(ROOT / v["memo"])
        if Path(v["hub"]).is_file():
            out.append(v)
    return out
