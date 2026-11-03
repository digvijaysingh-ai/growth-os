-- Growth OS hub: one table per source, all daily aggregates, then views that join them.
-- Nothing here identifies a person: no names, contact details, visitor keys or free text.

CREATE TABLE IF NOT EXISTS ads (
    ad_id TEXT PRIMARY KEY,
    ad_name TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

-- Meta delivery per ad per day
CREATE TABLE IF NOT EXISTS ad_daily (
    day TEXT NOT NULL,
    ad_id TEXT NOT NULL,
    campaign TEXT NOT NULL DEFAULT '',
    spend REAL NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    reach INTEGER NOT NULL DEFAULT 0,
    link_clicks INTEGER NOT NULL DEFAULT 0,
    form_leads INTEGER NOT NULL DEFAULT 0,          -- Instant Form submissions, as Meta counts them
    market TEXT NOT NULL DEFAULT '',                -- country, region or brand, for multi-market accounts
    platform TEXT NOT NULL DEFAULT 'meta',          -- meta, google, tiktok
    creative TEXT NOT NULL DEFAULT '',
    frequency REAL,                                 -- average times each person saw the ad
    platform_purchases INTEGER, platform_revenue REAL,   -- what the platform itself claims; compare with first-party sales
    line TEXT NOT NULL DEFAULT '',                  -- product line, where the business has several
    PRIMARY KEY (day, ad_id)
);

-- Website sessions per day x landing page x channel x ad x device
CREATE TABLE IF NOT EXISTS web_sessions (
    day TEXT NOT NULL,
    landing TEXT NOT NULL,
    channel TEXT NOT NULL,                          -- paid:meta, search, social, referral, direct
    ad_id TEXT NOT NULL DEFAULT '',
    device TEXT NOT NULL DEFAULT '',
    sessions INTEGER NOT NULL,
    bounces INTEGER NOT NULL,
    engaged_s INTEGER NOT NULL,
    scroll_25 INTEGER NOT NULL, scroll_50 INTEGER NOT NULL, scroll_75 INTEGER NOT NULL, scroll_100 INTEGER NOT NULL,
    form_starts INTEGER NOT NULL,
    form_errors INTEGER NOT NULL,
    form_submits INTEGER NOT NULL,
    market TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (day, market, landing, channel, ad_id, device)
);

CREATE TABLE IF NOT EXISTS web_sections (
    day TEXT NOT NULL, path TEXT NOT NULL, section TEXT NOT NULL, sessions INTEGER NOT NULL,
    PRIMARY KEY (day, path, section)
);

CREATE TABLE IF NOT EXISTS web_clicks (
    day TEXT NOT NULL, path TEXT NOT NULL, label TEXT NOT NULL, target TEXT NOT NULL, sessions INTEGER NOT NULL,
    PRIMARY KEY (day, path, label, target)
);

-- one anonymous row per lead: source, how far it got and how fast
CREATE TABLE IF NOT EXISTS leads (
    day TEXT NOT NULL,
    origin TEXT NOT NULL,                           -- web form, manual (calls, walk-ins, Instant Forms), manychat
    utm_source TEXT NOT NULL DEFAULT '',
    utm_medium TEXT NOT NULL DEFAULT '',
    ad_id TEXT NOT NULL DEFAULT '',
    sector TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL,
    lang TEXT NOT NULL DEFAULT '',
    wants_booking INTEGER NOT NULL DEFAULT 0,
    est_value REAL NOT NULL DEFAULT 0,
    hours_to_contact REAL,
    hours_to_demo REAL,
    days_to_win REAL,
    -- optional, for richer CRMs (all anonymous: ids, never names)
    landing TEXT,                                   -- landing page the lead came through
    owner TEXT,                                     -- sales rep who closed it
    sdr TEXT,                                       -- rep who qualified it
    lead_type TEXT,
    profile TEXT,                                   -- behaviour profile assigned by sales
    business_type TEXT,
    declared_revenue REAL,                          -- what the lead said it turns over
    value_after_90d REAL,                           -- revenue the customer generated in its first 90 days
    market TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_leads_day ON leads(day);

-- paid social by audience segment (campaign x age x gender x interest)
CREATE TABLE IF NOT EXISTS ad_segments (
    campaign TEXT NOT NULL, ad_id TEXT NOT NULL, age TEXT NOT NULL, gender TEXT NOT NULL, interest TEXT NOT NULL,
    impressions INTEGER NOT NULL, clicks INTEGER NOT NULL, spend REAL NOT NULL,
    conversions INTEGER NOT NULL,                   -- people who enquired
    approved INTEGER NOT NULL,                      -- people who bought
    PRIMARY KEY (ad_id)
);

CREATE TABLE IF NOT EXISTS demos (
    day TEXT PRIMARY KEY, demos_opened INTEGER NOT NULL, demo_sessions INTEGER NOT NULL, demo_engaged_s INTEGER NOT NULL
);

-- what the ads agent proposed and what the owner decided
CREATE TABLE IF NOT EXISTS agent_actions (
    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, ad_id TEXT NOT NULL, ad_name TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL, rule TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, result TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sync_log (
    ts TEXT NOT NULL, source TEXT NOT NULL, since TEXT NOT NULL, until TEXT NOT NULL, rows INTEGER NOT NULL, note TEXT NOT NULL DEFAULT ''
);

-- ---------- views the analyst queries ----------

DROP VIEW IF EXISTS v_qualified;
CREATE VIEW v_qualified AS
SELECT *, CASE WHEN stage IN ('Demo enviada', 'Negociando', 'Ganado') OR hours_to_demo IS NOT NULL THEN 1 ELSE 0 END AS qualified,
       CASE WHEN stage = 'Ganado' THEN 1 ELSE 0 END AS won
FROM leads;

-- the whole funnel per day, every channel
DROP VIEW IF EXISTS v_funnel_daily;
CREATE VIEW v_funnel_daily AS
WITH w AS (SELECT day, SUM(sessions) AS sessions, SUM(bounces) AS bounces, SUM(engaged_s) AS engaged_s, SUM(scroll_50) AS scroll_50,
                  SUM(form_starts) AS form_starts, SUM(form_errors) AS form_errors, SUM(form_submits) AS form_submits FROM web_sessions GROUP BY day),
     a AS (SELECT day, SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(link_clicks) AS link_clicks, SUM(form_leads) AS meta_form_leads FROM ad_daily GROUP BY day),
     l AS (SELECT day, COUNT(*) AS leads, SUM(qualified) AS qualified, SUM(won) AS won FROM v_qualified GROUP BY day),
     d AS (SELECT day FROM w UNION SELECT day FROM a UNION SELECT day FROM l)
SELECT d.day, COALESCE(a.spend, 0) AS spend, COALESCE(a.impressions, 0) AS impressions, COALESCE(a.link_clicks, 0) AS link_clicks,
       COALESCE(w.sessions, 0) AS sessions, COALESCE(w.bounces, 0) AS bounces, COALESCE(w.engaged_s, 0) AS engaged_s, COALESCE(w.scroll_50, 0) AS scroll_50,
       COALESCE(w.form_starts, 0) AS form_starts, COALESCE(w.form_errors, 0) AS form_errors, COALESCE(w.form_submits, 0) AS form_submits,
       COALESCE(a.meta_form_leads, 0) AS meta_form_leads,
       COALESCE(l.leads, 0) AS leads, COALESCE(l.qualified, 0) AS qualified, COALESCE(l.won, 0) AS won
FROM d LEFT JOIN w USING (day) LEFT JOIN a USING (day) LEFT JOIN l USING (day);

-- each ad end to end: spend -> clicks -> sessions -> leads -> qualified
-- leads = Meta's Instant Form count or the website's leads for that ad, whichever saw them (an ad uses one or the other)
DROP VIEW IF EXISTS v_ad_funnel;
CREATE VIEW v_ad_funnel AS
WITH a AS (SELECT ad_id, MAX(campaign) AS campaign, MIN(day) AS first_day, MAX(day) AS last_day, SUM(spend) AS spend, SUM(impressions) AS impressions,
                  SUM(link_clicks) AS link_clicks, SUM(form_leads) AS meta_form_leads FROM ad_daily GROUP BY ad_id),
     w AS (SELECT ad_id, SUM(sessions) AS sessions, SUM(engaged_s) AS engaged_s, SUM(form_starts) AS form_starts, SUM(form_submits) AS form_submits
           FROM web_sessions WHERE ad_id != '' GROUP BY ad_id),
     l AS (SELECT ad_id, COUNT(*) AS site_leads, SUM(qualified) AS qualified, SUM(won) AS won FROM v_qualified WHERE ad_id != '' GROUP BY ad_id)
SELECT a.ad_id, COALESCE(ads.ad_name, a.ad_id) AS ad_name, a.campaign, COALESCE(ads.status, '') AS status, a.first_day, a.last_day,
       a.spend, a.impressions, a.link_clicks, COALESCE(w.sessions, 0) AS sessions, COALESCE(w.engaged_s, 0) AS engaged_s,
       COALESCE(w.form_starts, 0) AS form_starts, a.meta_form_leads, COALESCE(l.site_leads, 0) AS site_leads,
       MAX(a.meta_form_leads, COALESCE(l.site_leads, 0)) AS leads, COALESCE(l.qualified, 0) AS qualified, COALESCE(l.won, 0) AS won,
       ROUND(a.spend / NULLIF(MAX(a.meta_form_leads, COALESCE(l.site_leads, 0)), 0), 2) AS cost_per_lead,
       ROUND(a.spend / NULLIF(COALESCE(l.qualified, 0), 0), 2) AS cost_per_qualified
FROM a LEFT JOIN ads USING (ad_id) LEFT JOIN w USING (ad_id) LEFT JOIN l USING (ad_id);

-- channels and landing pages: where visits come from and which pages turn them into form starts
DROP VIEW IF EXISTS v_landing;
CREATE VIEW v_landing AS
SELECT landing, channel, device, SUM(sessions) AS sessions, SUM(bounces) AS bounces, ROUND(1.0 * SUM(engaged_s) / NULLIF(SUM(sessions), 0), 1) AS engaged_s_per_session,
       SUM(scroll_50) AS reached_half, SUM(form_starts) AS form_starts, SUM(form_errors) AS form_errors, SUM(form_submits) AS form_submits
FROM web_sessions GROUP BY landing, channel, device;

-- the sales pipeline: how many leads reach each step and how long each step takes
DROP VIEW IF EXISTS v_pipeline;
CREATE VIEW v_pipeline AS
SELECT origin, utm_source, sector, COUNT(*) AS leads, SUM(hours_to_contact IS NOT NULL) AS contacted, SUM(qualified) AS demo_sent, SUM(won) AS won,
       ROUND(AVG(hours_to_contact), 1) AS avg_hours_to_contact, ROUND(AVG(hours_to_demo), 1) AS avg_hours_to_demo, ROUND(AVG(days_to_win), 1) AS avg_days_to_win,
       SUM(CASE WHEN won = 1 THEN est_value ELSE 0 END) AS won_value
FROM v_qualified GROUP BY origin, utm_source, sector;

-- lead sources end to end: volume, close rate, speed and the value of what was won
DROP VIEW IF EXISTS v_lead_channels;
CREATE VIEW v_lead_channels AS
SELECT COALESCE(NULLIF(utm_source, ''), '(none)') AS channel, COUNT(*) AS leads, SUM(won) AS won,
       ROUND(100.0 * SUM(won) / COUNT(*), 2) AS close_rate_pct,
       ROUND(AVG(days_to_win), 1) AS avg_days_to_win,
       SUM(value_after_90d IS NOT NULL) AS won_with_90d_data,
       ROUND(SUM(value_after_90d), 0) AS value_after_90d,
       ROUND(AVG(value_after_90d), 1) AS avg_value_per_won_customer   -- over won customers whose 90 days are fully in the data
FROM v_qualified GROUP BY channel;

DROP VIEW IF EXISTS v_lead_landing;
CREATE VIEW v_lead_landing AS
SELECT landing, COUNT(*) AS leads, SUM(won) AS won, ROUND(100.0 * SUM(won) / COUNT(*), 2) AS close_rate_pct,
       GROUP_CONCAT(DISTINCT utm_source) AS channels
FROM v_qualified WHERE landing IS NOT NULL AND landing != '' GROUP BY landing;

DROP VIEW IF EXISTS v_owners;
CREATE VIEW v_owners AS
SELECT owner, COUNT(*) AS won, ROUND(AVG(days_to_win), 1) AS avg_days_to_win,
       SUM(value_after_90d IS NOT NULL) AS won_with_90d_data, ROUND(SUM(value_after_90d), 0) AS value_after_90d,
       SUM(value_after_90d > 0) AS customers_selling_within_90d
FROM leads WHERE owner IS NOT NULL AND owner != '' GROUP BY owner;

DROP VIEW IF EXISTS v_ad_segments;
CREATE VIEW v_ad_segments AS
SELECT campaign, age, gender, interest, COUNT(*) AS ads, SUM(impressions) AS impressions, SUM(clicks) AS clicks, ROUND(SUM(spend), 2) AS spend,
       SUM(conversions) AS conversions, SUM(approved) AS approved,
       ROUND(100.0 * SUM(clicks) / NULLIF(SUM(impressions), 0), 3) AS ctr_pct,
       ROUND(SUM(spend) / NULLIF(SUM(conversions), 0), 2) AS cost_per_conversion,
       ROUND(SUM(spend) / NULLIF(SUM(approved), 0), 2) AS cost_per_approved
FROM ad_segments GROUP BY campaign, age, gender, interest;

-- ---------- listening ----------
-- one row per classified item: labels and an English paraphrase only, never the original text or its author
CREATE TABLE IF NOT EXISTS voice_items (
    item_id TEXT PRIMARY KEY,                       -- hash of the source id
    day TEXT NOT NULL, source TEXT NOT NULL, rating INTEGER, sentiment TEXT NOT NULL,
    segment TEXT NOT NULL DEFAULT '',               -- e.g. the acquisition channel of the merchant reviewed
    category TEXT NOT NULL DEFAULT '', pain_point TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS voice_themes (item_id TEXT NOT NULL, theme TEXT NOT NULL, PRIMARY KEY (item_id, theme));

DROP VIEW IF EXISTS v_voice_themes;
CREATE VIEW v_voice_themes AS
SELECT source, t.theme, COUNT(*) AS items, ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM voice_items v2 WHERE v2.source = v.source), 1) AS share_pct,
       ROUND(AVG(rating), 2) AS avg_rating, SUM(sentiment = 'negative') AS negative
FROM voice_themes t JOIN voice_items v USING (item_id) GROUP BY source, t.theme;

DROP VIEW IF EXISTS v_voice_by_segment;
CREATE VIEW v_voice_by_segment AS
SELECT segment, COUNT(*) AS items, ROUND(AVG(rating), 2) AS avg_rating, SUM(sentiment = 'negative') AS negative,
       ROUND(100.0 * SUM(sentiment = 'negative') / COUNT(*), 1) AS negative_pct,
       SUM(item_id IN (SELECT item_id FROM voice_themes WHERE theme IN ('late_delivery', 'not_delivered'))) AS delivery_complaints,
       SUM(item_id IN (SELECT item_id FROM voice_themes WHERE theme IN ('damaged_or_defective', 'poor_quality', 'not_as_described', 'wrong_or_missing_item'))) AS product_complaints
FROM voice_items GROUP BY segment;

-- multi-market accounts: the whole funnel per market and day
DROP VIEW IF EXISTS v_market_daily;
CREATE VIEW v_market_daily AS
WITH w AS (SELECT market, day, SUM(sessions) AS sessions, SUM(form_starts) AS form_starts, SUM(form_errors) AS form_errors, SUM(form_submits) AS form_submits FROM web_sessions GROUP BY market, day),
     a AS (SELECT market, day, SUM(spend) AS spend, SUM(link_clicks) AS link_clicks FROM ad_daily GROUP BY market, day),
     l AS (SELECT market, day, COUNT(*) AS leads, SUM(qualified) AS qualified, SUM(won) AS won, AVG(hours_to_contact) AS avg_hours_to_contact FROM v_qualified GROUP BY market, day),
     k AS (SELECT market, day FROM w UNION SELECT market, day FROM a UNION SELECT market, day FROM l)
SELECT k.market, k.day, COALESCE(a.spend, 0) AS spend, COALESCE(a.link_clicks, 0) AS link_clicks, COALESCE(w.sessions, 0) AS sessions,
       COALESCE(w.form_starts, 0) AS form_starts, COALESCE(w.form_errors, 0) AS form_errors, COALESCE(w.form_submits, 0) AS form_submits,
       COALESCE(l.leads, 0) AS leads, COALESCE(l.qualified, 0) AS qualified, COALESCE(l.won, 0) AS won, l.avg_hours_to_contact
FROM k LEFT JOIN w USING (market, day) LEFT JOIN a USING (market, day) LEFT JOIN l USING (market, day);

-- ---------- AI visibility ----------
CREATE TABLE IF NOT EXISTS ai_answers (
    answer_id TEXT PRIMARY KEY, day TEXT NOT NULL, assistant TEXT NOT NULL, question_id TEXT NOT NULL, question TEXT NOT NULL,
    branded INTEGER NOT NULL DEFAULT 0,             -- 1 if the question names the brand itself
    run INTEGER NOT NULL, answer TEXT NOT NULL, stop TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ai_mentions (answer_id TEXT NOT NULL, brand TEXT NOT NULL, mentioned INTEGER NOT NULL, rank INTEGER, cited INTEGER NOT NULL,
    PRIMARY KEY (answer_id, brand));
CREATE TABLE IF NOT EXISTS ai_citations (answer_id TEXT NOT NULL, domain TEXT NOT NULL, PRIMARY KEY (answer_id, domain));

-- share of voice in unbranded questions: how often each brand comes up when buyers don't name anyone
DROP VIEW IF EXISTS v_ai_share_of_voice;
CREATE VIEW v_ai_share_of_voice AS
SELECT a.day, a.assistant, m.brand, COUNT(*) AS answers, SUM(m.mentioned) AS mentioned,
       ROUND(100.0 * SUM(m.mentioned) / COUNT(*), 1) AS mention_rate_pct,
       SUM(m.rank = 1) AS mentioned_first, ROUND(AVG(m.rank), 2) AS avg_rank_when_mentioned, SUM(m.cited) AS own_site_cited
FROM ai_mentions m JOIN ai_answers a USING (answer_id) WHERE a.branded = 0 GROUP BY a.day, a.assistant, m.brand;

DROP VIEW IF EXISTS v_ai_cited_sites;
CREATE VIEW v_ai_cited_sites AS
SELECT a.day, c.domain, COUNT(DISTINCT c.answer_id) AS answers_citing FROM ai_citations c JOIN ai_answers a USING (answer_id) GROUP BY a.day, c.domain;

-- every company the answer named (found by a model), to surface competitors missing from the tracked list
CREATE TABLE IF NOT EXISTS ai_discovered (answer_id TEXT NOT NULL, name TEXT NOT NULL, PRIMARY KEY (answer_id, name));

-- ---------- B2C commerce: revenue, platforms, products, budgets ----------
-- ad_daily gains platform-level fields (platform, creative, frequency, platform-reported purchases and revenue) via migration

-- first-party sales by day x market x channel x ad x device (last click from the visit's UTM fields)
CREATE TABLE IF NOT EXISTS sales_daily (
    day TEXT NOT NULL, market TEXT NOT NULL,
    line TEXT NOT NULL DEFAULT '',                  -- product line, where the business has several
    channel TEXT NOT NULL,                          -- paid:<channel>, email, sms, organic / organic_search, organic_social, direct
    ad_id TEXT NOT NULL DEFAULT '', device TEXT NOT NULL DEFAULT '',   -- ios, android, desktop
    sessions INTEGER NOT NULL, checkouts INTEGER NOT NULL, orders INTEGER NOT NULL, revenue REAL NOT NULL, new_customers INTEGER NOT NULL,
    PRIMARY KEY (day, market, line, channel, ad_id, device)
);
CREATE TABLE IF NOT EXISTS markets (market TEXT PRIMARY KEY, launched_on TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'EUR');
-- time-limited products: they must sell before end_day
CREATE TABLE IF NOT EXISTS products (product_id TEXT PRIMARY KEY, market TEXT NOT NULL, line TEXT NOT NULL DEFAULT '', name TEXT NOT NULL, launch_day TEXT NOT NULL,
    end_day TEXT NOT NULL, capacity INTEGER NOT NULL, price REAL NOT NULL);
CREATE TABLE IF NOT EXISTS product_daily (day TEXT NOT NULL, product_id TEXT NOT NULL, units INTEGER NOT NULL, revenue REAL NOT NULL, PRIMARY KEY (day, product_id));
CREATE TABLE IF NOT EXISTS budgets (market TEXT NOT NULL, month TEXT NOT NULL, budget REAL NOT NULL, PRIMARY KEY (market, month));

-- each market per ISO week: spend, revenue (all channels and paid only), orders, ROAS, CAC
DROP VIEW IF EXISTS v_market_weekly;
CREATE VIEW v_market_weekly AS
WITH s AS (SELECT market, date(day, 'weekday 0', '-6 days') AS week, SUM(revenue) AS revenue, SUM(CASE WHEN channel LIKE 'paid:%' THEN revenue ELSE 0 END) AS paid_revenue,
                  SUM(orders) AS orders, SUM(new_customers) AS new_customers, SUM(CASE WHEN channel LIKE 'paid:%' THEN new_customers ELSE 0 END) AS paid_new_customers, SUM(sessions) AS sessions
           FROM sales_daily GROUP BY market, week),
     a AS (SELECT market, date(day, 'weekday 0', '-6 days') AS week, SUM(spend) AS spend FROM ad_daily GROUP BY market, week)
SELECT s.market, s.week, ROUND(COALESCE(a.spend, 0), 2) AS spend, ROUND(s.revenue, 2) AS revenue, ROUND(s.paid_revenue, 2) AS paid_revenue, s.orders, s.new_customers,
       s.sessions, ROUND(s.paid_revenue / NULLIF(a.spend, 0), 2) AS paid_roas, ROUND(a.spend / NULLIF(s.paid_new_customers, 0), 2) AS paid_cac
FROM s LEFT JOIN a USING (market, week);

-- each ad (creative) per week: delivery from the platform, revenue from first-party sales
DROP VIEW IF EXISTS v_creative_weekly;
CREATE VIEW v_creative_weekly AS
WITH a AS (SELECT ad_id, MAX(market) AS market, MAX(platform) AS platform, MAX(creative) AS creative, date(day, 'weekday 0', '-6 days') AS week,
                  SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(link_clicks) AS clicks, AVG(frequency) AS frequency, SUM(platform_revenue) AS platform_revenue
           FROM ad_daily GROUP BY ad_id, week),
     s AS (SELECT ad_id, date(day, 'weekday 0', '-6 days') AS week, SUM(orders) AS orders, SUM(revenue) AS revenue FROM sales_daily WHERE ad_id != '' GROUP BY ad_id, week)
SELECT a.ad_id, a.market, a.platform, a.creative, a.week, ROUND(a.spend, 2) AS spend, a.impressions, a.clicks,
       ROUND(100.0 * a.clicks / NULLIF(a.impressions, 0), 3) AS ctr_pct, ROUND(a.frequency, 2) AS frequency,
       COALESCE(s.orders, 0) AS orders, ROUND(COALESCE(s.revenue, 0), 2) AS revenue, ROUND(COALESCE(s.revenue, 0) / NULLIF(a.spend, 0), 2) AS roas,
       ROUND(a.platform_revenue, 2) AS platform_reported_revenue
FROM a LEFT JOIN s USING (ad_id, week);

-- revenue this year against the same ISO week last year
DROP VIEW IF EXISTS v_market_yoy;
CREATE VIEW v_market_yoy AS
SELECT t.market, t.week, t.revenue, l.revenue AS revenue_last_year, ROUND(100.0 * (t.revenue - l.revenue) / NULLIF(l.revenue, 0), 1) AS yoy_pct
FROM v_market_weekly t LEFT JOIN v_market_weekly l ON l.market = t.market AND l.week = date(t.week, '-364 days');

-- time-limited products: how much has sold against how much of the selling window has passed
DROP VIEW IF EXISTS v_product_pacing;
CREATE VIEW v_product_pacing AS
WITH asof AS (SELECT MAX(day) AS d FROM product_daily), sold AS (SELECT product_id, SUM(units) AS units, SUM(revenue) AS revenue FROM product_daily GROUP BY product_id)
SELECT p.product_id, p.market, p.name, p.launch_day, p.end_day, p.capacity, COALESCE(s.units, 0) AS sold, ROUND(COALESCE(s.revenue, 0), 2) AS revenue,
       ROUND(100.0 * COALESCE(s.units, 0) / p.capacity, 1) AS sold_pct,
       ROUND(100.0 * (julianday(asof.d) - julianday(p.launch_day)) / NULLIF(julianday(p.end_day) - julianday(p.launch_day), 0), 1) AS window_elapsed_pct,
       CAST(julianday(p.end_day) - julianday(asof.d) AS INTEGER) AS days_left, ROUND((p.capacity - COALESCE(s.units, 0)) * p.price, 2) AS unsold_value
FROM products p, asof LEFT JOIN sold s USING (product_id) WHERE p.end_day > asof.d AND p.launch_day <= asof.d;

-- this month's budget against spend so far
DROP VIEW IF EXISTS v_budget_pacing;
CREATE VIEW v_budget_pacing AS
WITH asof AS (SELECT MAX(day) AS d FROM ad_daily)
SELECT b.market, b.month, b.budget, ROUND(SUM(a.spend), 2) AS spent, ROUND(100.0 * SUM(a.spend) / b.budget, 1) AS spent_pct,
       ROUND(100.0 * CAST(strftime('%d', asof.d) AS REAL) / CAST(strftime('%d', date(b.month || '-01', '+1 month', '-1 day')) AS REAL), 1) AS month_elapsed_pct
FROM budgets b, asof JOIN ad_daily a ON a.market = b.market AND substr(a.day, 1, 7) = b.month WHERE b.month = substr(asof.d, 1, 7) GROUP BY b.market, b.month;

-- markets opened in the last year: revenue by week since launch, to compare a new market with earlier ones at the same age
DROP VIEW IF EXISTS v_launch_cohorts;
CREATE VIEW v_launch_cohorts AS
SELECT w.market, m.launched_on, CAST((julianday(w.week) - julianday(m.launched_on)) / 7 AS INTEGER) AS weeks_since_launch, w.revenue, w.spend, w.orders
FROM v_market_weekly w JOIN markets m USING (market) WHERE julianday(w.week) >= julianday(m.launched_on) AND m.launched_on >= date((SELECT MAX(day) FROM sales_daily), '-450 days');

-- ---------- recommendation tracker: every recommendation, who decided, and whether its metric moved ----------
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, memo_date TEXT NOT NULL, rank INTEGER NOT NULL, action TEXT NOT NULL, confidence TEXT NOT NULL,
    expected_impact TEXT NOT NULL DEFAULT '', metric_sql TEXT NOT NULL, direction TEXT NOT NULL, check_after_days INTEGER NOT NULL,
    baseline REAL, baseline_at TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',        -- proposed, accepted, rejected, done
    decided_by TEXT NOT NULL DEFAULT '', decided_at TEXT NOT NULL DEFAULT '',
    outcome REAL, outcome_at TEXT, verdict TEXT NOT NULL DEFAULT '',  -- moved as hoped, no change, moved the wrong way
    -- the action that carries it out (actions/catalog.py), who must approve it, and what happened
    exec_type TEXT NOT NULL DEFAULT 'manual', exec_target TEXT NOT NULL DEFAULT '', exec_to TEXT NOT NULL DEFAULT '',
    exec_pct REAL NOT NULL DEFAULT 0, exec_note TEXT NOT NULL DEFAULT '',
    risk TEXT NOT NULL DEFAULT 'low', approver_role TEXT NOT NULL DEFAULT 'growth_manager',
    reject_reason TEXT NOT NULL DEFAULT '', executed_at TEXT NOT NULL DEFAULT '',
    counterfactual REAL                             -- simulation only: the metric had nobody acted
);

-- every action the system carried out, blocked or undid: the audit log
CREATE TABLE IF NOT EXISTS action_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, rec_id INTEGER, kind TEXT NOT NULL, target TEXT NOT NULL DEFAULT '',
    params TEXT NOT NULL DEFAULT '{}', adapter TEXT NOT NULL, status TEXT NOT NULL,   -- executed, failed, blocked, rolled_back
    before TEXT NOT NULL DEFAULT '{}', after TEXT NOT NULL DEFAULT '{}', detail TEXT NOT NULL DEFAULT '',
    approved_by TEXT NOT NULL DEFAULT '', ts TEXT NOT NULL
);

-- sandbox ad account: what the executor changed (the simulated market reads it)
CREATE TABLE IF NOT EXISTS account_state (
    ad_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'ACTIVE', budget_mult REAL NOT NULL DEFAULT 1.0, updated_at TEXT NOT NULL DEFAULT ''
);

-- work handed to people and tools: tickets, A/B tests, email flows, notifications
CREATE TABLE IF NOT EXISTS work_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, rec_id INTEGER, kind TEXT NOT NULL, target TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open', opened_on TEXT NOT NULL, closed_on TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT ''
);

-- ---------------------------------------------------------------------------------------------------------------
-- Behaviour data: why people who came did not buy. Shaped like the exports of a product-analytics tool (Mixpanel
-- funnels), a session-behaviour tool (Hotjar heatmaps and recordings) and an on-site exit survey.
-- ---------------------------------------------------------------------------------------------------------------

-- users reaching each funnel step per day, market and device. Steps in order: session_start, view_product,
-- add_to_cart, begin_checkout, add_payment, purchase
CREATE TABLE IF NOT EXISTS events_daily (
    day TEXT NOT NULL, market TEXT NOT NULL, device TEXT NOT NULL, step TEXT NOT NULL, users INTEGER NOT NULL,
    PRIMARY KEY (day, market, device, step)
);

-- session behaviour per page: rage clicks (repeated clicks on one spot), dead clicks (clicks that do nothing),
-- average scroll depth, and sessions that left the site from this page
CREATE TABLE IF NOT EXISTS ux_daily (
    day TEXT NOT NULL, market TEXT NOT NULL, device TEXT NOT NULL, page TEXT NOT NULL,   -- /product, /cart, /checkout, /payment
    sessions INTEGER NOT NULL, rage_clicks INTEGER NOT NULL, dead_clicks INTEGER NOT NULL, avg_scroll_pct REAL, exits INTEGER NOT NULL,
    PRIMARY KEY (day, market, device, page)
);

-- "What stopped you buying today?" asked to a sample of visitors leaving without buying.
-- reason: price, sold_out, delivery_or_date, trust, payment_failed, just_browsing, other
CREATE TABLE IF NOT EXISTS exit_survey (
    day TEXT NOT NULL, market TEXT NOT NULL, device TEXT NOT NULL, product_id TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL, responses INTEGER NOT NULL,
    PRIMARY KEY (day, market, device, product_id, reason)
);

-- capacity events per product: sold_out (no units left), restocked
CREATE TABLE IF NOT EXISTS stock_events (product_id TEXT NOT NULL, day TEXT NOT NULL, event TEXT NOT NULL, PRIMARY KEY (product_id, day, event));

-- funnel step conversion per market and device, by week
DROP VIEW IF EXISTS v_funnel_steps;
CREATE VIEW v_funnel_steps AS
SELECT date(day, 'weekday 0', '-6 days') AS week, market, device,
       SUM(CASE WHEN step = 'session_start' THEN users END) AS sessions,
       SUM(CASE WHEN step = 'view_product' THEN users END) AS view_product,
       SUM(CASE WHEN step = 'add_to_cart' THEN users END) AS add_to_cart,
       SUM(CASE WHEN step = 'begin_checkout' THEN users END) AS begin_checkout,
       SUM(CASE WHEN step = 'add_payment' THEN users END) AS add_payment,
       SUM(CASE WHEN step = 'purchase' THEN users END) AS purchase
FROM events_daily GROUP BY week, market, device;

-- why visitors did not buy, by market and reason, last 28 days vs the 28 before
DROP VIEW IF EXISTS v_why_not_buy;
CREATE VIEW v_why_not_buy AS
WITH asof AS (SELECT MAX(day) AS d FROM exit_survey)
SELECT market, reason,
       SUM(CASE WHEN day > date(asof.d, '-28 days') THEN responses ELSE 0 END) AS responses_28d,
       SUM(CASE WHEN day <= date(asof.d, '-28 days') AND day > date(asof.d, '-56 days') THEN responses ELSE 0 END) AS responses_prev_28d
FROM exit_survey, asof GROUP BY market, reason;

-- targets the business manages to (scope: 'all' or a market name). metric: cpa, roas, mer, cac, cpm, payback_orders
CREATE TABLE IF NOT EXISTS targets (scope TEXT NOT NULL, metric TEXT NOT NULL, target REAL NOT NULL, direction TEXT NOT NULL,  -- max or min
    PRIMARY KEY (scope, metric));
-- gross margin per order, for payback (share of revenue kept after cost of goods and fulfilment)
CREATE TABLE IF NOT EXISTS unit_costs (scope TEXT PRIMARY KEY, gross_margin REAL NOT NULL);

-- unit economics per ad over the last 28 days: delivery cost (CPM, CPC, CTR), acquisition cost (CPA, CAC) and return (ROAS)
DROP VIEW IF EXISTS v_ad_economics_28d;
CREATE VIEW v_ad_economics_28d AS
WITH asof AS (SELECT MAX(day) AS d FROM ad_daily),
a AS (SELECT ad_id, market, platform, creative, SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(link_clicks) AS clicks,
             SUM(platform_revenue) AS platform_revenue FROM ad_daily, asof WHERE day > date(asof.d, '-28 days') GROUP BY ad_id),
s AS (SELECT ad_id, SUM(orders) AS orders, SUM(new_customers) AS new_customers, SUM(revenue) AS revenue FROM sales_daily, asof
      WHERE day > date(asof.d, '-28 days') AND ad_id != '' GROUP BY ad_id)
SELECT a.ad_id, a.market, a.platform, a.creative, ROUND(a.spend, 2) AS spend, a.impressions, a.clicks,
       ROUND(1000.0 * a.spend / NULLIF(a.impressions, 0), 2) AS cpm, ROUND(100.0 * a.clicks / NULLIF(a.impressions, 0), 2) AS ctr_pct,
       ROUND(a.spend / NULLIF(a.clicks, 0), 2) AS cpc, s.orders, s.new_customers, ROUND(s.revenue, 2) AS revenue,
       ROUND(a.spend / NULLIF(s.orders, 0), 2) AS cpa, ROUND(a.spend / NULLIF(s.new_customers, 0), 2) AS cac,
       ROUND(s.revenue / NULLIF(a.spend, 0), 2) AS roas, ROUND(a.platform_revenue / NULLIF(a.spend, 0), 2) AS platform_roas
FROM a LEFT JOIN s USING (ad_id);

-- per market over the last 28 days: MER (all revenue / all marketing spend), marketing spend as % of gross revenue,
-- blended CAC (all spend / all new customers) and how many first orders it takes to pay back that CAC
DROP VIEW IF EXISTS v_market_economics_28d;
CREATE VIEW v_market_economics_28d AS
WITH asof AS (SELECT MAX(day) AS d FROM sales_daily),
s AS (SELECT market, SUM(revenue) AS revenue, SUM(orders) AS orders, SUM(new_customers) AS new_customers FROM sales_daily, asof
      WHERE day > date(asof.d, '-28 days') GROUP BY market),
a AS (SELECT market, SUM(spend) AS spend, SUM(impressions) AS impressions FROM ad_daily, asof WHERE day > date(asof.d, '-28 days') GROUP BY market),
gm AS (SELECT COALESCE((SELECT gross_margin FROM unit_costs WHERE scope = 'all'), 0.5) AS g)
SELECT s.market, ROUND(s.revenue, 2) AS gross_revenue, ROUND(a.spend, 2) AS marketing_spend, s.orders, s.new_customers,
       ROUND(s.revenue / NULLIF(a.spend, 0), 2) AS mer, ROUND(100.0 * a.spend / NULLIF(s.revenue, 0), 1) AS spend_pct_of_revenue,
       ROUND(1000.0 * a.spend / NULLIF(a.impressions, 0), 2) AS cpm, ROUND(a.spend / NULLIF(s.orders, 0), 2) AS blended_cpa,
       ROUND(a.spend / NULLIF(s.new_customers, 0), 2) AS blended_cac,
       ROUND((a.spend / NULLIF(s.new_customers, 0)) / NULLIF(s.revenue / NULLIF(s.orders, 0) * gm.g, 0), 2) AS payback_orders
FROM s JOIN a USING (market), gm;

-- customer journeys: the ordered channel touches of one visitor before they bought or left (path: 'paid:meta > paid:google_brand')
CREATE TABLE IF NOT EXISTS journeys (market TEXT NOT NULL, journey_id TEXT NOT NULL, path TEXT NOT NULL, converted INTEGER NOT NULL, revenue REAL NOT NULL,
    PRIMARY KEY (market, journey_id));

-- who may approve as which role (an approval is checked against this, not against what the approver claims)
CREATE TABLE IF NOT EXISTS team (person TEXT NOT NULL, role TEXT NOT NULL, PRIMARY KEY (person, role));

-- ---------------------------------------------------------------------------------------------------------------
-- Market context for benchmarks and the demand engine
-- ---------------------------------------------------------------------------------------------------------------
-- market profile: real location and rounded metro population; affluence and competition are indices (1.0 = typical)
CREATE TABLE IF NOT EXISTS market_profile (market TEXT PRIMARY KEY, country TEXT NOT NULL, lat REAL, lon REAL, pop_m REAL, affluence REAL,
    competition REAL, launched_on TEXT);
-- real daily weather per city (Open-Meteo) and national public holidays (Nager.Date)
CREATE TABLE IF NOT EXISTS weather_daily (day TEXT NOT NULL, market TEXT NOT NULL, temp_c REAL, precip_mm REAL, source TEXT NOT NULL,
    PRIMARY KEY (day, market));
CREATE TABLE IF NOT EXISTS holidays (day TEXT NOT NULL, country TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY (day, country));
-- the marketing plan: monthly budget per market, product line and paid channel
CREATE TABLE IF NOT EXISTS budget_plan (month TEXT NOT NULL, market TEXT NOT NULL, line TEXT NOT NULL, channel TEXT NOT NULL, budget REAL NOT NULL,
    PRIMARY KEY (month, market, line, channel));

-- voice of customer: survey answers, NPS comments, reviews and support tickets (text), and the themes Claude assigned
CREATE TABLE IF NOT EXISTS voc_items (item_id TEXT PRIMARY KEY, day TEXT NOT NULL, market TEXT NOT NULL, line TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,          -- nps, exit_survey, review, support_ticket
    score INTEGER,                 -- NPS 0-10 or review stars 1-5 where the source has one
    lang TEXT NOT NULL DEFAULT 'en', text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS voc_labels (item_id TEXT PRIMARY KEY, theme TEXT NOT NULL, sentiment TEXT NOT NULL, summary TEXT NOT NULL, model TEXT NOT NULL);

-- spend, revenue and orders by market, product line and channel per ISO week: the base for curves and benchmarks
DROP VIEW IF EXISTS v_channel_weekly;
CREATE VIEW v_channel_weekly AS
WITH s AS (SELECT date(day, 'weekday 0', '-6 days') AS week, market, line, replace(channel, 'paid:', '') AS channel, SUM(revenue) AS revenue,
                  SUM(orders) AS orders, SUM(sessions) AS sessions FROM sales_daily GROUP BY 1, 2, 3, 4),
a AS (SELECT date(day, 'weekday 0', '-6 days') AS week, market, line, creative AS channel, SUM(spend) AS spend, SUM(impressions) AS impressions,
             SUM(link_clicks) AS clicks, SUM(platform_revenue) AS platform_revenue FROM ad_daily GROUP BY 1, 2, 3, 4)
SELECT s.week, s.market, s.line, s.channel, ROUND(s.revenue, 2) AS revenue, s.orders, s.sessions, ROUND(COALESCE(a.spend, 0), 2) AS spend,
       a.impressions, a.clicks, ROUND(a.platform_revenue, 2) AS platform_revenue
FROM s LEFT JOIN a USING (week, market, line, channel);

-- category search interest per market and product line per week (like a search-trends export): how many people look for
-- the category at all, whoever they buy from. A demand signal independent of the brand's own reach.
CREATE TABLE IF NOT EXISTS search_interest (week TEXT NOT NULL, market TEXT NOT NULL, line TEXT NOT NULL, searches INTEGER NOT NULL, source TEXT NOT NULL,
    PRIMARY KEY (week, market, line));

-- enterprise sandbox account: channel budget multipliers and pauses per 'Market|Line|channel', rain rules per 'Market|Line'
CREATE TABLE IF NOT EXISTS policy_state (key TEXT PRIMARY KEY, mult REAL NOT NULL DEFAULT 1.0, paused INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS weather_rules (key TEXT PRIMARY KEY, boost_pct REAL NOT NULL);
