"""Bankruptcy.

Thin binding: the decision lives in `financial_family.py`, which groups the event types that share a rule
shape so the shared parts cannot drift apart between copies. See that module's docstring for what
this event type does differently from its siblings.
"""

from __future__ import annotations

from typing import Mapping

from .base import Decision
from .financial_family import (
    BANKRUPTCY_EVENT_TYPE as EVENT_TYPE,
    BANKRUPTCY_SOURCE as SOURCE,
    decide_bankruptcy,
)

try:  # pragma: no cover - only some families declare a shared field list
    from .financial_family import MUST_HAVE_FIELDS  # noqa: F401
except ImportError:  # pragma: no cover
    MUST_HAVE_FIELDS = ("mapped_or_prominent_party_involved", "industry_relevance")


def decide(fields: Mapping[str, object]) -> Decision:
    return decide_bankruptcy(fields)
