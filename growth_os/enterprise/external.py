"""Real public inputs for the demand model, fetched once and cached in data/external/ (committed, with sources):

  weather   Open-Meteo historical archive and 16-day forecast: daily mean temperature and precipitation per city
            (open-meteo.com, CC BY 4.0)
  holidays  Nager.Date public holidays per country (date.nager.at, MIT)

    python -m growth_os.enterprise.external 2025-08-25 2026-11-01
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

from ..config import ROOT
from .profile import MARKETS

CACHE = ROOT / "data" / "external"
SOURCES = {"weather": "Open-Meteo (open-meteo.com), historical archive and forecast API, CC BY 4.0",
           "holidays": "Nager.Date (date.nager.at) public holidays API, MIT licence"}


def _get(url: str) -> dict | list:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def weather(since: date, until: date) -> dict[str, dict[str, tuple[float, float]]]:
    """city -> day -> (mean temperature °C, precipitation mm). History from the archive."""
    path = CACHE / f"weather-{since}-{until}.json"
    if path.is_file():
        return json.loads(path.read_text())
    out = {}
    for m, p in MARKETS.items():
        d = _get(f"https://archive-api.open-meteo.com/v1/archive?latitude={p['lat']}&longitude={p['lon']}&start_date={since}&end_date={until}"
                 f"&daily=temperature_2m_mean,precipitation_sum&timezone={p['tz']}")["daily"]
        out[m] = {t: (tm if tm is not None else 15.0, pr if pr is not None else 0.0)
                  for t, tm, pr in zip(d["time"], d["temperature_2m_mean"], d["precipitation_sum"])}
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def forecast(as_of: date) -> dict[str, dict[str, tuple[float, float]]]:
    """city -> day -> (temp, precipitation) for the next 16 days, as forecast on `as_of` (cached per day)."""
    path = CACHE / f"forecast-{as_of}.json"
    if path.is_file():
        return json.loads(path.read_text())
    out = {}
    for m, p in MARKETS.items():
        d = _get(f"https://api.open-meteo.com/v1/forecast?latitude={p['lat']}&longitude={p['lon']}&forecast_days=16"
                 f"&daily=temperature_2m_mean,precipitation_sum&timezone={p['tz']}")["daily"]
        out[m] = {t: (tm if tm is not None else 15.0, pr if pr is not None else 0.0)
                  for t, tm, pr in zip(d["time"], d["temperature_2m_mean"], d["precipitation_sum"])}
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def holidays(years: list[int]) -> dict[str, list[str]]:
    """country code -> list of national public holiday dates."""
    path = CACHE / f"holidays-{'-'.join(map(str, years))}.json"
    if path.is_file():
        return json.loads(path.read_text())
    out: dict[str, list[str]] = {}
    for cc in sorted({p["country"] for p in MARKETS.values()}):
        for y in years:
            out.setdefault(cc, []).extend(h["date"] for h in _get(f"https://date.nager.at/api/v3/PublicHolidays/{y}/{cc}") if h.get("global", True))
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


if __name__ == "__main__":
    s, u = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2])
    w = weather(s, u)
    h = holidays(sorted({s.year, u.year, u.year + 1}))
    f = forecast(date.today())
    print(f"weather: {sum(len(v) for v in w.values())} city-days; holidays: {sum(len(v) for v in h.values())}; forecast: {sum(len(v) for v in f.values())} city-days")
