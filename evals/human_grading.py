"""Checks the AI grader against a person.

    python evals/human_grading.py build   # writes evals/human/grading.html: memos + criteria, AI verdicts hidden
    (open it, mark each criterion pass/fail, press "Export", save the file as evals/human/grades.json)
    python evals/human_grading.py score   # agreement between you and the AI grader, per criterion and overall

Memos are drawn from the latest b2c and enterprise result files so the sample covers both scenarios.
"""
from __future__ import annotations

import glob
import html
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evals" / "human"
sys.path.insert(0, str(ROOT / "evals"))


def sample(n: int = 10, seed: int = 1) -> list[dict]:
    items = []
    for pattern in ("analyst-b2c-heldout-*.json", "analyst-b2c-dev-*.json", "analyst-enterprise-*.json"):
        files = sorted(glob.glob(str(ROOT / "evals" / "results" / pattern)))
        if not files:
            continue
        d = json.loads(Path(files[-1]).read_text())
        for r in d["runs"]:
            items.append({"file": Path(files[-1]).name, "scenario": d.get("scenario"), "seed": r["seed"], "memo": r["memo"],
                          "criteria": [g["criterion"] for g in r["grades"]], "ai": {g["criterion"]: g["pass"] for g in r["grades"]}})
    random.Random(seed).shuffle(items)
    return items[:n]


def build() -> Path:
    from analyst_eval import SCENARIOS
    OUT.mkdir(parents=True, exist_ok=True)
    items = sample()
    (OUT / "sample.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    cards = []
    for i, it in enumerate(items):
        m, crit = it["memo"], SCENARIOS[it["scenario"]]["criteria"]
        body = f"<h3>{html.escape(m['headline'])}</h3>" + "".join(f"<p><b>{html.escape(f['title'])}</b> ({f['confidence']}): {html.escape(f['evidence'])}</p>" for f in m["findings"])
        body += "<h4>Recommendations</h4><ol>" + "".join(f"<li><b>{html.escape(r['action'])}</b> · {html.escape(r['expected_impact'])}</li>" for r in m["recommendations"]) + "</ol>"
        qs = "".join(f"""<tr><td>{html.escape(crit[c])}</td><td><label><input type="radio" name="m{i}-{c}" value="1"> pass</label>
                         <label><input type="radio" name="m{i}-{c}" value="0"> fail</label></td></tr>""" for c in it["criteria"])
        cards.append(f'<section><h2>Memo {i + 1} of {len(items)} <small>({it["scenario"]})</small></h2><details open><summary>Read the memo</summary>{body}</details><table>{qs}</table></section>')
    page = f"""<!doctype html><meta charset="utf-8"><title>Grade the analyst</title>
<style>body{{font:15px/1.5 -apple-system,sans-serif;max-width:900px;margin:30px auto;padding:0 16px;color:#16181d}}section{{border:1px solid #ddd;border-radius:12px;padding:16px;margin:18px 0}}
td{{padding:8px;border-top:1px solid #eee;vertical-align:top}}td:last-child{{white-space:nowrap}}button{{font:inherit;padding:10px 18px;border-radius:10px;border:0;background:#2f5bd3;color:#fff;cursor:pointer}}</style>
<h1>Grade the analyst's memos</h1><p>For each memo, read it, then mark each criterion pass or fail. The AI grader's verdicts are hidden. When done, press Export and save the file as <code>evals/human/grades.json</code>.</p>
{''.join(cards)}<p><button id="x">Export grades</button></p>
<script>document.getElementById('x').onclick=()=>{{const g={{}};document.querySelectorAll('input:checked').forEach(i=>g[i.name]=i.value==='1');
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(g,null,1)],{{type:'application/json'}}));a.download='grades.json';a.click();}};</script>"""
    (OUT / "grading.html").write_text(page)
    return OUT / "grading.html"


def score() -> None:
    items = json.loads((OUT / "sample.json").read_text())
    human = json.loads((OUT / "grades.json").read_text())
    agree = total = 0
    by = {}
    for i, it in enumerate(items):
        for c in it["criteria"]:
            k = f"m{i}-{c}"
            if k not in human:
                continue
            total += 1
            same = human[k] == it["ai"][c]
            agree += same
            b = by.setdefault(c, [0, 0])
            b[0] += same
            b[1] += 1
    print(f"agreement {agree}/{total} = {100 * agree / max(1, total):.1f}%")
    for c, (a, t) in sorted(by.items(), key=lambda x: x[1][0] / x[1][1]):
        print(f"  {c}: {a}/{t}")
    (OUT / "agreement.json").write_text(json.dumps({"agree": agree, "total": total, "by_criterion": by}, indent=1))


if __name__ == "__main__":
    {"build": lambda: print(build()), "score": score}[sys.argv[1] if len(sys.argv) > 1 else "build"]()
