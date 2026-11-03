"""Attribution: four answers to "what did each channel bring in?", side by side, and a plan to settle it.

  last_click      first-party orders credited to the last channel before purchase (what sales_daily records)
  platform        what each ad platform claims for itself (ad_daily.platform_revenue): double-counts across platforms
  data_driven     a first-order Markov model over customer journeys: a channel's credit is how many conversions
                  would be lost if it were removed from every journey (removal effect), normalised to 100%
  incrementality  what actually happened when a campaign was switched off (natural experiments in the data)

They disagree, and the disagreement is the point: the last two are the only ones that estimate what a channel adds.
Where no natural experiment exists, holdout_plan() designs a geo holdout that would settle it.

Journeys come from the hub's `journeys` table. The B2C demo fills it with a SYNTHETIC journey sample
(simulate_journeys) with a known ground truth; last touch and data-driven credit are both computed on that sample, so
they compare like with like. A real deployment loads path exports from the analytics tool instead.
"""
from __future__ import annotations

import math
import random
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .hub import store

PROSPECTING = {"paid:meta": 0.30, "paid:tiktok": 0.15, "paid:google_generic": 0.15, "organic": 0.25, "direct": 0.10, "email": 0.05}
CLOSERS = {"paid:google_brand": 0.40, "direct": 0.25, "email": 0.20, "organic": 0.15}


def simulate_journeys(hub: Path, per_market: int = 4000, seed: int = 7) -> int:
    """SYNTHETIC journeys for the last 28 days. Ground truth: prospecting touches create demand; brand search mostly
    closes journeys that would have converted anyway (it adds little conversion probability of its own)."""
    db = store.connect(hub)
    db.execute("DELETE FROM journeys")
    rows = []
    markets = [r[0] for r in db.execute("SELECT DISTINCT market FROM sales_daily")]
    for m in markets:
        r = random.Random(f"jr|{seed}|{m}")
        for i in range(per_market):
            path = [r.choices(list(PROSPECTING), weights=list(PROSPECTING.values()))[0]]
            for _ in range(r.choice([0, 1, 1, 2, 3])):
                path.append(r.choices(list(CLOSERS), weights=list(CLOSERS.values()))[0])
            touched = set(path)
            p = 0.015 + 0.035 * bool(touched & {"paid:meta", "paid:tiktok"}) + 0.02 * ("paid:google_generic" in touched) \
                + 0.012 * ("email" in touched) + 0.004 * ("paid:google_brand" in touched) + 0.006 * (len(path) - 1)
            conv = r.random() < p
            rows.append((m, f"{m[:3].upper()}-{i}", " > ".join(path), int(conv), round(62 * r.uniform(0.8, 1.2), 2) if conv else 0.0))
    db.executemany("INSERT INTO journeys (market, journey_id, path, converted, revenue) VALUES (?, ?, ?, ?, ?)", rows)
    store.log_sync(db, "journeys", "", "", len(rows), "SYNTHETIC customer journeys (touch paths) for attribution, last 28 days")
    db.commit()
    db.close()
    return len(rows)


def _paths(db: sqlite3.Connection, market: str | None) -> list[tuple[list[str], int]]:
    q = "SELECT path, converted FROM journeys" + (" WHERE market = ?" if market else "")
    return [(p.split(" > "), c) for p, c in db.execute(q, (market,) if market else ())]


def _conv_prob(trans: dict, removed: str | None = None, iters: int = 200) -> float:
    """Probability of reaching 'conv' from 'start' in the Markov chain, with one channel removed (it becomes 'null')."""
    states = list(trans)
    p = {s: 0.0 for s in states}
    p["conv"], p["null"] = 1.0, 0.0
    for _ in range(iters):
        for s in states:
            if s in ("conv", "null"):
                continue
            if s == removed:
                p[s] = 0.0
                continue
            p[s] = sum(w * p.get(t, 0.0) if t != removed else 0.0 for t, w in trans[s].items())
    return p["start"]


