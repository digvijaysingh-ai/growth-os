"""Classifies items into a fixed taxonomy with Claude Haiku 5.5, through the Batch API (half price) or directly.

Each item gets: sentiment, one to three themes, the main pain point in a few English words, and a one-line English
paraphrase. The paraphrase replaces the original text in the hub, so no customer's words or identity are stored.
"""
from __future__ import annotations

import json
import re
import time

MODEL = "claude-haiku-5-5"

THEMES = {
    "late_delivery": "arrived later than promised",
    "not_delivered": "never arrived, or only part of the order arrived",
    "wrong_or_missing_item": "wrong product, colour, size or quantity, or an item missing",
    "damaged_or_defective": "arrived broken or does not work",
    "poor_quality": "works but quality is worse than expected",
    "not_as_described": "differs from the listing or photos",
    "seller_communication": "seller or support slow, unreachable or unhelpful",
    "returns_refunds": "trouble returning, exchanging or getting money back",
    "price_value": "comments on price or value for money",
    "fast_delivery": "praise for arriving quickly or early",
    "good_product": "praise for the product itself",
    "good_service": "praise for the seller, packaging or service",
    "would_recommend": "says they recommend the seller or product",
    "other": "none of the above",
}

SYSTEM = ("You label customer reviews from a Brazilian online marketplace (mostly in Portuguese) for a marketing team. "
          "Pick themes only from the list; use 'other' only if nothing fits. pain_point is the main complaint in at most 6 English "
          "words, or an empty string if there is none. summary is a neutral one-line English paraphrase, at most 20 words, with no "
          "names, phone numbers, order numbers or other personal details.\n\nThemes:\n"
          + "\n".join(f"- {k}: {v}" for k, v in THEMES.items()))

SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative", "mixed"]},
        "themes": {"type": "array", "items": {"type": "string", "enum": list(THEMES)}},
        "pain_point": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["sentiment", "themes", "pain_point", "summary"],
    "additionalProperties": False,
}


_REDACT = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"https?://\S+|www\.\S+"), "[link]"),
    (re.compile(r"\+?\d[\d\s().-]{7,}\d"), "[number]"),  # phone numbers, order and document numbers
]


def redact(text: str) -> str:
    """Strips contact details and long numbers before any model sees customer text. Names in free text are not
    reliably detectable this way; the hub never stores the text either way."""
    for pat, repl in _REDACT:
        text = pat.sub(repl, text)
    return text


def _params(item: dict) -> dict:
    return {
        "model": MODEL, "max_tokens": 400,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "thinking": {"type": "disabled"},
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        "messages": [{"role": "user", "content": f"Star rating: {item['rating']}/5\nReview: {redact(item['text'])}"}],
    }


def _parse(message) -> dict | None:
    if message.stop_reason != "end_turn":
        return None
    try:
        out = json.loads(next(b.text for b in message.content if b.type == "text"))
    except (StopIteration, json.JSONDecodeError):
        return None
    out["themes"] = list(dict.fromkeys(t for t in out.get("themes", []) if t in THEMES))[:3] or ["other"]
    return out


def classify_batch(client, items: list[dict], poll_seconds: int = 30, log=print) -> tuple[dict[str, dict], dict]:
    """Submits one batch, waits for it, returns ({item id: label}, usage)."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    batch = client.messages.batches.create(requests=[Request(custom_id=i["id"], params=MessageCreateParamsNonStreaming(**_params(i))) for i in items])
    log(f"batch {batch.id} submitted with {len(items)} items")
    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        log(f"  {b.processing_status}: {b.request_counts.processing} processing, {b.request_counts.succeeded} done")
        time.sleep(poll_seconds)
    labels, usage = {}, {"input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0, "failed": 0, "batch_id": batch.id}
    for r in client.messages.batches.results(batch.id):
        if r.result.type != "succeeded":
            usage["failed"] += 1
            continue
        m = r.result.message
        usage["input_tokens"] += m.usage.input_tokens
        usage["cache_read_input_tokens"] += m.usage.cache_read_input_tokens or 0
        usage["output_tokens"] += m.usage.output_tokens
        parsed = _parse(m)
        if parsed:
            labels[r.custom_id] = parsed
        else:
            usage["failed"] += 1
    return labels, usage


def classify_direct(client, items: list[dict]) -> tuple[dict[str, dict], dict]:
    """Same labels without the Batch API, for small runs and tests."""
    labels, usage = {}, {"input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0, "failed": 0}
    for i in items:
        m = client.messages.create(**_params(i))
        usage["input_tokens"] += m.usage.input_tokens
        usage["cache_read_input_tokens"] += m.usage.cache_read_input_tokens or 0
        usage["output_tokens"] += m.usage.output_tokens
        parsed = _parse(m)
        if parsed:
            labels[i["id"]] = parsed
        else:
            usage["failed"] += 1
    return labels, usage
