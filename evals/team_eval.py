"""Eval of the agent team on the enterprise world: does the team find what was planted, stay quiet on the traps,
propose actions that execute, and what are those actions worth over a simulated quarter?

    python evals/team_eval.py --seeds 301 302 303 --split heldout      # about 2.5 USD per seed (team + grader)

Grades: a separate Claude Opus grader checks the growth lead's decisions and findings, plus every specialist's
findings, against the answer key. Hard checks: decisions executable, numbers traceable to tool results, and the
simulated quarterly change in revenue and gross profit when every decision is approved.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from grounding import check as grounding_check  # noqa: E402
from growth_os.enterprise import outcomes, prepare, team  # noqa: E402
from growth_os.enterprise.world import planted as planted_for, scenario  # noqa: E402

def criteria(seed: int) -> tuple[dict, dict, dict]:
    planted, traps = planted_for(scenario(seed))
    c = {**{k: f"The team identifies this situation and attributes it to the right market (and line or device where relevant): {v}"
            for k, v in planted.items() if k != "overspend"},
         "seasonal_trap": f"The team does NOT present this market's drop against the previous period as a problem to act on; if mentioned, it is "
                          f"called seasonal or flat year over year. (Ground truth: {traps['seasonal_trap']})",
         "noise_markets": f"No decision acts on a problem in a noise-only market that is not one of the planted situations. (Ground truth: {traps['noise_markets']})",
         "right_owner": "Problems marketing cannot fix (payments, deliveries, stock, site, creative) go to the teams that fix them (open_ticket), not "
                        "answered with budget changes alone.",
         "sized_in_money": "The top decisions state the money at stake per month and are ranked by it."}
    return c, planted, traps


GRADER = """You grade the weekly output of an AI growth team (the growth lead's decisions plus each specialist's findings) against an
answer key. The business is synthetic; these situations were planted on purpose:
{key}

Grade each criterion pass or fail with one sentence pointing to the output. A situation counts as found if any specialist's finding or
the lead's decisions state it with the right market and direction; for criteria about decisions, look at the lead's recommendations."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["grades"], "properties": {"grades": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["criterion", "pass", "reason"],
    "properties": {"criterion": {"type": "string"}, "pass": {"type": "boolean"}, "reason": {"type": "string"}}}}}}


def grade(client, res: dict, seed: int) -> list[dict]:
    crit_d, planted, traps = criteria(seed)
    key = "\n".join(f"- {k}: {v}" for k, v in {**planted, **traps}.items())
    crit = "\n".join(f"- {k}: {v}" for k, v in crit_d.items())
    work = {"decisions": res["decisions"], "specialists": {k: [r["output"] for r in v] for k, v in res["specialists"].items()}}
    resp = client.messages.create(model="claude-opus-5-5", max_tokens=12000, system=GRADER.format(key=key),
                                  output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
                                  messages=[{"role": "user", "content": f"Criteria:\n{crit}\n\nTeam output (JSON):\n{json.dumps(work, ensure_ascii=False)}"}])
    if resp.stop_reason == "refusal":
        raise RuntimeError("grader declined")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))["grades"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[7])
    ap.add_argument("--split", choices=["dev", "heldout"], default="dev")
    ap.add_argument("--reuse", action="store_true", help="reuse a seed's saved team run (reports/team-eval-<seed>.json) instead of running the team again")
    a = ap.parse_args()
    client = anthropic.Anthropic(timeout=900, max_retries=3)
    runs = []
    for seed in a.seeds:
        hub = ROOT / "state" / f"team-eval-{seed}.sqlite"
        tj = ROOT / "reports" / f"team-eval-{seed}.json"
        reuse = a.reuse and tj.is_file()
        if not (reuse and hub.is_file()):
            prepare.prepare(hub, seed)
        if reuse:
            res = json.loads(tj.read_text())
        else:
            res = team.run_team(hub, "A consumer brand selling time-limited editions online in 12 cities and 4 product lines, about €3.3M of marketing a "
                                     "month. Leadership wants more revenue and gross profit from the same budget, and the problems fixed that cost the most.",
                                client=client)
            tj.parent.mkdir(exist_ok=True)
            tj.write_text(json.dumps(res, ensure_ascii=False, default=str))
        sources = [t["result"] for v in res["specialists"].values() for r in v for t in r["tool_calls"]]
        sources += [json.dumps(r["output"]) for v in res["specialists"].values() for r in v if r["output"]]
        g = grounding_check(res["decisions"], sources) if res["decisions"] else None
        out = outcomes.run(hub, tj) if res["decisions"] else None
        grades = grade(client, res, seed) if res["decisions"] else [{"criterion": c, "pass": False, "reason": "no decisions"} for c in criteria(seed)[0]]
        recs = res["decisions"].get("recommendations", []) if res["decisions"] else []
        hard = {"decisions": len(recs), "executable": sum(r["execution"]["type"] != "manual" for r in recs),
                "numbers_supported_pct": g["supported_pct"] if g else None,
                "quarter_revenue_change_pct": out["all_approved"]["change_pct"].get("revenue") if out else None,
                "quarter_gross_profit_change_pct": out["all_approved"]["change_pct"].get("gross_profit") if out else None,
                "quarter_gross_profit_change_eur": out["all_approved"]["change"]["gross_profit"] if out else None}
        runs.append({"seed": seed, "cost_usd": res["cost_usd"], "seconds": res["seconds"], "hard": hard, "grades": grades,
                     "agents": res["agents"], "routing": res["routing"]})
        print(f"seed {seed}: {sum(x['pass'] for x in grades)}/{len(grades)}, {hard}, ${res['cost_usd']}")
        for x in grades:
            if not x["pass"]:
                print(f"   FAIL {x['criterion']}: {x['reason']}")
    total = sum(len(r["grades"]) for r in runs)
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    summary = {"when": datetime.now().isoformat(timespec="seconds"), "scenario": "team-enterprise", "split": a.split, "commit": commit,
               "score": round(sum(x["pass"] for r in runs for x in r["grades"]) / total, 3), "runs": runs,
               "mean_cost_usd": round(sum(r["cost_usd"] for r in runs) / len(runs), 2)}
    path = ROOT / "evals" / "results" / f"team-enterprise-{a.split}-{datetime.now():%Y%m%d-%H%M}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"score {summary['score']:.0%}, mean cost ${summary['mean_cost_usd']}, saved {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
