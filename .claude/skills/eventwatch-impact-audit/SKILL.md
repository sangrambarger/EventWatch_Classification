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
same event. Classify `dedup_records.json` (one record per unique-event cluster) in step 3
instead of the full `records.json`. It is intentionally biased toward under-merging over
false-merging — see the module docstring in `scripts/dedup_rows.py` for the concrete false-merge
cases found and fixed during development, and treat every dedup-inherited verdict in the final
output (tagged `[Deduplicated: ...]` in its rationale) as spot-checkable, not infallible. Skip
this step for small files where the redundant-effort savings don't matter.

### 3. Triage: cheaply separate Irrelevant/Thin rows before the expensive pass (recommended for large files)

**Do this for anything beyond a few hundred rows — it is the single biggest cost lever in this
whole skill.** In real production data, roughly 45-55% of rows turn out to be "Irrelevant"
(expansions, resumptions, market commentary, out-of-scope sectors) or "Thin" (too sparse to
identify at all, which safe-defaults to Impactful without needing any deep lookup). Full
classification — reading all 43 event types' criteria, checking industry connection in depth,
writing a cited rationale — is expensive per row; deciding "is this even a candidate" is not.
Spending full effort on every row uniformly is the main reason this skill is expensive at scale.

Using **only** `references/triage-checklist.md` (do not load `global-rules.md`,
`event-types-*.md`, or `industries.md`'s full definitions for this pass — that defeats the
purpose), sort `dedup_records.json` into IRRELEVANT, THIN, or CANDIDATE per the checklist's exact
output format. Batch aggressively — hundreds of rows per single response is realistic here, since
the checklist is short and the output is terse (no rationale paragraphs, just a short reason
clause). Write the results as a JSON array to `triage.json`.

Then split mechanically (free, no judgment):
```
python3 scripts/run_audit.py --triage-split triage.json --records dedup_records.json \
  --out-verdicts triage_verdicts.json --out-candidates candidate_records.json
```
`triage_verdicts.json` already has fully-formed verdicts for every IRRELEVANT/THIN row — nothing
more to do with those. `candidate_records.json` is what actually needs step 4 below; it should be
substantially smaller than `dedup_records.json`.

Skip this step for small files (a few hundred rows or fewer) where the savings don't justify the
extra pass — go straight from dedup to step 4 with the full `dedup_records.json`.

### 4. Classify every row (this is the only step that needs your judgment, not the script's)

Classify `candidate_records.json` if you triaged in step 3, otherwise `dedup_records.json` (or
`records.json` if you skipped dedup too, for a small file). This step keeps its full depth and
cost per row — that's appropriate here, since triage already filtered out everything that didn't
need it, and cutting corners on a genuine candidate is exactly how the original misses happened.

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
   there's no disruption to evaluate in the first place. Also check #10-12 for three specific
   confirmed decisions: Fishing/general-hotels out of scope, Uber in scope, and Legal Action's
   materiality floor (a new filing is reportable; a law firm's templated deadline-reminder
   press release about an already-known suit is not).
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

### 5. Render the output workbook

If you triaged in step 3, first merge the triage-resolved verdicts with your step-4 classification
verdicts (this only concatenates and checks for accidental double-processing — no judgment):
```
python3 scripts/run_audit.py --merge-verdicts triage_verdicts.json candidate_verdicts.json --out cluster_verdicts.json
```
(Skip this if you didn't triage — your step-4 output already covers every deduped row, just call
it `cluster_verdicts.json`.)

If you deduplicated in step 2, expand your cluster-level verdicts back out to every original row:
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

Then classify those 8 records exactly as in step 4 above (they're real cases with enough
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
uniformly on every row. That does not scale to a daily volume in the tens of thousands — it will
burn a weekly quota on a single day's file. Two things actually move that number, and they are
not the same lever:

1. **Triage first (step 3).** This is a volume cut, not a per-row cost cut: it stops ~45-55% of
   rows from ever reaching the expensive stage at all. Always do this above a few hundred rows.
2. **Keep the classification pass (step 4) itself lean.** Most of the per-row cost isn't the
   reasoning — it's agentic overhead: re-reading files "just in case," re-verifying your own
   output, writing multi-sentence rationales when one clause would do. When invoking this skill
   at scale (e.g. via a subagent per batch), be explicit about all of the following, since none of
   it is automatic:
   - **Batch size**: hundreds of rows per invocation for triage (step 3), on the order of
     200-300 for the classification pass (step 4) — large enough to amortize the fixed cost of
     reading the reference docs once, small enough that quality doesn't degrade over a very long
     single response.
   - **Read reference docs once, at the start, and trust that reading.** Don't re-open
     `event-types-*.md` repeatedly per row beyond what's needed, don't re-read the output file
     back to "double check" — the record-keeping in this skill (row_index matching, the
     `--check-validate` and validation-case machinery) exists so mistakes get caught downstream,
     not so every batch re-verifies itself line by line.
   - **Rationale length**: one sentence, citing the specific rule/criterion by name. Not a
     paragraph. The rule citation is what makes it auditable; the prose around it is what makes it
     expensive.
   - **No exploratory tool calls beyond reading the reference docs and the input records file.**
     There should be exactly a handful of tool calls per batch (read SKILL.md, read the relevant
     reference files, read records, write verdicts) — if a batch is making many more than that,
     something is being re-checked that doesn't need to be.

Even with both levers applied, treat a sustained daily volume in the tens of thousands as likely
still too expensive for a subscription-based quota running through Claude Code subagents — that
architecture has inherent per-call overhead (tool-call loops, file re-reads, session setup) that
a direct API call doesn't. If that volume is a real, recurring requirement, the actual fix is
processing rows via the Claude API directly (ideally the Batch API, which is both cheaper per
token and free of agentic overhead entirely) — not something achievable by further prompt
engineering inside chat-based sessions alone.

## Maintaining the reference docs

`references/*.md` (except `validation_cases.md`) are generated, not hand-authored — see
`scripts/build_reference_docs.py`'s module docstring for why (verbatim fidelity to the source
documents; a pure mechanical reorganization, never a paraphrase). If Resilinc ships a new
version of the Thresholds & Guide, Prioritization Matrix, or Industry Definitions, replace the
source files in the repo root and re-run that script rather than hand-editing the generated
`references/*.md` files directly.
