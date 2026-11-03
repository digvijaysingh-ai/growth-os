import json
from pathlib import Path

from growth_os.config import load_config
from growth_os.agents.ads.rules import evaluate, join

ROOT = Path(__file__).resolve().parent.parent
CFG = load_config(ROOT / "config.example.toml")


def views(insights, site, ads=None):
    ads = ads or [{"id": r["ad_id"], "effective_status": "ACTIVE", "campaign_id": r.get("campaign_id", "c")} for r in insights]
    return join(insights, ads, site)


def ad(ad_id, spend, impressions=3000, clicks=40, freq=1.5, campaign="c"):
    return {"ad_id": ad_id, "ad_name": ad_id, "campaign_id": campaign, "spend": str(spend),
            "impressions": str(impressions), "frequency": str(freq), "inline_link_clicks": str(clicks)}


def by_id(verdicts):
    return {v.ad.ad_id: v for v in verdicts}


def test_learning_phase_is_never_judged():
    v = by_id(evaluate(views([ad("a", 3), ad("b", 50)], []), CFG))
    assert v["a"].rule == "learning" and v["a"].action == "keep"


def test_no_leads_after_three_times_target():
    v = by_id(evaluate(views([ad("a", 31), ad("b", 12)], [{"ad_id": "b", "leads": 2}]), CFG))
    assert v["a"].action == "pause" and v["a"].rule == "no_leads_after_spend"
    assert v["b"].action == "keep"


def test_cpl_is_from_site_leads_not_meta():
    v = by_id(evaluate(views([ad("a", 40), ad("b", 10)], [{"ad_id": "a", "leads": 1}, {"ad_id": "b", "leads": 2}]), CFG))
    assert v["a"].rule == "cpl_over_target" and v["a"].action == "pause"


def test_never_empties_a_campaign():
    v = by_id(evaluate(views([ad("a", 40), ad("b", 35)], []), CFG))
    assert sorted(x.action for x in v.values()) == ["keep", "pause"]
    kept = next(x for x in v.values() if x.action == "keep")
    assert kept.blocked_by == "last_active_in_campaign"


def test_paused_ads_are_ignored():
    vs = views([ad("a", 40)], [], ads=[{"id": "a", "effective_status": "PAUSED", "campaign_id": "c"}])
    assert evaluate(vs, CFG) == []


def test_sample_week_fixture():
    d = json.loads((ROOT / "fixtures/sample-week.json").read_text())
    v = by_id(evaluate(join(d["insights"], d["ads"], d["site"]), CFG))
    assert {k for k, x in v.items() if x.action == "pause"} == {"1002", "1003"}
    assert v["2001"].blocked_by == "last_active_in_campaign"


def test_instant_form_ads_use_metas_lead_count():
    a = ad("a", 40) | {"actions": [{"action_type": "lead", "value": "4"}, {"action_type": "onsite_conversion.lead_grouped", "value": "4"}]}
    b = ad("b", 40)
    # one Instant Form lead was tagged by hand in the dashboard and got a demo: qualified, not an extra lead
    v = by_id(evaluate(views([a, b], [{"ad_id": "a", "leads": 1, "qualified": 1}]), CFG))
    assert v["a"].ad.leads == 4 and v["a"].ad.qualified == 1 and v["a"].action == "keep"
    assert v["b"].rule == "no_leads_after_spend"
