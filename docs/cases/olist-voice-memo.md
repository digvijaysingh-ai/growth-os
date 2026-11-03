# Growth memo · Olist (public data) with customer reviews · 2018-05-01 to 2018-05-31

**May produced 130 closed deals against 183 in April. The drop is real and not just because May's leads are younger: the share of leads closed within 30 days started falling in the second half of April (13.1% down to 7.6%). Lead volume and channel mix hardly changed, and in the same weeks several reps stopped appearing on won deals, so the first thing to check is sales coverage, not marketing.**

> **Data:** Directional, not proven. Lead counts are large enough (about 1,300 a month) for solid conclusions on close rates by month, channel and landing page, and the April-vs-May drop is statistically clear (p=0.0005). But there is no spend data, so no cost per lead or cost per deal. There are no contact timestamps, so response speed can't be measured. Rep (sdr/owner), sector and lead type exist only for won deals: they can show when a rep stopped closing deals, but not how many leads each rep was given or why deals are won. The 90-day merchant value is incomplete for recent cohorts (75 of May's 130 deals have it), and one merchant (75,730 BRL, 'unknown' channel) dominates value totals. The month-to-month comparison uses a fixed 'closed within 30 days' window so April and May leads get the same time to close. Note the brief's 'previous period' (Mar 31-Apr 30, 1,362 leads) is one day off calendar April (1,352); this memo uses calendar April.

| KPI | This period | Previous | Note |
|---|---|---|---|
| Leads (MQLs) | 1,303 | 1,352 | -3.6%. Volume is flat, so it does not explain the fall in deals. |
| Closed deals from the month's leads (to date) | 130 | 183 | -29%. Part of this is May's leads being younger, but see the 30-day figure below. |
| Close rate (to date) | 9.98% | 13.54% | Statistically significant drop (p=0.0045). |
| Deals closed within 30 days of the lead | 91 (7.0%) | 147 (10.9%) | Same 30-day window for both months, so this is a fair comparison: -36%, p=0.0005. By half-month: Apr 1-15 13.1%, Apr 16-30 8.8%, May 1-15 7.4%, May 16-31 6.5%. |
| Won merchants selling within 90 days | 36 of 75 with full 90-day data (48%) | 79 of 155 (51%) | May's 90-day data is incomplete. The share is similar; the absolute count is down because there are fewer deals. |
| Search leads (organic + paid) | 610 | 621 | Steady. The search channels' 30-day closes still fell: organic 45→29, paid 36→21. |
| Social leads | 269 | 325 | Lower-converting channel. 30-day closes 13→4. |
| Email leads | 94 | 50 | Nearly doubled, but only 2 won (3 in April). |

## What happened

- **The fall in closings started mid-April and is not explained by younger leads** (high confidence). Closed within 30 days: Apr 1-15 86/655 (13.1%) vs Apr 16-May 31 152/2,000 (7.6%), p<0.001. May vs April: 91/1,303 vs 147/1,352, p=0.0005. Every May lead has had at least 5 months to close by the November 2018 data end, and the 30-day window is fully observed for both months.
- **Channel mix does not explain it: close rates fell inside each main channel** (high confidence). Applying April's 30-day close rate per channel to May's lead mix predicts about 144 deals, close to April's actual 147. May actually got 91. Within-channel 30-day closes, April→May: organic 45/349→29/344, paid search 36/272→21/266, social 13/325→4/269, direct 11/75→5/78. 'Unknown' held best (29/166→24/154).
- **Several reps stop appearing on won deals in late April, the same time the close rate fell** (medium confidence). Qualifying reps 068066e2 (81 wins all-time, last won lead Apr 20) and a8387c01 (59 wins, last won lead Apr 25) together qualified 40 of April's 183 wins and 0 of May's. Closing rep 9e4d1098 closed 18 April-lead deals and 0 May-lead deals (last lead Apr 25). Rep d3d1e91a dropped from 22 to 6 (last lead May 16). Limitation: rep fields exist only for won deals. We can't see how many leads these reps were given, so this is a strong hint about sales capacity, not proof.
- **Search brings deals and merchants who sell. Social and email convert far worse** (high confidence). Close rate for leads since Jan 2018: paid search 175/1,182 (14.8%) vs social 66/1,051 (6.3%), p<0.001, and vs email 14/347 (4.0%), p<0.001. Organic 255/1,736 (14.7%); 'unknown' 168/813 (20.7%). 90-day merchant sales per lead: paid search about 61 BRL, organic about 51, social about 12, email about 18. 'Unknown' is about 155, but one merchant at 75,730 BRL makes up 59% of that channel's all-time value. Won paid-search merchants sell within 90 days more often than organic ones: 74/135 (55%) vs 80/200 (40%), p=0.008. Merchant mix or onboarding may contribute. Without spend we can't say whether social or email are worth their cost.
- **For search leads, landing page 22c29808 closes far better than e492ee and f017be** (medium confidence). Search-lead close rate since 2018: 22c29808 125/521 (24.0%) vs f017be 16/155 (10.3%), p=0.0002, and vs e492ee 7/108 (6.5%), p<0.001. In May, f017be and e492ee still received 36 and 40 leads (all channels). This is observational: the pages may serve different keywords or audiences, so it needs a controlled test before a full switch. The two social pages are no different on 30-day closes (58326e 15/464 vs 88740e 10/285, both about 3%).
- **Merchants from search do not create unhappy customers. Customer reviews are better than the baseline** (medium confidence). Negative review share: organic-acquired merchants 97/446 (21.7%) and paid-search 115/469 (24.5%) vs merchants who joined outside the funnel 375/1,236 (30.3%), p=0.0005 and p=0.018. 'Other' channel is worse at 22/46 (47.8%, p=0.012), but those reviews come from only about 4 won merchants, so treat it as low confidence. The top complaint themes overall are not_delivered (12.7% of reviews) and wrong_or_missing_item (8.9%).

