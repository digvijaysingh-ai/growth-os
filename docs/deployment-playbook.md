# Deployment playbook: from one business to a marketing organisation

Growth OS was built and piloted on one small business. This is how the same design would be rolled out in a company running many brands, markets or channels: what changes, what stays the same, and how each step earns the right to the next.

## What stays the same at any scale

- **One hub, joined once.** Every agent and every dashboard reads the same views, so teams stop arguing about whose number is right.
- **Agents propose, people decide.** Autonomy is widened one action at a time, and only after the approval log shows the agent's proposals were accepted and right.
- **Statistics before claims.** No recommendation without a sample-size check. At enterprise volume more tests reach significance, so this matters more, not less.
- **Evaluation before rollout.** Every agent change is graded against an answer key before it reaches a real team.

## What changes

| Concern | Pilot | Enterprise |
|---|---|---|
| Hub storage | SQLite file | BigQuery, Snowflake or Postgres; same schema, new `store.py` |
| Sources | Meta, website, small CRM | + Google Ads, TikTok, LinkedIn, GA4, HubSpot or Salesforce, product analytics. One connector each, same output shape |
| Scheduling | launchd on a laptop | Airflow, Cloud Scheduler or Managed Agents scheduled deployments |
| Approvals | Dashboard page | Slack or Teams approval cards routed to the budget owner, with spend limits per role |
| Identity and access | One owner | Single sign-on, roles per brand or market, approver ≠ requester for anything above a spend threshold |
| Audit | JSONL file | Append-only table in the warehouse, reviewed monthly |
| Analyst | One memo for one business | One memo per brand or market, plus a roll-up for leadership; the same evals per segment |

## Rollout in four phases

| Phase | Weeks | Scope | Exit criteria (all must hold) |
|---|---|---|---|
| **0. Baseline** | 1–2 | Connect sources, build the hub, no agents. Reconcile hub numbers with each platform's own reports. | Hub matches platform reports within 2%; the team agrees the definitions (lead, qualified lead, won) |
| **1. Shadow** | 2–4 | Agents run, but proposals and memos go only to the project team. Each one is compared with what the marketers decided themselves. | Ads agent: ≥80% of proposals the team would have made anyway, no harmful ones. Analyst: eval score ≥90% on that organisation's own planted-pattern set |
| **2. Assisted** | 4–8 | Proposals go to the real owners for approval. Weekly memo replaces the manual Monday report for one brand or market. | Approval rate and time-to-decision tracked. Hours of manual reporting saved per week measured. No incident from an approved action |
| **3. Scale** | 8+ | More brands, markets and channels. Selected low-risk actions (e.g. pausing an ad with zero leads after 3× target spend) can become automatic with a notification, never silent. | Each automated action has its own track record of being approved, and a rollback |

## KPIs for the programme itself

| KPI | Why it matters |
|---|---|
| Cost per qualified lead (or per opportunity) | The business outcome everything else serves |
| Money spent on ads breaking the rules, before vs after | Direct, attributable saving from the ads agent |
| Time from data to decision (data lands → change made) | The core promise: decisions in hours, not weeks |
| Hours of manual reporting per week | The cost that disappears first |
| Proposal acceptance rate and reversal rate | Whether the agents are trusted, and whether they deserve it |
| Analyst eval score per segment | Quality gate before any change ships |
| Agent cost per week | 0.60–2 USD per memo depending on scope; budget per brand or market at scale |

## Risks and how the design handles them

| Risk | Handled by |
|---|---|
| Agent acts on noise | Learning-phase guard; statistics tool; "too little data" is an allowed and expected answer |
| Agent acts on its own | Only one action exists, and it needs approval; no write access for the analyst |
| Personal data leaks to a model | The hub is aggregates only; the model never sees a person |
| Numbers nobody trusts | Phase 0 reconciliation; every memo number traceable to a stored query |
| Model or prompt change breaks quality | Eval harness with planted answers, run before every change |
| Platform API changes | Connectors isolated behind one output shape; a failed sync stops the run instead of producing wrong numbers |
