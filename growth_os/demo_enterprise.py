"""SYNTHETIC enterprise scenario: 10 markets, 26 weeks, 30 ads. Three problems are planted in single markets, one
small-sample trap in another, and the other six markets carry only noise. It tests what matters at scale: finding the
needles in a long tail of segments without raising false alarms.

    python -m growth_os.demo_enterprise
    growth-os analyse --hub state/enterprise-hub.sqlite --period-days 28
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

from .config import ROOT
from .hub import store

PLANTED = {
    "fr_mobile_form": "France only: from about five weeks ago the mobile form errors on most starts and few mobile form starts become submits; desktop France and every other market are unaffected.",
    "de_ad_quality": "Germany only: ad 'DE · Before and after' still brings leads at the same rate, but from about five weeks ago almost none of them qualify (demo sent).",
    "it_slow_followup": "Italy only: from about eight weeks ago leads are contacted much more slowly (most after 24 h instead of most within 2 h), and Italy's qualified rate fell.",
    "nl_tiny_trap": "Netherlands: landing page /nl/oferta-b shows a much higher form-start rate than /nl/oferta, on so few sessions that it proves nothing.",
}
NOISE_ONLY = ["ES", "PT", "BE", "AT", "IE", "PL"]
MARKETS = {  # market: daily spend scale
    "ES": 1.4, "PT": 0.6, "FR": 1.3, "DE": 1.5, "IT": 1.1, "NL": 0.8, "BE": 0.5, "AT": 0.5, "IE": 0.4, "PL": 0.7,
}
ADS = [("Owner story", 0.55, 0.50), ("Before and after", 0.30, 0.42), ("Prices carousel", 0.48, 0.45)]  # name, cost per click, qualified share
DEVICES = [("Móvil", 0.7), ("Ordenador", 0.3)]


def build(path: Path = ROOT / "state" / "enterprise-hub.sqlite", until: date = date(2026, 10, 25), weeks: int = 26, seed: int = 7) -> Path:
    rnd = random.Random(seed)
    path.unlink(missing_ok=True)
    db = store.connect(path)
    days = [until - timedelta(days=i) for i in range(weeks * 7 - 1, -1, -1)]
    break_fr, break_de, break_it = until - timedelta(days=35), until - timedelta(days=35), until - timedelta(days=56)
    sessions, ad_daily, leads = {}, [], []

    def add_sessions(m, day, landing, channel, ad_id, device, n, start_rate):
        if n <= 0:
            return 0
        k = (day, m, landing, channel, ad_id, device)
        s = sessions.setdefault(k, dict(day=day, market=m, landing=landing, channel=channel, ad_id=ad_id, device=device, sessions=0, bounces=0,
                                        engaged_s=0, scroll_25=0, scroll_50=0, scroll_75=0, scroll_100=0, form_starts=0, form_errors=0, form_submits=0))
        broken = m == "FR" and device == "Móvil" and date.fromisoformat(day) >= break_fr
        err, sub = (0.66, 0.24) if broken else (0.12, 0.72)
        starts = sum(rnd.random() < start_rate for _ in range(n))
        submits = sum(rnd.random() < sub for _ in range(starts))
        s["sessions"] += n
        s["bounces"] += sum(rnd.random() < 0.45 for _ in range(n))
        s["engaged_s"] += sum(max(0, int(rnd.gauss(40, 15))) for _ in range(n))
        for mark, p in ((25, 0.7), (50, 0.45), (75, 0.25), (100, 0.12)):
            s[f"scroll_{mark}"] += sum(rnd.random() < p for _ in range(n))
        s["form_starts"] += starts
        s["form_errors"] += sum(rnd.random() < err for _ in range(starts))
        s["form_submits"] += submits
        return submits

    def add_lead(m, day, ad_id, qshare):
        d = date.fromisoformat(day)
        fast_share = 0.12 if (m == "IT" and d >= break_it) else 0.6
        fast = rnd.random() < fast_share
        hours = round(rnd.uniform(0.2, 2) if fast else rnd.uniform(24, 72), 1)
        qualified = rnd.random() < (0.72 if fast else 0.22) * (qshare / 0.45)
        won = qualified and rnd.random() < 0.25
        leads.append(dict(day=day, market=m, origin="web", utm_source="meta" if ad_id else "", utm_medium="paid" if ad_id else "", ad_id=ad_id,
                          sector=rnd.choice(["bar", "peluqueria", "clinica", "tienda"]),
                          stage="Ganado" if won else ("Demo enviada" if qualified else rnd.choice(["Contactado", "Perdido"])), lang=m.lower(),
                          wants_booking=0, est_value=500, hours_to_contact=hours, hours_to_demo=round(hours + rnd.uniform(12, 60), 1) if qualified else None,
                          days_to_win=round(rnd.uniform(3, 12), 1) if won else None))

    for day in days:
        ds = day.isoformat()
        for m, scale in MARKETS.items():
            for j, (name, cpc, qshare) in enumerate(ADS):
                ad_id = f"{m}{j + 1}"
                spend = round(15.0 * scale * rnd.uniform(0.75, 1.25), 2)
                clicks = max(0, round(spend / cpc * rnd.uniform(0.85, 1.15)))
                ad_daily.append(dict(day=ds, market=m, ad_id=ad_id, campaign=f"{m} always-on", spend=spend, impressions=clicks * rnd.randint(70, 110),
                                     reach=clicks * rnd.randint(50, 80), link_clicks=clicks, form_leads=0))
                q = 0.04 if (m == "DE" and name == "Before and after" and day >= break_de) else qshare
                for dev, share in DEVICES:
                    for _ in range(add_sessions(m, ds, f"/{m.lower()}/", "paid:meta", ad_id, dev, round(clicks * 0.8 * share), 0.09)):
                        add_lead(m, ds, ad_id, q)
            for dev, share in DEVICES:
                for _ in range(add_sessions(m, ds, f"/{m.lower()}/", "search", "", dev, round(rnd.randint(20, 50) * scale * share), 0.11)):
                    add_lead(m, ds, "", 0.5)
        if day >= until - timedelta(days=10):  # NL tiny-sample trap
            for landing, n, rate in (("/nl/oferta", rnd.randint(1, 3), 0.1), ("/nl/oferta-b", rnd.randint(0, 2), 0.6)):
                for _ in range(add_sessions("NL", ds, landing, "direct", "", "Ordenador", n, rate)):
                    add_lead("NL", ds, "", 0.5)

    s, u = days[0].isoformat(), days[-1].isoformat()
    for table, rows in (("ad_daily", ad_daily), ("web_sessions", list(sessions.values())), ("leads", leads)):
        store.replace_window(db, table, rows, s, u)
    db.executemany("INSERT INTO ads (ad_id, ad_name, campaign_id, status, updated_at) VALUES (?, ?, ?, 'ACTIVE', ?)",
                   [(f"{m}{j + 1}", f"{m} · {name}", f"{m} always-on", u) for m in MARKETS for j, (name, _, _) in enumerate(ADS)])
    store.log_sync(db, "demo-enterprise", s, u, len(ad_daily) + len(sessions) + len(leads), "SYNTHETIC enterprise scenario, planted patterns")
    db.commit()
    db.close()
    return path


if __name__ == "__main__":
    p = build()
    print(f"SYNTHETIC enterprise hub written to {p.relative_to(ROOT)}")
    for k, v in PLANTED.items():
        print(f"  planted {k}: {v}")
