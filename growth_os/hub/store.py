"""The hub database: a local SQLite file, rebuilt window by window so every sync is safe to repeat."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ..config import ROOT

SCHEMA = Path(__file__).with_name("schema.sql")
DEFAULT_DB = ROOT / "state" / "hub.sqlite"

# value used when a source has no such field (single-market sources have no market)
DEFAULTS = {"market": "", "platform": "meta", "creative": "", "line": ""}

# columns each table accepts, in insert order
COLUMNS = {
    "ad_daily": ["day", "ad_id", "campaign", "spend", "impressions", "reach", "link_clicks", "form_leads", "market",
                 "platform", "creative", "frequency", "platform_purchases", "platform_revenue", "line"],
    "sales_daily": ["day", "market", "line", "channel", "ad_id", "device", "sessions", "checkouts", "orders", "revenue", "new_customers"],
    "product_daily": ["day", "product_id", "units", "revenue"],
    "web_sessions": ["day", "landing", "channel", "ad_id", "device", "sessions", "bounces", "engaged_s",
                     "scroll_25", "scroll_50", "scroll_75", "scroll_100", "form_starts", "form_errors", "form_submits", "market"],
    "web_sections": ["day", "path", "section", "sessions"],
    "web_clicks": ["day", "path", "label", "target", "sessions"],
    "leads": ["day", "origin", "utm_source", "utm_medium", "ad_id", "sector", "stage", "lang", "wants_booking",
              "est_value", "hours_to_contact", "hours_to_demo", "days_to_win",
              "landing", "owner", "sdr", "lead_type", "profile", "business_type", "declared_revenue", "value_after_90d", "market"],
    "ad_segments": ["campaign", "ad_id", "age", "gender", "interest", "impressions", "clicks", "spend", "conversions", "approved"],
    "demos": ["day", "demos_opened", "demo_sessions", "demo_engaged_s"],
}


def connect(path: Path = DEFAULT_DB, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
        _migrate(db)
        db.executescript(SCHEMA.read_text())
    db.row_factory = sqlite3.Row
    return db


def _migrate(db: sqlite3.Connection) -> None:
    """Adds columns the schema gained since this hub file was created, so views over them can be built."""
    ref = sqlite3.connect(":memory:")
    ref.executescript(SCHEMA.read_text())
    tables = [r[0] for r in ref.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    for t in tables:
        have = {r[1] for r in db.execute(f"PRAGMA table_info({t})")}
        if not have:
            continue  # created fresh by the schema below
        for _, name, typ, notnull, default, _pk in ref.execute(f"PRAGMA table_info({t})"):
            if name not in have:
                db.execute(f"ALTER TABLE {t} ADD COLUMN {name} {typ}" + (f" NOT NULL DEFAULT {default}" if notnull and default is not None else
                                                                         (f" DEFAULT {default}" if default is not None else "")))
    ref.close()


def replace_window(db: sqlite3.Connection, table: str, rows: list[dict], since: str, until: str) -> int:
    """Delete the window's days, then insert what the source returned for them."""
    cols = COLUMNS[table]
    db.execute(f"DELETE FROM {table} WHERE day BETWEEN ? AND ?", (since, until))
    db.executemany(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                   [tuple(r.get(c, DEFAULTS.get(c)) for c in cols) for r in rows])
    return len(rows)


def log_sync(db: sqlite3.Connection, source: str, since: str, until: str, rows: int, note: str = "") -> None:
    db.execute("INSERT INTO sync_log (ts, source, since, until, rows, note) VALUES (?, ?, ?, ?, ?, ?)",
               (datetime.now().isoformat(timespec="seconds"), source, since, until, rows, note))


def schema_text() -> str:
    """Tables and views as the analyst sees them (column names and comments)."""
    return SCHEMA.read_text()
