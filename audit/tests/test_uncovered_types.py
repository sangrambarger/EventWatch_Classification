"""Branch coverage for Cyber Attack and the event types with no supplied extraction schema.

Each test group pins the one rule that would be easiest to get wrong for that event type, then
covers the remaining branches.
"""

from __future__ import annotations

import pytest

from logic import (
    airworthiness as aw,
    chemical_spill as cs,
    cyber_attack as cy,
    earthquake as eq,
    factory_fire as ff,
    layoffs as lo,
    leadership_transition as lt,
    mail_postal_delivery as mp,
    others as ot,
    power_outage as po,
    registry,
)
from logic.base import (
    IMPACTFUL,
    LOW,
    NEEDS_CONTEXT_REVIEW,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    RuleConflict,
)

GATE_OK = {"story_nature": "DISRUPTION_OR_RISK_SIGNAL", "subject_identifiable": "YES"}


# =================================================================== Cyber Attack

def cy_fields(**over):
    f = {
        **GATE_OK,
        "incident_nature": "CONFIRMED_ATTACK_OR_BREACH",
        "named_victim_status": "SPECIFIC_VICTIM_NAMED",
        "confirmation_status": "CONFIRMED_BY_COMPANY",
        "partner_software_attacked": "NO",
        "entity_role": "OTHER_SECTOR",
        "industry_connection": "CONNECTED",
    }
    f.update(over)
    return f


def test_vulnerability_advisory_is_reportable_but_never_warroom_eligible():
    """The rule that forces impact and WarRoom onto separate axes."""
    d = cy.decide(cy_fields(incident_nature="VULNERABILITY_ADVISORY_NO_KNOWN_ATTACK"))
    assert d.classification == IMPACTFUL
    assert d.warroom_eligible is False


def test_confirmed_attack_is_warroom_eligible():
    d = cy.decide(cy_fields())
    assert d.classification == IMPACTFUL
    assert d.warroom_eligible is True


def test_unconnected_industry_removes_the_row_even_for_a_real_hack():
    """Crypto-theft stories: a genuine breach, but not one of the 27 industries."""
    d = cy.decide(cy_fields(industry_connection="NOT_CONNECTED"))
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "CY.R6b"


def test_partner_software_attacked_short_circuits_everything():
    d = cy.decide(cy_fields(partner_software_attacked="YES", industry_connection="NOT_CONNECTED"))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "CY.R2"


def test_named_sector_is_sufficient():
    d = cy.decide(cy_fields(entity_role="DATA_CENTER", industry_connection="UNKNOWN"))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "CY.R5"


def test_company_denial_goes_to_review_because_the_source_is_silent():
    d = cy.decide(cy_fields(confirmation_status="DENIED_BY_COMPANY"))
    assert d.classification == THRESHOLD_REVIEW
    assert d.missing_fields == ("independent_confirmation",)


def test_drill_is_not_an_incident():
    d = cy.decide(cy_fields(incident_nature="CYBER_DRILL_OR_SIMULATION"))
    assert d.classification == NOT_IMPACTFUL


def test_cyber_enum_values_match_the_supplied_schema():
    """Guards against this module drifting from the schema the extractor is told to fill."""
    import json
    from pathlib import Path

    schema = json.loads(
        (Path(__file__).resolve().parent.parent / cy.SCHEMA).read_text(encoding="utf-8")
    )
    for field, allowed in [
        ("incident_nature", cy.INCIDENT_NATURE),
        ("named_victim_status", cy.NAMED_VICTIM_STATUS),
        ("confirmation_status", cy.CONFIRMATION_STATUS),
    ]:
        declared = set(schema["must_have"][field].split("/")) - {"UNKNOWN"}
        assert declared == set(allowed), f"{field} drifted from {cy.SCHEMA}"


# =================================================================== Factory Fire

