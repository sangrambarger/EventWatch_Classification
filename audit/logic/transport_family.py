"""Airport Disruption, Port Disruption and Labor Disruption.

Sources: `event-types-manmade.md` §§ Airport Disruption (3), Port Disruption (38), Labor
Disruption (31). P1, P1, P2.

These three carry the most explicit DO-NOT lists in the ruleset, which makes them the biggest
rule-driven workload reduction available — and they interlock, because a strike at a port or
airport is reclassified rather than decided where it lands:

> Labor Disruption: "Strikes likely to affect ports or airports -> classify as PORT/AIRPORT
> DISRUPTION."
> Airport Disruption: "Under airport disruptions, we also notify labor strikes threatening an
> airport."
> Port Disruption: "Under port disruptions, we also notify container ship accidents and labor
> strikes threatening a port."

So `labor_disruption.decide()` reroutes rather than deciding when the target is a port or airport.
That matters because the two destinations apply *stricter* tests — an airport strike still has to
clear the cargo test — so deciding it under Labor Disruption's permissive rules would over-report.

**Airport Disruption is cargo-centric, and that single fact removes most of its rows.** Passenger-
only disruption is out. A domestic airport with no cargo is out. "Minor disruption, resolved
quickly" is out. "Fire in aircraft hangar or airport parking, no flight disruptions" is out. In
the 216-row feed sample this event type looked like rank 2 by volume, but ~17 of its ~25 rows were
wire copies of a single cargo-plane crash — so dedup, not this module, is what handles that bulk.

**Both transport types treat a strike ballot differently from a confirmed strike.** Airport: "Strike
- if only a ballot is scheduled, and no strike date set" is a DO-NOT. Port: "Union planning a
strike ballot, no date confirmed -> send as bulletin only, no WarRoom" — reportable but not
WarRoom-eligible. Same fact pattern, two different answers, both encoded.

**Labor Disruption is the opposite — it reports at the earliest possible signal.** "Send Pre-Alert
immediately upon receiving the first credible signal or media feed, even if: the strike date is
unspecified | union votes confirming a strike (even without disclosed locations) | announcements
of strike intention even if voting is pending". Its only hard DO-NOT is a called-off strike, which
inverts to Not Impactful, plus commuter-only disruptions.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    IMPACTFUL,
    NEEDS_CONTEXT_REVIEW,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    evidence,
    get,
)
from .connection import connection_cascade, mapped_party, unresolved_cascade
from .global_gate import apply_global_gate

YES_NO = frozenset({"YES", "NO"})

# --- Airport Disruption ---------------------------------------------------------------------------

AIRPORT_EVENT_TYPE = "Airport Disruption"
AIRPORT_SOURCE = "rules/event-types-manmade.md § Airport Disruption (slide 3)"

CARGO_IMPACT = frozenset({"CARGO_DISRUPTED", "PASSENGER_ONLY", "NO_FLIGHT_DISRUPTION"})
AIRPORT_PROFILE = frozenset({"MAPPED", "NON_MAPPED_WITH_CARGO", "DOMESTIC_NO_CARGO"})
DISRUPTION_SCALE = frozenset(
    {"COMPLETE_HALT", "HIGH_CANCELLATIONS", "PARTIAL", "MINOR_RESOLVED_QUICKLY"}
)

_AP_MAPPED = "If the airport is mapped, we report straightaway."
_AP_CARGO = "If cargo activity is disrupted, notify straightaway."
_AP_HALT = "The airport halts its activities completely."
_AP_CANCEL = (
    "The airport reports a high number of flight cancelations, affecting cargo movement"
)
_AP_PASSENGER = "If a Passenger activity stops, notify only if major flights canceled."
_AP_DONT = (
    "DO NOT NOTIFY: Disruption affects only passenger flights (no cargo impact) | Domestic-only "
    "airport with no cargo | Minor disruption, resolved quickly | Fire in aircraft hangar or "
    "airport parking, no flight disruptions | Strike - if only a ballot is scheduled, and no "
    "strike date set"
)
_AP_AVOID = "Partial disruptions, no impact on cargo; Operations resumed - Avoid"
_AP_STRIKE = "Under airport disruptions, we also notify labor strikes threatening an airport."


def decide_airport_disruption(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=AIRPORT_EVENT_TYPE)
    if gate is not None:
        return gate

    profile = get(fields, "airport_profile", allowed=AIRPORT_PROFILE)
    cargo = get(fields, "cargo_impact", allowed=CARGO_IMPACT)
    scale = get(fields, "disruption_scale", allowed=DISRUPTION_SCALE)
    ballot_only = get(fields, "strike_ballot_only_no_date", allowed=YES_NO)
    trail = evidence(fields, "airport_profile", "cargo_impact", "disruption_scale")

    # R1 — a domestic airport with no cargo is out before anything else is considered. The
    # WarRoom guidance is even blunter: "Non-mapped airport with NO cargo -> DO NOT REPORT".
    if profile == "DOMESTIC_NO_CARGO":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="AP.R1", rule_text=_AP_DONT,
            source=AIRPORT_SOURCE, threshold_met=False, warroom_eligible=False, evidence=trail,
        )

    # R2 — a strike ballot with no date set is explicitly a DO-NOT here (Port Disruption answers
    # the same fact pattern differently; see that module).
    if ballot_only == "YES":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="AP.R2", rule_text=_AP_DONT,
            source=AIRPORT_SOURCE, threshold_met=False, warroom_eligible=False,
            evidence=trail + evidence(fields, "strike_ballot_only_no_date"),
            notes=("Port Disruption treats a dateless ballot as a bulletin-only event; Airport "
                   "excludes it outright. Divergence preserved from the slides.",),
        )

    # R3 — no flight disruption at all (the hangar/parking fire case).
    if cargo == "NO_FLIGHT_DISRUPTION":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="AP.R3", rule_text=_AP_DONT,
            source=AIRPORT_SOURCE, threshold_met=False, warroom_eligible=False, evidence=trail,
        )

    # R4 — a mapped airport reports straightaway, ahead of the cargo test.
    if profile == "MAPPED" or mapped_party(fields) == "YES":
        if scale == "MINOR_RESOLVED_QUICKLY" and cargo == "PASSENGER_ONLY":
            return Decision(
                classification=NOT_IMPACTFUL, rule_id="AP.R4b", rule_text=_AP_DONT,
                source=AIRPORT_SOURCE, threshold_met=False, warroom_eligible=False, evidence=trail,
            )
        return Decision(
            classification=IMPACTFUL, rule_id="AP.R4a", rule_text=_AP_MAPPED,
            source=AIRPORT_SOURCE, threshold_met=True, warroom_eligible=True, evidence=trail,
        )

    # R5 — cargo disrupted is reportable straightaway at any airport.
    if cargo == "CARGO_DISRUPTED":
        return Decision(
            classification=IMPACTFUL, rule_id="AP.R5", rule_text=_AP_CARGO,
            source=AIRPORT_SOURCE, threshold_met=True, warroom_eligible=True, evidence=trail,
        )

    # R6 — a complete halt affects cargo by definition.
    if scale == "COMPLETE_HALT":
        return Decision(
            classification=IMPACTFUL, rule_id="AP.R6", rule_text=_AP_HALT,
            source=AIRPORT_SOURCE, threshold_met=True, warroom_eligible=True, evidence=trail,
        )

    # R7 — passenger-only. Reportable only on major cancellations, per the conditional.
    if cargo == "PASSENGER_ONLY":
        if scale == "HIGH_CANCELLATIONS":
            return Decision(
                classification=IMPACTFUL, rule_id="AP.R7a",
                rule_text=_AP_PASSENGER + "  ||  " + _AP_CANCEL,
                source=AIRPORT_SOURCE, threshold_met=True, warroom_eligible=True, evidence=trail,
            )
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="AP.R7b",
            rule_text=_AP_DONT + "  ||  " + _AP_AVOID,
            source=AIRPORT_SOURCE, threshold_met=False, warroom_eligible=False, evidence=trail,
            notes=("Cargo is the axis this event type turns on; passenger-only disruption "
                   "clears the bar only on major cancellations.",),
        )

    if scale == "MINOR_RESOLVED_QUICKLY":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="AP.R8", rule_text=_AP_DONT,
            source=AIRPORT_SOURCE, threshold_met=False, warroom_eligible=False, evidence=trail,
        )

    return Decision(
        classification=THRESHOLD_REVIEW, rule_id="AP.R9",
        rule_text=_AP_CARGO + "  ||  " + _AP_DONT, source=AIRPORT_SOURCE,
        missing_fields=tuple(
            n for n, v in (("cargo_impact", cargo), ("airport_profile", profile),
                           ("disruption_scale", scale)) if v == UNKNOWN
        ) or ("cargo_impact",),
        evidence=trail,
    )


# --- Port Disruption ------------------------------------------------------------------------------

PORT_EVENT_TYPE = "Port Disruption"
PORT_SOURCE = "rules/event-types-manmade.md § Port Disruption (slide 38)"

PORT_PROFILE = frozenset({"CONTAINER_OR_CARGO_PORT", "LOCAL_PORT_NO_LOGISTICS"})

_PT_CONTAINER = "We notify disruptions at ports with container activities"
_PT_CARGO = "Cargo activity disrupted? Notify straightaway"
_PT_FUTURE = "Expected disruptions in the future? Notify today and send an update later"
_PT_LOCAL = "Local port with no logistics movement, we do not report it"
_PT_BALLOT = (
    "Union planning a strike ballot, no date confirmed -> send as bulletin only, no WarRoom"
)
_PT_CONFIRMED = (
    "Once the strike date is confirmed by vote -> Send update and create a WarRoom"
)


def decide_port_disruption(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=PORT_EVENT_TYPE)
    if gate is not None:
        return gate

    profile = get(fields, "port_profile", allowed=PORT_PROFILE)
    trail = evidence(fields, "port_profile", "cargo_activity_disrupted")

    if profile == "LOCAL_PORT_NO_LOGISTICS":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="PT.R1", rule_text=_PT_LOCAL,
            source=PORT_SOURCE, threshold_met=False, warroom_eligible=False, evidence=trail,
        )
    if profile == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="PT.R2",
            rule_text=_PT_CONTAINER + "  ||  " + _PT_LOCAL, source=PORT_SOURCE,
            missing_fields=("port_profile",), evidence=trail,
        )

    # A dateless strike ballot is reportable here as a bulletin, but is not WarRoom-eligible —
    # the opposite of Airport Disruption, which excludes it outright.
    if get(fields, "strike_ballot_only_no_date", allowed=YES_NO) == "YES":
        return Decision(
            classification=IMPACTFUL, rule_id="PT.R3", rule_text=_PT_BALLOT,
            source=PORT_SOURCE, threshold_met=True, warroom_eligible=False,
            evidence=trail + evidence(fields, "strike_ballot_only_no_date"),
            notes=("Bulletin only, no WarRoom. Airport Disruption excludes the same fact pattern "
                   "outright; divergence preserved from the slides.",),
        )

    return Decision(
        classification=IMPACTFUL, rule_id="PT.R4",
        rule_text=_PT_CONTAINER + "  ||  " + _PT_CARGO + "  ||  " + _PT_FUTURE,
        source=PORT_SOURCE, threshold_met=True, warroom_eligible=True,
        evidence=trail + evidence(fields, "strike_date_confirmed"),
        notes=("A container/cargo port is in scope for the full sub-type list — congestion, "
               "strikes, shutdowns, spills, customs, ship accidents.",),
    )


# --- Labor Disruption -------------------------------------------------------------------------------

LABOR_EVENT_TYPE = "Labor Disruption"
LABOR_SOURCE = "rules/event-types-manmade.md § Labor Disruption (slide 31)"

STRIKE_STATUS = frozenset(
    {
        "INTENTION_OR_BALLOT_PENDING",
        "VOTE_CONFIRMED",
        "FUTURE_DATED",
        "UNDERWAY",
        "CALLED_OFF",
        "CONTRACT_NEGOTIATIONS_ON",
    }
)
STRIKE_TARGET = frozenset({"PORT", "AIRPORT", "COMMUTER_TRANSPORT_ONLY", "OTHER"})

_LD_PREALERT = (
    "Send Pre-Alert immediately upon receiving the first credible signal or media feed, even if: "
    "The strike date is unspecified | Union votes confirming a strike (even without disclosed "
    "locations) | Announcements of strike intention even if voting is pending | The strike is "
    "tentatively scheduled for a future date"
)
_LD_NOTIFY = (
    "Notify: If a supplier is involved | If important utility services involved including major "
    "ports/airports | If product lines and applications match our verticals | If a strike has "
    "already started | If Contract negotiations are ON"
)
_LD_SERVICE = (
    "For Services sector, check if the company is serving the verticals we cover, including "
    "logistics, cargo shipping, port, airport, petrochemicals, specialty chemicals provider, IT "
    "company, utility provider, postal services, freight, rail, metal, mining, regulatory bodies, "
    "data center, etc."
)
_LD_CALLED_OFF = "Strike Called Off? Mark as Not Impactful."
_LD_COMMUTER = "Do NOT send alerts for commuter-only disruptions."
_LD_RECLASSIFY = (
    "Strikes likely to affect ports or airports -> classify as PORT/AIRPORT DISRUPTION."
)


def decide_labor_disruption(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=LABOR_EVENT_TYPE)
    if gate is not None:
        return gate

    status = get(fields, "strike_status", allowed=STRIKE_STATUS)
    target = get(fields, "strike_target", allowed=STRIKE_TARGET)
    trail = evidence(fields, "strike_status", "strike_target")

    # R1 — a called-off strike inverts to Not Impactful. `global-rules` #5 names this event type
    # as the example of a type that DOES stand down once resolved, unlike Factory Fire.
    if status == "CALLED_OFF":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="LD.R1", rule_text=_LD_CALLED_OFF,
            source=LABOR_SOURCE, threshold_met=False, warroom_eligible=False, evidence=trail,
        )

    # R2 — commuter-only disruption is excluded outright.
    if target == "COMMUTER_TRANSPORT_ONLY":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="LD.R2", rule_text=_LD_COMMUTER,
            source=LABOR_SOURCE, threshold_met=False, warroom_eligible=False, evidence=trail,
        )

    # R3 — reroute a port/airport strike rather than deciding it. Both destinations apply
    # stricter tests (an airport strike still has to clear the cargo bar), so deciding it here
    # under this slide's permissive pre-alert rules would over-report.
    if target in {"PORT", "AIRPORT"}:
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW, rule_id="LD.R3", rule_text=_LD_RECLASSIFY,
            source=LABOR_SOURCE, missing_fields=("event_type_reassignment",), evidence=trail,
            reroute_to="Port Disruption" if target == "PORT" else "Airport Disruption",
            notes=("Rerouted, not decided: the destination applies a stricter test than this "
                   "slide's pre-alert rules.",),
        )

    if status == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="LD.R4", rule_text=_LD_PREALERT,
            source=LABOR_SOURCE, missing_fields=("strike_status",), evidence=trail,
        )

    # R5 — every remaining status is reportable at the earliest signal, subject only to the
    # connection cascade. That is the point of the pre-alert rule.
    decision = connection_cascade(
        fields, rule_prefix="LD", source=LABOR_SOURCE,
        mapped_line=_LD_PREALERT + "  ||  " + _LD_NOTIFY,
        product_line=_LD_NOTIFY, service_line=_LD_SERVICE,
    )
    return decision or unresolved_cascade(
        fields, rule_prefix="LD", source=LABOR_SOURCE, rule_text=_LD_NOTIFY,
    )
