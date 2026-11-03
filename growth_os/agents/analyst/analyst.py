"""The analyst: reads the hub, checks its claims with real statistics, and hands back a growth memo.

It has three tools and no others: read-only SQL over the hub, a rate comparison, and submit_memo (a strict
schema, so every recommendation arrives with its evidence, confidence and the sample it needs). It cannot
change the website, the ads or anything else; a person decides what to act on.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from ...actions import catalog
from ...hub import store
from . import stats

MAX_TURNS = 20
MAX_ROWS = 200

SYSTEM = """You are the growth analyst for a business. Each period you read its marketing data hub and write a memo
for the people who run marketing and sales: what happened, why, what to do next, and what to test.

How you work:
- Start from the brief in the first message (it only contains the parts of the hub that hold data), then use run_sql
  to dig into whatever looks important. Query the views first; go to the raw tables only when you need more detail.
- Before you claim one rate beats another (one ad, page, channel or device against another), call compare_rates.
  Report its verdict honestly.
- When you scan many segments (markets, ads, pages) for changes, some will move by chance. Pass the number scanned as
  `comparisons`; a segment that is only significant before that correction is noise: call it stable, and never give it
  medium or high confidence. Only name a segment as changed when the corrected verdict says so.
- When a market or segment moves, drill down to which ad, page, device or step inside it caused the move before you
  recommend anything.
- Where revenue exists, size every finding in money (revenue or spend at stake per period) and rank by it. Before you
  call a revenue change, compare with the same period last year: a drop that happens every year is seasonality, not a
  problem. Platform-reported revenue is the platform's own claim; first-party sales are the truth, and the gap between
  them is itself worth reporting.
