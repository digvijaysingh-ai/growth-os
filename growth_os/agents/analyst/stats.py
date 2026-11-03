"""Small, dependency-free statistics the analyst calls instead of eyeballing rates.

Wilson intervals for one rate, a two-proportion z-test for two, and the sample per arm an A/B test needs.
"""
from __future__ import annotations

import math

Z95 = 1.959964
Z80_POWER = 0.841621


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def sample_per_arm(base_rate: float, relative_lift: float) -> int | None:
    """Visitors each version needs to detect the lift with 95% confidence and 80% power."""
    p1, p2 = base_rate, base_rate * (1 + relative_lift)
    if not 0 < p1 < 1 or not 0 < p2 < 1 or p1 == p2:
        return None
    pbar = (p1 + p2) / 2
    n = (Z95 * math.sqrt(2 * pbar * (1 - pbar)) + Z80_POWER * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 / (p2 - p1) ** 2
    return math.ceil(n)


def compare_rates(a_successes: int, a_n: int, b_successes: int, b_n: int, comparisons: int = 1) -> dict:
    """Is rate A really different from rate B? Returns both rates with 95% intervals, the p-value and a plain verdict.

    comparisons: how many segments are being scanned for the same kind of change (e.g. 10 markets). The verdict then
    uses a Bonferroni-adjusted p-value, so one market out of ten moving by chance is not reported as a change."""
    if a_n <= 0 or b_n <= 0:
        return {"verdict": "no data", "detail": "one side has no observations"}
    pa, pb = a_successes / a_n, b_successes / b_n
    pool = (a_successes + b_successes) / (a_n + b_n)
    se = math.sqrt(pool * (1 - pool) * (1 / a_n + 1 / b_n)) if 0 < pool < 1 else 0.0
    p_value = 2 * (1 - _phi(abs(pa - pb) / se)) if se else 1.0
    m = max(1, int(comparisons))
    p_adj = min(1.0, p_value * m)
    lift = (pb - pa) / pa if pa else None
    needed = sample_per_arm(pa, lift) if lift else None
    if min(a_n, b_n) < 30 or min(a_successes, b_successes, a_n - a_successes, b_n - b_successes) < 5:
        verdict = "too little data to tell"
    elif p_adj < 0.05:
        verdict = "different (95% confidence)" + (f", after correcting for {m} comparisons" if m > 1 else "")
    elif p_value < 0.05:
        verdict = f"not significant once corrected for {m} comparisons: likely noise"
    elif p_value < 0.2:
        verdict = "directional only, not proven"
    else:
        verdict = "no detectable difference"
    return {
        "a_rate": round(pa, 4), "a_95ci": [round(x, 4) for x in wilson(a_successes, a_n)],
        "b_rate": round(pb, 4), "b_95ci": [round(x, 4) for x in wilson(b_successes, b_n)],
        "relative_lift_b_vs_a": round(lift, 3) if lift is not None else None,
        "p_value": round(p_value, 4), "p_adjusted": round(p_adj, 4), "comparisons": m, "verdict": verdict,
        "sample_per_arm_to_confirm_this_lift": needed,
    }
