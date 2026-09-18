"""Mail/Postal/Package Delivery Services Disruptions threshold logic.

Source: `audit/rules/event-types-other.md` § Mail/Postal/Package Delivery Services Disruptions
(slide 47).
Priority: no row of its own in the Prioritization Matrix. The slide routes its sub-types to
"Labor disruptions OR port disruptions OR factory disruptions", all of which are P2, so P2 is
inherited. **No supplied extraction schema** — fields are author-derived.

The gate is a country-level one, which is unusual — every other event type gates on a site, a
region or a company:

> "Notify if we have sites in the country"

Above that gate the DO-report list is broad and needs no further qualification: service
disruptions, delays, shutdowns "due to whatever reason", fires/explosions/spills that could shut
a hub, national strikes, and a major postal service going bankrupt or being sold.

Note the last one. A postal service being **sold** is reportable here, and it would also satisfy
Business Sale's criteria. The slide's own sub-type note ("Notified under Labor disruptions OR
port disruptions OR factory disruptions") shows the source expects this type to overlap others
rather than own its rows exclusively, so `decide()` does not try to claim exclusivity — an
overlapping row reaching either module gets the same Impactful answer, which is the outcome that
matters.
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
from .connection import derived_or_given
from .global_gate import apply_global_gate

EVENT_TYPE = "Mail/Postal/Package Delivery Services Disruptions"
PRIORITY_INHERITS_FROM = "Labor Disruption"
SOURCE = "rules/event-types-other.md § Mail/Postal/Package Delivery Services Disruptions (slide 47)"

YES_NO = frozenset({"YES", "NO"})

#: The DO-report list, verbatim. `NONE_OF_THESE` is the only value that can reject.
DISRUPTION_KIND = frozenset(
    {
        "SERVICE_DISRUPTION_OR_DELAY",
        "EXPECTED_DELIVERY_DELAY",
        "SERVICE_SHUTDOWN",
        "HUB_FIRE_EXPLOSION_OR_SPILL",
        "NATIONAL_STRIKE_AFFECTING_POSTAL",
        "POSTAL_SERVICE_BANKRUPTCY_OR_SALE",
        "NONE_OF_THESE",
    }
)

MUST_HAVE_FIELDS = ("sites_in_country", "disruption_kind", "major_postal_operator")

_COUNTRY = "Notify if we have sites in the country"
_DISRUPTIONS = "Notify service disruptions/delays"
_DELAYS = "Notify expected delays in deliveries"
_SHUTDOWNS = "Notify service shutdowns due to whatever reason"
_HUB = (
    "Notify fires/explosions/spills and other events that can potentially shut down the "
    "cargo/postal hub(s)"
)
_STRIKES = "National strikes affecting postal services"
_BANKRUPT_SOLD = "Major postal service going bankrupt or getting sold"


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Mail/Postal reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    in_country = derived_or_given(fields, "sites_in_country")
    kind = get(fields, "disruption_kind", allowed=DISRUPTION_KIND)
    major = get(fields, "major_postal_operator", allowed=YES_NO)
    trail = evidence(fields, "disruption_kind", "major_postal_operator")

    # R1 — the country gate.
    if in_country == "NO":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="MP.R1",
            rule_text=_COUNTRY,
            source=SOURCE,
            threshold_met=False,
            warroom_eligible=False,
            evidence=evidence(fields, "sites_in_country") + trail,
            notes=(
                "Country-level gate — unusually coarse compared with other event types, but it "
                "is what the slide states.",
            ),
        )
    if in_country == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="MP.R2",
            rule_text=_COUNTRY,
            source=SOURCE,
            missing_fields=("sites_in_country",),
            evidence=trail,
        )

    if kind == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="MP.R3",
            rule_text=_DISRUPTIONS + "  ||  " + _SHUTDOWNS,
            source=SOURCE,
            missing_fields=("disruption_kind",),
            evidence=evidence(fields, "sites_in_country", "major_postal_operator"),
        )

    # R4 — bankruptcy or sale is qualified by "Major"; the other kinds are not.
    if kind == "POSTAL_SERVICE_BANKRUPTCY_OR_SALE":
        if major == "NO":
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="MP.R4a",
                rule_text=_BANKRUPT_SOLD,
                source=SOURCE,
                threshold_met=False,
                warroom_eligible=False,
                evidence=evidence(fields, "sites_in_country") + trail,
                notes=(
                    "The source qualifies this sub-type with 'Major'; a minor operator's sale "
                    "does not clear it here. It may still qualify under Business Sale on its own "
                    "criteria.",
                ),
            )
        if major == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW,
                rule_id="MP.R4b",
                rule_text=_BANKRUPT_SOLD,
                source=SOURCE,
                missing_fields=("major_postal_operator",),
                evidence=evidence(fields, "sites_in_country") + trail,
            )

    if kind == "NONE_OF_THESE":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="MP.R5",
            rule_text=_DISRUPTIONS + "  ||  " + _DELAYS + "  ||  " + _SHUTDOWNS,
            source=SOURCE,
            threshold_met=False,
            warroom_eligible=False,
            evidence=evidence(fields, "sites_in_country") + trail,
        )

    return Decision(
        classification=IMPACTFUL,
        rule_id="MP.R6",
        rule_text=" || ".join([_COUNTRY, _DISRUPTIONS, _DELAYS, _SHUTDOWNS, _HUB, _STRIKES]),
        source=SOURCE,
        threshold_met=True,
        warroom_eligible=True,
        evidence=evidence(fields, "sites_in_country") + trail,
        notes=(
            "The slide expects overlap with Labor Disruption, Port Disruption and Factory "
            "Disruption rather than exclusive ownership of the row.",
        ),
    )
