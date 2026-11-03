# Release: console, case study, public repo

Nothing here runs without the owner's approval in chat. There is no interactive prompt anywhere in the sequence.

## Order

```bash
python -m growth_os.enterprise.outcomes --leave-one-out --seed 7          # only if the team run or outcomes changed
REQUIRE_NODE=1 pytest -q                                                  # deck tests must run, not skip
growth-os console                                                         # never with --allow-stale-loo for a release
python scripts/publish_scan.py --deployed dist/console                    # GOS-106 on any hit
(cd ~/Projects/djcrafted && npm run build && node scripts/qa.mjs)        # case study pages
python scripts/publish_scan.py --deployed ~/Projects/djcrafted/dist/work/growth-os ~/Projects/djcrafted/dist/es/proyectos/growth-os
```

Then, after the owner approves:

1. Deploy the console first (the page links to it), then the case study with djcrafted's `scripts/deploy.mjs`.
   Never the archive deploy: it replaces the whole site.
2. Check each URL prints 200, and that the console serves the app.js the build named:

```bash
for u in https://djcrafted.com/growth-os/ https://djcrafted.com/work/growth-os/ https://djcrafted.com/es/proyectos/growth-os/ https://tulsi.djcrafted.com/; do
  printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$u")" "$u"; done
v=$(grep -o 'app.js?v=[a-f0-9]*' dist/console/index.html); curl -s https://djcrafted.com/growth-os/ | grep -q "$v" && echo "app.js $v live" || echo "app.js mismatch: redeploy the console"
```

## If something fails

- The console and the case study deploy independently. If the case-study deploy or one of its checks fails, redeploy
  the case study only; the console is unaffected.
- If the console check fails or shows the wrong app.js version, redeploy the previous `dist/console` (it is
  rebuilt from the committed snapshot with `growth-os console`) and look at the build again.
- The public repo is pushed from a fresh single-commit clone after `python scripts/publish_scan.py --repo <clone>`
  is clean. A bad push is fixed by a new commit; the history is never rewritten after it is public.
