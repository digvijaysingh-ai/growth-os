"""SYNTHETIC enterprise world: a consumer brand selling time-limited editions in 4 product lines across 12 cities, with
a €50k–100k monthly marketing budget per line per market spread over 8 paid channels, plus owned and organic channels.

How a day is made (per market and product line):
  demand     base potential (population, affluence, category propensity, competition) × season × REAL weather × REAL
             public holidays × day of week × launch ramp for new markets
  paid       each channel adds incremental orders on its own diminishing-returns curve (Hill function of daily spend)
  awareness  upper-funnel spend builds awareness (adstock), which lifts organic search, direct and brand search
  last click brand search and retargeting mostly collect buyers who would have come anyway; platforms over-claim
  funnel     sessions, checkouts and orders by device; first-party revenue by last click

The true curves, multipliers and planted situations are written to a separate truth file, never into the hub, so the
agents have to find them. Draws are seeded per day and cell with a fixed number of draws, so the same world run under
two budget policies differs only where the policy differs: that is how decisions are measured against doing nothing.

    python -m growth_os.enterprise.world state/enterprise-7.sqlite 7
"""
from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ..hub import store
from . import external
from .profile import CODES, LINES, MARKETS, OWNED, PAID, PLAN_SPLIT, PLATFORM, PLATFORM_CLAIM, PROPENSITY, UPPER_FUNNEL, monthly_budget

UNTIL = date(2026, 11, 1)
START = date(2025, 8, 25)
DEVICES = [("ios", 0.47), ("android", 0.31), ("desktop", 0.22)]
ESTABLISHED = [m for m, p in MARKETS.items() if not p["launched"]]
LAUNCHED = [m for m, p in MARKETS.items() if p["launched"]]
RAINY_EU = ["London", "Amsterdam", "Berlin", "Paris", "Milan"]


def scenario(seed: int) -> dict:
    """Where each planted situation lands, drawn from the seed: held-out businesses get a different answer key."""
    r = random.Random(f"scenario|{seed}")
    est = list(ESTABLISHED)
    r.shuffle(est)
    pick = iter(est)
    lines = list(LINES)
    sc = {
        "payment_markets": [next(pick), next(pick)], "payment_device": r.choice(["ios", "android"]),
        "delivery_market": next(pick), "seo_market": next(pick), "overspend_market": next(pick), "seasonal_market": next(pick),
        "brand_pause_market": next(pick), "noise_markets": [next(pick), next(pick)],
        "demand_gap": (r.choice(est), r.choice(lines)), "sellout": (r.choice(est), r.choice(lines)), "fatigue": (r.choice(est), r.choice(lines)),
        "saturated_meta": r.sample(est, 4), "weather_strong": r.sample(RAINY_EU, 3), "weather_line": r.choice(["Home", "Gifts"]),
        "slow_launch": r.choice(LAUNCHED),
    }
    sc["noise_markets"] = [m for m in sc["noise_markets"] if m not in sc["saturated_meta"] and m != sc["demand_gap"][0]
                           and m != sc["sellout"][0] and m != sc["fatigue"][0]] or sc["noise_markets"][:1]
    return sc


