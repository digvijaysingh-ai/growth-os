"""The action catalogue: everything the decision layer is allowed to do, and the rules around each action.

A recommendation from the analyst carries one `execution` block naming an action from this catalogue. It is checked
here before anyone sees it (does the target exist, is the change within limits) and routed to the role that must
approve it. Only approved actions run, and every one has a way back (rollback).

Risk tiers decide who approves:
  low     the channel or team owner              e.g. pause an ad, open a ticket
  medium  the growth manager                     e.g. move budget between ads, start an email flow
  high    the leadership (finance is told)  e.g. raise a market's total budget
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

ROLES = {
    "leadership": "Leadership",
    "growth_manager": "Growth manager",
    "channel_manager": "Paid media manager",
    "crm_manager": "CRM / lifecycle manager",
    "product_owner": "Product / engineering owner",
    "finance": "Finance partner",
}


@dataclass(frozen=True)
class Spec:
    kind: str
    label: str
    target: str            # what `target` must name: ad, market, product, page, team, role or nothing
    risk: str              # low, medium, high
    approver: str          # role that must approve
    executes: bool         # False = tracked only, a person does it
    rollback: str          # how it is undone
    min_pct: float = 0.0   # limits on amount_pct, where it applies
    max_pct: float = 0.0
    needs_to_target: bool = False
    description: str = ""


CATALOG: dict[str, Spec] = {s.kind: s for s in [
    Spec("pause_ad", "Pause an ad", "ad", "low", "channel_manager", True, "resume the ad",
         description="Stops delivery of one ad. Use for an ad that is wasting spend (fatigue, broken link, far above target CPA)."),
    Spec("resume_ad", "Resume an ad", "ad", "low", "channel_manager", True, "pause the ad again"),
    Spec("rotate_creative", "Rotate out a fatigued creative", "ad", "low", "channel_manager", True,
         "resume the old creative and restore budgets",
         description="Pauses one fatigued ad and hands its budget to the other ads in the same market and platform."),
    Spec("change_budget", "Change a market's paid budget", "market", "medium", "growth_manager", True,
         "restore the previous budget", -50, 30,
         description="Scales all paid spend in one market by amount_pct (-50 to +30). Increases above +10% are high risk and go to leadership."),
    Spec("shift_budget", "Move budget from one ad to another", "ad", "medium", "growth_manager", True,
         "move it back", 5, 50, needs_to_target=True,
         description="Moves amount_pct (5 to 50) of the target ad's daily budget to to_target (another ad in the same market). Total spend stays the same."),
    Spec("launch_ab_test", "Launch an A/B test", "page", "low", "growth_manager", True, "stop the test, keep the control",
         description="Creates a test on a page or step (target, e.g. 'checkout' or '/product'), with the variant described in note."),
    Spec("trigger_email_flow", "Start an email flow", "product", "medium", "crm_manager", True, "stop the flow",
         description="Sends a lifecycle email flow about one product (target) to opted-in customers in its market only."),
    Spec("open_ticket", "Open a ticket for a team", "team", "low", "product_owner", True, "close the ticket",
         description="Opens a ticket for engineering, product, creative or ops (target), with market and problem in note. Use for bugs and fixes outside marketing."),
    Spec("notify", "Tell a stakeholder", "role", "low", "growth_manager", True, "nothing to undo",
         description="Sends a short note to a role (target: leadership, finance, crm_manager, …) so they can act or plan."),
    Spec("reallocate_channel", "Move budget between channels", "market_line_channel", "medium", "growth_manager", True,
         "move it back", 5, 60, needs_to_target=True,
         description="Moves amount_pct (5 to 60) of one channel's budget to another channel in the same market and product line. Targets are "
                     "'Market|Line|channel' (both in the same market and line). The line's total is unchanged."),
    Spec("change_line_budget", "Change a product line's budget in a market", "market_line", "medium", "growth_manager", True,
         "restore the previous budget", -40, 40,
         description="Scales all paid spend of one product line in one market by amount_pct (-40 to +40). Target 'Market|Line'. Increases above "
                     "+15% are high risk and need leadership; finance is told."),
    Spec("pause_channel", "Pause a channel for a product line", "market_line_channel", "medium", "channel_manager", True, "resume the channel",
         description="Stops spend on one channel for one product line in one market. Target 'Market|Line|channel'."),
    Spec("weather_rule", "Boost spend on rainy days", "market_line", "low", "channel_manager", True, "remove the rule", 10, 50,
         description="On days the forecast shows rain, raises upper-funnel spend (Meta prospecting, TikTok, YouTube, creators) of one product line "
                     "in one market by amount_pct (10 to 50). Target 'Market|Line'."),
    Spec("apply_mix_plan", "Apply the mix model's channel split", "mix_scope", "medium", "growth_manager", True,
         "restore the previous split", 10, 50,
         description="Applies the marketing-mix model's reallocation (spend toward higher marginal ROAS, each line's total unchanged) to one "
                     "'Market|Line', one market ('Market') or the whole portfolio ('all'), moving no channel by more than amount_pct (10 to 50). "
                     "Portfolio-wide or market-wide changes are high risk and need leadership."),
    Spec("manual", "A person does it", "none", "low", "growth_manager", False, "not applicable",
         description="Anything outside the catalogue: tracked, measured, but not executed by the system."),
]}

TEAMS = ("engineering", "product", "creative", "ops", "data", "logistics", "seo")


@dataclass
class Check:
    ok: bool
    errors: list[str]
    risk: str = "low"
    approver: str = "growth_manager"


def _exists(db: sqlite3.Connection, sql: str, *p) -> bool:
    try:
        return db.execute(sql, p).fetchone() is not None
    except sqlite3.Error:
        return False


def check(db: sqlite3.Connection, ex: dict) -> Check:
    """Validates one execution block against the catalogue and the hub; returns risk and the approving role."""
    kind = ex.get("type", "")
    spec = CATALOG.get(kind)
    if not spec:
        return Check(False, [f"unknown action type {kind!r}; use one of {', '.join(CATALOG)}"])
    t, to, pct = (ex.get("target") or "").strip(), (ex.get("to_target") or "").strip(), float(ex.get("amount_pct") or 0)
    errs: list[str] = []
    if spec.target == "ad" and not _exists(db, "SELECT 1 FROM ads WHERE ad_id = ?", t):
        errs.append(f"{kind}: target {t!r} is not an ad_id in the ads table")
    if spec.target == "market" and not _exists(db, "SELECT 1 FROM ad_daily WHERE market = ? LIMIT 1", t):
        errs.append(f"{kind}: target {t!r} is not a market in ad_daily")
    if spec.target == "product" and not _exists(db, "SELECT 1 FROM products WHERE product_id = ?", t):
        errs.append(f"{kind}: target {t!r} is not a product_id in the products table")
    if spec.target == "team" and t not in TEAMS:
        errs.append(f"{kind}: target must be one of {', '.join(TEAMS)}")
    if spec.target == "role" and t not in ROLES:
        errs.append(f"{kind}: target must be one of {', '.join(ROLES)}")
    if spec.target in ("market_line", "market_line_channel"):
        for label, val in (("target", t), ("to_target", to) if spec.needs_to_target else ("target", t)):
            parts = val.split("|")
            want = 3 if spec.target == "market_line_channel" else 2
            if len(parts) != want:
                errs.append(f"{kind}: {label} must look like {'Market|Line|channel' if want == 3 else 'Market|Line'} (got {val!r})")
                continue
            q = "SELECT 1 FROM budget_plan WHERE market = ? AND line = ?" + (" AND channel = ?" if want == 3 else "") + " LIMIT 1"
            if not _exists(db, q, *parts):
                errs.append(f"{kind}: {label} {val!r} is not in the budget plan")
        if spec.needs_to_target and t.split("|")[:2] != to.split("|")[:2]:
            errs.append(f"{kind}: both channels must be in the same market and product line")
        if spec.needs_to_target and t == to:
            errs.append(f"{kind}: to_target must differ from target")
    if spec.target == "mix_scope":
        parts = t.split("|")
        if t != "all" and not _exists(db, "SELECT 1 FROM budget_plan WHERE market = ?" + (" AND line = ?" if len(parts) == 2 else "") + " LIMIT 1", *parts):
            errs.append(f"{kind}: target must be 'all', a market or 'Market|Line' in the budget plan (got {t!r})")
    if spec.target == "page" and not t:
        errs.append(f"{kind}: name the page or step to test in target")
    if spec.needs_to_target and spec.target == "ad":
        if not _exists(db, "SELECT 1 FROM ads WHERE ad_id = ?", to):
            errs.append(f"{kind}: to_target {to!r} is not an ad_id")
        elif to == t:
            errs.append(f"{kind}: to_target must differ from target")
        else:
            same = db.execute("SELECT COUNT(DISTINCT market) AS n FROM ad_daily WHERE ad_id IN (?, ?)", (t, to)).fetchone()
            if same and same[0] > 1:
                errs.append(f"{kind}: both ads must be in the same market")
    if spec.max_pct or spec.min_pct:
        if not (spec.min_pct <= pct <= spec.max_pct) or pct == 0:
            errs.append(f"{kind}: amount_pct must be between {spec.min_pct:g} and {spec.max_pct:g} and not 0 (got {pct:g})")
    if kind in ("launch_ab_test", "open_ticket", "notify", "manual") and not (ex.get("note") or "").strip():
        errs.append(f"{kind}: describe the work in note")
    risk, approver = spec.risk, spec.approver
    if kind == "change_budget" and pct > 10:
        risk, approver = "high", "leadership"
    if kind == "apply_mix_plan" and "|" not in t:
        risk, approver = "high", "leadership"
    if kind == "change_line_budget" and pct > 15:
        risk, approver = "high", "leadership"
    return Check(not errs, errs, risk, approver)


def schema() -> dict:
    """The strict JSON schema of an execution block, for the analyst's submit_memo tool."""
    return {
        "type": "object",
        "description": "The action that carries out this recommendation, from the action catalogue. The system executes it after the "
                       "named role approves. Use type 'manual' when no catalogue action fits; never force a fit. Unused fields: '' or 0.",
        "properties": {
            "type": {"type": "string", "enum": list(CATALOG)},
            "target": {"type": "string", "description": "ad_id, market name, 'Market|Line', 'Market|Line|channel', 'all', product_id, page/step, team (" + ", ".join(TEAMS) + ") or role ("
                       + ", ".join(ROLES) + "), depending on type."},
            "to_target": {"type": "string", "description": "shift_budget: the ad_id receiving the budget; reallocate_channel: the 'Market|Line|channel' receiving it."},
            "amount_pct": {"type": "number", "description": "change_budget -50..30; shift_budget 5..50; reallocate_channel 5..60; change_line_budget -40..40; weather_rule 10..50; apply_mix_plan 10..50 (max move per channel). Otherwise 0."},
            "note": {"type": "string", "description": "What exactly happens: the test variant, the ticket's problem and evidence, the message."},
        },
        "required": ["type", "target", "to_target", "amount_pct", "note"],
        "additionalProperties": False,
    }


def prompt_text() -> str:
    lines = ["Action catalogue (each recommendation's execution.type must be one of these):"]
    for s in CATALOG.values():
        lim = f" amount_pct {s.min_pct:g} to {s.max_pct:g}." if (s.max_pct or s.min_pct) else ""
        lines.append(f"- {s.kind} (target: {s.target}; risk {s.risk}; approved by {ROLES[s.approver]}).{lim} {s.description}")
    return "\n".join(lines)
