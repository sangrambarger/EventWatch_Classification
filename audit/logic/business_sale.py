"""Business Sale threshold logic.

Source: `audit/rules/event-types-manmade.md` § Business Sale (slide 6), with the cross-cutting
decisions in `audit/rules/global-rules.md`.

Business Sale sits deliberately close to Merger & Acquisition and differs on three points that
this module encodes explicitly, because the two are constantly confused in real feed data:

1. **A lower bar.** "Notify as soon as it is announced (signs/talks/plans)" with no sector
   exclusions. M&A gates six named sectors (retail, consulting/staffing, hospitality,
   investment/finance, insurance, crude oil, mining) on mapped/partner involvement; Business Sale
   does not gate any sector that way. A row rerouted here from `merger_acquisition.py` by its
   R2 rule is therefore being moved to a *more* permissive test, which is exactly why the
   reroute must happen rather than M&A deciding it.

2. **Completion is reported, not suppressed.** "Send updates on completion news." M&A says the
   opposite — "Do not send completion if the initial announcement has been notified". Same
   lifecycle stage, opposite handling; `merger_acquisition.py` carries the mirror of this note.

3. **Mapped status changes what is sent, not whether to report.** "Company mapped? - Send an
   impact with the initial bulletin. Company not mapped? - Send a bulletin if products have
   applications in the industries we cover." Both branches produce a bulletin when the product
   test passes, so unmapped status alone is never a reason to stand down here.

Priority is P3. Per `global-rules.md` #3 that is response urgency only, never an input to this
decision.
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
from .global_gate import apply_global_gate

EVENT_TYPE = "Business Sale"
SOURCE = "rules/event-types-manmade.md § Business Sale (slide 6)"

# --- Field schema ----------------------------------------------------------------------------
# AUTHOR-DERIVED: no extraction schema was supplied for Business Sale (see
# audit/EVENT_TYPE_BUILD_ORDER.md). Field names below are shared with merger_acquisition.py
# wherever the two rules read the same evidence, so a row can be rerouted between them without
# re-extraction.

SALE_STAGE = frozenset(
    {
        "ANNOUNCED",              # "Notify as soon as it is announced (signs/talks/plans)"
        "SIGNS_TALKS_OR_PLANS",   # same line
        "COMPLETED",              # "Send updates on completion news"
        "RUMOUR_NO_NAMED_PARTIES",
    }
)

YES_NO = frozenset({"YES", "NO"})

#: "Company not mapped? - Send a bulletin if products have applications in the industries we
#: cover."
PRODUCT_CONNECTION = frozenset({"CONNECTED", "NOT_CONNECTED"})

#: "If the service sector is involved - Check if their services have applications in our
#: vertical: logistics provider | cargo shipping | petrochemicals | specialty chemicals provider |
#: IT company | utility provider | farming company"
#: Note this list is *shorter* than M&A's: no travel, construction, recycling or communications.
#: The difference is preserved rather than harmonised — the two slides say different things and
#: inventing a merged list would be exactly the kind of quiet rule drift this project exists to
#: stop. A row whose service vertical appears on M&A's list but not this one resolves to
#: NOT_APPLICABLE here and is flagged in the spec as a known divergence.
SERVICE_APPLICABILITY = frozenset({"APPLICABLE", "NOT_APPLICABLE", "NOT_A_SERVICE_SECTOR"})

#: Sub-Types from the source slide, kept for reporting/grouping rather than for the decision.
SUB_TYPES = (
    "Sale involving factories/plants",
    "Sale involving Company (mapped/non-mapped)",
    "Business unit sale",
    "Subsidiary sale",
    "Asset sale",
    "Brand/portfolio sale",
)

MUST_HAVE_FIELDS = (
    "sale_stage",
    "mapped_or_prominent_party_involved",
    "product_line_connection",
    "service_sector_applicability",
)

# --- Verbatim source lines --------------------------------------------------------------------

_ANNOUNCE = "Notify as soon as it is announced (signs/talks/plans)"
_MAPPED = "Company mapped? - Send an impact with the initial bulletin."
_UNMAPPED = (
    "Company not mapped? - Send a bulletin if products have applications in the industries we "
    "cover."
)
_SERVICE = (
    "If the service sector is involved - Check if their services have applications in our "
    "vertical: logistics provider | cargo shipping| petrochemicals | specialty chemicals provider "
    "| IT company | utility provider| farming company"
)
_COMPLETION = "Send updates on completion news"
_MAPPED_HEURISTIC = (
    "global-rules.md #4: If the company/site is well-known and clearly important to one of the 27 "
    "industries, treat it as if it were mapped/critical ... Never dismiss a smaller or unfamiliar "
    "company purely because it isn't obviously 'big'. Check the product/commodity/service line for "
    "a plausible connection instead."
)


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Business Sale reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    stage = get(fields, "sale_stage", allowed=SALE_STAGE)
    mapped = get(fields, "mapped_or_prominent_party_involved", allowed=YES_NO)
    product = get(fields, "product_line_connection", allowed=PRODUCT_CONNECTION)
    service = get(fields, "service_sector_applicability", allowed=SERVICE_APPLICABILITY)

    # R1 — no named parties means no company to test mapping or product connection against.
    if stage == "RUMOUR_NO_NAMED_PARTIES":
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="BS.R1",
            rule_text=_ANNOUNCE,
            source=SOURCE,
            missing_fields=("seller_or_buyer_named",),
            evidence=evidence(fields, "sale_stage"),
        )
    if stage == UNKNOWN:
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="BS.R1",
            rule_text=_ANNOUNCE,
            source=SOURCE,
            missing_fields=("sale_stage",),
            evidence=evidence(fields, "sale_stage"),
        )

    # R2 — a mapped/prominent party makes this reportable on its own. The source attaches the
    # impact to the initial bulletin, which presupposes the bulletin; no product test is needed.
    # Completion is handled by the same branch because R5 makes completion reportable anyway.
    if mapped == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="BS.R2",
            rule_text=_MAPPED,
            source=SOURCE,
            threshold_met=True,
            evidence=evidence(
                fields, "mapped_or_prominent_party_involved", "sale_stage"
            ),
            notes=("Mapped/prominent party: impact accompanies the initial bulletin.",),
        )

    # R3 — service sector applicability, checked before the general product test because a
    # service business often has no "product line" to assess at all.
    if service == "APPLICABLE":
        return Decision(
            classification=IMPACTFUL,
            rule_id="BS.R3a",
            rule_text=_SERVICE,
            source=SOURCE,
            threshold_met=True,
            evidence=evidence(fields, "service_sector_applicability", "sale_stage"),
        )
    if service == "NOT_APPLICABLE":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="BS.R3b",
            rule_text=_SERVICE,
            source=SOURCE,
            threshold_met=False,
            evidence=evidence(fields, "service_sector_applicability"),
            notes=(
                "Business Sale's service list is shorter than M&A's (no travel, construction, "
                "recycling or communications) — divergence preserved from the source slides.",
            ),
        )

    # R4 — the unmapped general test.
    if product == "CONNECTED":
        return Decision(
            classification=IMPACTFUL,
            rule_id="BS.R4a",
            rule_text=_UNMAPPED,
            source=SOURCE,
            threshold_met=True,
            evidence=evidence(
                fields, "mapped_or_prominent_party_involved", "product_line_connection"
            ),
        )
    if product == "NOT_CONNECTED":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="BS.R4b",
            rule_text=_UNMAPPED,
            source=SOURCE,
            threshold_met=False,
            evidence=evidence(
                fields, "mapped_or_prominent_party_involved", "product_line_connection"
            ),
        )

    # R5 — completion with nothing else established. Completion news is reportable here (the
    # opposite of M&A), but only once the row has cleared some connection test; a completion
    # story about an unconnected business is still unconnected.
    if stage == "COMPLETED":
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="BS.R5",
            rule_text=_COMPLETION + "  ||  " + _UNMAPPED,
            source=SOURCE,
            missing_fields=("product_line_connection",),
            evidence=evidence(fields, "sale_stage", "mapped_or_prominent_party_involved"),
            notes=(
                "Completion is reportable for Business Sale, but the connection test still "
                "decides whether this business is one we cover.",
            ),
        )

    # R6 — nothing resolved it. Per rule #13, unknown is not "not connected".
    return Decision(
        classification=THRESHOLD_REVIEW,
        rule_id="BS.R6",
        rule_text=_UNMAPPED + "  ||  " + _MAPPED_HEURISTIC,
        source=SOURCE,
        missing_fields=("product_line_connection",),
        evidence=evidence(fields, "sale_stage", "mapped_or_prominent_party_involved"),
        notes=("Fail-closed operational default under global-rules #4 is Impactful.",),
    )
