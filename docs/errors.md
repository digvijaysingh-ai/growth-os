# Error codes

Every failure below prints its code first and its fix last, exits non-zero, and writes to stderr. None of them
leaves partial output: a build writes nothing until its checks pass, and a simulation removes its own folder.

## GOS-101

**A required input is missing.** The console build needs `reports/outcomes-loo-enterprise-<seed>.json` (or, without
hubs, `reports/console-data-7.json`); leave-one-out needs the hub, the team run and its outcomes report.
Fix: the message names the missing file and the command that makes it, usually
`python -m growth_os.enterprise.outcomes --leave-one-out --seed 7`.

## GOS-102

**The leave-one-out report is stale or inconsistent.** The team run or outcomes report changed since the runs, the runs
don't cover exactly the priced decisions, or the as-is quarter came out different (the hub or simulator changed).
The message prints both values, both paths and both report times.
Fix: regenerate in order: outcomes report, then leave-one-out. For local iteration only, `growth-os console
--allow-stale-loo` builds anyway and stamps the deck stale; a stale build must not be released.

## GOS-103

**A role string the console doesn't know.** Decisions and audit entries must map to Leadership, Growth manager,
Paid media manager, CRM manager, Product owner or Finance. The message names the decision or audit entry, never the
person's name.
Fix: add the role to `ROLE_LABELS` in `growth_os/console/build.py`.

## GOS-104

**A leave-one-out simulation failed.** The run stops, writes nothing to the report, removes its folder under
`state/sim`, and saves the traceback and the decision it was running to `reports/loo-failure-<time>.log`.
Fix: read the log, then rerun only that decision:
`python -m growth_os.enterprise.outcomes --leave-one-out --seed 7 --only <id>` (it merges into the existing report
only when both were made from the same inputs).

## GOS-105

**Not enough disk for the simulation.** A run needs about five copies of the hub plus 500 MB free.
Fix: free space (old copies may sit in `state/sim`), then run the same command again.

## GOS-106

**The publish scan found something that must not be published**: a name on the blocklist, a local path, or a key.
Each hit prints `file:line:rule` with the matched text masked.
Fix: remove the text (rotate the key if it was real), or, if it is a reviewed false positive, add a line to
`publish-scan.allow`: `rule file reason`.

## GOS-107

**Another outcomes run holds the lock** (`state/sim/outcomes.lock`), so two runs can't share files.
Fix: wait for it to finish. If none is running (a crash left the lock), delete the lock file and run again.
