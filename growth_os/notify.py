"""Slack notifications (Block Kit over an incoming webhook): the weekly memo and the ads agent's proposals.

Buttons open the approval page and the console; decisions are made there and land in the audit trail. Set
SLACK_WEBHOOK_URL in .env to turn it on; without it nothing is sent. Teams works the same way through its own webhook.
"""
from __future__ import annotations

import json
import os
import urllib.request

CONF = {"high": "🟢 high", "medium": "🟡 medium", "low": "⚪️ low"}


def memo_blocks(memo: dict, *, business: str, period: str, approvals_url: str = "", console_url: str = "", rec_ids: list[int] | None = None) -> dict:
    recs = memo.get("recommendations", [])[:3]
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Growth memo · {business}"[:150]}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"{period} · data: *{memo['data_sufficiency']['verdict'].replace('_', ' ')}*"}]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{memo['headline']}*"[:2900]}},
        {"type": "divider"},
    ]
    for i, r in enumerate(recs, 1):
        rid = f" · tracked as #{rec_ids[i - 1]}" if rec_ids and i <= len(rec_ids) else ""
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": (
            f"*{i}. {r['action']}*\n💶 {r['expected_impact']}\n{CONF.get(r['confidence'], r['confidence'])} confidence · effort {r['effort']}"
            f" · check in {r['check_after_days']} days{rid}")[:2900]}})
    buttons = [(label, url) for label, url in (("Review and approve", approvals_url), ("Open console", console_url)) if url]
    if buttons:
        blocks.append({"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": t}, "url": u, **({"style": "primary"} if j == 0 else {})}
                                                       for j, (t, u) in enumerate(buttons)]})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Agents propose, people decide. Nothing changes until someone approves it."}]})
    return {"text": memo["headline"][:300], "blocks": blocks}


def proposal_blocks(proposals: list[dict], approvals_url: str) -> dict:
    lines = [f"• *{p['ad_name']}*: pause ({p['rule']}). {p['reason']}" for p in proposals[:10]]
    return {"text": f"{len(proposals)} ad proposal(s) waiting for approval", "blocks": [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{len(proposals)} ad proposal(s) waiting for your decision*\n" + "\n".join(lines)}},
        {"type": "actions", "elements": [{"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "Review and approve"}, "url": approvals_url}]},
    ]}


def send(payload: dict) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        return False
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status == 200


REJECT_REASONS = ["Not now: a promotion is running", "Disagree with the evidence", "Too risky this week", "Already handled outside the system"]
RISK = {"low": "🟢 low risk", "medium": "🟡 medium risk", "high": "🔴 high risk"}


def decision_blocks(rec: dict, *, mention: str = "", console_url: str = "") -> dict:
    """One approval card per recommendation, sent to the role that must decide. Approve and Reject post back to the
    decision endpoint (growth-os serve, set as the Slack app's interactivity URL) with the recommendation id; rejecting means
    picking a reason, which the next memo reads."""
    from .actions import catalog
    spec = catalog.CATALOG.get(rec["exec_type"], catalog.CATALOG["manual"])
    what = f"{spec.label}: `{rec['exec_target']}`" + (f" → `{rec['exec_to']}`" if rec.get("exec_to") else "") + (f" ({rec['exec_pct']:+g}%)" if rec.get("exec_pct") else "")
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{mention + ' ' if mention else ''}*Decision needed #{rec['id']}*\n{rec['action']}"[:2900]}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Will run*\n{what}"[:1900]},
            {"type": "mrkdwn", "text": f"*Risk*\n{RISK.get(rec['risk'], rec['risk'])} · approver: {catalog.ROLES[rec['approver_role']]}"},
            {"type": "mrkdwn", "text": f"*Expected*\n{rec.get('expected_impact', '')}"[:1900]},
            {"type": "mrkdwn", "text": f"*Undo*\n{spec.rollback}"},
        ]},
        {"type": "actions", "block_id": f"decide-{rec['id']}", "elements": [
            {"type": "button", "style": "primary", "action_id": "approve", "value": str(rec["id"]), "text": {"type": "plain_text", "text": "Approve and run"}},
            {"type": "static_select", "action_id": "reject", "placeholder": {"type": "plain_text", "text": "Reject because…"},
             "options": [{"text": {"type": "plain_text", "text": t}, "value": f"{rec['id']}|{t}"} for t in REJECT_REASONS]},
            *([{"type": "button", "action_id": "open", "url": console_url, "text": {"type": "plain_text", "text": "See evidence"}}] if console_url else []),
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Runs only after approval, inside spend limits, with an audit log and a one-click rollback."}]},
    ]
    return {"text": f"Decision needed: {rec['action'][:200]}", "blocks": blocks}