def planted(sc: dict) -> tuple[dict, dict]:
    pm, dev = sc["payment_markets"], sc["payment_device"]
    others = [m for m in LAUNCHED if m != sc["slow_launch"]]
    p = {
        "meta_saturation": f"{', '.join(sc['saturated_meta'])}: Meta prospecting is far past the point of diminishing returns (marginal ROAS well below 1) "
                           "while TikTok and YouTube are under-funded with high marginal ROAS. Moving budget between them lifts revenue at the same spend.",
        "retargeting_overclaim": "Meta retargeting reports a strong platform ROAS everywhere, but almost all of its last-click orders would have come anyway "
                                 "(organic, direct, email); its incremental return is close to zero.",
        "brand_search_cannibalisation": f"Google brand search: about 88% of its buyers come through organic search when it is off. {sc['brand_pause_market']}'s "
                                        "brand campaigns were paused for two weeks (about 10 to 8 weeks before the end) and its revenue barely moved.",
        "demand_gap": f"{sc['demand_gap'][0]} {sc['demand_gap'][1]} has far more potential demand than it captures: high category interest for its profile, "
                      "low awareness and budget, unsaturated paid channels. It is the best place to add budget.",
        "weather": f"{sc['weather_line']} sells more on rainy days, strongly in {', '.join(sc['weather_strong'])}, but budgets do not move with the weather.",
        "payment_failure": f"{' and '.join(pm)}, {dev} only, all lines: from 18 days before the end, payments fail (checkout-to-order about 62% -> 22%).",
        "sellout": f"{sc['sellout'][0]} {sc['sellout'][1]}: the current edition sold out 10 days before the end, with weeks left to run.",
        "launch_behind": f"{sc['slow_launch']} (a recent launch) ramps up far slower than {' and '.join(others)} did at the same age; visitors say they do "
                         "not know or trust the brand yet.",
        "delivery_delays": f"{sc['delivery_market']}: from 30 days before the end, deliveries are late; repeat buyers (email, SMS) convert about a third "
                           "less and survey comments about delivery jump.",
        "seo_drop": f"{sc['seo_market']}: organic search sessions fell about 35% from 40 days before the end (site change); the team raised Google generic "
                    "spend about 40% from 35 days before the end to compensate, so revenue looks flat while MER falls.",
        "creative_fatigue": f"{sc['fatigue'][0]} {sc['fatigue'][1]}, Meta prospecting: over the last 5 weeks frequency rose from about 2 to over 5 and "
                            "click rate halved; its incremental return halved.",
        "overspend": f"{sc['overspend_market']} spent about 20% above plan in October.",
    }
    t = {"seasonal_trap": f"{sc['seasonal_market']} always dips in October (both years): against the previous 4 weeks it looks like a fall, year over "
                          "year it is flat.",
         "noise_markets": f"{' and '.join(sc['noise_markets'])} carry only noise."}
    return p, t


PLANTED, TRAPS = planted(scenario(7))  # the development seed's answer key (eval uses planted(scenario(seed)))


@dataclass
class Policy:
    """How spend is set. The plan is the as-is policy; decisions change multipliers or pause channels."""
    mult: dict = field(default_factory=dict)        # (market, line, channel) -> spend multiplier
    paused: set = field(default_factory=set)        # (market, line, channel)
    weather_boost: dict = field(default_factory=dict)  # (market, line) -> extra multiplier on upper-funnel spend on rainy days
    fixes: dict = field(default_factory=dict)       # name -> day it takes effect: payment_fix, delivery_fix, seo_fix, restock, new_creative
    start: date | None = None                       # budget changes apply from this day (history is never rewritten)
    note: str = "as-is plan"


def _z(r: random.Random, n: int) -> list[float]:
    return [r.gauss(0, 1) for _ in range(n)]


def _count(mu: float, z: float) -> int:
    """A count with mean mu and Poisson-like noise, from one fixed normal draw (keeps draws aligned across policies)."""
    return max(0, int(round(mu + math.sqrt(max(mu, 0.0)) * z)))


def truth(seed: int) -> dict:
    """The hidden ground truth: response curves per market × line × channel, and base potential."""
    r = random.Random(f"truth|{seed}")
    sc = scenario(seed)
    t = {"base": {}, "curves": {}, "scenario": sc}
    for m, p in MARKETS.items():
        for l, lp in LINES.items():
            base = 0.42 * (p["pop_m"] ** 0.62) * p["affluence"] * PROPENSITY[l] / (p["competition"] ** 0.3) * 150 * r.uniform(0.92, 1.08)
            if (m, l) == tuple(sc["demand_gap"]):
                base *= 1.9
            t["base"][f"{m}|{l}"] = round(base, 2)
            daily = monthly_budget(m) / 30.4
            for c in PAID:
                s_plan = daily * PLAN_SPLIT[c]
                # half-saturation spend relative to plan spend; < 1 means the plan is past the knee
                knee = {"meta_prospecting": 1.1, "meta_retargeting": 0.6, "tiktok": 1.6, "youtube": 1.7, "google_brand": 0.8,
                        "google_generic": 1.3, "affiliates": 1.0, "creators": 1.4}[c] * r.uniform(0.85, 1.15)
                # incremental orders at saturation, per euro of plan budget (incremental ROAS shape)
                beta = {"meta_prospecting": 0.030, "meta_retargeting": 0.0025, "tiktok": 0.050, "youtube": 0.045, "google_brand": 0.004,
                        "google_generic": 0.026, "affiliates": 0.020, "creators": 0.034}[c] * r.uniform(0.85, 1.15)
                if m in sc["saturated_meta"] and c == "meta_prospecting":
                    knee *= 0.35
                if m in sc["saturated_meta"] and c in ("tiktok", "youtube"):
                    knee *= 2.2
                    beta *= 1.5
                if (m, l) == tuple(sc["demand_gap"]) and c in UPPER_FUNNEL | {"google_generic"}:
                    knee *= 2.5
                    beta *= 1.7
                t["curves"][f"{m}|{l}|{c}"] = {"k": round(s_plan * knee, 2), "h": round(r.uniform(1.0, 1.25), 3),
                                               "vmax": round(beta * s_plan * (1 + knee), 3)}
    return t


