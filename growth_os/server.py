"""Decision endpoint: Slack's Approve and Reject land here, and an approved action runs at once.

    growth-os serve --hub state/hub.sqlite --port 8787      # set http(s)://<host>/slack/actions as the Slack app's
                                                             # interactivity URL (behind HTTPS in production)

Every request is checked before anything happens:
  - Slack's signature (HMAC-SHA256 with SLACK_SIGNING_SECRET) and a timestamp under 5 minutes old, so nobody else can
    post decisions and old requests cannot be replayed
  - the Slack user must be in the hub's team table with the role the action needs (or leadership)
  - then the executor's own guardrails: kill switch, four eyes, budget caps, the adapter's limits
The reply goes back to the Slack message: what ran, what was blocked and why.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .actions import catalog, executor
from .hub import store


def verify(secret: str, ts: str, body: bytes, signature: str, now: float | None = None) -> bool:
    if not secret or not ts or not signature:
        return False
    try:
        if abs((now or time.time()) - int(ts)) > 300:
            return False
    except ValueError:
        return False
    mac = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature)


def handle(hub: Path, payload: dict, adapter) -> str:
    """Applies one Slack block action. Returns the text to post back."""
    user = payload.get("user", {}).get("id", "")
    act = (payload.get("actions") or [{}])[0]
    with store.connect(hub, read_only=True) as db:
        roles = [r[0] for r in db.execute("SELECT role FROM team WHERE person = ?", (user,))]
    if not roles:
        return f"<@{user}> is not in the team table, so cannot decide."
    if act.get("action_id") == "approve":
        rid = int(act["value"])
        with store.connect(hub, read_only=True) as db:
            need = db.execute("SELECT approver_role FROM recommendations WHERE id = ?", (rid,)).fetchone()
        role = need[0] if need and need[0] in roles else ("leadership" if "leadership" in roles else roles[0])
        try:
            executor.decide(hub, rid, True, user, role)
        except executor.Refused as e:
            return f"Not approved: {e}"
        ran = [r for r in executor.run_approved(hub, adapter) if r["id"] == rid]
        return f"#{rid} approved by <@{user}> as {catalog.ROLES[role]}. " + ("; ".join(f"{r['status']}: {r['detail']}" for r in ran) or "Nothing to execute (manual).")
    if act.get("action_id") == "reject":
        rid, reason = act["selected_option"]["value"].split("|", 1)
        try:
            executor.decide(hub, int(rid), False, user, roles[0], reason)
        except executor.Refused as e:
            return f"Not recorded: {e}"
        return f"#{rid} rejected by <@{user}>: {reason}. The next memo reads this."
    return "Unknown action."


def serve(hub: Path, port: int, adapter) -> None:
    secret = os.environ.get("SLACK_SIGNING_SECRET", "")

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            if self.path != "/slack/actions" or not verify(secret, self.headers.get("X-Slack-Request-Timestamp", ""), body,
                                                           self.headers.get("X-Slack-Signature", "")):
                self.send_response(401)
                self.end_headers()
                return
            payload = json.loads(urllib.parse.parse_qs(body.decode())["payload"][0])
            text = handle(hub, payload, adapter)
            self.send_response(200)
            self.end_headers()
            if payload.get("response_url", "").startswith("https://hooks.slack.com/"):
                req = urllib.request.Request(payload["response_url"], data=json.dumps({"text": text, "replace_original": False}).encode(),
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10).close()

        def log_message(self, *a):
            pass

    print(f"decision endpoint on :{port}/slack/actions (hub {hub})")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
