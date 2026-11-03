"""Daily sync: pulls Meta and the website into the hub for a window of days.

The window is re-read in full each time (default: the last 35 days), because a lead's stage keeps changing
after the day it arrived and Meta revises recent numbers.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from ..agents.ads.rules import META_LEAD_ACTIONS
from ..connectors import Window
from .store import log_sync, replace_window


def _form_leads(actions: list[dict] | None) -> int:
    acts = {a.get("action_type"): a.get("value") for a in actions or []}
    return next((int(float(acts[k])) for k in META_LEAD_ACTIONS if acts.get(k)), 0)


def sync_meta(db: sqlite3.Connection, meta, w: Window) -> int:
    rows = [{
        "day": r["date_start"], "ad_id": r["ad_id"], "campaign": r.get("campaign_name", ""),
        "spend": float(r.get("spend") or 0), "impressions": int(r.get("impressions") or 0), "reach": int(r.get("reach") or 0),
        "link_clicks": int(r.get("inline_link_clicks") or 0), "form_leads": _form_leads(r.get("actions")),
    } for r in meta.insights_daily(w)]
    n = replace_window(db, "ad_daily", rows, w.since.isoformat(), w.until.isoformat())
    now = datetime.now().isoformat(timespec="seconds")
    db.executemany("INSERT OR REPLACE INTO ads (ad_id, ad_name, campaign_id, status, updated_at) VALUES (?, ?, ?, ?, ?)",
                   [(a["id"], a.get("name", ""), a.get("campaign_id", ""), a.get("effective_status", ""), now) for a in meta.ads()])
    log_sync(db, "meta", w.since.isoformat(), w.until.isoformat(), n)
    return n


def sync_site(db: sqlite3.Connection, site, w: Window) -> int:
    f = site.funnel(w)
    s, u = w.since.isoformat(), w.until.isoformat()
    n = 0
    for table, key in (("web_sessions", "sessions"), ("web_sections", "sections"), ("web_clicks", "clicks"), ("leads", "leads"), ("demos", "demos")):
        n += replace_window(db, table, f.get(key, []), s, u)
    db.executemany("INSERT OR REPLACE INTO agent_actions (id, created_at, ad_id, ad_name, action, rule, reason, status, result) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   [(a["id"], a["created_at"], a["ad_id"], a.get("ad_name", ""), a["action"], a.get("rule", ""), a.get("reason", ""), a["status"], a.get("result", ""))
                    for a in site.actions(w.since)])
    log_sync(db, "site", s, u, n)
    return n


def sync(db: sqlite3.Connection, meta, site, w: Window) -> dict:
    out = {"meta": sync_meta(db, meta, w), "site": sync_site(db, site, w)}
    db.commit()
    return out
