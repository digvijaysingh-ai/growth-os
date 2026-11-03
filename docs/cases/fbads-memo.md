# Growth memo · Facebook ads advertiser (public data) · whole dataset (undated)

**Campaign 1178 spends 20.4% of all budget (11,985 spend units) on women aged 45-49, at 137.76 per buyer. Men aged 30-34 in the same campaign cost 30.77 per buyer, and moving that budget toward younger and male audiences is the clearest way to get more buyers for the same spend.**

> **Data:** Directional, not proven. Volume is large where the money goes: campaign 1178 has 625 ads, 36,068 clicks, 2,669 enquiries and 872 buyers. Age, gender and campaign-level gaps are statistically clear. Four limits keep this at 'directional'. (1) There are no dates, so I can't see trends, saturation over time or a previous period, and the 'weeks' in the experiments assume the whole dataset is one 7-day period. (2) Attribution is loose. 207 ads with zero spend and zero clicks still got credited with 212 enquiries and 76 buyers, and 218 ads show more enquiries than clicks. So some of the conversions credited to ads don't depend on spend, and small ads look far cheaper than they really are. (3) The data is observational: Meta's delivery chose who saw each ad, so the gaps between segments are correlations, not proven effects of targeting. (4) Single interest cells hold only a few buyers, and the worst cells were picked after the fact, so cell-level numbers will partly regress toward the mean. Interest names are not available.

| KPI | This period | Previous | Note |
|---|---|---|---|
| Spend | 58,705.23 spend units | n/a | Campaign 1178 = 55,662.15 (94.8%), 936 = 2,893.37, 916 = 149.71 |
| Buyers (approved) | 1,079 | n/a | 1178: 872, 936: 183, 916: 24. Includes 76 credited to ads with zero spend. |
| Cost per buyer | 54.41 | n/a | 1178: 63.83, 936: 15.81, 916: 6.24. The cheap campaigns are cheap mostly because their ads are tiny (see findings). |
| Enquiries (conversions) | 3,264 | n/a | Cost per enquiry 17.99 |
| Enquiry-to-buyer rate | 33.1% | n/a | Similar across segments (28-38%). The big gaps are before the enquiry, not after it. |
| Clicks / CTR / CPC | 38,165 clicks / 0.0179% / 1.538 | n/a | From 213,434,828 impressions |

## What happened

- **Age drives cost per buyer: it rises steadily from 30-34 to 45-49** (high confidence). Campaign 1178, cost per buyer by age: 30-34 = 37.43 (14,786 spend, 395 buyers); 35-39 = 64.10; 40-44 = 78.88; 45-49 = 112.71 (19,049 spend, 169 buyers). Buyers per click: 1.33% (169/12,715) for 45-49 vs 4.32% (395/9,140) for 30-34. compare_rates: different at 95% confidence, p<0.001. The same order holds in campaign 936: 4.45 per buyer at 30-34 vs 46.34 at 45-49. The age band with the most spend is the least efficient one.
- **Women cost more per buyer than men, mainly because fewer of their clicks become enquiries** (high confidence). Campaign 1178: women 81.98 per buyer (32,052 spend, 391 buyers), men 49.08 (23,610 spend, 481 buyers). Buyers per click: women 1.76% (391/22,193) vs men 3.47% (481/13,875), different at 95% (p<0.001). Women's clicks are cheaper (CPC 1.44 vs 1.70), but not by nearly enough to make up for this. After an enquiry the gap is smaller: women 30.1% (495/1,644) vs men 36.0% (584/1,620) become buyers, still different at 95% (p=0.0003).
- **Women 45-49 in campaign 1178 are the biggest leak: 20.4% of all spend for 8% of buyers** (high confidence). 1178 women 45-49: 11,985 spend, 8,468 clicks, 308 enquiries, 87 buyers, 137.76 per buyer. 1178 men 30-34: 7,476 spend, 243 buyers, 30.77 per buyer. Buyers per click: 1.03% vs 5.70%, different at 95% (p<0.001). The women 45-49 ads with 150+ spend each run at 145.2 per buyer (9,439 spend, 65 buyers). The men 30-34 ads with 150+ spend each hold at 31.9 (4,240 spend, 133 buyers). So the efficient segment did not visibly saturate as ads grew, within the range we observed.
- **Interest matters, mostly among people aged 35+; interest 27 is the worst large one** (medium confidence). Campaign 1178: interest 27 costs 113.10 per buyer (4,864 spend, 43 buyers), and 203.7 at ages 35+ (3,463 spend, 17 buyers). Interest 29 costs 43.34 (4,768 spend, 110 buyers). Buyers per click 1.34% vs 3.54%, different at 95% (p<0.001). Interests 16 and 10 work well at 30-34 (21.7 and 24.4 per buyer) but poorly at 35+ (104.5 and 105.6). Across 1178, the 15 age×gender×interest cells with at least 300 spend and at least 150 per buyer took 9,701.6 spend for 35 buyers (277.2 per buyer). That cell-level figure was picked after the fact, so expect some regression to the mean.
- **Campaigns 936 and 916 look cheap because their ads are tiny, and scaling them would probably not stay cheap** (medium confidence). Zero-spend ads were credited with 212 enquiries and 76 buyers. In 936, ads under 10 spend: 739.7 spend, 93 buyers. Ads with 10+ spend: 2,153.7 spend, 25 buyers (86.15 per buyer), worse than 1178's 10+ spend ads at 66.50 (55,257.8 spend, 831 buyers). In 936, buyers per click fall from 17.0% (93/546) to 1.74% (25/1,438), different at 95%. Cost per buyer in 936 rises with spend per ad: 7.95 under 10, 57.88 at 10-50, 193.9 at 50-150. Do not shift 1178 budget into 936 expecting 15.81 per buyer.
- **After an enquiry, the share that buys is fairly stable, so the gaps come from targeting, not from the sales follow-up** (medium confidence). Enquiry-to-buyer rates range from about 28% to 38% across age×gender groups: women 45-49 28.1% (112/399) vs men 30-34 36.8% (299/812), different at 95% (p=0.0025). Click-to-enquiry rates in 1178 range from 3.64% (women 45-49) to 15.83% (men 30-34), a much bigger spread.

