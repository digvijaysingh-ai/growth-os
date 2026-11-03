> **Synthetic example.** Every number below comes from a generated data set, not a real business.

# Growth memo · Demo Studio (synthetic) · 2026-10-19 to 2026-10-25

**Spend rose 69% (124.49 → 210.30 EUR) with no increase in leads (22 both weeks). Almost all of the extra money went to "Reel: before and after", which tripled to 127.67 EUR and brought 443 visits but just 1 form start and 1 lead, so the first job this week is to cut it back and find out why.**

> **Data:** Directional, not proven. There are 6 weeks of data (14 Sep–25 Oct) and 136 leads in total. Site-level patterns have enough volume to call: mobile vs desktop form completion, how fast leads are contacted, and paid vs search form starts. All three passed compare_rates at 95%. Comparisons between individual ads use small lead counts, and compare_rates said 'too little data to tell' even where p-values were near 0. That covers the 9002 vs 9001 qualification rate (2/22 vs 15/24) and 9002's drop in form starts this week. Treat them as strong signals, not proof. This week's qualified count (7) will probably rise: 10 of this week's 22 leads are still at 'Contactado', and a demo usually goes out 33–80 h after the lead arrives. /oferta vs /oferta-b has only 15 sessions in total and settles nothing yet. The data is synthetic.

| KPI | This week | Previous | Note |
|---|---|---|---|
| Ad spend | 210.30 EUR | 124.49 EUR | +69%. The whole rise came from ad 9002 (41.24 → 127.67 EUR). The agent log has no action recorded for it. |
| Leads (all channels) | 22 | 22 | Flat even though spend rose. Leads not tied to an ad went 12 → 16; ad leads went 10 → 6. |
| Cost per lead, paid ads only | 35.05 EUR (210.30 / 6) | 12.45 EUR (124.49 / 10) | 3.5× the 10 EUR target. Blended across all leads it is 9.56 EUR (prev 5.66). |
| Qualified leads (demo sent) | 7 | 12 | Still incomplete: 10 of this week's leads are at 'Contactado'. Ads gave 4 (all from 9001), vs 5 last week. |
| Cost per qualified lead (blended) | 30.04 EUR | 10.37 EUR | Spend divided by all qualified leads. |
| Won | 1 | 4 | The win came from 9001 (owner story). |
| Sessions | 812 | 522 | +290, mostly from 9002 (145 → 443 sessions). |
| Form completion (submits / starts) | 22/57 = 39% | 22/49 = 45% | 30 form errors on 57 starts. Mobile: 8 submits from 39 starts; desktop: 14 from 18. |
| Leads first contacted within 2 h | 7 of 22 | 11 of 22 | Average time to first contact rose from 22.7 h to 34.1 h. |

## What happened

- **Ad 9002's budget tripled and the extra traffic is not converting** (medium confidence). 9002 spent 41–46 EUR a week for 5 weeks, then 127.67 EUR in the week of 19–25 Oct, about 15–20 EUR a day instead of 5–7. Its sessions went 145 → 443, but form starts went 10 → 1, with a single lead and 0 qualified. Engagement per session was unchanged (37.2 s vs 38.0 s) and about half of visitors still scrolled past the midpoint. So people are reading the page but not reaching or opening the form. Form start rate fell from 6.9% to 0.2%. compare_rates puts p≈0 but its verdict is 'too little data to tell'; it is still a consistent daily pattern, with 0 form starts on 6 of the 7 days. agent_actions has no entry for this change.
- **The before/after reel brings clicks that rarely qualify; the owner-story reel brings leads that do** (medium confidence). All time: 9002 has 22 leads, 2 qualified (9%), and 169.76 EUR per qualified lead. 9001 has 24 leads, 15 qualified (62.5%), 4 won, and 22.12 EUR per qualified lead. 9003 has 12 leads, 4 qualified, 41.68 EUR per qualified lead. compare_rates on 9002 vs 9001 qualification: p=0.0002, but verdict 'too little data to tell', because 9002 has only 2 qualified leads; it estimates about 12+ leads per arm to confirm.
- **The mobile form is broken or too hard to complete** (high confidence). All time, mobile has 202 form starts, 139 form errors and 59 submits (29%). Desktop has 105 starts, 9 errors and 77 submits (73%). compare_rates: different at 95% confidence. This week: mobile 39 starts → 8 submits; desktop 18 → 14. 71% of sessions this week were on mobile (575 of 812).
- **Leads contacted within 2 hours qualify far more often, and contact got slower this week** (high confidence). All time, 41 of 55 leads (75%) contacted within 2 h got a demo, against 17 of 81 (21%) contacted after more than 24 h. compare_rates: different at 95% confidence. This could be partly because better leads get called first, but the gap is large. This week only 7 of 22 leads were contacted within 2 h and 15 waited more than 24 h. Average time to first contact rose from 22.7 h to 34.1 h.
- **Meta traffic starts the form far less often than search traffic** (high confidence). Homepage this week: paid:meta 15 form starts from 559 sessions (2.7%); search 23 from 139 (16.5%). compare_rates: different at 95% confidence. Most of the gap is 9002's traffic. Search also gave 11 of the 22 form submits.
- **/oferta-b looks promising, but it has almost no traffic yet** (low confidence). Since 22 Oct, all direct traffic: /oferta 0 form starts from 9 sessions; /oferta-b 5 starts and 1 submit from 6 sessions. compare_rates: too little data to tell.

