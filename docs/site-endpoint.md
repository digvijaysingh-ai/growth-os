# The website contract

Growth OS talks to the website through one authenticated endpoint. The pilot implements it in about 250 lines of PHP over SQLite. Any stack can implement it, and it never returns personal data.

**Auth:** `Authorization: Bearer <token>` (or `X-Agent-Token: <token>` where a host strips `Authorization`). Compare the token in constant time, and rate-limit bad tokens.

| Operation | Method | Returns / does |
|---|---|---|
| `?op=stats&since&until` | GET | Per ad (`utm_content`): `visits`, `form_starts`, `engaged_s`, `leads`, `qualified`, `won` |
| `?op=funnel&since&until` | GET | `sessions[]`, `sections[]`, `clicks[]`, `leads[]` (anonymous rows), `demos[]` (shapes below) |
| `?op=propose` | POST `{actions:[{ad_id, ad_name, campaign, action:"pause", rule, reason, metrics}]}` | Queues proposals for approval; refuses any action other than `pause`; one open proposal per ad |
| `?op=decisions` | GET | Approved proposals not yet carried out |
| `?op=actions&since` | GET | Every proposal since a day, and its status |
| `?op=done` | POST `{id, ok, result}` | Records what happened in Meta |
| `?op=ads` | POST `{ads:[{id, name, status}]}` | Current ad list, for tagging hand-entered Instant Form leads |
| `?op=report` | POST `{subject, body}` | Emails the weekly report to the owner |

## `op=funnel` shapes

```jsonc
{
  "sessions": [{ "day": "2026-10-30", "landing": "/", "channel": "paid:meta", "ad_id": "120211…", "device": "Móvil",
                 "sessions": 41, "bounces": 18, "engaged_s": 1520, "scroll_25": 30, "scroll_50": 19, "scroll_75": 9, "scroll_100": 4,
                 "form_starts": 3, "form_errors": 2, "form_submits": 1 }],
  "sections": [{ "day": "…", "path": "/", "section": "precios", "sessions": 12 }],
  "clicks":   [{ "day": "…", "path": "/", "label": "Pide tu demo", "target": "/#demo", "sessions": 7 }],
  "leads":    [{ "day": "…", "origin": "web", "utm_source": "meta", "utm_medium": "paid", "ad_id": "…", "sector": "bar",
                 "stage": "Demo enviada", "lang": "es", "wants_booking": 0, "est_value": 500,
                 "hours_to_contact": 1.5, "hours_to_demo": 30.2, "days_to_win": null }],
  "demos":    [{ "day": "…", "demos_opened": 2, "demo_sessions": 3, "demo_engaged_s": 410 }]
}
```

`channel` is `paid:<utm_source>` when the visit carried UTM fields; otherwise `search`, `social`, `referral` or `direct` from the referrer's host. A session counts as a bounce when it has one page view, under 10 seconds engaged and no form start.
