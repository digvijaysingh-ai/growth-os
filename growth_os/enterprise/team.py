"""The agent team: specialists with dedicated roles, a growth lead who directs them and decides what to propose, and a
communications agent that briefs each stakeholder. All of them use the one tool layer in tools.py (also served over MCP).

  Benchmark analyst        compares every market with its own history, its peers and earlier launches; finds gaps
  Demand strategist        potential demand vs what is captured, weather and holiday effects, the 14-day outlook
  Customer voice analyst   what customers say (surveys, NPS, reviews, tickets) and where it explains a gap
  Media & budget planner   channel response curves, marginal ROAS, organic vs paid, platform claims, reallocations
  Growth lead              briefs the specialists, weighs their findings, and submits the decision memo: every
                           recommendation is one executable action from the catalogue, routed to the role that approves it
  Stakeholder comms        turns the decisions and the computed briefs into a short message per role
  Operations               the executor (actions/executor.py): rules, not a model, so nothing runs that was not approved

    growth-os team --hub state/enterprise-7.sqlite --out reports/team-enterprise-7.json
"""
from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..actions import catalog
from . import tools

import threading

MODEL = "claude-opus-5-5"
BUDGET = {"spent": 0.0, "cap": 10.0}   # USD per weekly run, across all agents; a run stops cleanly when it is reached
_lock = threading.Lock()
PRICE = {"in": 4.0, "out": 20.0, "cache_read": 0.20, "cache_write": 5.0}  # USD per million tokens

COMMON = """Rules for every member of the team:
- The data is a SYNTHETIC multi-market consumer brand (12 cities, 4 product lines: Home, Fashion drops, Beauty, Gifts), €50k–100k of
  marketing per line per market per month. Weather and public holidays in it are real.
- Never invent a number. Every figure you report comes from a tool result. Size findings in euros where the data allows.
- Before calling something a problem, check it against last year, peers and noise. Markets with only noise and seasonal dips that
  happen every year are not problems; say so when you see them.
- Be concise. Finish by calling submit_findings exactly once."""

SPECIALISTS = {
    "benchmark_analyst": ("Benchmark analyst", "You find where each market departs from what is normal for it: its own same period last year, "
                          "peer markets with a similar profile, and earlier launches at the same age for new markets. Scan every market on the "
                          "metrics that matter (revenue per day, MER, CPA, checkout-to-order overall and on each device, organic share, repeat share, "
                          "paid share), then drill into the outliers by line. Report each real gap with its benchmark and range."),
    "demand_strategist": ("Demand strategist", "You own one question: where is there demand the brand is not capturing, and what will demand do "
                          "next? Start from demand_potential (captured share of potential per market × line, against peers); for established "
                          "markets, a low captured share is a reach or budget gap, so check that line's marginal returns before calling it. Then "
                          "weather and holiday sensitivity, the next 14 days' forecast, and the model's holdout accuracy. Conversion faults (checkout, "
                          "stock) belong to other specialists: mention them only if they distort your numbers."),
    "customer_voice_analyst": ("Customer voice analyst", "You read what customers say (NPS comments, exit surveys, reviews, support tickets, already "
                               "labelled by theme) and find themes that are unusually frequent in a market or line, new against earlier weeks, "
                               "and tied to a business symptom. Quote the gist with voc_examples; give mentions and shares."),
    "media_budget_planner": ("Media & budget planner", "You decide where marketing money works. Quantify the portfolio-wide gain from the "
                             "reallocation plan (sum its expected gains) and where the model fits well, and say how sure the model is. Use the marketing-mix model (elasticities, "
                             "marginal ROAS per channel), organic vs paid trends, platform claims vs first-party revenue and budget pacing. Find "
                             "saturated channels, under-funded ones, channels whose platform-reported results far exceed what they add (compare "
                             "platform claims, first-party revenue and the model), lines where an extra euro earns most, and overspend. Propose specific moves with euros and the model's "
                             "expected gain, and say how sure the model is (r2, how far its estimate could be off)."),
}

