"""Joins Meta delivery data with first-party leads per ad, then applies the rules.

Leads come from the site (utm_content = the Meta ad id), not from a pixel: an ad is judged on people who
actually asked for a demo, and on how many of those got as far as a demo being sent ("qualified").
Instant Form ads are the exception: those people never visit the site, so Meta's own lead count is used,
and the leads the owner tags with the ad in the dashboard supply the qualified count.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Meta's action types for a submitted Instant Form; the first one present wins (they overlap)
META_LEAD_ACTIONS = ("onsite_conversion.lead_grouped", "lead", "leadgen_grouped")


@dataclass
class AdView:
    ad_id: str
    ad_name: str = ""
    campaign_id: str = ""
    campaign: str = ""
    status: str = "ACTIVE"
    spend: float = 0.0
    impressions: int = 0
    reach: int = 0
    frequency: float = 0.0
    clicks: int = 0
    meta_leads: int = 0  # Instant Form submissions, as Meta counts them
    # first-party, from the site
    visits: int = 0
    form_starts: int = 0
    site_leads: int = 0
    qualified: int = 0
    won: int = 0

    @property
    def leads(self) -> int:
        # an ad sends people either to an Instant Form or to the website, so take whichever source saw them;
        # Instant Form leads tagged by hand in the dashboard are a subset of Meta's count, not extra
        return max(self.meta_leads, self.site_leads)

    @property
    def ctr(self) -> float:
        return 100.0 * self.clicks / self.impressions if self.impressions else 0.0

    @property
    def cpl(self) -> float | None:
        return self.spend / self.leads if self.leads else None

    @property
    def cpql(self) -> float | None:
        return self.spend / self.qualified if self.qualified else None

    def metrics(self) -> dict:
        m = {"spend": round(self.spend, 2), "impressions": self.impressions, "clicks": self.clicks,
             "ctr": round(self.ctr, 2), "frequency": round(self.frequency, 2), "visits": self.visits,
             "leads": self.leads, "qualified": self.qualified}
        if self.meta_leads:
            m["meta_form_leads"] = self.meta_leads
        if self.cpl is not None:
            m["cpl"] = round(self.cpl, 2)
        return m


@dataclass
class Verdict:
    ad: AdView
    rule: str
    action: str  # "pause" or "keep"
    reason: str
    blocked_by: str = ""  # a guard that stopped a pause, e.g. last active ad in the campaign

    def proposal(self) -> dict:
        return {"ad_id": self.ad.ad_id, "ad_name": self.ad.ad_name, "campaign": self.ad.campaign,
                "action": self.action, "rule": self.rule, "reason": self.reason, "metrics": self.ad.metrics()}

    def log(self) -> dict:
        return {"ad_id": self.ad.ad_id, "ad_name": self.ad.ad_name, "rule": self.rule, "action": self.action,
                "reason": self.reason, "blocked_by": self.blocked_by, "metrics": self.ad.metrics()}


def join(insights: list[dict], ads: list[dict], site: list[dict]) -> list[AdView]:
    """One row per ad that either delivered in the window or brought site traffic."""
    views: dict[str, AdView] = {}
    for r in insights:
        v = views.setdefault(r["ad_id"], AdView(ad_id=r["ad_id"]))
        v.ad_name = r.get("ad_name", "")
        v.campaign_id = r.get("campaign_id", "")
        v.campaign = r.get("campaign_name", "")
        v.spend = float(r.get("spend") or 0)
        v.impressions = int(r.get("impressions") or 0)
        v.reach = int(r.get("reach") or 0)
        v.frequency = float(r.get("frequency") or 0)
        v.clicks = int(r.get("inline_link_clicks") or 0)
        acts = {a.get("action_type"): a.get("value") for a in r.get("actions") or []}
        v.meta_leads = next((int(float(acts[k])) for k in META_LEAD_ACTIONS if acts.get(k)), 0)
    for a in ads:
        v = views.get(a["id"])
        if v:
            v.status = a.get("effective_status", v.status)
            v.campaign_id = v.campaign_id or a.get("campaign_id", "")
    for s in site:
        v = views.setdefault(str(s["ad_id"]), AdView(ad_id=str(s["ad_id"]), status="UNKNOWN"))
        for k in ("visits", "form_starts", "qualified", "won"):
            setattr(v, k, int(s.get(k) or 0))
        v.site_leads = int(s.get("leads") or 0)
    return sorted(views.values(), key=lambda v: -v.spend)


def evaluate(views: list[AdView], cfg: dict) -> list[Verdict]:
    target = float(cfg["account"]["target_cpl"])
    g = cfg["guards"]
    rules = cfg["rules"]
    cur = cfg["account"].get("currency", "EUR")
    eur = (lambda x: f"{x:.2f} €") if cur == "EUR" else (lambda x: f"{x:.2f} {cur}")
    out: list[Verdict] = []

    for v in views:
        if v.status != "ACTIVE":
            continue
        if v.spend < g["min_spend"] or v.impressions < g["min_impressions"]:
            out.append(Verdict(v, "learning", "keep", f"Too early to judge: {eur(v.spend)} spent, {v.impressions} impressions."))
            continue

        hit: Verdict | None = None
        r = rules.get("no_leads_after_spend", {})
        if not hit and r.get("enabled") and v.leads == 0 and v.spend >= r["multiple"] * target:
            hit = Verdict(v, "no_leads_after_spend", "pause",
                          f"Spent {eur(v.spend)} ({v.spend / target:.1f}× the {eur(target)} target per lead) with no lead.")
        r = rules.get("cpl_over_target", {})
        if not hit and r.get("enabled") and v.cpl is not None and v.cpl > r["multiple"] * target:
            hit = Verdict(v, "cpl_over_target", "pause",
                          f"Cost per lead {eur(v.cpl)} is {v.cpl / target:.1f}× the {eur(target)} target ({v.leads} lead(s) for {eur(v.spend)}).")
        r = rules.get("low_ctr", {})
        if not hit and r.get("enabled") and v.impressions >= 2 * g["min_impressions"] and v.ctr < r["min_ctr_pct"] and v.leads == 0:
            hit = Verdict(v, "low_ctr", "pause",
                          f"Link CTR {v.ctr:.2f}% after {v.impressions} impressions (floor {r['min_ctr_pct']}%) and no leads.")
        r = rules.get("fatigue", {})
        if not hit and r.get("enabled") and v.frequency > r["max_frequency"] and (v.cpl is None or v.cpl > target):
            hit = Verdict(v, "fatigue", "pause",
                          f"Each person saw it {v.frequency:.1f} times on average (limit {r['max_frequency']}) and leads are above target cost.")
        out.append(hit or Verdict(v, "ok", "keep",
                                  f"Within rules: {v.leads} lead(s), " + (f"cost per lead {eur(v.cpl)}." if v.cpl else f"{eur(v.spend)} spent.")))

    # guard: never take a campaign to zero active ads
    keep_min = int(g.get("keep_min_active_per_campaign", 1))
    by_campaign: dict[str, list[Verdict]] = {}
    for vd in out:
        by_campaign.setdefault(vd.ad.campaign_id or vd.ad.campaign, []).append(vd)
    for group in by_campaign.values():
        # worst first (no lead at all counts as infinitely expensive), so the least bad one is the one kept
        pauses = sorted((vd for vd in group if vd.action == "pause"),
                        key=lambda vd: -(vd.ad.cpl if vd.ad.cpl is not None else float("inf")))
        allowed = max(0, len(group) - keep_min)
        for vd in pauses[allowed:]:
            vd.action, vd.blocked_by = "keep", "last_active_in_campaign"
            vd.reason += " Not proposed: it would leave the campaign with no active ad; pause the campaign yourself if you want it stopped."
    return out


def as_dict(v: AdView) -> dict:
    return {**asdict(v), "ctr": round(v.ctr, 2), "cpl": v.cpl, "cpql": v.cpql}
