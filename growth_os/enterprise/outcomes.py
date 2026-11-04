"""From the team's decisions to measured money: approve → execute → run the quarter → compare with doing nothing.

For each decision on its own, and for all of them together, the enterprise world runs 13 weeks forward twice from the
same day with the same random draws: once as-is, once with the executed policy. Every number is SIMULATED and comes
with the stated assumptions (policy.ASSUMPTIONS).

    python -m growth_os.enterprise.outcomes state/enterprise-7.sqlite reports/team-enterprise-7.json reports/outcomes-enterprise-7.json
    python -m growth_os.enterprise.outcomes --leave-one-out --seed 7     # every priced decision approved except one, ten runs

Each run works in its own directory under state/sim, removed when it ends, even after an error (docs/errors.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from .. import tracker
from ..actions import catalog, executor
from ..config import ROOT
from ..hub import store
from ..loop import ROLE_PEOPLE
from .policy import ASSUMPTIONS, EnterpriseSandbox, baseline, impact, to_policy

# A growth team's weekly hours on the work the system takes over. An ESTIMATE with stated assumptions, to be replaced
# with a real team's own numbers: hours per week for a 12-market, 4-line business.
TIME_MODEL = [
    ("Weekly performance reporting across 12 markets (pulling platform, analytics and sales data, building the deck)", 12 * 1.5, "1.5 h per market"),
    ("Cross-checking platform-reported conversions against first-party sales", 4, "half a day"),
    ("Budget and channel-mix analysis and reallocation proposals", 8, "one day"),
    ("Benchmarking markets against last year and peers to find what is abnormal", 6, ""),
    ("Reading and tagging survey, review and ticket comments", 6, "about 2,700 comments a month at ~8 s each"),
    ("Writing stakeholder updates (leadership, finance, channel owners, product)", 5, ""),
    ("Chasing approvals and making the changes in each platform", 6, ""),
]


class Failed(Exception):
    """A run that stopped on purpose: `code` names it in docs/errors.md, the message ends with the fix."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@contextmanager
def _scratch(sim_dir: Path | None, hub: Path):
    """One private directory per run under state/sim, removed whatever happens, behind a lock so two runs never
    share files. Fails early (GOS-105) when the disk can't hold about five copies of the hub."""
    root = ROOT / "state" / "sim"
    root.mkdir(parents=True, exist_ok=True)
    need, free = 5 * hub.stat().st_size + 500 * 2**20, shutil.disk_usage(root).free
    if free < need:
        raise Failed("GOS-105", f"not enough disk for the simulation: {need / 2**30:.1f} GB needed, {free / 2**30:.1f} GB free in {root}. "
                                f"Fix: free space (old copies live in {root}), then run the same command again.")
    lock = root / "outcomes.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Failed("GOS-107", f"another outcomes run holds {lock}. Fix: wait for it to finish; if none is running, delete {lock} and run again.") from None
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    d = Path(tempfile.mkdtemp(prefix="outcomes-", dir=sim_dir or root))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)
        lock.unlink(missing_ok=True)


def _prepare(hub: Path, team_json: Path, d: Path) -> tuple[dict, Path, list[dict], date, date, int]:
    team = json.loads(team_json.read_text())
    work = d / "work.sqlite"
    shutil.copy(hub, work)
    with store.connect(work, read_only=True) as db:
        until = date.fromisoformat(db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0])
    tracker.record(work, team["decisions"], until.isoformat())
    with store.connect(work) as db:
        db.executemany("INSERT OR IGNORE INTO team (person, role) VALUES (?, ?)", [(p, r) for r, p in ROLE_PEOPLE.items()])
        db.commit()
    seed = int(json.loads((hub.parent / f"{hub.stem}.truth.json").read_text())["seed"])
    return team, work, executor.inbox(work), until, until + timedelta(days=1), seed


def _approve(work: Path, copy: Path, recs: list[dict], ids: set[int], start: date, seed: int):
    """Approve the given decisions in a copy of the hub, execute them, and read back the quarter's policy."""
    shutil.copy(work, copy)
    for r in recs:
        if r["id"] in ids:
            executor.decide(copy, r["id"], True, ROLE_PEOPLE[r["approver_role"]], r["approver_role"])
    ran = executor.run_approved(copy, EnterpriseSandbox(), today=start.isoformat())
    with store.connect(copy, read_only=True) as db:
        pol = to_policy(db, start, seed)
    return pol, ran


