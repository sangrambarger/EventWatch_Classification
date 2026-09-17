"""Merger & Acquisition threshold logic.

Source: `audit/rules/event-types-manmade.md` § Merger & Acquisition (slide 35), with the
cross-cutting decisions in `audit/rules/global-rules.md`.

Two things in the source rules are easy to read past and are the reason this module exists as
code rather than prose:

1. **M&A carries a stricter bar than most event types, for six named sectors only.** Retail,
   consulting & staffing, hospitality, investment & finance, insurance, crude oil and mining are
   reportable *only if a mapped company or partner is involved* — the general "does the product
   line connect to a covered industry" test does not rescue them. Every other sector uses the
   general test.

2. **Completion is suppressed, and this is the opposite of Business Sale.** "Do not send
   completion if the initial announcement has been notified to the customers." Business Sale's
   own rules say "Send updates on completion news". Two adjacent event types, opposite handling
   of the same lifecycle stage; `business_sale.py` carries the mirror of this comment.

Priority is P4 — the lowest tier. Per `global-rules.md` #3 that is response urgency only and is
never a reason to lean Not Impactful; a P4 event meeting its criteria is still Impactful.
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
from .connection import mapped_party
from .global_gate import apply_global_gate

EVENT_TYPE = "Merger & Acquisition"
SOURCE = "rules/event-types-manmade.md § Merger & Acquisition (slide 35)"

# --- Field schema ----------------------------------------------------------------------------
# No extraction schema was supplied for this event type (the pack covers 35 types; M&A is not
# one of them — see audit/EVENT_TYPE_BUILD_ORDER.md). These field names are therefore
# AUTHOR-DERIVED from the verbatim reporting guidelines, and each is annotated with the source
# line it serves. Where a supplied schema exists for a later event type, its `must_have` names
# are used verbatim instead.

DEAL_STAGE = frozenset(
    {
        "ANNOUNCED",            # "Notify when the initial deal is announced - pre-regulatory approvals"
        "SIGNS_TALKS_OR_PLANS",  # same line; early-stage signals are in scope
        "REGULATORY_APPROVAL_PENDING",
        "COMPLETED",            # "Completion: Do not send completion if the initial announcement has been notified"
        "RUMOUR_NO_NAMED_PARTIES",
    }
)

#: The six sectors the source singles out for the stricter mapped/partner bar, plus NONE.
STRICT_BAR_SECTOR = frozenset(
    {
        "RETAIL",
        "CONSULTING_OR_STAFFING",
        "HOSPITALITY",
        "INVESTMENT_OR_FINANCE",
        "INSURANCE",
        "CRUDE_OIL",
        "MINING",
        "NONE",
    }
)

YES_NO = frozenset({"YES", "NO"})

#: "Product line and applications must be relevant to our verticals. Possible sub-tier or Tier 1
#: supplier yet to be mapped (decide based on product connection)."
PRODUCT_CONNECTION = frozenset({"CONNECTED", "NOT_CONNECTED"})

#: "If a service sector is involved, check if their services have applications in our industrial
#: verticals - logistics company, cargo shipping, travel, IT firm, agrochemicals, petrochemicals
#: or specialty chemicals, construction, manufacturing, recycling, communications, utility
#: supplier (Electricity, Water, Gas)."
SERVICE_APPLICABILITY = frozenset({"APPLICABLE", "NOT_APPLICABLE", "NOT_A_SERVICE_SECTOR"})

MUST_HAVE_FIELDS = (
    "deal_stage",
    "strict_bar_sector",
    "mapped_or_prominent_party_involved",
    "product_line_connection",
    "service_sector_applicability",
    "steel_company_involved",
    "steel_applications_match_or_partner_involved",
    "initial_announcement_already_notified",
    "selling_party_is_mapped_partner",
)

# --- Verbatim source lines --------------------------------------------------------------------

_ANNOUNCE = "Notify when the initial deal is announced - pre-regulatory approvals"
_PRODUCT = (
    "Product line and applications must be relevant to our verticals. Possible sub-tier or Tier 1 "
    "supplier yet to be mapped (decide based on product connection)"
)
_SERVICE = (
    "If a service sector is involved, check if their services have applications in our industrial "
    "verticals - logistics company, cargo shipping, travel, IT firm, agrochemicals, petrochemicals "
    "or specialty chemicals, construction, manufacturing, recycling, communications, utility "
    "supplier (Electricity, Water, Gas)."
)
_STEEL = "Steel company (only if applications match or a partner is involved)"
_STRICT = (
    "Retail, consulting & staffing, hospitality, investment & Finance group, insurance firm, "
    "crude oil, or mining company- Notify if a mapped company/partner is involved."
)
_COMPLETION = "Do not send completion if the initial announcement has been notified to the customers."
_REROUTE = "If a mapped partner sells the business, notify it as a business sale."
_MAPPED_HEURISTIC = (
    "global-rules.md #4: If the company/site is well-known and clearly important to one of the 27 "
    "industries, treat it as if it were mapped/critical ... If, after checking both company "
    "prominence and product/vertical connection, the case is genuinely ambiguous, classify "
    "Impactful (safe default)."
)


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Merger & Acquisition reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    stage = get(fields, "deal_stage", allowed=DEAL_STAGE)
    sector = get(fields, "strict_bar_sector", allowed=STRICT_BAR_SECTOR)
    mapped = mapped_party(fields)
    product = get(fields, "product_line_connection", allowed=PRODUCT_CONNECTION)
    service = get(fields, "service_sector_applicability", allowed=SERVICE_APPLICABILITY)
    steel = get(fields, "steel_company_involved", allowed=YES_NO)
    steel_ok = get(fields, "steel_applications_match_or_partner_involved", allowed=YES_NO)
    already_notified = get(fields, "initial_announcement_already_notified", allowed=YES_NO)
    seller_is_partner = get(fields, "selling_party_is_mapped_partner", allowed=YES_NO)

    # R1 — a rumour with no named parties has nothing to test a threshold against.
    if stage == "RUMOUR_NO_NAMED_PARTIES":
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="MA.R1",
            rule_text=_ANNOUNCE,
            source=SOURCE,
            missing_fields=("acquirer_or_target_named",),
            evidence=evidence(fields, "deal_stage"),
            notes=("No named parties, so neither the sector bar nor the product test can run.",),
        )
    if stage == UNKNOWN:
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="MA.R1",
            rule_text=_ANNOUNCE,
            source=SOURCE,
            missing_fields=("deal_stage",),
            evidence=evidence(fields, "deal_stage"),
        )

    # R2 — reroute before deciding. The source is explicit that a mapped partner *selling* is a
    # Business Sale event "that will follow different criteria", so this module must not decide it.
    if seller_is_partner == "YES":
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="MA.R2",
            rule_text=_REROUTE,
            source=SOURCE,
            missing_fields=("event_type_reassignment",),
            evidence=evidence(fields, "selling_party_is_mapped_partner"),
            reroute_to="Business Sale",
            notes=(
                "Rerouted, not decided: Business Sale applies a different (lower) bar, so "
                "deciding it here would apply the wrong rule.",
            ),
        )

    # R3 — completion suppression. Note this fires only when the announcement was already sent;
    # a completion we never announced is still news and falls through to the normal tests.
    if stage == "COMPLETED":
        if already_notified == "YES":
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="MA.R3",
                rule_text=_COMPLETION,
                source=SOURCE,
                threshold_met=False,
                evidence=evidence(
                    fields, "deal_stage", "initial_announcement_already_notified"
                ),
                notes=("Duplicate of an already-notified announcement, per the source rule.",),
            )
        if already_notified == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW,
                rule_id="MA.R3",
                rule_text=_COMPLETION,
                source=SOURCE,
                missing_fields=("initial_announcement_already_notified",),
                evidence=evidence(fields, "deal_stage"),
                notes=(
                    "Completion story; whether it duplicates an earlier bulletin decides it, and "
                    "that is a notification-history lookup, not a fact in the row.",
                ),
            )

    # R4 — the six strict-bar sectors. Checked before the general product test, because the
    # source makes this bar a replacement for it, not an addition to it.
    if sector != "NONE" and sector != UNKNOWN:
        if mapped == "YES":
            return Decision(
                classification=IMPACTFUL,
                rule_id="MA.R4a",
                rule_text=_STRICT,
                source=SOURCE,
                threshold_met=True,
                evidence=evidence(
                    fields, "strict_bar_sector", "mapped_or_prominent_party_involved", "deal_stage"
                ),
            )
        if mapped == "NO":
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="MA.R4b",
                rule_text=_STRICT,
                source=SOURCE,
                threshold_met=False,
                evidence=evidence(
                    fields, "strict_bar_sector", "mapped_or_prominent_party_involved"
                ),
                notes=(
                    f"{sector} is one of the six sectors the source gates on mapped/partner "
                    "involvement; the general product-connection test does not apply here.",
                ),
            )
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="MA.R4c",
            rule_text=_STRICT + "  ||  " + _MAPPED_HEURISTIC,
            source=SOURCE,
            missing_fields=("mapped_or_prominent_party_involved",),
            evidence=evidence(fields, "strict_bar_sector"),
            notes=(
                "Mapped status is the whole test for this sector and no supplier-mapping "
                "database is available to this pipeline.",
            ),
        )

    # R5 — steel, which the source calls out separately with its own qualifier.
    if steel == "YES":
        if steel_ok == "NO":
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="MA.R5a",
                rule_text=_STEEL,
                source=SOURCE,
                threshold_met=False,
                evidence=evidence(
                    fields,
                    "steel_company_involved",
                    "steel_applications_match_or_partner_involved",
                ),
            )
        if steel_ok == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW,
                rule_id="MA.R5b",
                rule_text=_STEEL,
                source=SOURCE,
                missing_fields=("steel_applications_match_or_partner_involved",),
                evidence=evidence(fields, "steel_company_involved"),
            )
        return Decision(
            classification=IMPACTFUL,
            rule_id="MA.R5c",
            rule_text=_STEEL,
            source=SOURCE,
            threshold_met=True,
            evidence=evidence(
                fields, "steel_company_involved", "steel_applications_match_or_partner_involved"
            ),
        )

    # R6 — service sectors get their own applicability list.
    if service == "NOT_APPLICABLE":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="MA.R6a",
            rule_text=_SERVICE,
            source=SOURCE,
            threshold_met=False,
            evidence=evidence(fields, "service_sector_applicability"),
        )
    if service == "APPLICABLE":
        return Decision(
            classification=IMPACTFUL,
            rule_id="MA.R6b",
            rule_text=_SERVICE,
            source=SOURCE,
            threshold_met=True,
            evidence=evidence(fields, "service_sector_applicability", "deal_stage"),
        )

    # R7 — the general test: product line and applications relevant to the covered verticals.
    # `mapped == "YES"` satisfies it outright: under the process-owner decision that a company
    # relevant to our industries IS a mapped partner, mapped status and product relevance are the
    # same finding expressed two ways, so requiring the product field separately would send
    # rows to review over a question already answered.
    if product == "CONNECTED" or mapped == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="MA.R7a",
            rule_text=_PRODUCT,
            source=SOURCE,
            threshold_met=True,
            evidence=evidence(fields, "product_line_connection", "deal_stage"),
        )
    if product == "NOT_CONNECTED":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="MA.R7b",
            rule_text=_PRODUCT,
            source=SOURCE,
            threshold_met=False,
            evidence=evidence(fields, "product_line_connection"),
        )

    # R8 — product connection unknown, and nothing above resolved it. Rule #13 forbids reading
    # this as "not connected"; rule #4's safe default is recorded separately so Ops still has an
    # actionable verdict while the row sits in the review queue.
    return Decision(
        classification=THRESHOLD_REVIEW,
        rule_id="MA.R8",
        rule_text=_PRODUCT + "  ||  " + _MAPPED_HEURISTIC,
        source=SOURCE,
        missing_fields=("product_line_connection",),
        evidence=evidence(fields, "deal_stage", "strict_bar_sector"),
        notes=("Fail-closed operational default under global-rules #4 is Impactful.",),
    )