FINDINGS_TOOL = {
    "name": "submit_findings", "strict": True,
    "description": "Hand your findings to the growth lead. Call once, at the end.",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["summary", "findings", "proposed_actions", "not_problems"],
                     "properties": {
                         "summary": {"type": "string", "description": "Two sentences: what matters most."},
                         "findings": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                      "required": ["title", "market", "line", "evidence", "money_at_stake_eur_per_month", "confidence"],
                                      "properties": {"title": {"type": "string"}, "market": {"type": "string"}, "line": {"type": "string"},
                                                     "evidence": {"type": "string", "description": "Numbers with their benchmark or test."},
                                                     "money_at_stake_eur_per_month": {"type": "number", "description": "0 if it cannot be sized."},
                                                     "confidence": {"type": "string", "enum": ["low", "medium", "high"]}}}},
                         "proposed_actions": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["action", "why"],
                                              "properties": {"action": {"type": "string"}, "why": {"type": "string"}}}},
                         "not_problems": {"type": "array", "items": {"type": "string"}, "description": "Things that look bad but are normal, and why."},
                     }},
}

LEAD_SYSTEM = """You are the growth lead of a multi-market consumer brand's growth team, and you run a team of AI specialists. Each week you
decide what the business should do, and every decision you propose is executed automatically once the right person approves it.

How you work:
1. Ask each specialist for their analysis (ask_benchmark_analyst, ask_demand_strategist, ask_customer_voice_analyst,
   ask_media_budget_planner). Ask them all in your first turn; give each a focused brief. Ask follow-ups only when findings conflict or a
   decision needs a number you do not have.
2. Weigh the findings: join findings from different specialists that describe the same situation into one decision, drop what is
   noise or seasonal, and rank by money at stake per month.
3. Check any number you rely on with run_sql when the specialists disagree or it drives a big decision.
4. Budget principles: when the media planner's model fits well in many places, propose applying its channel split across every
   market-line where the fit is good as ONE portfolio decision for leadership (apply_mix_plan with target 'all' or one market), capped
   per channel, rather than a few hand-picked lines. Where a market-line captures much less of its potential demand than peers AND its
   marginal returns are high, propose more budget for it (change_line_budget), funded by lines with low marginal returns. A weather
   rule only for lines whose measured weather effect is clearly positive.
5. Call submit_decisions once. Each recommendation carries exactly one executable action from the catalogue below, with real targets
   ('Market|Line|channel' for channel budgets). Prefer reversible, measurable moves; budget moves keep totals unless the evidence says
   the line deserves more. Problems marketing cannot fix go to the team that can, as open_ticket with the evidence in the note; name
   the market in the note. If nothing fits, use manual.
6. Every recommendation needs metric_sql: one read-only SELECT returning one row with a numeric column named value, over a rolling
   window ending at the latest day in the data, so the outcome can be checked later. Test it with run_sql first.

Roles that approve: Leadership, Growth manager, Paid media manager, CRM manager, Product owner, Finance. Never write "director".
Never invent a number. The data is synthetic; the weather and holidays are real.

""" + catalog.prompt_text()


@dataclass
class AgentRun:
    role: str
    output: dict | None = None
    turns: int = 0
    tool_calls: list = field(default_factory=list)
    transcript: list = field(default_factory=list)   # what the agent said between tool calls, and each call it made
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0})
    seconds: float = 0.0
    error: str = ""

    def cost(self) -> float:
        u = self.usage
        return round((u["input"] * PRICE["in"] + u["output"] * PRICE["out"] + u["cache_read"] * PRICE["cache_read"] + u["cache_write"] * PRICE["cache_write"]) / 1e6, 3)


