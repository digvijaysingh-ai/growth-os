"""Source adapters. Each returns items: {id, day, source, text, rating, segment, category}.

Today: Olist marketplace reviews (Kaggle). Reddit, YouTube comments, Google reviews, RSS and Bluesky plug in behind
the same shape; X and Meta are access-limited (see docs/listening.md).
"""
from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path


def _rows(raw: Path, name: str) -> list[dict]:
    with (raw / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def olist_reviews(raw: Path, sample: int, seed: int = 7) -> list[dict]:
    """Customer reviews with a written comment. segment = the acquisition channel of the merchant who sold the order,
    when that merchant came through the marketing funnel; otherwise 'merchant not from funnel'."""
    seller_of = {}
    category_of_product = {p["product_id"]: p["product_category_name"] for p in _rows(raw, "olist_products_dataset.csv")}
    english = {r["﻿product_category_name"] if "﻿product_category_name" in r else r["product_category_name"]: r["product_category_name_english"]
               for r in _rows(raw, "product_category_name_translation.csv")}
    category_of_order = {}
    for it in _rows(raw, "olist_order_items_dataset.csv"):
        seller_of.setdefault(it["order_id"], it["seller_id"])
        cat = category_of_product.get(it["product_id"], "")
        category_of_order.setdefault(it["order_id"], english.get(cat, cat))
    mql_origin = {m["mql_id"]: m["origin"] for m in _rows(raw, "olist_marketing_qualified_leads_dataset.csv")}
    channel_of_seller = {d["seller_id"]: mql_origin.get(d["mql_id"], "") or "(none)" for d in _rows(raw, "olist_closed_deals_dataset.csv")}

    items = []
    for r in _rows(raw, "olist_order_reviews_dataset.csv"):
        text = " ".join(x for x in (r["review_comment_title"].strip(), r["review_comment_message"].strip()) if x)
        if len(text) < 8:
            continue
        seller = seller_of.get(r["order_id"], "")
        items.append({
            "id": hashlib.sha1(r["review_id"].encode()).hexdigest()[:16], "day": r["review_creation_date"][:10], "source": "olist_reviews",
            "text": text[:1000], "rating": int(r["review_score"]),
            "segment": channel_of_seller.get(seller, "merchant not from funnel"), "category": category_of_order.get(r["order_id"], ""),
        })
    rnd = random.Random(seed)
    # every review from funnel merchants (the rare, interesting ones), then a random sample of the rest
    funnel = [i for i in items if i["segment"] != "merchant not from funnel"]
    rest = [i for i in items if i["segment"] == "merchant not from funnel"]
    return funnel + rnd.sample(rest, max(0, min(len(rest), sample - len(funnel))))
