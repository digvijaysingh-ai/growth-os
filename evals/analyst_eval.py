"""Grades the analyst against a synthetic hub whose answers are known.

For each seed: build the demo hub (growth_os.demo, patterns planted on purpose), run the analyst, then a separate
grader call scores the memo on the criteria below, given the answer key. Hard checks (memo handed in, statistics
used, cost) are computed in code.

    .venv/bin/python evals/analyst_eval.py --seeds 7        # one run, about 1 USD
    .venv/bin/python evals/analyst_eval.py --seeds 7 11 23  # three runs
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from growth_os import behaviour, demo, demo_b2c, demo_enterprise, showcase  # noqa: E402
from grounding import check as grounding_check, sources_of  # noqa: E402
from growth_os.agents.analyst.analyst import analyse  # noqa: E402
from growth_os.hub import store  # noqa: E402

PRICE_IN, PRICE_OUT, PRICE_CACHE_READ, PRICE_CACHE_WRITE = 4.0, 20.0, 0.20, 5.0  # USD per million tokens, claude-opus-5-5

COMMON = {
    "no_budget_increase": "The memo does not recommend raising total ad spend.",
    "actionable": "Every recommendation is a concrete action someone could do in the next period, with a way to measure it.",
    "honest_uncertainty": "Where the memo reports a comparison of two rates, its confidence wording matches the evidence it quotes "
                          "(no 'proven' or 'clearly better' on samples the memo itself calls small).",
}

SCENARIOS = {
    "small": {
        "build": lambda seed, path: demo.build(path, seed=seed), "planted": demo.PLANTED, "days": 7,
        "business": "Demo Studio (synthetic)", "context": "Target cost per lead: 10 EUR.",
        "criteria": {
            **{k: f"The memo identifies this planted pattern as a finding or recommendation: {v}" for k, v in demo.PLANTED.items() if k != "tiny_sample_trap"},
            "tiny_sample_trap": "The memo does NOT present /oferta-b as a proven winner; if it mentions it, it says the sample is too small and at most proposes testing it. "
                                f"(Ground truth: {demo.PLANTED['tiny_sample_trap']})",
            **COMMON,
        },
    },
    "enterprise": {
        "build": lambda seed, path: demo_enterprise.build(path, seed=seed), "planted": demo_enterprise.PLANTED, "days": 28,
        "business": "Demo Group, 10 European markets (synthetic)",
        "context": "A web studio group running the same three Meta ads in 10 European markets (market column). Target cost per lead: 10 EUR. "
                   "The marketing director wants to know which markets need attention and why.",
        "criteria": {
            **{k: f"The memo identifies this planted pattern AND attributes it to the right market: {v}" for k, v in demo_enterprise.PLANTED.items() if k != "nl_tiny_trap"},
            "nl_tiny_trap": "The memo does NOT present /nl/oferta-b as a proven winner; if it mentions it, it says the sample is too small. "
                            f"(Ground truth: {demo_enterprise.PLANTED['nl_tiny_trap']})",
            "no_false_alarms": f"No finding with medium or high confidence claims a problem or a change in {', '.join(demo_enterprise.NOISE_ONLY)} "
                               "beyond the planted patterns. Those markets only contain random noise; calling them stable or normal is correct.",
            **COMMON,
        },
    },
    "b2c": {
        "build": lambda seed, path: demo_b2c.build(path, seed=seed), "planted": demo_b2c.PLANTED, "days": 28,
        "business": "Consumer brand, 12 cities (synthetic)",
        "context": "A consumer brand selling time-limited products online in 12 cities (market column), with paid acquisition on Meta, Google "
                   "(brand and generic search) and TikTok, plus email, organic and direct. sales_daily is first-party revenue by last click; "
                   "ad_daily holds delivery and what each platform claims. Products must sell before their end date. Currency EUR. The growth "
                   "director wants to know where money is being lost or left on the table this month, and what to do on Monday.",
        "criteria": {
            **{k: f"The memo identifies this planted situation AND attributes it to the right market (and ad or device where relevant): {v}"
               for k, v in demo_b2c.PLANTED.items() if not k.endswith("_trap")},
            "new_york_seasonal_trap": "The memo does NOT present New York's drop against the previous period as a problem; if it mentions it, it notes that "
                                      f"year over year it is flat or seasonal. (Ground truth: {demo_b2c.PLANTED['new_york_seasonal_trap']})",
            "porto_tiny_trap": f"The memo does NOT present a change in Porto as real with medium or high confidence. (Ground truth: {demo_b2c.PLANTED['porto_tiny_trap']})",
            "no_false_alarms": f"No finding with medium or high confidence claims a problem in {', '.join(demo_b2c.NOISE_ONLY)} beyond the planted situations.",
            "sized_in_money": "The top recommendations state the money at stake (revenue or spend, in EUR) and are ranked by it.",
            **COMMON,
        },
    },
}
# the full showcase: the B2C business plus behaviour data, journeys and targets, and recommendations that must execute
SCENARIOS["showcase"] = {
    **SCENARIOS["b2c"],
    "build": lambda seed, path: showcase.prepare(path, seed=seed), "planted": showcase.PLANTED,
    "context": SCENARIOS["b2c"]["context"] + " Behaviour data (product-analytics funnel steps, session behaviour, exit survey, stock events), "
               "customer journeys and the team's targets are also in the hub.",
    "criteria": {
        **SCENARIOS["b2c"]["criteria"],
        "ios_payment_signals": "The memo explains the Berlin/Amsterdam iOS problem as a payment failure, citing at least one behaviour source "
                               f"(payment step drop-off, rage clicks on /payment, or 'payment failed' survey answers). (Ground truth: {behaviour.PLANTED['ios_payment_signals']})",
        "ios_routed_to_engineering": "The memo's recommendation for the iOS payment failure is a ticket to engineering (execution type open_ticket, target "
                                     "engineering), not a marketing change.",
        "london_sellout": f"The memo identifies the London sell-out as lost demand for lack of capacity. (Ground truth: {behaviour.PLANTED['london_sellout']})",
        "mexico_trust_or_price": "The memo explains Mexico City's slow launch with what visitors say (trust / not knowing the brand), or at least does not call "
                                 f"it a price problem. (Ground truth: {behaviour.PLANTED['mexico_trust']})",
        "targets_used": "The memo names at least one market or ad that misses a stated target (MER, CAC, CPA, ROAS, CPM or payback) and by how much.",
        "attribution_honest": "Where the memo discusses a channel's value (e.g. brand search), it does not rely on last click or platform-claimed ROAS alone; "
                              "it uses the natural experiment, the data-driven view or proposes a holdout.",
    },
}

GRADER = """You grade a growth memo written by an AI analyst against an answer key.
The data it analysed is synthetic and had these patterns planted on purpose:
{key}

