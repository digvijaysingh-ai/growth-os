"""Builds the complete SYNTHETIC enterprise hub: 62 weeks of the business (real weather and holidays), customer comments
labelled by Claude (cached by text, so rebuilds cost nothing), and the targets the team manages to.

    python -m growth_os.enterprise.prepare state/enterprise-7.sqlite 7
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..hub import store
from . import voc, world

TARGETS = [("all", "mer", 8.0, "min"), ("all", "blended_cac", 30.0, "max"), ("all", "cpa", 25.0, "max"), ("all", "roas", 2.0, "min"),
           ("all", "cpm", 12.0, "max")]


def prepare(hub: Path, seed: int = 7, classify: bool = True) -> Path:
    world.build(hub, seed)
    voc.generate(hub, seed)
    if classify:
        voc.classify(hub, log=lambda *_: None)
    with store.connect(hub) as db:
        db.executemany("INSERT OR REPLACE INTO targets (scope, metric, target, direction) VALUES (?, ?, ?, ?)", TARGETS)
        db.commit()
    return hub


if __name__ == "__main__":
    p = prepare(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 7)
    print(f"SYNTHETIC enterprise hub ready: {p}")
