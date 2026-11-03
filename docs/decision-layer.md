# Decision layer: recommend → approve or reject → execute → measure

Dashboards stop at "here is what happened". A growth team's week is spent on what comes after: deciding what to do,
getting the right person to sign off, making the change in five tools, and checking weeks later whether it worked.
The decision layer does that part.

```
analyst memo ──► every recommendation carries ONE catalogue action (validated against the hub)
                    │
                    ▼
            decision inbox ──► routed to the role that must approve (by risk tier)
                    │                       │
              approve ▼                     ▼ reject (reason required)
          guardrails: kill switch,      reason stored; the next memo reads it
          role check, 4-eyes on risk,   and does not re-propose without new evidence
          budget caps per action/day
                    │
                    ▼
          adapter executes: sandbox account · Meta (live: pause/resume only) · tickets · email flows · Slack
                    │
                    ▼
          audit log (before/after) · one-click rollback · outcome measured on the recommendation's own metric
```

## The action catalogue

| Action | Target | Risk | Approver | Limits | Undo |
|---|---|---|---|---|---|
| pause_ad / resume_ad | ad | low | Paid media manager | — | the opposite |
| rotate_creative | ad | low | Paid media manager | budget moves to sibling ads | resume, restore budgets |
| change_budget | market | medium (high above +10%) | Growth manager (leadership above +10%) | −50% to +30% | restore |
| shift_budget | ad → ad, same market | medium | Growth manager | 5–50%, total unchanged | move back |
| launch_ab_test | page or step | low | Growth manager | — | stop, keep control |
| trigger_email_flow | product | medium | CRM manager | opted-in customers in that market only | stop the flow |
| open_ticket | team | low | Product / engineering owner | evidence in the ticket | close |
| notify | role | low | Growth manager | — | — |
| manual | — | — | Growth manager | tracked, not executed | — |

Defined in `growth_os/actions/catalog.py`. The analyst's `submit_memo` schema includes the action, and a memo whose
action names an ad, market or product that does not exist is sent back to the analyst with the errors.

## Guardrails

- **Kill switch**: `GROWTH_OS_KILL=1` or a file `state/KILL` blocks every execution and logs it as blocked.
- **Role check**: only the required role (or leadership) can approve.
- **Four eyes**: medium- and high-risk actions cannot be approved by whoever requested them.
- **Budget caps**: per action from the catalogue; across actions, at most 40% of budget change per day.
- **The live account is narrower than the catalogue**: the real pilot's adapter only pauses and resumes ads, and
  refuses anything else even if approved.
- **Audit log** (`action_runs`): every executed, blocked, failed or rolled-back action with before and after state.

## Measuring the decision, not just the metric

A metric moving after an action does not prove the action moved it. In the simulated business, every recommendation is
run forward twice from the same day with the same random draws: once approved and executed, once with nothing done.
The difference is what the decision was worth. The simulation's assumptions are listed in `growth_os/world.py` and
shown next to every result. In a real business the same comparison needs a holdout; the attribution module plans one.

## Commands

```bash
growth-os inbox --hub <hub>                                   # what is waiting, for whom
growth-os decide accept:12 --who "Sam" --role growth_manager --hub <hub>
growth-os decide reject:13 --reason "promo starts Monday" --who "Sam" --role growth_manager --hub <hub>
growth-os execute --hub <hub>                                 # sandbox; add --live for the real account
growth-os rollback 4 --hub <hub>
growth-os simulate --days 14 --hub <b2c hub>                  # run the simulated market forward
growth-os loop --hub <b2c hub> --memo reports/memo.json       # every recommendation: approved vs not, side by side
```
