"""Branch coverage for Business Sale, including the points where it must diverge from M&A."""

from __future__ import annotations

import pytest

from logic import business_sale as bs
from logic import merger_acquisition as ma
from logic.base import (
    IMPACTFUL,
    NEEDS_CONTEXT_REVIEW,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    priority_for,
)


def base_fields(**over):
    f = {
        "story_nature": "CORPORATE_STRUCTURE_CHANGE",
        "subject_identifiable": "YES",
        "sale_stage": "ANNOUNCED",
        "mapped_or_prominent_party_involved": "NO",
        "product_line_connection": "CONNECTED",
        "service_sector_applicability": "NOT_A_SERVICE_SECTOR",
    }
    f.update(over)
    return f


# --- Mapped party (BS.R2) ---------------------------------------------------------------------

def test_mapped_party_is_impactful_without_needing_the_product_test():
    d = bs.decide(
        base_fields(
            mapped_or_prominent_party_involved="YES", product_line_connection="NOT_CONNECTED"
        )
    )
    assert d.classification == IMPACTFUL
    assert d.rule_id == "BS.R2"


@pytest.mark.parametrize("stage", ["ANNOUNCED", "SIGNS_TALKS_OR_PLANS", "COMPLETED"])
def test_signs_talks_and_plans_are_all_reportable_stages(stage):
    """'Notify as soon as it is announced (signs/talks/plans)' — early stages are in scope."""
    d = bs.decide(base_fields(sale_stage=stage, mapped_or_prominent_party_involved="YES"))
    assert d.classification == IMPACTFUL


# --- Unmapped general test (BS.R4) ------------------------------------------------------------

def test_unmapped_with_connected_products_is_impactful():
    d = bs.decide(base_fields())
    assert d.classification == IMPACTFUL
    assert d.rule_id == "BS.R4a"


def test_unmapped_with_unconnected_products_is_not_impactful():
    d = bs.decide(base_fields(product_line_connection="NOT_CONNECTED"))
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "BS.R4b"
    assert d.removes_from_queue


def test_unknown_product_connection_goes_to_review():
    d = bs.decide(base_fields(product_line_connection=""))
    assert d.classification == THRESHOLD_REVIEW
    assert d.missing_fields == ("product_line_connection",)


# --- Service sector (BS.R3) -------------------------------------------------------------------

def test_service_applicable_is_impactful():
    d = bs.decide(
        base_fields(
            service_sector_applicability="APPLICABLE", product_line_connection="NOT_CONNECTED"
        )
    )
    assert d.classification == IMPACTFUL
    assert d.rule_id == "BS.R3a"


def test_service_not_applicable_is_not_impactful_and_flags_the_divergence():
    d = bs.decide(base_fields(service_sector_applicability="NOT_APPLICABLE"))
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "BS.R3b"
    assert "shorter than M&A" in d.notes[0]


# --- Divergences from M&A that must not be harmonised away ------------------------------------

def test_completion_is_reported_here_but_suppressed_for_manda():
    """Same lifecycle stage, opposite handling — the asymmetry is in the source slides."""
    sale = bs.decide(
        base_fields(sale_stage="COMPLETED", mapped_or_prominent_party_involved="YES")
    )
    acq = ma.decide(
        {
            "story_nature": "CORPORATE_STRUCTURE_CHANGE",
            "subject_identifiable": "YES",
            "deal_stage": "COMPLETED",
            "strict_bar_sector": "NONE",
            "mapped_or_prominent_party_involved": "YES",
            "product_line_connection": "CONNECTED",
            "service_sector_applicability": "NOT_A_SERVICE_SECTOR",
            "steel_company_involved": "NO",
            "steel_applications_match_or_partner_involved": "NO",
            "initial_announcement_already_notified": "YES",
            "selling_party_is_mapped_partner": "NO",
        }
    )
    assert sale.classification == IMPACTFUL
    assert acq.classification == NOT_IMPACTFUL


def test_business_sale_has_no_strict_sector_bar():
    """A retail sale is reportable here on product connection alone; under M&A it would not be."""
    fields = base_fields(product_line_connection="CONNECTED")
    assert bs.decide(fields).classification == IMPACTFUL

    acq = ma.decide(
        {
            "story_nature": "CORPORATE_STRUCTURE_CHANGE",
            "subject_identifiable": "YES",
            "deal_stage": "ANNOUNCED",
            "strict_bar_sector": "RETAIL",
            "mapped_or_prominent_party_involved": "NO",
            "product_line_connection": "CONNECTED",
            "service_sector_applicability": "NOT_A_SERVICE_SECTOR",
            "steel_company_involved": "NO",
            "steel_applications_match_or_partner_involved": "NO",
            "initial_announcement_already_notified": "NO",
            "selling_party_is_mapped_partner": "NO",
        }
    )
    assert acq.classification == NOT_IMPACTFUL


def test_a_row_rerouted_from_manda_is_decidable_here_with_the_same_field_names():
    """The reroute is only safe if both modules read the same evidence names."""
    shared = {
        "story_nature": "CORPORATE_STRUCTURE_CHANGE",
        "subject_identifiable": "YES",
        "deal_stage": "ANNOUNCED",
        "sale_stage": "ANNOUNCED",
        "strict_bar_sector": "RETAIL",
        "mapped_or_prominent_party_involved": "YES",
        "product_line_connection": "CONNECTED",
        "service_sector_applicability": "NOT_A_SERVICE_SECTOR",
        "steel_company_involved": "NO",
        "steel_applications_match_or_partner_involved": "NO",
        "initial_announcement_already_notified": "NO",
        "selling_party_is_mapped_partner": "YES",
    }
    rerouted = ma.decide(shared)
    assert rerouted.reroute_to == "Business Sale"
    landed = bs.decide(shared)
    assert landed.classification == IMPACTFUL


# --- Rumour / unknown stage (BS.R1) -----------------------------------------------------------

def test_rumour_with_no_named_parties_needs_context():
    d = bs.decide(base_fields(sale_stage="RUMOUR_NO_NAMED_PARTIES"))
    assert d.classification == NEEDS_CONTEXT_REVIEW
    assert d.missing_fields == ("seller_or_buyer_named",)


def test_completion_with_unknown_connection_goes_to_review_not_auto_reported():
    """'Send updates on completion news' still needs the business to be one we cover."""
    d = bs.decide(base_fields(sale_stage="COMPLETED", product_line_connection=""))
    assert d.classification == THRESHOLD_REVIEW
    assert d.rule_id == "BS.R5"


# --- Carve-out and contract -------------------------------------------------------------------

def test_a_sale_is_not_swallowed_by_the_expansion_carve_out():
    d = bs.decide(base_fields(story_nature="ORGANIC_EXPANSION_OR_INVESTMENT"))
    assert d.classification == IMPACTFUL
    assert not d.rule_id.startswith("GLOBAL")


def test_priority_is_p3():
    assert priority_for(bs.EVENT_TYPE) == "P3"
