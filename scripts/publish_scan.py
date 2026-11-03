"""Publish safety scan (GOS-106): run on the exact bytes that will be published, before any deploy or push.

    python scripts/publish_scan.py --deployed dist/console ~/Projects/djcrafted/dist/work/growth-os
    python scripts/publish_scan.py --repo /path/to/fresh-publish-clone      # scans `git ls-files` there

Rules:
  blocklist   names that must never appear (one per line in .publish-blocklist, private, never published)
  persona     the console's fictional approver names (deployed pages only; the code defines them on purpose)
  local-path  home directories and private state paths
  key         API keys and tokens
A hit prints file:line:rule with the matched text masked and exits 1. Reviewed false positives go in
publish-scan.allow, one per line: `<rule> <file> <reason>`.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from growth_os.loop import ROLE_PEOPLE  # noqa: E402  the fictional approvers, so this list can't drift from the code

PERSONAS = sorted({v.split(" (")[0] for v in ROLE_PEOPLE.values()})
RULES = {
    "local-path": re.compile(r"/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|C:\\Users\\"),
    "key": re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|ghp_[A-Za-z0-9]{20,}|EAA[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}"),
}
FIX = {"blocklist": "remove the name", "persona": "map it to a role label (growth_os/console/build.py ROLE_LABELS)",
       "local-path": "use a relative path", "key": "remove it and rotate the key"}
TEXT = {".py", ".js", ".mjs", ".html", ".md", ".json", ".toml", ".txt", ".css", ".svg", ".yml", ".yaml", ".sql", ".csv", ".sh", ".example", ""}


def _mask(s: str) -> str:
    return s[:3] + "…" + ("*" * max(3, len(s) - 3))


def _rules(deployed: bool) -> dict[str, re.Pattern]:
    rules = dict(RULES)
    block = ROOT / ".publish-blocklist"
    names = [n.strip() for n in block.read_text().splitlines() if n.strip() and not n.startswith("#")] if block.is_file() else []
    if names:
        rules["blocklist"] = re.compile("|".join(re.escape(n) for n in names), re.IGNORECASE)
    if deployed:
        rules["persona"] = re.compile(r"\b(" + "|".join(PERSONAS) + r")\b")
    return rules


def _allowed() -> set[tuple[str, str]]:
    f = ROOT / "publish-scan.allow"
    rows = [l.split(None, 2) for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")] if f.is_file() else []
    return {(r[0], r[1]) for r in rows if len(r) >= 2}


def _files(paths: list[Path], repo: bool) -> list[tuple[Path, str]]:
    out = []
    for p in paths:
        if repo:
            listed = subprocess.run(["git", "-C", str(p), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
            out += [(p / f, f) for f in listed]
        elif p.is_file():
            out.append((p, str(p)))
        else:  # named as given on the command line, so an allowlist entry can target one page
            out += [(f, str(f)) for f in sorted(p.rglob("*")) if f.is_file()]
    return [(f, n) for f, n in out if f.suffix.lower() in TEXT and f.stat().st_size < 20_000_000]


def scan(paths: list[Path], repo: bool = False) -> list[str]:
    rules, allow, hits = _rules(not repo), _allowed(), []
    for f, name in _files(paths, repo):
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for rule, rx in rules.items():
                for m in rx.finditer(line):
                    if (rule, name) not in allow:
                        hits.append(f"{name}:{i}:{rule} {_mask(m.group(0))}  fix: {FIX[rule]}")
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scan what will be published for names, local paths and keys (GOS-106).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--deployed", nargs="+", type=Path, help="built pages and assets to be deployed")
    g.add_argument("--repo", type=Path, help="a git clone to be pushed; scans `git ls-files`")
    a = ap.parse_args(argv)
    paths, repo = ([a.repo], True) if a.repo else (a.deployed, False)
    for p in paths:
        if not p.exists():
            print(f"GOS-101: {p} does not exist. Fix: build it first, then scan the exact files you will publish.", file=sys.stderr)
            return 1
    hits = scan(paths, repo)
    for h in hits:
        print(h, file=sys.stderr)
    stamp = [p for p in (paths if not repo else []) if p.is_dir() and (p / "index.html").is_file() and '"stale": true' in (p / "index.html").read_text()]
    for p in stamp:
        print(f"{p}/index.html:stale-build  fix: rebuild without --allow-stale-loo", file=sys.stderr)
    if hits or stamp:
        print(f"GOS-106: {len(hits) + len(stamp)} problem(s) in what would be published. Fix: see each line; reviewed false positives go in publish-scan.allow.",
              file=sys.stderr)
        return 1
    print(f"publish scan clean: {', '.join(str(p) for p in paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
