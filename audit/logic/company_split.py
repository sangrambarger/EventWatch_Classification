"""Company Split — `event-types-manmade.md` § Company Split (slide 9). P3.

Standard connection cascade plus the steel / mining / crude-oil rider shared with Corporate
Restructuring. See `corporate_family.py` for why that rider is worded differently from M&A's
six-sector bar and why the difference is preserved rather than harmonised.
"""

from __future__ import annotations

from typing import Mapping

from .base import Decision
from .corporate_family import MUST_HAVE_FIELDS, _decide_split_family  # noqa: F401

EVENT_TYPE = "Company Split"
SOURCE = "rules/event-types-manmade.md § Company Split (slide 9)"


def decide(fields: Mapping[str, object]) -> Decision:
    return _decide_split_family(fields, event_type=EVENT_TYPE, prefix="CSP", source=SOURCE)
