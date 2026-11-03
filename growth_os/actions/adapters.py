"""Where approved actions land.

SandboxAdapter  a simulated ad account, ticket tracker, email tool and messenger, stored in the hub; the simulated
                market (world.py) reads it. Used by the public demo and by tests.
MetaAdapter     the real pilot ad account: pause and resume one ad. It refuses everything else on purpose.

Each adapter returns (before, after, detail) from apply() so the audit log shows exactly what changed, and undo()
restores `before`.
"""
from __future__ import annotations

import json
from datetime import datetime

from . import catalog
from .executor import Refused


def _ads_state(db, ad_ids):
    have = {r[0]: (r[1], r[2]) for r in db.execute(
        f"SELECT ad_id, status, budget_mult FROM account_state WHERE ad_id IN ({','.join('?' * len(ad_ids))})", ad_ids)}
    return {a: {"status": have.get(a, ("ACTIVE", 1.0))[0], "budget_mult": have.get(a, ("ACTIVE", 1.0))[1]} for a in ad_ids}


def _set(db, ad_id, status=None, mult=None):
    cur = _ads_state(db, [ad_id])[ad_id]
    db.execute("INSERT OR REPLACE INTO account_state (ad_id, status, budget_mult, updated_at) VALUES (?, ?, ?, ?)",
               (ad_id, status or cur["status"], cur["budget_mult"] if mult is None else round(mult, 4), datetime.now().isoformat(timespec="seconds")))


class SandboxAdapter:
    name = "sandbox"

    def apply(self, db, ex: dict, rec_id: int, today: str):
        kind, t = ex["type"], ex["target"]
        if kind in ("pause_ad", "resume_ad"):
            before = _ads_state(db, [t])
            _set(db, t, status="PAUSED" if kind == "pause_ad" else "ACTIVE")
            return before, _ads_state(db, [t]), f"{t} {'paused' if kind == 'pause_ad' else 'resumed'} in the sandbox ad account"
        if kind == "rotate_creative":
            m, p = db.execute("SELECT market, platform FROM ad_daily WHERE ad_id = ? LIMIT 1", (t,)).fetchone()
            sibs = [r[0] for r in db.execute("SELECT DISTINCT ad_id FROM ad_daily WHERE market = ? AND platform = ? AND ad_id != ?", (m, p, t))]
            before = _ads_state(db, [t, *sibs])
            share = before[t]["budget_mult"] / max(1, len(sibs))
            _set(db, t, status="PAUSED")
            for s in sibs:
                _set(db, s, mult=before[s]["budget_mult"] + share)
            return before, _ads_state(db, [t, *sibs]), f"{t} paused; its budget split across {', '.join(sibs)}"
        if kind == "change_budget":
            ids = [r[0] for r in db.execute("SELECT DISTINCT ad_id FROM ad_daily WHERE market = ? AND platform IN ('meta', 'tiktok', 'google')", (t,))]
            before = _ads_state(db, ids)
            for a in ids:
                _set(db, a, mult=before[a]["budget_mult"] * (1 + ex["amount_pct"] / 100))
            return before, _ads_state(db, ids), f"{t}: paid budget {ex['amount_pct']:+g}% on {len(ids)} ads"
        if kind == "shift_budget":
            from ..world import base_spend
            to = ex["to_target"]
            before = _ads_state(db, [t, to])
            moved = base_spend(t) * before[t]["budget_mult"] * ex["amount_pct"] / 100
            _set(db, t, mult=before[t]["budget_mult"] * (1 - ex["amount_pct"] / 100))
            _set(db, to, mult=before[to]["budget_mult"] + moved / base_spend(to))
            return before, _ads_state(db, [t, to]), f"moved {ex['amount_pct']:g}% of {t}'s budget (about {moved:.0f}/day) to {to}"
        work = {"launch_ab_test": "ab_test", "trigger_email_flow": "email_flow", "open_ticket": "ticket", "notify": "notification"}
        if kind in work:
            status = "sent" if kind == "notify" else ("running" if kind in ("launch_ab_test", "trigger_email_flow") else "open")
            cur = db.execute("INSERT INTO work_items (rec_id, kind, target, note, status, opened_on) VALUES (?, ?, ?, ?, ?, ?)",
                             (rec_id, work[kind], t, ex.get("note", ""), status, today))
            what = {"ab_test": "A/B test started on", "email_flow": "email flow started for", "ticket": "ticket opened for",
                    "notification": "message sent to"}[work[kind]]
            return {}, {"work_item": cur.lastrowid}, f"{what} {t} (sandbox #{cur.lastrowid})"
        raise Refused(f"the sandbox cannot run {kind}")

    def undo(self, db, ex: dict, before: dict, rec_id: int) -> str:
        if "work_item" in json.dumps(before) or not before:
            db.execute("UPDATE work_items SET status = 'cancelled' WHERE rec_id = ? AND status IN ('open', 'running', 'sent')", (rec_id,))
            return "work item cancelled"
        for ad_id, s in before.items():
            _set(db, ad_id, status=s["status"], mult=s["budget_mult"])
        return f"restored {len(before)} ad(s)"


class MetaAdapter:
    """The real pilot account. Only pause and resume, whatever the catalogue allows."""
    name = "meta"
    ALLOWED = ("pause_ad", "resume_ad")

    def __init__(self, meta):
        self.meta = meta

    def apply(self, db, ex: dict, rec_id: int, today: str):
        if ex["type"] not in self.ALLOWED:
            raise Refused(f"the live account only allows {', '.join(self.ALLOWED)}; {catalog.CATALOG[ex['type']].label.lower()} must be done by a person")
        status = "PAUSED" if ex["type"] == "pause_ad" else "ACTIVE"
        self.meta.set_status(ex["target"], status)
        return {"status": "ACTIVE" if status == "PAUSED" else "PAUSED"}, {"status": status}, f"Meta ad {ex['target']} set to {status}"

    def undo(self, db, ex: dict, before: dict, rec_id: int) -> str:
        self.meta.set_status(ex["target"], before["status"])
        return f"Meta ad {ex['target']} set back to {before['status']}"
