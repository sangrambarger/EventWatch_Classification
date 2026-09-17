"""Airport Disruption.

Thin binding: the decision lives in `transport_family.py`, which groups the event types that share a rule
shape so the shared parts cannot drift apart between copies. See that module's docstring for what
this event type does differently from its siblings.
"""

from __future__ import annotations

from typing import Mapping

from .base import Decision
from .transport_family import (
    AIRPORT_EVENT_TYPE as EVENT_TYPE,
    AIRPORT_SOURCE as SOURCE,
    decide_airport_disruption,
)

try:  # pragma: no cover - only some families declare a shared field list
    from .transport_family import MUST_HAVE_FIELDS  # noqa: F401
except ImportError:  # pragma: no cover
    MUST_HAVE_FIELDS = ("mapped_or_prominent_party_involved", "industry_relevance")


def decide(fields: Mapping[str, object]) -> Decision:
    return decide_airport_disruption(fields)
