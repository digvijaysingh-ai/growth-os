"""The website's agent endpoint (api/agent.php): aggregates only, never personal data."""
from __future__ import annotations

import urllib.parse
from datetime import date

from ..config import Secrets
from .http import SourceError, Window, _request


class Site:
    """The site's api/agent.php: aggregates only, no personal data."""

    def __init__(self, s: Secrets):
        self.url = s.site_url
        self.headers = {"Authorization": f"Bearer {s.site_token}", "X-Agent-Token": s.site_token}

    def _call(self, op: str, params: dict | None = None, data: dict | None = None) -> dict:
        q = urllib.parse.urlencode({"op": op, **(params or {})})
        out = _request(f"{self.url}?{q}", data=data, headers=self.headers)
        if not out.get("ok"):
            raise SourceError(f"site {op}: {out}")
        return out

    def stats(self, w: Window) -> list[dict]:
        return self._call("stats", {"since": w.since.isoformat(), "until": w.until.isoformat()})["ads"]

    def funnel(self, w: Window) -> dict:
        """Website sessions, sections, clicks, anonymous lead rows and demo opens for the window."""
        return self._call("funnel", {"since": w.since.isoformat(), "until": w.until.isoformat()})

    def propose(self, actions: list[dict]) -> list[dict]:
        return self._call("propose", data={"actions": actions})["actions"]

    def approved(self) -> list[dict]:
        return self._call("decisions")["approved"]

    def actions(self, since: date) -> list[dict]:
        return self._call("actions", {"since": since.isoformat()})["actions"]

    def done(self, action_id: int, ok: bool, result: str) -> None:
        self._call("done", data={"id": action_id, "ok": ok, "result": result})

    def send_ads(self, ads: list[dict]) -> None:
        """The ad list for the dashboard's "Anuncio de Meta" dropdown, so Instant Form leads can be tagged."""
        self._call("ads", data={"ads": [{"id": a["id"], "name": a.get("name", ""), "status": a.get("effective_status", "")} for a in ads]})

    def send_report(self, subject: str, body: str) -> None:
        self._call("report", data={"subject": subject, "body": body})
