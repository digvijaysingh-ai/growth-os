"""SYNTHETIC multi-market B2C scenario: a consumer brand selling time-limited products online in 12 cities, with paid
acquisition on Meta, Google and TikTok, plus email, organic and direct. 60 weeks of daily data, so year-over-year
comparisons work. Revenue is first-party (last click); platforms also report their own, inflated, revenue.

Situations a multi-city growth team actually meets are planted on purpose (PLANTED), including two traps where the
right answer is to stay quiet. The analyst is graded on finding them without false alarms.

    python -m growth_os.demo_b2c
    growth-os analyse --hub state/b2c-hub.sqlite --period-days 28
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta
from pathlib import Path

from .config import ROOT
from .hub import store

PLANTED = {
    "paris_creative_fatigue": "Paris, Meta ad 'Video A': for about five weeks its frequency has climbed (about 2 to over 5) and its click rate has fallen by more than half while spend stayed the same, so its ROAS collapsed and Paris paid ROAS fell. Other Paris ads are fine.",
    "milan_brand_search": "Milan's Google brand-search campaign shows a very high ROAS, but when it was paused for two weeks (about 10 to 8 weeks ago) Milan's total revenue barely moved because organic picked up most of those buyers. Brand-search ROAS overstates what it adds.",
    "ios_checkout_berlin_amsterdam": "Berlin and Amsterdam only: from about 18 days ago, iOS checkouts stopped turning into orders (checkout-to-order rate fell from about 62% to about 22%); Android and desktop are fine, and other markets' iOS is fine.",
    "mexico_launch_behind": "Mexico City, opened about 8 weeks ago, is ramping up much more slowly than São Paulo and Miami did at the same number of weeks after their launches.",
    "london_email_masks_paid": "London's total revenue looks roughly flat, but paid revenue fell (costs per click rose on Meta and TikTok) while a large email push lifted email revenue, hiding the paid decline.",
    "madrid_product_pacing": "Madrid product 'Autumn special' ends in about 12 days but has sold well under half its capacity while most of its selling window has passed, unlike other products that track their windows.",
    "barcelona_budget_pacing": "Barcelona has spent nearly all of its October budget with about a fifth of the month left, because spend ran well above plan all month.",
    "new_york_seasonal_trap": "New York revenue fell sharply against the previous four weeks, but it falls the same way every year at this time: year over year it is flat. Flagging it as a problem is a false alarm.",
    "porto_tiny_trap": "Porto is a very small market whose numbers swing on tiny counts; treating a Porto swing as a real change is a false alarm.",
}
NOISE_ONLY = ["São Paulo", "Miami"]

MARKETS = {  # name: (size, days since launch before the last day, or None for long-established)
    "Madrid": (1.2, None), "Barcelona": (1.1, None), "Porto": (0.1, None), "Paris": (1.3, None), "London": (1.5, None), "Milan": (0.9, None),
    "Berlin": (1.0, None), "Amsterdam": (0.8, None), "New York": (1.6, None), "São Paulo": (1.0, 300), "Miami": (0.8, 230), "Mexico City": (0.9, 56),
}
CODES = {"Madrid": "MAD", "Barcelona": "BCN", "Porto": "OPO", "Paris": "PAR", "London": "LON", "Milan": "MIL", "Berlin": "BER", "Amsterdam": "AMS",
         "New York": "NYC", "São Paulo": "SAO", "Miami": "MIA", "Mexico City": "MEX"}
DEVICES = [("ios", 0.5), ("android", 0.3), ("desktop", 0.2)]
META_ADS = [("Video A", 0.014), ("Carousel B", 0.011), ("UGC C", 0.013)]
TIKTOK_ADS = [("Creator 1", 0.009), ("Creator 2", 0.008)]
AOV = 62.0


def _season(m: str, d: date) -> float:
    doy = d.timetuple().tm_yday
    s = 1 + 0.12 * math.sin(2 * math.pi * (doy - 80) / 365)
    if date(d.year, 12, 1) <= d <= date(d.year, 12, 23):
        s *= 1.35
    if m == "New York" and d.month == 10:  # every October; the seasonal trap
        s *= 0.70
    return s


def _ramp(age_days: int | None, slow: bool) -> float:
    if age_days is None:
        return 1.0
    if age_days < 0:
        return 0.0
    return 1 - math.exp(-age_days / (7 * (22 if slow else 7)))


def build(path: Path = ROOT / "state" / "b2c-hub.sqlite", until: date = date(2026, 10, 25), weeks: int = 60, seed: int = 7) -> Path:
    rnd = random.Random(seed)
    path.unlink(missing_ok=True)
    db = store.connect(path)
    days = [until - timedelta(days=i) for i in range(weeks * 7 - 1, -1, -1)]
    fatigue_start, ios_break = until - timedelta(days=35), until - timedelta(days=18)
    milan_pause = (until - timedelta(days=70), until - timedelta(days=57))
    london_from = until - timedelta(days=27)
    binom = rnd.binomialvariate
    ad_rows, sales, product_rows, products, budgets = [], [], [], [], []
    launched = {m: (until - timedelta(days=age)).isoformat() if age else (days[0] - timedelta(days=900)).isoformat() for m, (_, age) in MARKETS.items()}

    def sell(ds, m, channel, ad_id, sessions_total, p_checkout, p_order, p_new):
        """Splits sessions over devices and draws checkouts, orders, revenue; returns first-party revenue and orders."""
        rev_total, orders_total = 0.0, 0
        for dev, share in DEVICES:
            n = round(sessions_total * share)
            if n <= 0:
                continue
            po = 0.22 if (m in ("Berlin", "Amsterdam") and dev == "ios" and date.fromisoformat(ds) >= ios_break) else p_order
            co = binom(n, min(0.95, p_checkout))
            o = binom(co, po)
            rev = round(sum(rnd.gauss(AOV, 14) for _ in range(o)), 2) if o < 40 else round(o * AOV * rnd.uniform(0.93, 1.07), 2)
            sales.append(dict(day=ds, market=m, channel=channel, ad_id=ad_id, device=dev, sessions=n, checkouts=co, orders=o, revenue=max(0.0, rev),
                              new_customers=binom(o, p_new)))
            rev_total += max(0.0, rev)
            orders_total += o
        return rev_total, orders_total

    for d in days:
        ds = d.isoformat()
        for m, (size, age) in MARKETS.items():
            code = CODES[m]
            a = None if age is None else (d - (until - timedelta(days=age))).days
            ramp = _ramp(a, slow=(m == "Mexico City"))
            if ramp == 0:
                continue
            season = _season(m, d) * rnd.gauss(1, 0.05)
            demand = season * ramp
            spend_k = size * (1.18 if (m == "Barcelona" and d.month == 10 and d.year == until.year) else 1.0)
            london = m == "London" and d >= london_from

            # Meta: three creatives; Paris 'Video A' fatigues
            for j, (name, ctr) in enumerate(META_ADS):
                ad_id = f"{code}-META-{j + 1}"
                spend = round(110 * spend_k * min(1.0, ramp * 1.4) * rnd.uniform(0.85, 1.15), 2)
                cpm = 7.0 * (1.4 if london else 1.0) * rnd.uniform(0.9, 1.1)
                imps = int(spend / cpm * 1000)
                freq, c = 1.9 + rnd.uniform(-0.2, 0.2), ctr
                if m == "Paris" and j == 0 and d >= fatigue_start:
                    t = (d - fatigue_start).days / 35
                    freq, c = 2.0 + 3.6 * t, ctr * (1 - 0.62 * t)
                clicks = binom(imps, c)
                rev, orders = sell(ds, m, "paid:meta", ad_id, int(clicks * 0.85), 0.10 * demand, 0.62, 0.55)
                ad_rows.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Meta prospecting", spend=spend, impressions=imps, reach=int(imps / freq),
                                    link_clicks=clicks, form_leads=0, market=m, platform="meta", creative=name, frequency=round(freq, 2),
                                    platform_purchases=round(orders * 1.35), platform_revenue=round(rev * rnd.uniform(1.25, 1.45), 2)))
            # TikTok: two creators
            for j, (name, ctr) in enumerate(TIKTOK_ADS):
                ad_id = f"{code}-TT-{j + 1}"
                spend = round(55 * spend_k * min(1.0, ramp * 1.4) * rnd.uniform(0.85, 1.15), 2)
                imps = int(spend / (4.2 * (1.4 if london else 1.0) * rnd.uniform(0.9, 1.1)) * 1000)
                clicks = binom(imps, ctr)
                rev, orders = sell(ds, m, "paid:tiktok", ad_id, int(clicks * 0.8), 0.055 * demand, 0.6, 0.65)
                ad_rows.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · TikTok", spend=spend, impressions=imps, reach=int(imps / 1.7), link_clicks=clicks,
                                    form_leads=0, market=m, platform="tiktok", creative=name, frequency=round(1.7 + rnd.uniform(-0.2, 0.2), 2),
                                    platform_purchases=round(orders * 1.7), platform_revenue=round(rev * rnd.uniform(1.55, 1.85), 2)))
            # Google brand search: buyers who were looking for the brand anyway; Milan's pause shows it
            paused = m == "Milan" and milan_pause[0] <= d <= milan_pause[1]
            brand_sessions = int(150 * size * demand * rnd.uniform(0.9, 1.1))
            ad_id = f"{code}-GGL-BRAND"
            if paused:
                ad_rows.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Google brand", spend=0.0, impressions=0, reach=0, link_clicks=0, form_leads=0,
                                    market=m, platform="google", creative="Brand search", frequency=None, platform_purchases=0, platform_revenue=0.0))
            else:
                spend = round(60 * spend_k * min(1.0, ramp * 1.4) * rnd.uniform(0.85, 1.15), 2)
                rev, orders = sell(ds, m, "paid:google_brand", ad_id, brand_sessions, 0.2 * min(1.2, season), 0.7, 0.25)
                ad_rows.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Google brand", spend=spend, impressions=int(brand_sessions * 2.2), reach=int(brand_sessions * 2),
                                    link_clicks=brand_sessions, form_leads=0, market=m, platform="google", creative="Brand search", frequency=None,
                                    platform_purchases=round(orders * 1.08), platform_revenue=round(rev * rnd.uniform(1.03, 1.12), 2)))
            # Google generic search
            ad_id = f"{code}-GGL-GENERIC"
            spend = round(85 * spend_k * min(1.0, ramp * 1.4) * rnd.uniform(0.85, 1.15), 2)
            clicks = int(spend / rnd.uniform(0.85, 1.0))
            rev, orders = sell(ds, m, "paid:google_generic", ad_id, int(clicks * 0.9), 0.07 * demand, 0.62, 0.6)
            ad_rows.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Google generic", spend=spend, impressions=clicks * 18, reach=clicks * 15, link_clicks=clicks,
                                form_leads=0, market=m, platform="google", creative="Generic search", frequency=None,
                                platform_purchases=round(orders * 1.1), platform_revenue=round(rev * rnd.uniform(1.05, 1.15), 2)))
            # owned and earned channels; most of Milan's paused brand searchers arrive organically instead
            email_k = 2.3 if london else 1.0
            sell(ds, m, "email", "", int(220 * size * season * ramp * email_k * rnd.uniform(0.85, 1.15)), 0.11, 0.66, 0.15)
            organic_extra = int(brand_sessions * 0.85) if paused else 0
            sell(ds, m, "organic", "", int(560 * size * demand * rnd.uniform(0.9, 1.1)) + organic_extra, 0.09 if not organic_extra else 0.12, 0.64, 0.4)
            sell(ds, m, "direct", "", int(300 * size * demand * rnd.uniform(0.9, 1.1)), 0.1, 0.65, 0.3)

    # time-limited products: each market launches one every two weeks, each sells for six weeks
    by_market_day = {}
    for r in sales:
        by_market_day[(r["market"], r["day"])] = by_market_day.get((r["market"], r["day"]), 0) + r["orders"]
    for m in MARKETS:
        code = CODES[m]
        k = 0
        start = days[0]
        while start <= until:
            end = start + timedelta(days=42)
            pid = f"{code}-P{k:03d}"
            planted = m == "Madrid" and start <= until - timedelta(days=30) < end and end >= until + timedelta(days=5)
            if m == "Madrid" and until - timedelta(days=42) <= start <= until - timedelta(days=40):
                end, planted = until + timedelta(days=12), True
            name = "Autumn special" if planted else f"Edition {k + 1}"
            share = 0.4 if planted else 1.0
            expected, units = 0.0, []
            for i in range((min(end, until) - start).days + 1):
                dd = (start + timedelta(days=i)).isoformat()
                active = 3  # about three products are on sale at any time
                exp = by_market_day.get((m, dd), 0) / active
                expected += exp
                u = binom(int(exp * 1.6) + 1, min(1.0, share / 1.6))
                units.append((dd, u))
            full_window = (end - start).days + 1
            cap = max(10, int(expected / max(1, len(units)) * full_window * (1.0 if not planted else 1.0) * rnd.uniform(1.02, 1.12)))
            products.append(dict(product_id=pid, market=m, name=f"{m} · {name}", launch_day=start.isoformat(), end_day=end.isoformat(), capacity=cap,
                                 price=round(AOV * rnd.uniform(0.85, 1.2), 2)))
            product_rows += [dict(day=dd, product_id=pid, units=u, revenue=round(u * products[-1]["price"], 2)) for dd, u in units]
            start += timedelta(days=14)
            k += 1
    # October budgets: plan = typical October spend; Barcelona runs 18% over it
    for m, (size, age) in MARKETS.items():
        month = until.strftime("%Y-%m")
        planned = sum(r["spend"] for r in ad_rows if r["market"] == m and r["day"].startswith(month)) / until.day * 31
        if m == "Barcelona":
            planned /= 1.18
        budgets.append((m, month, round(planned * rnd.uniform(1.0, 1.06), 2)))

    s, u = days[0].isoformat(), days[-1].isoformat()
    store.replace_window(db, "ad_daily", ad_rows, s, u)
    store.replace_window(db, "sales_daily", sales, s, u)
    store.replace_window(db, "product_daily", product_rows, s, u)
    db.executemany("INSERT INTO products (product_id, market, name, launch_day, end_day, capacity, price) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   [(p["product_id"], p["market"], p["name"], p["launch_day"], p["end_day"], p["capacity"], p["price"]) for p in products])
    db.executemany("INSERT INTO budgets (market, month, budget) VALUES (?, ?, ?)", budgets)
    db.executemany("INSERT INTO markets (market, launched_on) VALUES (?, ?)", list(launched.items()))
    db.executemany("INSERT OR REPLACE INTO ads (ad_id, ad_name, campaign_id, status, updated_at) VALUES (?, ?, ?, 'ACTIVE', ?)",
                   sorted({(r["ad_id"], f"{r['market']} · {r['platform'].capitalize()} · {r['creative']}", r["campaign"], u) for r in ad_rows}))
    store.log_sync(db, "demo-b2c", s, u, len(ad_rows) + len(sales), "SYNTHETIC multi-market B2C scenario, planted patterns")
    db.commit()
    db.close()
    return path


if __name__ == "__main__":
    p = build()
    print(f"SYNTHETIC B2C hub written to {p.relative_to(ROOT)}")
    for k, v in PLANTED.items():
        print(f"  planted {k}: {v}")
