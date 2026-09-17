"""Airworthiness threshold logic.

Source: `audit/rules/event-types-other.md` § Airworthiness (slide 48).
Priority: no row of its own in the Prioritization Matrix; the slide says "Notify under
Compliance", which is P3. **No supplied extraction schema** — fields are author-derived.

This is the simplest module in the set and the only **notify-always** event type:

> "Notify every AD on a daily basis"
> "Notify even if the company receiving the AD is not mapped"

An Airworthiness Directive is reportable unconditionally. There is no connection test, no
mapping gate, no severity bar — so this module has **no Not Impactful branch at all**, and that
absence is the rule, not an oversight.

Two operational details from the slide that are not reportability decisions but do belong on the
Decision, because downstream consumers need them:

- **Consolidation.** "Notify via 1 consolidated bulletin", "Send the bulletin out at around
  midday PST". So N airworthiness rows in a period collapse into one bulletin. For the workload
  funnel this matters: these rows are all Impactful yet they generate a single artefact, so
  counting them as N units of analyst work would overstate the burden. `consolidates_into` marks
  the grouping.
- **No customer impact.** "Customer Impact is not needed", so `warroom_eligible` is False even
  though every row is reportable — another case where the impact call and the WarRoom call
  genuinely diverge.

The only thing this module must get right is not accidentally rejecting a row. The single
review path exists for rows where it is unclear whether an actual AD was issued at all.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    evidence,
    get,
)
from .global_gate import apply_global_gate

EVENT_TYPE = "Airworthiness"
#: No Airworthiness row in priority-matrix.md; the slide files it under Compliance.
PRIORITY_INHERITS_FROM = "Compliance"
SOURCE = "rules/event-types-other.md § Airworthiness (slide 48)"

YES_NO = frozenset({"YES", "NO"})

MUST_HAVE_FIELDS = ("airworthiness_directive_issued", "issuing_authority", "recipient_company")

_EVERY_AD = "Notify every AD on a daily basis"
_CONSOLIDATED = "Notify via 1 consolidated bulletin"
_MIDDAY = "Send the bulletin out at around midday PST"
_EVEN_UNMAPPED = "Notify even if the company receiving the AD is not mapped"
_NO_IMPACT = "Customer Impact is not needed"


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Airworthiness reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    issued = get(fields, "airworthiness_directive_issued", allowed=YES_NO)

    if issued == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="AW.R1",
            rule_text=_EVERY_AD,
            source=SOURCE,
            missing_fields=("airworthiness_directive_issued",),
            evidence=evidence(fields, "issuing_authority", "recipient_company"),
            notes=(
                "Whether an AD was actually issued is the only question this type asks; "
                "everything else about the row is irrelevant to reportability.",
            ),
        )

    if issued == "NO":
        # Not an AD at all. Reroute rather than reject: an aviation-safety story that is not an
        # Airworthiness Directive is likely a different event type (Compliance, FDA/EMA/OSHA
        # Action, Airport Disruption), and this module has no authority to decide those.
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="AW.R2",
            rule_text=_EVERY_AD,
            source=SOURCE,
            missing_fields=("event_type_reassignment",),
            evidence=evidence(fields, "airworthiness_directive_issued"),
            reroute_to="Compliance",
            notes=(
                "No AD issued, so the Airworthiness rules do not apply; sent back for event-type "
                "reassignment rather than decided here.",
            ),
        )

    return Decision(
        classification=IMPACTFUL,
        rule_id="AW.R3",
        rule_text=_EVERY_AD + "  ||  " + _EVEN_UNMAPPED + "  ||  " + _CONSOLIDATED,
        source=SOURCE,
        threshold_met=True,
        # "Customer Impact is not needed" — reportable, but no WarRoom.
        warroom_eligible=False,
        evidence=evidence(
            fields, "airworthiness_directive_issued", "issuing_authority", "recipient_company"
        ),
        notes=(
            "Notify-always: no mapping gate and no connection test exist for this type.",
            f"Consolidated — {_CONSOLIDATED}, {_MIDDAY}. Many rows produce one bulletin, so "
            "these should not be counted as one unit of analyst work each.",
            _NO_IMPACT,
        ),
    )


#: Marks that every Impactful row of this type merges into a single daily bulletin, so the
#: workload funnel can count artefacts rather than rows for this event type.
CONSOLIDATES_INTO = "one daily bulletin, ~midday PST"
