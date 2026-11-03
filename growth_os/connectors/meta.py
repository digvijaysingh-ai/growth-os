"""Meta Marketing API: delivery data per ad, ad status, and pausing one ad. Nothing else, on purpose."""
from __future__ import annotations

import json
import urllib.parse

from ..config import Secrets
from .http import SourceError, Window, _request


class Meta:
    """Read insights and ad status; pause or resume one ad. Nothing else is implemented on purpose."""

    def __init__(self, s: Secrets):
        self.base = f"https://graph.facebook.com/{s.meta_version}"
        self.token = s.meta_token
        self.account = s.meta_account

    def _get_all(self, path: str, params: dict) -> list[dict]:
        url = f"{self.base}/{path}?" + urllib.parse.urlencode({**params, "access_token": self.token})
        rows: list[dict] = []
        while url:
            page = _request(url)
            rows += page.get("data", [])
            url = page.get("paging", {}).get("next", "")
        return rows

    def insights(self, w: Window) -> list[dict]:
        return self._get_all(f"{self.account}/insights", {
            "level": "ad",
            "fields": "ad_id,ad_name,campaign_id,campaign_name,spend,impressions,reach,frequency,inline_link_clicks,actions",
            "time_range": json.dumps({"since": w.since.isoformat(), "until": w.until.isoformat()}),
            "limit": 200,
        })

    def insights_daily(self, w: Window) -> list[dict]:
        """One row per ad per day, for the hub."""
        return self._get_all(f"{self.account}/insights", {
            "level": "ad",
            "time_increment": 1,
            "fields": "ad_id,campaign_name,spend,impressions,reach,inline_link_clicks,actions",
            "time_range": json.dumps({"since": w.since.isoformat(), "until": w.until.isoformat()}),
            "limit": 500,
        })

    def ads(self) -> list[dict]:
        return self._get_all(f"{self.account}/ads", {"fields": "id,name,effective_status,campaign_id", "limit": 200})

    def pause(self, ad_id: str) -> dict:
        return self.set_status(ad_id, "PAUSED")

    def set_status(self, ad_id: str, status: str) -> dict:
        """PAUSED or ACTIVE, nothing else: the executor's MetaAdapter uses it for approved pauses and their rollback."""
        if status not in ("PAUSED", "ACTIVE"):
            raise ValueError(status)
        return _request(f"{self.base}/{ad_id}", data={"status": status, "access_token": self.token}, form=True)