def run(hub: Path, team_json: Path, days: int = 91, sim_dir: Path | None = None, singles: bool = True) -> dict:
    """singles=False skips pricing each decision alone and simulates only the quarter with every decision approved."""
    with _scratch(sim_dir, hub) as d:
        team, work, recs, until, start, seed = _prepare(hub, team_json, d)
        results = []
        for r in recs if singles else []:  # each decision alone: approve it in a copy, execute, simulate the quarter
            one = d / f"one-{r['id']}.sqlite"
            pol, ran = _approve(work, one, recs, {r["id"]}, start, seed)
            base = baseline(start)
            changed = pol.mult or pol.paused or pol.weather_boost or pol.fixes != base.fixes
            sim = impact(pol, seed, days, until, label=f"rec{r['id']}", sim_dir=d) if changed else None
            results.append({"id": r["id"], "rank": r["rank"], "action": r["action"], "type": r["exec_type"], "target": r["exec_target"], "to": r["exec_to"],
                            "pct": r["exec_pct"], "risk": r["risk"], "approver": catalog.ROLES[r["approver_role"]], "executed": ran,
                            "simulated": bool(sim), "change": sim["change"] if sim else None, "change_pct": sim["change_pct"] if sim else None})
            one.unlink(missing_ok=True)
        for r in recs:  # all together
            executor.decide(work, r["id"], True, ROLE_PEOPLE[r["approver_role"]], r["approver_role"])
        executor.run_approved(work, EnterpriseSandbox(), today=start.isoformat())
        with store.connect(work, read_only=True) as db:
            pol = to_policy(db, start, seed)
            audit = [dict(x) for x in db.execute("SELECT kind, target, status, detail, approved_by FROM action_runs")]
        total = impact(pol, seed, days, until, label="all", sim_dir=d)
    hours = sum(h for _, h, _ in TIME_MODEL)
    return {"hub": hub.name, "from": start.isoformat(), "days": days, "decisions": results, "all_approved": total, "audit": audit,
            "assumptions": ASSUMPTIONS, "team_cost_usd": team.get("cost_usd"), "team_seconds": team.get("seconds"),
            "time_estimate": {"rows": [{"task": t, "hours_per_week": h, "basis": b} for t, h, b in TIME_MODEL], "hours_per_week": hours,
                              "note": "ESTIMATE: typical hours for this work in a 12-market team; replace with a real team's own numbers."},
            "note": "SIMULATED outcomes on a SYNTHETIC business; each decision measured alone and all together against doing nothing."}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def leave_one_out(hub: Path, team_json: Path, outcomes_json: Path, days: int = 91, only: list[int] | None = None,
                  sim_dir: Path | None = None) -> dict:
    """The quarter with every priced decision approved except one, for each priced decision (or only those in `only`).
    Unpriced decisions (no simulated effect) stay approved, as in the all-approved run. Same random draws as the
    outcomes report, so each run differs from the all-approved run only by the decision left out."""
    out = json.loads(outcomes_json.read_text())
    priced = [x["id"] for x in out["decisions"] if x["simulated"]]
    todo = only or priced
    if unknown := [i for i in todo if i not in priced]:
        raise Failed("GOS-102", f"decision(s) {unknown} are not priced in {outcomes_json} (priced: {priced}). Fix: pass --only with a priced id.")
    runs, baseline_gp = [], None
    with _scratch(sim_dir, hub) as d:
        team, work, recs, until, start, seed = _prepare(hub, team_json, d)
        if [r["id"] for r in recs] != [x["id"] for x in out["decisions"]]:
            raise Failed("GOS-102", f"{team_json} and {outcomes_json} list different decisions. Fix: regenerate the outcomes report: "
                                    f"python -m growth_os.enterprise.outcomes {hub} {team_json} {outcomes_json}")
        everyone = {r["id"] for r in recs}
        for left in todo:
            try:
                pol, _ = _approve(work, d / f"loo-{left}.sqlite", recs, everyone - {left}, start, seed)
                sim = impact(pol, seed, days, until, label=f"loo-{left}", sim_dir=d)
            except Exception as e:
                e.decision_id = left
                raise
            finally:
                (d / f"loo-{left}.sqlite").unlink(missing_ok=True)
            if baseline_gp is None:
                baseline_gp = sim["as_is"]["gross_profit"]
                if baseline_gp != out["all_approved"]["as_is"]["gross_profit"]:
                    raise Failed("GOS-102", f"the as-is quarter came out at {baseline_gp:,} gross profit, but {outcomes_json} was measured against "
                                            f"{out['all_approved']['as_is']['gross_profit']:,}. The hub or simulator changed since that report. "
                                            f"Fix: regenerate the outcomes report first, then run leave-one-out again.")
            runs.append({"left_out": left, "change": sim["change"], "change_pct": sim["change_pct"], "with_decisions": sim["with_decisions"]})
    return {"mode": "leave_one_out", "hub": hub.name, "from": start.isoformat(), "days": days,
            "inputs": {"team_json": team_json.name, "team_sha256": _sha(team_json), "outcomes_json": outcomes_json.name,
                       "outcomes_sha256": _sha(outcomes_json), "priced_ids": priced,
                       "all_approved_gross_profit": out["all_approved"]["change"]["gross_profit"]},
            "baseline_gross_profit": baseline_gp, "complete": sorted(todo) == sorted(priced), "runs": runs,
            "note": "SIMULATED: synthetic business; each run approves every decision except one and shares every random draw with the "
                    "all-approved run, so its difference from that run is the decision left out."}