## What to do next

1. **This week, find out whether reps 068066e2, a8387c01, 9e4d1098 (and d3d1e91a) left, moved or lost their lead queue after mid-April. Reassign their open MQLs and rebalance the queue so every new lead is picked up.** · effort S · medium confidence
   - Why: The 30-day close rate fell from 13.1% to 7.6% at the same time these reps stopped appearing on wins. Lead volume and channel mix didn't change.
   - Expected impact: If 30-day close returns to the early-April 13.1% on about 1,300 leads a month, that is about 70 more deals a month than at 7.6%. Even half the gap is about 35.
   - How to measure: Weekly 30-day close rate per weekly lead cohort, tracked against the 13.1% early-April benchmark.
2. **Re-contact the unclosed late-April and May MQL backlog (about 1,790 leads: 1,173 from May plus 616 from Apr 16-30). Start with search, 'unknown' and referral leads. Do it as the controlled re-contact test below.** · effort M · medium confidence
   - Why: Those cohorts were probably under-worked during the coverage gap. Search and 'unknown' leads close at 15-21% when worked normally.
   - Expected impact: Recovers part of the roughly 56 deals May fell short of what April's channel rates predict (about 144 expected vs 91 actual within 30 days).
   - How to measure: Won within 30 days of re-contact, re-contacted half vs held-out half (see experiment).
3. **While capacity is short, order the SDR queue by channel: paid/organic search, 'unknown', referral and direct first; social, email, display and other last.** · effort S · high confidence
   - Why: Close rates since 2018: search about 14.8%, 'unknown' 20.7% vs social 6.3% and email 4.0%. Paid-search merchants also sell more often within 90 days (55%).
   - Expected impact: Each SDR hour spent on search leads produces about 2-3x the deals of an hour on social, and 3-4x email.
   - How to measure: Deals per SDR per week, and 30-day close rate by channel.
4. **Send paid-search traffic currently landing on f017be / e492ee to landing page 22c29808, as a split test first (separate ads or ad groups per page).** · effort S · medium confidence
   - Why: Search leads on 22c29808 close at 24.0% vs 10.3% (f017be) and 6.5% (e492ee). This is observational, so confirm before a full switch.
   - Expected impact: If even half the gap holds, the 76 May leads on those two pages would bring about 5-7 more deals a month.
   - How to measure: Leads per click and 30-day close rate per page in the test.
5. **Check list quality and targeting on the email channel, which nearly doubled to 94 leads but closed 2. Hold social and email volume flat until spend figures are available.** · effort S · medium confidence
   - Why: Email closes at 4.0% and social at 6.3% vs about 15% for search. More of these leads uses up SDR time when capacity is already short.
   - Expected impact: Frees SDR time for higher-converting leads. Cost savings depend on spend we can't see.
   - How to measure: Email/social share of SDR-touched leads and their close rate; cost per deal once spend is shared.

## Experiments worth running

| Hypothesis | Version B | Metric | Sample per version | Weeks at current traffic |
|---|---|---|---|---|
| Unclosed late-April and May leads were under-worked during the rep gap. A structured re-contact cadence will lift their 30-day close rate. Sized on the 7.6% vs 13.1% gap between the later and early-April cohorts. | B: a randomly chosen half of the unclosed Apr 16-May 31 backlog gets a fresh SDR call-plus-email cadence. A: the other half stays in the normal queue. | Deals closed within 30 days of assignment | 476 | 1 |
| Paid-search leads that land on 22c29808 close at a higher rate than those landing on f017be (observed 24.0% vs 10.3%). | B: paid-search ads point to landing 22c29808. A: matching ads point to f017be. Same keywords and budget split 50/50. | Close rate of paid-search leads within 30 days (also leads per click) | 119 | 4 |

## Questions for you

- Did reps 068066e2, a8387c01 and 9e4d1098 leave or change role around Apr 20-25? Where did their leads go? Was d3d1e91a off after mid-May?
- Can you share how many leads each SDR was assigned (not just won), and the contact timestamps? Then we can measure response speed and coverage directly.
- What do social, email and paid search cost per month? Without spend we can't judge whether social (6.3% close) and email (4.0%) are worth funding.
- What keywords or audiences feed landing pages f017be and e492ee vs 22c29808? Can paid-search ad groups be re-pointed for a test?
- What is behind the 'unknown' utm_source? It closes best (20.7%), and if it is a partner or outbound source it may be worth growing.

---
Real public data: Olist marketing funnel, e-commerce orders and customer reviews (Kaggle, CC BY-NC-SA 4.0). 3,000 reviews classified by claude-haiku-5-5 (0.07 USD). Memo written by claude-opus-5-5 in 10 turns, 11 queries and 11 statistical checks.
