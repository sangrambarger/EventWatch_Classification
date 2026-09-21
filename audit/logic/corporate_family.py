"""Business Spin-off, Company Split and Corporate Restructuring.

Sources: `event-types-manmade.md` §§ Business Spin-off (slide 5), Company Split (slide 9),
Corporate Restructuring (slide 11). All three are P3.

These three sit alongside Merger & Acquisition and Business Sale in the corporate-structure
family that `global-rules.md` #8 explicitly carves out of its expansion/commentary short-circuit.
They share the standard connection cascade, and Company Split and Corporate Restructuring carry
an identical commodity rider that M&A words slightly differently:

| | M&A (slide 35) | Company Split / Corporate Restructuring (slides 9, 11) |
|---|---|---|
| Steel | "only if applications match **or a partner is involved**" | "strong product application **or** a partner is involved" |
| Mining | one of six sectors needing a mapped company/partner | "only if a partner is involved" |
| Crude oil | same six-sector bar | "only if a partner is involved" |
| Retail / consulting / hospitality / finance / insurance | mapped company or partner required | **no such bar** |

So a retail restructuring is reportable on product connection alone, while a retail acquisition
is not. That asymmetry is in the source slides and is preserved rather than harmonised — the
same discipline applied to Business Sale's shorter service list.

Business Spin-off has no commodity rider at all and is a plain cascade, plus "Send updates on
completion news" — so, like Business Sale and unlike M&A, completion is reported rather than
suppressed.
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
from .connection import connection_cascade, derived_or_given, unresolved_cascade
from .global_gate import apply_global_gate

YES_NO = frozenset({"YES", "NO"})
STAGE = frozenset({"ANNOUNCED", "SIGNS_TALKS_OR_PLANS", "COMPLETED", "RUMOUR_NO_NAMED_PARTIES"})

#: "Steel (strong product application or a partner is involved)" / "Mining company (only if a
#: partner is involved)" / "Crude (only if a partner is involved)".
COMMODITY_RIDER = frozenset({"STEEL", "MINING", "CRUDE_OIL", "NONE"})

MUST_HAVE_FIELDS = (
    "stage",
    "mapped_or_prominent_party_involved",
    "product_line_connection",
    "service_sector_applicability",
    "commodity_rider",
    "partner_involved",
)

_ANNOUNCE_SPINOFF = "Notify the spin-off as soon as it is announced."
_ANNOUNCE_SPLIT = "Notify as soon as it is announced (signs/talks/plans)"
_MAPPED_SPINOFF = "If a supplier company is involved, send impact with initial bulletins."
_MAPPED_SPLIT = "For a mapped company- Send an impact with the initial bulletin."
_PRODUCT_SPINOFF = "Company Not mapped? Check if the product line and applications connect."
_PRODUCT_SPLIT = (
    "If the company is not mapped - Send a bulletin if products have applications in the "
    "industries, we cover. Possible sub-tier or Tier 1 yet to be mapped (decide based on product "
    "line)"
)
_SERVICE_SPINOFF = (
    "If the service sector is involved - Check if their services have applications in our "
    "vertical: logistics provider | cargo shipping| petrochemicals | specialty chemicals provider "
    "| IT company | utility provider| farming company"
)
_SERVICE_SPLIT = "Services sector- Check if serving into the verticals we cover"
_COMPLETION_SPINOFF = "Send updates on completion news."
_STEEL = "Steel (strong product application or a partner is involved)"
_MINING = "Mining company (only if a partner is involved)"
_CRUDE = "Crude (only if a partner is involved)"


def _stage_guard(fields: Mapping[str, object], prefix: str, source: str, announce_line: str):
    stage = get(fields, "stage", allowed=STAGE)
    if stage == "RUMOUR_NO_NAMED_PARTIES":
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id=f"{prefix}.R1",
            rule_text=announce_line,
            source=source,
            missing_fields=("named_parties",),
            evidence=evidence(fields, "stage"),
        )
    if stage == UNKNOWN:
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id=f"{prefix}.R1",
            rule_text=announce_line,
            source=source,
            missing_fields=("stage",),
            evidence=evidence(fields, "stage"),
        )
    return None


def _commodity_rider(fields: Mapping[str, object], prefix: str, source: str) -> Decision | None:
    """Steel / mining / crude oil riders on Company Split and Corporate Restructuring.

    Mining and crude are gated on a partner **alone** — no product-connection escape — while
    steel accepts either a strong product application or a partner.
    """
    rider = get(fields, "commodity_rider", allowed=COMMODITY_RIDER)
    if rider in {"NONE", UNKNOWN}:
        return None
    # `partner_involved` is a supplier-mapping lookup no story answers, so it resolves through
    # industry relevance like every other member of DERIVED_FROM_RELEVANCE. Reading it raw here
    # made the mining and crude riders unreachable in practice: the field was always UNKNOWN, so
    # every rider row went to review.
    partner = derived_or_given(fields, "partner_involved")
    product = get(fields, "product_line_connection", allowed=frozenset({"CONNECTED", "NOT_CONNECTED"}))

    if rider in {"MINING", "CRUDE_OIL"}:
        line = _MINING if rider == "MINING" else _CRUDE
        if partner == "YES":
            return Decision(
                classification=IMPACTFUL, rule_id=f"{prefix}.RIDER_OK", rule_text=line,
                source=source, threshold_met=True, warroom_eligible=True,
                evidence=evidence(fields, "commodity_rider", "partner_involved"),
            )
        if partner == "NO":
            return Decision(
                classification=NOT_IMPACTFUL, rule_id=f"{prefix}.RIDER_NO", rule_text=line,
                source=source, threshold_met=False, warroom_eligible=False,
                evidence=evidence(fields, "commodity_rider", "partner_involved"),
                notes=(f"{rider} is gated on partner involvement alone; a connected product line "
                       "does not clear it.",),
            )
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id=f"{prefix}.RIDER_REVIEW", rule_text=line,
            source=source, missing_fields=("partner_involved",),
            evidence=evidence(fields, "commodity_rider"),
        )

    # Steel: either limb satisfies it.
    if partner == "YES" or product == "CONNECTED":
        return Decision(
            classification=IMPACTFUL, rule_id=f"{prefix}.STEEL_OK", rule_text=_STEEL,
            source=source, threshold_met=True, warroom_eligible=True,
            evidence=evidence(fields, "commodity_rider", "partner_involved",
                              "product_line_connection"),
        )
    if partner == "NO" and product == "NOT_CONNECTED":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id=f"{prefix}.STEEL_NO", rule_text=_STEEL,
            source=source, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "commodity_rider", "partner_involved",
                              "product_line_connection"),
        )
    return Decision(
        classification=THRESHOLD_REVIEW, rule_id=f"{prefix}.STEEL_REVIEW", rule_text=_STEEL,
        source=source,
        missing_fields=tuple(
            n for n, v in (("partner_involved", partner), ("product_line_connection", product))
            if v == UNKNOWN
        ) or ("partner_involved",),
        evidence=evidence(fields, "commodity_rider"),
    )


def _decide_split_family(fields, *, event_type, prefix, source):
    gate = apply_global_gate(fields, candidate_event_type=event_type)
    if gate is not None:
        return gate
    guard = _stage_guard(fields, prefix, source, _ANNOUNCE_SPLIT)
    if guard is not None:
        return guard
    rider = _commodity_rider(fields, prefix, source)
    if rider is not None:
        return rider
    decision = connection_cascade(
        fields, rule_prefix=prefix, source=source,
        mapped_line=_MAPPED_SPLIT, product_line=_PRODUCT_SPLIT, service_line=_SERVICE_SPLIT,
    )
    return decision or unresolved_cascade(
        fields, rule_prefix=prefix, source=source, rule_text=_PRODUCT_SPLIT,
    )


# --- Business Spin-off -------------------------------------------------------------------------

EVENT_TYPE = "Business Spin-off"
SOURCE = "rules/event-types-manmade.md § Business Spin-off (slide 5)"


def decide(fields: Mapping[str, object]) -> Decision:
    """Business Spin-off: a plain cascade, with completion reported rather than suppressed."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate
    guard = _stage_guard(fields, "BSO", SOURCE, _ANNOUNCE_SPINOFF)
    if guard is not None:
        return guard
    decision = connection_cascade(
        fields, rule_prefix="BSO", source=SOURCE,
        mapped_line=_MAPPED_SPINOFF, product_line=_PRODUCT_SPINOFF, service_line=_SERVICE_SPINOFF,
    )
    if decision is not None:
        return decision
    if get(fields, "stage") == "COMPLETED":
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="BSO.COMPLETION",
            rule_text=_COMPLETION_SPINOFF + "  ||  " + _PRODUCT_SPINOFF, source=SOURCE,
            missing_fields=("product_line_connection",),
            evidence=evidence(fields, "stage", "mapped_or_prominent_party_involved"),
            notes=("Completion is reportable for a spin-off (as for Business Sale, unlike M&A), "
                   "but the connection test still decides whether this is a business we cover.",),
        )
    return unresolved_cascade(
        fields, rule_prefix="BSO", source=SOURCE, rule_text=_PRODUCT_SPINOFF,
    )
