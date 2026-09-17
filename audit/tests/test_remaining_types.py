"""Branch coverage for the 34 event types completing the rulebook.

One test per rule that would change a verdict if read wrongly, plus the DO-NOT branches that
actually remove rows from the analyst queue. Grouped by the family module each type lives in.
"""

from __future__ import annotations

import pytest

from logic import (
    airport_disruption as ap,
    bankruptcy as bk,
    business_spinoff as bso,
    company_split as csp,
    corporate_restructuring as crs,
    counterfeit as cf,
    extreme_weather as ew,
    factory_disruption as fdis,
    financial_distress as fd,
    fine as fn,
    flood as fl,
    force_majeure as fm,
    labor_disruption as ld,
    mine_shutdown as mn,
    port_disruption as pt,
    price_fluctuation as pf,
    profit_warning as pw,
    protest_riot as pr,
    regulatory_change as rc,
    supply_shortage as ss,
    tornado as to,
    volcano as vo,
)
from logic.base import (
    HIGH,
    IMPACTFUL,
    NEEDS_CONTEXT_REVIEW,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
)

GATE = {"story_nature": "DISRUPTION_OR_RISK_SIGNAL", "subject_identifiable": "YES"}
CORP = {"story_nature": "CORPORATE_STRUCTURE_CHANGE", "subject_identifiable": "YES"}

CONNECTED = {
    "mapped_or_prominent_party_involved": "NO",
    "industry_relevance": "RELEVANT",
    "product_line_connection": "CONNECTED",
    "service_sector_applicability": "NOT_A_SERVICE_SECTOR",
}
UNCONNECTED = {
    "mapped_or_prominent_party_involved": "NO",
    "industry_relevance": "NOT_RELEVANT",
    "product_line_connection": "NOT_CONNECTED",
    "service_sector_applicability": "NOT_A_SERVICE_SECTOR",
}


# ============================================================ corporate family

def test_mining_rider_ignores_a_connected_product_line():
    """'Mining company (only if a partner is involved)' — no product-connection escape."""
    d = crs.decide({**CORP, **CONNECTED, "stage": "ANNOUNCED",
                    "commodity_rider": "MINING", "partner_involved": "NO"})
    assert d.classification == NOT_IMPACTFUL
    assert "partner involvement alone" in d.notes[0]


def test_steel_rider_accepts_either_limb():
    base = {**CORP, **UNCONNECTED, "stage": "ANNOUNCED", "commodity_rider": "STEEL"}
    assert csp.decide({**base, "partner_involved": "YES"}).classification == IMPACTFUL
    assert csp.decide({**base, "partner_involved": "NO"}).classification == NOT_IMPACTFUL


def test_spinoff_has_no_commodity_rider():
    d = bso.decide({**CORP, **CONNECTED, "stage": "ANNOUNCED"})
    assert d.classification == IMPACTFUL


# ============================================================ financial family

def test_bankruptcy_pins_high_severity_on_the_mapped_branch():
    d = bk.decide({**GATE, **CONNECTED, "mapped_or_prominent_party_involved": "YES",
                   "bankruptcy_stage": "SIGNS_OR_TALKS"})
    assert d.classification == IMPACTFUL
    assert d.severity == HIGH


def test_bankruptcy_reports_at_the_signs_and_talks_stage():
    d = bk.decide({**GATE, **CONNECTED, "bankruptcy_stage": "SIGNS_OR_TALKS"})
    assert d.classification == IMPACTFUL


def test_profit_warning_is_supplier_only_however_large_the_company():
    d = pw.decide({**GATE, **CONNECTED, "supplier_or_partner_involved": "NO"})
    assert d.classification == NOT_IMPACTFUL
    assert "no product-line fallback" in d.notes[0]


def test_financial_distress_records_the_unresolved_source_conflict():
    d = fd.decide({**GATE, **CONNECTED, "distress_trigger": "CREDIT_RATING_DOWNGRADE",
                   "supplier_or_partner_involved": "YES"})
    assert d.classification == IMPACTFUL
    assert any("Classify it as" in n for n in d.notes), "source conflict must stay visible"


