# Triage Checklist — NOT CURRENTLY USED — see SKILL.md before touching this

> **Do not use this file in the normal workflow.** It was built to cheaply pre-filter rows before
> full classification, then validated against 350 rows with known-correct answers (from a
> completed full-classification run) — it was only 71.8% accurate on the rows it tried to resolve
> directly (a ~28% error rate), concentrated in exactly the highest-value judgment calls (real
> defendant vs. third-party speculation in lawsuit-template titles, M&A vs. "growth," Leadership
> Transition, geopolitical events framed through market reaction). It was also barely cheaper per
> row than the full pass (~654 vs. ~1,000 tokens). Process-owner decision: rejected in favor of
> full-depth classification on every row — see SKILL.md's "Running at scale" section. This file
> is kept for the record and in case a much narrower version is worth building and re-validating
> later; do not resurrect it without testing against known-correct answers again, the way this
> version was tested.

---

Purpose: before spending full per-row reasoning (reading all 43 event types' DO/DON'T criteria,
checking industry connection in depth, writing a cited rationale) on every row, sort rows into
three buckets using ONLY this short checklist. Do not read `global-rules.md`,
`event-types-*.md`, or `industries.md`'s full definitions for this pass — that's the whole
point: this pass is deliberately shallow and fast, and only the rows that need the deep pass get
it. Batch as many rows as reasonably fit into a single response — this checklist plus terse
output is short enough that hundreds of rows per call should be practical, unlike the full
classification pass.

## The three outcomes

For each row, decide exactly one of:

### IRRELEVANT
The row is Not Impactful for a reason that doesn't require checking the 43 event types or
industry sub-sector detail at all:
- **Expansion/growth/investment with no disruption** — a company growing, investing, expanding
  capacity, confirming new operations. (Example: "Chevron to double production in Venezuela.")
- **Resumption-only follow-up** — a later story whose only content is "operations have now
  resumed / back to normal," with no new disruption information.
- **Financial/crypto market commentary** — trading/price/yield analysis with no described
  physical or operational event. (Example: "Bitcoin rally tested by Treasury yields.")
- **Recycled legal-notice/deadline-reminder or "How Company X Could/May Address Y Following Z"
  stock-analysis-mill template** — a law firm's reminder of an already-known lawsuit's deadline,
  or a speculative "third party may be affected by someone else's suit" filler article. Not a
  new filing, ruling, or settlement.
- **Out-of-scope sector, clearly identified, no stated connection to any of the 27 industries
  below** — commercial fishing, general hotels/restaurants (**except** major global QSR/restaurant
  chains — confirmed: Starbucks, McDonald's, KFC, and comparably large global chains, which ARE
  in scope), cannabis, primary/secondary education, general municipal/public administration,
  charities/nonprofits. If the story ties the sector to one of the 27 industries anyway (e.g. a
  hotel's *construction* project, a university's material-testing *lab*), that's not this
  bucket — send it to CANDIDATE instead, the connection needs the deeper pass to evaluate
  properly.
- **Tobacco/E-cigarettes** with no other stated vertical connection.

If IRRELEVANT, output: `{"row_index": ..., "triage_result": "IRRELEVANT", "event_type": "Irrelevant / Not a Disruption" | "Irrelevant / Out of Scope Industry", "reason": "<one short clause>"}`

### THIN (safe-default to Impactful, no deeper pass needed)
The row is so sparse — no company, no location, no industry, no identifiable subject at all
(e.g. a bare "structure fire" headline with nothing else) — that there is genuinely nothing to
evaluate. This is NOT the same as IRRELEVANT: you can't identify what it's about, so you cannot
conclude it has no connection to a covered industry. Per the safe-default rule, this resolves
directly to Impactful without needing the full event-type/industry lookup.

Do not use this bucket for a row you *can* identify but are merely unsure about after a real
connection check — that's CANDIDATE (the deep pass is designed for exactly that judgment call).
THIN is only for "there is nothing here to judge."

If THIN, output: `{"row_index": ..., "triage_result": "THIN", "event_type": "Impactful / Insufficient Information (Safe Default)", "reason": "<what's missing>"}`

### CANDIDATE
Everything else — a real, identifiable event that might connect to one of the 27 industries or
match one of the 43 event types, where the actual classification depends on the kind of detail
only the full reference docs capture (which event type, what the specific DO/DON'T criteria say,
whether the company is prominent/connected enough, whether the disruption is resolved in a way
that matters for that specific type). Send these to the full classification pass unchanged.

If CANDIDATE, output only: `{"row_index": ..., "triage_result": "CANDIDATE"}` — no event_type or
reason needed yet, the full pass will determine those.

## The 27 industries (names only — see `industries.md` for full definitions, needed only for the
full classification pass, not triage)

Aerospace, Agrochemicals, Automotive, Biotechnology, Construction, Consumer Electronics,
Cosmetics & Skincare, Defense, Food & Beverage, Freight, Furnishing Goods, General Manufacturing,
Healthcare, High Tech, Industrial Chemicals, Insurance & Finance, Life Sciences, Natural
Resources & Mining, Oil & Gas, Packaging, Power & Energy, Public Transportation, Research &
Development (R&D), Retail, Software as a Service (SaaS), Telecommunications, Textile.

## Confirmed carve-ins (in scope despite looking like an excluded category)

- **Uber** (ride-hailing, Uber Eats, Uber Freight collectively) — always CANDIDATE at minimum
  (in practice: Impactful for any genuine operational story — layoffs, market exit,
  restructuring — regardless of business line named).
- **Major global QSR/restaurant chains** (Starbucks, McDonald's, KFC, and comparably large
  global chains) — CANDIDATE, not IRRELEVANT, despite the general restaurant/hospitality
  exclusion.

## Output format

One JSON object per input row, as a JSON array, in this exact shape (fields vary slightly by
`triage_result` as shown above — CANDIDATE rows omit `event_type`/`reason`):
```json
[{"row_index": ..., "triage_result": "IRRELEVANT"|"THIN"|"CANDIDATE", "event_type": "...", "reason": "..."}]
```
Do not skip any row. Do not write a rationale paragraph — the `reason` field is a single short
clause, not a cited explanation; that level of detail is for the full classification pass on
CANDIDATE rows only.
