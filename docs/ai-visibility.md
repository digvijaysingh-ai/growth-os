# AI visibility: does an assistant recommend you?

More buyers now ask an AI assistant "which tool should I use?" instead of searching. If the assistant never names you, you are out of the shortlist before any ad or landing page gets a chance. No dashboard shows this, because it never touches your site.

## How it is measured

1. **Questions buyers actually ask**, in their language, written per market (`cases/olist.visibility.toml`). Most are **unbranded**: they don't name any company, so a mention has to be earned. Branded questions ("is Olist worth it?") are tracked separately and left out of share of voice.
2. **Several runs per question.** Assistant answers vary from one run to the next, so each question is asked several times, and every rate is shown with its 95% range.
3. **The assistant searches the live web**, as it does for real users. Claude with the web search tool today; ChatGPT, Gemini and Perplexity plug in behind the same `ask()` once their API keys are available.
4. **Counting is deterministic.** A brand counts as mentioned when its name appears in the answer (exact, word-bounded match, so "tinyurl" is not "Tiny"). Its rank is the order of first mention. Its own site counts as a source when the assistant read or cited it. No model judges another model's answer.
5. **Everything goes to the hub** (`ai_answers`, `ai_mentions`, `ai_citations`, views `v_ai_share_of_voice` and `v_ai_cited_sites`), so the analyst can relate AI visibility to the funnel.

## What it is good for

| Question | Where it shows |
|---|---|
| Are we on the AI shortlist for the questions that matter? | Mention rate per brand on unbranded questions |
| Who is named first? | Mentioned first, average rank |
| Which sites shape the answer? | Sites used as sources: often marketplaces, review sites and blogs, not the brands' own pages, which tells you where to earn mentions |
| Is it getting better? | The same question set run every week; the date is stored with every answer |

## Limits, stated plainly

- One assistant, at one point in time. Results from other assistants will differ.
- A handful of runs per question gives wide ranges. Read the band, not just the bar. Runs of the same question aren't independent of each other, so the 95% band treats them as if they were and is somewhat too narrow. With 5 questions, the honest unit of evidence is closer to 5 than to 15.
- Answers depend on wording. Keep the question set fixed over time, and change it deliberately.
