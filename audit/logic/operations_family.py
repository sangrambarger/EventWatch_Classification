"""Factory Disruption, Force Majeure, Supply Shortage and Mine Shutdown.

Sources: `event-types-manmade.md` §§ Factory Disruption (20), Force Majeure (24), Supply Shortage
(43), Mine Shutdown (36). All P2 except Force Majeure (P1) and Mine Shutdown (P3).

Four operational types sharing the connection cascade, each with one qualifier worth encoding.

**Factory Disruption is where `global-rules.md` #6's materiality floor bites.** Its sub-types
include "Future/scheduled shutdowns", read literally a keyword match on any announced maintenance
window. #6 says that bullet exists to catch shutdowns that are themselves the disruptive event or
a response to one — not routine, long-pre-announced, business-as-usual maintenance. So a
`ROUTINE_PLANNED_MAINTENANCE` disruption with no stated cause and no unusual duration is Not
Impactful, and #6 is explicit that this is a *clear* case rather than one where the
safe-default-to-Impactful rule applies.

Note the contrast with Layoffs, whose slide names future layoffs as reportable outright — so #6
applies here and not there. The difference is whether the source names the future case
explicitly.

**Force Majeure notifies planned activity too**, which looks like the opposite of the above:
"Notify FMs due to maintenance activities or preplanned activities". A declared force majeure is
itself the reportable act, whatever triggered it, so there is no materiality floor here.

**Mine Shutdown gates coal separately**: "Coal? Notify only if disruptions to the power industry
are expected OR disruptions expected for our verticals."

**Supply Shortage asks for the source of the shortage**, and its multi-tier line is the one that
matters in practice — "Connect the dots to multi-tier verticals" with the worked example of
semiconductor process materials in the petroleum supply chain. A shortage whose direct commodity
looks unconnected may still connect a tier down, so `multi_tier_connection` is a distinct field
rather than being folded into `product_line_connection`.
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
from .connection import connection_cascade, unresolved_cascade
from .global_gate import apply_global_gate

YES_NO = frozenset({"YES", "NO"})

# --- Factory Disruption ---------------------------------------------------------------------------

FACTORY_DISRUPTION_EVENT_TYPE = "Factory Disruption"
FACTORY_DISRUPTION_SOURCE = "rules/event-types-manmade.md § Factory Disruption (slide 20)"

DISRUPTION_NATURE = frozenset(
    {
        "UNPLANNED_SHUTDOWN",
        "FUTURE_OR_SCHEDULED_SHUTDOWN",
        "ROUTINE_PLANNED_MAINTENANCE",
        "PARTIAL_OR_FULL_CLOSURE",
        "EVACUATION_OR_LOCKDOWN",
        "PRODUCTION_HALT_OR_CUT",
        "INDUSTRIAL_ACCIDENT",
        "SECURITY_INCIDENT",
        "BLOCKED_ACCESS",
    }
)

_FD_SCOPE = (
    "We notify shutdowns, evacuations, industrial accidents, labor strikes, shooting incidents, "
    "production transfer, and other site-level disruptions that can affect the site's operations."
)
_FD_MAPPED = (
    "If a temporary/permanent closure is reported at the mapped partner site/warehouse, notify it "
    "with impact to the exact site."
)
_FD_UNMAPPED = (
    "If a non-mapped partner announces closure, report if the product line and applications match "
    "our verticals. Assume it's a possible sub-tier or a T1 yet to be mapped."
)
_FD_SERVICE = (
    "If a service sector is involved - Check if their services have applications in our vertical: "
    "logistics provider, cargo shipping, petrochemicals, specialty chemicals, IT consultancy, "
    "utility provider, farming company, and more"
)
_MATERIALITY_FLOOR = (
    "global-rules.md #6: Before classifying Impactful on a 'scheduled'/'future'/'planned' keyword "
    "match alone, check for an actual materiality signal: unusual duration, a stated cause tied to "
    "a disruption, or scope beyond ordinary operations. A title that is purely 'Company X's "
    "planned annual maintenance shutdown, dates announced', with nothing else, is Not Impactful."
)


def decide_factory_disruption(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=FACTORY_DISRUPTION_EVENT_TYPE)
    if gate is not None:
        return gate

    nature = get(fields, "disruption_nature", allowed=DISRUPTION_NATURE)
    if nature == "ROUTINE_PLANNED_MAINTENANCE":
        signal = get(fields, "materiality_signal", allowed=YES_NO)
        if signal == "NO":
            return Decision(
                classification=NOT_IMPACTFUL, rule_id="FDIS.R1", rule_text=_MATERIALITY_FLOOR,
                source=FACTORY_DISRUPTION_SOURCE, threshold_met=False, warroom_eligible=False,
                evidence=evidence(fields, "disruption_nature", "materiality_signal"),
                notes=(
                    "global-rules #6 is explicit that 'routine and pre-planned with no stated "
                    "disruption' is a clear signal, not ambiguity, so the safe-default-to-"
                    "Impactful rule does not apply here.",
                ),
            )
        if signal == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW, rule_id="FDIS.R2", rule_text=_MATERIALITY_FLOOR,
                source=FACTORY_DISRUPTION_SOURCE, missing_fields=("materiality_signal",),
                evidence=evidence(fields, "disruption_nature"),
            )

    decision = connection_cascade(
        fields, rule_prefix="FDIS", source=FACTORY_DISRUPTION_SOURCE,
        mapped_line=_FD_MAPPED, product_line=_FD_UNMAPPED, service_line=_FD_SERVICE,
    )
    return decision or unresolved_cascade(
        fields, rule_prefix="FDIS", source=FACTORY_DISRUPTION_SOURCE, rule_text=_FD_SCOPE,
    )


# --- Force Majeure -------------------------------------------------------------------------------

FORCE_MAJEURE_EVENT_TYPE = "Force Majeure"
FORCE_MAJEURE_SOURCE = "rules/event-types-manmade.md § Force Majeure (slide 24)"

_FM_ANNOUNCED = "We notify Force Majeure as soon as it is announced"
_FM_APPLICATIONS = (
    "We notify if the affected commodity has applications in our verticals, including "
    "petrochemicals, specialty chemicals, APIs, general manufacturing, plastics, glass, coatings, "
    "resins, adhesives, foam, packaging, metals, and more"
)
_FM_PLANNED = "Notify FMs due to maintenance activities or preplanned activities"


def decide_force_majeure(fields: Mapping[str, object]) -> Decision:
    """Force Majeure. No materiality floor — a declared FM is itself the reportable act.

    Deliberately the opposite of Factory Disruption's handling of planned activity, because this
    slide names preplanned FMs as reportable where Factory Disruption's "future/scheduled
    shutdowns" bullet is a broad sub-type that `global-rules` #6 narrows.
    """
    gate = apply_global_gate(fields, candidate_event_type=FORCE_MAJEURE_EVENT_TYPE)
    if gate is not None:
        return gate
    declared = get(fields, "force_majeure_declared", allowed=YES_NO)
    if declared == "NO":
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="FM.R0", rule_text=_FM_ANNOUNCED,
            source=FORCE_MAJEURE_SOURCE, missing_fields=("event_type_reassignment",),
            evidence=evidence(fields, "force_majeure_declared"),
            notes=("No FM declared, so this slide's rules do not apply; the underlying cause "
                   "(fire, flood, accident) is the event type to decide under.",),
        )
    decision = connection_cascade(
        fields, rule_prefix="FM", source=FORCE_MAJEURE_SOURCE,
        mapped_line=_FM_ANNOUNCED + "  ||  " + _FM_PLANNED,
        product_line=_FM_APPLICATIONS, service_line=_FM_APPLICATIONS,
    )
    return decision or unresolved_cascade(
        fields, rule_prefix="FM", source=FORCE_MAJEURE_SOURCE, rule_text=_FM_APPLICATIONS,
    )


# --- Supply Shortage ------------------------------------------------------------------------------

SUPPLY_SHORTAGE_EVENT_TYPE = "Supply Shortage"
SUPPLY_SHORTAGE_SOURCE = "rules/event-types-manmade.md § Supply Shortage (slide 43)"

_SS_APPLICATIONS = "Notify if the applications of the commodity involved match our verticals"
_SS_COMPANY = "Notify if a company reports products shortages"
_SS_MULTITIER = (
    "Connect the dots to multi-tier verticals. Several semiconductor process materials in the "
    "petroleum supply chain are running short, including acetone, NMP, IPA, and solvents. Thus, "
    "affecting the customers from our verticals."
)


def decide_supply_shortage(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=SUPPLY_SHORTAGE_EVENT_TYPE)
    if gate is not None:
        return gate

    # The multi-tier rescue runs before the direct cascade rejects: a commodity that looks
    # unconnected at first tier may connect a tier down, which is the whole point of that line.
    if get(fields, "multi_tier_connection", allowed=YES_NO) == "YES":
        return Decision(
            classification=IMPACTFUL, rule_id="SS.MULTITIER", rule_text=_SS_MULTITIER,
            source=SUPPLY_SHORTAGE_SOURCE, threshold_met=True, warroom_eligible=True,
            evidence=evidence(fields, "multi_tier_connection", "product_line_connection"),
        )

    decision = connection_cascade(
        fields, rule_prefix="SS", source=SUPPLY_SHORTAGE_SOURCE,
        mapped_line=_SS_COMPANY, product_line=_SS_APPLICATIONS, service_line=_SS_APPLICATIONS,
    )
    if decision is not None and decision.classification == NOT_IMPACTFUL:
        if get(fields, "multi_tier_connection", allowed=YES_NO) == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW, rule_id="SS.MULTITIER_REVIEW",
                rule_text=_SS_MULTITIER, source=SUPPLY_SHORTAGE_SOURCE,
                missing_fields=("multi_tier_connection",),
                evidence=evidence(fields, "product_line_connection"),
                notes=("Direct commodity looks unconnected, but the multi-tier question the "
                       "source insists on has not been asked.",),
            )
    return decision or unresolved_cascade(
        fields, rule_prefix="SS", source=SUPPLY_SHORTAGE_SOURCE, rule_text=_SS_APPLICATIONS,
        extra_fields=("multi_tier_connection",),
    )


# --- Mine Shutdown ---------------------------------------------------------------------------------

MINE_EVENT_TYPE = "Mine Shutdown"
MINE_SOURCE = "rules/event-types-manmade.md § Mine Shutdown (slide 36)"

_MN_ONLY = "We notify only if the applications of affected commodity match our verticals"
_MN_MAPPED = "Check if the mine is mapped"
_MN_COAL = (
    "Coal? Notify only if disruptions to the power industry are expected OR disruptions expected "
    "for our verticals"
)
_MN_FUTURE = "Pre-announced shutdown? Notify today and send an update later when it shuts down"


def decide_mine_shutdown(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=MINE_EVENT_TYPE)
    if gate is not None:
        return gate

    if get(fields, "commodity_is_coal", allowed=YES_NO) == "YES":
        power = get(fields, "power_industry_disruption_expected", allowed=YES_NO)
        verticals = get(fields, "product_line_connection",
                        allowed=frozenset({"CONNECTED", "NOT_CONNECTED"}))
        if power == "YES" or verticals == "CONNECTED":
            return Decision(
                classification=IMPACTFUL, rule_id="MN.COAL_OK", rule_text=_MN_COAL,
                source=MINE_SOURCE, threshold_met=True, warroom_eligible=True,
                evidence=evidence(fields, "commodity_is_coal",
                                  "power_industry_disruption_expected",
                                  "product_line_connection"),
            )
        if power == "NO" and verticals == "NOT_CONNECTED":
            return Decision(
                classification=NOT_IMPACTFUL, rule_id="MN.COAL_NO", rule_text=_MN_COAL,
                source=MINE_SOURCE, threshold_met=False, warroom_eligible=False,
                evidence=evidence(fields, "commodity_is_coal",
                                  "power_industry_disruption_expected",
                                  "product_line_connection"),
            )
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="MN.COAL_REVIEW", rule_text=_MN_COAL,
            source=MINE_SOURCE, missing_fields=("power_industry_disruption_expected",),
            evidence=evidence(fields, "commodity_is_coal", "product_line_connection"),
        )

    decision = connection_cascade(
        fields, rule_prefix="MN", source=MINE_SOURCE,
        mapped_line=_MN_MAPPED + "  ||  " + _MN_FUTURE,
        product_line=_MN_ONLY, service_line=_MN_ONLY,
    )
    return decision or unresolved_cascade(
        fields, rule_prefix="MN", source=MINE_SOURCE, rule_text=_MN_ONLY,
    )
