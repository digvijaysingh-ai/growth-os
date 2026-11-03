"""Recommendation tracker: the closed loop between a memo and its outcome.

record(): stores each recommendation with the baseline of its metric (its metric_sql run now).
decide(): a person accepts or rejects it (from Slack, the dashboard or the command line).
followup(): once check_after_days have passed, re-runs the metric and records whether it moved the way it should.
The insight-to-action rate and the outcome of acted-on recommendations then come out of this table.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .actions import catalog
from .agents.analyst.analyst import run_sql
from .hub import store

MOVE = 0.05  # a 5% move in the hoped-for direction counts as "moved"


def _value(db: sqlite3.Connection, sql: str) -> float | None:
    out = json.loads(run_sql(db, sql))
    rows = out.get("rows") or []
    if not rows or "value" not in rows[0] or rows[0]["value"] is None:
        return None
    try:
        return float(rows[0]["value"])
    except (TypeError, ValueError):
        return None


def record(hub: Path, memo: dict, memo_date: str) -> list[dict]:
    store.connect(hub).close()
    with store.connect(hub, read_only=True) as ro:
        baselines = [_value(ro, r["metric_sql"]) for r in memo.get("recommendations", [])]
        checks = [catalog.check(ro, r.get("execution") or {"type": "manual", "note": r["action"]}) for r in memo.get("recommendations", [])]
    now = datetime.now().isoformat(timespec="seconds")
    out = []
    with store.connect(hub) as db:
        for i, (r, base, chk) in enumerate(zip(memo.get("recommendations", []), baselines, checks), 1):
            ex = r.get("execution") or {}
            kind = ex.get("type", "manual") if chk.ok else "manual"  # an action that fails validation is never executable
            db.execute("""INSERT INTO recommendations (memo_date, rank, action, confidence, expected_impact, metric_sql, direction, check_after_days, baseline,
                          baseline_at, exec_type, exec_target, exec_to, exec_pct, exec_note, risk, approver_role)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (memo_date, i, r["action"], r["confidence"], r["expected_impact"], r["metric_sql"], r["direction"], int(r["check_after_days"]), base, now,
                        kind, ex.get("target", ""), ex.get("to_target", ""), float(ex.get("amount_pct") or 0), ex.get("note", ""), chk.risk, chk.approver))
            out.append({"rank": i, "action": r["action"][:80], "baseline": base, "metric_ok": base is not None, "execution": kind, "approver": chk.approver})
        db.commit()
    return out


def decide(hub: Path, rec_id: int, accept: bool, who: str) -> None:
    with store.connect(hub) as db:
        db.execute("UPDATE recommendations SET status = ?, decided_by = ?, decided_at = ? WHERE id = ? AND status = 'proposed'",
                   ("accepted" if accept else "rejected", who, datetime.now().isoformat(timespec="seconds"), rec_id))
        db.commit()


def followup(hub: Path, today: date | None = None) -> list[dict]:
    today = today or date.today()
    store.connect(hub).close()
    with store.connect(hub) as db:
        due = db.execute("""SELECT id, action, metric_sql, direction, baseline, memo_date, check_after_days FROM recommendations
                            WHERE status IN ('accepted', 'proposed') AND outcome IS NULL""").fetchall()
        out = []
        for r in due:
            if date.fromisoformat(r["memo_date"]) + timedelta(days=r["check_after_days"]) > today:
                continue
            now_v = _value(db, r["metric_sql"])
            if now_v is None or r["baseline"] is None:
                verdict = "metric unavailable"
            else:
                change = (now_v - r["baseline"]) / abs(r["baseline"]) if r["baseline"] else 0.0
                good = change if r["direction"] == "up" else -change
                verdict = "moved as hoped" if good >= MOVE else ("moved the wrong way" if good <= -MOVE else "no clear change")
            db.execute("UPDATE recommendations SET outcome = ?, outcome_at = ?, verdict = ? WHERE id = ?", (now_v, today.isoformat(), verdict, r["id"]))
            out.append({"id": r["id"], "action": r["action"][:80], "baseline": r["baseline"], "now": now_v, "verdict": verdict})
        db.commit()
    return out


def summary(hub: Path) -> dict:
    with store.connect(hub, read_only=True) as db:
        r = db.execute("""SELECT COUNT(*) AS total, SUM(status != 'proposed') AS decided, SUM(status = 'accepted') AS accepted,
                          SUM(verdict = 'moved as hoped') AS worked, SUM(verdict != '') AS checked FROM recommendations""").fetchone()
        return dict(r)
