# TODOS

## Showcase

### Deck for the held-out businesses (seeds 301–303)
- **What:** let the console's decision deck switch between the showcase business and the three held-out businesses.
- **Why:** shows the approve/reject loop on businesses the agents never saw, not only the showcase run.
- **Pros:** stronger evidence of generalisation, same UI.
- **Cons:** per-decision quarter outcomes for 301–303 must be recomputed (the eval deleted its work files); more data in the console.
- **Context:** `reports/team-eval-30{1,2,3}.json` hold the decisions; `enterprise/outcomes.py` computes per-decision results.
- **Effort estimate:** human L / CC M
- **Priority:** P3
- **Depends on / blocked by:** the leave-one-out runs and deck for seed 7.

### Fresh private held-out seeds
- **What:** pick new seeds, keep them private, run the team eval on them after the repo is public.
- **Why:** publishing the full eval retires 301–303 as held-out; new seeds keep a live held-out claim.
- **Pros:** an honest, current held-out score.
- **Cons:** about $7.50 of model spend per three seeds and a grader run.
- **Context:** `evals/team_eval.py --seeds <new> --split heldout`.
- **Effort estimate:** human M / CC S
- **Priority:** P3
- **Depends on / blocked by:** public repo published.

### Shareable deck state in the URL hash
- **What:** encode the visitor's approve/reject choices in the console URL (`#<view>&deck=1:<12 a/r>`), sharing the view router.
- **Why:** lets a visitor or the LinkedIn post link to a specific "my quarter vs the AI" result.
- **Pros:** shareable results.
- **Cons:** needs one router for view and deck (template.html:597-600 already owns the hash), malformed-hash handling, tests.
- **Context:** full spec was written in the CEO review of 3 Nov 2026 (docs/plan/GOAL.md, CEO review record), then deferred as passive.
- **Effort estimate:** human M / CC S
- **Priority:** P3
- **Depends on / blocked by:** the decision deck.

## Product

### Enterprise team reads rejection reasons
- **What:** feed `reject_reason` from rejected decisions into the growth lead's next weekly run.
- **Why:** the decision layer should learn from "no"; today only the v1 analyst and stakeholder briefs read it.
- **Pros:** closes the loop the owner described; a rejected idea is not proposed again without new evidence.
- **Cons:** prompt change to the growth lead, so the team eval must be re-run.
- **Context:** growth_os/actions/executor.py:48-68 writes it; agents/analyst/analyst.py:386 shows the v1 pattern; growth_os/enterprise/team.py has no read.
- **Effort estimate:** human M / CC S
- **Priority:** P2
- **Depends on / blocked by:** nothing.

## Developer experience

### Per-command CLI help
- **What:** restructure `growth_os/cli.py` into argparse subparsers so `growth-os team --help` shows only team flags.
- **Why:** today every command prints the same global help listing v1 commands; evaluators can't tell which flags apply.
- **Pros:** guessable CLI; agents read layered help.
- **Cons:** touches every command's argument handling; needs a test per command.
- **Context:** found in the DX review of 3 Nov 2026; the epilog now lists team and impact as a stopgap.
- **Effort estimate:** human M / CC S
- **Priority:** P3
- **Depends on / blocked by:** nothing.

### Clear error when the team runs without an API key
- **What:** check `ANTHROPIC_API_KEY` before starting `growth-os team` / team_eval and fail with the env var name and a fix line.
- **Why:** today the client is built at growth_os/enterprise/team.py:273 and the auth failure surfaces inside worker threads.
- **Pros:** agent-ready error for the rerun path.
- **Cons:** small; needs one test with the key unset.
- **Context:** eng review 3 Nov 2026 marked this path unverified.
- **Effort estimate:** human S / CC S
- **Priority:** P2
- **Depends on / blocked by:** nothing.