def test_settlement_carries_a_higher_bar_than_a_fine():
    unmapped_connected = {**GATE, **CONNECTED}
    assert fn.decide({**unmapped_connected, "fine_kind": "FINE"}).classification == IMPACTFUL
    d = fn.decide({**unmapped_connected, "fine_kind": "SETTLEMENT",
                   "major_company_in_our_verticals": "NO",
                   "mapped_or_prominent_party_involved": "NO",
                   "industry_relevance": "NOT_RELEVANT"})
    assert d.classification == NOT_IMPACTFUL


def test_routine_price_move_is_out_before_any_connection_test():
    d = pf.decide({**GATE, **CONNECTED, "move_significance": "MINOR_OR_ROUTINE"})
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "PF.R1"


# ============================================================ regulatory family

def test_counterfeit_excludes_luxury_and_fashion_outright():
    for subject in ("CURRENCY_NOTES", "LUXURY_GOODS", "FASHION_ITEMS"):
        d = cf.decide({**GATE, **CONNECTED, "counterfeit_subject": subject})
        assert d.classification == NOT_IMPACTFUL, subject
        assert "only explicit product-category exclusion" in d.notes[0]


def test_counterfeit_reports_components():
    d = cf.decide({**GATE, **CONNECTED,
                   "counterfeit_subject": "RAW_MATERIALS_PARTS_COMPONENTS"})
    assert d.classification == IMPACTFUL


def test_proposal_stage_bill_needs_a_significance_finding():
    base = {**GATE, **CONNECTED, "legislative_stage": "PROPOSAL"}
    assert rc.decide({**base, "reputable_sources_indicate_significant_impact": "NO"}
                     ).classification == NOT_IMPACTFUL
    assert rc.decide({**base, "reputable_sources_indicate_significant_impact": "YES"}
                     ).classification == IMPACTFUL


def test_later_stage_bill_needs_no_significance_finding():
    d = rc.decide({**GATE, **CONNECTED, "legislative_stage": "SIGNED_INTO_LAW"})
    assert d.classification == IMPACTFUL


def test_legal_action_recycled_reminder_is_removed_by_the_global_gate():
    """global-rules #12 runs upstream, so the module itself never sees these."""
    from logic import legal_action as la
    d = la.decide({**CONNECTED, "story_nature": "RECYCLED_REMINDER_OF_KNOWN_DEVELOPMENT",
                   "subject_identifiable": "YES"})
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "GLOBAL.R12"


# ============================================================ operations family

def test_routine_maintenance_shutdown_is_a_clear_no_not_an_ambiguity():
    """global-rules #6: 'routine and pre-planned with no stated disruption' is itself a signal."""
    d = fdis.decide({**GATE, **CONNECTED, "disruption_nature": "ROUTINE_PLANNED_MAINTENANCE",
                     "materiality_signal": "NO"})
    assert d.classification == NOT_IMPACTFUL
    assert "not ambiguity" in " ".join(d.notes)


def test_unplanned_shutdown_skips_the_materiality_floor():
    d = fdis.decide({**GATE, **CONNECTED, "disruption_nature": "UNPLANNED_SHUTDOWN",
                     "materiality_signal": "NO"})
    assert d.classification == IMPACTFUL


def test_force_majeure_reports_preplanned_activity_unlike_factory_disruption():
    d = fm.decide({**GATE, **CONNECTED, "force_majeure_declared": "YES"})
    assert d.classification == IMPACTFUL


def test_supply_shortage_multi_tier_rescues_an_unconnected_commodity():
    d = ss.decide({**GATE, **UNCONNECTED, "multi_tier_connection": "YES"})
    assert d.classification == IMPACTFUL
    assert d.rule_id == "SS.MULTITIER"


def test_supply_shortage_asks_the_multi_tier_question_before_dropping():
    d = ss.decide({**GATE, **UNCONNECTED, "multi_tier_connection": ""})
    assert d.classification == THRESHOLD_REVIEW
    assert d.missing_fields == ("multi_tier_connection",)


