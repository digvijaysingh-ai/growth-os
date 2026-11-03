"""The SYNTHETIC enterprise business: 12 markets × 4 product lines, a marketing plan of €50k–100k a month per line per
market, split across 8 paid channels, plus owned and organic channels.

City coordinates, time zones and countries are real (they drive the real weather and holidays). Population is a rounded
public figure for the metro area, used only as a size input. Everything else here (affluence, category propensity,
competition, response curves, the plan) is synthetic and labelled so.
"""
from __future__ import annotations

MARKETS = {  # name: real location, rounded metro population (millions), synthetic profile
    "Madrid":      {"lat": 40.42, "lon": -3.70, "tz": "Europe/Madrid", "country": "ES", "pop_m": 6.8, "affluence": 1.00, "competition": 1.00, "launched": None},
    "Barcelona":   {"lat": 41.39, "lon": 2.17, "tz": "Europe/Madrid", "country": "ES", "pop_m": 5.6, "affluence": 1.02, "competition": 1.05, "launched": None},
    "Lisbon":      {"lat": 38.72, "lon": -9.14, "tz": "Europe/Lisbon", "country": "PT", "pop_m": 2.9, "affluence": 0.85, "competition": 0.80, "launched": None},
    "Paris":       {"lat": 48.86, "lon": 2.35, "tz": "Europe/Paris", "country": "FR", "pop_m": 12.3, "affluence": 1.15, "competition": 1.25, "launched": None},
    "London":      {"lat": 51.51, "lon": -0.13, "tz": "Europe/London", "country": "GB", "pop_m": 14.8, "affluence": 1.20, "competition": 1.30, "launched": None},
    "Milan":       {"lat": 45.46, "lon": 9.19, "tz": "Europe/Rome", "country": "IT", "pop_m": 4.3, "affluence": 1.10, "competition": 1.00, "launched": None},
    "Berlin":      {"lat": 52.52, "lon": 13.40, "tz": "Europe/Berlin", "country": "DE", "pop_m": 4.7, "affluence": 1.05, "competition": 0.95, "launched": None},
    "Amsterdam":   {"lat": 52.37, "lon": 4.90, "tz": "Europe/Amsterdam", "country": "NL", "pop_m": 2.5, "affluence": 1.12, "competition": 0.90, "launched": None},
    "New York":    {"lat": 40.71, "lon": -74.01, "tz": "America/New_York", "country": "US", "pop_m": 19.5, "affluence": 1.25, "competition": 1.40, "launched": None},
    "São Paulo":   {"lat": -23.55, "lon": -46.63, "tz": "America/Sao_Paulo", "country": "BR", "pop_m": 22.4, "affluence": 0.70, "competition": 0.90, "launched": 300},
    "Miami":       {"lat": 25.76, "lon": -80.19, "tz": "America/New_York", "country": "US", "pop_m": 6.1, "affluence": 1.05, "competition": 1.00, "launched": 230},
    "Mexico City": {"lat": 19.43, "lon": -99.13, "tz": "America/Mexico_City", "country": "MX", "pop_m": 21.8, "affluence": 0.65, "competition": 0.85, "launched": 56},
}
CODES = {"Madrid": "MAD", "Barcelona": "BCN", "Lisbon": "LIS", "Paris": "PAR", "London": "LON", "Milan": "MIL", "Berlin": "BER",
         "Amsterdam": "AMS", "New York": "NYC", "São Paulo": "SAO", "Miami": "MIA", "Mexico City": "MEX"}

LINES = {  # product line: average order value (EUR), gross margin, weather sensitivity (rain, heat), seasonal peaks (synthetic)
    "Home":          {"code": "HOM", "aov": 74.0, "margin": 0.48, "rain": 0.16, "heat": -0.10, "peaks": [(11, 1.15), (12, 1.30), (1, 1.10)]},
    "Fashion drops": {"code": "FSH", "aov": 58.0, "margin": 0.55, "rain": -0.06, "heat": 0.04, "peaks": [(3, 1.15), (4, 1.10), (9, 1.20), (10, 1.10)]},
    "Beauty":        {"code": "BTY", "aov": 41.0, "margin": 0.62, "rain": 0.03, "heat": 0.02, "peaks": [(5, 1.10), (12, 1.25)]},
    "Gifts":         {"code": "GFT", "aov": 66.0, "margin": 0.44, "rain": 0.05, "heat": -0.02, "peaks": [(2, 1.20), (5, 1.15), (11, 1.35), (12, 1.90)]},
}
PROPENSITY = {"Home": 1.0, "Fashion drops": 1.15, "Beauty": 1.25, "Gifts": 0.85}  # orders per 1,000 residents per month, relative

PAID = ["meta_prospecting", "meta_retargeting", "tiktok", "youtube", "google_brand", "google_generic", "affiliates", "creators"]
OWNED = ["email", "sms"]
ORGANIC = ["organic_search", "organic_social", "direct"]
PLATFORM = {"meta_prospecting": "meta", "meta_retargeting": "meta", "tiktok": "tiktok", "youtube": "google", "google_brand": "google",
            "google_generic": "google", "affiliates": "affiliates", "creators": "creators"}
UPPER_FUNNEL = {"meta_prospecting", "tiktok", "youtube", "creators"}   # build awareness that lifts organic and brand demand

# the (synthetic) plan everyone follows today: share of each line's monthly budget per channel
PLAN_SPLIT = {"meta_prospecting": 0.30, "meta_retargeting": 0.12, "google_brand": 0.14, "google_generic": 0.18, "tiktok": 0.08,
              "youtube": 0.06, "affiliates": 0.06, "creators": 0.06}
# platform-reported conversions as a multiple of first-party last-click (synthetic, typical direction)
PLATFORM_CLAIM = {"meta_prospecting": 1.35, "meta_retargeting": 2.1, "tiktok": 1.7, "youtube": 1.9, "google_brand": 1.05, "google_generic": 1.12,
                  "affiliates": 1.25, "creators": 1.4}


def monthly_budget(market: str) -> float:
    """€50k–100k per product line per market per month, by market size and affluence (synthetic plan)."""
    p = MARKETS[market]
    size = (p["pop_m"] ** 0.35) * p["affluence"]
    lo, hi = (min((q["pop_m"] ** 0.35) * q["affluence"] for q in MARKETS.values()), max((q["pop_m"] ** 0.35) * q["affluence"] for q in MARKETS.values()))
    return round(50_000 + 50_000 * (size - lo) / (hi - lo), -3)
