"""Asks an assistant the buyer questions (several runs each, since answers vary), then counts which brands it
mentions and which sites it used as sources (search results it read, plus any inline citations). Mentions are found by exact name matching, not judged by a model.

Today: Claude with live web search. Other assistants (ChatGPT, Gemini, Perplexity) plug in behind ask().
"""
from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from ..hub import store

MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT, PRICE_SEARCH = 4.0, 20.0, 10.0  # USD per million tokens; per thousand searches

SYSTEM = ("You are a helpful assistant answering a small business owner. Search the web when it helps, then answer in the "
          "language of the question with concrete recommendations, naming the companies or tools you recommend.")


@dataclass
class Brand:
    name: str
    aliases: list[str]
    domains: list[str]

    def pattern(self) -> re.Pattern:
        return re.compile(r"(?<![\w])(" + "|".join(re.escape(a) for a in self.aliases) + r")(?![\w])", re.I)


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        cfg = tomllib.load(f)
    cfg["brands"] = [Brand(b["name"], b.get("aliases", [b["name"]]), b.get("domains", [])) for b in cfg["brands"]]
    return cfg


def _domain(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def ask(client, question: str, max_searches: int = 3) -> dict:
    """One answer from Claude with web search; returns text, cited domains and usage."""
    messages = [{"role": "user", "content": question}]
    text, cited, usage = "", [], {"input_tokens": 0, "output_tokens": 0, "searches": 0}
    for _ in range(4):  # resume if the server pauses a long search turn
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=4000, system=SYSTEM, messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}],
            output_config={"effort": "low"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        usage["input_tokens"] += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens
        stu = getattr(resp.usage, "server_tool_use", None)
        usage["searches"] += getattr(stu, "web_search_requests", 0) or 0
        for b in resp.content:
            if b.type == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):  # an error is an object, not a list
                cited += [_domain(r.url) for r in b.content if getattr(r, "url", None)]
            if b.type == "text":
                text += b.text
                for c in getattr(b, "citations", None) or []:
                    if getattr(c, "url", None):
                        cited.append(_domain(c.url))
        if resp.stop_reason != "pause_turn":
            break
        messages = [{"role": "user", "content": question}, {"role": "assistant", "content": resp.content}]
    return {"text": text.strip(), "cited": cited, "usage": usage, "model": resp.model, "stop": resp.stop_reason}


def score(answer: str, cited: list[str], brands: list[Brand]) -> list[dict]:
    """Per brand: mentioned or not, rank by first mention, cited or not."""
    found = []
    for b in brands:
        m = b.pattern().search(answer)
        found.append({"brand": b.name, "pos": m.start() if m else None, "cited": any(d == bd or d.endswith("." + bd) for d in cited for bd in b.domains)})
    ranked = sorted((f for f in found if f["pos"] is not None), key=lambda f: f["pos"])
    for i, f in enumerate(ranked, 1):
        f["rank"] = i
    return [{**f, "mentioned": f["pos"] is not None, "rank": f.get("rank")} for f in found]


DISCOVER_SCHEMA = {"type": "object", "properties": {"companies": {"type": "array", "items": {"type": "string"}}},
                   "required": ["companies"], "additionalProperties": False}


