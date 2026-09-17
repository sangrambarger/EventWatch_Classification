"""Power Outage threshold logic, including the Software/Internet Outage variant.

Sources: `audit/rules/event-types-natural.md` § Power Outage (slide 37) and
`audit/rules/event-types-other.md` § Software/Internet Outage (slide 55), which the taxonomy
redirects here — "We notify it under Power Outages".
Priority: P1. **No supplied extraction schema** — fields are author-derived.

Power Outage is the only event type built so far whose bar is a **duration**, and it has three
different durations depending on what is affected:

| Case | Threshold |
|---|---|
| Semiconductor-fab regions (Taiwan, South Korea, China, Japan, USA, Singapore, Germany, Israel, Netherlands, Malaysia, …) | **report all outages**, even under 6 hours |
| Rest of world | longer than **6 hours**, or expected to be |
| Software/Internet variant, tech/industrial zones | longer than **3 hours** |

Two source lines invert the usual "missing data means we can't decide" instinct, and both are
encoded literally:

> "We notify if Expected Recovery Time is not provided"

An **absent** recovery time is a reason to notify, not a reason to send the row to review. This
is the one place in the whole ruleset where UNKNOWN resolves toward Impactful by explicit
instruction rather than by the fail-closed default, so it is called out here and tested.

> "We notify power outages only in a region with sites mapped."

That "only" is a hard gate, and it is what actually removes rows for this type — unlike the
duration tests, which mostly let rows through.

The Software/Internet variant carries its own DO-NOT list that the base Power Outage rules lack
(residential issues, recovery within 1-2 hrs without business impact, operations already
resumed), so it is a branch rather than a separate module.
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
from .connection import mapped_party
from .global_gate import apply_global_gate

EVENT_TYPE = "Power Outage"
SOURCE = "rules/event-types-natural.md § Power Outage (slide 37)"
SOURCE_SW = "rules/event-types-other.md § Software/Internet Outage (slide 55)"

YES_NO = frozenset({"YES", "NO"})

OUTAGE_KIND = frozenset({"POWER", "SOFTWARE_OR_INTERNET"})

#: "Power out at a site, warehouse, port, airport, mine, industrial park, etc."
OUTAGE_LOCATION = frozenset(
    {
        "SITE",
        "WAREHOUSE",
        "PORT",
        "AIRPORT",
        "MINE",
        "INDUSTRIAL_PARK",
        "RESIDENTIAL_OR_LOCAL_USER",
        "OTHER_LOCATION",
    }
)

MUST_HAVE_FIELDS = (
    "outage_kind",
    "sites_mapped_in_region",
    "semiconductor_fab_region",
    "expected_recovery_time_provided",
    "duration_hours",
    "outage_location",
    "important_manufacturing_region",
    "operations_already_resumed",
    "mapped_site_confirms_impact",
)

_ONLY_MAPPED = "We notify power outages only in a region with sites mapped."
_NO_ERT = "We notify if Expected Recovery Time is not provided"
_FABS = (
    "For regions with semiconductor fabs, including Taiwan, South Korea, China, Japan, USA, "
    "Singapore, Germany, Israel, Netherlands, Malaysia etc. - report all power outages even if "
    "the expected recovery time is less than 6 hours"
)
_ROW_6H = (
    "Rest of the World - If the outage lasts or is expected to last longer than 6 hours"
)
_LOCATIONS = "Power out at a site, warehouse, port, airport, mine, industrial park, etc."
_IMPORTANT = "Important manufacturing regions affected"
_SW_NOTIFY = (
    "Notify if: Mapped/partner site confirms operational impact | Outage >3 hrs in tech or "
    "industrial zones (Taiwan, India, Singapore, etc.) | Major internet or telecom outage hits "
    "multiple mapped locations | Global/regional SaaS outage affecting ERP/CRM/Logistics "
    "platforms | Confirmed disruption to manufacturing, logistics, or services"
)
_SW_DO_NOT = (
    "Do NOT notify if: Residential/local user issue | Recovery within 1-2 hrs without business "
    "impact | Services/operations have already resumed | System outages have recovered"
)


def _as_float(fields: Mapping[str, object], name: str) -> float | None:
    raw = fields.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Power Outage reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    kind = get(fields, "outage_kind", allowed=OUTAGE_KIND)
    mapped = get(fields, "sites_mapped_in_region", allowed=YES_NO)
    if mapped == UNKNOWN:
        # Mapped status resolves through industry relevance (process-owner decision).
        mapped = mapped_party(fields)
    fab_region = get(fields, "semiconductor_fab_region", allowed=YES_NO)
    ert_provided = get(fields, "expected_recovery_time_provided", allowed=YES_NO)
    location = get(fields, "outage_location", allowed=OUTAGE_LOCATION)
    important = get(fields, "important_manufacturing_region", allowed=YES_NO)
    resumed = get(fields, "operations_already_resumed", allowed=YES_NO)
    confirms = get(fields, "mapped_site_confirms_impact", allowed=YES_NO)
    duration = _as_float(fields, "duration_hours")

    trail = evidence(fields, "outage_kind", "outage_location", "sites_mapped_in_region")

    # --- Software/Internet variant -----------------------------------------------------------
    # Handled first because it carries DO-NOT rules the base Power Outage slide does not have.
    if kind == "SOFTWARE_OR_INTERNET":
        if location == "RESIDENTIAL_OR_LOCAL_USER":
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="PO.S1",
                rule_text=_SW_DO_NOT,
                source=SOURCE_SW,
                threshold_met=False,
                warroom_eligible=False,
                evidence=trail,
            )
        if confirms == "YES":
            return Decision(
                classification=IMPACTFUL,
                rule_id="PO.S2",
                rule_text=_SW_NOTIFY,
                source=SOURCE_SW,
                threshold_met=True,
                warroom_eligible=True,
                evidence=trail + evidence(fields, "mapped_site_confirms_impact"),
            )
        if resumed == "YES" and (duration is not None and duration <= 2):
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="PO.S3",
                rule_text=_SW_DO_NOT,
                source=SOURCE_SW,
                threshold_met=False,
                warroom_eligible=False,
                evidence=trail + evidence(fields, "operations_already_resumed", "duration_hours"),
                notes=("Recovered within 1-2 hrs with no confirmed business impact.",),
            )
        if duration is not None:
            if duration > 3:
                return Decision(
                    classification=IMPACTFUL,
                    rule_id="PO.S4",
                    rule_text=_SW_NOTIFY,
                    source=SOURCE_SW,
                    threshold_met=True,
                    warroom_eligible=True,
                    evidence=trail + evidence(fields, "duration_hours"),
                )
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="PO.S5",
                rule_text=_SW_DO_NOT + "  ||  " + _SW_NOTIFY,
                source=SOURCE_SW,
                threshold_met=False,
                warroom_eligible=False,
                evidence=trail + evidence(fields, "duration_hours"),
                notes=("Under the 3-hour bar for the Software/Internet variant.",),
            )
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="PO.S6",
            rule_text=_SW_NOTIFY,
            source=SOURCE_SW,
            missing_fields=("duration_hours",),
            evidence=trail,
        )

    # --- Base Power Outage --------------------------------------------------------------------

    # R1 — the hard mapped-region gate. This is what removes rows for this type.
    if mapped == "NO" and important != "YES":
        if important == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW,
                rule_id="PO.R1a",
                rule_text=_ONLY_MAPPED + "  ||  " + _IMPORTANT,
                source=SOURCE,
                missing_fields=("important_manufacturing_region",),
                evidence=trail,
            )
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="PO.R1b",
            rule_text=_ONLY_MAPPED,
            source=SOURCE,
            threshold_met=False,
            warroom_eligible=False,
            evidence=trail + evidence(fields, "important_manufacturing_region"),
            notes=("The source says 'only' — no mapped sites and not an important region.",),
        )
    if mapped == UNKNOWN and important == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="PO.R1c",
            rule_text=_ONLY_MAPPED,
            source=SOURCE,
            missing_fields=("sites_mapped_in_region",),
            evidence=trail,
        )

    # R2 — semiconductor-fab regions report everything, so the duration tests never run.
    if fab_region == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="PO.R2",
            rule_text=_FABS,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=trail + evidence(fields, "semiconductor_fab_region"),
            notes=("Fab region: reported regardless of expected recovery time.",),
        )

    # R3 — an absent expected recovery time is itself a trigger. Encoded literally: this is the
    # one rule in the ruleset where missing data resolves toward Impactful by instruction rather
    # than by the fail-closed default.
    if ert_provided == "NO":
        return Decision(
            classification=IMPACTFUL,
            rule_id="PO.R3",
            rule_text=_NO_ERT,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=trail + evidence(fields, "expected_recovery_time_provided"),
            notes=(
                "No expected recovery time is a stated reason to notify, not a reason to review.",
            ),
        )

    # R4 — the rest-of-world 6-hour bar.
    if duration is None:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="PO.R4",
            rule_text=_ROW_6H + "  ||  " + _NO_ERT,
            source=SOURCE,
            missing_fields=("duration_hours",),
            evidence=trail + evidence(fields, "expected_recovery_time_provided"),
            notes=(
                "A recovery time was said to be provided but no duration was extracted — that "
                "is an extraction gap, distinct from the 'not provided' case in PO.R3.",
            ),
        )
    if duration > 6:
        return Decision(
            classification=IMPACTFUL,
            rule_id="PO.R5",
            rule_text=_ROW_6H,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=trail + evidence(fields, "duration_hours"),
        )
    return Decision(
        classification=NOT_IMPACTFUL,
        rule_id="PO.R6",
        rule_text=_ROW_6H,
        source=SOURCE,
        threshold_met=False,
        warroom_eligible=False,
        evidence=trail + evidence(fields, "duration_hours", "semiconductor_fab_region"),
        notes=(f"{duration}h is at or under the 6-hour rest-of-world bar.",),
    )
