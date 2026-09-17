"""Earthquake threshold logic — both regional variants.

Source: `audit/rules/event-types-natural.md` § Earthquake (Japan/Taiwan/S.Korea/Philippines/
Indonesia/China) (slide 14) and § Earthquake (Rest of the World) (slide 15).
Priority: P0. **No supplied extraction schema** — fields are author-derived (see
`audit/EVENT_TYPE_BUILD_ORDER.md`).

The two variants share their structure and differ only in the magnitude floor, so they are one
module with a `region_variant` field rather than two near-duplicate files that could drift:

| | Regional (JP/TW/KR/PH/ID/CN) | Rest of World |
|---|---|---|
| Notify straightaway at | **M5.0** and above | **M5.7** and above |
| M5.0 – M5.6 | already above the floor | "Closely monitor ... notify only if disruptions observed" |

This is the first module with **numeric** thresholds rather than enums, and the first where the
source supplies a deterministic geometry table. Two consequences:

1. **Magnitude is a float, and a missing magnitude is not a small magnitude.** An unparseable or
   absent magnitude routes to review; it never falls through to "below threshold".
2. **The WarRoom radius is a table lookup, never an estimate.** `radius_km()` implements the two
   verbatim depth × magnitude tables from the slides. The sibling `eventwatch-analyst-skill`
   repo learned this the hard way and built a dedicated script for it after a reasoned radius
   went wrong; the rule there is "never reason/estimate a radius instead", and it is honoured
   here by reading the table.

The "no sites mapped" branches do **not** reject. The source says to send a LOW FYI News and
save an empty polygon when the region is an important manufacturing country, or when it holds
important infrastructure. So an unmapped region is a severity question, not a reportability one.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    IMPACTFUL,
    LOW,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    RuleConflict,
    evidence,
    get,
)
from .global_gate import apply_global_gate

EVENT_TYPE_REGIONAL = "Earthquake"
SOURCE_REGIONAL = (
    "rules/event-types-natural.md § Earthquake (Japan/Taiwan/S.Korea/Philippines/Indonesia/China)"
    " (slide 14)"
)
SOURCE_ROW = "rules/event-types-natural.md § Earthquake (Rest of the World) (slide 15)"
#: Module-level source for the dispatch contract. This module serves two slides, so each Decision
#: cites the variant-specific source above; this names both for callers that inspect the module.
SOURCE = f"{SOURCE_REGIONAL}  ||  {SOURCE_ROW}"

YES_NO = frozenset({"YES", "NO"})

REGION_VARIANT = frozenset({"JP_TW_KR_PH_ID_CN", "REST_OF_WORLD"})
EPICENTER = frozenset({"ON_LAND", "OFF_COAST"})

#: Magnitude floors, verbatim: "Notify Magnitude 5.0 or above straightaway" (regional) and
#: "Notify Magnitude 5.7 or above straightaway" (RoW).
FLOOR = {"JP_TW_KR_PH_ID_CN": 5.0, "REST_OF_WORLD": 5.7}

#: "Closely monitor M5.0 – M5.6 (notify only if disruptions observed)" — RoW only.
ROW_MONITOR_BAND = (5.0, 5.6)

MUST_HAVE_FIELDS = (
    "region_variant",
    "magnitude",
    "depth_miles",
    "epicenter",
    "sites_mapped_in_region",
    "important_region",
    "tsunami_alert",
    "disruptions_observed",
    "important_infrastructure_in_region",
)

_REGIONAL_NOTIFY = (
    "Notify Magnitude 5.0 or above straightaway when:- Epicenter on land and sites mapped in the "
    "region- Epicenter on land, no sites mapped but an important region- Epicenter off the coast "
    "and sites mapped in the coastal regions- Epicenter off the coast/Tsunami Alert issued"
)
_ROW_NOTIFY = (
    "Notify Magnitude 5.7 or above straightaway when:- Epicenter on land and sites mapped in the "
    "region- Epicenter on land, no sites mapped but an important region- Epicenter off the coast "
    "and sites mapped in the coastal regions- Epicenter off the coast/Tsunami Alert issued"
)
_ROW_MONITOR = "Closely monitor M5.0 – M5.6 (notify only if disruptions observed)"
_NOT_ALL = (
    "We do not notify all earthquakes. Alerting happens based on the following thresholds "
    "provided by Resilinc"
)
_FYI_MANUFACTURING = (
    "If no sites are mapped, but an important manufacturing country, send a LOW FYI News and save "
    "an empty polygon"
)
_FYI_INFRASTRUCTURE = (
    "If no sites are mapped, but important infrastructure in the region including, but not limited "
    "to, ports, airports, power plants, dams, major border crossings, etc., send a LOW FYI News "
    "and save an empty polygon"
)

# --- WarRoom radius tables (verbatim from the two slides) --------------------------------------
# Rows are depth bands in MILES (as the slides label them); columns are magnitude bands.
# Kept as data rather than interpolated, because the slides give discrete cells and inventing a
# smooth function between them would not be the approved geometry.

_MAG_BANDS = (
    (5.0, 5.4),
    (5.5, 6.0),
    (6.1, 6.5),
    (6.6, 7.0),
    (7.1, 7.5),
    (7.6, 8.0),
    (8.1, 8.5),
    (8.6, 9.0),
    (9.0, float("inf")),
)

_DEPTH_BANDS = ((0, 10), (11, 20), (21, 40), (41, 60), (61, float("inf")))

#: "South Korea, Philippines, Indonesia, & China" table, and the RoW default.
_RADIUS_GENERAL = (
    (153, 225, 270, 315, 360, 405, 450, 495, 540),
    (135, 180, 225, 270, 315, 360, 405, 450, 495),
    (108, 153, 198, 243, 288, 333, 378, 423, 468),
    (90, 135, 180, 225, 270, 315, 360, 405, 450),
    (72, 108, 162, 198, 252, 288, 333, 378, 423),
)

#: "Japan / Taiwan" table — materially tighter radii than the general table.
_RADIUS_JP_TW = (
    (70, 88, 109, 137, 171, 214, 267, 333, 416),
    (63, 79, 98, 123, 154, 192, 240, 300, 375),
    (57, 71, 89, 111, 138, 173, 216, 270, 337),
    (51, 64, 80, 100, 125, 156, 195, 243, 303),
    (46, 57, 72, 90, 112, 140, 175, 218, 272),
)


def _band_index(value: float, bands: tuple) -> int:
    for i, (lo, hi) in enumerate(bands):
        if lo <= value <= hi:
            return i
    if value < bands[0][0]:
        return 0
    return len(bands) - 1


def radius_km(magnitude: float, depth_miles: float, *, japan_or_taiwan: bool) -> int:
    """Look up the WarRoom polygon radius from the source tables.

    Never estimated or interpolated. `japan_or_taiwan` selects the tighter Japan/Taiwan table;
    everything else (including South Korea, the Philippines, Indonesia, China and the rest of the
    world) uses the general table, which is how the slides split them.
    """
    if magnitude < 0 or depth_miles < 0:
        raise RuleConflict(
            f"magnitude={magnitude} depth_miles={depth_miles} is not a physical reading"
        )
    table = _RADIUS_JP_TW if japan_or_taiwan else _RADIUS_GENERAL
    return table[_band_index(depth_miles, _DEPTH_BANDS)][_band_index(magnitude, _MAG_BANDS)]


def _as_float(fields: Mapping[str, object], name: str) -> float | None:
    raw = fields.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Earthquake reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE_REGIONAL)
    if gate is not None:
        return gate

    variant = get(fields, "region_variant", allowed=REGION_VARIANT)
    if variant == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="EQ.R0",
            rule_text=_NOT_ALL,
            source=SOURCE_REGIONAL,
            missing_fields=("region_variant",),
            evidence=evidence(fields, "region_variant"),
            notes=("The magnitude floor differs by region (5.0 vs 5.7), so it decides nothing "
                   "until the region is known.",),
        )

    source = SOURCE_REGIONAL if variant == "JP_TW_KR_PH_ID_CN" else SOURCE_ROW
    notify_line = _REGIONAL_NOTIFY if variant == "JP_TW_KR_PH_ID_CN" else _ROW_NOTIFY

    magnitude = _as_float(fields, "magnitude")
    if magnitude is None:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="EQ.R1",
            rule_text=notify_line,
            source=source,
            missing_fields=("magnitude",),
            evidence=evidence(fields, "region_variant"),
            notes=(
                "A missing magnitude is not a small magnitude — GDACS/USGS lookup needed. The "
                "source directs: 'Check GDACS and USGS for details on earthquakes.'",
            ),
        )

    epicenter = get(fields, "epicenter", allowed=EPICENTER)
    mapped = get(fields, "sites_mapped_in_region", allowed=YES_NO)
    important = get(fields, "important_region", allowed=YES_NO)
    tsunami = get(fields, "tsunami_alert", allowed=YES_NO)
    disruptions = get(fields, "disruptions_observed", allowed=YES_NO)
    infrastructure = get(fields, "important_infrastructure_in_region", allowed=YES_NO)

    trail = evidence(fields, "region_variant", "magnitude", "epicenter")

    # R2 — a tsunami alert notifies on its own, at any magnitude above the floor and regardless
    # of mapping. Checked early because the source lists it as an independent trigger.
    floor = FLOOR[variant]

    # R3 — the RoW monitor band: M5.0-M5.6 notifies only on observed disruptions.
    if variant == "REST_OF_WORLD" and ROW_MONITOR_BAND[0] <= magnitude <= ROW_MONITOR_BAND[1]:
        if disruptions == "YES":
            return Decision(
                classification=IMPACTFUL,
                rule_id="EQ.R3a",
                rule_text=_ROW_MONITOR,
                source=source,
                threshold_met=True,
                warroom_eligible=True,
                evidence=trail + evidence(fields, "disruptions_observed"),
            )
        if disruptions == "NO":
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="EQ.R3b",
                rule_text=_ROW_MONITOR,
                source=source,
                threshold_met=False,
                warroom_eligible=False,
                evidence=trail + evidence(fields, "disruptions_observed"),
                notes=("Monitor band with no disruptions observed — monitored, not notified.",),
            )
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="EQ.R3c",
            rule_text=_ROW_MONITOR,
            source=source,
            missing_fields=("disruptions_observed",),
            evidence=trail,
        )

    # R4 — below the floor entirely.
    if magnitude < floor:
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="EQ.R4",
            rule_text=_NOT_ALL + "  ||  " + notify_line,
            source=source,
            threshold_met=False,
            warroom_eligible=False,
            evidence=trail,
            notes=(f"M{magnitude} is below the M{floor} floor for {variant}.",),
        )

    # R5 — at or above the floor. The source gives four independent triggers; any one suffices.
    if tsunami == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="EQ.R5a",
            rule_text=notify_line,
            source=source,
            threshold_met=True,
            warroom_eligible=True,
            evidence=trail + evidence(fields, "tsunami_alert"),
        )
    if epicenter == "OFF_COAST":
        # "Epicenter off the coast/Tsunami Alert issued" — the slash makes an off-coast epicenter
        # a trigger in its own right, not only when a tsunami alert follows.
        return Decision(
            classification=IMPACTFUL,
            rule_id="EQ.R5b",
            rule_text=notify_line,
            source=source,
            threshold_met=True,
            warroom_eligible=True,
            evidence=trail + evidence(fields, "sites_mapped_in_region"),
        )
    if mapped == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="EQ.R5c",
            rule_text=notify_line,
            source=source,
            threshold_met=True,
            warroom_eligible=True,
            evidence=trail + evidence(fields, "sites_mapped_in_region"),
        )
    if important == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="EQ.R5d",
            rule_text=notify_line,
            source=source,
            threshold_met=True,
            warroom_eligible=True,
            evidence=trail + evidence(fields, "important_region"),
        )

    # R6 — no mapped sites and not an "important region", but the source still notifies as a LOW
    # FYI when the country is an important manufacturing one or holds key infrastructure.
    if infrastructure == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="EQ.R6",
            rule_text=_FYI_INFRASTRUCTURE + "  ||  " + _FYI_MANUFACTURING,
            source=source,
            threshold_met=True,
            severity=LOW,
            warroom_eligible=True,
            evidence=trail + evidence(fields, "important_infrastructure_in_region"),
            notes=("LOW FYI News with an empty polygon, per the source.",),
        )

    unresolved = tuple(
        name
        for name, value in (
            ("sites_mapped_in_region", mapped),
            ("important_region", important),
            ("important_infrastructure_in_region", infrastructure),
            ("epicenter", epicenter),
        )
        if value == UNKNOWN
    )
    if unresolved:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="EQ.R7",
            rule_text=notify_line + "  ||  " + _FYI_MANUFACTURING,
            source=source,
            missing_fields=unresolved,
            evidence=trail,
            notes=("Fail-closed operational default under global-rules #4 is Impactful.",),
        )

    return Decision(
        classification=NOT_IMPACTFUL,
        rule_id="EQ.R8",
        rule_text=notify_line + "  ||  " + _NOT_ALL,
        source=source,
        threshold_met=False,
        warroom_eligible=False,
        evidence=trail
        + evidence(
            fields,
            "sites_mapped_in_region",
            "important_region",
            "important_infrastructure_in_region",
        ),
        notes=(
            "Above the magnitude floor but on land with no mapped sites, no regional importance "
            "and no key infrastructure — every trigger on the slide answered NO.",
        ),
    )
