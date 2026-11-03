"""SYNTHETIC behaviour data for the B2C scenario: product-analytics funnel steps, session-behaviour signals and an
exit survey, derived from the scenario's own sessions, checkouts and orders so every source tells one story.

What it adds on top of demo_b2c (planted, for the analyst and the why-not-buy engine to find):
  - the Berlin/Amsterdam iOS payment failure shows up as visitors reaching the payment step and not purchasing, rage
    clicks on /payment and "payment failed" in the exit survey; it is derived from the orders data, so a fix shows too
  - Mexico City: visitors say they do not know or trust the brand yet
  - Madrid 'Autumn special': visitors say it costs too much
  - London: one product sells out early (capacity), visitors keep asking for it and say "sold out"

Random draws are seeded per day and cell, so running it on a world copy gives the same answers where nothing changed.

    python -m growth_os.behaviour state/loop-b2c-7.sqlite
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

from .hub import store

PLANTED = {
    "ios_payment_signals": "Berlin and Amsterdam iOS: visitors reach the payment step but do not purchase, rage clicks on /payment jump, "
                           "and 'payment_failed' becomes a leading exit-survey reason there (other markets and devices are normal).",
    "mexico_trust": "Mexico City exit-survey answers name 'trust' (not knowing the brand) far more often than other markets: the slow launch is a "
                    "brand-awareness problem, not price.",
    "madrid_price": "Madrid 'Autumn special': exit-survey answers about it are dominated by 'price', which explains its slow sales.",
    "london_sellout": "London: one product sold out about 10 days before the data ends, well before its end date; visitors keep viewing it and "
                      "'sold_out' rises in London's exit survey: demand is being turned away for lack of capacity.",
}
REASONS = {"just_browsing": 45, "price": 18, "delivery_or_date": 12, "trust": 8, "sold_out": 5, "payment_failed": 3, "other": 9}
SURVEY_RATE = 0.03  # share of non-buying visitors who answer


def _r(seed, *key) -> random.Random:
    return random.Random("|".join(map(str, ("bhv", seed, *key))))


def plant_sellout(db, until: date) -> str | None:
    """Caps one London product at what it had sold 10 days before `until`: it sells out, sales stop."""
    cut = (until - timedelta(days=10)).isoformat()
    row = db.execute("""SELECT p.product_id FROM products p WHERE p.market = 'London' AND p.launch_day <= ? AND p.end_day >= ?
                        ORDER BY p.launch_day DESC LIMIT 1""", (date.fromisoformat(cut).isoformat(), (until + timedelta(days=7)).isoformat())).fetchone()
    if not row:
        return None
    pid = row[0]
    if db.execute("SELECT 1 FROM stock_events WHERE product_id = ?", (pid,)).fetchone():
        return pid
    sold = db.execute("SELECT COALESCE(SUM(units), 0) FROM product_daily WHERE product_id = ? AND day <= ?", (pid, cut)).fetchone()[0]
    db.execute("UPDATE products SET capacity = ? WHERE product_id = ?", (sold, pid))
    db.execute("UPDATE product_daily SET units = 0, revenue = 0 WHERE product_id = ? AND day > ?", (pid, cut))
    db.execute("INSERT OR IGNORE INTO stock_events (product_id, day, event) VALUES (?, ?, 'sold_out')", (pid, cut))
    return pid


def add(hub: Path, since: str | None = None, seed: int = 7) -> int:
    """Derives behaviour rows for every day from `since` (default: all days in sales_daily). Returns rows written."""
    db = store.connect(hub)
    last = date.fromisoformat(db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0])
    if since is None:
        origin = db.execute("SELECT until FROM sync_log WHERE source = 'demo-b2c' ORDER BY ts LIMIT 1").fetchone()
        plant_sellout(db, date.fromisoformat(origin[0]) if origin else last)
    since = since or db.execute("SELECT MIN(day) FROM sales_daily").fetchone()[0]
    agg = db.execute("""SELECT day, market, device, SUM(sessions) AS s, SUM(checkouts) AS co, SUM(orders) AS o FROM sales_daily
                        WHERE day >= ? GROUP BY day, market, device""", (since,)).fetchall()
    sold_out = {r[0]: r[1] for r in db.execute("SELECT product_id, day FROM stock_events WHERE event = 'sold_out'")}
    restocked = {r[0]: r[1] for r in db.execute("SELECT product_id, day FROM stock_events WHERE event = 'restocked'")}
    active = {}
    for p in db.execute("SELECT product_id, market, name, launch_day, end_day FROM products"):
        active.setdefault(p[1], []).append(dict(p))
    events, ux, survey = [], [], []
    for day, m, dev, s, co, o in agg:
        r = _r(seed, day, m, dev)
        view = round(s * r.uniform(0.58, 0.66))
        cart = max(co, round(co * r.uniform(1.75, 2.05)))
        pay = max(o, round(co * r.uniform(0.86, 0.93)))
        events += [dict(day=day, market=m, device=dev, step=k, users=v) for k, v in
                   (("session_start", s), ("view_product", view), ("add_to_cart", cart), ("begin_checkout", co), ("add_payment", pay), ("purchase", o))]
        fail = max(0.0, 0.60 - (o / co if co else 0.6))  # payment failures, read from the orders data itself
        on_sale = [p for p in active.get(m, []) if p["launch_day"] <= day <= p["end_day"]]
        so = [p for p in on_sale if p["product_id"] in sold_out and day > sold_out[p["product_id"]] and not day >= restocked.get(p["product_id"], "9999")]
        ux += [
            dict(day=day, market=m, device=dev, page="/product", sessions=view, rage_clicks=r.binomialvariate(view, 0.004 + (0.02 if so else 0)),
                 dead_clicks=r.binomialvariate(view, 0.01), avg_scroll_pct=round(r.uniform(52, 62), 1), exits=max(0, view - cart)),
            dict(day=day, market=m, device=dev, page="/cart", sessions=cart, rage_clicks=r.binomialvariate(cart, 0.003),
                 dead_clicks=r.binomialvariate(cart, 0.008), avg_scroll_pct=round(r.uniform(60, 72), 1), exits=max(0, cart - co)),
            dict(day=day, market=m, device=dev, page="/checkout", sessions=co, rage_clicks=r.binomialvariate(co, 0.004),
                 dead_clicks=r.binomialvariate(co, 0.008), avg_scroll_pct=round(r.uniform(70, 82), 1), exits=max(0, co - pay)),
            dict(day=day, market=m, device=dev, page="/payment", sessions=pay, rage_clicks=r.binomialvariate(pay, min(0.6, 0.006 + 0.9 * fail)),
                 dead_clicks=r.binomialvariate(pay, 0.006 + 0.2 * fail), avg_scroll_pct=round(r.uniform(80, 92), 1), exits=max(0, pay - o)),
        ]
        weights = dict(REASONS)
        weights["payment_failed"] += 260 * fail
        if m == "Mexico City":
            weights["trust"] *= 3.2
        if so:
            weights["sold_out"] *= 6
        n = r.binomialvariate(max(0, s - o), SURVEY_RATE)
        counts: dict[tuple[str, str], int] = {}
        for _ in range(n):
            reason = r.choices(list(weights), weights=list(weights.values()))[0]
            pid = ""
            if on_sale:
                autumn = [p for p in on_sale if "Autumn special" in p["name"]]
                if reason == "price" and autumn and r.random() < 0.7:
                    pid = autumn[0]["product_id"]
                elif reason == "sold_out" and so:
                    pid = so[0]["product_id"]
                else:
                    pid = r.choice(on_sale)["product_id"]
            if m == "Madrid" and pid and "Autumn special" in next(p["name"] for p in on_sale if p["product_id"] == pid) and reason == "just_browsing" and r.random() < 0.5:
                reason = "price"
            counts[(pid, reason)] = counts.get((pid, reason), 0) + 1
        survey += [dict(day=day, market=m, device=dev, product_id=pid, reason=k, responses=v) for (pid, k), v in counts.items()]
    for t, rows, cols in (("events_daily", events, ["day", "market", "device", "step", "users"]),
                          ("ux_daily", ux, ["day", "market", "device", "page", "sessions", "rage_clicks", "dead_clicks", "avg_scroll_pct", "exits"]),
                          ("exit_survey", survey, ["day", "market", "device", "product_id", "reason", "responses"])):
        db.execute(f"DELETE FROM {t} WHERE day >= ?", (since,))
        db.executemany(f"INSERT OR REPLACE INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [tuple(x[c] for c in cols) for x in rows])
    store.log_sync(db, "behaviour", since, last.isoformat(), len(events) + len(ux) + len(survey),
                   "SYNTHETIC product-analytics funnel, session behaviour and exit survey, derived from sales_daily")
    db.commit()
    db.close()
    return len(events) + len(ux) + len(survey)


if __name__ == "__main__":
    p = Path(sys.argv[1])
    print(f"{add(p)} behaviour rows added to {p}")
    for k, v in PLANTED.items():
        print(f"  planted {k}: {v}")
