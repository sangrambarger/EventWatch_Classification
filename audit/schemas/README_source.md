# EventWatch Extraction Schemas — Package Contents

**35 event types · 2525 fields** — 31 schemas built in this engagement, 4 baseline schemas supplied at the start and included for completeness.

## Folder structure

| Folder | Contents |
|---|---|
| `01_Extraction_Only_Fields_JSON/` | The schema files. **This is what the extraction script consumes.** |
| `02_Field_Guides_for_Data_Science/` | Field-by-field explanation of why each field exists, with real bulletin titles as examples. Every guide includes dedicated company-mapping and geofencing sections. |
| `03_Field_Rationales/` | The governance trail — which rule in the rulebook, playbook, WarRoom geometry table, geofence-mapper or Thresholds PDF forced each field — plus honest evidence gaps and cross-type boundary notes. |

## Format contract

Every schema has exactly three top-level keys, in this order: `must_have`, `good_to_have`, `less_important`. Each is a **flat** map of `field_name` → type string. No nesting, no arrays-of-objects; a repeating field is typed `"array (repeats per entry)"`. No field name ends in `_raw`.

Schemas built in this engagement additionally **exclude** `article_title`, `source_url` and `source_type`, per the standing instruction. The four baseline schemas still contain those three fields — see Notes.

## Inventory

| Event type | must | good | less | total | Guide | Rationale | 3-tier flat | excl. fields absent | no `_raw` | `company_name` |
|---|---|---|---|---|---|---|---|---|---|---|
| Airport Disruption *(baseline)* | 38 | 26 | 5 | 69 | — | — | yes | — | yes | — |
| Bankruptcy *(baseline)* | 38 | 27 | 5 | 70 | yes | — | yes | — | yes | — |
| Bribery Corruption | 32 | 18 | 5 | 55 | yes | yes | yes | yes | yes | — |
| Business Spinoff | 31 | 19 | 5 | 55 | yes | yes | yes | yes | yes | — |
| Company Split | 34 | 19 | 5 | 58 | yes | yes | yes | yes | yes | — |
| Compliance | 34 | 17 | 5 | 56 | yes | yes | yes | yes | yes | — |
| Corporate Restructuring *(baseline)* | 31 | 23 | 5 | 59 | yes | yes | yes | — | yes | — |
| Counterfeit | 33 | 15 | 5 | 53 | yes | yes | yes | yes | yes | — |
| Cyber Attack | 39 | 18 | 5 | 62 | yes | yes | yes | yes | yes | — |
| Environmental Hazard | 60 | 17 | 5 | 82 | yes | yes | yes | yes | yes | yes |
| Extreme Weather | 63 | 17 | 5 | 85 | yes | yes | yes | yes | yes | yes |
| FDA EMA OSHA Action | 36 | 17 | 5 | 58 | yes | yes | yes | yes | yes | — |
| Factory Disruption | 39 | 37 | 5 | 81 | yes | — | yes | yes | yes | — |
| Financial Distress | 42 | 17 | 5 | 64 | yes | yes | yes | yes | yes | — |
| Fine | 42 | 17 | 5 | 64 | yes | yes | yes | yes | yes | — |
| Flood | 71 | 17 | 5 | 93 | yes | yes | yes | yes | yes | yes |
| Force Majeure | 43 | 17 | 5 | 65 | yes | yes | yes | yes | yes | — |
| Forest Fire | 67 | 17 | 5 | 89 | yes | yes | yes | yes | yes | yes |
| Geopolitical | 48 | 17 | 5 | 70 | yes | yes | yes | yes | yes | — |
| Human Health | 64 | 17 | 5 | 86 | yes | yes | yes | yes | yes | yes |
| Hurricane Typhoon Post Landfall | 68 | 17 | 5 | 90 | yes | yes | yes | yes | yes | yes |
| Hurricane Typhoon Pre Landfall | 65 | 17 | 5 | 87 | yes | yes | yes | yes | yes | yes |
| Labor Disruption | 52 | 17 | 5 | 74 | yes | yes | yes | yes | yes | — |
| Labor Violation | 53 | 17 | 5 | 75 | yes | yes | yes | yes | yes | — |
| Legal Action | 50 | 17 | 5 | 72 | yes | yes | yes | yes | yes | — |
| Mine Shutdown | 54 | 17 | 5 | 76 | yes | yes | yes | yes | yes | — |
| Port Disruption *(baseline)* | 43 | 25 | 5 | 73 | — | — | yes | — | yes | — |
| Price Fluctuation | 48 | 17 | 5 | 70 | yes | yes | yes | yes | yes | yes |
| Profit Warning | 45 | 17 | 5 | 67 | yes | yes | yes | yes | yes | yes |
| Protest Riot | 51 | 17 | 5 | 73 | yes | yes | yes | yes | yes | yes |
| Recall | 50 | 17 | 5 | 72 | yes | yes | yes | yes | yes | yes |
| Regulatory Change | 56 | 17 | 5 | 78 | yes | yes | yes | yes | yes | yes |
| Supply Shortage | 58 | 17 | 5 | 80 | yes | yes | yes | yes | yes | yes |
| Tornado | 57 | 17 | 5 | 79 | yes | yes | yes | yes | yes | yes |
| Volcano | 63 | 17 | 5 | 85 | yes | yes | yes | yes | yes | yes |
| **Total** | | | | **2525** | | | | | | |

