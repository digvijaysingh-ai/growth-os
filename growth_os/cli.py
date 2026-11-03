"""growth-os sync | check | report | status

  sync    daily: pull Meta and the website funnel into the hub (state/hub.sqlite)
  check   hourly: the ads agent judges every active ad, queues pause proposals, carries out approved ones
  report  weekly: numbers per ad + a summary paragraph, emailed through the site
  analyse the analyst reads the hub and writes the weekly growth memo (reports/memo-<date>.md)
  status  show what the ads agent sees right now, change nothing

--fixture FILE replays a saved data set offline (no Meta, no site, nothing sent) for demos and tests.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .report import ads as report
from .config import ROOT, Secrets, load_config, load_env
from .agents.ads.rules import evaluate, join
from .connectors import Meta, Site, SourceError, Window
from .hub import store
from .hub.sync import sync

STATE = ROOT / "state"
REPORTS = ROOT / "reports"


def log(event: str, **data) -> None:
    """Append-only decision log: every proposal, execution and skip, with the numbers behind it."""
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "decisions.jsonl").open("a") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "event": event, **data}, ensure_ascii=False) + "\n")


class Replay:
    """Meta and Site stand-ins that read a fixture and print what would have been sent."""

    def __init__(self, path: Path):
        self.d = json.loads(path.read_text())
        self.note = self.d.get("note", "")

    def insights(self, w): return self.d["insights"]
    def ads(self): return self.d["ads"]
    def stats(self, w): return self.d["site"]
    def actions(self, since): return self.d.get("actions", [])
    def approved(self): return [a for a in self.d.get("actions", []) if a.get("status") == "approved"]

    def propose(self, actions):
        for a in actions:
            print(f"  [replay] would propose: pause {a['ad_name']} ({a['rule']})")
        return [{"id": i, "ad_id": a["ad_id"], "new": True} for i, a in enumerate(actions, 1)]

    def pause(self, ad_id): print(f"  [replay] would pause ad {ad_id} in Meta"); return {"success": True}
    def done(self, action_id, ok, result): pass
    def send_ads(self, ads): pass
    def send_report(self, subject, body): print(f"  [replay] would email: {subject}")


def window(cfg: dict, fixture: Replay | None) -> Window:
    if fixture:
        return Window(date.fromisoformat(fixture.d["since"]), date.fromisoformat(fixture.d["until"]))
    today = datetime.now(ZoneInfo(cfg["account"].get("timezone", "Europe/Madrid"))).date()
    return Window(today - timedelta(days=int(cfg["account"].get("lookback_days", 7)) - 1), today)


def check(cfg: dict, meta, site, w: Window, execute: bool) -> int:
    ads = meta.ads()
    try:  # only feeds the dashboard's dropdown; never worth failing the check over
        site.send_ads(ads)
    except SourceError as e:
        log("send_ads_failed", error=str(e)[:300])
    views = join(meta.insights(w), ads, site.stats(w))
    verdicts = evaluate(views, cfg)
    pauses = [v for v in verdicts if v.action == "pause"]
    for v in verdicts:
        mark = "PAUSE?" if v.action == "pause" else "keep  "
        print(f"{mark} {(v.ad.ad_name or v.ad.ad_id)[:34]:<34} {v.rule:<22} {v.reason}")
    if pauses:
        new = []
        for res, v in zip(site.propose([v.proposal() for v in pauses]), pauses):
            if res.get("new"):
                log("proposed", **v.log())
                new.append(v.proposal())
        if new and not isinstance(meta, Replay):
            from . import notify
            if notify.send(notify.proposal_blocks(new, cfg.get("notify", {}).get("approvals_url", ""))):
                log("slack_sent", kind="proposals", count=len(new))
    for v in verdicts:
        if v.blocked_by:
            log("guarded", **v.log())

    # carry out only what the owner approved, and only if the ad is still running; same kill switch and audit log as
    # the decision inbox (actions/executor.py), so every executed action is in one place
    from .actions import executor
    if executor.killed():
        print("kill switch on: approved pauses are not executed")
        log("blocked", reason="kill switch")
        return 0
    live = {a["id"]: a.get("effective_status") for a in meta.ads()}
    for a in site.approved():
        if live.get(a["ad_id"]) != "ACTIVE":
            site.done(a["id"], True, f"already {live.get(a['ad_id'], 'gone')} in Meta, nothing to do")
            log("skipped", ad_id=a["ad_id"], reason="not active anymore")
            continue
        if not execute:
            print(f"approved but not executed (--no-execute): {a['ad_name']}")
            continue
        try:
            meta.pause(a["ad_id"])
            site.done(a["id"], True, "paused in Meta")
            if not isinstance(meta, Replay):
                with store.connect() as db:
                    db.execute("""INSERT INTO action_runs (rec_id, kind, target, params, adapter, status, before, after, detail, approved_by, ts)
                                  VALUES (NULL, 'pause_ad', ?, ?, 'meta', 'executed', '{"status": "ACTIVE"}', '{"status": "PAUSED"}', ?, ?, ?)""",
                               (a["ad_id"], json.dumps({"rule": a.get("rule")}), f"ads agent proposal approved on the dashboard: {a.get('ad_name')}",
                                a.get("decided_by", "owner"), datetime.now().isoformat(timespec="seconds")))
                    db.commit()
            log("paused", ad_id=a["ad_id"], ad_name=a.get("ad_name"), rule=a.get("rule"), approved_at=a.get("decided_at"))
            print(f"paused (approved): {a['ad_name']}")
        except SourceError as e:
            site.done(a["id"], False, str(e)[:300])
            log("pause_failed", ad_id=a["ad_id"], error=str(e)[:300])
    return 0


def weekly(cfg: dict, meta, site, w: Window, send: bool) -> int:
    views = [v for v in join(meta.insights(w), meta.ads(), site.stats(w)) if v.spend or v.leads]
    actions = site.actions(w.since)
    guarded = [{"ad_name": v.ad.ad_name or v.ad.ad_id, "rule": v.rule, "reason": v.reason}
               for v in evaluate(views, cfg) if v.blocked_by]
    f = report.facts(views, actions, cfg, w.since.isoformat(), w.until.isoformat(), guarded)
    paragraph, note = report.summary(f, cfg)
    text = report.render(views, actions, cfg, w.since.isoformat(), w.until.isoformat(), paragraph, note, guarded)
    out = REPORTS / f"{w.until.isoformat()}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)
    print(f"saved {out.relative_to(ROOT)}")
    # the growth memo goes on top: refresh the hub, then let the analyst read it (skipped in replays)
    memo_text = ""
    if not isinstance(meta, Replay) and cfg.get("analyst", {}).get("enabled", True):
        try:
            with store.connect() as db:
                sync(db, meta, site, Window(w.until - timedelta(days=34), w.until))
            memo = write_memo(cfg, store.DEFAULT_DB, w.until - timedelta(days=1))
            memo_text = memo[1] if memo else ""
        except Exception as e:  # the ads report still goes out if the memo fails
            log("memo_failed", error=str(e)[:300])
            memo_text = f"(The growth memo could not be written this week: {str(e)[:200]})\n"
    if send and memo_text and not isinstance(meta, Replay):
        from . import notify
        latest = json.loads((REPORTS / f"memo-{(w.until - timedelta(days=1)).isoformat()}.json").read_text()) if (REPORTS / f"memo-{(w.until - timedelta(days=1)).isoformat()}.json").is_file() else None
        if latest and notify.send(notify.memo_blocks(latest["memo"], business=cfg["account"].get("name", ""), period=f"{w.since:%d %b} – {w.until:%d %b}",
                                                     approvals_url=cfg.get("notify", {}).get("approvals_url", ""), console_url=cfg.get("notify", {}).get("console_url", ""))):
            log("slack_sent", kind="memo")
            from .actions import executor as ex
            mentions = cfg.get("notify", {}).get("roles", {})  # role -> "<@U123>" in config.toml [notify.roles]
            for rec in ex.inbox(store.DEFAULT_DB):
                notify.send(notify.decision_blocks(rec, mention=mentions.get(rec["approver_role"], ""), console_url=cfg.get("notify", {}).get("console_url", "")))
    if send:
        body = (memo_text + "\n" + "=" * 60 + "\n\n" + text) if memo_text else text
        site.send_report(f"Growth memo and ads report {w.since:%d/%m} - {w.until:%d/%m}", body)
        log("report_sent", since=w.since.isoformat(), until=w.until.isoformat())
    return 0


def write_memo(cfg: dict, hub: Path, until: date | None, days: int = 7, business: str | None = None,
               context: str | None = None, stem_name: str | None = None) -> tuple[str, str] | None:
    """Runs the analyst on the hub; saves the memo as Markdown + JSON and returns (markdown, plain text)."""
    from .agents.analyst.analyst import analyse
    from .report import memo as memo_fmt

    store.connect(hub).close()  # bring an older hub file up to the current schema before reading it read-only
    with store.connect(hub, read_only=True) as db:
        last = db.execute("SELECT MAX(day) FROM v_funnel_daily").fetchone()[0]
        until = until or (date.fromisoformat(last) if last else date.today())
        acct = cfg["account"]
        ctx = context if context is not None else (f"Target cost per lead: {acct['target_cpl']} {acct.get('currency', 'EUR')}. "
                                                  f"{cfg.get('analyst', {}).get('context', '')}").strip()
        name = business or acct.get("name", "")
        run = analyse(db, until, business=name, model=cfg.get("report", {}).get("model", "claude-opus-5-5"), context=ctx, days=days)
    if not run.memo:
        log("memo_failed", stop=run.stop, turns=run.turns)
        print(f"the analyst did not hand in a memo (stop: {run.stop}, turns: {run.turns})", file=sys.stderr)
        return None
    since = (until - timedelta(days=days - 1)).isoformat() if last else ""  # undated hubs (e.g. audience segments) have no period
    footer = (f"Written by {run.model} from the hub, in {run.turns} turns with {len(run.queries)} queries and "
              f"{len(run.comparisons)} statistical checks. Every number comes from the data; nothing was changed.")
    md = memo_fmt.markdown(run.memo, business=name, since=since, until=until.isoformat(), footer=footer)
    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = REPORTS / (stem_name or f"memo-{until.isoformat()}")
    stem.with_suffix(".md").write_text(md)
    stem.with_suffix(".json").write_text(json.dumps({"memo": run.memo, "queries": run.queries, "comparisons": run.comparisons,
        "turns": run.turns, "input_tokens": run.input_tokens, "output_tokens": run.output_tokens, "model": run.model}, ensure_ascii=False, indent=2))
    log("memo", until=until.isoformat(), turns=run.turns, queries=len(run.queries), tokens_in=run.input_tokens, tokens_out=run.output_tokens)
    from . import tracker
    recs = tracker.record(hub, run.memo, until.isoformat())
    log("recommendations_recorded", until=until.isoformat(), count=len(recs), with_working_metric=sum(r["metric_ok"] for r in recs))
    print(f"saved {stem.relative_to(ROOT)}.md and .json")
    return md, memo_fmt.plain(run.memo, business=name, since=since, until=until.isoformat()) + "\n" + footer + "\n"


def analyse_cmd(cfg: dict, hub: Path, until: date | None, days: int, business: str | None, context: str | None, name: str | None) -> int:
    if not hub.is_file():
        print(f"no hub at {hub}: run growth-os sync first", file=sys.stderr)
        return 2
    out = write_memo(cfg, hub, until, days, business, context, name)
    if out:
        print(out[0])
    return 0 if out else 1


def decision_cmd(a, cfg: dict) -> int:
    """The decision inbox: list, execute approved actions, roll back, run the simulated market forward, run the loop."""
    from .actions import catalog, executor
    from .actions.adapters import MetaAdapter, SandboxAdapter
    hub = a.hub or store.DEFAULT_DB
    if a.command == "inbox":
        rows = executor.inbox(hub)
        if not rows:
            print("inbox empty: nothing waiting for a decision")
        for r in rows:
            ex = f"{r['exec_type']} {r['exec_target']}" + (f" -> {r['exec_to']}" if r["exec_to"] else "") + (f" {r['exec_pct']:+g}%" if r["exec_pct"] else "")
            print(f"#{r['id']:<4} [{r['risk']:<6}] needs {catalog.ROLES[r['approver_role']]:<28} {ex}\n      {r['action'][:110]}")
        return 0
    if a.command == "loop":
        from . import loop
        if not a.memo or not a.hub:
            print("usage: growth-os loop --hub <b2c hub> --memo <memo.json> [--out reports/loop.json]", file=sys.stderr)
            return 2
        res = loop.main(a.hub, a.memo, a.out or REPORTS / "loop.json")
        for r in res["recommendations"]:
            d = r.get("delta", {})
            print(f"#{r['rank']} {r['label']:<32} {r['verdict']:<20} revenue {d.get('revenue', 0):+,.0f}  spend {d.get('spend', 0):+,.0f}  {r['action'][:60]}")
        print(f"saved {(a.out or REPORTS / 'loop.json')}")
        return 0
    if a.command == "simulate":
        from . import world
        print(f"simulated market now runs to {world.step(hub, a.days if a.days != 35 else 7)}")
        return 0
    adapter = SandboxAdapter()
    if a.live:
        s = Secrets.from_env()
        if s.missing():
            print("Missing in .env: " + ", ".join(s.missing()), file=sys.stderr)
            return 2
        adapter = MetaAdapter(Meta(s))
    if a.command == "serve":
        from .server import serve
        serve(hub, a.port, adapter)
        return 0
    if a.command == "execute":
        today = None
        if not a.live:  # the sandbox runs on the simulated market's clock: the day after its last day of data
            with store.connect(hub, read_only=True) as db:
                last = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
            today = (date.fromisoformat(last) + timedelta(days=1)).isoformat() if last else None
        for r in executor.run_approved(hub, adapter, today=today):
            print(f"#{r['id']} {r['type']} {r['target']}: {r['status']} — {r['detail']}")
        return 0
    if not a.dataset:
        print("usage: growth-os rollback <action run id> [--live]", file=sys.stderr)
        return 2
    try:
        print(executor.rollback(hub, int(a.dataset), adapter))
    except executor.Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="growth-os", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="enterprise (12-market agent team):\n"
                                       "  team     run the agent team on a hub: growth-os team --hub state/enterprise-7.sqlite (needs ANTHROPIC_API_KEY)\n"
                                       "  impact   measure a team run's decisions over a simulated quarter\n"
                                       "  console  build dist/console; without the hubs it renders the saved snapshot (no key needed)\n"
                                       "leave-one-out runs: python -m growth_os.enterprise.outcomes --leave-one-out --seed 7")
    p.add_argument("command", choices=["sync", "check", "report", "analyse", "status", "load", "listen", "console", "visibility", "followup", "decide",
                                        "inbox", "execute", "rollback", "simulate", "loop", "briefs", "remind", "serve", "team", "impact"])
    p.add_argument("dataset", nargs="?", help="load/listen: olist or fbads; decide: accept:<id> or reject:<id>")
    p.add_argument("--who", default="owner", help="decide: who made the decision (kept in the audit trail)")
    p.add_argument("--role", default="", help="decide: the decider's role (leadership, growth_manager, channel_manager, crm_manager, product_owner, finance)")
    p.add_argument("--reason", default="", help="decide reject: why (the next memo reads it)")
    p.add_argument("--live", action="store_true", help="execute/rollback: use the real Meta account (pause/resume only) instead of the sandbox")
    p.add_argument("--port", type=int, default=8787, help="serve: port for the Slack decision endpoint")
    p.add_argument("--memo", type=Path, help="loop: memo JSON to run through approve -> execute -> measure")
    p.add_argument("--out", type=Path, help="console: output folder (default dist/console)")
    p.add_argument("--allow-stale-loo", action="store_true",
                   help="console: build even if the leave-one-out runs are stale (local iteration only; the build is stamped stale)")
    p.add_argument("--visibility", type=Path, help="visibility: questions and brands file (TOML)")
    p.add_argument("--runs", type=int, default=3, help="visibility: answers per question (answers vary between runs)")
    p.add_argument("--rescore", action="store_true", help="visibility: re-count stored answers against the brand list, ask nothing new")
    p.add_argument("--sample", type=int, default=3000, help="listen: how many items to classify")
    p.add_argument("--direct", action="store_true", help="listen: call the API directly instead of the Batch API")
    p.add_argument("--raw", type=Path, default=ROOT / "data" / "raw", help="load: folder with the downloaded CSV files")
    p.add_argument("--hub", type=Path, help="analyse/load: hub database (default state/hub.sqlite)")
    p.add_argument("--until", type=date.fromisoformat, help="analyse: last day of the period (default: last day with data)")
    p.add_argument("--period-days", type=int, default=7, help="analyse: length of the period compared with the one before")
    p.add_argument("--business", help="analyse: business name for the memo")
    p.add_argument("--context", type=Path, help="analyse: text file with what the analyst should know about this business")
    p.add_argument("--name", help="analyse: file name for the memo in reports/ (default memo-<date>)")
    p.add_argument("--days", type=int, default=35, help="sync: how many days back to refresh")
    p.add_argument("--fixture", type=Path, help="replay a saved data set offline")
    p.add_argument("--config", type=Path)
    p.add_argument("--no-execute", action="store_true", help="check: never call Meta to pause, even approved ads")
    p.add_argument("--no-send", action="store_true", help="report: save it, don't email it")
    a = p.parse_args(argv)

    load_env()
    cfg = load_config(a.config)
    if a.command == "load":
        from .datasets import fbads, olist
        if a.dataset not in ("olist", "fbads") or not a.hub:
            print("usage: growth-os load olist|fbads --hub state/case-<name>.sqlite [--raw data/raw]", file=sys.stderr)
            return 2
        print({"olist": olist, "fbads": fbads}[a.dataset].load(a.raw, a.hub))
        return 0
    if a.command in ("followup", "decide"):
        from . import tracker
        hub = a.hub or store.DEFAULT_DB
        if a.command == "decide":
            if not a.dataset or a.dataset.split(":")[0] not in ("accept", "reject"):
                print("usage: growth-os decide accept:<id>|reject:<id> [--hub ...] [--who name]", file=sys.stderr)
                return 2
            from .actions import executor
            verb, rid = a.dataset.split(":")
            if not a.role:
                print("decide needs --who <person> and --role <role>; both are checked against the hub's team table", file=sys.stderr)
                return 2
            try:
                executor.decide(hub, int(rid), verb == "accept", a.who, a.role, a.reason)
            except executor.Refused as e:
                print(f"refused: {e}", file=sys.stderr)
                return 1
            print(f"recommendation {rid} {verb}ed by {a.who} ({a.role})" + (" — run `growth-os execute` to carry it out" if verb == "accept" else ""))
            return 0
        for r in tracker.followup(hub, a.until):
            print(f"#{r['id']} {r['verdict']}: {r['baseline']} -> {r['now']}  {r['action']}")
        print(tracker.summary(hub))
        return 0
    if a.command in ("inbox", "execute", "rollback", "simulate", "loop", "serve"):
        return decision_cmd(a, cfg)
    if a.command in ("team", "impact"):
        from .enterprise import policy as epol
        from .enterprise import team as eteam
        hub = a.hub or ROOT / "state" / "enterprise-7.sqlite"
        out = a.out or ROOT / "reports" / f"{a.command}-{hub.stem}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        if a.command == "team":
            ctx = a.context.read_text() if a.context else ("A consumer brand selling time-limited editions online in 12 cities and 4 product lines (Home, "
                   "Fashion drops, Beauty, Gifts), €50k–100k of marketing per line per market per month (about €3.3M a month) across Meta, TikTok, "
                   "YouTube, Google, affiliates and creators, plus email, SMS and organic. Leadership wants more revenue and gross profit from the same "
                   "budget, and the problems fixed that cost the most.")
            res = eteam.run_team(hub, ctx)
            out.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
            for ag in res["agents"]:
                print(f"{ag['role']:<24} {ag['turns']:>2} turns {ag['tool_calls']:>3} tool calls  ${ag['cost_usd']:.2f}  {ag['seconds']}s {ag['error']}")
            for r in res["routing"]:
                print(f"#{r['rank']} [{r['risk']}] {r['type']:<20} -> {r['approver']:<22} {r['action'][:80]}")
            print(f"total ${res['cost_usd']} in {res['seconds']}s; saved {out}")
            return 0
        print("use: python -m growth_os.enterprise.impact (see docs)")
        return 0
    if a.command in ("briefs", "remind"):
        from . import notify, stakeholders
        hub = a.hub or store.DEFAULT_DB
        if a.command == "briefs":
            b = stakeholders.briefs(hub)
            out = a.out or ROOT / "reports" / f"briefs-{b['as_of']}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(b, indent=1, ensure_ascii=False, default=str))
            out.with_suffix(".md").write_text(stakeholders.markdown(b))
            print(stakeholders.markdown(b))
            print(f"saved {out} and .md")
            return 0
        for r in stakeholders.reminders(hub):
            print(f"{r['kind']:<10} to {r['to']:<16} #{r['id']} waiting {r['waiting_hours']} h (service level {r['sla_hours']} h): {r['action'][:80]}")
            notify.send({"text": f"{'Escalation' if r['kind'] == 'escalation' else 'Reminder'}: decision #{r['id']} has waited {r['waiting_hours']} h. {r['action'][:200]}"})
        return 0
    if a.command == "visibility":
        from .visibility.track import run as vis_run
        if not a.hub or not a.visibility:
            print("usage: growth-os visibility --visibility cases/olist.visibility.toml --hub state/case-olist.sqlite [--runs 3]", file=sys.stderr)
            return 2
        if a.rescore:
            from .visibility.track import rescore
            print(rescore(a.visibility, a.hub))
        else:
            print(vis_run(a.visibility, a.hub, a.runs))
        return 0
    if a.command == "console":
        from .console.build import BuildError, build, default_views, render_snapshot
        snapshot = ROOT / "reports" / "console-data-7.json"
        views = default_views()
        try:
            if any(v["id"] == "enterprise-team" for v in views):
                out = build(a.out or ROOT / "dist" / "console", views, allow_stale=a.allow_stale_loo, snapshot=snapshot)
                print(f"console written to {out} ({len(views)} data sets; snapshot saved to {snapshot})")
            else:  # a clone without the hubs: the committed snapshot, no API key or model calls
                out = render_snapshot(a.out or ROOT / "dist" / "console", snapshot)
                print(f"console written to {out} from the saved snapshot {snapshot.name}")
        except BuildError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0
    if a.command == "listen":
        from .listening.run import listen
        if not a.dataset or not a.hub:
            print("usage: growth-os listen olist --hub state/case-olist.sqlite [--sample 3000] [--direct]", file=sys.stderr)
            return 2
        print(listen(a.dataset, a.raw, a.hub, a.sample, batch=not a.direct))
        return 0
    if a.command == "analyse":  # reads only the hub, so it needs no live credentials
        ctx = a.context.read_text() if a.context else None
        return analyse_cmd(cfg, a.hub or store.DEFAULT_DB, a.until, a.period_days, a.business, ctx, a.name)
    fixture = Replay(a.fixture) if a.fixture else None
    if fixture:
        global STATE, REPORTS
        STATE, REPORTS = ROOT / "state" / "replay", ROOT / "reports" / "replay"  # keep replays out of the real log
        print(f"Replaying {a.fixture.name}: {fixture.note}\n")
        meta = site = fixture
    else:
        s = Secrets.from_env()
        if s.missing():
            print("Missing in .env: " + ", ".join(s.missing()), file=sys.stderr)
            return 2
        meta, site = Meta(s), Site(s)
    w = window(cfg, fixture)
    try:
        if a.command == "sync":
            if fixture:
                print("sync reads live sources only; for a demo hub run: python -m growth_os.demo", file=sys.stderr)
                return 2
            sw = Window(w.until - timedelta(days=a.days - 1), w.until)
            with store.connect() as db:
                n = sync(db, meta, site, sw)
            log("synced", since=sw.since.isoformat(), until=sw.until.isoformat(), **n)
            print(f"hub synced {sw.since} to {sw.until}: {n['meta']} Meta rows, {n['site']} website rows -> state/hub.sqlite")
            return 0
        if a.command == "check":
            return check(cfg, meta, site, w, execute=not a.no_execute)
        if a.command == "report":
            return weekly(cfg, meta, site, w, send=not a.no_send)
        for v in evaluate(join(meta.insights(w), meta.ads(), site.stats(w)), cfg):
            print(f"{v.action:<6} {(v.ad.ad_name or v.ad.ad_id)[:34]:<34} {v.rule:<22} {v.reason}")
        return 0
    except SourceError as e:
        log("error", error=str(e)[:500])
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
