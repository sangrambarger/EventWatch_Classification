# Merger & Acquisition — decision spec

**Source:** `audit/rules/event-types-manmade.md` § Merger & Acquisition (slide 35)
**Priority:** P4 (response urgency only — never an input to the decision, per `global-rules.md` #3)
**Code:** `audit/logic/merger_acquisition.py` · **Tests:** `audit/tests/test_merger_acquisition.py`

> **Field names in this spec are AUTHOR-DERIVED, not schema-supplied.** The uploaded extraction
> pack covers 35 event types and Merger & Acquisition is not one of them (see
> `audit/EVENT_TYPE_BUILD_ORDER.md`). Every field below is annotated with the source line it
> serves, so a reviewer can check the derivation. From Cyber Attack onward, the supplied
> schema's `must_have` names are used verbatim instead.

## Evidence this decision reads

| Field | Values | Serves which source line |
|---|---|---|
| `story_nature` | `CORPORATE_STRUCTURE_CHANGE` · `DISRUPTION_OR_RISK_SIGNAL` · `ORGANIC_EXPANSION_OR_INVESTMENT` · `RESUMPTION_OR_ALL_CLEAR_ONLY` · `MARKET_COMMENTARY_NO_PHYSICAL_EVENT` · `ENFORCEMENT_AGAINST_ILLICIT_ACTOR` · `RECYCLED_REMINDER_OF_KNOWN_DEVELOPMENT` · `UNKNOWN` | `global-rules.md` #8/#9/#12/#16 |
| `subject_identifiable` | `YES` · `NO` · `UNKNOWN` | `global-rules.md` #13 |
| `deal_stage` | `ANNOUNCED` · `SIGNS_TALKS_OR_PLANS` · `REGULATORY_APPROVAL_PENDING` · `COMPLETED` · `RUMOUR_NO_NAMED_PARTIES` · `UNKNOWN` | "Notify when the initial deal is announced - pre-regulatory approvals" |
| `strict_bar_sector` | `RETAIL` · `CONSULTING_OR_STAFFING` · `HOSPITALITY` · `INVESTMENT_OR_FINANCE` · `INSURANCE` · `CRUDE_OIL` · `MINING` · `NONE` · `UNKNOWN` | "Retail, consulting & staffing, hospitality, investment & Finance group, insurance firm, crude oil, or mining company- Notify if a mapped company/partner is involved." |
| `mapped_or_prominent_party_involved` | `YES` · `NO` · `UNKNOWN` | same line, read through the `global-rules.md` #4 heuristic (no mapping database is available) |
| `product_line_connection` | `CONNECTED` · `NOT_CONNECTED` · `UNKNOWN` | "Product line and applications must be relevant to our verticals. Possible sub-tier or Tier 1 supplier yet to be mapped (decide based on product connection)" |
| `service_sector_applicability` | `APPLICABLE` · `NOT_APPLICABLE` · `NOT_A_SERVICE_SECTOR` · `UNKNOWN` | "If a service sector is involved, check if their services have applications in our industrial verticals - logistics company, cargo shipping, travel, IT firm, agrochemicals, petrochemicals or specialty chemicals, construction, manufacturing, recycling, communications, utility supplier (Electricity, Water, Gas)." |
| `steel_company_involved` | `YES` · `NO` · `UNKNOWN` | "Steel company (only if applications match or a partner is involved)" |
| `steel_applications_match_or_partner_involved` | `YES` · `NO` · `UNKNOWN` | same line |
| `initial_announcement_already_notified` | `YES` · `NO` · `UNKNOWN` | "Do not send completion if the initial announcement has been notified to the customers." |
| `selling_party_is_mapped_partner` | `YES` · `NO` · `UNKNOWN` | "If a mapped partner sells the business, notify it as a business sale." |

## Decision table — evaluated top to bottom, first match wins

| # | Rule | Condition | Outcome |
|---|---|---|---|
| 0 | `GLOBAL.R13` | `subject_identifiable` is `NO` or `UNKNOWN` | **Needs Context Review** — missing `subject_identifiable` |
| 0 | `GLOBAL.R8` | `story_nature` is `UNKNOWN` | **Needs Context Review** — missing `story_nature` |
| — | carve-out | event type is M&A → rule #8's expansion/resumption/commentary short-circuits are **skipped entirely** | continue |
| 1 | `MA.R1` | `deal_stage` = `RUMOUR_NO_NAMED_PARTIES` | **Needs Context Review** — missing `acquirer_or_target_named` |
| 1 | `MA.R1` | `deal_stage` = `UNKNOWN` | **Needs Context Review** — missing `deal_stage` |
| 2 | `MA.R2` | `selling_party_is_mapped_partner` = `YES` | **Reroute to Business Sale** — not decided here |
| 3 | `MA.R3` | `deal_stage` = `COMPLETED` **and** `initial_announcement_already_notified` = `YES` | **Not Impactful** |
| 3 | `MA.R3` | `deal_stage` = `COMPLETED` **and** notification history `UNKNOWN` | **Threshold Review** — missing `initial_announcement_already_notified` |
| — | | `deal_stage` = `COMPLETED` **and** never announced | falls through to rules 4-8 |
| 4a | `MA.R4a` | `strict_bar_sector` ≠ `NONE` **and** `mapped_or_prominent_party_involved` = `YES` | **Impactful** |
| 4b | `MA.R4b` | `strict_bar_sector` ≠ `NONE` **and** mapped = `NO` | **Not Impactful** — even if `product_line_connection` = `CONNECTED` |
| 4c | `MA.R4c` | `strict_bar_sector` ≠ `NONE` **and** mapped = `UNKNOWN` | **Threshold Review** — missing `mapped_or_prominent_party_involved` |
| 5a | `MA.R5a` | `steel_company_involved` = `YES` **and** qualifier = `NO` | **Not Impactful** |
| 5b | `MA.R5b` | steel = `YES` **and** qualifier = `UNKNOWN` | **Threshold Review** |
| 5c | `MA.R5c` | steel = `YES` **and** qualifier = `YES` | **Impactful** |
| 6a | `MA.R6a` | `service_sector_applicability` = `NOT_APPLICABLE` | **Not Impactful** |
| 6b | `MA.R6b` | `service_sector_applicability` = `APPLICABLE` | **Impactful** |
| 7a | `MA.R7a` | `product_line_connection` = `CONNECTED` | **Impactful** |
| 7b | `MA.R7b` | `product_line_connection` = `NOT_CONNECTED` | **Not Impactful** |
| 8 | `MA.R8` | nothing above resolved it (`product_line_connection` = `UNKNOWN`) | **Threshold Review** — missing `product_line_connection`; fail-closed operational default recorded as Impactful |

## Three decisions a reviewer should check hardest

1. **Rule 4b is the biggest workload lever in this module, and the easiest to get wrong.** For the
   six named sectors, the strict bar *replaces* the product-connection test rather than adding to
   it — a retail acquisition with a perfectly good product connection is Not Impactful if no
   mapped company or partner is involved. If that reading is wrong, this module will
   under-report retail, hospitality, finance, insurance, crude oil, mining and
   consulting/staffing deals. The source line is quoted verbatim in the table above; it is worth
   confirming against the slide.

2. **Completion suppression is conditional, and inverted relative to Business Sale.** M&A
   suppresses completion *only when the announcement was already notified*; a completion we never
   announced still gets tested normally. Business Sale does the opposite and reports completion as
   an update. Both behaviours are in the source slides and are deliberately not harmonised.

3. **Rule #8's carve-out is load-bearing.** M&A plus Business Sale was the largest group in a
   216-row sample of real feed data (~14%). If the expansion/"no disruption described"
   short-circuit were allowed to reach this event type, it would delete that entire group and
   present it as a workload win. `test_a_sale_is_not_swallowed_by_the_expansion_carve_out` guards
   this.

## Known open question

`strict_bar_sector` = `UNKNOWN` currently falls through to the general product test (rules 6-8)
rather than going to review, because the source gives no instruction for "sector not
determined". That is the more permissive reading: an unrecognised sector is treated as an
ordinary one. The alternative — routing unknown sector to Threshold Review — would be safer but
would push a large share of rows into the review queue. **Flagged for your decision rather than
settled silently.**
