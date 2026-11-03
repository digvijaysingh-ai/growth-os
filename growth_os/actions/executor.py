"""The decision inbox and the executor: approve or reject a recommendation, and the approved action runs.

    inbox(hub)                       what is waiting, who must decide, risk, and the action that will run
    decide(hub, id, approve, who, role, reason)
                                     records the decision; a rejection keeps its reason, which the next memo reads
    run_approved(hub, adapter)       executes every approved action through guardrails, logs each one
    rollback(hub, run_id, adapter)   undoes one executed action

Guardrails, checked before anything runs:
  - a kill switch: GROWTH_OS_KILL=1 in the environment, or a file state/KILL, stops every execution
  - the decider must hold the role the action requires (or leadership, who can approve anything), checked against the
    hub's team table (person -> roles), not against what the decider claims
  - risky actions (medium and high) need a different person from the one who requested them
  - budget changes are capped per action by the catalogue, and per day across actions (MAX_DAILY_BUDGET_PCT)
  - an adapter can refuse an action it does not support (the real pilot only pauses and resumes ads)
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from ..config import ROOT
from ..hub import store
from . import catalog

MAX_DAILY_BUDGET_PCT = 40.0   # sum of |budget change %| the system may execute in one day
KILL_FILE = ROOT / "state" / "KILL"


class Refused(Exception):
    pass


def killed() -> bool:
    return os.environ.get("GROWTH_OS_KILL") == "1" or KILL_FILE.exists()


def inbox(hub: Path) -> list[dict]:
    store.connect(hub).close()
    with store.connect(hub, read_only=True) as db:
        return [dict(r) for r in db.execute("""SELECT id, memo_date, rank, action, confidence, expected_impact, exec_type, exec_target, exec_to, exec_pct,
                                                      exec_note, risk, approver_role, status FROM recommendations
                                               WHERE status = 'proposed' ORDER BY memo_date DESC, rank""")]


def decide(hub: Path, rec_id: int, approve: bool, who: str, role: str, reason: str = "", requested_by: str = "analyst") -> dict:
    """Records a decision after checking the decider may make it. Raises Refused otherwise."""
    with store.connect(hub) as db:
        r = db.execute("SELECT * FROM recommendations WHERE id = ?", (rec_id,)).fetchone()
        if not r:
            raise Refused(f"no recommendation #{rec_id}")
        if r["status"] != "proposed":
            raise Refused(f"#{rec_id} is already {r['status']}")
        roles = {x[0] for x in db.execute("SELECT role FROM team WHERE person = ?", (who,))}
        if db.execute("SELECT EXISTS(SELECT 1 FROM team)").fetchone()[0] and role not in roles:
            raise Refused(f"{who} does not hold the role {catalog.ROLES.get(role, role)} in the team table")
        if approve:
            if role not in (r["approver_role"], "leadership"):
                raise Refused(f"#{rec_id} needs {catalog.ROLES[r['approver_role']]} (or leadership); {who} decides as {catalog.ROLES.get(role, role)}")
            if r["risk"] in ("medium", "high") and who == requested_by:
                raise Refused(f"#{rec_id} is {r['risk']} risk: the approver must not be the person who requested it")
        elif not reason.strip():
            raise Refused("a rejection needs a reason; the next memo reads it")
        db.execute("UPDATE recommendations SET status = ?, decided_by = ?, decided_at = ?, reject_reason = ? WHERE id = ?",
                   ("accepted" if approve else "rejected", f"{who} ({role})", datetime.now().isoformat(timespec="seconds"), reason.strip(), rec_id))
        db.commit()
        return {"id": rec_id, "status": "accepted" if approve else "rejected"}


def _log(db, rec_id, kind, target, params, adapter, status, before=None, after=None, detail="", approved_by=""):
    db.execute("""INSERT INTO action_runs (rec_id, kind, target, params, adapter, status, before, after, detail, approved_by, ts)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
               (rec_id, kind, target, json.dumps(params), adapter, status, json.dumps(before or {}), json.dumps(after or {}), detail, approved_by,
                datetime.now().isoformat(timespec="seconds")))


