# Does the agent team beat simpler setups?

Run on 3 November 2026 on the three held-out businesses (seeds 301–303). The team saw none of them during development. Three
arms ran on the same data, were graded by the same Claude grader in the same pass, and were priced by the same quarter-long
simulation (every decision approved, against the as-is business with its stated fix delays). Code: `evals/baselines.py`.
Raw results: `evals/results/baselines-301-302-303-20261103-1857.json`.

| Arm | What it is | Checks passed (AI grader) | Gross profit next quarter (simulated) | Model cost per week | Time |
|---|---|---|---|---|---|
| Agent team | Growth lead + four specialists choosing which tools to call | 37/45 | +2.7%, +4.6%, +3.9% (€3.78M) | $2.24–2.78 | 5.5–7 min |
| Single prompt | One Claude call, given every tool's output for every market up front | 35/45 | +3.4%, +4.2%, +4.4% (€4.06M) | $1.82–1.93 | 6–8 min |
| Rules playbook | No model: a fixed weekly checklist over the same tools, tuned on the development business only | 39/45 | +3.4%, +4.2%, +3.9% (€3.85M) | $0 | ~20 s |

## What this says

- **The team does not beat the simpler setups here.** All three land within a few checks and a few hundred thousand euros of each
  other. On three businesses that is noise, not a ranking.
- **The value is in the engines and the approval loop, not in the number of agents.** The statistics, the benchmarks, the mix model
  and the action catalogue are shared by all three arms, and they do most of the work. Once their output is on the table, one well-
  instructed call finds about as much as a team does.
- **Every arm misses Meta saturation on every business** (9 of 9). That is the mix model, not the agents: it overestimates returns
  (correlation 0.59 with the truth), so no reader of its output, human, model or rule, sees the saturation.
- **The playbook is an upper bound, not a naive baseline.** Its author knows which kinds of problem the generator plants. A real
  business has problems nobody listed in advance; that is where judgement over the same tools should matter, and this benchmark
  cannot show it.

## What it does not say

- It does not test open-ended problems: every situation here is one a checklist could name.
- The single prompt got every tool's output precomputed (~25k tokens). On a real business with more markets and data, that pack
  stops fitting and something has to choose what to look at.
- Three businesses is a small sample, and the grader is the same model family (see the grader check below).

## Grader check against a person

One person graded the team's 45 held-out checks (file: `evals/human/team-heldout-grades.json`, scorer: `python evals/human_grading.py team`).

| | Passed |
|---|---|
| Person | 41/45 |
| AI grader | 37/45 |
| Agreement | 37/45 (82%), Cohen's kappa 0.24 |

The AI grader was stricter on six checks (Meta saturation on all three businesses, the search-traffic drop on 301 and 302, the
demand gap on 302) and more lenient on two (brand search on 303, sizing in money on 302). Kappa is low because almost every check
passes, so chance agreement is already high: the grader's pass/fail on a single check is not reliable, and the totals above
should be read as ± a few checks. Whether the person saw the AI's verdicts while grading is not recorded.
