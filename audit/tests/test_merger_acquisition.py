"""Branch coverage for Merger & Acquisition and the global gate it runs behind.

Every DO-NOT-report branch is covered, not just the happy path: a threshold module that has only
been tested on rows it reports is untested on exactly the decisions that remove rows from the
analyst queue, which is the whole point of the funnel.
"""

from __future__ import annotations

import pytest

from logic import merger_acquisition as ma
from logic.base import (
    IMPACTFUL,
    NEEDS_CONTEXT_REVIEW,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    Decision,
    priority_for,
)


def base_fields(**over):
    """A row that passes the global gate and reaches the event-type rules."""
    f = {
        "story_nature": "CORPORATE_STRUCTURE_CHANGE",
        "subject_identifiable": "YES",
        "deal_stage": "ANNOUNCED",
        "strict_bar_sector": "NONE",
        "mapped_or_prominent_party_involved": "NO",
        "product_line_connection": "CONNECTED",
        "service_sector_applicability": "NOT_A_SERVICE_SECTOR",
        "steel_company_involved": "NO",
        "steel_applications_match_or_partner_involved": "NO",
        "initial_announcement_already_notified": "NO",
        "selling_party_is_mapped_partner": "NO",
    }
    f.update(over)
    return f


# --- The general product-connection test (MA.R7) ---------------------------------------------

def test_announced_deal_with_connected_product_line_is_impactful():
    d = ma.decide(base_fields())
    assert d.classification == IMPACTFUL
    assert d.rule_id == "MA.R7a"
    assert d.threshold_met is True
    assert not d.removes_from_queue


def test_unconnected_product_line_is_not_impactful():
    d = ma.decide(base_fields(product_line_connection="NOT_CONNECTED"))
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "MA.R7b"
    assert d.removes_from_queue


def test_unknown_product_connection_goes_to_review_not_to_not_impactful():
    """global-rules.md #13: two earlier passes collapsed 'can't tell' into 'no connection'."""
    d = ma.decide(base_fields(product_line_connection=""))
    assert d.classification == THRESHOLD_REVIEW
    assert d.missing_fields == ("product_line_connection",)
    assert not d.removes_from_queue
    assert any("Impactful" in n for n in d.notes), "fail-closed default must be recorded"


# --- The six strict-bar sectors (MA.R4) -------------------------------------------------------

@pytest.mark.parametrize(
    "sector",
    [
        "RETAIL",
        "CONSULTING_OR_STAFFING",
        "HOSPITALITY",
        "INVESTMENT_OR_FINANCE",
        "INSURANCE",
        "CRUDE_OIL",
        "MINING",
    ],
)
def test_strict_sector_without_mapped_party_is_not_impactful_even_when_product_connects(sector):
    """The strict bar *replaces* the product test; a connected product must not rescue the row."""
    d = ma.decide(
        base_fields(
            strict_bar_sector=sector,
            mapped_or_prominent_party_involved="NO",
            product_line_connection="CONNECTED",
        )
    )
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "MA.R4b"
    assert sector in d.notes[0]


def test_strict_sector_with_mapped_party_is_impactful():
    d = ma.decide(
        base_fields(strict_bar_sector="MINING", mapped_or_prominent_party_involved="YES")
    )
    assert d.classification == IMPACTFUL
    assert d.rule_id == "MA.R4a"


def test_strict_sector_with_unknown_mapping_goes_to_review():
    d = ma.decide(
        base_fields(strict_bar_sector="RETAIL", mapped_or_prominent_party_involved="")
    )
    assert d.classification == THRESHOLD_REVIEW
    assert d.missing_fields == ("mapped_or_prominent_party_involved",)


# --- Completion suppression (MA.R3) — the mirror of Business Sale ------------------------------

def test_completion_already_notified_is_suppressed():
    d = ma.decide(
        base_fields(deal_stage="COMPLETED", initial_announcement_already_notified="YES")
    )
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "MA.R3"
    assert d.removes_from_queue


def test_completion_never_announced_falls_through_to_the_normal_tests():
    """A completion we never announced is still news; suppression is conditional, not blanket."""
    d = ma.decide(
        base_fields(deal_stage="COMPLETED", initial_announcement_already_notified="NO")
    )
    assert d.classification == IMPACTFUL
    assert d.rule_id == "MA.R7a"


def test_completion_with_unknown_notification_history_goes_to_review():
    d = ma.decide(
        base_fields(deal_stage="COMPLETED", initial_announcement_already_notified="")
    )
    assert d.classification == THRESHOLD_REVIEW
    assert d.missing_fields == ("initial_announcement_already_notified",)


# --- Reroute to Business Sale (MA.R2) ---------------------------------------------------------

