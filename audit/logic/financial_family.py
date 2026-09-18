"""Bankruptcy, Financial Distress, Profit Warning, Fine and Price Fluctuation.

Sources: `event-types-manmade.md` §§ Bankruptcy (slide 4), Financial Distress (22), Fine (21),
Price Fluctuation (39), Profit Warning (46).

All five run the shared connection cascade, but three of them carry a qualifier that changes the
answer, and those are the reason this file exists rather than five near-identical stubs.

**Bankruptcy (P1) reports early and pins severity.** "Notify as soon as signs or talks of a
possible bankruptcy become public" — so a rumour stage is reportable here, unlike M&A where a
rumour with no named parties goes to review. And "Company mapped? Report with High Severity"
pins severity on the mapped branch, which matters downstream because Supplier Impact Confirmation
is suppressed only for LOW.

**Profit Warning and Financial Distress are supplier-only.** Both slides condition every DO-report
bullet on a supplier or partner: "Notify when a **supplier** is reevaluating the profit forecast",
"We create a WarRoom when Partner(s) involved". There is no product-line fallback for a company
that is not a supplier, so a profit warning from an unconnected listed company is Not Impactful
however large. This mirrors Layoffs' strictness and is the opposite of the general cascade.

**Fine distinguishes a fine from a settlement.** "Notify case settlements for partners only for
mapped partners or major companies from our verticals" — settlements carry a higher bar than
fines, and the WarRoom line adds "Settlement/fine? The impact is not needed unless financial
hazards expected". So a settlement at an unmapped, non-major company does not clear the bar even
when its product line connects.

Financial Distress also carries an oddity worth flagging rather than silently resolving: its own
slide ends with "Classify it as 'Other.'" That instruction conflicts with it being a named event
type with its own row in the Prioritization Matrix. Encoded as a note on every verdict, not acted
on — plan guardrail 15 says mark a rule conflict rather than invent a resolution.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    HIGH,
    IMPACTFUL,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    evidence,
    get,
)
from .connection import connection_cascade, derived_or_given, unresolved_cascade
from .global_gate import apply_global_gate

YES_NO = frozenset({"YES", "NO"})

# --- Bankruptcy --------------------------------------------------------------------------------

BANKRUPTCY_EVENT_TYPE = "Bankruptcy"
BANKRUPTCY_SOURCE = "rules/event-types-manmade.md § Bankruptcy (slide 4)"

BANKRUPTCY_STAGE = frozenset(
    {"SIGNS_OR_TALKS", "FILED", "PROCEEDING_UNDERWAY", "MISSED_OR_DEFAULT_PAYMENTS",
     "REBRANDING_AFTER_BANKRUPTCY"}
)

_BK_PROACTIVE = "Notify bankruptcy/insolvency proceeding proactively"
_BK_SIGNS = "Notify as soon as signs or talks of a possible bankruptcy become public."
_BK_MAPPED = "Company mapped? Report with High Severity"
_BK_PRODUCT = "Company Not mapped? Check if the product line & applications connect"
_BK_SERVICE = "Service provider - Check if the applications of the services offered within our vertices"


def decide_bankruptcy(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=BANKRUPTCY_EVENT_TYPE)
    if gate is not None:
        return gate
    stage = get(fields, "bankruptcy_stage", allowed=BANKRUPTCY_STAGE)
    if stage == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="BK.R1",
            rule_text=_BK_PROACTIVE + "  ||  " + _BK_SIGNS, source=BANKRUPTCY_SOURCE,
            missing_fields=("bankruptcy_stage",), evidence=evidence(fields, "bankruptcy_stage"),
        )
    decision = connection_cascade(
        fields, rule_prefix="BK", source=BANKRUPTCY_SOURCE,
        mapped_line=_BK_MAPPED, product_line=_BK_PRODUCT, service_line=_BK_SERVICE,
        severity_when_mapped=HIGH,
    )
    return decision or unresolved_cascade(
        fields, rule_prefix="BK", source=BANKRUPTCY_SOURCE, rule_text=_BK_PRODUCT,
    )


# --- Supplier-only types: Profit Warning and Financial Distress ---------------------------------

PROFIT_WARNING_EVENT_TYPE = "Profit Warning"
PROFIT_WARNING_SOURCE = "rules/event-types-manmade.md § Profit Warning (slide 46)"
FINANCIAL_DISTRESS_EVENT_TYPE = "Financial Distress"
FINANCIAL_DISTRESS_SOURCE = "rules/event-types-manmade.md § Financial Distress (slide 22)"

_PW_SUPPLIER = (
    "Notify when a supplier is reevaluating the profit forecast for a year | Notify when a "
    "supplier is withdrawing profit report | When a supplier company is reducing the profit "
    "forecast for the year"
)
_FD_PARTNER = "We create a WarRoom when Partner(s) involved"
_FD_TRIGGERS = (
    "Major Shareholder Withdrawal | Cancelation of Rights Issue & Debt Refinancing | Changes in "
    "Credit Rating: Downgrades by credit rating agencies that reflect deteriorating financial "
    "health and increased risk."
)
_FD_CLASSIFY_OTHER = "Classify it as \"Other.\""

FD_TRIGGER = frozenset(
    {"MAJOR_SHAREHOLDER_WITHDRAWAL", "RIGHTS_ISSUE_CANCELLED_OR_DEBT_REFINANCING",
     "CREDIT_RATING_DOWNGRADE", "NONE_OF_THESE"}
)


def _supplier_only(
    fields: Mapping[str, object], *, event_type: str, prefix: str, source: str, rule_text: str,
    extra_notes: tuple[str, ...] = (),
) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=event_type)
    if gate is not None:
        return gate
    supplier = derived_or_given(fields, "supplier_or_partner_involved")
    if supplier == "NO":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id=f"{prefix}.R1", rule_text=rule_text,
            source=source, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "supplier_or_partner_involved"),
            notes=(
                "This slide conditions every DO-report bullet on a supplier or partner and offers "
                "no product-line fallback, so company size is irrelevant.",
            ) + extra_notes,
        )
    if supplier == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id=f"{prefix}.R2", rule_text=rule_text,
            source=source, missing_fields=("supplier_or_partner_involved",),
            evidence=evidence(fields, "supplier_or_partner_involved"), notes=extra_notes,
        )
    return Decision(
        classification=IMPACTFUL, rule_id=f"{prefix}.R3", rule_text=rule_text, source=source,
        threshold_met=True, warroom_eligible=True,
        evidence=evidence(fields, "supplier_or_partner_involved"), notes=extra_notes,
    )


def decide_profit_warning(fields: Mapping[str, object]) -> Decision:
    return _supplier_only(
        fields, event_type=PROFIT_WARNING_EVENT_TYPE, prefix="PW",
        source=PROFIT_WARNING_SOURCE, rule_text=_PW_SUPPLIER,
    )


def decide_financial_distress(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=FINANCIAL_DISTRESS_EVENT_TYPE)
    if gate is not None:
        return gate
    trigger = get(fields, "distress_trigger", allowed=FD_TRIGGER)
    conflict_note = (
        "Source conflict, unresolved: this slide ends 'Classify it as \"Other.\"' yet Financial "
        "Distress is a named event type with its own Prioritization Matrix row. Flagged, not "
        "acted on.",
    )
    if trigger == "NONE_OF_THESE":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="FD.R0", rule_text=_FD_TRIGGERS,
            source=FINANCIAL_DISTRESS_SOURCE, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "distress_trigger"), notes=conflict_note,
        )
    if trigger == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="FD.R0", rule_text=_FD_TRIGGERS,
            source=FINANCIAL_DISTRESS_SOURCE, missing_fields=("distress_trigger",),
            evidence=evidence(fields, "distress_trigger"), notes=conflict_note,
        )
    return _supplier_only(
        fields, event_type=FINANCIAL_DISTRESS_EVENT_TYPE, prefix="FD",
        source=FINANCIAL_DISTRESS_SOURCE, rule_text=_FD_PARTNER + "  ||  " + _FD_TRIGGERS,
        extra_notes=conflict_note,
    )


# --- Fine --------------------------------------------------------------------------------------

FINE_EVENT_TYPE = "Fine"
FINE_SOURCE = "rules/event-types-manmade.md § Fine (slide 21)"

FINE_KIND = frozenset({"FINE", "SETTLEMENT"})

_FN_MAPPED = "If a mapped partner or its site is fined, notify with customer impact"
_FN_PRODUCT = "We notify if the product line and applications of the company match our verticals"
_FN_SETTLEMENT = (
    "Notify case settlements for partners only for mapped partners or major companies from our "
    "verticals"
)


def decide_fine(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=FINE_EVENT_TYPE)
    if gate is not None:
        return gate
    kind = get(fields, "fine_kind", allowed=FINE_KIND)
    mapped = get(fields, "mapped_or_prominent_party_involved", allowed=YES_NO)

    # A settlement carries a higher bar than a fine: mapped partner OR a major company from our
    # verticals, with no plain product-connection route.
    if kind == "SETTLEMENT":
        major = derived_or_given(fields, "major_company_in_our_verticals")
        if mapped == "YES" or major == "YES":
            return Decision(
                classification=IMPACTFUL, rule_id="FN.S1", rule_text=_FN_SETTLEMENT,
                source=FINE_SOURCE, threshold_met=True, warroom_eligible=True,
                evidence=evidence(fields, "fine_kind", "mapped_or_prominent_party_involved",
                                  "major_company_in_our_verticals"),
            )
        if mapped == "NO" and major == "NO":
            return Decision(
                classification=NOT_IMPACTFUL, rule_id="FN.S2", rule_text=_FN_SETTLEMENT,
                source=FINE_SOURCE, threshold_met=False, warroom_eligible=False,
                evidence=evidence(fields, "fine_kind", "mapped_or_prominent_party_involved",
                                  "major_company_in_our_verticals"),
                notes=("Settlements carry a higher bar than fines — 'only for mapped partners or "
                       "major companies from our verticals' — so a connected product line does "
                       "not clear it.",),
            )
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="FN.S3", rule_text=_FN_SETTLEMENT,
            source=FINE_SOURCE, missing_fields=("major_company_in_our_verticals",),
            evidence=evidence(fields, "fine_kind", "mapped_or_prominent_party_involved"),
        )

    decision = connection_cascade(
        fields, rule_prefix="FN", source=FINE_SOURCE,
        mapped_line=_FN_MAPPED, product_line=_FN_PRODUCT,
        service_line=_FN_PRODUCT,
    )
    return decision or unresolved_cascade(
        fields, rule_prefix="FN", source=FINE_SOURCE, rule_text=_FN_PRODUCT,
    )


# --- Price Fluctuation --------------------------------------------------------------------------

PRICE_EVENT_TYPE = "Price Fluctuation"
PRICE_SOURCE = "rules/event-types-manmade.md § Price Fluctuation (slide 39)"

MOVE_SIGNIFICANCE = frozenset({"SIGNIFICANT_OR_EXPECTED", "MINOR_OR_ROUTINE"})

_PF_APPLICATIONS = (
    "We notify if the affected product/commodity/ mineral has applications in our verticals"
)
_PF_SIGNIFICANT = (
    "Report only significant increase or decrease in prices occurs OR expected (sharp increase, "
    "price hike, price fall)"
)


def decide_price_fluctuation(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=PRICE_EVENT_TYPE)
    if gate is not None:
        return gate

    # The significance gate runs first: the source says "report ONLY significant ... " so a
    # routine price move is out regardless of how well the commodity connects.
    significance = get(fields, "move_significance", allowed=MOVE_SIGNIFICANCE)
    if significance == "MINOR_OR_ROUTINE":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="PF.R1", rule_text=_PF_SIGNIFICANT,
            source=PRICE_SOURCE, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "move_significance"),
        )
    if significance == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="PF.R2", rule_text=_PF_SIGNIFICANT,
            source=PRICE_SOURCE, missing_fields=("move_significance",),
            evidence=evidence(fields, "move_significance"),
        )
    decision = connection_cascade(
        fields, rule_prefix="PF", source=PRICE_SOURCE,
        mapped_line=_PF_APPLICATIONS, product_line=_PF_APPLICATIONS,
        service_line=_PF_APPLICATIONS,
    )
    return decision or unresolved_cascade(
        fields, rule_prefix="PF", source=PRICE_SOURCE, rule_text=_PF_APPLICATIONS,
    )