- Platform-reported and brand-search ROAS overstate what a campaign adds: many of those buyers would have come anyway.
  Before recommending more or less spend on a campaign, look for evidence of incrementality, such as the
  natural_experiments section (periods when a campaign was off and what happened to the market's total revenue).
- Judge a recently opened market against earlier launches at the same number of weeks since launch, not against
  established markets.
- ROAS and revenue are not proportions, so compare_rates does not apply to them. Use it for the rates underneath (click
  rate, checkout-to-order rate, conversion), and use the weekly series and last year for the rest. Small samples are normal here; say "too little data to tell" when that is the case,
  and say how much more data would settle it.
- Never invent numbers. Every figure in the memo must come from the brief, a query or compare_rates.
- Read the business context for what the stages mean. Where present: leads for Instant Form ads are Meta's count
  (form_leads), leads for website ads come from the site, and "qualified" means a demo was sent. Money is in the
  account currency.
- Watch for selection effects: a field that only exists for won deals (owner, lead type, segment) cannot explain
  why deals are won, and recent cohorts have had less time to close. Say so when it limits a conclusion.
- Recommendations must be concrete actions the team can take in the next period, ranked by expected impact on
  qualified outcomes (won deals, revenue, purchases) per unit of spend or effort. Prefer cheap, reversible actions.
  Do not recommend raising total spend unless the data clearly supports it.
- Experiments: only propose a test the volume can finish; give the sample per version and the weeks it would take at
  the current volume. Where the website is cookieless, a test runs as separate ads pointing at different pages.
- Every recommendation carries metric_sql, a query that measures its success metric, so the outcome is checked later
  without anyone having to remember. Test it with run_sql before you submit; it must return one row with a column named
  value, over a rolling window anchored on the latest day in the data.
- Manage to the targets when present (targets, market_economics_28d): MER is gross revenue / all marketing spend
  (marketing as a share of gross revenue is its inverse), blended CAC is all spend / new customers, payback_orders is how
  many first orders' gross margin it takes to cover CAC. Name the markets and ads that miss a target and by how much.
- attribution_28d shows several answers to "what did each channel bring in?". Last click over-credits closing channels
  (brand search, direct, email); platforms over-claim; the data-driven share and natural experiments are closer to what a
  channel adds. Where they disagree on a channel that matters, recommend the holdout that would settle it.
- why_not_buy_28d is the why-not-buy engine: causes found in the funnel, session behaviour, exit survey and stock data,
  with the money at stake where it can be sized. Use it to explain lost conversions, and check it with run_sql
  (events_daily, ux_daily, exit_survey, stock_events, products) before you rely on it.
- Every recommendation carries an `execution`: the one catalogue action that carries it out, with a real target from
  the hub (an ad_id, market, product_id, page, team or role). The system runs it automatically once the named role
  approves, so be exact and conservative: the smallest change that tests the idea, within the catalogue's limits.
  Bugs and fixes outside marketing go to a team as open_ticket with the evidence in note. If nothing in the catalogue
  fits, use manual. submit_memo is checked and returned with errors if a target does not exist.
- Read past_decisions in the brief when present: what people approved, what they rejected and why, and what happened
  after. Do not re-propose a rejected action unless new evidence answers the reason given; say so when you do.
- When you have what you need, call submit_memo exactly once. Do not write the memo as plain text.

""" + catalog.prompt_text()

TOOLS = [
    {
        "name": "run_sql",
        "description": "Run one read-only SQLite SELECT (or WITH ... SELECT) against the hub and get up to 200 rows back as JSON. "
                       "Use it to check numbers and drill into a finding.",
        "input_schema": {"type": "object", "properties": {"sql": {"type": "string", "description": "A single SELECT statement."}},
                         "required": ["sql"], "additionalProperties": False},
        "strict": True,
    },
    {
        "name": "compare_rates",
        "description": "Compare two conversion rates (A = baseline, B = challenger) with a two-proportion z-test. Returns both rates "
                       "with 95% intervals, the p-value, a verdict and the sample per arm needed to confirm the observed lift. When the "
                       "comparison comes from scanning several segments for the same kind of change (markets, ads, pages), pass how many "
                       "were scanned as `comparisons`, so chance swings are not reported as changes.",
        "input_schema": {"type": "object", "properties": {
            "label": {"type": "string", "description": "What is being compared, e.g. 'form start rate: mobile vs desktop'."},
            "a_successes": {"type": "integer"}, "a_n": {"type": "integer"},
            "b_successes": {"type": "integer"}, "b_n": {"type": "integer"},
            "comparisons": {"type": "integer", "description": "How many segments were scanned for this kind of change; 1 if this comparison was planned."},
        }, "required": ["label", "a_successes", "a_n", "b_successes", "b_n", "comparisons"], "additionalProperties": False},
        "strict": True,
    },
    {
        "name": "submit_memo",
        "description": "Hand in the growth memo. Call once, at the end.",
        "input_schema": {
            "type": "object",
            "properties": {
                "headline": {"type": "string", "description": "One sentence: the most important thing this period."},
                "data_sufficiency": {"type": "object", "properties": {
                    "verdict": {"type": "string", "enum": ["too_little", "directional", "solid"]},
                    "explanation": {"type": "string"},
                }, "required": ["verdict", "explanation"], "additionalProperties": False},
                "kpis": {"type": "array", "description": "The period's key numbers, each compared with the previous period.", "items": {
                    "type": "object", "properties": {
                        "name": {"type": "string"}, "value": {"type": "string"}, "previous": {"type": "string"}, "note": {"type": "string"},
                    }, "required": ["name", "value", "previous", "note"], "additionalProperties": False}},
                "findings": {"type": "array", "items": {"type": "object", "properties": {
                    "title": {"type": "string"},
                    "evidence": {"type": "string", "description": "The numbers behind it, with n."},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                }, "required": ["title", "evidence", "confidence"], "additionalProperties": False}},
                "recommendations": {"type": "array", "description": "Ranked, most impact first.", "items": {"type": "object", "properties": {
                    "action": {"type": "string"},
                    "why": {"type": "string"},
                    "expected_impact": {"type": "string"},
                    "effort": {"type": "string", "enum": ["S", "M", "L"]},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "how_to_measure": {"type": "string"},
                    "metric_sql": {"type": "string", "description": "One read-only SELECT over the hub returning a single row with one numeric column named "
                                   "value: the metric this action should move, over a rolling window ending at the latest day in the data "
                                   "(e.g. WHERE day > date((SELECT MAX(day) FROM ad_daily), '-14 days')), so it can be re-run unchanged later."},
                    "check_after_days": {"type": "integer", "description": "When to check whether the metric moved, in days."},
                    "direction": {"type": "string", "enum": ["up", "down"], "description": "Which way the metric should move if the action works."},
                    "execution": catalog.schema(),
                }, "required": ["action", "why", "expected_impact", "effort", "confidence", "how_to_measure", "metric_sql", "check_after_days", "direction",
                                "execution"],
                "additionalProperties": False}},
                "experiments": {"type": "array", "items": {"type": "object", "properties": {
                    "hypothesis": {"type": "string"},
                    "variant": {"type": "string", "description": "What changes in version B."},
                    "metric": {"type": "string"},
                    "sample_per_version": {"type": "integer"},
                    "weeks_at_current_traffic": {"type": "number"},
                }, "required": ["hypothesis", "variant", "metric", "sample_per_version", "weeks_at_current_traffic"], "additionalProperties": False}},
                "questions_for_owner": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["headline", "data_sufficiency", "kpis", "findings", "recommendations", "experiments", "questions_for_owner"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

_SELECT = re.compile(r"^\s*(with|select)\b", re.I)
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum)\b", re.I)


@dataclass
class Run:
    memo: dict | None = None
    queries: list[dict] = field(default_factory=list)
    comparisons: list[dict] = field(default_factory=list)
    turns: int = 0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    brief: dict = field(default_factory=dict)
    model: str = ""
    stop: str = ""
    rejected_submits: int = 0


def run_sql(db: sqlite3.Connection, sql: str) -> str:
    sql = sql.strip().rstrip(";")
    if not _SELECT.match(sql) or _FORBIDDEN.search(sql) or ";" in sql:
        return json.dumps({"error": "only one read-only SELECT is allowed"})
    try:
        cur = db.execute(sql)
        rows = cur.fetchmany(MAX_ROWS + 1)
    except sqlite3.Error as e:
        return json.dumps({"error": str(e)})
    out = [dict(r) for r in rows[:MAX_ROWS]]
    return json.dumps({"rows": out, "truncated": len(rows) > MAX_ROWS}, default=str)


def _rows(db: sqlite3.Connection, sql: str, *p) -> list[dict]:
    return [dict(r) for r in db.execute(sql, p).fetchall()]


def _has(db: sqlite3.Connection, table: str, where: str = "1") -> bool:
    return db.execute(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {where})").fetchone()[0] == 1


def _ly(d: str) -> str:
    return (date.fromisoformat(d) - timedelta(days=364)).isoformat()


def natural_experiments(db: sqlite3.Connection, min_days: int = 7) -> list[dict]:
    """Campaigns that went dark for a week or more while normally spending: what the market's total revenue, and its
    organic and direct revenue, did while they were off, against the two weeks before and after. A cheap incrementality test."""
    out = []
    for (ad_id, market, campaign) in db.execute("""SELECT ad_id, MAX(market), MAX(campaign) FROM ad_daily GROUP BY ad_id
                                                   HAVING SUM(spend = 0) >= ? AND SUM(spend > 0) >= 28""", (min_days,)).fetchall():
        days = [r[0] for r in db.execute("SELECT day FROM ad_daily WHERE ad_id = ? AND spend = 0 ORDER BY day", (ad_id,))]
        runs, start, prev = [], days[0], days[0]
        for d in days[1:] + [None]:
            if d and date.fromisoformat(d) - date.fromisoformat(prev) == timedelta(days=1):
                prev = d
                continue
            if (date.fromisoformat(prev) - date.fromisoformat(start)).days + 1 >= min_days:
                runs.append((start, prev))
            if d:
                start = prev = d
        for a, z in runs[-3:]:
            n = (date.fromisoformat(z) - date.fromisoformat(a)).days + 1
            before = ((date.fromisoformat(a) - timedelta(days=n)).isoformat(), (date.fromisoformat(a) - timedelta(days=1)).isoformat())
            after = ((date.fromisoformat(z) + timedelta(days=1)).isoformat(), (date.fromisoformat(z) + timedelta(days=n)).isoformat())
            row = {"campaign": campaign, "ad_id": ad_id, "market": market, "off_from": a, "off_to": z, "days_off": n}
            for label, (x, y) in (("before", before), ("during", (a, z)), ("after", after)):
                r = db.execute("""SELECT ROUND(SUM(revenue)), ROUND(SUM(CASE WHEN channel IN ('organic', 'direct') THEN revenue ELSE 0 END)),
                                  ROUND(SUM(CASE WHEN ad_id = ? THEN revenue ELSE 0 END)) FROM sales_daily WHERE market = ? AND day BETWEEN ? AND ?""",
                               (ad_id, market, x, y)).fetchone()
                row[f"market_revenue_{label}"], row[f"organic_direct_revenue_{label}"], row[f"campaign_revenue_{label}"] = r
            sp = db.execute("SELECT ROUND(SUM(spend)) FROM ad_daily WHERE ad_id = ? AND day BETWEEN ? AND ?", (ad_id, *before)).fetchone()[0]
            row["campaign_spend_before"] = sp
            out.append(row)
    return out


def commerce_brief(db: sqlite3.Connection, c: tuple, p: tuple) -> dict:
    """Revenue, ROAS, channels, creatives, devices, pacing and launches: this period, the previous one, and the same period last year."""
    ly = (_ly(c[0]), _ly(c[1]))
    win = lambda a, col: f"SUM(CASE WHEN day BETWEEN '{a[0]}' AND '{a[1]}' THEN {col} ELSE 0 END)"
    out = {}
    out["markets"] = _rows(db, f"""WITH s AS (SELECT market, {win(c, 'revenue')} AS revenue_now, {win(p, 'revenue')} AS revenue_before, {win(ly, 'revenue')} AS revenue_last_year,
            {win(c, "CASE WHEN channel LIKE 'paid:%' THEN revenue END")} AS paid_revenue_now, {win(p, "CASE WHEN channel LIKE 'paid:%' THEN revenue END")} AS paid_revenue_before,
            {win(c, 'orders')} AS orders_now, {win(p, 'orders')} AS orders_before, {win(c, 'new_customers')} AS new_customers_now, {win(p, 'new_customers')} AS new_customers_before
            FROM sales_daily GROUP BY market),
        a AS (SELECT market, {win(c, 'spend')} AS spend_now, {win(p, 'spend')} AS spend_before FROM ad_daily GROUP BY market)
        SELECT s.market, ROUND(spend_now) AS spend_now, ROUND(spend_before) AS spend_before, ROUND(revenue_now) AS revenue_now, ROUND(revenue_before) AS revenue_before,
               ROUND(revenue_last_year) AS revenue_same_period_last_year, ROUND(paid_revenue_now) AS paid_revenue_now, ROUND(paid_revenue_before) AS paid_revenue_before,
               ROUND(paid_revenue_now / NULLIF(spend_now, 0), 2) AS paid_roas_now, ROUND(paid_revenue_before / NULLIF(spend_before, 0), 2) AS paid_roas_before,
               orders_now, orders_before, new_customers_now, new_customers_before
        FROM s LEFT JOIN a USING (market) ORDER BY revenue_now DESC""")
    out["channels_by_market"] = _rows(db, f"""SELECT market, channel, ROUND({win(c, 'revenue')}) AS revenue_now, ROUND({win(p, 'revenue')}) AS revenue_before,
        {win(c, 'orders')} AS orders_now, {win(p, 'orders')} AS orders_before FROM sales_daily GROUP BY market, channel ORDER BY market, revenue_now DESC""")
    out["creatives_now_vs_before"] = _rows(db, f"""WITH a AS (SELECT ad_id, MAX(market) AS market, MAX(platform) AS platform, MAX(creative) AS creative,
            {win(c, 'spend')} AS spend_now, {win(p, 'spend')} AS spend_before, {win(c, 'impressions')} AS imp_now, {win(p, 'impressions')} AS imp_before,
            {win(c, 'link_clicks')} AS clicks_now, {win(p, 'link_clicks')} AS clicks_before,
            AVG(CASE WHEN day BETWEEN '{c[0]}' AND '{c[1]}' THEN frequency END) AS freq_now, AVG(CASE WHEN day BETWEEN '{p[0]}' AND '{p[1]}' THEN frequency END) AS freq_before
            FROM ad_daily GROUP BY ad_id),
        s AS (SELECT ad_id, {win(c, 'revenue')} AS rev_now, {win(p, 'revenue')} AS rev_before FROM sales_daily WHERE ad_id != '' GROUP BY ad_id)
        SELECT a.market, a.platform, a.creative, a.ad_id, ROUND(spend_now) AS spend_now, ROUND(spend_before) AS spend_before, imp_now, imp_before, clicks_now, clicks_before,
               ROUND(freq_now, 2) AS frequency_now, ROUND(freq_before, 2) AS frequency_before, ROUND(rev_now) AS revenue_now, ROUND(rev_before) AS revenue_before,
               ROUND(rev_now / NULLIF(spend_now, 0), 2) AS roas_now, ROUND(rev_before / NULLIF(spend_before, 0), 2) AS roas_before
        FROM a LEFT JOIN s USING (ad_id) ORDER BY a.market, a.platform, a.creative""")
    out["checkout_by_device"] = _rows(db, f"""SELECT market, device, {win(c, 'checkouts')} AS checkouts_now, {win(c, 'orders')} AS orders_now,
        {win(p, 'checkouts')} AS checkouts_before, {win(p, 'orders')} AS orders_before FROM sales_daily GROUP BY market, device ORDER BY market, device""")
    out["platform_vs_first_party"] = _rows(db, f"""WITH a AS (SELECT platform, {win(c, 'spend')} AS spend, {win(c, 'platform_revenue')} AS platform_reported FROM ad_daily GROUP BY platform),
        s AS (SELECT CASE WHEN channel = 'paid:meta' THEN 'meta' WHEN channel = 'paid:tiktok' THEN 'tiktok' WHEN channel LIKE 'paid:google%' THEN 'google' END AS platform,
              {win(c, 'revenue')} AS first_party FROM sales_daily WHERE channel LIKE 'paid:%' GROUP BY 1)
        SELECT platform, ROUND(spend) AS spend, ROUND(platform_reported) AS platform_reported_revenue, ROUND(first_party) AS first_party_revenue,
               ROUND(platform_reported / NULLIF(first_party, 0), 2) AS platform_overclaim_ratio FROM a JOIN s USING (platform)""")
    out["natural_experiments"] = natural_experiments(db)
    if _has(db, "products"):
        out["products_on_sale"] = _rows(db, "SELECT market, name, capacity, sold, sold_pct, window_elapsed_pct, days_left, unsold_value FROM v_product_pacing ORDER BY days_left")
    if _has(db, "budgets"):
        out["budget_pacing_this_month"] = _rows(db, "SELECT * FROM v_budget_pacing ORDER BY spent_pct DESC")
    if _has(db, "markets"):
        out["launch_curves_recent_markets"] = _rows(db, """SELECT market, weeks_since_launch, ROUND(revenue) AS revenue, ROUND(spend) AS spend FROM v_launch_cohorts
            WHERE weeks_since_launch <= (SELECT MAX(weeks_since_launch) FROM v_launch_cohorts WHERE market = (SELECT market FROM markets ORDER BY launched_on DESC LIMIT 1)) + 1
            ORDER BY weeks_since_launch, market""")
    return out


def brief(db: sqlite3.Connection, until: date, days: int = 7) -> dict:
    """The starting picture: this period against the one before, plus the breakdowns this hub has data for."""
    cur_s, prev_s, prev_u = until - timedelta(days=days - 1), until - timedelta(days=2 * days - 1), until - timedelta(days=days)
    c, p = (cur_s.isoformat(), until.isoformat()), (prev_s.isoformat(), prev_u.isoformat())
    tot = """SELECT ROUND(SUM(spend), 2) AS spend, SUM(impressions) AS impressions, SUM(link_clicks) AS link_clicks, SUM(sessions) AS sessions,
             SUM(bounces) AS bounces, SUM(form_starts) AS form_starts, SUM(form_errors) AS form_errors, SUM(form_submits) AS form_submits,
             SUM(meta_form_leads) AS meta_form_leads, SUM(leads) AS leads, SUM(qualified) AS qualified, SUM(won) AS won
             FROM v_funnel_daily WHERE day BETWEEN ? AND ?"""
    b: dict = {"period": {"since": c[0], "until": c[1], "previous_since": p[0], "previous_until": p[1], "days": days},
               "data_window": _rows(db, "SELECT MIN(day) AS first_day, MAX(day) AS last_day FROM v_funnel_daily")[0],
               "sources": _rows(db, "SELECT DISTINCT source, note FROM sync_log")}
    if _has(db, "v_funnel_daily"):
        b["totals_this_period"] = _rows(db, tot, *c)[0]
        b["totals_previous_period"] = _rows(db, tot, *p)[0]
    commerce = _has(db, "sales_daily")
    if _has(db, "ad_daily") and not commerce:
        b["ads_all_time"] = _rows(db, "SELECT * FROM v_ad_funnel ORDER BY spend DESC LIMIT 30")
        b["agent_actions_this_period"] = _rows(db, "SELECT created_at, ad_name, rule, status FROM agent_actions WHERE substr(created_at, 1, 10) >= ?", c[0])
    if _has(db, "web_sessions"):
        b["landing_this_period"] = _rows(db, """SELECT landing, channel, SUM(sessions) AS sessions, SUM(bounces) AS bounces, SUM(scroll_50) AS reached_half,
             SUM(form_starts) AS form_starts, SUM(form_submits) AS form_submits FROM web_sessions WHERE day BETWEEN ? AND ?
             GROUP BY landing, channel ORDER BY sessions DESC LIMIT 25""", *c)
        b["devices_this_period"] = _rows(db, """SELECT device, SUM(sessions) AS sessions, SUM(form_starts) AS form_starts, SUM(form_submits) AS form_submits
             FROM web_sessions WHERE day BETWEEN ? AND ? GROUP BY device""", *c)
    if _has(db, "leads"):
        b["pipeline_all_time"] = _rows(db, "SELECT * FROM v_pipeline ORDER BY leads DESC LIMIT 30")
        b["leads_by_month"] = _rows(db, "SELECT substr(day, 1, 7) AS month, COUNT(*) AS leads, SUM(qualified) AS qualified, SUM(won) AS won FROM v_qualified GROUP BY month")
    if _has(db, "leads", "hours_to_contact IS NOT NULL"):
        # speed to lead: how often a lead reaches a demo depending on how fast it was first contacted
        b["qualified_by_contact_speed_all_time"] = _rows(db, """SELECT CASE WHEN hours_to_contact IS NULL THEN 'not contacted'
             WHEN hours_to_contact <= 2 THEN 'within 2 h' WHEN hours_to_contact <= 24 THEN '2-24 h' ELSE 'over 24 h' END AS first_contact,
             COUNT(*) AS leads, SUM(qualified) AS qualified FROM v_qualified GROUP BY first_contact""")
    if _has(db, "leads", "landing IS NOT NULL OR owner IS NOT NULL"):
        b["lead_channels_all_time"] = _rows(db, "SELECT * FROM v_lead_channels ORDER BY leads DESC")
        b["landing_pages_summary"] = _rows(db, """SELECT COUNT(*) AS pages, SUM(leads >= 30) AS pages_with_30_plus_leads, SUM(won = 0) AS pages_with_no_win,
             MAX(leads) AS most_leads_on_one_page FROM v_lead_landing""")[0]
        b["landing_pages_top_by_leads"] = _rows(db, "SELECT * FROM v_lead_landing ORDER BY leads DESC LIMIT 20")
        b["owners_top"] = _rows(db, "SELECT * FROM v_owners ORDER BY won DESC LIMIT 15")
    if commerce:
        b.update(commerce_brief(db, c, p))
    elif db.execute("SELECT COUNT(DISTINCT market) FROM v_market_daily WHERE market != ''").fetchone()[0] > 1:
        mk = """SELECT market, ROUND(SUM(spend), 2) AS spend, SUM(sessions) AS sessions, SUM(form_starts) AS form_starts, SUM(form_errors) AS form_errors,
                SUM(form_submits) AS form_submits, SUM(leads) AS leads, SUM(qualified) AS qualified, SUM(won) AS won
                FROM v_market_daily WHERE day BETWEEN ? AND ? GROUP BY market ORDER BY spend DESC"""
        b["markets_this_period"] = _rows(db, mk, *c)
        b["markets_previous_period"] = _rows(db, mk, *p)
        if _has(db, "ad_daily"):
            # each ad inside each market, this period against the previous one, so a single failing ad is visible
            am = """SELECT a.market, l.ad_id, COALESCE(ads.ad_name, l.ad_id) AS ad_name,
                    SUM(l.day BETWEEN ? AND ?) AS leads_now, SUM(CASE WHEN l.day BETWEEN ? AND ? THEN l.qualified ELSE 0 END) AS qualified_now,
                    SUM(l.day BETWEEN ? AND ?) AS leads_before, SUM(CASE WHEN l.day BETWEEN ? AND ? THEN l.qualified ELSE 0 END) AS qualified_before
                    FROM v_qualified l JOIN (SELECT DISTINCT ad_id, market FROM ad_daily) a USING (ad_id) LEFT JOIN ads USING (ad_id)
                    WHERE l.ad_id != '' GROUP BY a.market, l.ad_id ORDER BY a.market, l.ad_id"""
            b["ads_by_market_now_vs_before"] = _rows(db, am, *c, *c, *p, *p)
    if _has(db, "voice_items"):
        b["voice_themes"] = _rows(db, "SELECT * FROM v_voice_themes ORDER BY items DESC")
        b["voice_by_segment"] = _rows(db, "SELECT * FROM v_voice_by_segment ORDER BY items DESC")
        b["voice_note"] = ("voice_items are classified customer texts (labels and English paraphrases only). segment says which group "
                           "the text is about; see the business context for what it means.")
    if _has(db, "ai_answers"):
        b["ai_share_of_voice_unbranded"] = _rows(db, "SELECT * FROM v_ai_share_of_voice ORDER BY day DESC, mentioned DESC")
        b["ai_sites_used_as_sources"] = _rows(db, "SELECT * FROM v_ai_cited_sites ORDER BY day DESC, answers_citing DESC LIMIT 20")
        b["ai_note"] = ("AI visibility: buyer questions asked to an AI assistant with web search, several runs each. mention_rate_pct is "
                        "over unbranded questions only. One assistant at one point in time; answers vary between runs.")
    if _has(db, "ad_segments"):
        seg = """SELECT {k}, SUM(ads) AS ads, ROUND(SUM(spend), 2) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
                 SUM(conversions) AS conversions, SUM(approved) AS approved,
                 ROUND(SUM(spend) / NULLIF(SUM(approved), 0), 2) AS cost_per_approved FROM v_ad_segments GROUP BY {k} ORDER BY spend DESC LIMIT 25"""
        for k in ("campaign", "age", "gender", "interest"):
            b[f"ad_segments_by_{k}"] = _rows(db, seg.format(k=k))
    b.update(growth_brief(db))
    b.update(decisions_brief(db))
    return b


def growth_brief(db: sqlite3.Connection) -> dict:
    """Unit economics against targets, attribution lenses and the why-not-buy engine, where the hub has the data."""
    out: dict = {}
    try:
        if _has(db, "targets"):
            out["targets"] = _rows(db, "SELECT scope, metric, target, direction FROM targets")
        if _has(db, "sales_daily") and _has(db, "ad_daily"):
            out["market_economics_28d"] = _rows(db, "SELECT * FROM v_market_economics_28d ORDER BY gross_revenue DESC")
            out["worst_ads_by_cpa_28d"] = _rows(db, """SELECT ad_id, market, platform, creative, spend, cpm, ctr_pct, cpc, cpa, roas, platform_roas
                 FROM v_ad_economics_28d WHERE spend > 500 ORDER BY cpa DESC LIMIT 12""")
        if _has(db, "journeys"):
            from ... import attribution
            out["attribution_28d"] = {"note": "Shares of credit per channel. last_click_pct is first-party sales; journeys_last_touch_pct and "
                                              "data_driven_pct (Markov removal effect) are computed on the same journey sample; "
                                              "platform_overclaim_x is platform-claimed revenue / first-party revenue.",
                                      "channels": attribution.compare(db),
                                      "brand_search_holdout_plan": attribution.holdout_plan(db, "paid:google_brand")}
        if _has(db, "events_daily"):
            from ... import whynot
            out["why_not_buy_28d"] = [{**c, "evidence": c["evidence"][:4]} for c in whynot.engine(db)[:10]]
            out["funnel_steps_by_device_28d"] = _rows(db, """SELECT device, step, SUM(users) AS users FROM events_daily
                 WHERE day > date((SELECT MAX(day) FROM events_daily), '-28 days') GROUP BY device, step""")
    except sqlite3.Error as e:
        out["growth_brief_error"] = str(e)
    return out


def decisions_brief(db: sqlite3.Connection) -> dict:
    """What people decided about earlier recommendations, what the system executed, and what came of it."""
    out: dict = {}
    try:
        if _has(db, "recommendations", "status != 'proposed'"):
            out["past_decisions"] = _rows(db, """SELECT memo_date, action, exec_type, exec_target, status, decided_by, reject_reason, executed_at,
                 baseline, outcome, verdict FROM recommendations WHERE status != 'proposed' ORDER BY memo_date DESC, rank LIMIT 30""")
        if _has(db, "work_items"):
            out["work_in_progress"] = _rows(db, "SELECT kind, target, note, status, opened_on, closed_on, result FROM work_items ORDER BY id DESC LIMIT 20")
        if _has(db, "account_state"):
            out["ad_account_changes"] = _rows(db, "SELECT ad_id, status, budget_mult, updated_at FROM account_state ORDER BY updated_at DESC LIMIT 30")
    except sqlite3.Error:
        pass  # an old hub without these tables
    return out


def analyse(db: sqlite3.Connection, until: date, *, business: str, model: str = "claude-opus-5-5", days: int = 7,
            context: str = "", client=None) -> Run:
    import anthropic

    client = client or anthropic.Anthropic(timeout=600, max_retries=3)
    run = Run(model=model)
    b = brief(db, until, days)
    run.brief = b
    intro = (f"Business: {business}.\n{context}\n\nThe hub schema (tables, views and what each column means):\n```sql\n{store.schema_text()}\n```\n\n"
             f"This week's brief:\n```json\n{json.dumps(b, ensure_ascii=False, default=str)}\n```\n"
             "Analyse it, check what matters with run_sql and compare_rates, then call submit_memo.")
    messages: list[dict] = [{"role": "user", "content": intro}]

    while run.turns < MAX_TURNS and run.memo is None:
        run.turns += 1
        resp = client.beta.messages.create(
            model=model, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
            output_config={"effort": "high"},
            cache_control={"type": "ephemeral"},  # the brief and history are resent each turn: read them from cache
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        run.input_tokens += resp.usage.input_tokens
        run.cache_read_tokens += resp.usage.cache_read_input_tokens or 0
        run.cache_write_tokens += resp.usage.cache_creation_input_tokens or 0
        run.output_tokens += resp.usage.output_tokens
        run.model, run.stop = resp.model, resp.stop_reason
        if resp.stop_reason == "refusal":
            break
        messages.append({"role": "assistant", "content": resp.content})
        calls = [c for c in resp.content if c.type == "tool_use"]
        if not calls:
            messages.append({"role": "user", "content": "Please hand in the memo now by calling submit_memo."})
            continue
        results = []
        for c in calls:
            if c.name == "run_sql":
                out = run_sql(db, str(c.input.get("sql", "")))
                run.queries.append({"sql": c.input.get("sql", ""), "result": out[:20000]})
            elif c.name == "compare_rates":
                try:
                    out_d = {"label": c.input["label"], **stats.compare_rates(int(c.input["a_successes"]), int(c.input["a_n"]),
                                                                           int(c.input["b_successes"]), int(c.input["b_n"]),
                                                                           int(c.input.get("comparisons", 1) or 1))}
                except (KeyError, TypeError, ValueError) as e:
                    out_d = {"error": f"bad input: {e}"}
                run.comparisons.append(out_d)
                out = json.dumps(out_d)
            elif c.name == "submit_memo":
                errs = [f"recommendation {i}: {e}" for i, r in enumerate(c.input.get("recommendations", []), 1)
                        for e in catalog.check(db, r.get("execution", {})).errors]
                if errs and run.rejected_submits < 2:
                    run.rejected_submits += 1
                    results.append({"type": "tool_result", "tool_use_id": c.id, "is_error": True,
                                    "content": "Not accepted. Fix these executions and call submit_memo again:\n" + "\n".join(errs)})
                    continue
                run.memo = dict(c.input)
                out = "Memo received."
            else:
                out = json.dumps({"error": f"unknown tool {c.name}"})
            results.append({"type": "tool_result", "tool_use_id": c.id, "content": out})
        left = MAX_TURNS - run.turns
        if run.memo is None and left <= 4:  # make sure the work ends in a memo, not in a cut-off
            results.append({"type": "text", "text": f"Turn budget: {left} turn(s) left. Stop exploring; finish checking metric_sql and call submit_memo."})
        messages.append({"role": "user", "content": results})
    return run