def test_mapped_partner_selling_reroutes_to_business_sale_rather_than_deciding():
    d = ma.decide(base_fields(selling_party_is_mapped_partner="YES"))
    assert d.reroute_to == "Business Sale"
    assert d.classification == NEEDS_CONTEXT_REVIEW
    assert not d.is_resolved, "a rerouted row must not be counted as decided"


def test_reroute_wins_over_the_product_test():
    """Ordering guard: the reroute must fire even when the product test would have answered."""
    d = ma.decide(
        base_fields(selling_party_is_mapped_partner="YES", product_line_connection="CONNECTED")
    )
    assert d.rule_id == "MA.R2"


# --- Steel (MA.R5) ----------------------------------------------------------------------------

def test_steel_without_matching_applications_or_partner_is_not_impactful():
    d = ma.decide(
        base_fields(
            steel_company_involved="YES",
            steel_applications_match_or_partner_involved="NO",
        )
    )
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "MA.R5a"


def test_steel_with_matching_applications_is_impactful():
    d = ma.decide(
        base_fields(
            steel_company_involved="YES",
            steel_applications_match_or_partner_involved="YES",
        )
    )
    assert d.classification == IMPACTFUL
    assert d.rule_id == "MA.R5c"


def test_steel_with_unknown_qualifier_goes_to_review():
    d = ma.decide(
        base_fields(
            steel_company_involved="YES",
            steel_applications_match_or_partner_involved="",
        )
    )
    assert d.classification == THRESHOLD_REVIEW


# --- Service sector (MA.R6) -------------------------------------------------------------------

def test_service_sector_not_applicable_is_not_impactful():
    d = ma.decide(base_fields(service_sector_applicability="NOT_APPLICABLE"))
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "MA.R6a"


def test_service_sector_applicable_is_impactful():
    d = ma.decide(
        base_fields(
            service_sector_applicability="APPLICABLE", product_line_connection="NOT_CONNECTED"
        )
    )
    assert d.classification == IMPACTFUL
    assert d.rule_id == "MA.R6b"


# --- Rumour / unknown stage (MA.R1) -----------------------------------------------------------

def test_rumour_with_no_named_parties_needs_context():
    d = ma.decide(base_fields(deal_stage="RUMOUR_NO_NAMED_PARTIES"))
    assert d.classification == NEEDS_CONTEXT_REVIEW
    assert d.missing_fields == ("acquirer_or_target_named",)


def test_unknown_stage_needs_context():
    d = ma.decide(base_fields(deal_stage=""))
    assert d.classification == NEEDS_CONTEXT_REVIEW
    assert d.missing_fields == ("deal_stage",)


# --- The rule #8 carve-out: the trap that would delete the top-volume event type ---------------

def test_a_sale_is_not_swallowed_by_the_expansion_carve_out():
    """global-rules #8 explicitly does not reach into M&A even when nothing is disrupted."""
    d = ma.decide(base_fields(story_nature="ORGANIC_EXPANSION_OR_INVESTMENT"))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "MA.R7a"
    assert not d.rule_id.startswith("GLOBAL")


def test_thin_row_with_no_identifiable_subject_needs_context():
    d = ma.decide(base_fields(subject_identifiable="NO"))
    assert d.classification == NEEDS_CONTEXT_REVIEW
    assert d.rule_id == "GLOBAL.R13"


# --- Contract guards -------------------------------------------------------------------------

def test_priority_is_p4_and_never_reaches_the_decision():
    assert priority_for(ma.EVENT_TYPE) == "P4"


def test_review_outcome_must_name_a_missing_field():
    with pytest.raises(ValueError, match="must name the evidence"):
        Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="X",
            rule_text="t",
            source="s",
        )


def test_resolved_outcome_must_not_claim_missing_fields():
    with pytest.raises(ValueError, match="must not also report"):
        Decision(
            classification=NOT_IMPACTFUL,
            rule_id="X",
            rule_text="t",
            source="s",
            missing_fields=("a",),
        )


def test_every_outcome_quotes_a_source_line():
    for fields in [
        base_fields(),
        base_fields(product_line_connection="NOT_CONNECTED"),
        base_fields(strict_bar_sector="RETAIL"),
        base_fields(deal_stage="RUMOUR_NO_NAMED_PARTIES"),
        base_fields(subject_identifiable="NO"),
    ]:
        d = ma.decide(fields)
        assert d.rule_text.strip(), d.rule_id
        assert d.source.strip(), d.rule_id


def test_unschema_value_is_rejected_rather_than_falling_through():
    with pytest.raises(ValueError, match="not in its schema"):
        ma.decide(base_fields(strict_bar_sector="AGRICULTURE"))
