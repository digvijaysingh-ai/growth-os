"""Facebook ads conversions (Kaggle "Sales conversion optimization"): 1,143 real ads from 3 campaigns,
each targeted at one age band, gender and interest, with spend, enquiries and purchases."""
from __future__ import annotations

import csv
from pathlib import Path

from ..hub import store

CREDIT = "Sales conversion optimization dataset (Kaggle)"


def load(raw: Path, hub: Path) -> dict:
    with (raw / "KAG_conversion_data.csv").open(newline="", encoding="utf-8") as f:  # old Mac line endings, csv copes
        src = list(csv.DictReader(f))
    rows = [{"campaign": r["xyz_campaign_id"], "ad_id": r["ad_id"], "age": r["age"], "gender": r["gender"], "interest": r["interest"],
             "impressions": int(r["Impressions"]), "clicks": int(r["Clicks"]), "spend": float(r["Spent"]),
             "conversions": int(r["Total_Conversion"]), "approved": int(r["Approved_Conversion"])} for r in src]
    hub.unlink(missing_ok=True)
    db = store.connect(hub)
    cols = store.COLUMNS["ad_segments"]
    db.executemany(f"INSERT INTO ad_segments ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [tuple(r[c] for c in cols) for r in rows])
    store.log_sync(db, "fbads", "", "", len(rows), CREDIT)
    db.commit()
    db.close()
    return {"ads": len(rows), "spend": round(sum(r["spend"] for r in rows), 2), "conversions": sum(r["conversions"] for r in rows),
            "approved": sum(r["approved"] for r in rows)}
