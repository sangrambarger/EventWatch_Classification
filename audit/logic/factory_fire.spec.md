# Factory Fire — decision spec

**Source:** `audit/rules/event-types-manmade.md` § Factory Fire (slide 19) · **Priority:** P2
**Schema:** none supplied — fields author-derived · **Code:** `logic/factory_fire.py`

## The rule that defines this event type

> "Report factory fires proactively. We report a factory fire, even if the articles say it is a
> small fire or has been extinguished."

`fire_status` (`ACTIVE`/`EXTINGUISHED`/`UNDER_INVESTIGATION`/`RECOVERED`) and `fire_scale`
(`MINOR`/`SIGNIFICANT`/`EXPLOSION`) are recorded as evidence and have **no rejecting branch at
all**. Neither does `site_relation` — "Fire/explosion at a neighboring facility" and "Fire just
outside the facility" are both in-scope sub-types. This is the event type `global-rules.md` #5
names when it forbids a blanket "the disruption is over, so mark Not Impactful" shortcut.

## The six-fallback connection cascade — each step rescues the one before

| # | Rule | Condition | Outcome |
|---|---|---|---|
| 1 | `FF.R1` | `partner_site_involved` = `YES` | **Impactful** |
| 2 | `FF.R2` | `product_line_connection` = `CONNECTED` | **Impactful** |
| 3 | `FF.R3` | `indirect_supplier` = `YES` | **Impactful** |
| 4 | `FF.R4` | `service_sector_applicability` = `APPLICABLE` | **Impactful** |
| 5 | `FF.R5` | `utility_or_service_region_has_mapped_sites` = `YES` | **Impactful** |
| 6 | `FF.R6` | `affected_region_has_major_infrastructure` = `YES` | **Impactful** |
| 7 | `FF.R7` | `neighbouring_evacuations` = `YES` | **Impactful** |
| 8 | `FF.R8` | **any** cascade step still `UNKNOWN` | **Threshold Review**, naming each unanswered step |
| 9 | `FF.R9` | every step answered `NO` | **Not Impactful** |

Step 3 is the one most easily lost: "If applications do not have a connection to our verticals?
Check if its an indirect supplier, if yes, notify." A module that stopped at step 2 would drop
rows the source explicitly rescues. Step 5 asks about the region **served** by an affected
utility, not the region of the fire.

Rule 8 is the safety property: an unanswered step is not a negative answer (`global-rules.md`
#13), so the row cannot be dropped on an incomplete cascade.
