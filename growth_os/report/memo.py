"""Renders the analyst's memo as Markdown (saved, shown on GitHub) and plain text (emailed)."""
from __future__ import annotations

SUFFICIENCY = {"too_little": "Too little data to conclude", "directional": "Directional, not proven", "solid": "Solid enough to act on"}


def _period(since: str, until: str) -> str:
    return "whole dataset (undated)" if not since else f"{since} to {until}"


def markdown(memo: dict, *, business: str, since: str, until: str, footer: str = "") -> str:
    out = [f"# Growth memo · {business} · {_period(since, until)}", "", f"**{memo['headline']}**", ""]
    ds = memo["data_sufficiency"]
    out += [f"> **Data:** {SUFFICIENCY.get(ds['verdict'], ds['verdict'])}. {ds['explanation']}", ""]
    if memo["kpis"]:
        out += ["| KPI | This period | Previous | Note |", "|---|---|---|---|"]
        out += [f"| {k['name']} | {k['value']} | {k['previous']} | {k['note']} |" for k in memo["kpis"]]
        out.append("")
    if memo["findings"]:
        out += ["## What happened", ""]
        out += [f"- **{f['title']}** ({f['confidence']} confidence). {f['evidence']}" for f in memo["findings"]]
        out.append("")
    if memo["recommendations"]:
        out += ["## What to do next", ""]
        for i, r in enumerate(memo["recommendations"], 1):
            out += [f"{i}. **{r['action']}** · effort {r['effort']} · {r['confidence']} confidence",
                    f"   - Why: {r['why']}", f"   - Expected impact: {r['expected_impact']}", f"   - How to measure: {r['how_to_measure']}"]
        out.append("")
    if memo["experiments"]:
        out += ["## Experiments worth running", "", "| Hypothesis | Version B | Metric | Sample per version | Weeks at current traffic |", "|---|---|---|---|---|"]
        out += [f"| {e['hypothesis']} | {e['variant']} | {e['metric']} | {e['sample_per_version']} | {e['weeks_at_current_traffic']} |" for e in memo["experiments"]]
        out.append("")
    if memo["questions_for_owner"]:
        out += ["## Questions for you", ""] + [f"- {q}" for q in memo["questions_for_owner"]] + [""]
    if footer:
        out += ["---", footer, ""]
    return "\n".join(out)


def plain(memo: dict, *, business: str, since: str, until: str) -> str:
    """Email version: same content, no Markdown syntax."""
    ds = memo["data_sufficiency"]
    out = [f"Growth memo · {business} · {_period(since, until)}", "", memo["headline"], "",
           f"Data: {SUFFICIENCY.get(ds['verdict'], ds['verdict'])}. {ds['explanation']}", ""]
    if memo["kpis"]:
        out += ["Key numbers (this period / previous):"] + [f"  {k['name']}: {k['value']} / {k['previous']}. {k['note']}" for k in memo["kpis"]] + [""]
    if memo["findings"]:
        out += ["What happened:"] + [f"  - {f['title']} ({f['confidence']} confidence). {f['evidence']}" for f in memo["findings"]] + [""]
    if memo["recommendations"]:
        out.append("What to do next:")
        for i, r in enumerate(memo["recommendations"], 1):
            out += [f"  {i}. {r['action']} (effort {r['effort']}, {r['confidence']} confidence)",
                    f"     Why: {r['why']}", f"     Expected impact: {r['expected_impact']}", f"     Measure: {r['how_to_measure']}"]
        out.append("")
    if memo["experiments"]:
        out.append("Experiments worth running:")
        out += [f"  - {e['hypothesis']} Version B: {e['variant']}. Metric: {e['metric']}. "
                f"{e['sample_per_version']} visitors per version, about {e['weeks_at_current_traffic']} weeks." for e in memo["experiments"]]
        out.append("")
    if memo["questions_for_owner"]:
        out += ["Questions for you:"] + [f"  - {q}" for q in memo["questions_for_owner"]] + [""]
    return "\n".join(out)
