---
name: eventwatch-impact-audit
description: Re-audits a workbook of EventWatch analyst "Not Impactful" classifications against the Resilinc EventWatch Thresholds & Guidelines, catching cases where an analyst incorrectly downgraded a genuinely critical supply-chain event. Use this whenever the user provides a workbook of feed titles analysts marked Not Impactful (e.g. "NotImpctful Events.xlsx") and wants them re-checked, wants a second opinion on analyst classifications, mentions catching missed/incorrectly-downgraded EventWatch events, or asks to validate/audit/QA a batch of "not impactful" calls before they reach customers. Always use this skill for that task rather than improvising ad hoc keyword rules — the distilled ruleset here was extracted verbatim from the source Thresholds & Guide, Prioritization Matrix, and Industry Definitions documents specifically to avoid inventing or guessing rules.
---

# EventWatch "Not Impactful" Re-Classification Audit

## Why this exists

Analysts clearing a backlog of supply-chain event feeds sometimes mark a genuinely critical
story "Not Impactful" in haste. This has already caused real customer complaints (see
`references/validation_cases.md` for 8 documented real examples — a Ford supplier fire, a
ransomware attack on a Western Digital component supplier, an OFAC sanctions alert on the
Strait of Hormuz, and more, all wrongly downgraded and later re-escalated). This skill re-runs
every "Not Impactful" row through the actual source rules and flags the ones that should be
overturned, with a rationale tied to the specific rule.

**This skill only ever re-audits rows already marked Not Impactful.** Rows already marked
Impactful are out of scope.

