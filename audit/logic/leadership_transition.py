"""Leadership Transition threshold logic.

Source: `audit/rules/event-types-manmade.md` § Leadership Transition (slide 33).
Priority: P4. **No supplied extraction schema** — fields are author-derived (see
`audit/EVENT_TYPE_BUILD_ORDER.md`).

This is the **strictest** event type built so far, and the mirror image of Chemical Spill. Two
source lines gate everything:

> "Notify only when a partner is involved, and sites are mapped"
> "Notify only CEO/CFO/COO change"

Both are hard requirements — note "only" appears three times on the slide. So:

- A CEO change at an unmapped company is Not Impactful.
- A General Counsel, CMO, CTO or division-head change is Not Impactful **even at a mapped
  partner**, because the role list is closed.

The one softener is the executive-level line — "Executive level changes (only if it can lead to
changes in the supply chain department)" — which admits a non-CEO/CFO/COO role *only* on a
demonstrated supply-chain consequence, not on seniority. That conditional is encoded as its own
field rather than folded into the role check, because treating it as a general escape hatch
would quietly reopen the closed role list.

Severity is pinned by the source: "FYI event. Always gauged Low." Per the global rule that
Supplier Impact Confirmation is not sent for LOW severity, that has a real downstream effect, so
`Decision.severity` is set here rather than left for a later guess.

In the 216-row feed sample this type was ~5% of rows and almost all of them were appointment
announcements at companies with no mapped-partner relationship — i.e. a large, clean removal.
That makes the strictness of the role list load-bearing for the workload funnel: loosening it
would take back most of the saving.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    IMPACTFUL,
    LOW,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    evidence,
    get,
)
from .connection import MAPPED_IS_INDUSTRY_RELEVANCE, derived_or_given
from .global_gate import apply_global_gate

EVENT_TYPE = "Leadership Transition"
SOURCE = "rules/event-types-manmade.md § Leadership Transition (slide 33)"

YES_NO = frozenset({"YES", "NO"})

#: Closed list, verbatim from "Notify only CEO/CFO/COO change". `OTHER_EXECUTIVE` is every other
#: title — General Counsel, CMO, CTO, division president, company secretary, managing director of
#: a subsidiary — and reaches the supply-chain conditional rather than the main path.
ROLE = frozenset({"CEO", "CFO", "COO", "OTHER_EXECUTIVE"})

#: Sub-types from the slide. Recorded as evidence; the source treats them alike, so none of them
#: rejects a row and none of them rescues one.
TRANSITION_NATURE = frozenset(
    {
        "RETIRES",
        "RESIGNS",
        "JOINS",
        "REMOVED_OR_LET_GO",
        "INVESTIGATED_OR_ARRESTED",
        "FRAUDULENT",
        "HEALTH_ISSUES",
    }
)

MUST_HAVE_FIELDS = (
    "role",
    "partner_involved",
    "sites_mapped",
    "supply_chain_department_consequence",
    "transition_nature",
    "announced",
)

_PARTNER_AND_MAPPED = "Notify only when a partner is involved, and sites are mapped"
_ROLE_ONLY = "Notify only CEO/CFO/COO change"
_EXEC_CONDITIONAL = (
    "Executive level changes (only if it can lead to changes in the supply chain department)"
)
_ANNOUNCED = "Notify when announced"
_MAPPED_ONLY = "Notify only for mapped companies"
_FYI = "FYI event. Always gauged Low."


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Leadership Transition reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    role = get(fields, "role", allowed=ROLE)
    # Both halves of "a partner is involved, AND sites are mapped" resolve through the same
    # industry-relevance test per the process-owner decision, so they no longer disagree: a
    # company relevant to our industries satisfies both.
    mapped = derived_or_given(fields, "sites_mapped")
    partner = derived_or_given(fields, "partner_involved")
    sc_consequence = get(fields, "supply_chain_department_consequence", allowed=YES_NO)
    announced = get(fields, "announced", allowed=YES_NO)
    get(fields, "transition_nature", allowed=TRANSITION_NATURE)

    trail = evidence(fields, "role", "transition_nature")

    # R1 — the mapped-partner gate, checked first because it rejects regardless of role. Both
    # halves of "a partner is involved, AND sites are mapped" must hold.
    if partner == "NO" or mapped == "NO":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="LT.R1",
            rule_text=_PARTNER_AND_MAPPED + "  ||  " + _MAPPED_ONLY + "  ||  " + MAPPED_IS_INDUSTRY_RELEVANCE,
            source=SOURCE,
            threshold_met=False,
            severity=LOW,
            warroom_eligible=False,
            evidence=evidence(fields, "partner_involved", "sites_mapped") + trail,
            notes=(
                "The source says 'only' — an unmapped company's CEO change is not reportable "
                "however senior the role.",
            ),
        )

    if partner == UNKNOWN or mapped == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="LT.R2",
            rule_text=_PARTNER_AND_MAPPED + "  ||  " + MAPPED_IS_INDUSTRY_RELEVANCE,
            source=SOURCE,
            missing_fields=tuple(
                name
                for name, value in (("partner_involved", partner), ("sites_mapped", mapped))
                if value == UNKNOWN
            ),
            evidence=trail,
            notes=(
                "Mapped status resolves through industry relevance, and neither that nor the "
                "product line was determined for this row.",
            ),
        )

    # R3 — role. Closed list; a non-CEO/CFO/COO title only survives via the explicit
    # supply-chain conditional below, never on seniority alone.
    if role == "OTHER_EXECUTIVE":
        if sc_consequence == "YES":
            return Decision(
                classification=IMPACTFUL,
                rule_id="LT.R3a",
                rule_text=_EXEC_CONDITIONAL,
                source=SOURCE,
                threshold_met=True,
                severity=LOW,
                warroom_eligible=True,
                evidence=evidence(fields, "supply_chain_department_consequence") + trail,
                notes=(
                    "Admitted by the executive-level conditional, not by the CEO/CFO/COO list.",
                ),
            )
        if sc_consequence == "NO":
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="LT.R3b",
                rule_text=_ROLE_ONLY + "  ||  " + _EXEC_CONDITIONAL,
                source=SOURCE,
                threshold_met=False,
                severity=LOW,
                warroom_eligible=False,
                evidence=evidence(fields, "supply_chain_department_consequence") + trail,
                notes=(
                    "Role is outside the closed CEO/CFO/COO list and no supply-chain "
                    "consequence was demonstrated — seniority alone does not qualify.",
                ),
            )
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="LT.R3c",
            rule_text=_EXEC_CONDITIONAL,
            source=SOURCE,
            missing_fields=("supply_chain_department_consequence",),
            evidence=trail,
        )

    if role == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="LT.R4",
            rule_text=_ROLE_ONLY,
            source=SOURCE,
            missing_fields=("role",),
            evidence=trail,
        )

    # R5 — CEO/CFO/COO at a mapped partner. "Notify when announced".
    if announced == "NO":
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="LT.R5",
            rule_text=_ANNOUNCED,
            source=SOURCE,
            missing_fields=("announced",),
            evidence=trail,
            notes=("Source notifies on announcement; an unannounced change has no trigger yet.",),
        )

    return Decision(
        classification=IMPACTFUL,
        rule_id="LT.R6",
        rule_text=_ROLE_ONLY + "  ||  " + _PARTNER_AND_MAPPED + "  ||  " + _FYI,
        source=SOURCE,
        threshold_met=True,
        severity=LOW,
        warroom_eligible=True,
        evidence=evidence(fields, "role", "partner_involved", "sites_mapped", "announced"),
        notes=(
            "Severity pinned LOW by the source, which suppresses Supplier Impact Confirmation "
            "under the global rule.",
        ),
    )
