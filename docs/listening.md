# Listening: what customers and the market say

Warehouses hold what people **did**: clicks, orders, deals. What they **say** sits in reviews, forums, comments and support tickets, and it rarely reaches the warehouse because it is unstructured. The listening module turns it into counted themes that sit next to the funnel data, so the analyst can say *"delivery complaints doubled in the segment whose close rate fell"* rather than just *"close rate fell"*.

## Pipeline

1. **Collect.** A source adapter returns items of one shape: id, day, source, text, rating, segment, category (`growth_os/listening/sources.py`).
2. **Classify.** Claude Haiku 5.5 labels each item with sentiment, one to three themes from a fixed taxonomy, the main pain point in a few English words, and a one-line English paraphrase. It uses structured output, so every label is valid, and the Batch API at half price (`growth_os/listening/classify.py`).
3. **Store.** Only the labels and the paraphrase go into the hub (`voice_items`, `voice_themes`). The original text and anything that identifies its author never do.
4. **Count.** The views `v_voice_themes` and `v_voice_by_segment` give theme volume, average rating and negative share per segment, joinable with the rest of the hub.

A fixed taxonomy, rather than free-form topics, is deliberate. Counts stay comparable week to week and across markets, and a theme that grows is a real change, not the model naming things differently.

## Sources: what is realistically available

Access is where most listening projects fail, so this is stated up front. Terms and prices change; check each one before building on it.

| Source | Access | Use |
|---|---|---|
| Your own reviews, surveys, support tickets, CRM notes | You own them | ✅ The richest source, and the one enterprises most often ignore |
| Reddit | Official API, free with OAuth at low volume; commercial use needs Reddit's agreement | ✅ Candid pain points, competitor mentions |
| Google reviews | Places API returns only a handful of reviews per place | ⚠️ A signal, not a census |
| YouTube comments | Data API with a free daily quota | ✅ "How do I…" questions, objections |
| News, blogs | RSS, GDELT | ✅ Trends and press |
| Bluesky | Open API | ✅ Free; smaller audience |
| X | Read access is a paid tier | ⚠️ Pluggable, off by default |
| Facebook / Instagram | No search of public posts; only your own account's comments, plus limited hashtag search | ⚠️ Own-account only |
| TikTok | Research API is for academic researchers only; organic stats only for your own account | ⚠️ Own-account only |
| Meta Ad Library | Public API, and in the EU it covers all ads | ✅ Competitor ads (a separate module) |

## Governance

- **What the model sees.** The classifier reads the text, after emails, phone numbers, links and long numbers are stripped. Names in free text are not reliably removable, so this step is processing of customer text and belongs in your data agreement.
- **No personal data in the hub.** Item ids are hashes, and the text is replaced by a paraphrase written without names, phone numbers or order numbers.
- **Aggregates, not people.** Themes are counted per segment. There is no profiling of individual authors, and nothing that would let anyone look one up.
- **Platform terms.** Each adapter uses the platform's official API within its terms; no scraping behind logins.

## Run it

```bash
growth-os listen olist --hub state/case-olist.sqlite --sample 3000          # Batch API, half price
growth-os listen olist --hub state/case-olist.sqlite --sample 50 --direct   # quick test without batching
```
