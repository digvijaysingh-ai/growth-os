import json

from growth_os import demo
from growth_os.agents.analyst.analyst import brief, run_sql
from growth_os.agents.analyst.stats import compare_rates, sample_per_arm, wilson
from growth_os.hub import store


def test_wilson_interval_contains_rate():
    lo, hi = wilson(20, 400)
    assert lo < 0.05 < hi and round(lo, 3) == 0.033


def test_sample_size_matches_standard_calculators():
    # 5% baseline, +50% relative lift, 95% confidence, 80% power: about 1,470 per arm
    assert 1450 <= sample_per_arm(0.05, 0.5) <= 1490


def test_small_samples_are_called_small():
    assert compare_rates(1, 6, 4, 7)["verdict"] == "too little data to tell"
    assert compare_rates(55, 198, 81, 113)["verdict"] == "different (95% confidence)"


def test_demo_hub_views_and_brief(tmp_path):
    hub = demo.build(tmp_path / "hub.sqlite", seed=7)
    with store.connect(hub, read_only=True) as db:
        ads = {r["ad_name"]: dict(r) for r in db.execute("SELECT * FROM v_ad_funnel")}
        assert set(ads) == {"Reel: owner story", "Reel: before and after", "Carousel: prices"}
        clicky, story = ads["Reel: before and after"], ads["Reel: owner story"]
        assert clicky["link_clicks"] > story["link_clicks"] and clicky["cost_per_qualified"] > story["cost_per_qualified"]
        b = brief(db, demo.date(2026, 10, 25))
        assert b["totals_this_period"]["sessions"] > b["totals_previous_period"]["sessions"]
        assert {r["first_contact"] for r in b["qualified_by_contact_speed_all_time"]} >= {"within 2 h", "over 24 h"}


def test_sql_tool_is_read_only(tmp_path):
    hub = demo.build(tmp_path / "hub.sqlite", seed=7)
    with store.connect(hub, read_only=True) as db:
        assert "rows" in json.loads(run_sql(db, "SELECT COUNT(*) AS n FROM leads"))
        for bad in ("DELETE FROM leads", "SELECT 1; DROP TABLE leads", "UPDATE leads SET stage = 'x'", "PRAGMA table_info(leads)"):
            assert "error" in json.loads(run_sql(db, bad))
        assert db.execute("SELECT COUNT(*) FROM leads").fetchone()[0] > 0


def test_scanning_many_segments_corrects_for_chance():
    # p ≈ 0.03 on its own: "different" for one planned comparison, noise when it is 1 of 10 markets scanned
    one = compare_rates(150, 300, 180, 300)
    ten = compare_rates(150, 300, 180, 300, comparisons=10)
    assert one["verdict"].startswith("different") and "likely noise" in ten["verdict"]
    assert compare_rates(192, 400, 120, 400, comparisons=10)["verdict"].startswith("different")
