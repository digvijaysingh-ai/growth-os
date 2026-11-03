"""SIMULATED market for the B2C scenario: runs the business forward day by day, reading what the executor changed.

The history in a B2C hub comes from demo_b2c.build(). This module continues it: the same markets, channels and planted
problems carry on (the Paris creative keeps fatiguing, the Berlin/Amsterdam iOS checkout stays broken, London's paid
costs stay high), and every change the executor made (paused ads, budgets, tickets, email flows) takes effect.

Random draws are seeded per day and per cell (market, channel, ad, device), so two copies of a hub run forward with the
same seed differ only where an action changed something. That is what makes the counterfactual honest: "with the
action" minus "without it", everything else identical.

What an action does here is a modelling assumption, stated in ASSUMPTIONS and shown next to every simulated outcome.
"""
from __future__ import annotations

import math
import random
import re
import shutil
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

from .demo_b2c import AOV, CODES, DEVICES, MARKETS, META_ADS, TIKTOK_ADS, _ramp, _season
from .hub import store

ASSUMPTIONS = [
    "Paused prospecting ads (Meta, TikTok, generic search) lose their buyers, except about 10% who come back directly.",
    "Paused brand-search ads lose few buyers: about 85% of brand searchers arrive through organic search instead.",
    "Clicks grow with spend at a diminishing rate (spend to the power 0.8).",
    "An engineering ticket about the iOS checkout is fixed 3 days after it is opened.",
    "An email flow about a product adds email visits in its market and lifts that product's sales by about 60% while it runs (14 days).",
    "An ops ticket to restock a sold-out product restocks it 2 days later, at the size of the market's typical product.",
    "While a product is sold out, its market loses about a sixth of its orders (a third of demand is for that product; half of those buyers pick another).",
    "A/B tests, notifications and other tickets are recorded and executed; their effects are not simulated.",
]


def simulated(ex: dict) -> bool:
    """Whether the simulation models this action's effect (otherwise it is executed and tracked, but not measured)."""
    kind, t, note = ex.get("exec_type") or ex.get("type"), ex.get("exec_target") or ex.get("target"), (ex.get("exec_note") or ex.get("note") or "")
    if kind in ("pause_ad", "resume_ad", "rotate_creative", "change_budget", "shift_budget", "trigger_email_flow"):
        return True
    if kind == "open_ticket" and t == "engineering" and re.search(r"ios|iphone|checkout|payment|apple pay", note, re.I):
        return True
    if kind == "open_ticket" and t == "ops" and re.search(r"[A-Z]{3}-P\d{3}", note) and re.search(r"capacity|restock|stock|sold out", note, re.I):
        return True
    return False


def _restocks(db: sqlite3.Connection) -> dict[str, date]:
    """Ops tickets naming a sold-out product: product_id -> day it is back in stock."""
    sold_out = {r[0] for r in db.execute("SELECT product_id FROM stock_events WHERE event = 'sold_out'")} if _has_table(db, "stock_events") else set()
    out = {}
    for note, opened in db.execute("SELECT note, opened_on FROM work_items WHERE kind = 'ticket' AND target = 'ops'"):
        if not re.search(r"capacity|restock|stock|sold out", note, re.I):
            continue
        for pid in re.findall(r"[A-Z]{3}-P\d{3}", note):
            if pid in sold_out:
                out[pid] = date.fromisoformat(opened) + timedelta(days=2)
    return out


def _has_table(db, name) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone() is not None
from .config import ROOT as _ROOT

SIM = _ROOT / "state" / "sim"   # throwaway hub copies for counterfactuals; world.cleanup() removes them
BASE_SPEND = {"META": 110.0, "TT": 55.0, "GGL-BRAND": 60.0, "GGL-GENERIC": 85.0}
ELASTICITY = 0.8


def _cell(seed: int, *key) -> random.Random:
    return random.Random("|".join(map(str, (seed, *key))))


