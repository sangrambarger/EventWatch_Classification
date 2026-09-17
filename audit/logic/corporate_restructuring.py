"""Corporate Restructuring — `event-types-manmade.md` § Corporate Restructuring (slide 11). P3.

Textually identical reporting guidelines to Company Split, down to the steel / mining / crude
rider, so it shares that implementation. Its sub-types are broader (they include workforce
restructuring, rebranding and recapitalisation), but the source gives none of them differentiated
treatment, so none of them changes the decision.

Note the overlap with Layoffs: "Workforce/employee restructuring" appears here as a sub-type while
Layoffs has its own slide with a much stricter bar ("only notify if a supplier is making
layoffs"). A job-cuts story reaching this module gets the more permissive cascade. That is a real
ambiguity in the source rather than a bug here, and it is flagged in the spec for a ruling.
"""

from __future__ import annotations

from typing import Mapping

from .base import Decision
from .corporate_family import MUST_HAVE_FIELDS, _decide_split_family  # noqa: F401

EVENT_TYPE = "Corporate Restructuring"
SOURCE = "rules/event-types-manmade.md § Corporate Restructuring (slide 11)"


def decide(fields: Mapping[str, object]) -> Decision:
    return _decide_split_family(fields, event_type=EVENT_TYPE, prefix="CRS", source=SOURCE)
