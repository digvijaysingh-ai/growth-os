"""Voice of customer: what customers write in NPS surveys, exit surveys, reviews and support tickets, read by Claude.

    generate(hub, seed)   SYNTHETIC customer text for the enterprise world, in each market's language, with planted
                          issues hidden among everyday comments (template-built, labelled synthetic)
    classify(hub)         Claude Haiku 5.5 labels every item (theme, sentiment, one-line English summary) through the
                          Batch API; the labels go to voc_labels
    gaps(db)              which themes are over-represented in a market or line against everywhere else, whether that
                          is new (last 28 days vs before), significance corrected for cells scanned, and the market's
                          conversion and NPS beside it

    python -m growth_os.enterprise.voc state/enterprise-7.sqlite 7
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from ..agents.analyst.stats import compare_rates
from ..hub import store
from .profile import LINES, MARKETS

MODEL = "claude-haiku-5-5"
THEMES = {
    "delivery_late": "order arrived late or delivery date missed",
    "payment_problem": "payment failed, card declined, could not complete checkout",
    "price_value": "too expensive, price or value for money",
    "sold_out": "product sold out or unavailable",
    "trust_brand": "does not know or trust the brand, worried about scams or quality",
    "product_quality": "quality or condition of the product",
    "sizing_fit": "size or fit problems",
    "returns_refunds": "returns, exchanges or refunds",
    "customer_service": "support slow or unhelpful",
    "website_ux": "website hard to use, broken pages or links, search",
    "ad_fatigue": "sees the brand's ads too often, annoying ads",
    "wants_more_range": "wants more products, ranges or availability in their city",
    "praise_product": "likes the product",
    "praise_service": "likes delivery, packaging or service",
    "other": "none of the above",
}
LANG = {"Madrid": "es", "Barcelona": "es", "Mexico City": "es", "Lisbon": "pt", "São Paulo": "pt", "Paris": "fr", "Milan": "it",
        "Berlin": "de", "Amsterdam": "en", "London": "en", "New York": "en", "Miami": "en"}
T = {  # a few phrasings per theme and language; {p} is the product line
    "delivery_late": {"en": ["My order came a week late.", "Delivery was promised for Friday and arrived the next Thursday.", "Still waiting for my {p} order, tracking hasn't moved."],
                      "es": ["El pedido llegó una semana tarde.", "Me dijeron viernes y llegó el jueves siguiente.", "Sigo esperando mi pedido de {p}."],
                      "pt": ["A encomenda chegou uma semana atrasada.", "Ainda estou à espera do meu pedido."],
                      "fr": ["Ma commande est arrivée avec une semaine de retard.", "Toujours en attente de ma livraison."],
                      "it": ["L'ordine è arrivato con una settimana di ritardo.", "Consegna promessa per venerdì, arrivata giovedì dopo.", "Sto ancora aspettando il mio ordine, il tracking è fermo."],
                      "de": ["Die Lieferung kam eine Woche zu spät.", "Warte immer noch auf meine Bestellung."]},
    "payment_problem": {"en": ["Payment kept failing on my phone.", "The payment page froze at checkout, gave up.", "Card declined three times, it works everywhere else."],
                        "es": ["El pago falló varias veces desde el móvil.", "No pude pagar, la tarjeta daba error.", "La página de pago se quedaba colgada."],
                        "pt": ["O pagamento falhou no telemóvel.", "A página de pagamento bloqueou."], "fr": ["Le paiement échoue sur mon téléphone.", "Impossible de payer, la carte est refusée."],
                        "it": ["Il pagamento non andava a buon fine.", "La pagina di pagamento si blocca dal telefono."],
                        "de": ["Zahlung auf dem Handy ging nicht durch.", "Die Bezahlseite hat sich aufgehängt, habe abgebrochen.", "Karte dreimal abgelehnt, woanders geht sie."]},
    "price_value": {"en": ["A bit pricey for what it is.", "Too expensive compared with other shops."], "es": ["Demasiado caro.", "Precio alto para lo que es."],
                    "pt": ["Um pouco caro."], "fr": ["Trop cher."], "it": ["Un po' caro."], "de": ["Zu teuer."]},
    "sold_out": {"en": ["The {p} edition I wanted was sold out.", "Sold out before I could buy, again.", "Everything I liked was out of stock."],
                 "es": ["Estaba agotado."], "pt": ["Esgotado."], "fr": ["En rupture de stock."], "it": ["Era esaurito."], "de": ["War ausverkauft."]},
    "trust_brand": {"en": ["Never heard of this brand, not sure it's legit."], "es": ["No conozco la marca, no me fío.", "¿Es de confianza? Nunca había oído de ellos.", "Me da desconfianza comprar a una marca que no conozco."],
                    "pt": ["Não conheço a marca."], "fr": ["Je ne connais pas la marque."], "it": ["Non conosco il marchio."], "de": ["Kenne die Marke nicht."]},
    "product_quality": {"en": ["Quality could be better."], "es": ["La calidad podría ser mejor."], "pt": ["A qualidade podia ser melhor."],
                        "fr": ["Qualité moyenne."], "it": ["Qualità nella media."], "de": ["Qualität ist okay."]},
    "sizing_fit": {"en": ["Runs small, had to size up."], "es": ["Talla pequeña."], "pt": ["Tamanho pequeno."], "fr": ["Taille petit."], "it": ["Veste piccolo."], "de": ["Fällt klein aus."]},
    "returns_refunds": {"en": ["Return took ages to refund."], "es": ["La devolución tardó mucho."], "pt": ["O reembolso demorou."], "fr": ["Remboursement lent."],
                        "it": ["Rimborso lento."], "de": ["Rückerstattung dauerte lange."]},
    "customer_service": {"en": ["Support never answered my email."], "es": ["Atención al cliente no responde."], "pt": ["O apoio não responde."],
                         "fr": ["Le service client ne répond pas."], "it": ["Assistenza assente."], "de": ["Support antwortet nicht."]},
    "website_ux": {"en": ["Couldn't find the page from Google, link was broken."], "es": ["Los enlaces de Google dan error, la web cambió.", "No encuentro las páginas que antes salían en Google.", "La búsqueda de la web no funciona bien."],
                   "pt": ["O site é confuso."], "fr": ["Site difficile à utiliser."], "it": ["Sito confuso."], "de": ["Website unübersichtlich."]},
    "ad_fatigue": {"en": ["I see your ads ten times a day."], "es": ["Veo vuestros anuncios todo el rato."], "pt": ["Vejo os vossos anúncios sempre."],
                   "fr": ["Je vois votre pub partout, ça devient lourd.", "Toujours la même vidéo pub, dix fois par jour."], "it": ["Vedo i vostri annunci di continuo."],
                   "de": ["Sehe eure Werbung ständig."]},
    "wants_more_range": {"en": ["Wish you had more {p} options here."], "es": ["Ojalá hubiera más variedad."], "pt": ["Queria mais variedade."],
                         "fr": ["J'aimerais plus de choix."], "it": ["Vorrei più scelta."],
                         "de": ["Hätte gern mehr Auswahl bei {p}.", "Mehr {p} bitte, finde hier sonst nichts Vergleichbares.", "Gibt es das auch in anderen Sorten? Würde mehr kaufen."]},
    "praise_product": {"en": ["Love it, great {p}.", "Really happy with the quality."], "es": ["Me encanta.", "Muy contento con la compra."], "pt": ["Adorei."],
                       "fr": ["J'adore."], "it": ["Bellissimo."], "de": ["Super Produkt."]},
    "praise_service": {"en": ["Fast delivery, lovely packaging."], "es": ["Envío rápido."], "pt": ["Entrega rápida."], "fr": ["Livraison rapide."],
                       "it": ["Spedizione veloce."], "de": ["Schnelle Lieferung."]},
}
BASE_MIX = {"praise_product": 22, "praise_service": 12, "price_value": 12, "product_quality": 8, "delivery_late": 6, "sizing_fit": 4, "returns_refunds": 5,
            "customer_service": 5, "website_ux": 4, "sold_out": 4, "trust_brand": 3, "payment_problem": 2, "ad_fatigue": 2, "wants_more_range": 3, "other": 8}
def planted(seed: int) -> dict:
    """Customer-comment traces of the world's planted situations (same scenario as world.scenario(seed))."""
    from .world import scenario
    sc = scenario(seed)
    return {"delivery": (sc["delivery_market"], None, "delivery_late", 30, 6.0),
            "payment": ("|".join(sc["payment_markets"]), None, "payment_problem", 18, 9.0),
            "launch_trust": (sc["slow_launch"], None, "trust_brand", 56, 5.0),
            "sold_out": (sc["sellout"][0], sc["sellout"][1], "sold_out", 10, 8.0),
            "website": (sc["seo_market"], None, "website_ux", 40, 5.0),
            "ad_fatigue": (sc["fatigue"][0], sc["fatigue"][1], "ad_fatigue", 35, 6.0),
            "wants_more": (sc["demand_gap"][0], sc["demand_gap"][1], "wants_more_range", 120, 6.0)}


