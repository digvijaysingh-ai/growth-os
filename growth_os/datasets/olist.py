"""Olist marketing funnel (Kaggle, CC BY-NC-SA 4.0): 8,000 B2B leads from June 2017 to May 2018 and the 842 that closed.

Each lead becomes one anonymous hub row. Closed deals get the sales rep, segment and lead type, and the seller's
real revenue in its first 90 days, joined from the Olist e-commerce orders.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from ..hub import store

CREDIT = "Olist marketing funnel and Brazilian e-commerce datasets (Kaggle, CC BY-NC-SA 4.0)"


def _ts(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _rows(raw: Path, name: str) -> list[dict]:
    with (raw / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def seller_value(raw: Path, windows: dict[str, datetime], days: int = 90) -> dict[str, float]:
    """Sum of item prices each seller sold in the `days` after it signed (orders that were not cancelled)."""
    purchase = {o["order_id"]: _ts(o["order_purchase_timestamp"]) for o in _rows(raw, "olist_orders_dataset.csv")
                if o["order_status"] not in ("canceled", "unavailable")}
    last = max(t for t in purchase.values() if t)
    # a seller whose 90 days run past the end of the order data has no complete figure: leave it out, never count it as 0
    out: dict[str, float] = {s: 0.0 for s, start in windows.items() if start + timedelta(days=days) <= last}
    for it in _rows(raw, "olist_order_items_dataset.csv"):
        start = windows.get(it["seller_id"])
        t = purchase.get(it["order_id"])
        if it["seller_id"] in out and t and start <= t < start + timedelta(days=days):
            out[it["seller_id"]] += float(it["price"] or 0)
    return out


def load(raw: Path, hub: Path) -> dict:
    mql = _rows(raw, "olist_marketing_qualified_leads_dataset.csv")
    deals = {d["mql_id"]: d for d in _rows(raw, "olist_closed_deals_dataset.csv")}
    windows = {d["seller_id"]: _ts(d["won_date"]) for d in deals.values() if _ts(d["won_date"])}
    value = seller_value(raw, windows)
    rows = []
    for m in mql:
        first = _ts(m["first_contact_date"])
        d = deals.get(m["mql_id"])
        won = _ts(d["won_date"]) if d else None
        rev = (d or {}).get("declared_monthly_revenue", "")
        rows.append({
            "day": first.date().isoformat(), "origin": "marketing", "utm_source": m["origin"] or "", "utm_medium": "",
            "ad_id": "", "sector": (d or {}).get("business_segment", "") or "", "stage": "Ganado" if d else "MQL", "lang": "pt",
            "wants_booking": 0, "est_value": 0, "hours_to_contact": None, "hours_to_demo": None,
            "days_to_win": round((won - first).total_seconds() / 86400, 1) if won else None,
            "landing": m["landing_page_id"], "owner": (d or {}).get("sr_id") or None, "sdr": (d or {}).get("sdr_id") or None,
            "lead_type": (d or {}).get("lead_type") or None, "profile": (d or {}).get("lead_behaviour_profile") or None,
            "business_type": (d or {}).get("business_type") or None,
            "declared_revenue": float(rev) if rev not in ("", None) else None,
            "value_after_90d": round(value[d["seller_id"]], 2) if d and d["seller_id"] in value else None,
        })
    hub.unlink(missing_ok=True)
    db = store.connect(hub)
    days = [r["day"] for r in rows]
    n = store.replace_window(db, "leads", rows, min(days), max(days))
    store.log_sync(db, "olist", min(days), max(days), n, CREDIT)
    db.commit()
    db.close()
    return {"leads": n, "won": len(deals), "won_with_full_90d_window": len(value), "of_which_sold": sum(1 for v in value.values() if v > 0),
            "first_day": min(days), "last_day": max(days)}