def discover(client, answer: str) -> list[str]:
    """Every company, product or marketplace the answer names, so brands missing from the tracked list still surface."""
    import json
    resp = client.messages.create(
        model="claude-haiku-5-5", max_tokens=600, thinking={"type": "disabled"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": DISCOVER_SCHEMA}},
        messages=[{"role": "user", "content": "List every company, product, platform or marketplace named in this text, as written, without duplicates:\n\n" + answer[:12000]}],
    )
    if resp.stop_reason != "end_turn":
        return []
    names = json.loads(next(b.text for b in resp.content if b.type == "text")).get("companies", [])
    return list(dict.fromkeys(n.strip() for n in names if n and len(n) <= 60))


def rescore(config: Path, hub: Path, find_new: bool = True) -> dict:
    """Re-counts stored answers against the (edited) brand list; optionally re-runs discovery. No new questions are asked."""
    import anthropic

    cfg = load_config(config)
    client = anthropic.Anthropic(timeout=600, max_retries=3) if find_new else None
    with store.connect(hub) as db:
        rows = db.execute("SELECT answer_id, answer FROM ai_answers").fetchall()
        for aid, answer in rows:
            cited = [d for (d,) in db.execute("SELECT domain FROM ai_citations WHERE answer_id = ?", (aid,))]
            db.execute("DELETE FROM ai_mentions WHERE answer_id = ?", (aid,))
            db.executemany("INSERT INTO ai_mentions (answer_id, brand, mentioned, rank, cited) VALUES (?, ?, ?, ?, ?)",
                           [(aid, s["brand"], int(s["mentioned"]), s["rank"], int(s["cited"])) for s in score(answer, cited, cfg["brands"])])
            if find_new:
                db.execute("DELETE FROM ai_discovered WHERE answer_id = ?", (aid,))
                db.executemany("INSERT OR IGNORE INTO ai_discovered (answer_id, name) VALUES (?, ?)", [(aid, n) for n in discover(client, answer)])
        db.commit()
    return {"answers_rescored": len(rows), "brands": len(cfg["brands"])}


def run(config: Path, hub: Path, runs: int, log=print) -> dict:
    import anthropic

    cfg = load_config(config)
    client = anthropic.Anthropic(timeout=600, max_retries=3)
    today = date.today().isoformat()
    totals = {"answers": 0, "input_tokens": 0, "output_tokens": 0, "searches": 0}
    with store.connect(hub) as db:
        for q in cfg["questions"]:
            for r in range(1, runs + 1):
                a = ask(client, q["text"], cfg.get("max_searches", 3))
                aid = hashlib.sha1(f"{today}|{q['id']}|{r}".encode()).hexdigest()[:16]
                db.execute("INSERT OR REPLACE INTO ai_answers (answer_id, day, assistant, question_id, question, branded, run, answer, stop) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (aid, today, a["model"], q["id"], q["text"], int(q.get("branded", False)), r, a["text"][:20000], a["stop"]))
                db.execute("DELETE FROM ai_mentions WHERE answer_id = ?", (aid,))
                db.executemany("INSERT INTO ai_mentions (answer_id, brand, mentioned, rank, cited) VALUES (?, ?, ?, ?, ?)",
                               [(aid, s["brand"], int(s["mentioned"]), s["rank"], int(s["cited"])) for s in score(a["text"], a["cited"], cfg["brands"])])
                db.execute("DELETE FROM ai_citations WHERE answer_id = ?", (aid,))
                db.executemany("INSERT INTO ai_citations (answer_id, domain) VALUES (?, ?)", [(aid, d) for d in dict.fromkeys(a["cited"])])
                db.execute("DELETE FROM ai_discovered WHERE answer_id = ?", (aid,))
                db.executemany("INSERT OR IGNORE INTO ai_discovered (answer_id, name) VALUES (?, ?)", [(aid, n) for n in discover(client, a["text"])])
                db.commit()
                totals["answers"] += 1
                for k in ("input_tokens", "output_tokens", "searches"):
                    totals[k] += a["usage"][k]
                log(f"  {q['id']} run {r}: {len(a['text'])} chars, {len(set(a['cited']))} sites cited")
        store.log_sync(db, "ai-visibility", today, today, totals["answers"], f"{cfg.get('name', '')}: {len(cfg['questions'])} questions x {runs} runs on {MODEL} with web search")
    totals["cost_usd"] = round(totals["input_tokens"] / 1e6 * PRICE_IN + totals["output_tokens"] / 1e6 * PRICE_OUT + totals["searches"] / 1e3 * PRICE_SEARCH, 2)
    return totals
