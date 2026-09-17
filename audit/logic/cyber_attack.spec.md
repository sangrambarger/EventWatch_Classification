# Cyber Attack — decision spec

**Source:** `audit/rules/event-types-manmade.md` § Cyber Attack (slide 12) · **Priority:** P1
**Schema:** `audit/schemas/extraction_fields/Cyber_Attack_Extraction_Only_Fields.json` (39 `must_have` fields)
**Code:** `logic/cyber_attack.py` · **Tests:** `tests/test_uncovered_types.py`

> **First schema-backed module.** `incident_nature`, `named_victim_status` and
> `confirmation_status` use the supplied schema's field names and enum values **verbatim**.
> `test_cyber_enum_values_match_the_supplied_schema` fails the build if this module and the
> schema ever drift, so the extractor and the decision cannot disagree about what a value means.
> Only 6 of the 39 `must_have` fields feed the threshold; the rest exist for bulletin drafting.

## Evidence this decision reads

| Field | Values | Source |
|---|---|---|
| `incident_nature` | `CONFIRMED_ATTACK_OR_BREACH` · `VULNERABILITY_ADVISORY_NO_KNOWN_ATTACK` · `ACTIVE_EXPLOITATION_CAMPAIGN_NO_NAMED_VICTIM` · `ALLEGED_OR_UNCONFIRMED_INCIDENT` · `CYBER_DRILL_OR_SIMULATION` | schema, verbatim |
| `named_victim_status` | `SPECIFIC_VICTIM_NAMED` · `MULTIPLE_VICTIMS_NAMED` · `NO_NAMED_VICTIM_VENDOR_OR_PRODUCT_ONLY` | schema, verbatim |
| `confirmation_status` | `CONFIRMED_BY_COMPANY` · `CONFIRMED_BY_AUTHORITY` · `REPORTED_BY_THREAT_ACTOR_OR_THIRD_PARTY` · `ALLEGED_OR_UNDER_INVESTIGATION` · `DENIED_BY_COMPANY` | schema, verbatim |
| `partner_software_attacked` | `YES` · `NO` · `UNKNOWN` | author-derived — "Partner's software attacked? Notify with impact attached" |
| `entity_role` | `SERVICE_PROVIDER` · `MANUFACTURER` · `UTILITY_SERVICES` · `DATA_CENTER` · `FINANCIAL_INSTITUTION` · `COMMUNICATION_SERVICES` · `CARGO_OR_FREIGHT_SERVICES` · `OTHER_SECTOR` | author-derived: the schema's `entity_sector_or_service_role` is free text, which a decision cannot branch on, so the source line's own list is enumerated |
| `industry_connection` | `CONNECTED` · `NOT_CONNECTED` · `UNKNOWN` | author-derived — "serves our customer industries", against the 27 in `industries.md` |

## Decision table — first match wins

| # | Rule | Condition | Outcome | WarRoom |
|---|---|---|---|---|
| 0 | `GLOBAL.*` | gate (thin row, commentary, enforcement-against-illicit-actor, recycled reminder) | per gate | — |
| 0 | `CY.R0` | `incident_nature` `UNKNOWN` | Needs Context Review | — |
| 1 | `CY.R1` | `CYBER_DRILL_OR_SIMULATION` | **Not Impactful** | no |
| 2 | `CY.R2` | `partner_software_attacked` = `YES` | **Impactful** | yes iff confirmed attack |
| 3 | `CY.R3` | `confirmation_status` = `DENIED_BY_COMPANY` | **Threshold Review** | — |
| 4a | `CY.R4a` | vulnerability/exploitation-campaign **and** `industry_connection` = `NOT_CONNECTED` | **Not Impactful** | no |
| 4b | `CY.R4b` | vulnerability/exploitation-campaign, industry **and** role both `UNKNOWN` | **Threshold Review** | — |
| 4c | `CY.R4c` | vulnerability/exploitation-campaign otherwise | **Impactful** | **no** |
| 5 | `CY.R5` | `entity_role` is one of the six named sectors | **Impactful** | yes iff confirmed attack |
| 6a | `CY.R6a` | `industry_connection` = `CONNECTED` | **Impactful** | yes iff confirmed attack |
| 6b | `CY.R6b` | `industry_connection` = `NOT_CONNECTED` | **Not Impactful** | no |
| 7 | `CY.R7` | otherwise | **Threshold Review** | — |

## What a reviewer should check hardest

1. **Rule 4c is why `Decision` has a `warroom_eligible` axis at all.** "Incase of Cyber
   vulnerabilities, send news alerts but DO NOT create a WarRoom. Create a WarRoom only when a
   Cyber Attack actually happens." A vulnerability advisory is therefore **reportable** (so,
   Impactful) while being WarRoom-ineligible. Collapsing the two into one boolean would either
   suppress a reportable alert or open WarRooms the guidelines forbid.
2. **This event type's own rules remove almost nothing.** "Notify all kinds of hacks, breaches,
   ransomware, attacks, and service interruptions" plus "Notify glitches ... vulnerable to cyber
   attacks" is close to notify-always. What actually removes rows is rule 6b, the industry
   connection — in the feed sample this group was dominated by crypto-theft stories, which fail
   because blockchain/crypto is not one of the 27 industries, **not** because of anything in the
   cyber rules. If the funnel shows Cyber Attack removing rows for any other reason, check the
   extraction.
3. **Two branches are author-derived and flagged as such**: the drill/simulation rejection (the
   source does not contemplate a drill, but the schema enumerates one, so it needed an answer)
   and the company-denial review route (the source is silent on denials, so plan guardrail 15
   says mark the gap rather than invent a reading). **Both are open for your ruling.**
