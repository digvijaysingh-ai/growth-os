"""Shared HTTPS + JSON helper for the connectors (standard library only)."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date

TIMEOUT = 30


class SourceError(RuntimeError):
    pass


def _request(url: str, *, data: dict | None = None, headers: dict | None = None, form: bool = False) -> dict:
    body = None
    hdrs = {"Accept": "application/json", "User-Agent": "growth-os/0.2", **(headers or {})}
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read()[:500].decode(errors="replace")
        raise SourceError(f"{e.code} from {urllib.parse.urlsplit(url).netloc}: {detail}") from None
    except urllib.error.URLError as e:
        raise SourceError(f"cannot reach {urllib.parse.urlsplit(url).netloc}: {e.reason}") from None


@dataclass
class Window:
    since: date
    until: date
