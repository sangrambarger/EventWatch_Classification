"""Cross-cutting gate applied to every row before any event-type rule runs.

Encodes the process-owner decisions in `audit/rules/global-rules.md` that short-circuit the whole
procedure — the ones that answer "is there a disruption to evaluate at all?" before anyone looks
up a threshold.

The trap this module exists to avoid is rule #8's own carve-out, and it is worth spelling out
because getting it backwards silently deletes the highest-volume event type in the feed:

> Rule #8 classifies expansions, resumptions and pure market commentary as Not Impactful — but it
> **explicitly does NOT reach into Business Sale, Business Spin-off, Merger & Acquisition or
> Corporate Restructuring.** Those are their own event types with their own DO-report criteria. A
> company being acquired, sold, split or restructured is a real corporate-structure change worth
> tracking "regardless of whether it reads as positive news".

So "Nestlé sells its vitamins business for $1bn" is *not* a rule-#8 expansion story even though
nothing is being disrupted, while "Chevron will allocate $7bn to double production in Venezuela"
is — the difference is whether the story corresponds to a defined event type at all. In a
216-row sample of real feed data, Merger & Acquisition plus Business Sale was the single largest
group (~14%); a gate that swallowed them would look like a spectacular workload reduction and be
entirely wrong.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    NEEDS_CONTEXT_REVIEW,
    NOT_IMPACTFUL,
    UNKNOWN,
    Decision,
    evidence,
    get,
)

SOURCE = "rules/global-rules.md"

#: Event types that rule #8's expansion/resumption/commentary carve-out must never touch,
#: quoted from the rule itself.
CORPORATE_STRUCTURE_TYPES = frozenset(
    {
        "Business Sale",
        "Business Spin-off",
        "Merger & Acquisition",
        "Corporate Restructuring",
    }
)

STORY_NATURE_VALUES = frozenset(
    {
        "DISRUPTION_OR_RISK_SIGNAL",
        "ORGANIC_EXPANSION_OR_INVESTMENT",
        "RESUMPTION_OR_ALL_CLEAR_ONLY",
        "MARKET_COMMENTARY_NO_PHYSICAL_EVENT",
        "ENFORCEMENT_AGAINST_ILLICIT_ACTOR",
        "CORPORATE_STRUCTURE_CHANGE",
        "RECYCLED_REMINDER_OF_KNOWN_DEVELOPMENT",
    }
)

SUBJECT_IDENTIFIABLE_VALUES = frozenset({"YES", "NO"})

# Verbatim source lines, so a verdict can be traced without opening the rules file.
_R8_EXPANSION = (
    "Expansion/growth/investment announcements with no disruption angle. ... Do not let company "
    "prominence or headline dollar amounts override the basic question of whether a disruption is "
    "being described at all."
)
_R8_RESUMPTION = (
    "Resumption/recovery-only follow-ups. Once a previously-disruptive event is confirmed over "
    "and operations have resumed normally, a later story whose only content is 'operations have "
    "now resumed' is not independently reportable."
)
_R8_COMMENTARY = (
    "Financial/crypto market commentary with no described physical or operational event. ... No "
    "company, asset, or price-movement story qualifies for Impactful unless it describes an "
    "actual physical/operational disruption, not just market reaction to one."
)
_R16_ENFORCEMENT = (
    "A law-enforcement or regulatory action against an illegitimate operation ... is not a "
    "supply-chain disruption to a legitimate supplier. It's the reverse: authorities disrupting "
    "an illegitimate one."
)
_R12_REMINDER = (
    "Those are recycled solicitation notices about a lawsuit that was already reported ... they "
    "contain no new legal development, just a deadline reminder."
)
_R13_THIN = (
    "'No stated industry connection' is not the same as 'no information at all' ... before citing "
    "'no industry connection' as your reason, confirm you actually know what the story is about."
)


def apply_global_gate(
    fields: Mapping[str, object], candidate_event_type: str | None = None
) -> Decision | None:
    """Return a short-circuit Decision, or None to continue to the event-type rules.

    `candidate_event_type` is the type the row has been assigned so far. It is needed only to
    honour rule #8's corporate-structure carve-out; pass None when the type is not yet known and
    the carve-out is applied on `story_nature` alone.
    """
    nature = get(fields, "story_nature", allowed=STORY_NATURE_VALUES)
    subject_known = get(fields, "subject_identifiable", allowed=SUBJECT_IDENTIFIABLE_VALUES)

    # Rule #13 first: a row too thin to identify anything is "unknown", not "unconnected", and
    # must never be resolved by a downstream "no connection" branch. Checked before the #8
    # patterns because deciding a story is mere commentary also requires knowing what it is about.
    if subject_known == "NO":
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="GLOBAL.R13",
            rule_text=_R13_THIN,
            source=SOURCE,
            missing_fields=("subject_identifiable",),
            evidence=evidence(fields, "subject_identifiable"),
            notes=(
                "Row is too thin to identify a subject; 'can't tell' is not 'no connection'.",
            ),
        )
    if subject_known == UNKNOWN:
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="GLOBAL.R13",
            rule_text=_R13_THIN,
            source=SOURCE,
            missing_fields=("subject_identifiable",),
            evidence=evidence(fields, "subject_identifiable"),
        )

    if nature == UNKNOWN:
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="GLOBAL.R8",
            rule_text=_R8_EXPANSION,
            source=SOURCE,
            missing_fields=("story_nature",),
            evidence=evidence(fields, "story_nature"),
            notes=(
                "Cannot tell whether a disruption is described at all, so no threshold applies "
                "yet.",
            ),
        )

    # The carve-out. A corporate-structure change is governed by its own event type's rules, so
    # the #8 patterns below are not even consulted for it.
    in_carve_out = (
        candidate_event_type in CORPORATE_STRUCTURE_TYPES
        or nature == "CORPORATE_STRUCTURE_CHANGE"
    )
    if in_carve_out:
        return None

    short_circuits = {
        "ORGANIC_EXPANSION_OR_INVESTMENT": ("GLOBAL.R8a", _R8_EXPANSION),
        "RESUMPTION_OR_ALL_CLEAR_ONLY": ("GLOBAL.R8b", _R8_RESUMPTION),
        "MARKET_COMMENTARY_NO_PHYSICAL_EVENT": ("GLOBAL.R8c", _R8_COMMENTARY),
        "ENFORCEMENT_AGAINST_ILLICIT_ACTOR": ("GLOBAL.R16", _R16_ENFORCEMENT),
        "RECYCLED_REMINDER_OF_KNOWN_DEVELOPMENT": ("GLOBAL.R12", _R12_REMINDER),
    }
    if nature in short_circuits:
        rule_id, rule_text = short_circuits[nature]
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id=rule_id,
            rule_text=rule_text,
            source=SOURCE,
            threshold_met=False,
            evidence=evidence(fields, "story_nature", "subject_identifiable"),
            notes=(
                # Rule #9: keep these out of the headline overturn statistics — they were never
                # candidate events, which is a different thing from a real event that missed its
                # bar.
                "Labelled under rule #9 as never-a-candidate, not as a real event below its "
                "threshold.",
            ),
        )

    return None