def _hill(s: float, k: float, h: float, vmax: float) -> float:
    if s <= 0:
        return 0.0
    return vmax * s ** h / (k ** h + s ** h)


def _season(l: str, m: str, d: date, sc: dict) -> float:
    s = 1.0
    for month, f in LINES[l]["peaks"]:
        if d.month == month:
            s *= f
    if MARKETS[m]["lat"] < 0:  # southern hemisphere: fashion peaks flip
        s = s if l != "Fashion drops" else 1 + (1.0 / s - 1) * 0.5
    if m == sc["seasonal_market"] and d.month == 10:
        s *= 0.75
    return s * (1.0 + 0.08 * (d.weekday() >= 5) - 0.04 * (d.weekday() == 0))


def _weather(l: str, m: str, temp: float, rain: float, sc: dict) -> float:
    lp = LINES[l]
    rain_k = (lp["rain"] if l != sc["weather_line"] else max(lp["rain"], 0.16)) * (1.9 if (l == sc["weather_line"] and m in sc["weather_strong"]) else 1.0)
    wet = 1.0 if rain >= 2.0 else rain / 2.0
    hot = max(0.0, (temp - 24) / 8)
    return max(0.5, 1 + rain_k * wet + lp["heat"] * hot)


def _ramp(m: str, d: date, until: date, sc: dict) -> float:
    age_days = MARKETS[m]["launched"]
    if age_days is None:
        return 1.0
    age = (d - (until - timedelta(days=age_days))).days
    if age < 0:
        return 0.0
    tau = 7 * (24 if m == sc["slow_launch"] else 8)
    return 1 - math.exp(-age / tau)


