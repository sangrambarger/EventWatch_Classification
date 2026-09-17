# Event-type build order — derived from real feed volume

Per the plan, per-event-type logic is built in descending order of real-world volume, so the
earliest modules remove the most rows from the analyst queue.

## Method

Sample: every 5th row by `RowID` from `audit/data/raw/2026-09-07/batch_*.csv` — **216 of 1,079
rows (20%)**, spread evenly across the whole shift rather than taken from one batch. Each title
was read and assigned its closest EventWatch event type by hand against
`audit/rules/event-types-*.md`. This is a **volume estimate for sequencing only** — it is not a
classification ground truth and no dashboard figure is derived from it. The real labels come from
the teacher pass (plan Part B).

Caveat: a 20% sample gives roughly ±3-4 rows of noise on any single type, so ranks within a band
(e.g. the 11-14 band) are not meaningfully separated. The bands are what drive the order, not the
exact counts.

## Observed distribution (216-row sample)

| Rank | Event type | Sample rows | ~% of sample | Notes |
|---|---|---|---|---|
| 1 | **Merger & Acquisition + Business Sale** | ~30 | 14% | Largest single group. Both are P3/P4 and carry a **stricter** threshold (mapped/prominent company required for retail, consulting/staffing, hospitality, insurance/finance, crude oil, mining). High volume + strict bar = the biggest reduction opportunity in the file. |
| 2 | Airport Disruption | ~25 | 12% | **Heavily inflated by one event** — ~17 of the 25 are wire copies of the Amazon cargo crash at Miami. Real distinct-event volume is far lower; this is a dedup story more than a threshold story. |
| 3 | Geopolitical | ~14 | 6% | Tariffs, sanctions, strikes on infrastructure, diplomatic incidents. |
| 4= | Factory Fire | ~13 | 6% | Carries the "report even if small or extinguished" rule. |
| 4= | Labor Disruption | ~13 | 6% | Strikes, threatened strikes, called-off strikes (which invert to Not Impactful). |
| 4= | Cyber Attack | ~13 | 6% | Confirmed breach vs vulnerability advisory vs crypto-theft commentary. |
| 4= | Legal Action / Fine / Compliance | ~13 | 6% | Where `global-rules.md` #12 and #14 do the heavy lifting. |
| 8 | Flood + Extreme Weather | ~12 | 6% | |
| 9= | Leadership Transition | ~11 | 5% | P4. Source text limits it to CEO/CFO/COO only — not GC, CMO or division heads. |
| 9= | Protest / Riot | ~11 | 5% | |
| 11 | Environmental Hazard | ~7 | 3% | |
| 11 | Corporate Restructuring / Layoffs | ~7 | 3% | |
| 13 | Bankruptcy + Financial Distress | ~6 | 3% | |
| 13 | Supply Shortage | ~6 | 3% | |
| 15 | Power Outage | ~5 | 2% | |
| 15 | Recall | ~5 | 2% | |
| 17 | Factory Disruption | ~4 | 2% | |
| 18 | Human Health | ~3 | 1% | |
| 19 | Volcano, Mine Shutdown, Port Disruption | ~2 each | 1% each | |
| 20 | Forest Fire | ~1 | <1% | |
| — | **No event type — noise/commentary** | **~15** | **7%** | Market commentary, "final day of operation", trade-body policy statements, unrelated crime. These die at Stage 1 and never reach a threshold rule. |

## Build order

1. **Merger & Acquisition + Business Sale** — top volume, strictest bar, biggest reduction. Built
   as one module pair because the source rules cross-reference each other ("If a mapped partner
   sells the business, notify it as a business sale").
2. **Cyber Attack** — second build, chosen deliberately to exercise the extraction-schema path
   (see the gap below): it has the richest supplied schema, 39 `must_have` fields.
3. Geopolitical → Factory Fire → Labor Disruption → Legal Action → Flood/Extreme Weather →
   Leadership Transition → Protest/Riot, then the tail in the order above.

## Finding: the supplied schema pack does not cover the top-volume type

`audit/schemas/extraction_fields/` holds 35 schemas. The rulebook covers ~43 event types. The
types with **no supplied extraction schema** include, notably:

- **Merger & Acquisition** ← rank 1
- **Business Sale** ← rank 1
- **Leadership Transition** ← rank 9
- **Factory Fire** ← rank 4
- **Chemical Spill**
- **Power Outage** ← rank 15
- **Earthquake** (both regional variants)
- Layoffs, Airworthiness, Mail/Postal Delivery Disruptions, Others

So for the first module the evidence-field list is **derived from the verbatim reporting
guidelines, not supplied by the approved schema pack**. Every such field is annotated in the spec
with the source line it came from, and the spec flags itself as author-derived so a reviewer knows
which fields carry schema authority and which do not. Where a schema exists (Cyber Attack
onwards), its `must_have` names are used verbatim so the two artefacts stay reconcilable.

## Redirects preserved

`Military Drills` → Geopolitical, `Container Ship Accidents` → Port Disruption, `Mad Cow Disease`
→ Regulatory Change / Human Health, `Software/Internet Outage` → Power Outage, `Deforestation` →
Forest Fire / Regulatory Change / Environmental Hazard / Protest-Riot. These resolve to the
canonical type; no logic module is written for a redirect label.

`Restricted Access` is a cross-cutting sourcing rule, not an event type, and gets no module.
