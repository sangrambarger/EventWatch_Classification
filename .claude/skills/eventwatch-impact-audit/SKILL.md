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

### 2. Classify every row (this is the only step that needs your judgment, not the script's)

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
   database is available — apply the heuristic instead), and the resolved-event rule (never a
   blanket "if it's over, mark NI" — it varies by event type).
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

### 3. Render the output workbook

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

Then classify those 8 records exactly as in step 2 above (they're real cases with enough
context to judge, though reconstructed from a downstream complaints log rather than the
original story summary — see the honesty note at the top of `references/validation_cases.md`),
write verdicts, and check:

```
python3 scripts/run_audit.py --check-validate validation_verdicts.json --records validation_records.json
```

All 8 must come back Impactful. If any don't, the gap is in `references/event-types-*.md`, not
in the case — fix the rule text there (re-run `scripts/build_reference_docs.py` first if the
source pptx/docx/pdf changed) rather than special-casing around a single failure.

## Maintaining the reference docs

`references/*.md` (except `validation_cases.md`) are generated, not hand-authored — see
`scripts/build_reference_docs.py`'s module docstring for why (verbatim fidelity to the source
documents; a pure mechanical reorganization, never a paraphrase). If Resilinc ships a new
version of the Thresholds & Guide, Prioritization Matrix, or Industry Definitions, replace the
source files in the repo root and re-run that script rather than hand-editing the generated
`references/*.md` files directly.