def ff_fields(**over):
    f = {
        **GATE_OK,
        "partner_site_involved": "NO",
        "product_line_connection": "NOT_CONNECTED",
        "indirect_supplier": "NO",
        "service_sector_applicability": "NOT_A_SERVICE_SECTOR",
        "utility_or_service_region_has_mapped_sites": "NO",
        "affected_region_has_major_infrastructure": "NO",
        "neighbouring_evacuations": "NO",
        "fire_status": "ACTIVE",
        "fire_scale": "SIGNIFICANT",
        "site_relation": "AT_THE_FACILITY",
    }
    f.update(over)
    return f


@pytest.mark.parametrize("status", ["EXTINGUISHED", "RECOVERED"])
@pytest.mark.parametrize("scale", ["MINOR", "SIGNIFICANT"])
def test_a_small_or_extinguished_fire_is_still_reported(status, scale):
    """'We report a factory fire, even if the articles say it is a small fire or has been
    extinguished.' Neither field may ever reject."""
    d = ff.decide(
        ff_fields(fire_status=status, fire_scale=scale, product_line_connection="CONNECTED")
    )
    assert d.classification == IMPACTFUL


def test_indirect_supplier_rescues_an_unconnected_product_line():
    d = ff.decide(ff_fields(indirect_supplier="YES"))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "FF.R3"


def test_all_six_cascade_steps_must_be_answered_before_dropping():
    d = ff.decide(ff_fields(affected_region_has_major_infrastructure=""))
    assert d.classification == THRESHOLD_REVIEW
    assert "affected_region_has_major_infrastructure" in d.missing_fields


def test_fire_drops_only_when_every_rescue_is_a_no():
    d = ff.decide(ff_fields())
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "FF.R9"


def test_neighbouring_evacuation_reports_regardless_of_connection():
    d = ff.decide(ff_fields(neighbouring_evacuations="YES"))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "FF.R7"


# =================================================================== Chemical Spill

def cs_fields(**over):
    f = {
        **GATE_OK,
        "news_is_public": "YES",
        "spill_location": "OTHER_LOCATION",
        "external_disruption": "NONE_REPORTED",
        "regional_industrial_importance": "NOT_IMPORTANT",
    }
    f.update(over)
    return f


@pytest.mark.parametrize(
    "loc", ["INDUSTRIAL_UNIT", "WAREHOUSE", "PORT", "AIRPORT", "MINE", "TRAIN_TRACK", "HIGHWAY"]
)
def test_spill_at_any_named_location_is_reported_without_a_mapping_gate(loc):
    d = cs.decide(cs_fields(spill_location=loc))
    assert d.classification == IMPACTFUL


def test_spill_with_a_consequence_is_reported_anywhere():
    d = cs.decide(cs_fields(external_disruption="EVACUATION"))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "CS.R2"


def test_the_single_narrow_exit_exists_and_is_narrow():
    d = cs.decide(cs_fields())
    assert d.classification == NOT_IMPACTFUL
    assert "should be rare" in d.notes[0]


# =================================================================== Leadership Transition

def lt_fields(**over):
    f = {
        **GATE_OK,
        "role": "CEO",
        "partner_involved": "YES",
        "sites_mapped": "YES",
        "supply_chain_department_consequence": "NO",
        "transition_nature": "JOINS",
        "announced": "YES",
    }
    f.update(over)
    return f


def test_ceo_change_at_an_unmapped_company_is_not_impactful():
    d = lt.decide(lt_fields(sites_mapped="NO"))
    assert d.classification == NOT_IMPACTFUL
    assert d.severity == LOW


def test_non_ceo_role_is_rejected_even_at_a_mapped_partner():
    """The role list is closed; seniority alone does not qualify."""
    d = lt.decide(lt_fields(role="OTHER_EXECUTIVE"))
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "LT.R3b"


def test_non_ceo_role_qualifies_only_on_a_supply_chain_consequence():
    d = lt.decide(lt_fields(role="OTHER_EXECUTIVE", supply_chain_department_consequence="YES"))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "LT.R3a"


def test_mapped_partner_ceo_change_is_impactful_and_pinned_low():
    d = lt.decide(lt_fields())
    assert d.classification == IMPACTFUL
    assert d.severity == LOW


