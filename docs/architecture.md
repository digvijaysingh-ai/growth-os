# Architecture

## Layers

| Layer | Code | Runs | Holds |
|---|---|---|---|
| Connectors | `growth_os/connectors/` | on demand | nothing; each returns plain dicts |
| Hub | `growth_os/hub/` (`schema.sql`, `sync.py`, `store.py`) | daily 06:30 | `state/hub.sqlite`: daily aggregates and joined views |
| Ads agent | `growth_os/agents/ads/` | hourly | proposals on the site, `state/decisions.jsonl` |
| Analyst | `growth_os/agents/analyst/` | Monday, or on demand | `reports/memo-<date>.md` and `.json`, including every query it ran |
| Reports | `growth_os/report/` | Monday | one email: memo + ads table |

Agents never call a vendor API directly. The ads agent uses the Meta and site connectors. The analyst only reads the hub, through a read-only connection and a SQL tool that accepts a single `SELECT`.

## Data flow

1. **Collection.** The website records cookieless events (page views, sections reached, scroll depth, engaged time, clicks, form start, error and submit) with the visit's UTM fields. Meta reports delivery per ad. The CRM stores lead stage and the time of each step.
2. **Sync.** `growth-os sync` re-reads the last 35 days from every source and replaces those days in the hub, so a sync is always safe to repeat. Lead stages keep changing after the day a lead arrives, and Meta revises recent numbers, which is why the window is re-read in full.
3. **Join.** Views do the joining once, so agents and people see the same numbers:
   - `v_ad_funnel`: spend → clicks → sessions → leads → qualified → won, per ad;
   - `v_funnel_daily`: the same steps per day, all channels;
   - `v_landing`: landing page × channel × device, from visit to form submit;
   - `v_pipeline`: lead stages and the time each step takes.
4. **Decide.** The ads agent applies rules to live data every hour. The analyst reads the hub weekly. Both produce proposals; people decide.

## Attribution without cookies

- **Website ads:** the ad's URL carries `utm_content={{ad.id}}`. The site stores it on the visit and on the lead. Nothing is stored on the visitor's device.
- **Instant Form ads:** people never visit the site, so the lead count comes from Meta (`onsite_conversion.lead_grouped`). When the owner enters such a lead in the CRM, they pick the ad from a dropdown the ads agent keeps up to date, so qualified and won still count per ad.
- **One ad, one source:** an ad sends people either to a form or to the website, so its leads are `max(meta_form_leads, site_leads)`. Nothing is counted twice.

## Why SQLite

One file, no server, zero cost, and fast enough for years of one business's daily aggregates.

**Moving to a warehouse (BigQuery, Snowflake, Postgres) changes four things, not one:**
1. `hub/store.py`: the connection.
2. `run_sql` in the analyst: the read-only guard becomes a read-only service account, plus a cap on bytes scanned per query.
3. `schema.sql` views: a few SQLite functions (`GROUP_CONCAT`, `julianday`) need dialect equivalents. Better, the views become dbt models.
4. The analyst's prompt names the SQL dialect.

The agents, tools, memo schema, evals and governance stay the same.

## Cost

| Part | Cost |
|---|---|
| Hub, ads agent, sync | none beyond the machine it runs on |
| Analyst memo | about 0.60 USD (single business), 1–2 USD (10 markets or a real-data case), claude-opus-5-5 |
| Ads report summary paragraph | a few cents a week |
