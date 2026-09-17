"""'Others' — the residual event type.

Source: `audit/rules/event-types-other.md` § Others (slide 51).
Priority: P4. **No supplied extraction schema** — and correctly so; there is nothing type-specific
to extract.

> "These events are mostly new event types that we never covered before."
> "We notify events under OTHERs when we do not have a specific type to select"

This module is deliberately the thinnest in the package, because **`Others` is not a threshold,
it is an admission that no threshold applies.** The source gives no DO-report criteria beyond
"we had nowhere else to put it", so there is nothing here to test a row against.

That creates a real risk worth naming, since it is the kind of thing that quietly ruins an audit:
`Others` is an attractive dumping ground. A classifier that is unsure will reach for it, and
because it has no rejecting criteria, every row landing here would come out Impactful and the
funnel would show a large unexplained bulge of low-value "events". So this module resolves
**nothing** on its own — every row routes to `Needs Context Review`, which keeps it visible in
the review queue and out of both the Impactful and the Not Impactful counts.

Two consequences, both intended:

1. A genuinely novel event that belongs in `Others` reaches a human, which is exactly what
   "a new event type we never covered before" warrants.
2. A misrouted row — one that really belongs to a defined type — also reaches a human instead of
   being silently auto-reported, and the size of this queue becomes a **measurable signal of
   event-type classification quality**. A growing `Others` queue means the type classifier is
   failing, and the dashboard should surface it that way rather than hiding it inside an
   Impactful total.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    NEEDS_CONTEXT_REVIEW,
    Decision,
    evidence,
)
from .global_gate import apply_global_gate

EVENT_TYPE = "Other"
SOURCE = "rules/event-types-other.md § Others (slide 51)"

MUST_HAVE_FIELDS = ("candidate_specific_event_type",)

_NEW_TYPES = "These events are mostly new event types that we never covered before."
_NO_SPECIFIC = "We notify events under OTHERs when we do not have a specific type to select"
_NO_SUPPLIER_IMPACT = (
    "Don't Send supplier impact emails (unless manufacturing is confirmed affected)"
)


def decide(fields: Mapping[str, object]) -> Decision:
    """Route an 'Others' row to human review — this type has no threshold to apply.

    The global gate still runs first, so a row that is plainly not an event at all (market
    commentary, an expansion announcement, enforcement against an illicit actor) is still
    removed here rather than being parked in the review queue. Only rows that survive the gate
    and genuinely have no applicable event type reach a human.
    """
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    return Decision(
        classification=NEEDS_CONTEXT_REVIEW,
        rule_id="OT.R1",
        rule_text=_NEW_TYPES + "  ||  " + _NO_SPECIFIC,
        source=SOURCE,
        missing_fields=("candidate_specific_event_type",),
        evidence=evidence(fields, "story_nature", "subject_identifiable"),
        reroute_to=None,
        warroom_eligible=False,
        notes=(
            "'Others' carries no DO-report criteria, so no threshold can be applied and no "
            "automatic verdict is honest here.",
            "Queue size for this type is a quality signal for the event-type classifier, not a "
            "backlog to clear by auto-reporting.",
            _NO_SUPPLIER_IMPACT,
        ),
    )