def _loop(client, system: str, tool_defs: list, first: str, handle, submit: str, max_turns: int, effort: str, run: AgentRun) -> None:
    messages = [{"role": "user", "content": first}]
    t0 = time.time()
    while run.turns < max_turns and run.output is None:
        run.turns += 1
        resp = client.beta.messages.create(model=MODEL, max_tokens=16000, system=system, tools=tool_defs, messages=messages,
                                           output_config={"effort": effort}, cache_control={"type": "ephemeral"},
                                           betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        u = resp.usage
        run.usage["input"] += u.input_tokens
        run.usage["output"] += u.output_tokens
        run.usage["cache_read"] += u.cache_read_input_tokens or 0
        run.usage["cache_write"] += u.cache_creation_input_tokens or 0
        step = (u.input_tokens * PRICE["in"] + u.output_tokens * PRICE["out"] + (u.cache_read_input_tokens or 0) * PRICE["cache_read"]
                + (u.cache_creation_input_tokens or 0) * PRICE["cache_write"]) / 1e6
        with _lock:
            BUDGET["spent"] += step
            over = BUDGET["spent"] > BUDGET["cap"]
        run.transcript += [{"turn": run.turns, "text": b.text} for b in resp.content if b.type == "text" and b.text.strip()]
        run.transcript += [{"turn": run.turns, "call": b.name, "input": dict(b.input)} for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "refusal":
            run.error = "refusal"
            break
        if over:
            run.error = f"run cost cap of ${BUDGET['cap']:.0f} reached"
            break
        messages.append({"role": "assistant", "content": resp.content})
        calls = [c for c in resp.content if c.type == "tool_use"]
        if not calls:
            messages.append({"role": "user", "content": f"Please call {submit} now."})
            continue
        results = handle(calls)
        left = max_turns - run.turns
        if run.output is None and left <= 3:
            results.append({"type": "text", "text": f"Turn budget: {left} left. Finish and call {submit}."})
        messages.append({"role": "user", "content": results})
    run.seconds = round(time.time() - t0, 1)


def specialist(client, hub, role: str, brief: str, max_turns: int = 10) -> AgentRun:
    name, job = SPECIALISTS[role]
    run = AgentRun(role)
    system = f"You are the {name} on a growth team. {job}\n\n{COMMON}"
    defs = [tools.REGISTRY[t].schema() for t in tools.ROLES_TOOLS[role]] + [FINDINGS_TOOL]
    db = sqlite3.connect(f"file:{hub}?mode=ro", uri=True, check_same_thread=False)

    def handle(calls):
        out = []
        for c in calls:
            if c.name == "submit_findings":
                run.output = dict(c.input)
                out.append({"type": "tool_result", "tool_use_id": c.id, "content": "Received."})
                continue
            res = tools.call(db, c.name, dict(c.input))
            run.tool_calls.append({"tool": c.name, "input": dict(c.input), "result": res[:4000]})
            out.append({"type": "tool_result", "tool_use_id": c.id, "content": res})
        return out

    try:
        _loop(client, system, defs, f"Brief from the growth lead: {brief}", handle, "submit_findings", max_turns, "medium", run)
    except Exception as e:
        run.error = f"{type(e).__name__}: {e}"[:300]
    return run


def lead(client, hub, context: str, max_turns: int = 12) -> tuple[AgentRun, dict[str, list[AgentRun]]]:
    from ..agents.analyst.analyst import TOOLS as ANALYST_TOOLS
    memo_tool = next(t for t in ANALYST_TOOLS if t["name"] == "submit_memo")
    submit = {**memo_tool, "name": "submit_decisions",
              "description": "Hand in the week's decisions. Call once. Each recommendation carries one executable action (execution)."}
    ask = [{"name": f"ask_{r}", "strict": True, "description": f"Brief the {SPECIALISTS[r][0]} and get their findings back.",
            "input_schema": {"type": "object", "additionalProperties": False, "required": ["brief"], "properties": {"brief": {"type": "string"}}}}
           for r in SPECIALISTS]
    defs = ask + [tools.REGISTRY["run_sql"].schema(), submit]
    run = AgentRun("growth_lead")
    team: dict[str, list[AgentRun]] = {r: [] for r in SPECIALISTS}
    db = sqlite3.connect(f"file:{hub}?mode=ro", uri=True, check_same_thread=False)

    def handle(calls):
        asks = [c for c in calls if c.name.startswith("ask_")]
        with ThreadPoolExecutor(max_workers=4) as pool:  # specialists work in parallel
            done = dict(zip([c.id for c in asks], pool.map(lambda c: specialist(client, hub, c.name[4:], c.input["brief"]), asks)))
        out = []
        for c in calls:
            if c.name != "submit_decisions":
                run.tool_calls.append({"tool": c.name, "input": dict(c.input), "result": ""})
            if c.id in done:
                sr = done[c.id]
                team[c.name[4:]].append(sr)
                body = json.dumps(sr.output, ensure_ascii=False) if sr.output else json.dumps({"error": sr.error or "no findings returned"})
                out.append({"type": "tool_result", "tool_use_id": c.id, "content": body})
            elif c.name == "run_sql":
                out.append({"type": "tool_result", "tool_use_id": c.id, "content": tools.call(db, "run_sql", dict(c.input))})
            elif c.name == "submit_decisions":
                errs = [f"recommendation {i}: {e}" for i, r in enumerate(c.input.get("recommendations", []), 1)
                        for e in catalog.check(db, r.get("execution", {})).errors]
                if errs and getattr(run, "_resubmits", 0) < 2:
                    run._resubmits = getattr(run, "_resubmits", 0) + 1
                    out.append({"type": "tool_result", "tool_use_id": c.id, "is_error": True,
                                "content": "Not accepted. Fix these actions and call submit_decisions again:\n" + "\n".join(errs)})
                    continue
                run.output = dict(c.input)
                out.append({"type": "tool_result", "tool_use_id": c.id, "content": "Decisions received."})
            else:
                out.append({"type": "tool_result", "tool_use_id": c.id, "is_error": True, "content": f"unknown tool {c.name}"})
        return out

    first = (f"{context}\n\nThis week: brief your specialists, weigh what they find, and submit the decisions. The data runs to "
             f"{db.execute('SELECT MAX(day) FROM sales_daily').fetchone()[0]}.")
    try:
        _loop(client, LEAD_SYSTEM, defs, first, handle, "submit_decisions", max_turns, "high", run)
    except Exception as e:
        run.error = f"{type(e).__name__}: {e}"[:300]
    return run, team


COMMS_SYSTEM = """You write the weekly message each stakeholder of a growth team receives. You get the decisions the growth lead proposed
(with who must approve each) and computed facts. For each role write 3-5 short sentences in plain English: what changed for them, what
they must decide (by number), and what was done for them. Use only numbers from the input. Roles: Leadership, Growth manager, Paid media
manager, CRM manager, Product owner, Finance. Call submit_briefs once."""
BRIEFS_TOOL = {"name": "submit_briefs", "strict": True, "description": "One message per role.",
               "input_schema": {"type": "object", "additionalProperties": False, "required": ["briefs"],
                                "properties": {"briefs": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                                      "required": ["role", "message"],
                                                                                      "properties": {"role": {"type": "string", "enum": list(catalog.ROLES.values())},
                                                                                                     "message": {"type": "string"}}}}}}}


