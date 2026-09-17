# Earthquake — decision spec (both regional variants)

**Sources:** `event-types-natural.md` § Earthquake (JP/TW/KR/PH/ID/CN) slide 14 and
§ Earthquake (Rest of the World) slide 15 · **Priority:** P0
**Schema:** none supplied — fields author-derived · **Code:** `logic/earthquake.py`

One module, two variants selected by `region_variant`, because they share their structure and
differ only in the floor — two near-duplicate files would drift.

| | JP/TW/KR/PH/ID/CN | Rest of World |
|---|---|---|
| Notify straightaway at | **M5.0**+ | **M5.7**+ |
| M5.0 – M5.6 | above the floor | "Closely monitor ... notify only if disruptions observed" |

| # | Rule | Condition | Outcome |
|---|---|---|---|
| 0 | `EQ.R0` | `region_variant` `UNKNOWN` | **Threshold Review** — the floor depends on it |
| 1 | `EQ.R1` | magnitude absent or unparseable | **Threshold Review** — "Check GDACS and USGS" |
| 3a/b/c | `EQ.R3*` | RoW, M5.0–5.6 | Impactful if disruptions observed; Not Impactful if none; Review if unknown |
| 4 | `EQ.R4` | below the variant floor | **Not Impactful** |
| 5a | `EQ.R5a` | `tsunami_alert` = `YES` | **Impactful** |
| 5b | `EQ.R5b` | `epicenter` = `OFF_COAST` | **Impactful** |
| 5c | `EQ.R5c` | `sites_mapped_in_region` = `YES` | **Impactful** |
| 5d | `EQ.R5d` | `important_region` = `YES` | **Impactful** |
| 6 | `EQ.R6` | no sites, but key infrastructure in region | **Impactful**, severity **LOW** (FYI + empty polygon) |
| 7 | `EQ.R7` | any trigger still `UNKNOWN` | **Threshold Review** |
| 8 | `EQ.R8` | every trigger answered `NO` | **Not Impactful** |

## Two things to check

1. **A missing magnitude is not a small magnitude.** It routes to review and never falls through
   to "below threshold".
2. **`radius_km()` is a table lookup, never an estimate.** Both verbatim depth × magnitude tables
   are encoded. Japan/Taiwan uses a materially tighter table than the general one — at M6.3,
   depth 15 miles: **98 km** vs **225 km**. The sibling `eventwatch-analyst-skill` repo built a
   dedicated script for exactly this after a reasoned radius went wrong; its rule is "never
   reason/estimate a radius instead".

**Open question:** rule 5b reads "Epicenter off the coast/Tsunami Alert issued" as *two*
independent triggers (the slash = "or"), so any off-coast epicentre above the floor notifies
even with no tsunami alert and no mapped coastal sites. The stricter reading would require
mapped coastal sites. **Flagged for your ruling.**