def base_spend(ad_id: str) -> float:
    code, rest = ad_id.split("-", 1)
    size = MARKETS[{v: k for k, v in CODES.items()}[code]][0]
    kind = rest.rsplit("-", 1)[0] if rest.startswith(("META", "TT")) else rest
    return BASE_SPEND[kind] * size


def _origin(db: sqlite3.Connection) -> date:
    """The scenario's original last day: the planted problems are timed from it."""
    r = db.execute("SELECT until FROM sync_log WHERE source = 'demo-b2c' ORDER BY ts LIMIT 1").fetchone()
    return date.fromisoformat(r[0])


def _state(db: sqlite3.Connection) -> dict[str, tuple[str, float]]:
    return {r[0]: (r[1], r[2]) for r in db.execute("SELECT ad_id, status, budget_mult FROM account_state")}


def _fixes(db: sqlite3.Connection) -> dict[str, date]:
    """iOS checkout fixes: market -> day it works again (3 days after an engineering ticket about it)."""
    out: dict[str, date] = {}
    for r in db.execute("SELECT note, target, opened_on FROM work_items WHERE kind = 'ticket'"):
        if r[1] != "engineering" or not re.search(r"ios|iphone|checkout|payment|apple pay", r[0], re.I):
            continue
        named = [m for m in ("Berlin", "Amsterdam") if m.lower() in r[0].lower()] or ["Berlin", "Amsterdam"]
        for m in named:
            fix = date.fromisoformat(r[2]) + timedelta(days=3)
            out[m] = min(out.get(m, fix), fix)
    return out


def _flows(db: sqlite3.Connection) -> list[tuple[str, date]]:
    return [(r[0], date.fromisoformat(r[1])) for r in db.execute("SELECT target, opened_on FROM work_items WHERE kind = 'email_flow'")]