# =================================================================== Earthquake

def eq_fields(**over):
    f = {
        **GATE_OK,
        "region_variant": "REST_OF_WORLD",
        "magnitude": "6.0",
        "depth_miles": "15",
        "epicenter": "ON_LAND",
        "sites_mapped_in_region": "YES",
        "important_region": "NO",
        "tsunami_alert": "NO",
        "disruptions_observed": "NO",
        "important_infrastructure_in_region": "NO",
    }
    f.update(over)
    return f


def test_magnitude_floor_differs_by_region():
    """M5.2: above the regional floor of 5.0, below the RoW floor of 5.7."""
    regional = eq.decide(eq_fields(region_variant="JP_TW_KR_PH_ID_CN", magnitude="5.2"))
    row = eq.decide(eq_fields(region_variant="REST_OF_WORLD", magnitude="5.2"))
    assert regional.classification == IMPACTFUL
    assert row.classification == NOT_IMPACTFUL
    assert row.rule_id == "EQ.R3b"


def test_row_monitor_band_notifies_only_on_observed_disruptions():
    d = eq.decide(eq_fields(magnitude="5.3", disruptions_observed="YES"))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "EQ.R3a"


def test_missing_magnitude_is_not_a_small_magnitude():
    d = eq.decide(eq_fields(magnitude=""))
    assert d.classification == THRESHOLD_REVIEW
    assert d.missing_fields == ("magnitude",)


def test_unmapped_but_key_infrastructure_is_a_low_fyi_not_a_rejection():
    d = eq.decide(
        eq_fields(
            sites_mapped_in_region="NO",
            important_region="NO",
            important_infrastructure_in_region="YES",
        )
    )
    assert d.classification == IMPACTFUL
    assert d.severity == LOW


def test_radius_comes_from_the_table_and_japan_taiwan_is_tighter():
    general = eq.radius_km(6.3, 15, japan_or_taiwan=False)
    jp = eq.radius_km(6.3, 15, japan_or_taiwan=True)
    assert general == 225  # depth band 11-20, magnitude band 6.1-6.5
    assert jp == 98
    assert jp < general


def test_radius_rejects_a_nonphysical_reading():
    with pytest.raises(RuleConflict):
        eq.radius_km(-1, 10, japan_or_taiwan=False)


# =================================================================== Power Outage

def po_fields(**over):
    f = {
        **GATE_OK,
        "outage_kind": "POWER",
        "sites_mapped_in_region": "YES",
        "semiconductor_fab_region": "NO",
        "expected_recovery_time_provided": "YES",
        "duration_hours": "10",
        "outage_location": "SITE",
        "important_manufacturing_region": "NO",
        "operations_already_resumed": "NO",
        "mapped_site_confirms_impact": "NO",
    }
    f.update(over)
    return f


def test_absent_recovery_time_is_a_reason_to_notify_not_to_review():
    """The one rule where missing data resolves toward Impactful by explicit instruction."""
    d = po.decide(po_fields(expected_recovery_time_provided="NO", duration_hours=""))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "PO.R3"


def test_fab_region_reports_a_short_outage():
    d = po.decide(po_fields(semiconductor_fab_region="YES", duration_hours="1"))
    assert d.classification == IMPACTFUL
    assert d.rule_id == "PO.R2"


def test_rest_of_world_short_outage_is_removed():
    d = po.decide(po_fields(duration_hours="4"))
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "PO.R6"


def test_unmapped_region_is_the_hard_gate():
    d = po.decide(po_fields(sites_mapped_in_region="NO", important_manufacturing_region="NO"))
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "PO.R1b"


def test_software_variant_uses_a_three_hour_bar():
    over = po.decide(po_fields(outage_kind="SOFTWARE_OR_INTERNET", duration_hours="4"))
    under = po.decide(po_fields(outage_kind="SOFTWARE_OR_INTERNET", duration_hours="2"))
    assert over.classification == IMPACTFUL
    assert under.classification == NOT_IMPACTFUL


