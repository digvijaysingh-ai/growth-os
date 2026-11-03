# Case studies on real public data

The analyst was run, unchanged, on two real public datasets. The memos are its output as written. Afterwards, the key figures were recomputed straight from the raw CSV files with separate code (not through the hub) to check that nothing was invented.

| Case | Data | Memo | Headline finding |
|---|---|---|---|
| **B2B sales funnel** | Olist marketing funnel: 8,000 leads, 495 landing pages, 842 closed deals; merchants' first 90 days of sales joined from Olist's orders | [olist-memo.md](olist-memo.md) | May's 30-day close rate fell from 10.9% to 7.0% (p=0.0005) across channels, while two sales reps went from 33 closes to 0, which points to sales follow-through rather than lead quality |
| **Paid social** | 1,143 Facebook ads in 3 campaigns, by age, gender and interest | [fbads-memo.md](fbads-memo.md) | 20.4% of all spend goes to women 45–49 in one campaign at 137.76 per buyer, against 30.77 for men 30–34. It also flags that 207 zero-spend ads are credited with 76 buyers, which makes the small campaigns look far cheaper than they are |

| **Funnel + what customers say** | The same Olist funnel plus 3,000 written customer reviews, classified into themes by Claude Haiku 5.5 and joined to how each reviewed merchant was acquired | [olist-voice-memo.md](olist-voice-memo.md) | Merchants acquired through search have happier customers than the baseline (21.7% and 24.5% negative reviews against 30.3%, p=0.0005 and p=0.018) |

### A hypothesis the analyst didn't confirm

Before this run I expected the "unknown" channel, the most valuable one by merchant sales, to bring merchants with unhappier customers: 28.3% negative reviews against 21.7% for organic search. That gap is real (p=0.02), but it was the wrong comparison. The analyst compared each channel with merchants who joined outside the funnel (30.3% negative), found "unknown" no different from that baseline (p=0.39), and reported instead that *search* brings merchants with happier customers. That is the behaviour the tool is built for: test against the right baseline, and don't confirm what someone hoped to find.

## Checked against the raw data

| Claim in the memo | Recomputed from raw CSV |
|---|---|
| April / May leads, 30-day closes | 1,352 / 147 (10.9%) and 1,303 / 91 (7.0%) ✓ |
| Deals closed in the calendar month, April / May | 207 / 122 ✓ |
| Rep 9e4d… and rep 060c… closes, April → May | 24 → 0 and 9 → 0 ✓ |
| 2018 close rate, paid search / social | 175/1,182 and 66/1,051 ✓ |
| 2018 organic search, page 22c298… / f017be… | 105/413 and 12/143 ✓ |
| Landing pages that never produced a deal | 361 of 495 ✓ |
| Zero-spend, zero-click ads credited with conversions | 207 ads, 212 enquiries, 76 buyers ✓ |
| Ads with more enquiries than clicks | 218 ✓ |
| Negative reviews: organic / paid search / outside the funnel / unknown | 97/446, 115/469, 375/1,236, 143/506 (recounted from the hub's labels) ✓ |
| Campaign 1178, women 45–49 | 11,985 spend, 87 buyers, 137.76 per buyer, 20.4% of all spend ✓ |
| Campaign 1178, men 30–34 | 7,476 spend, 243 buyers, 30.77 per buyer ✓ |

## What these show, and what they don't

- **They show** the analyst finds the patterns that matter in real, messy data. It applies significance tests, names selection effects (fields only recorded for won deals, cohorts that have had less time to close) and catches data-quality problems no one asked about.
- **They don't show** business impact: nobody acted on these memos. The recommendations' "expected impact" figures are the analyst's estimates from historical data and are labelled that way. Impact is measured on the live pilot.

## Reproduce

Download the datasets from Kaggle into `data/raw/`: `olistbr/marketing-funnel-olist`, `olistbr/brazilian-ecommerce` and `loveall/clicks-conversion-tracking`. Then:

```bash
growth-os load olist  --raw data/raw --hub state/case-olist.sqlite
growth-os load fbads  --raw data/raw --hub state/case-fbads.sqlite
growth-os analyse --hub state/case-olist.sqlite --until 2018-05-31 --period-days 31 --business "Olist (public data)" --context cases/olist.context.txt --name case-olist
growth-os analyse --hub state/case-fbads.sqlite --business "Facebook ads advertiser (public data)" --context cases/fbads.context.txt --name case-fbads
```

Data credits: Olist marketing funnel and Brazilian e-commerce datasets (Kaggle, CC BY-NC-SA 4.0); "Sales conversion optimization" dataset (Kaggle). Raw files are not redistributed here.
