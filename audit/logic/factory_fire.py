"""Factory Fire threshold logic.

Source: `audit/rules/event-types-manmade.md` § Factory Fire (slide 19).
Priority: P2. **No supplied extraction schema** — fields are author-derived from the verbatim
guidelines (see `audit/EVENT_TYPE_BUILD_ORDER.md`).

Factory Fire is the event type that breaks naive resolved-event logic, and it does so in the
source's own words:

> "Report factory fires proactively. We report a factory fire, even if the articles say it is a
> small fire or has been extinguished."

`global-rules.md` #5 exists specifically to stop a blanket "the disruption is over, so mark Not
Impactful" shortcut, and names this event type as the example. So neither `fire_scale` nor
`fire_status` can ever produce a Not Impactful verdict here — they are recorded as evidence and
have no rejecting branch. That is deliberate and is the single most important thing to preserve
in this module.

What *can* remove a row is the connection chain, and the source makes it unusually long. Read as
a cascade, each step a fallback for the one before:

1. partner site → report with impact to the exact site
2. non-mapped factory, product line relevant to our verticals → report
3. applications not connected → **check indirect supplier; if yes, still report**
4. service sector → check the service vertical list
5. utility/services → check for mapped sites in the region *served*
6. no sites at all → check for major manufacturing hubs, ports, airports, roads, mining in the
   affected region

Only after all six fail is there nothing to report. A module that stopped at step 2 or 3 would
drop rows the source explicitly rescues, which is why every step is a named field rather than
folded into one "connected" boolean.
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

EVENT_TYPE = "Factory Fire"
SOURCE = "rules/event-types-manmade.md § Factory Fire (slide 19)"

YES_NO = frozenset({"YES", "NO"})

#: Recorded for reporting only. There is deliberately NO branch that rejects on these values.
FIRE_STATUS = frozenset({"ACTIVE", "EXTINGUISHED", "UNDER_INVESTIGATION", "RECOVERED"})
FIRE_SCALE = frozenset({"MINOR", "SIGNIFICANT", "EXPLOSION"})

#: "Fire/explosion at a neighboring facility" and "Fire just outside the facility" are both
#: in-scope sub-types, so location relative to the site does not reject either.
SITE_RELATION = frozenset({"AT_THE_FACILITY", "NEIGHBOURING_FACILITY", "JUST_OUTSIDE"})

PRODUCT_CONNECTION = frozenset({"CONNECTED", "NOT_CONNECTED"})
SERVICE_APPLICABILITY = frozenset({"APPLICABLE", "NOT_APPLICABLE", "NOT_A_SERVICE_SECTOR"})

MUST_HAVE_FIELDS = (
    "partner_site_involved",
    "product_line_connection",
    "indirect_supplier",
    "service_sector_applicability",
    "utility_or_service_region_has_mapped_sites",
    "affected_region_has_major_infrastructure",
    "fire_status",
    "fire_scale",
    "site_relation",
    "neighbouring_evacuations",
)

_PROACTIVE = (
    "Report factory fires proactively. We report a factory fire, even if the articles say it is a "
    "small fire or has been extinguished."
)
_PARTNER = (
    "If a fire is reported at a partner site/warehouse, notify with impact to the exact site."
)
_NON_MAPPED = (
    "If a fire breaks out at a non-mapped factory/warehouse, notify if the product line of the "
    "company is relevant to our industrial verticals. Assume it's a possible sub-tier or a T1 yet "
    "to be mapped."
)
_INDIRECT = (
    "If applications do not have a connection to our verticals? Check if its an indirect "
    "supplier, if yes, notify"
)
_SERVICE = (
    "If the service sector is involved - Check if their services have applications in our "
    "vertical: logistics provider, cargo shipping, petrochemicals, specialty chemicals, IT "
    "consultancy, utility provider, farming company, and more"
)
_UTILITY_REGION = (
    "Utility or services sector? Check if there are sites mapped in the region served by the "
    "affected services"
)
_NO_SITES = (
    "No sites? Check if major manufacturing hubs, ports, airports, roads, and mining operations "
    "in the affected region"
)
_EVAC = (
    "Check if there are evacuations in neighboring sites. If yes, notify with a polygon. However, "
    "check if a street address is provided by the news sources"
)


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Factory Fire reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    partner = get(fields, "partner_site_involved", allowed=YES_NO)
    if partner == UNKNOWN:
        partner = mapped_party(fields)
    product = get(fields, "product_line_connection", allowed=PRODUCT_CONNECTION)
    indirect = get(fields, "indirect_supplier", allowed=YES_NO)
    service = get(fields, "service_sector_applicability", allowed=SERVICE_APPLICABILITY)
    utility_region = get(
        fields, "utility_or_service_region_has_mapped_sites", allowed=YES_NO
    )
    infrastructure = get(fields, "affected_region_has_major_infrastructure", allowed=YES_NO)
    evac = get(fields, "neighbouring_evacuations", allowed=YES_NO)
    # Read purely as evidence. Validated so a bad label surfaces, but never branched on to reject.
    get(fields, "fire_status", allowed=FIRE_STATUS)
    get(fields, "fire_scale", allowed=FIRE_SCALE)
    get(fields, "site_relation", allowed=SITE_RELATION)

    trail = evidence(fields, "fire_status", "fire_scale", "site_relation")

    # R1 — partner site. Reported with impact to the exact site, no further test.
    if partner == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="FF.R1",
            rule_text=_PARTNER,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "partner_site_involved") + trail,
        )

    # R2 — the non-mapped product-line test.
    if product == "CONNECTED":
        return Decision(
            classification=IMPACTFUL,
            rule_id="FF.R2",
            rule_text=_NON_MAPPED,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "product_line_connection") + trail,
        )

    # R3 — the indirect-supplier rescue. This step is what makes a bare "not connected" reading
    # wrong on its own; the source explicitly asks the further question.
    if indirect == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="FF.R3",
            rule_text=_INDIRECT,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "product_line_connection", "indirect_supplier") + trail,
        )

    # R4 — service vertical.
    if service == "APPLICABLE":
        return Decision(
            classification=IMPACTFUL,
            rule_id="FF.R4",
            rule_text=_SERVICE,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "service_sector_applicability") + trail,
        )

    # R5 — utility/services: mapped sites in the region *served*, not the region of the fire.
    if utility_region == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="FF.R5",
            rule_text=_UTILITY_REGION,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "utility_or_service_region_has_mapped_sites") + trail,
        )

    # R6 — regional infrastructure, the last rescue in the cascade.
    if infrastructure == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="FF.R6",
            rule_text=_NO_SITES,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "affected_region_has_major_infrastructure") + trail,
        )

    # R7 — neighbouring evacuations make it reportable regardless of the connection chain: the
    # source asks for a polygon, which presupposes a bulletin.
    if evac == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="FF.R7",
            rule_text=_EVAC,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=True,
            evidence=evidence(fields, "neighbouring_evacuations") + trail,
        )

    # R8 — every rescue in the cascade must have been actively answered NO before the row can be
    # dropped. Any UNKNOWN left in the chain means the cascade was not completed, and per
    # global-rules #13 an incomplete check is not a negative result.
    cascade = {
        "partner_site_involved": partner,
        "product_line_connection": product,
        "indirect_supplier": indirect,
        "service_sector_applicability": service,
        "utility_or_service_region_has_mapped_sites": utility_region,
        "affected_region_has_major_infrastructure": infrastructure,
        "neighbouring_evacuations": evac,
    }
    unresolved = tuple(name for name, value in cascade.items() if value == UNKNOWN)
    if unresolved:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="FF.R8",
            rule_text=_PROACTIVE + "  ||  " + _INDIRECT,
            source=SOURCE,
            missing_fields=unresolved,
            evidence=trail,
            notes=(
                "The source's connection cascade has six fallbacks; an unanswered step is not a "
                "negative answer. Fail-closed operational default under global-rules #4 is "
                "Impactful.",
            ),
        )

    return Decision(
        classification=NOT_IMPACTFUL,
        rule_id="FF.R9",
        rule_text=_NON_MAPPED + "  ||  " + _INDIRECT + "  ||  " + _NO_SITES,
        source=SOURCE,
        threshold_met=False,
        warroom_eligible=False,
        evidence=evidence(fields, *cascade.keys()) + trail,
        notes=(
            "Every step of the six-fallback connection cascade was answered NO. Note that fire "
            "scale and status played no part: the source reports a fire even if small or already "
            "extinguished.",
        ),
    )
