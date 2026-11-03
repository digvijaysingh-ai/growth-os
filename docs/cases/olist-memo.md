# Growth memo · Olist (public data) · 2018-05-01 to 2018-05-31

**May lead volume held steady (1,303 vs 1,352 in April), but the share of leads that closed within 30 days fell from 10.9% to 7.0%, a real drop and not just a timing effect. It hit every main channel, and closings by month fell from 207 to 122 while two closers who had 33 April closes recorded none in May, so the problem looks like sales follow-through more than lead quality.**

> **Data:** Directional, not proven. There are about 1,300 leads a month, which is enough to see month-level changes in close rate (the April vs May 30-day close rate passes the significance test, p=0.0005). It is not enough to rank most landing pages or channel-and-page pairs: 361 of 495 pages have never produced a deal. Closed deals are recorded through 2018-11-14, so a 30-day close window is fully observed for every cohort. That makes it the fair way to compare months; the raw counts (130 May wins vs 183 April) are not. Owner, sector, SDR, lead type and profile only exist for closed deals (even the SDR field is filled only on won leads), so they can't explain why deals close. There is no spend, contact-time or website data, so cost per deal, speed to lead and on-page behaviour can't be measured. 90-day merchant sales are known for only 75 of 130 May deals (155 of 183 for April).