## What to do next

1. **Today, bring 'Reel: before and after' (9002) back to its old level of about 6 EUR a day, or pause it while you check its destination URL. Make sure the link still goes to the homepage with the form and the 'Pide tu demo' button working, and test it on a phone.** · effort S · high confidence
   - Why: It took about 86 EUR more than usual this week and returned 1 lead and 0 qualified. Visitors still read the page for the same time but stopped starting the form, which points to a changed link or broken page, or a new audience that doesn't fit. Across all time it costs 169.76 EUR per qualified lead, against 22.12 for 9001.
   - Expected impact: Saves about 80–90 EUR a week. At last week's 9002 spend, paid cost per lead should go back toward about 12 EUR instead of 35 EUR, without losing any qualified leads.
   - How to measure: 9002's daily spend goes back to about 6 EUR. If the link is fixed, form starts per 9002 session go back to about 5–7% (10 from 145 before). Paid cost per lead next week is under 15 EUR.
2. **Fix the mobile form. On a phone, fill it in with common mistakes (phone format, required fields, keyboard type) to find which field causes the errors. Then cut it to the minimum fields and add the WhatsApp button next to it as a fallback.** · effort M · high confidence
   - Why: On mobile, 139 errors on 202 starts and only 29% completion; on desktop, 73%. Mobile is 71% of traffic. If mobile completed like desktop, this week's 39 mobile starts would have been about 28 submits instead of 8.
   - Expected impact: If mobile completion reaches 50% instead of 29%, that is about 8 more form leads a week at this week's form start volume, at no extra cost.
   - How to measure: Mobile form_errors / form_starts and form_submits / form_starts, the week before vs the week after the fix (from 69% errors and 29% completion now).
3. **Call or WhatsApp every new web lead within 2 hours during working hours. Turn on a phone notification for new leads and block two short slots a day to reply.** · effort S · medium confidence
   - Why: 75% of leads contacted within 2 h qualified, against 21% after 24 h, and this week 15 of 22 leads waited more than 24 h. Of all the levers here, this one costs nothing.
   - Expected impact: If half of the slow leads had become fast ones this week, at the observed rates that is roughly 3–4 more demos sent a week. This is an estimate: some of the gap may be because better leads get called first.
   - How to measure: Share of leads with hours_to_contact ≤ 2 (7/22 this week) and the qualified rate of the week's leads, checked 5 days later.
4. **Don't raise total spend. Any budget freed from 9002 can go to 'Reel: owner story' (9001), but only modestly, about +2 EUR a day, and only after rec 1 is done.** · effort S · low confidence
   - Why: 9001 has the best qualified-lead cost (22.12 EUR) and 4 of the 5 wins from ads. Its spend has held at about 54–59 EUR a week, so it is untested at higher budgets. The one sharp budget jump we have (9002) went badly.
   - Expected impact: Small: maybe 1 extra qualified lead a week if 9001 keeps its rate at higher spend.
   - How to measure: 9001's weekly cost per qualified lead stays under about 30 EUR after the increase.
5. **Run the /oferta-b landing page test below, using duplicate ads.** · effort M · low confidence
   - Why: Meta visitors start the form at 2.7%, against 16.5% from search. A landing page built for ad traffic could close part of that gap. The early /oferta-b numbers are too small to judge.
   - Expected impact: If /oferta-b doubles or triples paid form starts, that would mean several more leads a week at the same spend.
   - How to measure: Form starts per session for each ad pair, after about 280 sessions per version.

## Experiments worth running

| Hypothesis | Version B | Metric | Sample per version | Weeks at current traffic |
|---|---|---|---|---|
| Meta visitors who land on /oferta-b, a page built around the offer with the form near the top, start the form much more often than visitors who land on the homepage (2.7% of paid sessions this week). | Duplicate each active ad (9001, 9003, and 9002 at its normal budget). Point the copy at /oferta-b and keep the original pointing at /. Split each ad's budget 50/50 so the total doesn't change. Ship the mobile form fix to both pages first, or neither, so the form doesn't skew the result. | Form starts per session, by landing page (paid:meta only). Track submits and qualified leads too, but only as a secondary check. | 280 | 2 |

## Questions for you

- Who raised the budget on 'Reel: before and after' around 19 Oct, and why? The agent log has nothing. Did its link, audience or placement change at the same time?
- Is the mobile form known to have validation problems, such as phone number format or required fields? 69% of mobile form starts hit an error.
- Who handles first contact with leads, and what slowed it down this week? Average time to first contact went from 22.7 h to 34.1 h.
- What is /oferta-b, where are its direct visits coming from, and is it ready for paid traffic?
- Most of this week's leads (16 of 22) didn't come through an ad, and only 3 qualified so far. Did anything change in search or organic posts?

---
SYNTHETIC data with planted patterns (growth_os/demo.py, seed 7). Written by claude-opus-5-5 in 7 turns, 13 queries, 6 statistical checks, about $0.62. Graded 8/8 against the answer key.
