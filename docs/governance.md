# Governance

What the agents can and cannot do, what data they see, and how every decision can be traced.

## What each agent may do

| Agent | Reads | May propose | May do on its own |
|---|---|---|---|
| Ads agent | Meta delivery and status; website aggregates per ad | Pause an ad | Nothing. It carries out a pause only after a person approves it, and only if the ad is still running. |
| Analyst | The hub, read-only | Findings, recommendations and experiments in a memo | Nothing. It has no write access to anything. |

Not implemented on purpose: launching ads, changing budgets or bids, editing creatives, editing the website, or contacting leads.

## Approval flow

1. The ads agent proposes, with the rule, the reason and the numbers behind it.
2. The owner gets an email and decides in the dashboard (approve or reject).
3. Proposals nobody decides on expire after 3 days, so a stale one is never approved by accident.
4. On its next hourly run, the agent carries out approved pauses and records the result. If the ad is no longer running, it records that and does nothing.

## Guards

- No judgement until an ad has spent a minimum amount and had a minimum number of impressions (Meta's learning phase).
- Never propose a pause that would leave a campaign with no active ad.
- One open proposal per ad and action, so no duplicates.

## Data protection

- **Data minimisation.** The hub holds daily aggregates and anonymous lead rows (stage, source, sector, timing). It never holds names, phone numbers, emails, IP addresses, visitor keys or anything a person typed.
- **What reaches the model.**
  - The analyst and the ads agent see only aggregates and the hub's schema.
  - The listening classifier is the one exception. It has to read customer text to label it, so emails, phone numbers, links and long numbers are stripped first (`listening/classify.py: redact`). Names written inside free text can't be removed reliably by pattern, so treat the classifier as a processor of customer text under your data agreement with the model provider.
  - Only the labels and an English paraphrase are stored.
- **Website tracking.** First-party and cookieless, with nothing stored on the device. It respects Global Privacy Control and Do Not Track, and never stores the IP. It is designed so that no consent banner is needed: nothing is stored on or read from the visitor's device. Have your own counsel confirm that for your jurisdiction.
- **Meta Instant Forms.** Meta collects those leads under its own terms. The form links to the business's privacy policy, and the owner downloads leads and enters them by hand.
- **Secrets.** Tokens live in `.env` (git-ignored, readable only by the owner) and in the site's private config, never in code or in the hub.

## Audit trail

`state/decisions.jsonl` is append-only and records every:

- proposal and guard (with its metrics);
- approved pause and its result in Meta;
- skip ("ad no longer active");
- sync (rows per source);
- memo (turns, tokens);
- error.

Each memo's JSON also keeps every SQL query the analyst ran and every statistical check, so any number in a memo can be traced to the query that produced it.

## Failure behaviour

| If this fails | What happens |
|---|---|
| Meta or the site is unreachable | The run logs the error and exits; nothing is proposed or changed |
| The ad list can't be sent to the site | The check carries on; only the dashboard dropdown is stale |
| The analyst can't write a memo | The ads report still goes out, with a note that the memo is missing |
| Claude declines a request | Server-side fallback retries on a suitable model; if that also declines, the report goes without the summary |