def comms(client, decisions: dict, facts: dict) -> AgentRun:
    run = AgentRun("stakeholder_comms")

    def handle(calls):
        out = []
        for c in calls:
            if c.name == "submit_briefs":
                run.output = dict(c.input)
            out.append({"type": "tool_result", "tool_use_id": c.id, "content": "Received."})
        return out

    first = json.dumps({"decisions": decisions, "facts": facts}, ensure_ascii=False, default=str)
    try:
        _loop(client, COMMS_SYSTEM, [BRIEFS_TOOL], first, handle, "submit_briefs", 3, "low", run)
    except Exception as e:
        run.error = f"{type(e).__name__}: {e}"[:300]
    return run


def run_team(hub, context: str, client=None, cost_cap: float = 10.0) -> dict:
    import anthropic
    client = client or anthropic.Anthropic(timeout=900, max_retries=3)
    BUDGET.update(spent=0.0, cap=cost_cap)
    t0 = time.time()
    lead_run, team = lead(client, hub, context)
    decisions = lead_run.output or {}
    db = sqlite3.connect(f"file:{hub}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    routed = []
    for i, r in enumerate(decisions.get("recommendations", []), 1):
        chk = catalog.check(db, r.get("execution", {}))
        routed.append({"rank": i, "action": r["action"], "approver": catalog.ROLES[chk.approver], "risk": chk.risk, "type": r["execution"]["type"]})
    facts = {"budget_pacing": json.loads(tools.call(db, "budget_pacing", {}))[:12], "routing": routed}
    comms_run = comms(client, {"headline": decisions.get("headline"), "recommendations": routed}, facts) if decisions else AgentRun("stakeholder_comms")
    runs = [lead_run, *[r for rs in team.values() for r in rs], comms_run]
    return {
        "decisions": decisions, "routing": routed, "briefs": (comms_run.output or {}).get("briefs", []),
        "transcripts": {r.role + (f"-{i}" if i else ""): r.transcript for i, r in enumerate(runs)},
        "cost_cap_usd": cost_cap,
        "specialists": {role: [{"output": r.output, "turns": r.turns, "tool_calls": r.tool_calls, "cost_usd": r.cost(), "seconds": r.seconds, "error": r.error}
                               for r in rs] for role, rs in team.items()},
        "agents": [{"role": r.role, "turns": r.turns, "tool_calls": len(r.tool_calls), "cost_usd": r.cost(), "seconds": r.seconds, "error": r.error} for r in runs],
        "cost_usd": round(sum(r.cost() for r in runs), 2), "seconds": round(time.time() - t0), "model": MODEL,
    }