def markov(db: sqlite3.Connection, market: str | None = None) -> dict[str, float]:
    """Share of conversions credited to each channel by removal effect."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for path, conv in _paths(db, market):
        seq = ["start", *path, "conv" if conv else "null"]
        for a, b in zip(seq, seq[1:]):
            counts[a][b] += 1
    trans = {s: {t: n / sum(c.values()) for t, n in c.items()} for s, c in counts.items()}
    trans.setdefault("conv", {})
    trans.setdefault("null", {})
    base = _conv_prob(trans)
    channels = [s for s in trans if s not in ("start", "conv", "null")]
    effect = {c: max(0.0, 1 - _conv_prob(trans, c) / base) if base else 0.0 for c in channels}
    tot = sum(effect.values()) or 1.0
    return {c: round(100 * e / tot, 1) for c, e in sorted(effect.items(), key=lambda x: -x[1])}


def compare(db: sqlite3.Connection, market: str | None = None) -> list[dict]:
    """Per channel: share of credit under last click (journeys and first-party sales), platform claims, and Markov."""
    where, args = (" AND market = ?", (market,)) if market else ("", ())
    asof = db.execute("SELECT MAX(day) FROM sales_daily").fetchone()[0]
    fp = {r[0]: r[1] or 0 for r in db.execute(f"""SELECT channel, SUM(revenue) FROM sales_daily WHERE day > date(?, '-28 days'){where}
                                                  GROUP BY channel""", (asof, *args))}
    plat = {}
    for r in db.execute(f"""SELECT platform, CASE WHEN ad_id LIKE '%BRAND' THEN 'brand' WHEN ad_id LIKE '%GENERIC' THEN 'generic' ELSE '' END,
                            SUM(platform_revenue) FROM ad_daily WHERE day > date(?, '-28 days'){where} GROUP BY 1, 2""", (asof, *args)):
        key = {"meta": "paid:meta", "tiktok": "paid:tiktok"}.get(r[0]) or f"paid:google_{r[1]}"
        plat[key] = r[2] or 0
    last = Counter()
    for path, conv in _paths(db, market):
        if conv:
            last[path[-1]] += 1
    mk = markov(db, market) if last else {}
    tot_fp, tot_last = sum(fp.values()) or 1, sum(last.values()) or 1
    out = []
    for ch in sorted(set(fp) | set(mk), key=lambda c: -fp.get(c, 0)):
        out.append({"channel": ch, "first_party_revenue": round(fp.get(ch, 0)), "last_click_pct": round(100 * fp.get(ch, 0) / tot_fp, 1),
                    "journeys_last_touch_pct": round(100 * last.get(ch, 0) / tot_last, 1) if last else None,
                    "data_driven_pct": mk.get(ch), "platform_claimed_revenue": round(plat[ch]) if ch in plat else None,
                    "platform_overclaim_x": round(plat[ch] / fp[ch], 2) if ch in plat and fp.get(ch) else None})
    return out


def holdout_plan(db: sqlite3.Connection, channel: str = "paid:google_brand", mde_pct: float = 5.0, power_z: float = 0.84, alpha_z: float = 1.96) -> dict:
    """Designs a geo holdout: switch `channel` off in matched markets, compare total revenue with the markets that
    keep it. Weeks needed come from how much weekly market revenue moves by itself."""
    rows = db.execute("""SELECT market, week, revenue FROM v_market_weekly WHERE week > date((SELECT MAX(week) FROM v_market_weekly), '-84 days')
                         ORDER BY market, week""").fetchall()
    young = {r[0] for r in db.execute("""SELECT market FROM markets WHERE launched_on > date((SELECT MAX(day) FROM sales_daily), '-182 days')""")}
    by: dict[str, list[float]] = defaultdict(list)
    for m, _w, rev in rows:
        if m not in young:  # markets still ramping up would read as a channel effect
            by[m].append(rev or 0.0)
    cvs = []
    for m, xs in by.items():
        diffs = [b / a - 1 for a, b in zip(xs, xs[1:]) if a]
        if len(diffs) > 2 and sum(xs) / len(xs) > 20000:
            mu = sum(diffs) / len(diffs)
            cvs.append(math.sqrt(sum((d - mu) ** 2 for d in diffs) / (len(diffs) - 1)))
    cv = sorted(cvs)[len(cvs) // 2] if cvs else 0.1
    size = sorted(((sum(xs) / len(xs), m) for m, xs in by.items() if sum(xs) / len(xs) > 20000), reverse=True)
    test, control = [m for _, m in size[0::2]], [m for _, m in size[1::2]]
    k = max(1, min(len(test), len(control)))
    weeks = math.ceil(2 * (alpha_z + power_z) ** 2 * cv ** 2 / ((mde_pct / 100) ** 2 * k))
    spend = db.execute("""SELECT ROUND(SUM(spend) / 4.0) FROM ad_daily WHERE day > date((SELECT MAX(day) FROM ad_daily), '-28 days') AND
                          (CASE ? WHEN 'paid:google_brand' THEN ad_id LIKE '%BRAND' WHEN 'paid:google_generic' THEN ad_id LIKE '%GENERIC'
                           ELSE platform = replace(?, 'paid:', '') END) AND market IN (MARKETS)""".replace("MARKETS", ",".join("?" * len(test))),
                       (channel, channel, *test)).fetchone()[0]
    return {"channel": channel, "switch_off_in": test, "keep_on_in": control, "weeks": weeks, "detects_change_of_pct": mde_pct,
            "weekly_noise_pct": round(100 * cv, 1), "weekly_spend_paused": spend,
            "how": f"Pause {channel} in {', '.join(test)} for {weeks} weeks; compare their total revenue with {', '.join(control)} against the "
                   f"weeks before. Markets alternate by size so both groups match. A change smaller than {mde_pct:g}% will not be detectable."}
