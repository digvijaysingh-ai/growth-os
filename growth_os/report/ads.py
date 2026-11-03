"""Weekly report: numbers computed here, one summary paragraph written by Claude (optional).

The model only sees aggregates per ad, never anything about individual leads, and it is told not to
invent causes the numbers don't show.
"""
from __future__ import annotations

import json

from ..agents.ads.rules import AdView

SYSTEM = (
    "You write the summary paragraph of a weekly Meta ads report for a small business owner. "
    "Plain text, 4-6 sentences, no headings, no bullet points, no markdown. "
    "Use only the numbers given. Leads come from the business's own website, or for Instant Form ads (meta_form_leads) from Meta's count; "
    "qualified leads are ones that got as far as a demo, recorded by the business. "
    "Say which ad did best and which did worst by cost per lead, what the agent proposed and what the owner decided, "
    "and one concrete thing to try next week. If the numbers are too small to conclude anything, say so plainly. "
    "Never guess a cause the data does not show."
)


def _money(x: float | None, cur: str) -> str:
    if x is None:
        return "-"
    return f"{x:,.2f} €" if cur == "EUR" else f"{x:,.2f} {cur}"


def table(views: list[AdView], cur: str) -> str:
    head = f"{'Ad':<28} {'Spend':>10} {'Impr.':>7} {'CTR':>6} {'Visits':>6} {'Leads':>5} {'Qual.':>5} {'CPL':>10}"
    lines = [head, "-" * len(head)]
    for v in views:
        lines.append(f"{(v.ad_name or v.ad_id)[:28]:<28} {_money(v.spend, cur):>10} {v.impressions:>7} {v.ctr:>5.2f}% "
                     f"{v.visits:>6} {v.leads:>5} {v.qualified:>5} {_money(v.cpl, cur):>10}")
    spend = sum(v.spend for v in views)
    leads = sum(v.leads for v in views)
    qual = sum(v.qualified for v in views)
    lines.append("-" * len(head))
    lines.append(f"{'Total':<28} {_money(spend, cur):>10} {sum(v.impressions for v in views):>7} {'':>6} "
                 f"{sum(v.visits for v in views):>6} {leads:>5} {qual:>5} {_money(spend / leads if leads else None, cur):>10}")
    return "\n".join(lines)


def facts(views: list[AdView], actions: list[dict], cfg: dict, since: str, until: str, guarded: list[dict] = ()) -> dict:
    return {
        "period": {"since": since, "until": until},
        "target_cost_per_lead": cfg["account"]["target_cpl"],
        "currency": cfg["account"].get("currency", "EUR"),
        "ads": [{"name": v.ad_name or v.ad_id, "status": v.status, **v.metrics()} for v in views],
        "agent_actions": [{k: a.get(k) for k in ("ad_name", "rule", "reason", "status")} for a in actions],
        "not_proposed_because_of_a_guard": list(guarded),
    }


def summary(f: dict, cfg: dict) -> tuple[str, str]:
    """Returns (paragraph, note). Falls back to no paragraph when Claude is off or unreachable."""
    rc = cfg.get("report", {})
    if not rc.get("use_claude", True):
        return "", "summary off in config"
    try:
        import anthropic
    except ImportError:
        return "", "anthropic package not installed"
    try:
        client = anthropic.Anthropic(timeout=600, max_retries=3)
        resp = client.beta.messages.create(
            model=rc.get("model", "claude-opus-5-5"),
            max_tokens=2000,
            system=SYSTEM,
            output_config={"effort": "low"},
            # if a safety classifier declines, the API retries on a suitable fallback model
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": "This week's numbers as JSON:\n" + json.dumps(f, ensure_ascii=False)}],
        )
    except anthropic.APIConnectionError:
        return "", "Claude unreachable"
    except anthropic.AuthenticationError:
        return "", "no Claude credentials"
    except anthropic.APIStatusError as e:
        return "", f"Claude error {e.status_code}"
    if resp.stop_reason == "refusal":
        return "", "Claude declined"
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text, f"written by {resp.model}"


def render(views: list[AdView], actions: list[dict], cfg: dict, since: str, until: str, paragraph: str, note: str,
           guarded: list[dict] = ()) -> str:
    cur = cfg["account"].get("currency", "EUR")
    name = cfg["account"].get("name", "")
    parts = [f"Ads report · {name} · {since} to {until}", ""]
    if paragraph:
        parts += [paragraph, f"(Summary {note}. Numbers below are computed, not written by AI.)", ""]
    parts += [table(views, cur), "",
              "Leads: website form (matched by utm_content) or, for Instant Form ads, Meta's count. Qualified: a demo was sent, from the dashboard.",
              f"Target cost per lead: {_money(cfg['account']['target_cpl'], cur)}.", ""]
    parts.append("What the agent proposed this week:")
    if not actions:
        parts.append("  nothing; every ad stayed within the rules.")
    for a in actions:
        parts.append(f"  - {a.get('ad_name') or a.get('ad_id')}: pause ({a.get('rule')}), {a.get('status')}. {a.get('reason')}")
    for g in guarded:
        parts.append(f"  - {g['ad_name']}: broke {g['rule']} but was not proposed. {g['reason']}")
    return "\n".join(parts) + "\n"