Grade each criterion pass or fail, with one sentence quoting or pointing to the memo.
Be strict: a pattern only counts as found if the memo states it with the right direction."""

SCHEMA = {
    "type": "object",
    "properties": {"grades": {"type": "array", "items": {"type": "object", "properties": {
        "criterion": {"type": "string"}, "pass": {"type": "boolean"}, "reason": {"type": "string"},
    }, "required": ["criterion", "pass", "reason"], "additionalProperties": False}}},
    "required": ["grades"], "additionalProperties": False,
}


def grade(client: anthropic.Anthropic, memo: dict, sc: dict) -> list[dict]:
    key = "\n".join(f"- {k}: {v}" for k, v in sc["planted"].items())
    crit = "\n".join(f"- {k}: {v}" for k, v in sc["criteria"].items())
    resp = client.messages.create(
        model="claude-opus-5-5", max_tokens=8000, system=GRADER.format(key=key),
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": f"Criteria:\n{crit}\n\nMemo (JSON):\n{json.dumps(memo, ensure_ascii=False)}"}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("grader declined")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))["grades"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[7])
    ap.add_argument("--scenario", choices=list(SCENARIOS), default="small")
    ap.add_argument("--split", choices=["dev", "heldout"], default="dev",
                    help="dev: seeds used while improving the analyst; heldout: run once on a frozen analyst, never tuned on")
    a = ap.parse_args()
    client = anthropic.Anthropic()
    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = []
    sc = SCENARIOS[a.scenario]
    for seed in a.seeds:
        hub = sc["build"](seed, ROOT / "state" / f"eval-{a.scenario}-{seed}.sqlite")
        with store.connect(hub, read_only=True) as db:
            run = analyse(db, date(2026, 10, 25), business=sc["business"], context=sc["context"], days=sc["days"], client=client)
        cost = (run.input_tokens * PRICE_IN + run.output_tokens * PRICE_OUT + run.cache_read_tokens * PRICE_CACHE_READ
                + run.cache_write_tokens * PRICE_CACHE_WRITE) / 1e6
        grades = grade(client, run.memo, sc) if run.memo else [{"criterion": c, "pass": False, "reason": "no memo"} for c in sc["criteria"]]
        hard = {"memo_handed_in": run.memo is not None, "used_statistics": len(run.comparisons) > 0}
        if run.memo:
            g = grounding_check(run.memo, sources_of(run))
            hard["numbers_supported_pct"] = g["supported_pct"]
            hard["numbers_unsupported"] = g["unsupported"]
            from growth_os import tracker
            recs = tracker.record(hub, run.memo, "2026-10-25")
            hard["recommendations_measurable"] = f"{sum(r['metric_ok'] for r in recs)}/{len(recs)}"
            hard["actions_executable"] = f"{sum(r['execution'] != 'manual' for r in recs)}/{len(recs)}"
            hard["memo_resubmitted_for_bad_actions"] = run.rejected_submits
        runs.append({"seed": seed, "grounding": grounding_check(run.memo, sources_of(run)) if run.memo else None, "turns": run.turns, "queries": len(run.queries), "comparisons": len(run.comparisons),
                     "cost_usd": round(cost, 2), "hard": hard, "grades": grades, "memo": run.memo})
        passed = sum(g["pass"] for g in grades)
        print(f"seed {seed}: {passed}/{len(grades)} criteria, hard checks {hard}, {run.turns} turns, ${cost:.2f}")
        for g in grades:
            print(f"   {'PASS' if g['pass'] else 'FAIL'} {g['criterion']}: {g['reason']}")
    total = sum(len(r["grades"]) for r in runs)
    score = sum(g["pass"] for r in runs for g in r["grades"]) / total if total else 0
    import subprocess
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "growth_os"], capture_output=True, text=True).stdout.strip())
    summary = {"when": datetime.now().isoformat(timespec="seconds"), "scenario": a.scenario, "split": a.split, "commit": commit + ("-dirty" if dirty else ""),
               "score": round(score, 3), "runs": runs,
               "mean_cost_usd": round(sum(r["cost_usd"] for r in runs) / len(runs), 2)}
    path = out_dir / f"analyst-{a.scenario}-{a.split}-{datetime.now():%Y%m%d-%H%M}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nscore {score:.0%} over {len(runs)} run(s), mean cost ${summary['mean_cost_usd']}, saved {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