def generate(hub: Path, seed: int = 7, days: int = 120) -> int:
    db = store.connect(hub)
    until = date.fromisoformat(db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0])
    plants = planted(seed)
    rows = []
    for i in range(days):
        d = until - timedelta(days=days - 1 - i)
        ds = d.isoformat()
        for m in MARKETS:
            launched = db.execute("SELECT launched_on FROM market_profile WHERE market = ?", (m,)).fetchone()[0]
            if launched and ds < launched:
                continue
            for l in LINES:
                r = random.Random(f"voc|{seed}|{ds}|{m}|{l}")
                mix = dict(BASE_MIX)
                for _k, (pm, pl, theme, age, boost) in plants.items():
                    if m in pm.split("|") and (pl is None or pl == l) and d > until - timedelta(days=age):
                        mix[theme] *= boost
                for n in range(r.choice([1, 2, 2, 3])):
                    theme = r.choices(list(mix), weights=list(mix.values()))[0]
                    lang = LANG[m]
                    src = r.choices(["nps", "exit_survey", "review", "support_ticket"], weights=[40, 25, 25, 10])[0]
                    phr = T.get(theme, {}).get(lang) or T.get(theme, {}).get("en") or ["Ok."]
                    text = r.choice(phr).format(p=l.lower())
                    neg = theme not in ("praise_product", "praise_service", "other")
                    mild = theme in ("price_value", "product_quality", "sizing_fit", "wants_more_range", "other")
                    score = ((r.randint(6, 8) if mild else r.randint(0, 6)) if neg else r.randint(8, 10)) if src == "nps" else \
                        ((r.randint(2, 4) if neg else r.randint(4, 5)) if src == "review" else None)
                    rows.append((f"{seed}-{ds}-{m[:3]}-{l[:3]}-{n}", ds, m, l, src, score, lang, text))
    db.execute("DELETE FROM voc_items")
    db.executemany("INSERT INTO voc_items (item_id, day, market, line, source, score, lang, text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    store.log_sync(db, "voc", rows[0][1], rows[-1][1], len(rows), "SYNTHETIC customer text (NPS, exit survey, reviews, tickets), template-built")
    db.commit()
    db.close()
    return len(rows)


SYSTEM = ("You label customer comments for a consumer brand's growth team. Comments come from NPS surveys, exit surveys, reviews and support "
          "tickets, in Spanish, Portuguese, French, Italian, German or English. Pick the single best theme from the list; use 'other' only if "
          "nothing fits. summary is a neutral English paraphrase of at most 15 words with no personal details.\n\nThemes:\n"
          + "\n".join(f"- {k}: {v}" for k, v in THEMES.items()))
SCHEMA = {"type": "object", "properties": {"theme": {"type": "string", "enum": list(THEMES)},
                                           "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                                           "summary": {"type": "string"}},
          "required": ["theme", "sentiment", "summary"], "additionalProperties": False}


def classify(hub: Path, client=None, log=print) -> dict:
    """Labels every unlabelled item. Identical texts are labelled once (common in surveys), then mapped back."""
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    client = client or anthropic.Anthropic(timeout=600, max_retries=3)
    db = store.connect(hub)
    items = db.execute("SELECT v.item_id, v.text, v.source, v.score FROM voc_items v LEFT JOIN voc_labels l USING (item_id) WHERE l.item_id IS NULL").fetchall()
    from ..config import ROOT
    cache_path = ROOT / "data" / "external" / "voc-label-cache.json"  # labels for identical texts are reused across rebuilds
    cache = json.loads(cache_path.read_text()) if cache_path.is_file() else {}
    uniq_all = sorted({(t, s) for _, t, s, _ in items})
    key = {u: f"u{i}" for i, u in enumerate(uniq_all)}
    uniq = [u for u in uniq_all if f"{u[1]}|{u[0]}" not in cache]
    reqs = [Request(custom_id=key[(t, s)], params=MessageCreateParamsNonStreaming(
        model=MODEL, max_tokens=300, system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "disabled"}, output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": f"Source: {s}\nComment: {t}"}])) for t, s in uniq]
    usage = {"items": len(items), "unique_texts": len(uniq), "input_tokens": 0, "output_tokens": 0, "failed": 0}
    labels = {key[u]: cache[f"{u[1]}|{u[0]}"] for u in uniq_all if f"{u[1]}|{u[0]}" in cache}
    if reqs:
        _run_batch(client, reqs, labels, usage, log)
        inv = {v: k for k, v in key.items()}
        cache.update({f"{inv[k][1]}|{inv[k][0]}": v for k, v in labels.items()})
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    _store(db, items, key, labels)
    usage["cost_usd"] = round((usage["input_tokens"] * 0.10 + usage["output_tokens"] * 0.50) / 1e6 / 2, 4)  # batch = half price
    return usage


def _run_batch(client, reqs, labels, usage, log):
    import time
    b = client.messages.batches.create(requests=reqs)
    log(f"batch {b.id}: {len(reqs)} unique texts")
    while client.messages.batches.retrieve(b.id).processing_status != "ended":
        time.sleep(20)
    for r in client.messages.batches.results(b.id):
        if r.result.type != "succeeded" or r.result.message.stop_reason != "end_turn":
            usage["failed"] += 1
            continue
        m = r.result.message
        usage["input_tokens"] += m.usage.input_tokens + (m.usage.cache_read_input_tokens or 0)
        usage["output_tokens"] += m.usage.output_tokens
        try:
            labels[r.custom_id] = json.loads(next(x.text for x in m.content if x.type == "text"))
        except (StopIteration, json.JSONDecodeError):
            usage["failed"] += 1


def _store(db, items, key, labels):
    db.executemany("INSERT OR REPLACE INTO voc_labels (item_id, theme, sentiment, summary, model) VALUES (?, ?, ?, ?, ?)",
                   [(iid, labels[key[(t, s)]]["theme"], labels[key[(t, s)]]["sentiment"], labels[key[(t, s)]]["summary"], MODEL)
                    for iid, t, s, _ in items if key[(t, s)] in labels])
    store.log_sync(db, "voc-labels", "", "", len(labels), f"themes by {MODEL} (Batch API)")
    db.commit()
    db.close()


def gaps(db, days: int = 28) -> list[dict]:
    """Themes over-represented in a market (or market × line) in the last `days`, against all other markets, and
    whether they are new against the market's own earlier weeks."""
    asof = db.execute("SELECT MAX(day) FROM voc_items").fetchone()[0]
    if not asof:
        return []
    rows = db.execute(f"""SELECT v.market, v.line, l.theme, v.day > date(?, '-{days} days') AS recent, COUNT(*) AS n
                          FROM voc_items v JOIN voc_labels l USING (item_id) GROUP BY 1, 2, 3, 4""", (asof,)).fetchall()
    tot_recent = {}
    cell = {}
    for m, l, th, rec, n in rows:
        for scope in ((m, ""), (m, l)):
            c = cell.setdefault(scope, {}).setdefault(th, [0, 0])
            c[0 if rec else 1] += n
        if rec:
            tot_recent[th] = tot_recent.get(th, 0) + n
    all_recent = sum(tot_recent.values()) or 1
    scanned = len(cell) * len(THEMES)
    nps = {(r[0], ""): r[1] for r in db.execute(f"""SELECT market, ROUND(100.0 * (SUM(score >= 9) - SUM(score <= 6)) / COUNT(*), 0) FROM voc_items
                                                   WHERE source = 'nps' AND day > date(?, '-{days} days') GROUP BY 1""", (asof,))}
    out = []
    for (m, l), themes in cell.items():
        n_recent = sum(v[0] for v in themes.values())
        n_before = sum(v[1] for v in themes.values())
        if n_recent < 30:
            continue
        for th, (k_rec, k_bef) in themes.items():
            if th.startswith("praise") or th == "other":
                continue
            base_k = tot_recent.get(th, 0) - (k_rec if l == "" else 0)
            base_n = all_recent - (n_recent if l == "" else 0)
            v = compare_rates(base_k, base_n, k_rec, n_recent, scanned)
            if "different" not in v["verdict"] or k_rec / n_recent <= base_k / max(1, base_n):
                continue
            trend = compare_rates(k_bef, n_before, k_rec, n_recent, 1) if n_before else None
            out.append({"market": m, "line": l or "all lines", "theme": th, "share_pct": round(100 * k_rec / n_recent, 1),
                        "elsewhere_pct": round(100 * base_k / max(1, base_n), 1), "mentions": k_rec, "of": n_recent,
                        "before_pct": round(100 * k_bef / n_before, 1) if n_before else None,
                        "new": bool(trend and "different" in trend["verdict"] and k_rec / n_recent > k_bef / max(1, n_before)),
                        "nps": nps.get((m, "")), "p_value": v["p_value"]})
    return sorted(out, key=lambda x: -(x["share_pct"] / max(0.5, x["elsewhere_pct"])))


if __name__ == "__main__":
    h = Path(sys.argv[1])
    print(f"{generate(h, int(sys.argv[2]) if len(sys.argv) > 2 else 7)} SYNTHETIC customer comments")
    if "--classify" in sys.argv:
        print(classify(h))
