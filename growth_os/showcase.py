"""Builds the full SYNTHETIC showcase business in one hub: 60 weeks of multi-market sales and ads (demo_b2c), behaviour
data (funnel, session signals, exit survey, sell-outs), customer journeys for attribution, and the plan the team
manages to (targets, gross margin).

    python -m growth_os.showcase state/showcase-7.sqlite 7
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from . import attribution, behaviour, demo_b2c
from .hub import store

TARGETS = [  # scope, metric, target, direction: the (synthetic) plan
    ("all", "mer", 10.0, "min"),            # revenue at least 10x marketing spend: spend at most 10% of gross revenue
    ("all", "blended_cac", 16.0, "max"),
    ("all", "cpa", 20.0, "max"),            # per ad, first-party orders
    ("all", "roas", 3.0, "min"),            # per ad, first-party revenue
    ("all", "cpm", 9.0, "max"),             # Meta and TikTok
    ("all", "payback_orders", 0.6, "max"),  # first order's gross margin covers CAC
]
GROSS_MARGIN = 0.45


def prepare(hub: Path, seed: int = 7, until: date = date(2026, 10, 25), build: bool = True) -> Path:
    if build:
        demo_b2c.build(hub, until=until, seed=seed)
    behaviour.add(hub, seed=seed)
    attribution.simulate_journeys(hub, seed=seed)
    with store.connect(hub) as db:
        db.executemany("INSERT OR REPLACE INTO targets (scope, metric, target, direction) VALUES (?, ?, ?, ?)", TARGETS)
        db.execute("INSERT OR REPLACE INTO unit_costs (scope, gross_margin) VALUES ('all', ?)", (GROSS_MARGIN,))
        db.commit()
    return hub


PLANTED = {**demo_b2c.PLANTED, **behaviour.PLANTED}

if __name__ == "__main__":
    p = prepare(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 7)
    print(f"SYNTHETIC showcase hub written to {p}")
