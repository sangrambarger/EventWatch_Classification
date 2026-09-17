# Chemical Spill — decision spec

**Source:** `audit/rules/event-types-manmade.md` § Chemical Spill (slide 8) · **Priority:** P2
**Schema:** none supplied — fields author-derived · **Code:** `logic/chemical_spill.py`

## The most permissive bar in the ruleset

> "We notify spills and leaks as soon as the news is made public. **Notify even if no sites are
> mapped.** Check the industrial importance of the region, product and services affected"

Mapped status is **not a gate here at all**. The location list is an inclusion list, not an
exclusion list.

| # | Rule | Condition | Outcome |
|---|---|---|---|
| 1 | `CS.R1` | `news_is_public` = `NO` | **Threshold Review** |
| 2 | `CS.R2` | `external_disruption` is any of evacuation / road closure / plant shutdown / water contamination / product scarcity / health advisory | **Impactful** |
| 3 | `CS.R3` | `spill_location` is any named type (industrial unit, warehouse, port, airport, industrial park, mine, logistics hub, train track, medical lab, highway) | **Impactful** |
| 4 | `CS.R4` | location unnamed but `regional_industrial_importance` = `IMPORTANT` | **Impactful** |
| 5 | `CS.R5` | any of the three still `UNKNOWN` | **Threshold Review** |
| 6 | `CS.R6` | unnamed location, no consequence, unimportant region | **Not Impactful** |

**Expect this event type to remove almost nothing.** Rule 6 is the single narrow exit. If a run
shows Chemical Spill removing a large share of its rows, that is an extraction fault or a bug in
this module — not a workload win. The module attaches that warning to every `CS.R6` verdict.
