from growth_os.connectors.behaviour import Clarity, HotjarSurvey, Mixpanel


def test_mixpanel_funnel_maps_steps_and_segments():
    payload = {"data": {"2026-10-20": {"Berlin|iOS": [{"event": "view_item", "count": 900}, {"event": "add_payment_info", "count": 120},
                                                      {"event": "purchase", "count": 30}], "$overall": [{"event": "purchase", "count": 99}]}}}
    rows = Mixpanel.parse(payload)
    assert {"day": "2026-10-20", "market": "Berlin", "device": "ios", "step": "add_payment", "users": 120} in rows
    assert len(rows) == 3


def test_clarity_rage_clicks_per_page_and_device():
    payload = [{"metricName": "Traffic", "information": [{"sessionsCount": "400", "OS": "iOS", "URL": "https://x.com/checkout/payment"}]},
               {"metricName": "RageClickCount", "information": [{"sessionsCount": "90", "subTotal": "140", "OS": "iOS", "URL": "https://x.com/checkout/payment?a=1"}]}]
    rows = Clarity("t", "Berlin").parse(payload, "2026-10-20", {"/checkout/payment": "/payment"})
    assert rows == [{"day": "2026-10-20", "market": "Berlin", "device": "ios", "page": "/payment", "sessions": 400, "rage_clicks": 140,
                     "dead_clicks": 0, "avg_scroll_pct": None, "exits": 0}]


def test_hotjar_answers_become_reasons():
    res = [{"created_time": "2026-10-20T10:00:00Z", "device": "mobile", "answers": [{"answer": "My card payment kept failing"}]},
           {"created_time": "2026-10-20T11:00:00Z", "device": "mobile", "answers": [{"answer": "Demasiado caro"}]},
           {"created_time": "2026-10-20T12:00:00Z", "device": "desktop", "answers": [{"answer": "hmm"}]}]
    rows = HotjarSurvey("a", "b", "1", "2", "Madrid").parse(res)
    assert {(r["reason"], r["responses"]) for r in rows} == {("payment_failed", 1), ("price", 1), ("other", 1)}
