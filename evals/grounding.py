"""Checks that every number in a memo traces to the data the analyst was given.

A number is *grounded* when it appears (allowing for rounding) in the brief, a query result or a statistical check.
It is *derived* when it is a simple calculation from two grounded numbers in the same memo item: a ratio, a percentage,
a difference or a percentage change. Anything else is *unsupported* and listed, so a person can look.
"""
from __future__ import annotations

import itertools
import json
import re

NUM = re.compile(r"(?<![\w.])[-−]?\d[\d,]*(?:\.\d+)?")


def _nums(text: str) -> list[float]:
    out = []
    for m in NUM.findall(text):
        t = m.replace("−", "-").replace(",", "")
        try:
            out.append(float(t))
        except ValueError:
            pass
    return out


def _close(a: float, b: float) -> bool:
    if a == b:
        return True
    tol = max(0.51, abs(b) * 0.006) if abs(b) >= 100 else (0.051 if abs(b) < 10 else 0.51)
    return abs(a - b) <= tol


def _pool(values: set[float]):
    vals = sorted(values)
    return vals


def _in(x: float, pool: list[float]) -> bool:
    import bisect
    i = bisect.bisect_left(pool, x - max(0.51, abs(x) * 0.006))
    while i < len(pool) and pool[i] <= x + max(0.51, abs(x) * 0.006):
        if _close(x, pool[i]):
            return True
        i += 1
    return False


def check(memo: dict, sources: list[str]) -> dict:
    pool = _pool({abs(v) for src in sources for v in _nums(src)} | {v * 100 for src in sources for v in _nums(src) if 0 < abs(v) <= 1})
    items = [k["value"] + " " + k["previous"] + " " + k["note"] for k in memo.get("kpis", [])]
    items += [f["evidence"] for f in memo.get("findings", [])] + [r["why"] + " " + r["expected_impact"] for r in memo.get("recommendations", [])]
    items += [memo.get("headline", ""), memo.get("data_sufficiency", {}).get("explanation", "")]
    grounded = derived = unsupported = 0
    examples = []
    for text in items:
        nums = [abs(n) for n in _nums(text)]
        ok = [n for n in nums if _in(n, pool)]
        for n in nums:
            if n < 2 and float(n).is_integer():  # 0 and 1 carry no evidence
                continue
            if _in(n, pool):
                grounded += 1
            elif any(_close(n, v) for a, b in itertools.permutations(ok, 2) if b
                     for v in (a / b, 100 * a / b, a - b, 100 * (a - b) / b, a * b)):
                derived += 1
            else:
                unsupported += 1
                if len(examples) < 12:
                    examples.append({"number": n, "in": text[:160]})
    total = grounded + derived + unsupported
    return {"numbers": total, "grounded": grounded, "derived": derived, "unsupported": unsupported,
            "supported_pct": round(100 * (grounded + derived) / total, 1) if total else 100.0, "unsupported_examples": examples}


def sources_of(run) -> list[str]:
    return [json.dumps(run.brief, default=str)] + [q["result"] for q in run.queries] + [json.dumps(c) for c in run.comparisons]
