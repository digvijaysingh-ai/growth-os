"""Collect, classify and store: `growth-os listen olist --hub ... --sample N`."""
from __future__ import annotations

from pathlib import Path

from ..hub import store
from . import classify, sources

HAIKU_IN, HAIKU_CACHE, HAIKU_OUT = 0.10, 0.01, 0.50  # USD per million tokens, claude-haiku-5-5, prompts under 100K


def listen(source: str, raw: Path, hub: Path, sample: int, batch: bool = True, log=print) -> dict:
    import anthropic

    if source != "olist":
        raise ValueError(f"unknown source {source}")
    items = sources.olist_reviews(raw, sample)
    client = anthropic.Anthropic(timeout=600, max_retries=3)
    labels, usage = classify.classify_batch(client, items, log=log) if batch else classify.classify_direct(client, items)
    by_id = {i["id"]: i for i in items}
    with store.connect(hub) as db:
        db.executemany("INSERT OR REPLACE INTO voice_items (item_id, day, source, rating, sentiment, segment, category, pain_point, summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       [(k, by_id[k]["day"], by_id[k]["source"], by_id[k]["rating"], v["sentiment"], by_id[k]["segment"], by_id[k]["category"],
                         v["pain_point"][:80], v["summary"][:200]) for k, v in labels.items()])
        db.executemany("INSERT OR IGNORE INTO voice_themes (item_id, theme) VALUES (?, ?)", [(k, t) for k, v in labels.items() for t in v["themes"]])
        store.log_sync(db, f"listen:{source}", min(i["day"] for i in items), max(i["day"] for i in items), len(labels),
                       f"{len(labels)} classified by {classify.MODEL}, {usage['failed']} failed")
    factor = 0.5 if batch else 1.0
    cost = factor * (usage["input_tokens"] * HAIKU_IN + usage["cache_read_input_tokens"] * HAIKU_CACHE + usage["output_tokens"] * HAIKU_OUT) / 1e6
    return {"items": len(items), "classified": len(labels), **usage, "cost_usd": round(cost, 3)}
