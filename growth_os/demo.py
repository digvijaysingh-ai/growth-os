"""Builds a SYNTHETIC hub for demos and for evaluating the analyst: six weeks of a fictional studio's funnel.

Patterns are planted on purpose so the analyst can be graded against known answers (see PLANTED):
anything it reports must be one of these, or honestly marked as uncertain.

    python -m growth_os.demo                 # writes state/demo-hub.sqlite
    growth-os analyse --hub state/demo-hub.sqlite
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

from .config import ROOT
from .hub import store

PLANTED = {
    "mobile_form_errors": "On mobile, the form errors far more often and few form starts become submits; desktop converts normally.",
    "clicky_ad_low_quality": "Ad 'Reel: before and after' has the cheapest clicks and most sessions but the lowest share of qualified leads.",
    "speed_to_lead": "Leads contacted within 2 hours get a demo far more often than those contacted after 24 hours.",
    "traffic_up_leads_flat": "In the last week sessions rose sharply but leads per session fell clearly, because the extra traffic is the clicky ad, which barely converts.",
    "tiny_sample_trap": "Landing page /oferta-b shows a much higher form-start rate than /oferta, but on so few sessions it proves nothing.",
}

ADS = [  # id, name, cost per click, qualified share among its leads, base daily spend
    ("9001", "Reel: owner story", 0.55, 0.55, 8.0),
    ("9002", "Reel: before and after", 0.22, 0.12, 6.0),
    ("9003", "Carousel: prices", 0.48, 0.45, 4.0),
]
DEVICES = [("Móvil", 0.72), ("Ordenador", 0.28)]


def build(path: Path = ROOT / "state" / "demo-hub.sqlite", until: date = date(2026, 10, 25), weeks: int = 6, seed: int = 7) -> Path:
    rnd = random.Random(seed)
    path.unlink(missing_ok=True)
    db = store.connect(path)
    days = [until - timedelta(days=i) for i in range(weeks * 7 - 1, -1, -1)]
    last_week = days[-7:]
    sessions, ad_daily, leads, sections, clicks, demos = {}, [], [], [], [], []

    def add_sessions(day, landing, channel, ad_id, device, n, start_rate):
        if n <= 0:
            return 0
        k = (day, landing, channel, ad_id, device)
        s = sessions.setdefault(k, dict(day=day, landing=landing, channel=channel, ad_id=ad_id, device=device, sessions=0, bounces=0, engaged_s=0,
                                        scroll_25=0, scroll_50=0, scroll_75=0, scroll_100=0, form_starts=0, form_errors=0, form_submits=0))
        starts = sum(rnd.random() < start_rate for _ in range(n))
        err_rate, submit_rate = (0.62, 0.28) if device == "Móvil" else (0.12, 0.74)  # planted: mobile form is broken
        errors = sum(rnd.random() < err_rate for _ in range(starts))
        submits = sum(rnd.random() < submit_rate for _ in range(starts))
        s["sessions"] += n
        s["bounces"] += sum(rnd.random() < (0.55 if channel == "paid:meta" else 0.4) for _ in range(n))
        s["engaged_s"] += sum(int(rnd.gauss(38, 15)) for _ in range(n))
        for m, p in ((25, 0.7), (50, 0.45), (75, 0.25), (100, 0.12)):
            s[f"scroll_{m}"] += sum(rnd.random() < p for _ in range(n))
        s["form_starts"] += starts
        s["form_errors"] += errors
        s["form_submits"] += submits
        return submits

    def add_lead(day, origin, ad_id, source, medium, qualified_share):
        fast = rnd.random() < 0.45
        hours = round(rnd.uniform(0.2, 2) if fast else rnd.uniform(24, 72), 1)
        demo_p = 0.72 if fast else 0.2  # planted: speed to lead
        qualified = rnd.random() < demo_p * (qualified_share / 0.45)
        won = qualified and rnd.random() < 0.25
        stage = "Ganado" if won else ("Demo enviada" if qualified else rnd.choice(["Contactado", "Perdido", "Contactado"]))
        leads.append(dict(day=day, origin=origin, utm_source=source, utm_medium=medium, ad_id=ad_id, sector=rnd.choice(["bar", "peluqueria", "clinica", "tienda"]),
                          stage=stage, lang="es", wants_booking=int(rnd.random() < 0.3), est_value=500, hours_to_contact=hours,
                          hours_to_demo=round(hours + rnd.uniform(12, 60), 1) if qualified else None, days_to_win=round(rnd.uniform(3, 12), 1) if won else None))

    for day in days:
        d = day.isoformat()
        surge = day in last_week
        for ad_id, name, cpc, qshare, spend0 in ADS:
            spend = round(spend0 * rnd.uniform(0.8, 1.2) * (3.0 if surge and ad_id == "9002" else 1), 2)  # planted: last week's extra traffic is the clicky ad
            link_clicks = max(0, int(spend / cpc * rnd.uniform(0.85, 1.15)))
            ad_daily.append(dict(day=d, ad_id=ad_id, campaign="Always-on", spend=spend, impressions=int(link_clicks * rnd.uniform(70, 110)),
                                 reach=int(link_clicks * rnd.uniform(50, 80)), link_clicks=link_clicks, form_leads=0))
            visits = round(link_clicks * 0.8)
            start_rate = (0.01 if surge else 0.07) if ad_id == "9002" else 0.1  # planted: the surge brings visits, not leads
            for dev, share in DEVICES:
                for _ in range(add_sessions(d, "/", "paid:meta", ad_id, dev, round(visits * share), start_rate)):
                    add_lead(d, "web", ad_id, "meta", "paid", qshare if not (surge and ad_id == "9002") else 0.05)
        for channel, n in (("search", rnd.randint(14, 24)), ("direct", rnd.randint(6, 14)), ("social", rnd.randint(2, 6))):
            for dev, share in DEVICES:
                for _ in range(add_sessions(d, "/", channel, "", dev, round(n * share), 0.11)):
                    add_lead(d, "web", "", "", "", 0.5)
        if day in last_week[-4:]:  # planted: tiny-sample trap
            for landing, n, rate in (("/oferta", rnd.randint(1, 3), 0.1), ("/oferta-b", rnd.randint(1, 2), 0.6)):
                for _ in range(add_sessions(d, landing, "direct", "", "Ordenador", n, rate)):
                    add_lead(d, "web", "", "", "", 0.5)
        for sec, p in (("hero", 0.95), ("ejemplos", 0.55), ("precios", 0.38), ("faq", 0.18), ("demo", 0.22)):
            sections.append(dict(day=d, path="/", section=sec, sessions=int(sum(s["sessions"] for k, s in sessions.items() if k[0] == d) * p)))
        clicks.append(dict(day=d, path="/", label="Pide tu demo", target="/#demo", sessions=rnd.randint(4, 12)))
        clicks.append(dict(day=d, path="/", label="WhatsApp", target="wa.me", sessions=rnd.randint(1, 5)))
        demos.append(dict(day=d, demos_opened=rnd.randint(0, 3), demo_sessions=rnd.randint(0, 5), demo_engaged_s=rnd.randint(0, 600)))

    s, u = days[0].isoformat(), days[-1].isoformat()
    for table, rows in (("ad_daily", ad_daily), ("web_sessions", list(sessions.values())), ("web_sections", sections),
                        ("web_clicks", clicks), ("leads", leads), ("demos", demos)):
        store.replace_window(db, table, rows, s, u)
    db.executemany("INSERT INTO ads (ad_id, ad_name, campaign_id, status, updated_at) VALUES (?, ?, 'c1', 'ACTIVE', ?)", [(a[0], a[1], u) for a in ADS])
    store.log_sync(db, "demo", s, u, len(ad_daily) + len(sessions) + len(leads), "SYNTHETIC data, planted patterns")
    db.commit()
    db.close()
    return path


if __name__ == "__main__":
    p = build()
    print(f"SYNTHETIC demo hub written to {p.relative_to(ROOT)}")
    for k, v in PLANTED.items():
        print(f"  planted {k}: {v}")