## Notes

**1. The four baseline schemas contain the excluded fields.** `Corporate_Restructuring`, `Bankruptcy`, `Airport_Disruption` and `Port_Disruption` were supplied at the start of the engagement and each still carries `article_title`, `source_url` and `source_type`. Every schema built since excludes all three. If the pipeline expects consistency across the set, these four need the three fields stripped — a one-line change per file, not a rebuild.

**2. Guides without a JSON in this package (4).** Business Sale, Chemical Spill, Earthquake, and a combined Factory Fire / Airport / Port guide. These were written against schemas supplied separately; the guides are included because they carry the mappable-organisation analysis — companies, ports, airports, utilities, rail and logistics operators.

**3. JSONs without a guide (2).** Airport Disruption and Port Disruption — baseline schemas, guides not yet written.

**4. `company_name` coverage.** Present in every schema built from the Price Fluctuation round onward. Earlier schemas use role-specific names only (for example `acquiring_company_name`, `recalling_company_name`). A retrofit across the earlier set is available on request.

**5. Tracker hygiene — applies to every event type.** The `Type` column contains case and whitespace variants that silently split single event types in two. Confirmed in this corpus:

| Label | Variant counts | Loss if filtered on exact string |
|---|---|---|
| Hurricane/Typhoon | `Hurricane/Typhoon` 1,017 · `Hurricane / Typhoon` 305 | 23% |
| Forest Fire | `Forest Fire` 338 · `Forest fire` 68 | 17% |
| Factory Fire | `Factory Fire` 13,231 · `factory fire` 2 · `Factory FIre` 1 | <1% |
| Protest/Riot | `Protest/Riot` · `Protest / Riot` | — |
| FDA/EMA/OSHA Action | `FDA/EMA/OSHA Action` · `FDA / EMA / OSHA Action` | — |

Normalise by lowercasing **and** collapsing whitespace around punctuation — case-only normalisation does not catch the Hurricane/Typhoon split. `Country` carries the same problem (`United States of America` vs `USA`; `Russia` vs `Russian Federation`), as does `Material` (bullet and tab artefacts).

**6. Two event types share one tracker label.** Hurricane/Typhoon (Pre-Landfall) and (Post-Landfall) are separate event types in the governance set — different Supplier Impact rules, different geometry, a documented hard handoff — but the tracker has one label for both. The pre/post distinction must be derived from content; there is no ground truth for either phase until a labelled set is built.
