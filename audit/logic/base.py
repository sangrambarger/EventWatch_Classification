"""Shared decision contract for every per-event-type threshold module.

Every module in this package exposes exactly one entry point:

    decide(fields: Mapping[str, object]) -> Decision

`fields` holds the *already-extracted* evidence for one row — the enum/boolean values an
extraction pass produced from the story title and summary. A decision module never reads the
raw title or summary, never calls a model, and never matches keywords. That separation is the
whole point: the contextual reading happens upstream, and what happens here is a pure function
over named evidence that Product and Data Science can read as a table and diff as a code change.

Three consequences worth stating, because they are easy to erode:

1. **Every outcome cites the verbatim source line it fired on.** `Decision.rule_text` is copied
   from `audit/rules/event-types-*.md`, which is itself a mechanical extract of the approved
   Thresholds & Guide. A decision nobody can trace back to a source line is not auditable, and
   an unauditable verdict is the failure mode this project exists to remove.

2. **A review outcome must name the field it is missing.** `NEEDS_CONTEXT_REVIEW` and
   `THRESHOLD_REVIEW` exist only for *absent evidence in the row*, never for "the rule is
   unclear" — the rules are clear, and treating them as unclear is how ambiguity becomes a
   dumping ground. A review Decision with an empty `missing_fields` is rejected at construction.

3. **`UNKNOWN` is not `NO`.** `global-rules.md` #13 records two independent classification passes
   that collapsed "can't tell" into "no connection, therefore Not Impactful". Modules must branch
   on `UNKNOWN` separately and route it to review.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from pathlib import Path
from typing import Mapping

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

# --- Outcomes -------------------------------------------------------------------------------

IMPACTFUL = "Impactful"
NOT_IMPACTFUL = "Not Impactful"
THRESHOLD_REVIEW = "Threshold Review"
NEEDS_CONTEXT_REVIEW = "Needs Context Review"

#: Outcomes that mean "no decision was reached because the row lacks evidence". These are
#: excluded from every accuracy denominator on the dashboard (plan guardrail 13) and are the only
#: outcomes permitted to carry `missing_fields`.
REVIEW_OUTCOMES = frozenset({THRESHOLD_REVIEW, NEEDS_CONTEXT_REVIEW})

ALL_OUTCOMES = frozenset({IMPACTFUL, NOT_IMPACTFUL, THRESHOLD_REVIEW, NEEDS_CONTEXT_REVIEW})

#: Sentinel meaning "the extraction pass could not determine this field from the row".
UNKNOWN = "UNKNOWN"


class RuleConflict(Exception):
    """Raised when the source rules give no consistent answer for a reachable field combination.

    Deliberately an exception rather than a silent default: plan guardrail 15 requires rule
    conflicts and insufficient documentation to be marked explicitly rather than resolved by
    invention. A module that cannot decide must say so loudly enough to reach a human.
    """


@dataclass(frozen=True)
class Decision:
    """One threshold verdict for one row, with its full audit trail."""

    classification: str
    rule_id: str
    rule_text: str
    source: str
    evidence: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    threshold_met: bool | None = None
    #: Set when a rule reassigns the row to a different event type rather than deciding it
    #: (e.g. M&A's "if a mapped partner sells the business, notify it as a business sale").
    reroute_to: str | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.classification not in ALL_OUTCOMES:
            raise ValueError(
                f"{self.classification!r} is not one of {sorted(ALL_OUTCOMES)}"
            )
        if self.classification in REVIEW_OUTCOMES and not self.missing_fields:
            raise ValueError(
                f"{self.classification!r} must name the evidence it is missing "
                f"(rule {self.rule_id}); a review outcome with no missing field is a rule "
                "ambiguity in disguise, which this contract does not allow"
            )
        if self.classification not in REVIEW_OUTCOMES and self.missing_fields:
            raise ValueError(
                f"{self.classification!r} (rule {self.rule_id}) reached a decision, so it must "
                "not also report missing_fields"
            )
        if not self.rule_text.strip():
            raise ValueError(f"rule {self.rule_id} must quote the source line it fired on")

    @property
    def is_resolved(self) -> bool:
        return self.classification not in REVIEW_OUTCOMES

    @property
    def removes_from_queue(self) -> bool:
        """True when this verdict takes the row off the analyst queue.

        Only `Not Impactful` does. `Impactful` means a bulletin is owed, and a review outcome
        means a human is owed — neither is a workload saving, and counting them as one is how a
        reduction funnel starts lying.
        """
        return self.classification == NOT_IMPACTFUL


# --- Priority (urgency only, never the impact axis) ------------------------------------------

def _load_priority_matrix() -> dict[str, str]:
    """Parse the P0-P4 table out of `rules/priority-matrix.md`.

    Read from the file rather than hardcoded so a change to the approved matrix cannot silently
    diverge from what this code applies — the same reason the event-type names are read fresh
    elsewhere instead of being duplicated in a second list.
    """
    matrix: dict[str, str] = {}
    path = RULES_DIR / "priority-matrix.md"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---") or "| Priority" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 2 and cells[1].startswith("P") and cells[1][1:].isdigit():
            matrix[cells[0]] = cells[1]
    if not matrix:  # pragma: no cover - guards against a silently reformatted source table
        raise RuleConflict(f"no priority rows parsed from {path}")
    return matrix


PRIORITY_BY_EVENT_TYPE = _load_priority_matrix()


def priority_for(event_type: str) -> str:
    """Return P0-P4 for an event type.

    Per `global-rules.md` #3 this is *response urgency* for an already-impactful event. It is
    never an input to any threshold decision, which is why it lives outside `Decision` and is
    attached after the fact.
    """
    try:
        return PRIORITY_BY_EVENT_TYPE[event_type]
    except KeyError:
        raise RuleConflict(
            f"event type {event_type!r} has no row in priority-matrix.md; add it to the "
            "approved matrix rather than guessing a tier here"
        ) from None


# --- Field access ---------------------------------------------------------------------------

def get(fields: Mapping[str, object], name: str, *, allowed: frozenset[str] | None = None) -> str:
    """Read an enum field, defaulting to `UNKNOWN` when absent or blank.

    Validates against `allowed` when given, so a typo in an extraction label surfaces as an
    error here instead of quietly falling through to a wrong branch.
    """
    raw = fields.get(name)
    value = UNKNOWN if raw is None or str(raw).strip() == "" else str(raw).strip()
    if allowed is not None and value != UNKNOWN and value not in allowed:
        raise ValueError(
            f"field {name!r} has value {value!r}, which is not in its schema "
            f"{sorted(allowed)}"
        )
    return value


def evidence(fields: Mapping[str, object], *names: str) -> tuple[str, ...]:
    """Render `field=value` pairs for the audit trail."""
    return tuple(f"{n}={get(fields, n)}" for n in names)