def _merge(path: Path, part: dict) -> dict:
    """Fold an --only run into an existing report, but only when both were made from the same inputs."""
    if not path.is_file():
        return part
    full = json.loads(path.read_text())
    if full.get("inputs") != part["inputs"] or full.get("baseline_gross_profit") != part["baseline_gross_profit"]:
        return part
    runs = {r["left_out"]: r for r in full["runs"]} | {r["left_out"]: r for r in part["runs"]}
    full["runs"] = [runs[i] for i in full["inputs"]["priced_ids"] if i in runs]
    full["complete"] = len(full["runs"]) == len(full["inputs"]["priced_ids"])
    return full


def _write(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str))
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m growth_os.enterprise.outcomes",
                                 description="Measure the team's decisions over a simulated quarter (each alone and all together), "
                                             "or with --leave-one-out, all together minus one.")
    ap.add_argument("paths", nargs="*", help="HUB TEAM_JSON OUT (each-alone mode)")
    ap.add_argument("--leave-one-out", action="store_true", help="all priced decisions approved except one, for each priced decision")
    ap.add_argument("--seed", type=int, default=7, help="names the default hub and report paths (default 7)")
    ap.add_argument("--only", type=int, action="append", help="leave-one-out for this decision id only (repeatable)")
    ap.add_argument("--out", type=Path, help="report path (default reports/outcomes-loo-enterprise-<seed>.json)")
    a = ap.parse_args(argv)
    if not a.leave_one_out:
        if len(a.paths) != 3:
            ap.error("give HUB TEAM_JSON OUT, or use --leave-one-out")
        out = run(Path(a.paths[0]), Path(a.paths[1]))
        _write(Path(a.paths[2]), out)
        t = out["all_approved"]
        print(f"all approved: revenue {t['change']['revenue']:+,.0f} ({t['change_pct'].get('revenue')}%), gross profit {t['change']['gross_profit']:+,.0f} "
              f"({t['change_pct'].get('gross_profit')}%), spend {t['change']['spend']:+,.0f}; MER {t['as_is']['mer']} -> {t['with_decisions']['mer']}")
        for d in out["decisions"]:
            c = d["change"] or {}
            print(f"#{d['rank']} {d['type']:<20} {d['approver']:<22} rev {c.get('revenue', 0):+,.0f}  profit {c.get('gross_profit', 0):+,.0f}  {d['action'][:70]}")
        return 0
    hub = ROOT / "state" / f"enterprise-{a.seed}.sqlite"
    team, outcomes = ROOT / "reports" / f"team-enterprise-{a.seed}.json", ROOT / "reports" / f"outcomes-enterprise-{a.seed}.json"
    path = a.out or ROOT / "reports" / f"outcomes-loo-enterprise-{a.seed}.json"
    for need in (hub, team, outcomes):
        if not need.is_file():
            print(f"GOS-101: {need} is missing; leave-one-out needs the hub, the team run and its outcomes report. "
                  f"Fix: python -m growth_os.enterprise.prepare (hub), growth-os team (team run), then the each-alone outcomes run.", file=sys.stderr)
            return 1
    started = time.time()
    try:
        rep = leave_one_out(hub, team, outcomes, only=a.only)
    except Failed as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        log = ROOT / "reports" / f"loo-failure-{datetime.now():%Y%m%d-%H%M%S}.log"
        left = getattr(e, "decision_id", None)
        log.write_text(f"decision left out: {left}\nhub: {hub}\nteam: {team}\noutcomes: {outcomes}\n\n" + traceback.format_exc())
        rerun = f"python -m growth_os.enterprise.outcomes --leave-one-out --seed {a.seed}" + (f" --only {left}" if left else "")
        print(f"GOS-104: leave-one-out run for decision #{left} failed: {e}. Nothing was written to {path}; the run's files in state/sim "
              f"were removed. Trace: {log}. Fix: {rerun}", file=sys.stderr)
        return 1
    rep = _merge(path, rep) if a.only else rep
    _write(path, rep)
    for r in rep["runs"]:
        print(f"left out #{r['left_out']:<3} gross profit {r['change']['gross_profit']:+,.0f} vs as-is")
    print(f"wrote {path} ({'complete' if rep['complete'] else 'partial'}, {time.time() - started:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