def simulate(hub: Path, since: date, until: date, policy: Policy, seed: int, t: dict, weather: dict, holidays: dict,
             state: dict | None = None, origin: date = UNTIL) -> dict:
    """Writes days since..until into the hub under `policy`. `state` carries awareness and stock between calls."""
    state = state if state is not None else {"aw": {}, "sold": {}}
    db = store.connect(hub)
    products = {(r[1], r[2]): dict(product_id=r[0], capacity=r[3], end_day=r[4]) for r in db.execute(
        "SELECT product_id, market, line, capacity, end_day FROM products WHERE launch_day <= ? AND end_day >= ?", (until.isoformat(), since.isoformat()))} \
        if db.execute("SELECT 1 FROM sqlite_master WHERE name = 'products'").fetchone() else {}
    ads, sales, prod = [], [], []
    d = since
    hol = {cc: set(v) for cc, v in holidays.items()}
    sc = t["scenario"]
    while d <= until:
        ds = d.isoformat()
        for m, mp in MARKETS.items():
            ramp = _ramp(m, d, origin, sc)
            if ramp == 0:
                continue
            temp, rain = weather.get(m, {}).get(ds, (15.0, 0.0))
            is_hol = ds in hol.get(mp["country"], set())
            for l, lp in LINES.items():
                r = random.Random(f"{seed}|{ds}|{m}|{l}")
                z = _z(r, 160)
                zi = iter(z)
                base = t["base"][f"{m}|{l}"]
                rel = _season(l, m, d, sc) * _weather(l, m, temp, rain, sc) * (1.12 if is_hol and l in ("Home", "Gifts") else 1.0) * ramp * math.exp(0.06 * next(zi))
                daily = monthly_budget(m) / 30.4
                week = (d - START).days // 7
                rw = random.Random(f"flight|{seed}|{week}|{m}|{l}")  # weekly budget changes: what makes curves learnable
                rainy = rain >= 2.0
                spend = {}
                for c in PAID:
                    s = daily * PLAN_SPLIT[c] * rw.uniform(0.6, 1.4) * math.exp(0.05 * next(zi))  # weekly budget moves and tests
                    s *= ramp if mp["launched"] else 1.0
                    if m == sc["overspend_market"] and d.month == 10:
                        s *= 1.2
                    if m == sc["seo_market"] and c == "google_generic" and d >= origin - timedelta(days=35) and not (
                            policy.fixes.get("seo_fix") and d >= date.fromisoformat(policy.fixes["seo_fix"])):
                        s *= 1.4
                    if m == sc["brand_pause_market"] and c == "google_brand" and origin - timedelta(days=70) <= d <= origin - timedelta(days=57):
                        s = 0.0
                    on = policy.start is None or d >= policy.start
                    if on:
                        s *= policy.mult.get((m, l, c), 1.0)
                        if rainy and c in UPPER_FUNNEL:
                            s *= policy.weather_boost.get((m, l), 1.0)
                        if (m, l, c) in policy.paused:
                            s = 0.0
                    spend[c] = round(s, 2)
                # awareness: adstock of upper-funnel spend relative to the line's plan
                ref = daily * sum(PLAN_SPLIT[c] for c in UPPER_FUNNEL)
                key = f"{m}|{l}"
                up = sum(spend[c] for c in UPPER_FUNNEL) / ref if ref else 0
                aw = state["aw"].get(key, up if up else 1.0) * 0.93 + 0.07 * up
                state["aw"][key] = aw
                aw_f = 0.55 + 0.45 * aw / (aw + 0.6) / (1 / 1.6)  # ~1.0 at plan
                if (m, l) == tuple(sc["demand_gap"]):
                    aw_f *= 0.62  # little awareness yet
                if m == sc["slow_launch"]:
                    aw_f *= 0.7
                pot = base * rel
                # incremental orders by paid channel
                inc = {}
                for c in PAID:
                    cv = t["curves"][f"{m}|{l}|{c}"]
                    vmax = cv["vmax"]
                    if (m, l) == tuple(sc["fatigue"]) and c == "meta_prospecting" and d >= origin - timedelta(days=35) and not (
                            policy.fixes.get("new_creative") and d >= date.fromisoformat(policy.fixes["new_creative"])):
                        vmax *= 1 - 0.5 * min(1.0, (d - (origin - timedelta(days=35))).days / 35)
                    inc[c] = _hill(spend[c], cv["k"], cv["h"], vmax) * rel
                # organic and owned demand
                seo = 0.65 if (m == sc["seo_market"] and d >= origin - timedelta(days=40) and not (
                    policy.fixes.get("seo_fix") and d >= date.fromisoformat(policy.fixes["seo_fix"]))) else 1.0
                late = m == sc["delivery_market"] and d >= origin - timedelta(days=30) and not (policy.fixes.get("delivery_fix") and d >= date.fromisoformat(policy.fixes["delivery_fix"]))
                brand_searchers = pot * aw_f * 0.20
                organic = pot * aw_f * 0.30 * seo
                direct = pot * aw_f * 0.20
                social = pot * aw_f * 0.05
                email = pot * 0.11 * (0.65 if late else 1.0)
                sms = pot * 0.035 * (0.65 if late else 1.0)
                if spend["google_brand"] > 0:
                    brand_lc = brand_searchers + inc["google_brand"]
                else:
                    brand_lc, organic = 0.0, organic + brand_searchers * 0.88
                # retargeting collects buyers who were already coming (from organic, direct, email)
                steal = min(0.18, 0.045 * (spend["meta_retargeting"] / max(1.0, daily * PLAN_SPLIT["meta_retargeting"])) ** 0.6)
                pool = organic + direct + email
                retarget_lc = pool * steal + inc["meta_retargeting"]
                organic, direct, email = organic * (1 - steal), direct * (1 - steal), email * (1 - steal)
                lc = {**{c: inc[c] for c in PAID}, "google_brand": brand_lc, "meta_retargeting": retarget_lc,
                      "organic_search": organic, "direct": direct, "organic_social": social, "email": email, "sms": sms}
                # funnel by device; orders limited by stock if an edition sold out
                aov = lp["aov"]
                prow = products.get((m, l))
                sold_out = False
                if prow:
                    sold = state["sold"].get(prow["product_id"], 0)
                    restock = policy.fixes.get("restock")
                    cap = prow["capacity"] + (prow["capacity"] * 3 if restock and d >= date.fromisoformat(restock) and (m, l) == tuple(sc["sellout"]) else 0)
                    sold_out = sold >= cap
                day_orders = 0
                for ch, mu_orders in lc.items():
                    if sold_out:
                        mu_orders *= 0.55  # the current edition is gone; some buy another
                    ad_id = f"{CODES[m]}-{lp['code']}-{ch.upper().replace('_', '-')}" if ch in PAID else ""
                    for dev, share in DEVICES:
                        p_order = 0.62
                        if m in sc["payment_markets"] and dev == sc["payment_device"] and d >= origin - timedelta(days=18) and not (
                                policy.fixes.get("payment_fix") and d >= date.fromisoformat(policy.fixes["payment_fix"])):
                            p_order = 0.22
                        intent = mu_orders * share / 0.62  # people who reach checkout
                        co = _count(intent, next(zi))
                        o = _count(co * p_order, next(zi) * 0.5)
                        o = min(o, co)
                        sessions = int(co / {"google_brand": 0.16, "meta_retargeting": 0.09, "email": 0.10, "sms": 0.12, "direct": 0.07}.get(ch, 0.035))
                        rev = round(o * aov * (1 + 0.08 * next(zi) / max(1, math.sqrt(o or 1))), 2)
                        sales.append((ds, m, l, ch if ch not in PAID else "paid:" + ch, ad_id, dev, sessions, co, o, max(0.0, rev), int(o * (0.45 if ch in PAID else 0.25))))
                        day_orders += o
                if prow:
                    state["sold"][prow["product_id"]] = state["sold"].get(prow["product_id"], 0) + int(day_orders * 0.35)
                    prod.append((ds, prow["product_id"], int(day_orders * 0.35), round(day_orders * 0.35 * aov, 2)))
                # delivery and what each platform claims
                for c in PAID:
                    s = spend[c]
                    cpm = {"meta_prospecting": 7.5, "meta_retargeting": 11, "tiktok": 4.8, "youtube": 6.5, "google_brand": 30, "google_generic": 45,
                           "affiliates": 12, "creators": 9}[c] * (1.25 if m in ("London", "New York", "Paris") else 1.0)
                    imps = int(s / cpm * 1000)
                    ctr = {"meta_prospecting": 0.012, "meta_retargeting": 0.016, "tiktok": 0.009, "youtube": 0.005, "google_brand": 0.18,
                           "google_generic": 0.05, "affiliates": 0.02, "creators": 0.011}[c]
                    freq = 1.9
                    if (m, l) == tuple(sc["fatigue"]) and c == "meta_prospecting" and d >= origin - timedelta(days=35) and not (
                            policy.fixes.get("new_creative") and d >= date.fromisoformat(policy.fixes["new_creative"])):
                        f = min(1.0, (d - (origin - timedelta(days=35))).days / 35)
                        freq, ctr = 2.0 + 3.4 * f, ctr * (1 - 0.5 * f)
                    clicks = int(imps * ctr)
                    lc_orders = lc[c]
                    ads.append((ds, f"{CODES[m]}-{lp['code']}-{c.upper().replace('_', '-')}", f"{m} · {l} · {c}", s, imps, int(imps / freq), clicks, 0, m,
                                PLATFORM[c], c, l, round(freq, 2) if PLATFORM[c] in ("meta", "tiktok") else None,
                                round(lc_orders * PLATFORM_CLAIM[c]), round(lc_orders * PLATFORM_CLAIM[c] * aov, 2)))
        d += timedelta(days=1)
    db.execute("DELETE FROM sales_daily WHERE day BETWEEN ? AND ?", (since.isoformat(), until.isoformat()))
    db.execute("DELETE FROM ad_daily WHERE day BETWEEN ? AND ?", (since.isoformat(), until.isoformat()))
    db.executemany("""INSERT INTO sales_daily (day, market, line, channel, ad_id, device, sessions, checkouts, orders, revenue, new_customers)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", sales)
    db.executemany("""INSERT INTO ad_daily (day, ad_id, campaign, spend, impressions, reach, link_clicks, form_leads, market, platform, creative, line,
                      frequency, platform_purchases, platform_revenue) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", ads)
    db.executemany("INSERT OR REPLACE INTO product_daily (day, product_id, units, revenue) VALUES (?, ?, ?, ?)", prod)
    db.commit()
    db.close()
    return state


def weather_ext(until: date, horizon: int) -> dict:
    """History from the archive; the next 16 days from the real forecast made on the day after `until` when cached;
    beyond that, the same calendar day last year (a stated simplification)."""
    wx = {m: dict(v) for m, v in external.weather(START, UNTIL).items()}
    fc = {}
    try:
        fc = external.forecast(until + timedelta(days=1))
    except Exception:
        pass
    for m in wx:
        for i in range(1, horizon + 1):
            d = (until + timedelta(days=i)).isoformat()
            wx[m][d] = tuple(fc.get(m, {}).get(d) or wx[m].get((until + timedelta(days=i - 364)).isoformat(), (15.0, 0.0)))
    return wx


def build(hub: Path, seed: int = 7, until: date = UNTIL, weeks: int = 62, horizon: int = 0, policy: Policy | None = None) -> Path:
    """History up to `until` under the as-is plan; with `horizon`, `horizon` more days under `policy` (from until+1)."""
    since = until - timedelta(days=weeks * 7 - 1)
    hub.unlink(missing_ok=True)
    t = truth(seed)
    wx = weather_ext(until, horizon) if horizon else external.weather(START, UNTIL)
    hol = external.holidays([2025, 2026, 2027])
    db = store.connect(hub)
    # macro and plan tables the agents can read
    db.executemany("INSERT INTO market_profile (market, country, lat, lon, pop_m, affluence, competition, launched_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   [(m, p["country"], p["lat"], p["lon"], p["pop_m"], p["affluence"], p["competition"],
                     (until - timedelta(days=p["launched"])).isoformat() if p["launched"] else None) for m, p in MARKETS.items()])
    db.executemany("INSERT INTO markets (market, launched_on) VALUES (?, ?)",
                   [(m, (until - timedelta(days=p["launched"])).isoformat() if p["launched"] else since.isoformat()) for m, p in MARKETS.items()])
    db.executemany("INSERT INTO weather_daily (day, market, temp_c, precip_mm, source) VALUES (?, ?, ?, ?, ?)",
                   [(day, m, v[0], v[1], "open-meteo archive") for m, days in wx.items() for day, v in days.items() if since.isoformat() <= day <= until.isoformat()])
    db.executemany("INSERT OR IGNORE INTO holidays (day, country, source) VALUES (?, ?, 'nager.date')", [(d, cc) for cc, ds in hol.items() for d in ds])
    months = sorted({(since + timedelta(days=i)).strftime("%Y-%m") for i in range((until - since).days + 1)})
    db.executemany("INSERT INTO budget_plan (month, market, line, channel, budget) VALUES (?, ?, ?, ?, ?)",
                   [(mo, m, l, c, round(monthly_budget(m) * PLAN_SPLIT[c], 2)) for mo in months for m in MARKETS for l in LINES for c in PAID])
    db.executemany("INSERT INTO budgets (market, month, budget) VALUES (?, ?, ?)", [(m, mo, monthly_budget(m) * len(LINES)) for mo in months for m in MARKETS])
    # editions: one per line per market every 6 weeks; capacity sized to typical demand. The planted sell-out's current one is small.
    prods = []
    for m in MARKETS:
        for l, lp in LINES.items():
            k, s = 0, since
            while s <= until + timedelta(days=42 + horizon):
                e = s + timedelta(days=41)
                per_day = t["base"][f"{m}|{l}"] * 0.35 * 1.16   # units a typical day sells
                cap = int(per_day * 42 * 2.2)                    # room for seasonal peaks
                if (m, l) == tuple(t["scenario"]["sellout"]) and s <= until - timedelta(days=10) <= e:
                    cap = int(per_day * max(1, (until - timedelta(days=10) - s).days))  # sized far too small: sells out 10 days before the end
                prods.append((f"{CODES[m]}-{lp['code']}-E{k:02d}", m, l, f"{m} · {l} · Edition {k + 1}", s.isoformat(), e.isoformat(), cap, lp["aov"]))
                s, k = s + timedelta(days=42), k + 1
    db.executemany("INSERT INTO products (product_id, market, line, name, launch_day, end_day, capacity, price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", prods)
    db.commit()
    db.close()
    state = {"aw": {}, "sold": {}}
    # simulate edition by edition so stock resets with each new edition
    end = until + timedelta(days=horizon)
    pol = policy or Policy()
    pol.start = pol.start or (until + timedelta(days=1))
    edges = sorted({date.fromisoformat(p[4]) for p in prods if date.fromisoformat(p[4]) <= end} | {since} | ({until + timedelta(days=1)} if horizon else set()))
    for i, a in enumerate(edges):
        b = (edges[i + 1] - timedelta(days=1)) if i + 1 < len(edges) else end
        if b < a:
            continue
        simulate(hub, a, b, pol, seed, t, wx, hol, state, origin=until)
    # category search interest: potential demand × season × weather, before the brand's awareness or spend
    si = []
    wk = since - timedelta(days=since.weekday())
    while wk <= until:  # history only: the agents never see the future
        for m, mp in MARKETS.items():
            for l in LINES:
                tot = 0.0
                for i in range(7):
                    d = wk + timedelta(days=i)
                    if d < since or d > until:
                        continue
                    tmp, rn = wx.get(m, {}).get(d.isoformat(), (15.0, 0.0))
                    tot += t["base"][f"{m}|{l}"] * _season(l, m, d, t["scenario"]) * _weather(l, m, tmp, rn, t["scenario"]) * _ramp(m, d, until, t["scenario"]) * 55
                if tot:
                    si.append((wk.isoformat(), m, l, int(tot * random.Random(f"si|{seed}|{wk}|{m}|{l}").uniform(0.93, 1.07)), "SYNTHETIC search-trends style index"))
        wk += timedelta(days=7)
    with store.connect(hub) as db:
        db.executemany("INSERT INTO search_interest (week, market, line, searches, source) VALUES (?, ?, ?, ?, ?)", si)
        for (pid, sold) in state["sold"].items():
            cap = db.execute("SELECT capacity, end_day FROM products WHERE product_id = ?", (pid,)).fetchone()
            if cap and sold >= cap[0]:
                day = db.execute("""SELECT day FROM (SELECT day, SUM(units) OVER (ORDER BY day) AS cum FROM product_daily WHERE product_id = ?)
                                    WHERE cum >= ? ORDER BY day LIMIT 1""", (pid, cap[0])).fetchone()
                if day:
                    db.execute("INSERT OR IGNORE INTO stock_events (product_id, day, event) VALUES (?, ?, 'sold_out')", (pid, day[0]))
        store.log_sync(db, "enterprise-world", since.isoformat(), until.isoformat(), 0,
                       "SYNTHETIC enterprise business (12 markets x 4 lines); real weather (Open-Meteo) and public holidays (Nager.Date)")
        db.commit()
    (hub.parent / f"{hub.stem}.truth.json").write_text(json.dumps({"seed": seed, "until": until.isoformat(), "planted": planted(t["scenario"])[0], "traps": planted(t["scenario"])[1], **t}))
    return hub


if __name__ == "__main__":
    import time
    t0 = time.time()
    p = build(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 7)
    print(f"SYNTHETIC enterprise hub written to {p} in {time.time() - t0:.0f}s")
