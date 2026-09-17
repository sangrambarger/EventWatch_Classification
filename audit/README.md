# EventWatch workload-reduction classifier & audit

Per-event-type reporting logic, distilled local classifiers, and a workload-reduction audit
dashboard. See the plan's structure in `EVENT_TYPE_BUILD_ORDER.md` for why event types are built
in the order they are.

## Layout

| Path | What it is |
|---|---|
| `rules/` | Verbatim extracts of the approved Thresholds & Guide, Prioritization Matrix and Industry Definitions, copied from the `eventwatch-impact-audit` skill. **Generated upstream — never hand-edit.** |
| `schemas/extraction_fields/` | The 35 supplied per-event-type extraction schemas (`must_have` / `good_to_have` / `less_important`). Names the evidence a decision may read. |
| `logic/` | One `<event_type>.py` + `<event_type>.spec.md` per event type. The `.py` is a pure function over extracted evidence; the `.spec.md` is the same decision as a reviewable table. |
| `tests/` | One test module per event type, covering every branch including DO-NOT-report ones. |
| `data/raw/<period>/` | Feed chunks as uploaded. |

## The contract every logic module honours

`decide(fields) -> Decision`, where `Decision` carries the classification, the **verbatim source
line it fired on**, the evidence that satisfied it, and — for a review outcome — the **named
missing field**. See `logic/base.py` for why each of those is enforced at construction rather
than left to convention.

A decision module never reads a title or summary, never calls a model, and never matches
keywords. Contextual reading happens upstream in extraction; what happens here is a pure
function that Product and Data Science can read as a table and diff as a code change.

## Run

```bash
pip install pytest
python3 -m pytest audit -q
```
