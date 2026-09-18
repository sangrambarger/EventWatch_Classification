"""The cheatsheet must offer exactly the values the decision modules accept.

This file exists because the same defect shipped twice, and both times it cost most of a teacher
pass:

1. The cheatsheet listed fields and enums separately, keyed by Python constant name, leaving the
   field -> values mapping to inference. 95 of 220 rows (43%) came back undecidable.
2. After fixing that, fields guarded by an *inline* `frozenset({...})` still reported as YES/NO,
   because the regex's bare-identifier branch matched the literal word "frozenset" and swallowed
   the alternation. 18 more rows came back undecidable.

Neither was visible to any unit test or to the app smoke test — only to running real rows through
and counting the failures. These tests make the contract checkable without spending a pass.
"""

from __future__ import annotations

import pytest

from logic import registry
from logic.base import UNKNOWN
from logic.connection import DERIVED_FROM_RELEVANCE
from scripts.build_batches import build_cheatsheet, fields_read_by


@pytest.fixture(scope="module")
def sheet():
    return build_cheatsheet()


def test_every_registered_event_type_appears(sheet):
    assert set(sheet["event_types"]) == set(registry.MODULES)


def test_every_field_offers_a_value_list(sheet):
    """A field with no values is a field the labeller has to guess at."""
    for event_type, spec in sheet["event_types"].items():
        for field, values in spec["fields_to_extract"].items():
            assert values, f"{event_type}.{field} offers no values"
            assert isinstance(values, list), f"{event_type}.{field} is not a list"


def test_unknown_is_always_offered(sheet):
    """UNKNOWN is the correct answer whenever a story does not say, so it must always be legal."""
    for event_type, spec in sheet["event_types"].items():
        for field, values in spec["fields_to_extract"].items():
            if values == ["<number>"]:
                continue
            assert UNKNOWN in values, f"{event_type}.{field} cannot be answered UNKNOWN"


def test_no_field_is_offered_as_a_bare_yes_no_when_its_module_wants_an_enum(sheet):
    """The inline-frozenset bug, pinned.

    `smog_alert_tier`, `volcanic_activity`, `action_kind` and `tornado_status` are all guarded by
    an anonymous frozenset at the call site. Reporting them as YES/NO/UNKNOWN made every row using
    them undecidable.
    """
    expected = {
        ("Environmental Hazard", "smog_alert_tier"): {"RED_HIGHEST", "LOWER", "NOT_A_SMOG_ALERT"},
        ("Volcano", "volcanic_activity"): {
            "SIGNS_OF_ERUPTION", "ERUPTING", "ALERT_OR_EVACUATION", "NONE_REPORTED",
        },
        ("FDA/EMA/OSHA Action", "action_kind"): {"FORM_483", "OTHER_ACTION"},
        ("Tornado", "tornado_status"): {"WARNING_ONLY", "TOUCHDOWN"},
    }
    for (event_type, field), wanted in expected.items():
        offered = set(sheet["event_types"][event_type]["fields_to_extract"][field]) - {UNKNOWN}
        assert offered == wanted, f"{event_type}.{field} offers {offered}, module wants {wanted}"


def test_derived_fields_are_never_requested(sheet):
    """Asking for a supplier-mapping lookup produced 80-100% UNKNOWN and an unclearable queue."""
    for event_type, spec in sheet["event_types"].items():
        leaked = set(spec["fields_to_extract"]) & DERIVED_FROM_RELEVANCE
        assert not leaked, f"{event_type} still asks for derived field(s): {sorted(leaked)}"


def test_industry_relevance_is_asked_wherever_mapping_matters(sheet):
    """It is the field the derived ones resolve through, so it has to be collected."""
    for event_type, spec in sheet["event_types"].items():
        fields = spec["fields_to_extract"]
        module = registry.resolve(event_type)
        needs_mapping = any(
            f in DERIVED_FROM_RELEVANCE for f in fields_read_by(module)
        )
        if needs_mapping:
            assert "industry_relevance" in fields, (
                f"{event_type} derives mapping status but never collects industry_relevance"
            )


def test_every_cheatsheet_value_is_accepted_by_its_module(sheet):
    """End-to-end contract: anything the sheet offers must decide without raising.

    Builds a row per event type using the first non-UNKNOWN value of every field, which is the
    cheapest possible proof that the sheet and the modules speak the same language.
    """
    for event_type, spec in sheet["event_types"].items():
        fields = {}
        for field, values in spec["fields_to_extract"].items():
            if values == ["<number>"]:
                fields[field] = "6"
                continue
            concrete = [v for v in values if v != UNKNOWN]
            fields[field] = concrete[0] if concrete else UNKNOWN
        decision = registry.decide(event_type, fields)
        assert decision.classification, event_type


def test_every_cheatsheet_value_individually_decides(sheet):
    """Each offered value, one at a time, against an otherwise-UNKNOWN row."""
    for event_type, spec in sheet["event_types"].items():
        for field, values in spec["fields_to_extract"].items():
            if values == ["<number>"]:
                continue
            for value in values:
                row = {f: UNKNOWN for f in spec["fields_to_extract"]}
                row[field] = value
                registry.decide(event_type, row)  # must not raise