| KPI | This period | Previous | Note |
|---|---|---|---|
| Marketing qualified leads | 1,303 | 1,352 (Apr 1-30; 1,362 in the brief's Mar 31-Apr 30 window) | Flat, down about 4%. Social fell from 325 to 269 and email rose from 50 to 94; search held steady. |
| Leads closed within 30 days | 91 (7.0%) | 147 (10.9%) | This is the like-for-like measure. The drop is significant (p=0.0005), and May is also below Jan-Mar 2018 (9.15%, p=0.018). |
| Closed deals from the cohort so far | 130 | 183 | Not like-for-like: older cohorts have had longer to close. May's count has had through Nov 2018 to accumulate. |
| Deals closed during the calendar month (any cohort) | 122 | 207 | Sales output fell 41% while the number of active closers went from 11 to 12. |
| Closed within 14 days | 75 | 116 | Fast closes fell most: the sales team converted fewer fresh leads quickly. |
| Won merchants selling within 90 days | 36 of 75 with full 90-day data (48%) | 79 of 155 (51%) | Of the deals we can measure, about half sell within 90 days in both months. May's figure is incomplete. |

## What happened

- **The May close rate drop is real, not a timing effect** (high confidence). The 30-day close rate went from 147/1,352 = 10.9% (April) to 91/1,303 = 7.0% (May): compare_rates says different, p=0.0005, -36%. May is also below the Jan-Mar 2018 average of 306/3,343 = 9.15% (p=0.018). Every cohort's 30-day window is fully observed (last recorded close 2018-11-14).
- **The decline is across channels, which points to the sales side rather than lead mix** (medium confidence). 30-day close rate, April vs May: paid search 36/272 (13.2%) to 21/266 (7.9%), p=0.044, different. Organic search 45/349 (12.9%) to 29/344 (8.4%), p=0.057, directional. Social 13/325 to 4/269, too little data. The unknown channel held at 29/166 to 24/154. Volume by channel barely moved apart from social (down) and email (up), so the channel mix doesn't explain the drop.
- **Sales closing output fell sharply in May, partly from two closers going quiet** (medium confidence). Deals closed during the calendar month fell from 207 (April) to 122 (May). Owner 9e4d… closed 24 in April and 0 in May; owner 060c… closed 9 and then 0, which accounts for 33 of the 85-deal drop. Most other owners also closed fewer (e.g. 4ef15… 33 to 18, fbf4… 21 to 7). Two owners new to the April/May figures closed 11 and 13. Caveat: owner is only recorded on won deals, so we can't see how many open leads each rep held. This explains volume, not each rep's skill.
- **Search and the 'unknown' channel bring merchants who close and sell; social and email mostly don't** (high confidence). 2018 close rate: paid search 175/1,182 = 14.8% vs social 66/1,051 = 6.3% (compare_rates: different, p<0.001). Won merchants already selling within 90 days, per 100 leads: unknown 7.6, paid search 6.3, direct 5.5, organic 4.6, social 2.1, email 1.4. Average 90-day sales per won merchant (all time): unknown 832 BRL, paid search 512, organic 433, social 232. Email leads almost doubled in May (50 to 94) and only 1 closed within 30 days.
- **Within organic search, landing page matters: 22c298… closes about three times better than f017be…** (medium confidence). 2018 organic leads: page 22c298… 105/413 = 25.4% vs f017be… 12/143 = 8.4%, compare_rates different (p<0.001). Page e492ee… had 4/85 = 4.7%; the tool flags that as too little data to tell (it wants about 46 wins-worth of sample per arm), but e492ee… also has only 10 wins from 291 leads all time. Pages are not randomly assigned, so part of the gap may be intent from different search terms.
- **Within paid search, page 40dec9… closes better than the other pages** (medium confidence). 2018 paid-search leads: 40dec9… 48/217 = 22.1% vs all other pages 127/965 = 13.2%, compare_rates different (p=0.0008). Not randomised, so this is a test candidate rather than a proven cause.
- **The two social landing pages may differ, but there is too little data to tell** (low confidence). 2018 social leads: 58326e… 24/464 = 5.2% vs 88740e… 25/285 = 8.8%. compare_rates: directional only, p=0.053; it would take about 785 leads per page to confirm. In May, 58326e… took 221 leads and closed 4 within 30 days.

## What to do next

1. **Run a recovery sweep on May search and unknown-channel leads that haven't closed: reassign the open leads of the two closers who had no May closes (9e4d…, 060c…) and set a rule that every search or unknown lead gets a sales touch within its first 14 days.** · effort S · medium confidence
   - Why: Lead volume and channel mix held, but fast closes fell from 116 to 75 and monthly closings from 207 to 122. Those are signs of a capacity or follow-through gap, not a demand gap. Search and unknown leads close at 13-16% vs about 6% for social, so they repay sales time best.
   - Expected impact: Bringing the 30-day close rate back from 7.0% toward the Jan-Mar level of 9.15% on about 1,300 leads a month would add roughly 28 closed deals a month. With about half of measured won merchants selling within 90 days, that is around 14 more selling merchants.
   - How to measure: Track the June cohort's 30-day close rate overall and for search and unknown leads, against May (7.0%) and Jan-Mar (9.15%). Track monthly closings against 207 (Apr) and 122 (May).
2. **Make search and unknown-channel leads the top of the sales queue. Social and email leads move to a lighter-touch track (e.g. a self-serve demo link first, then a call only if they engage).** · effort S · medium confidence
   - Why: Social leads close at 6.3% vs 14.8% for paid search (significant), and produce 2.1 vs 6.3 selling merchants per 100 leads. Email leads (doubled to 94 in May) produce 1.4 selling merchants per 100 leads. Spending equal sales time on all leads wastes capacity at a moment when capacity seems to be the constraint.
   - Expected impact: Frees sales hours equivalent to about 360 social and email leads a month for the higher-yield queue. That should raise wins per rep without adding marketing spend.
   - How to measure: Compare wins per active closer per month, and the search and unknown 30-day close rate, before and after the change. Watch the social and email close rate to make sure it doesn't fall below its current ~6% and ~3%.
3. **Add a prominent link or redirect from the weak organic pages (f017be…, e492ee…) to the layout and offer of page 22c298…, or rebuild them to match it. Keep the old versions so the change can be undone.** · effort M · low confidence
   - Why: Within organic search, 22c298… closes 25.4% vs 8.4% for f017be… (significant). Together the two weak pages took 76 leads in May.
   - Expected impact: If those pages' leads closed even at the organic average (about 15%) instead of 5-8%, that would mean roughly 5 more deals a month. Treat this as an upper-bound guess, because some of the gap comes from searcher intent.
   - How to measure: Compare the organic-search close rate on those pages before and after the change, at 30 days after the lead date. Organic search can't be split into a clean A/B test, so pair this with the paid-search test below.
4. **Stop increasing email lead generation until it is shown to close. Email leads went from 50 to 94 in May with 1 closed within 30 days.** · effort S · medium confidence
   - Why: Email has a 3.0% all-time close rate and 1.4 selling merchants per 100 leads. Growing it mostly adds sales workload.
   - Expected impact: Small direct effect on wins, but it removes about 40-90 low-yield leads a month from the queue.
   - How to measure: Email leads per month and the email 30-day close rate.

## Experiments worth running

| Hypothesis | Version B | Metric | Sample per version | Weeks at current traffic |
|---|---|---|---|---|
| Paid-search traffic sent to page 40dec9… closes at a higher rate than the same traffic sent to the pages it lands on now (13.2% vs 22.1% observed, not randomised). | Duplicate each paid-search ad group that now points to another page. Version B's ads send traffic to 40dec9…, with the same keywords and an even budget split. The site is cookieless, so the test runs as separate ads. | Share of leads closed within 30 days of the lead date (secondary: share of won merchants with sales within 90 days) | 283 | 11.3 |
| Social leads are cheaper to close through page 88740e… than 58326e… (8.8% vs 5.2%, directional only). | Point half of the social ads at 88740e… instead of 58326e…. Note the volume problem: about 785 leads per version are needed, and at roughly 62 social leads a week that is about 25 weeks, too long to finish this quarter. Run it only if social volume rises, or accept it as a slow background test. | Share of leads closed within 30 days | 785 | 25.3 |

## Questions for you

- Did closers 9e4d… and 060c… leave, change role or stop taking leads in May? Between them they closed 33 deals in April and none in May.
- Can we get contact and demo timestamps for every lead, not just won ones? Speed to lead is the most likely cause of the fast-close drop, and right now we can't see it.
- Who owns the 'unknown' channel (1,099 leads, best close rate at 16.3% and best merchant sales at 832 BRL per won merchant)? If we can identify the source, we can grow it.
- What drove the jump in email leads (50 to 94) and the drop in social leads (325 to 269) in May? Was anything changed on purpose?
- Is there spend data per channel? Without it we can only rank channels by close rate and merchant sales, not by cost per closed deal.

---
Real public data: Olist marketing funnel and e-commerce datasets (Kaggle, CC BY-NC-SA 4.0). Written by claude-opus-5-5 in 10 turns, 12 queries and 10 statistical checks. Key figures were then recomputed from the raw CSVs with independent code; see docs/cases/README.md.
