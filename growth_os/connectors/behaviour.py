"""Connectors for behaviour data, written to each tool's documented API and mapped into the hub's tables.

  Mixpanel   Funnels API (query/funnels), one segment property per market and device  -> events_daily
  Clarity    Data Export API (project-live-insights): rage clicks, dead clicks, scroll -> ux_daily
             (Hotjar has no public API for heatmap or rage-click data; Microsoft Clarity exposes the same signals)
  Hotjar     Survey responses API (v1 surveys/responses), answers mapped to reasons    -> exit_survey

Each class has fetch() (network) and a pure parse() that turns the documented response shape into hub rows, so the
mapping is tested without credentials. Not yet run against live accounts: the demo uses synthetic data in the same
tables (behaviour.py).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from base64 import b64encode
from datetime import date

STEP_MAP = {"session_start": "session_start", "view_item": "view_product", "add_to_cart": "add_to_cart", "begin_checkout": "begin_checkout",
            "add_payment_info": "add_payment", "purchase": "purchase"}


def _get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


class Mixpanel:
    """Funnel counts per day and segment. The site sets one event property, gos_segment = "<market>|<device>", so a
    single funnel query splits by both."""

    def __init__(self, project_id: str, user: str, secret: str, funnel_id: str, region: str = "eu"):
        self.base = f"https://{'eu.' if region == 'eu' else ''}mixpanel.com/api/query/funnels"
        self.auth = "Basic " + b64encode(f"{user}:{secret}".encode()).decode()
        self.project_id, self.funnel_id = project_id, funnel_id

    def fetch(self, since: date, until: date) -> dict:
        q = urllib.parse.urlencode({"project_id": self.project_id, "funnel_id": self.funnel_id, "from_date": since.isoformat(),
                                    "to_date": until.isoformat(), "unit": "day", "on": 'properties["gos_segment"]'})
        return _get(f"{self.base}?{q}", {"Authorization": self.auth, "Accept": "application/json"})

    @staticmethod
    def parse(payload: dict) -> list[dict]:
        rows = []
        for day, segments in payload.get("data", {}).items():
            for seg, steps in segments.items():
                if "|" not in seg:
                    continue
                market, device = seg.split("|", 1)
                for s in steps:
                    step = STEP_MAP.get(s.get("event") or s.get("step_label"))
                    if step:
                        rows.append({"day": day, "market": market, "device": device.lower(), "step": step, "users": int(s.get("count", 0))})
        return rows


class Clarity:
    """Rage clicks, dead clicks and scroll depth per page and device (OS). The API returns up to the last 3 days, so it
    runs daily."""
    URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"

    def __init__(self, token: str, market: str):
        self.token, self.market = token, market  # one Clarity project per market site

    def fetch(self, days: int = 1) -> list:
        q = urllib.parse.urlencode({"numOfDays": days, "dimension1": "OS", "dimension2": "URL"})
        return _get(f"{self.URL}?{q}", {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})

    def parse(self, payload: list, day: str, pages: dict[str, str]) -> list[dict]:
        """pages maps a URL prefix to the hub's page name, e.g. {"/checkout/payment": "/payment"}."""
        acc: dict[tuple[str, str], dict] = {}
        for metric in payload:
            name = metric.get("metricName")
            for info in metric.get("information", []):
                url = urllib.parse.urlparse(info.get("URL", "")).path
                page = next((v for k, v in pages.items() if url.startswith(k)), None)
                if not page:
                    continue
                dev = {"ios": "ios", "android": "android"}.get(str(info.get("OS", "")).lower(), "desktop")
                a = acc.setdefault((dev, page), {"sessions": 0, "rage_clicks": 0, "dead_clicks": 0, "scroll": []})
                n = int(float(info.get("sessionsCount", 0) or 0))
                if name == "Traffic":
                    a["sessions"] += n
                elif name == "RageClickCount":
                    a["rage_clicks"] += int(float(info.get("subTotal", 0) or 0))
                elif name == "DeadClickCount":
                    a["dead_clicks"] += int(float(info.get("subTotal", 0) or 0))
                elif name == "ScrollDepth":
                    a["scroll"].append(float(info.get("averageScrollDepth", 0) or 0))
        return [{"day": day, "market": self.market, "device": dev, "page": page, "sessions": a["sessions"], "rage_clicks": a["rage_clicks"],
                 "dead_clicks": a["dead_clicks"], "avg_scroll_pct": round(sum(a["scroll"]) / len(a["scroll"]), 1) if a["scroll"] else None,
                 "exits": 0} for (dev, page), a in acc.items()]


class HotjarSurvey:
    """Exit-survey answers ("What stopped you buying today?"), mapped to the hub's reasons by keyword."""
    REASONS = {"price": ("expensive", "price", "cost", "caro", "precio"), "sold_out": ("sold out", "agotado", "no tickets", "unavailable"),
               "delivery_or_date": ("date", "delivery", "fecha", "envío"), "trust": ("trust", "never heard", "scam", "confianza"),
               "payment_failed": ("payment", "card", "pago", "tarjeta"), "just_browsing": ("browsing", "looking", "mirando")}

    def __init__(self, client_id: str, client_secret: str, site_id: str, survey_id: str, market: str):
        self.cid, self.secret, self.site, self.survey, self.market = client_id, client_secret, site_id, survey_id, market

    def _token(self) -> str:
        data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.cid, "client_secret": self.secret}).encode()
        req = urllib.request.Request("https://api.hotjar.io/v1/oauth/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["access_token"]

    def fetch(self) -> list[dict]:
        tok, out, cursor = self._token(), [], ""
        while True:
            url = f"https://api.hotjar.io/v1/sites/{self.site}/surveys/{self.survey}/responses?limit=100" + (f"&cursor={cursor}" if cursor else "")
            page = _get(url, {"Authorization": f"Bearer {tok}"})
            out += page.get("results", [])
            cursor = page.get("next_cursor")
            if not cursor:
                return out

    def parse(self, results: list[dict]) -> list[dict]:
        counts: dict[tuple[str, str, str], int] = {}
        for r in results:
            day = str(r.get("created_time", ""))[:10]
            dev = {"phone": "mobile"}.get(r.get("device", ""), r.get("device", "") or "")
            text = " ".join(str(a.get("answer", "")) for a in r.get("answers", [])).lower()
            reason = next((k for k, words in self.REASONS.items() if any(w in text for w in words)), "other")
            counts[(day, dev, reason)] = counts.get((day, dev, reason), 0) + 1
        return [{"day": d, "market": self.market, "device": dev, "product_id": "", "reason": reason, "responses": n} for (d, dev, reason), n in counts.items()]