def step(hub: Path, days: int, seed: int = 7) -> date:
    """Appends `days` simulated days to a B2C hub. Returns the new last day."""
    db = store.connect(hub)
    u0 = _origin(db)
    last = date.fromisoformat(db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0])
    launched = {r[0]: date.fromisoformat(r[1]) for r in db.execute("SELECT market, launched_on FROM markets")}
    state, fixes = _state(db), _fixes(db)
    flows = _flows(db)
    flow_products = {p for p, _ in flows}
    products = [dict(r) for r in db.execute("SELECT product_id, market, name, launch_day, end_day, capacity, price FROM products")]
    sold = {r[0]: r[1] or 0 for r in db.execute("SELECT product_id, SUM(units) FROM product_daily GROUP BY product_id")}
    restock = _restocks(db)
    sold_out_on = {r[0]: date.fromisoformat(r[1]) for r in db.execute("SELECT product_id, day FROM stock_events WHERE event = 'sold_out'")} \
        if _has_table(db, "stock_events") else {}
    typical_cap = {}
    for p in products:
        typical_cap.setdefault(p["market"], []).append(p["capacity"])
    typical_cap = {m: sorted(v)[len(v) // 2] for m, v in typical_cap.items()}
    ads, sales, prows = [], [], []

    def st(ad_id):  # (active?, spend multiplier)
        s, mult = state.get(ad_id, ("ACTIVE", 1.0))
        return s == "ACTIVE", mult

    for i in range(1, days + 1):
        d = last + timedelta(days=i)
        ds = d.isoformat()
        orders_by_market: dict[str, int] = {}

        out_of_stock = {p["market"] for p in products if p["product_id"] in sold_out_on and sold_out_on[p["product_id"]] < d <= date.fromisoformat(p["end_day"])
                        and not (p["product_id"] in restock and d >= restock[p["product_id"]])}

        def sell(m, channel, ad_id, sessions_total, p_checkout, p_order, p_new):
            rev_t, ord_t = 0.0, 0
            if m in out_of_stock:
                p_order *= 5 / 6
            for dev, share in DEVICES:
                n = round(sessions_total * share)
                if n <= 0:
                    continue
                r = _cell(seed, ds, m, channel, ad_id, dev)
                broken = m in ("Berlin", "Amsterdam") and dev == "ios" and not (m in fixes and d >= fixes[m])
                po = 0.22 if broken else p_order
                co = r.binomialvariate(n, min(0.95, p_checkout))
                o = r.binomialvariate(co, po)
                rev = round(o * AOV * r.uniform(0.93, 1.07), 2)
                sales.append(dict(day=ds, market=m, channel=channel, ad_id=ad_id, device=dev, sessions=n, checkouts=co, orders=o, revenue=rev,
                                  new_customers=r.binomialvariate(o, p_new)))
                rev_t += rev
                ord_t += o
            orders_by_market[m] = orders_by_market.get(m, 0) + ord_t
            return rev_t, ord_t

        for m, (size, _age) in MARKETS.items():
            code = CODES[m]
            age = (d - launched[m]).days if m in launched and _age is not None else None
            ramp = _ramp(age, slow=(m == "Mexico City"))
            r0 = _cell(seed, ds, m, "market")
            season = _season(m, d) * r0.gauss(1, 0.05)
            demand = season * ramp
            spend_k = size * (1.18 if m == "Barcelona" else 1.0)  # Barcelona keeps overspending until someone acts
            london = m == "London"
            lost_direct = 0  # buyers of paused prospecting ads who come back directly

            def spend_for(ad_id, base):
                active, mult = st(ad_id)
                r = _cell(seed, ds, ad_id, "spend")
                return (round(base * mult / size * spend_k * min(1.0, ramp * 1.4) * r.uniform(0.85, 1.15), 2) if active else 0.0), mult, active

            for j, (name, ctr) in enumerate(META_ADS):
                ad_id = f"{code}-META-{j + 1}"
                spend, mult, active = spend_for(ad_id, base_spend(ad_id))
                r = _cell(seed, ds, ad_id, "delivery")
                cpm = 7.0 * (1.4 if london else 1.0) * r.uniform(0.9, 1.1)
                full_imps = int(110 * spend_k * min(1.0, ramp * 1.4) / cpm * 1000)
                freq, c = 1.9 + r.uniform(-0.2, 0.2), ctr
                if m == "Paris" and j == 0:
                    t = min(1.4, (d - (u0 - timedelta(days=35))).days / 35)
                    freq, c = 2.0 + 3.6 * t, ctr * max(0.25, 1 - 0.62 * t)
                if not active:
                    lost_direct += int(full_imps * c * 0.85 * 0.10)
                    ads.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Meta prospecting", spend=0.0, impressions=0, reach=0, link_clicks=0, form_leads=0,
                                    market=m, platform="meta", creative=name, frequency=None, platform_purchases=0, platform_revenue=0.0))
                    continue
                imps = int(full_imps * mult ** ELASTICITY)
                clicks = r.binomialvariate(imps, c)
                rev, orders = sell(m, "paid:meta", ad_id, int(clicks * 0.85), 0.10 * demand, 0.62, 0.55)
                ads.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Meta prospecting", spend=spend, impressions=imps, reach=int(imps / freq),
                                link_clicks=clicks, form_leads=0, market=m, platform="meta", creative=name, frequency=round(freq, 2),
                                platform_purchases=round(orders * 1.35), platform_revenue=round(rev * r.uniform(1.25, 1.45), 2)))
            for j, (name, ctr) in enumerate(TIKTOK_ADS):
                ad_id = f"{code}-TT-{j + 1}"
                spend, mult, active = spend_for(ad_id, base_spend(ad_id))
                r = _cell(seed, ds, ad_id, "delivery")
                full_imps = int(55 * spend_k * min(1.0, ramp * 1.4) / (4.2 * (1.4 if london else 1.0) * r.uniform(0.9, 1.1)) * 1000)
                if not active:
                    lost_direct += int(full_imps * ctr * 0.8 * 0.10)
                    ads.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · TikTok", spend=0.0, impressions=0, reach=0, link_clicks=0, form_leads=0,
                                    market=m, platform="tiktok", creative=name, frequency=None, platform_purchases=0, platform_revenue=0.0))
                    continue
                imps = int(full_imps * mult ** ELASTICITY)
                clicks = r.binomialvariate(imps, ctr)
                rev, orders = sell(m, "paid:tiktok", ad_id, int(clicks * 0.8), 0.055 * demand, 0.6, 0.65)
                ads.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · TikTok", spend=spend, impressions=imps, reach=int(imps / 1.7), link_clicks=clicks,
                                form_leads=0, market=m, platform="tiktok", creative=name, frequency=round(1.7 + r.uniform(-0.2, 0.2), 2),
                                platform_purchases=round(orders * 1.7), platform_revenue=round(rev * r.uniform(1.55, 1.85), 2)))
            ad_id = f"{code}-GGL-BRAND"
            r = _cell(seed, ds, ad_id, "delivery")
            brand_sessions = int(150 * size * demand * r.uniform(0.9, 1.1))
            spend, mult, active = spend_for(ad_id, base_spend(ad_id))
            organic_extra = 0
            if active:
                bs = int(brand_sessions * min(1.15, mult ** 0.3))  # brand demand barely responds to budget
                rev, orders = sell(m, "paid:google_brand", ad_id, bs, 0.2 * min(1.2, season), 0.7, 0.25)
                ads.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Google brand", spend=spend, impressions=int(bs * 2.2), reach=int(bs * 2),
                                link_clicks=bs, form_leads=0, market=m, platform="google", creative="Brand search", frequency=None,
                                platform_purchases=round(orders * 1.08), platform_revenue=round(rev * r.uniform(1.03, 1.12), 2)))
            else:
                organic_extra = int(brand_sessions * 0.85)
                ads.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Google brand", spend=0.0, impressions=0, reach=0, link_clicks=0, form_leads=0,
                                market=m, platform="google", creative="Brand search", frequency=None, platform_purchases=0, platform_revenue=0.0))
            ad_id = f"{code}-GGL-GENERIC"
            r = _cell(seed, ds, ad_id, "delivery")
            spend, mult, active = spend_for(ad_id, base_spend(ad_id))
            if active:
                clicks = int(85 * spend_k * min(1.0, ramp * 1.4) / r.uniform(0.85, 1.0) * mult ** ELASTICITY)
                rev, orders = sell(m, "paid:google_generic", ad_id, int(clicks * 0.9), 0.07 * demand, 0.62, 0.6)
                ads.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Google generic", spend=spend, impressions=clicks * 18, reach=clicks * 15,
                                link_clicks=clicks, form_leads=0, market=m, platform="google", creative="Generic search", frequency=None,
                                platform_purchases=round(orders * 1.1), platform_revenue=round(rev * r.uniform(1.05, 1.15), 2)))
            else:
                lost_direct += int(85 * spend_k * min(1.0, ramp * 1.4) * 0.9 * 0.10)
                ads.append(dict(day=ds, ad_id=ad_id, campaign=f"{m} · Google generic", spend=0.0, impressions=0, reach=0, link_clicks=0, form_leads=0,
                                market=m, platform="google", creative="Generic search", frequency=None, platform_purchases=0, platform_revenue=0.0))
            flow_on = any(p["market"] == m and p["product_id"] == fp and fd <= d < fd + timedelta(days=14) for p in products for fp, fd in flows)
            email_k = (2.3 if london else 1.0) + (0.5 if flow_on else 0.0)
            r = _cell(seed, ds, m, "owned")
            sell(m, "email", "", int(220 * size * season * ramp * email_k * r.uniform(0.85, 1.15)), 0.11, 0.66, 0.15)
            base_org = int(560 * size * demand * r.uniform(0.9, 1.1))
            # brand searchers who now arrive organically keep their own (higher) intent to buy
            p_org = (base_org * 0.09 + organic_extra * 0.2 * min(1.2, season)) / max(1, base_org + organic_extra)
            sell(m, "organic", "", base_org + organic_extra, p_org, 0.64, 0.4)
            sell(m, "direct", "", int(300 * size * demand * r.uniform(0.9, 1.1)) + lost_direct, 0.1, 0.65, 0.3)

        for p in products:
            if not (p["launch_day"] <= ds <= p["end_day"]):
                continue
            r = _cell(seed, ds, p["product_id"], "units")
            exp = orders_by_market.get(p["market"], 0) / 3
            share = 0.4 if "Autumn special" in p["name"] else 1.0
            if p["product_id"] in flow_products and any(fp == p["product_id"] and fd <= d < fd + timedelta(days=14) for fp, fd in flows):
                share *= 1.6
            cap = p["capacity"] + (typical_cap.get(p["market"], 0) if p["product_id"] in restock and d >= restock[p["product_id"]] else 0)
            units = min(r.binomialvariate(int(exp * 1.6) + 1, min(1.0, share / 1.6)), max(0, cap - sold.get(p["product_id"], 0)))
            sold[p["product_id"]] = sold.get(p["product_id"], 0) + units
            prows.append(dict(day=ds, product_id=p["product_id"], units=units, revenue=round(units * p["price"], 2)))

    s, u = (last + timedelta(days=1)).isoformat(), (last + timedelta(days=days)).isoformat()
    store.replace_window(db, "ad_daily", ads, s, u)
    store.replace_window(db, "sales_daily", sales, s, u)
    store.replace_window(db, "product_daily", prows, s, u)
    for pid, day in restock.items():
        if day <= last + timedelta(days=days):
            db.execute("INSERT OR IGNORE INTO stock_events (product_id, day, event) VALUES (?, ?, 'restocked')", (pid, day.isoformat()))
            db.execute("""UPDATE work_items SET status = 'done', closed_on = ?, result = 'restocked (simulated: 2 days after the ticket)'
                          WHERE kind = 'ticket' AND status = 'open' AND target = 'ops' AND note LIKE ?""", (day.isoformat(), f"%{pid}%"))
    for m, fix in fixes.items():
        if fix <= last + timedelta(days=days):
            db.execute("""UPDATE work_items SET status = 'done', closed_on = ?, result = 'fixed (simulated: 3 days after the ticket)'
                          WHERE kind = 'ticket' AND status = 'open' AND target = 'engineering'""", (fix.isoformat(),))
    store.log_sync(db, "world", s, u, len(ads) + len(sales), "SIMULATED forward days")
    db.commit()
    has_behaviour = db.execute("SELECT EXISTS(SELECT 1 FROM events_daily)").fetchone()[0]
    db.close()
    if has_behaviour:
        from . import behaviour
        behaviour.add(hub, since=s, seed=seed)
    return last + timedelta(days=days)