def run_approved(hub: Path, adapter, today: str | None = None) -> list[dict]:
    """Executes every accepted, not yet executed recommendation whose action the system can carry out."""
    today = today or datetime.now().date().isoformat()
    out = []
    with store.connect(hub) as db:
        rows = db.execute("""SELECT * FROM recommendations WHERE status = 'accepted' AND executed_at = '' AND exec_type != 'manual'
                             ORDER BY memo_date, rank""").fetchall()
        used = db.execute("""SELECT COALESCE(SUM(ABS(json_extract(params, '$.amount_pct'))), 0) FROM action_runs
                             WHERE status = 'executed' AND kind IN ('change_budget', 'shift_budget') AND substr(ts, 1, 10) = ?""", (today,)).fetchone()[0]
        for r in rows:
            ex = {"type": r["exec_type"], "target": r["exec_target"], "to_target": r["exec_to"], "amount_pct": r["exec_pct"], "note": r["exec_note"]}
            res = {"id": r["id"], "type": ex["type"], "target": ex["target"]}
            if killed():
                _log(db, r["id"], ex["type"], ex["target"], ex, adapter.name, "blocked", detail="kill switch on", approved_by=r["decided_by"])
                out.append({**res, "status": "blocked", "detail": "kill switch on"})
                continue
            chk = catalog.check(db, ex)
            if not chk.ok:
                _log(db, r["id"], ex["type"], ex["target"], ex, adapter.name, "blocked", detail="; ".join(chk.errors), approved_by=r["decided_by"])
                out.append({**res, "status": "blocked", "detail": "; ".join(chk.errors)})
                continue
            if ex["type"] in ("change_budget", "shift_budget") and used + abs(ex["amount_pct"]) > MAX_DAILY_BUDGET_PCT:
                _log(db, r["id"], ex["type"], ex["target"], ex, adapter.name, "blocked", detail=f"daily budget-change cap {MAX_DAILY_BUDGET_PCT:g}% reached",
                     approved_by=r["decided_by"])
                out.append({**res, "status": "blocked", "detail": "daily budget-change cap reached; runs tomorrow"})
                continue
            try:
                before, after, detail = adapter.apply(db, ex, rec_id=r["id"], today=today)
            except Refused as e:
                _log(db, r["id"], ex["type"], ex["target"], ex, adapter.name, "blocked", detail=str(e), approved_by=r["decided_by"])
                out.append({**res, "status": "blocked", "detail": str(e)})
                continue
            except Exception as e:  # a failed call is logged, never retried blindly
                _log(db, r["id"], ex["type"], ex["target"], ex, adapter.name, "failed", detail=str(e)[:300], approved_by=r["decided_by"])
                out.append({**res, "status": "failed", "detail": str(e)[:300]})
                continue
            if ex["type"] in ("change_budget", "shift_budget"):
                used += abs(ex["amount_pct"])
            _log(db, r["id"], ex["type"], ex["target"], ex, adapter.name, "executed", before, after, detail, r["decided_by"])
            db.execute("UPDATE recommendations SET executed_at = ? WHERE id = ?", (today, r["id"]))
            out.append({**res, "status": "executed", "detail": detail})
        db.commit()
    return out


def rollback(hub: Path, run_id: int, adapter) -> dict:
    with store.connect(hub) as db:
        r = db.execute("SELECT * FROM action_runs WHERE id = ? AND status = 'executed'", (run_id,)).fetchone()
        if not r:
            raise Refused(f"no executed action #{run_id}")
        detail = adapter.undo(db, json.loads(r["params"]), json.loads(r["before"]), rec_id=r["rec_id"])
        db.execute("UPDATE action_runs SET status = 'rolled_back', detail = detail || ' | rolled back: ' || ? WHERE id = ?", (detail, run_id))
        db.commit()
        return {"run": run_id, "status": "rolled_back", "detail": detail}
