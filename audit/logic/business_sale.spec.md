# Business Sale — decision spec

**Source:** `audit/rules/event-types-manmade.md` § Business Sale (slide 6)
**Priority:** P3 (response urgency only — never an input to the decision, per `global-rules.md` #3)
**Code:** `audit/logic/business_sale.py` · **Tests:** `audit/tests/test_business_sale.py`

> Field names are **AUTHOR-DERIVED**, not schema-supplied — Business Sale is not among the 35
> event types in the uploaded extraction pack. Field names are deliberately shared with
> `merger_acquisition.spec.md` wherever the two rules read the same evidence, so a row rerouted
> from M&A rule 2 can be decided here without being re-extracted.

## Evidence this decision reads

| Field | Values | Serves which source line |
|---|---|---|
| `story_nature` | as in the M&A spec | `global-rules.md` #8/#9/#12/#16 |
| `subject_identifiable` | `YES` · `NO` · `UNKNOWN` | `global-rules.md` #13 |
| `sale_stage` | `ANNOUNCED` · `SIGNS_TALKS_OR_PLANS` · `COMPLETED` · `RUMOUR_NO_NAMED_PARTIES` · `UNKNOWN` | "Notify as soon as it is announced (signs/talks/plans)" and "Send updates on completion news" |
| `mapped_or_prominent_party_involved` | `YES` · `NO` · `UNKNOWN` | "Company mapped? - Send an impact with the initial bulletin." — read through `global-rules.md` #4 |
| `product_line_connection` | `CONNECTED` · `NOT_CONNECTED` · `UNKNOWN` | "Company not mapped? - Send a bulletin if products have applications in the industries we cover." |
| `service_sector_applicability` | `APPLICABLE` · `NOT_APPLICABLE` · `NOT_A_SERVICE_SECTOR` · `UNKNOWN` | "If the service sector is involved - Check if their services have applications in our vertical: logistics provider \| cargo shipping \| petrochemicals \| specialty chemicals provider \| IT company \| utility provider \| farming company" |

Sub-types from the slide (`Sale involving factories/plants`, `Sale involving Company
(mapped/non-mapped)`, `Business unit sale`, `Subsidiary sale`, `Asset sale`, `Brand/portfolio
sale`) are carried for grouping and reporting. **None of them affects the decision** — the source
gives them no differentiated treatment, and inventing one would be rule drift.

## Decision table — evaluated top to bottom, first match wins

| # | Rule | Condition | Outcome |
|---|---|---|---|
| 0 | `GLOBAL.R13` | `subject_identifiable` is `NO` or `UNKNOWN` | **Needs Context Review** |
| 0 | `GLOBAL.R8` | `story_nature` is `UNKNOWN` | **Needs Context Review** |
| — | carve-out | event type is Business Sale → rule #8's short-circuits are **skipped entirely** | continue |
| 1 | `BS.R1` | `sale_stage` = `RUMOUR_NO_NAMED_PARTIES` | **Needs Context Review** — missing `seller_or_buyer_named` |
| 1 | `BS.R1` | `sale_stage` = `UNKNOWN` | **Needs Context Review** — missing `sale_stage` |
| 2 | `BS.R2` | `mapped_or_prominent_party_involved` = `YES` | **Impactful** — no product test needed |
| 3a | `BS.R3a` | `service_sector_applicability` = `APPLICABLE` | **Impactful** |
| 3b | `BS.R3b` | `service_sector_applicability` = `NOT_APPLICABLE` | **Not Impactful** |
| 4a | `BS.R4a` | `product_line_connection` = `CONNECTED` | **Impactful** |
| 4b | `BS.R4b` | `product_line_connection` = `NOT_CONNECTED` | **Not Impactful** |
| 5 | `BS.R5` | `sale_stage` = `COMPLETED` and connection still `UNKNOWN` | **Threshold Review** — missing `product_line_connection` |
| 6 | `BS.R6` | nothing above resolved it | **Threshold Review** — missing `product_line_connection`; fail-closed default recorded as Impactful |

## Where Business Sale deliberately differs from Merger & Acquisition

These three divergences are in the source slides. They are preserved, not harmonised — merging
them would be convenient and wrong, and each has a test asserting the difference.

| | Business Sale (slide 6) | Merger & Acquisition (slide 35) |
|---|---|---|
| **Sector bar** | None. Any sector is reportable on mapped status or product connection. | Six named sectors (retail, consulting/staffing, hospitality, investment/finance, insurance, crude oil, mining) are reportable **only** with a mapped company/partner. |
| **Completion** | Reported — "Send updates on completion news". | Suppressed when the announcement was already notified. |
| **Service vertical list** | 7 entries: logistics, cargo shipping, petrochemicals, specialty chemicals, IT, utility, **farming**. | 11 entries: adds **travel, construction, recycling, communications**; drops farming. |

The service-list divergence has a practical consequence worth flagging: a row about the sale of a
**construction** or **travel** services business resolves to `NOT_APPLICABLE` here but
`APPLICABLE` under M&A. `BS.R3b` attaches a note to every such verdict saying so, so the
divergence is visible on the row rather than buried in a spec.

## Because the bar is lower, the reroute direction matters

M&A rule 2 sends "a mapped partner sells the business" here. That moves the row from a stricter
test to a more permissive one, which is the safe direction. The reverse would not be — nothing in
this module reroutes to M&A.

## Known open questions

1. **`BS.R2` treats "mapped" as sufficient at any stage, including completion.** The source says
   mapped companies get "an impact with the initial bulletin", which presupposes the bulletin
   exists; combined with "send updates on completion news", reporting a mapped company's
   completion follows. If in practice a mapped company's completion should be suppressed the way
   M&A suppresses it, this rule needs a notification-history check like `MA.R3`. **Flagged for
   your decision.**
2. **The service list divergence** above may be a genuine intent difference between the two
   slides or a drafting artefact of the source deck. Encoded as written; worth a ruling.