def test_coal_mine_needs_power_industry_or_vertical_disruption():
    base = {**GATE, **UNCONNECTED, "commodity_is_coal": "YES"}
    assert mn.decide({**base, "power_industry_disruption_expected": "NO"}
                     ).classification == NOT_IMPACTFUL
    assert mn.decide({**base, "power_industry_disruption_expected": "YES"}
                     ).classification == IMPACTFUL


# ============================================================ transport family

def ap_fields(**over):
    f = {**GATE, "airport_profile": "NON_MAPPED_WITH_CARGO", "cargo_impact": "CARGO_DISRUPTED",
         "disruption_scale": "HIGH_CANCELLATIONS", "strike_ballot_only_no_date": "NO",
         **UNCONNECTED}
    f.update(over)
    return f


def test_domestic_airport_with_no_cargo_is_out_first():
    d = ap.decide(ap_fields(airport_profile="DOMESTIC_NO_CARGO"))
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "AP.R1"


def test_passenger_only_disruption_needs_major_cancellations():
    assert ap.decide(ap_fields(cargo_impact="PASSENGER_ONLY", disruption_scale="PARTIAL")
                     ).classification == NOT_IMPACTFUL
    assert ap.decide(ap_fields(cargo_impact="PASSENGER_ONLY",
                               disruption_scale="HIGH_CANCELLATIONS")
                     ).classification == IMPACTFUL


def test_hangar_fire_with_no_flight_disruption_is_out():
    d = ap.decide(ap_fields(cargo_impact="NO_FLIGHT_DISRUPTION"))
    assert d.classification == NOT_IMPACTFUL


def test_a_dateless_strike_ballot_splits_between_airport_and_port():
    """Same fact pattern, opposite answers — both verbatim from their own slides."""
    air = ap.decide(ap_fields(strike_ballot_only_no_date="YES"))
    port = pt.decide({**GATE, "port_profile": "CONTAINER_OR_CARGO_PORT",
                      "strike_ballot_only_no_date": "YES", "cargo_activity_disrupted": "YES",
                      "strike_date_confirmed": "NO"})
    assert air.classification == NOT_IMPACTFUL
    assert port.classification == IMPACTFUL
    assert port.warroom_eligible is False, "bulletin only, no WarRoom"


def test_local_port_with_no_logistics_is_out():
    d = pt.decide({**GATE, "port_profile": "LOCAL_PORT_NO_LOGISTICS",
                   "cargo_activity_disrupted": "NO", "strike_date_confirmed": "NO"})
    assert d.classification == NOT_IMPACTFUL


def test_called_off_strike_inverts_to_not_impactful():
    d = ld.decide({**GATE, **CONNECTED, "strike_status": "CALLED_OFF", "strike_target": "OTHER"})
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "LD.R1"


def test_commuter_only_strike_is_excluded():
    d = ld.decide({**GATE, **CONNECTED, "strike_status": "UNDERWAY",
                   "strike_target": "COMMUTER_TRANSPORT_ONLY"})
    assert d.classification == NOT_IMPACTFUL


@pytest.mark.parametrize("target,dest", [("PORT", "Port Disruption"),
                                         ("AIRPORT", "Airport Disruption")])
def test_port_and_airport_strikes_reroute_rather_than_being_decided(target, dest):
    d = ld.decide({**GATE, **CONNECTED, "strike_status": "UNDERWAY", "strike_target": target})
    assert d.reroute_to == dest
    assert not d.is_resolved


def test_strike_intention_with_no_date_is_still_reportable():
    """The pre-alert rule: report at the first credible signal."""
    d = ld.decide({**GATE, **CONNECTED, "strike_status": "INTENTION_OR_BALLOT_PENDING",
                   "strike_target": "OTHER"})
    assert d.classification == IMPACTFUL


# ============================================================ natural family

