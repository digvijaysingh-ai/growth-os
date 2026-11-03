"""Growth OS as an MCP server: ask the hub questions from Claude (or any MCP client) under the same rules as the agents.

Read-only by construction: one SELECT at a time, aggregates and anonymous rows only, no tool that changes anything.

    growth-os-mcp --hub state/b2c-hub.sqlite            # stdio, for Claude Code / Claude Desktop
    claude mcp add growth-os -- /path/to/.venv/bin/growth-os-mcp --hub /path/to/hub.sqlite
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .agents.analyst.analyst import run_sql
from .agents.analyst.stats import compare_rates as _compare
from .config import ROOT
from .hub import store

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
HUB = Path(os.environ.get("GROWTH_OS_HUB", str(store.DEFAULT_DB)))

server = MCPServer(
    name="growth-os", title="Growth OS hub",
    instructions=("Marketing data hub: ads, website funnel, sales, pipeline, customer voice themes and AI visibility, as daily aggregates. "
                  "Start with describe_hub, query the v_* views first, and use compare_rates before saying one rate beats another "
                  "(pass how many segments you scanned as comparisons). Everything is read-only."),
)


def _db():
    store.connect(HUB).close()  # bring an older file up to the current schema
    return store.connect(HUB, read_only=True)


@server.tool(annotations=READ_ONLY)
def describe_hub() -> str:
    """The hub's tables and views with row counts, plus the schema with what every column means. Call this first."""
    with _db() as db:
        objs = db.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
        counts = {n: db.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n, t in objs if t == "table"}
    tables = [f"{n}: {counts[n]} rows" for n, t in objs if t == "table" and counts[n]]
    views = [n for n, t in objs if t == "view"]
    return json.dumps({"hub": HUB.name, "tables_with_data": tables, "views": views}) + "\n\n" + store.SCHEMA.read_text()


@server.tool(annotations=READ_ONLY)
def query(sql: str) -> str:
    """Run one read-only SQLite SELECT (or WITH ... SELECT) on the hub; returns up to 200 rows as JSON."""
    with _db() as db:
        return run_sql(db, sql)


@server.tool(annotations=READ_ONLY)
def compare_rates(a_successes: int, a_n: int, b_successes: int, b_n: int, comparisons: int = 1) -> str:
    """Is rate B really different from rate A? Two-proportion z-test with 95% intervals, the sample needed to confirm the
    lift, and a Bonferroni correction when the comparison comes from scanning several segments (pass how many)."""
    return json.dumps(_compare(a_successes, a_n, b_successes, b_n, comparisons))


@server.tool(annotations=READ_ONLY)
def latest_memo() -> str:
    """The most recent growth memo written by the analyst agent (Markdown)."""
    files = sorted(glob.glob(str(ROOT / "reports" / "memo-*.md")))
    return Path(files[-1]).read_text() if files else "No memo yet: run growth-os analyse."


@server.tool(annotations=READ_ONLY)
def recommendations(status: str = "") -> str:
    """Tracked recommendations: what was proposed, who decided, the metric's baseline and whether it moved.
    status: proposed, accepted, rejected or empty for all."""
    with _db() as db:
        where = "WHERE status = ?" if status else ""
        rows = db.execute(f"SELECT id, memo_date, rank, action, confidence, status, decided_by, baseline, outcome, verdict FROM recommendations {where} ORDER BY id DESC LIMIT 50",
                          (status,) if status else ()).fetchall()
    return json.dumps([dict(r) for r in rows], default=str)


@server.tool(annotations=READ_ONLY)
def list_engines() -> str:
    """The analysis engines the agent team uses (benchmarks, demand, customer voice, marketing mix, budget), with each one's
    arguments. Call run_engine with a name and its arguments."""
    from .enterprise.tools import REGISTRY
    return json.dumps([{"name": t.name, "description": t.description, "arguments": t.props} for t in REGISTRY.values()])


@server.tool(annotations=READ_ONLY)
def run_engine(name: str, arguments_json: str = "{}") -> str:
    """Run one engine from list_engines on the hub, e.g. name="demand_potential", arguments_json="{}" or
    name="benchmark", arguments_json='{"market": "Berlin", "metric": "mer", "line": "all", "days": 28}'. Read-only."""
    from .enterprise.tools import call
    with _db() as db:
        return call(db, name, json.loads(arguments_json or "{}"))


def main() -> None:
    global HUB
    ap = argparse.ArgumentParser(prog="growth-os-mcp")
    ap.add_argument("--hub", type=Path, default=HUB)
    ap.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    a = ap.parse_args()
    HUB = a.hub.resolve()
    server.run(transport=a.transport)


if __name__ == "__main__":
    main()