def fork(hub: Path, name: str) -> Path:
    """A throwaway copy of a hub, for running a counterfactual."""
    from .config import ROOT
    SIM.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="gos-", dir=SIM)) / f"{name}.sqlite"
    shutil.copy(hub, out)
    return out


def cleanup() -> None:
    """Removes every throwaway copy fork() made (only those; other simulations in state/sim are left alone)."""
    for d in SIM.glob("gos-*"):
        shutil.rmtree(d, ignore_errors=True)


def metric(hub: Path, sql: str) -> float | None:
    from .tracker import _value
    with store.connect(hub, read_only=True) as db:
        return _value(db, sql)


def money(hub: Path, since: date) -> dict:
    """Revenue, spend and orders from `since` onwards, total and by market: what an action changed, in money."""
    with store.connect(hub, read_only=True) as db:
        tot = db.execute("SELECT ROUND(SUM(revenue), 2), SUM(orders) FROM sales_daily WHERE day >= ?", (since.isoformat(),)).fetchone()
        sp = db.execute("SELECT ROUND(SUM(spend), 2) FROM ad_daily WHERE day >= ?", (since.isoformat(),)).fetchone()
        return {"revenue": tot[0] or 0.0, "orders": tot[1] or 0, "spend": sp[0] or 0.0}

