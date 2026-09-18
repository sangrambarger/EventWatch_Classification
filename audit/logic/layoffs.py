"""Layoffs threshold logic.

Source: `audit/rules/event-types-other.md` § Layoffs (slide 49). The slide also says "Notify
under labor disruptions", i.e. Layoffs is a reporting sub-type of Labor Disruption rather than a
separate notification category — but it carries its own DO-report criteria, so it gets its own
module and marks the grouping on the Decision.
Priority: Layoffs has no row of its own in the Prioritization Matrix; it inherits Labor
Disruption's P2. **No supplied extraction schema** — fields are author-derived.

One line does all the work, and it is unusually strict for this ruleset:

> "Only notify if a supplier is making layoffs"

No product-connection fallback, no industry test, no "possible unmapped sub-tier" rescue of the
kind Factory Fire and M&A both offer. A large, famous, obviously important company laying off
thousands of people is Not Impactful here unless it is a supplier. In the 216-row feed sample
this type showed up mostly as automaker job-cut stories, so the strictness matters to the funnel.

The counterweight, also explicit:

> "Notify even if layoffs are scheduled for future"

So a future-dated or announced-but-not-yet-executed layoff is in scope. `global-rules.md` #6's
materiality floor — which asks for a real signal before reporting something merely "scheduled" —
does **not** apply here, because this slide names future layoffs as reportable outright rather
than leaving it to a broadly-worded sub-type. Encoding #6 here would contradict the source.
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

EVENT_TYPE = "Layoffs"
#: No Layoffs row exists in priority-matrix.md; the slide files it under Labor Disruption.
PRIORITY_INHERITS_FROM = "Labor Disruption"
SOURCE = "rules/event-types-other.md § Layoffs (slide 49)"

YES_NO = frozenset({"YES", "NO"})

LAYOFF_NATURE = frozenset({"TEMPORARY", "PERMANENT", "FUTURE_SCHEDULED", "FURLOUGH"})
LAYOFF_SCOPE = frozenset({"EXACT_SITE_MAPPED", "GLOBAL", "SPECIFIC_DIVISION", "UNIDENTIFIED"})

MUST_HAVE_FIELDS = ("supplier_making_layoffs", "layoff_nature", "layoff_scope")

_ONLY_SUPPLIER = "Only notify if a supplier is making layoffs"
_FUTURE = "Notify even if layoffs are scheduled for future"
_SITE = "Send impact if the exact site is mapped"
_GLOBAL = "If layoffs happening globally, send impact to all sites"
_UNDER_LABOR = "Notify under labor disruptions"


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Layoffs reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    supplier = derived_or_given(fields, "supplier_making_layoffs")
    nature = get(fields, "layoff_nature", allowed=LAYOFF_NATURE)
    scope = get(fields, "layoff_scope", allowed=LAYOFF_SCOPE)
    trail = evidence(fields, "layoff_nature", "layoff_scope")

    if supplier == "NO":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="LO.R1",
            rule_text=_ONLY_SUPPLIER,
            source=SOURCE,
            threshold_met=False,
            warroom_eligible=False,
            evidence=evidence(fields, "supplier_making_layoffs") + trail,
            notes=(
                "The source offers no product-connection or industry fallback here, unlike "
                "Factory Fire or M&A — company size and prominence are irrelevant.",
            ),
        )
    if supplier == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="LO.R2",
            rule_text=_ONLY_SUPPLIER,
            source=SOURCE,
            missing_fields=("supplier_making_layoffs",),
            evidence=trail,
        )

    # A supplier is making layoffs. Every nature — including future-scheduled and furlough — is
    # reportable; scope only changes who the impact goes to.
    if nature == UNKNOWN and scope == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="LO.R3",
            rule_text=_FUTURE + "  ||  " + _SITE,
            source=SOURCE,
            missing_fields=("layoff_nature", "layoff_scope"),
            evidence=evidence(fields, "supplier_making_layoffs"),
        )

    return Decision(
        classification=IMPACTFUL,
        rule_id="LO.R4",
        rule_text=_ONLY_SUPPLIER + "  ||  " + _FUTURE + "  ||  " + _UNDER_LABOR,
        source=SOURCE,
        threshold_met=True,
        warroom_eligible=True,
        evidence=evidence(fields, "supplier_making_layoffs") + trail,
        notes=(
            "Reported under Labor Disruption per the slide. Scope decides impact routing "
            f"({_SITE} / {_GLOBAL}), not reportability.",
        ),
    )