## What to do next

1. **In campaign 1178, cut the women 45-49 budget by about half (around 6,000 spend units). Start with the large ads (150+ spend each, 145.2 per buyer). Give the freed budget to men 30-34 ad sets, and to interests 29, 16, 10 and 15 at age 30-34. Total spend stays the same.** · effort S · medium confidence
   - Why: This moves money from 137.76 per buyer (145.2 on the large ads) to a segment at 30.77 that held 31.9 per buyer even on 150+ spend ads. The gap is significant (buyers per click 1.03% vs 5.70%).
   - Expected impact: Rough upper bound: about 41 buyers lost (6,000/145.2) and about 188 gained (6,000/31.9), so roughly +147 buyers, about +14% on 1,079. Even if the new money costs twice the current rate (about 64 per buyer), the net is still around +50. This is an estimate from observational data, not a forecast.
   - How to measure: Each week, track cost per buyer and total buyers for 1178, split by age×gender. Run it as the first experiment below, with the women 45-49 budget split, before committing the full shift.
2. **Pause or cap campaign 1178 ads in interest 27 for ages 35+, and in the worst cells (at least 300 spend and at least 150 per buyer). Move that money to the same 30-34 and male segments.** · effort S · medium confidence
   - Why: Interest 27 at 35+ costs 203.7 per buyer (3,463 spend, 17 buyers). The 15 worst cells took 9,701.6 spend for 35 buyers. Some of this overlaps with the women 45-49 cut, so don't count it twice.
   - Expected impact: Frees about 3,500 spend units at interest 27 (35+) that currently buys 17 buyers. At the 1178 30-34 rate of 37.43 per buyer, the same money could buy about 90 buyers, before any diminishing returns.
   - How to measure: Compare buyers and cost per buyer for the moved budget against the paused cells' history. Re-check after one cycle and switch any cell back on if its replacement does no better.
3. **Do not scale campaigns 936 or 916 on their headline cost per buyer. If they get more money, cap spend per ad at roughly 10 units and add more small ads instead of raising budgets on existing ones.** · effort S · medium confidence
   - Why: Their low cost per buyer comes from tiny ads and from conversions credited to zero-spend ads. Ads in 936 with 10+ spend cost 86.15 per buyer, worse than 1178.
   - Expected impact: Avoids wasting reallocated budget. The upside of adding small ads is unproven and probably limited by the attribution floor.
   - How to measure: Track cost per buyer by spend-per-ad band each week. Make sure the zero-spend credit is excluded when judging these campaigns.
4. **Keep 30-34 women running, but treat them as second priority after 30-34 men. Women 35+ should get only the budget needed to keep testing.** · effort S · medium confidence
   - Why: In 1178, 30-34 women cost 48.09 per buyer, better than any 35+ group except men 35-39 (52.29), but worse than men 30-34 (30.77).
   - Expected impact: Small. Mainly avoids cutting a segment that is still reasonably efficient.
   - How to measure: Cost per buyer by age×gender in the weekly report.

## Experiments worth running

| Hypothesis | Version B | Metric | Sample per version | Weeks at current traffic |
|---|---|---|---|---|
| Moving budget from women 45-49 to men 30-34 in campaign 1178 at least doubles buyers per spend unit. | A: half of the current 1178 women 45-49 budget stays on women 45-49 (same interests and ads). B: the other half goes to men 30-34 ad sets with the same creative and interests 29/16/10/15. Equal budgets, run at the same time. | Buyers (approved) per click, then cost per buyer | 481 | 1 |
| For ages 35+ in campaign 1178, interest 29 brings more buyers per click than interest 27. | A: interest 27, ages 35-49. B: interest 29, same ages, genders, creative and budget. | Buyers (approved) per click | 768 | 1 |

## Questions for you

- What dates does this data cover? Without dates I can't see trends or saturation, and the experiment timings assume the dataset is one 7-day period.
- Why do ads with zero spend and zero clicks get credited with enquiries and buyers (212 enquiries, 76 buyers)? Are these view-through or a reporting artefact? This changes how much the small campaigns 936 and 916 can be trusted.
- Is a 45-49 buyer worth more than a 30-34 buyer (order value, repeat purchases)? If so, part of the higher cost per buyer may be justified, and the reallocation should be judged on revenue rather than buyer count.
- What do campaigns 1178, 936 and 916 differ in (objective, bidding, creative, timing)? Campaign 1178 is the only one that was scaled.
- Can you share the interest names behind ids 27, 29, 16, 10 and 15, so new audiences can be built around the ones that work?

---
Real public data: Kaggle Sales conversion optimization dataset. Written by claude-opus-5-5 in 12 turns, 12 queries and 8 statistical checks. Key figures were then recomputed from the raw CSVs with independent code; see docs/cases/README.md.