REGION_NONE = {"sites_mapped_in_region": "NO", "region_industrially_important": "NO",
               "operational_disruptions_reported": "NO", **UNCONNECTED}
REGION_SITES = {"sites_mapped_in_region": "YES", "region_industrially_important": "NO",
                "operational_disruptions_reported": "NO", **CONNECTED}


def test_volcano_reports_even_with_no_sites_in_the_region():
    d = vo.decide({**GATE, **REGION_NONE, "volcanic_activity": "SIGNS_OF_ERUPTION"})
    assert d.classification == IMPACTFUL
    assert "No regional gate" in d.notes[0]


def test_extreme_weather_excludes_routine_weather_outright():
    d = ew.decide({**GATE, **REGION_SITES, "weather_severity": "MINOR_OR_ROUTINE"})
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "EW.R1"


def test_extreme_weather_needs_a_reported_disruption_as_well_as_sites():
    d = ew.decide({**GATE, **REGION_SITES, "weather_severity": "HIGHLY_DISRUPTIVE",
                   "operational_disruptions_reported": "NO"})
    assert d.classification == NOT_IMPACTFUL


def test_a_major_named_storm_is_notified_proactively():
    d = ew.decide({**GATE, **REGION_SITES, "weather_severity": "MAJOR_NAMED_STORM",
                   "operational_disruptions_reported": "NO"})
    assert d.classification == IMPACTFUL


@pytest.mark.parametrize("tier", ["WATCH", "ADVISORY"])
def test_flood_watch_and_advisory_are_not_reportable(tier):
    d = fl.decide({**GATE, **REGION_SITES, "flood_alert_tier": tier})
    assert d.classification == NOT_IMPACTFUL


def test_flood_warning_is_reportable():
    d = fl.decide({**GATE, **REGION_SITES, "flood_alert_tier": "WARNING"})
    assert d.classification == IMPACTFUL


def test_tornado_warning_alone_is_a_monitor_state():
    d = to.decide({**GATE, **REGION_SITES, "tornado_status": "WARNING_ONLY"})
    assert d.classification == NOT_IMPACTFUL
    assert "Monitor state" in d.notes[0]


def test_martial_law_reroutes_a_protest_to_geopolitical():
    d = pr.decide({**GATE, **REGION_SITES, "martial_law_introduced": "YES"})
    assert d.reroute_to == "Geopolitical"
    assert d.classification == NEEDS_CONTEXT_REVIEW


def test_regional_types_drop_only_when_every_limb_is_no():
    d = fl.decide({**GATE, **REGION_NONE, "flood_alert_tier": "ACTUAL_FLOODING"})
    assert d.classification == NOT_IMPACTFUL
    assert d.rule_id == "FL.NONE"


# ============================================================ priority coverage

def test_every_registered_event_type_resolves_to_a_priority_tier():
    """Caught a real gap: the Prioritization Matrix and the rulebook name 8 types differently or
    omit them, so priority_for() raised for 8 of 47 modules before aliases and documented
    inheritance were added."""
    from logic import registry
    from logic.base import priority_for

    unresolved = []
    for name in registry.MODULES:
        try:
            tier = priority_for(name)
        except Exception as exc:  # noqa: BLE001 - the point is to report, not to raise
            unresolved.append((name, str(exc)[:60]))
            continue
        assert tier in {"P0", "P1", "P2", "P3", "P4"}, (name, tier)
    assert unresolved == [], unresolved


def test_inherited_priorities_match_the_type_their_slide_files_them_under():
    from logic.base import priority_for

    assert priority_for("Layoffs") == priority_for("Labor Disruption")
    assert priority_for("Airworthiness") == priority_for("Compliance")
    assert priority_for("Earthquake (Rest of the World)") == "P0"
    assert priority_for("Counterfeit (CFSI)") == "P3"


def test_an_unknown_event_type_still_raises_rather_than_defaulting():
    import pytest as _pytest
    from logic.base import RuleConflict, priority_for

    with _pytest.raises(RuleConflict):
        priority_for("Interpretive Dance Disruption")