def test_software_variant_rejects_residential_issues():
    d = po.decide(
        po_fields(outage_kind="SOFTWARE_OR_INTERNET", outage_location="RESIDENTIAL_OR_LOCAL_USER")
    )
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "PO.S1"


# =================================================================== Layoffs / Airworthiness / Mail / Others

def test_layoffs_reject_a_non_supplier_however_large():
    d = lo.decide(
        {**GATE_OK, "supplier_making_layoffs": "NO", "layoff_nature": "PERMANENT",
         "layoff_scope": "GLOBAL"}
    )
    assert d.classification == NOT_IMPACTFUL


def test_future_scheduled_layoffs_at_a_supplier_are_reported():
    d = lo.decide(
        {**GATE_OK, "supplier_making_layoffs": "YES", "layoff_nature": "FUTURE_SCHEDULED",
         "layoff_scope": "SPECIFIC_DIVISION"}
    )
    assert d.classification == IMPACTFUL


def test_airworthiness_has_no_not_impactful_branch():
    d = aw.decide(
        {**GATE_OK, "airworthiness_directive_issued": "YES", "issuing_authority": "FAA",
         "recipient_company": "Acme"}
    )
    assert d.classification == IMPACTFUL
    assert d.warroom_eligible is False, "Customer Impact is not needed"


def test_a_non_ad_row_reroutes_rather_than_being_rejected():
    d = aw.decide({**GATE_OK, "airworthiness_directive_issued": "NO"})
    assert d.reroute_to == "Compliance"
    assert not d.is_resolved


def test_mail_postal_country_gate():
    d = mp.decide(
        {**GATE_OK, "sites_in_country": "NO", "disruption_kind": "SERVICE_SHUTDOWN",
         "major_postal_operator": "YES"}
    )
    assert d.classification == NOT_IMPACTFUL


def test_minor_postal_operator_sale_does_not_clear_the_major_qualifier():
    d = mp.decide(
        {**GATE_OK, "sites_in_country": "YES",
         "disruption_kind": "POSTAL_SERVICE_BANKRUPTCY_OR_SALE", "major_postal_operator": "NO"}
    )
    assert d.classification == NOT_IMPACTFUL
    assert "Business Sale" in d.notes[0]


def test_others_never_auto_resolves():
    d = ot.decide(dict(GATE_OK))
    assert d.classification == NEEDS_CONTEXT_REVIEW
    assert not d.is_resolved


def test_others_still_drops_a_row_the_global_gate_rejects():
    d = ot.decide(
        {"story_nature": "MARKET_COMMENTARY_NO_PHYSICAL_EVENT", "subject_identifiable": "YES"}
    )
    assert d.classification == NOT_IMPACTFUL


# =================================================================== Registry

def test_registry_resolves_a_redirect_to_its_canonical_module():
    assert registry.resolve("Software/Internet Outage") is po
    assert registry.resolve("Software/Internet Outage (redirect -> Power Outage)") is po


def test_registry_fails_closed_on_an_unknown_type():
    with pytest.raises(RuleConflict, match="no decision module"):
        registry.resolve("Interpretive Dance Disruption")


def test_registry_refuses_a_non_event_type():
    with pytest.raises(RuleConflict, match="not an event type"):
        registry.resolve("Restricted Access (cross-cutting sourcing rule, not an event type)")


def test_every_registered_module_exposes_the_contract():
    for name in registry.MODULES:
        module = registry.resolve(name)
        assert callable(module.decide), name
        assert getattr(module, "MUST_HAVE_FIELDS", None), name
        assert getattr(module, "SOURCE", "").strip(), name


def test_coverage_ledger_is_honest_about_what_is_left():
    cov = registry.coverage()
    assert "Cyber Attack" in " ".join(cov["with_module"])
    # The point of the ledger: the untouched types must still be listed, not quietly dropped.
    assert cov["without_module"], "ledger must name the event types still to build"
    assert "Merger & Acquisition" in cov["module_but_no_supplied_schema"]
