"""Chemical Spill threshold logic.

Source: `audit/rules/event-types-manmade.md` § Chemical Spill (slide 8).
Priority: P2. **No supplied extraction schema** — fields are author-derived from the verbatim
guidelines (see `audit/EVENT_TYPE_BUILD_ORDER.md`).

Chemical Spill has the most permissive bar of any event type built so far, and it says so
directly:

> "We notify spills and leaks as soon as the news is made public. **Notify even if no sites are
> mapped.** Check the industrial importance of the region, product and services affected"

So mapped status cannot reject a row here — it is not a gate at all. The only thing that removes
a spill is the location test, and even that is written as a broad inclusion list rather than an
exclusion:

> "Report chemical spills at an industrial unit, warehouse, port, airport, industrial park,
> mines, logistic hubs, train track, medical labs, and highway"

The practical consequence for the workload funnel: this event type is close to notify-always, so
it should be expected to remove almost nothing. A run that shows Chemical Spill removing a large
share of its rows is a bug in extraction or in this module, not a win.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    IMPACTFUL,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    evidence,
    get,
)
from .global_gate import apply_global_gate

EVENT_TYPE = "Chemical Spill"
SOURCE = "rules/event-types-manmade.md § Chemical Spill (slide 8)"

YES_NO = frozenset({"YES", "NO"})

#: Verbatim from "Report chemical spills at an industrial unit, warehouse, port, airport,
#: industrial park, mines, logistic hubs, train track, medical labs, and highway". `OTHER_LOCATION`
#: covers a site type the list does not name — e.g. a residential street or a farm field — and is
#: the only value that can lead to a Not Impactful verdict.
SPILL_LOCATION = frozenset(
    {
        "INDUSTRIAL_UNIT",
        "WAREHOUSE",
        "PORT",
        "AIRPORT",
        "INDUSTRIAL_PARK",
        "MINE",
        "LOGISTICS_HUB",
        "TRAIN_TRACK",
        "MEDICAL_LAB",
        "HIGHWAY",
        "OTHER_LOCATION",
    }
)

#: From "Check the industrial importance of the region, product and services affected".
REGIONAL_IMPORTANCE = frozenset({"IMPORTANT", "NOT_IMPORTANT"})

#: From "Spills and leaks can cause plant/ region evacuations, road closures, temporary plant
#: shutdowns, environmental hazards, investigations, product scarcity, and more". Any of these
#: makes the spill consequential regardless of where it happened.
EXTERNAL_DISRUPTION = frozenset(
    {
        "EVACUATION",
        "ROAD_CLOSURE",
        "PLANT_SHUTDOWN",
        "WATER_OR_RIVER_CONTAMINATION",
        "PRODUCT_SCARCITY",
        "HEALTH_ADVISORY",
        "NONE_REPORTED",
    }
)

MUST_HAVE_FIELDS = (
    "spill_location",
    "external_disruption",
    "regional_industrial_importance",
    "news_is_public",
)

_PUBLIC = (
    "We notify spills and leaks as soon as the news is made public. Notify even if no sites are "
    "mapped. Check the industrial importance of the region, product and services affected"
)
_LOCATIONS = (
    "Report chemical spills at an industrial unit, warehouse, port, airport, industrial park, "
    "mines, logistic hubs, train track, medical labs, and highway"
)
_CONSEQUENCES = (
    "Spills and leaks can cause plant/ region evacuations, road closures, temporary plant "
    "shutdowns, environmental hazards, investigations, product scarcity, and more"
)


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Chemical Spill reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    public = get(fields, "news_is_public", allowed=YES_NO)
    location = get(fields, "spill_location", allowed=SPILL_LOCATION)
    disruption = get(fields, "external_disruption", allowed=EXTERNAL_DISRUPTION)
    importance = get(fields, "regional_industrial_importance", allowed=REGIONAL_IMPORTANCE)

    # R1 — "as soon as the news is made public" is the one precondition the source states.
    if public == "NO":
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="CS.R1",
            rule_text=_PUBLIC,
            source=SOURCE,
            missing_fields=("news_is_public",),
            evidence=evidence(fields, "news_is_public"),
            notes=(
                "The source conditions notification on the news being public; a non-public "
                "report is not something this pipeline should resolve alone.",
            ),
        )

    # R2 — any named consequence makes the spill reportable wherever it happened.
    if disruption not in {"NONE_REPORTED", UNKNOWN}:
        return Decision(
            classification=IMPACTFUL,
            rule_id="CS.R2",
            rule_text=_CONSEQUENCES,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "external_disruption", "spill_location"),
        )

    # R3 — a spill at any of the named site types is reportable, mapped or not.
    if location not in {"OTHER_LOCATION", UNKNOWN}:
        return Decision(
            classification=IMPACTFUL,
            rule_id="CS.R3",
            rule_text=_LOCATIONS + "  ||  " + _PUBLIC,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "spill_location", "external_disruption"),
            notes=("Mapped status is explicitly not a gate for this event type.",),
        )

    # R4 — a location the list does not name, but an industrially important region.
    if importance == "IMPORTANT":
        return Decision(
            classification=IMPACTFUL,
            rule_id="CS.R4",
            rule_text=_PUBLIC,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "regional_industrial_importance", "spill_location"),
        )

    if location == UNKNOWN or importance == UNKNOWN or disruption == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="CS.R5",
            rule_text=_LOCATIONS + "  ||  " + _PUBLIC,
            source=SOURCE,
            missing_fields=tuple(
                name
                for name, value in (
                    ("spill_location", location),
                    ("external_disruption", disruption),
                    ("regional_industrial_importance", importance),
                )
                if value == UNKNOWN
            ),
            evidence=evidence(fields, "news_is_public"),
            notes=("Fail-closed operational default under global-rules #4 is Impactful.",),
        )

    # R6 — the only path out. A spill at an unnamed location type, with no reported consequence,
    # in a region of no industrial importance.
    return Decision(
        classification=NOT_IMPACTFUL,
        rule_id="CS.R6",
        rule_text=_LOCATIONS,
        source=SOURCE,
        threshold_met=False,
        warroom_eligible=False,
        evidence=evidence(
            fields, "spill_location", "external_disruption", "regional_industrial_importance"
        ),
        notes=(
            "Chemical Spill is near notify-always; this is the single narrow exit and should be "
            "rare. A high Not Impactful rate for this event type indicates an extraction fault.",
        ),
    )