**Binary output only.** Every row gets exactly one of two recommended classifications:
Impactful or Not Impactful. When a case is genuinely ambiguous after applying every rule below,
classify **Impactful** — that is the standing safe default (see `references/global-rules.md`
#4). Never invent a third bucket like "maybe" or "needs review" as the classification itself.

## Workflow

### 1. Extract the input

```
python3 scripts/run_audit.py --extract "<path to the workbook>" --out records.json
```

This reads the workbook (auto-detecting the known column names — `Story Title`, `Story
Summary`, `Owner`, `Moved to Not Impactful (Owner)`, `Not Impactful Feedback`, `Event
Classification`, or close variants) and writes one JSON record per row. If it errors because it
can't find a title column, open the workbook and check the actual header row — the schema may
differ from what was described when this skill was built.

**Do not skip or sample rows.** The whole point of this audit is that a skimmed row is exactly
how the original miss happened. Process every record in `records.json`, in full.

### 2. Deduplicate near-identical wire copies of the same event (recommended for large files)

Real production data includes many near-identical wire-service copies of the same underlying
event — the same factory fire or sabotage campaign reported by 3-12 different outlets, each a
separate row. Classifying every copy independently wastes effort and risks inconsistent verdicts
across copies of the same fact pattern (see `references/global-rules.md` #7).

```
python3 scripts/dedup_rows.py records.json --out-representatives dedup_records.json --out-clusters clusters.json
```

This is a purely mechanical, deterministic step (title/summary text-similarity clustering, no
LLM judgment) — it never decides relevance, only groups rows that are near-certainly about the
same event. Classify `dedup_records.json` (one record per unique-event cluster) in the next step
instead of the full `records.json`. It is intentionally biased toward under-merging over
false-merging — see the module docstring in `scripts/dedup_rows.py` for the concrete false-merge
cases found and fixed during development, and treat every dedup-inherited verdict in the final
output (tagged `[Deduplicated: ...]` in its rationale) as spot-checkable, not infallible. Skip
this step for small files where the redundant-effort savings don't matter.

### (Do not use) Triage shortcut — tried, validated against ground truth, rejected

A cheap pre-filter (`references/triage-checklist.md`, `scripts/run_audit.py --triage-split`) was
built to sort rows into Irrelevant/Thin/Candidate before the expensive pass, on the theory that
~45-55% of rows don't need full reasoning. **It was tested against 350 rows with known-correct
answers (from a completed full-classification run) and failed the accuracy bar**: of the rows it
tried to resolve directly, only 71.8% matched the actual correct verdict — a ~28% error rate,
concentrated exactly in the highest-value judgment calls (a real defendant in a new lawsuit vs.
speculative third-party commentary about someone else's case; a genuine M&A event vs. "growth" it
got confused with; Leadership Transition; a real geopolitical event framed through market
reaction). It was also barely cheaper per row than the full pass (~654 vs. ~1,000 tokens), so the
cost case was weak even before the accuracy problem. **Process-owner decision: do not use this
shortcut.** The files remain in the repo, clearly marked, in case a much narrower version is
worth revisiting later — do not resurrect it without re-validating against known-correct answers
first, the way this one was.

### 3. Classify every row (this is the only step that needs your judgment, not the script's)

_(This is the step that matters most — see "Building a skill that really understands the
EventWatch team's requirements" near the end of this file for the full set of judgment patterns
learned from real production runs, beyond what's summarized below.)_

Classify `dedup_records.json` (or `records.json` if you skipped dedup too, for a small file).
Every row gets the same full depth and cost — no shortcut, per the decision above. Cutting
corners on any row is exactly how the original misses happened; that is a worse outcome than the
extra cost.

For each record, read `record["feed_title"]` + `record["story_summary"]` in full — the title
alone is usually too thin to judge whether a disruption is confirmed, ongoing, or genuinely
resolved; the summary is where that lives. Weigh `record["analyst_stated_reason"]` critically:
does it hold up against what the summary actually says, or does it echo the exact failure
pattern in the validation cases (a real disruption dismissed on a technicality)? Do **not**
trust `record["upstream_event_classification"]` as given — one of the 8 known real misses had
the upstream tag wrong too, not just the analyst's downstream call.

Apply, in order:

1. **Read `references/global-rules.md` first, always** — it's short and applies to every row:
   the safe-default-to-Impactful rule, the severity gauge, why priority tiers (P0-P4) are never
   a reason to call something Not Impactful, the mapped/critical-company heuristic (no supplier
   database is available — apply the heuristic instead), the resolved-event rule (never a
   blanket "if it's over, mark NI" — it varies by event type), and — check these before anything
   else, since they short-circuit the whole procedure — rules #8-9: **we report disruptions, not
   expansions, resumptions, or market commentary.** A story about a company growing, investing,
   or announcing expanded capacity, or a follow-up saying operations have simply resumed, or
   financial/crypto market commentary with no described physical event, is Not Impactful
   regardless of company size or industry (Event Type: "Irrelevant / Not a Disruption") — don't
   spend effort on the mapped/critical-company or industry-connection checks for these, since
   there's no disruption to evaluate in the first place. Also check #10-16 for confirmed process-
   owner decisions: Fishing/general-hotels out of scope (except major global QSR chains — #10),
   Uber in scope (#11), Legal Action's materiality floor (#12, a new filing is reportable, a
   templated deadline-reminder isn't), "no connection" requires actually knowing what the story
   is about, not just short text (#13), the "How Company X Could Address Y" template requiring a
   real-defendant check (#14), market-reaction framing of a real event vs. pure market commentary
   (#15), and enforcement action against illicit actors not counting as a disruption to us (#16).
2. **Re-derive Event Type** against the taxonomy in `references/event-types-manmade.md`,
   `references/event-types-natural.md`, and `references/event-types-other.md` — only open the
   one file matching the row's likely category (each has a Contents list at the top; skim that
   before reading the full entry). Several types are explicit redirects (Deforestation,
   Military Drills, Mad Cow Disease, Container Ship Accidents, Software/Internet Outage) —
   resolve to the underlying canonical type they redirect to, not the redirect label itself.
3. **Apply that event type's own Reporting Guidelines** — specifically its DO-report and
   DO-NOT-report criteria, quoted verbatim in that file. This is where most of the real judgment
   happens.
4. **Check industry/product connection** against `references/industries.md` (27 industries,
   authoritative — never invent a 28th; note "Tobacco and E-cigarettes" is explicitly excluded
   despite appearing in the raw pptx, per process-owner decision recorded in that file).
5. Arrive at a verdict: `event_type`, `recommended_classification` (exactly `"Impactful"` or
   `"Not Impactful"`), and a `rationale` — one paragraph, citing the specific rule/criterion you
   applied (not a generic restatement of the title). If the analyst's stated reason is
   contradicted by the summary, say so explicitly in the rationale.

Write all verdicts to a JSON array, one object per record:
```json
[{"row_index": <same value as the record's row_index>, "event_type": "...",
  "recommended_classification": "Impactful", "rationale": "..."}]
```

### 4. Render the output workbook

If you deduplicated in step 2, expand your cluster-level verdicts back out to every original row
(name your step-3 output `cluster_verdicts.json` first):
```
python3 scripts/run_audit.py --expand-verdicts cluster_verdicts.json clusters.json --out verdicts.json
```
(Skip this if you classified `records.json` directly without deduplication — go straight to
`--write` with your verdicts.)

```
python3 scripts/run_audit.py --write verdicts.json "<output path>.xlsx" --records records.json
```

This produces the final formatted workbook (highlighted overturned rows, an aggregate Summary &
Feedback sheet) per the column spec: Feed Title, Analyst Name, Analyst's Original
Classification, Recommended Classification, Event Type, Rationale, Analyst's Stated Reason,
Feedback for Next Run (left blank for the process owner/QA). Hand this file back to the user —
don't just report a summary in chat.

## Validating the ruleset itself

Before trusting this skill against a real production file, or after editing anything in
`references/`, run it against the 8 known real historical misses:

```
python3 scripts/run_audit.py --validate --out validation_records.json
```

Then classify those 8 records exactly as in step 3 above (they're real cases with enough
context to judge, though reconstructed from a downstream complaints log rather than the
original story summary — see the honesty note at the top of `references/validation_cases.md`),
write verdicts, and check:

```
python3 scripts/run_audit.py --check-validate validation_verdicts.json --records validation_records.json
```

All 8 must come back Impactful. If any don't, the gap is in `references/event-types-*.md`, not
in the case — fix the rule text there (re-run `scripts/build_reference_docs.py` first if the
source pptx/docx/pdf changed) rather than special-casing around a single failure.

## Running at scale — what actually drives cost, and what to do about it

A real production run (3,088 rows, one shift's worth of "Not Impactful" calls) cost roughly
1,000 tokens/row end to end when classified via autonomous subagents doing full-depth reasoning
on every row. A cheap pre-filter to skip full reasoning on "obviously irrelevant" rows was built
and tested against known-correct answers — it had a ~28% error rate on exactly the categories
that matter most (see "(Do not use) Triage shortcut" above) and was rejected. **There is
currently no validated way to safely reduce reasoning depth per row.** Full depth on every row is
the floor, not a starting point to optimize down from casually.

The one lever that remains safe — cutting *overhead* around the reasoning, not the reasoning
itself — is keeping the classification pass lean:
- **Batch size**: roughly 200-300 rows per invocation — large enough to amortize the fixed cost
  of reading the reference docs once, small enough that quality doesn't degrade over a very long
  single response.
- **Read reference docs once, at the start, and trust that reading.** Don't re-open
  `event-types-*.md` repeatedly per row beyond what's needed, don't re-read the output file back
  to "double check" — the record-keeping in this skill (row_index matching, the
  `--check-validate` and validation-case machinery) exists so mistakes get caught downstream, not
  so every batch re-verifies itself line by line.
- **Rationale length**: one sentence, citing the specific rule/criterion by name. Not a
  paragraph. The rule citation is what makes it auditable; the prose around it is what makes it
  expensive. This does not mean skipping reasoning — it means not narrating the reasoning at
  length once it's done.
- **No exploratory tool calls beyond reading the reference docs and the input records file.**
  There should be exactly a handful of tool calls per batch (read SKILL.md, read the relevant
  reference files, read records, write verdicts) — if a batch is making many more than that,
  something is being re-checked that doesn't need to be, not something being reasoned through
  more carefully.

Realistically, this lever alone yields a modest reduction (perhaps 20-30%), not an
order-of-magnitude one. Treat a sustained daily volume in the tens of thousands as too expensive
for a subscription-based quota running through Claude Code subagents at *any* achievable
per-row depth this skill validates as safe — that architecture also has inherent per-call
overhead (tool-call loops, file re-reads, session setup) beyond what prompting can remove. If
that volume is a real, recurring requirement, the actual fix is processing rows via the Claude
API directly (ideally the Batch API, cheaper per token and free of agentic overhead) — not
further prompt engineering inside chat-based sessions, and not cutting reasoning depth to make
the current architecture fit an unfitting volume.

## Building a skill that really understands the EventWatch team's requirements

Correctness is the priority here, not speed (process-owner decision, after the triage
experiment's accuracy failure). Beyond the rules already in `references/global-rules.md`, these
are judgment patterns that showed up repeatedly across a real 3,088-row production run —
documented here so they inform every future classification pass, not just something one batch
figured out and the next batch has to rediscover:

- **"How Company X Could/May Address Y Following Z" template titles** (a recurring stock-analysis-
  mill format) require reading closely enough to tell whether X is the actual real defendant/
  litigant in a genuine new legal action (→ Legal Action applies normally) or an unrelated third
  party being speculated about in connection with someone else's case (→ Not Impactful, no new
  legal development for X). This distinction cannot be made from the title alone or from a
  shallow pass — it is exactly the kind of case that needs the full read of `story_summary`.
- **A genuine geopolitical/physical event described through market-reaction framing** ("US-Iran
  clashes drive oil surge, Dow drops 0.7%") is not the same as rule #8's pure market-commentary
  carve-out (a story that is *only* about trading/price movement with no described physical
  event, e.g. the Bitcoin-rally example). If a real conflict, sanction, attack, or disruption is
  described and the market reaction is just color/context around it, classify by the underlying
  event, not by the framing.
- **Law-enforcement or regulatory action against illicit/bad actors** (an illegal-refinery bust,
  a botnet takedown, a raid on counterfeit operations) is not a disruption to a legitimate
  supplier — it's the opposite, authorities disrupting an illegitimate operation. Classify Not
  Impactful for that reason specifically, distinct from any of rules #1-13.
- **Leadership Transition and the sector-specific stricter M&A/Business Sale bar are already
  correctly scoped in the verbatim source text** — Leadership Transition explicitly covers only
  CEO/CFO/COO changes (not General Counsel, CMO, or division-level titles), and M&A/Business Sale
  explicitly requires a mapped/prominent company specifically for retail, consulting/staffing,
  hospitality, insurance/finance, crude oil, and mining (a stricter bar than the general
  product-line-connection test used elsewhere). These aren't gaps to patch — they're there in
  `event-types-manmade.md` already; the point of naming them here is so a future pass trusts that
  specificity instead of re-deriving or second-guessing it.
- **Near-duplicate wire copies with genuinely different subjects** (the same template headline
  applied to different companies, e.g. "FDA Warning Letter to <Company>" sent to five different
  peptide manufacturers) must not be merged by `dedup_rows.py` — see that script's own docstring
  for the specific false-merge bugs found and fixed. If a future dedup run produces a cluster that
  looks like it spans different real-world subjects, that is a bug to fix in the dedup script,
  not a batch to just push through.

## Maintaining the reference docs

`references/*.md` (except `validation_cases.md`) are generated, not hand-authored — see
`scripts/build_reference_docs.py`'s module docstring for why (verbatim fidelity to the source
documents; a pure mechanical reorganization, never a paraphrase). If Resilinc ships a new
version of the Thresholds & Guide, Prioritization Matrix, or Industry Definitions, replace the
source files in the repo root and re-run that script rather than hand-editing the generated
`references/*.md` files directly.
