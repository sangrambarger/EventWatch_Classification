"""Pin the deterministic extraction patterns against the real headlines that motivated them.

Every case here is a verbatim title from the 2026-09-07 shift that reached review with the named
field missing. A regex is easy to write and easy to break — widening one alternative to catch a
new phrasing routinely swallows a neighbouring value, and first-match-wins ordering means the
damage is silent. These tests are the record of which title each pattern was written for.

The negative cases matter more than the positive ones. A pattern that fires on everything is
worse than no pattern at all: it converts a review row, which a human resolves, into a confident
wrong field, which nobody catches.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract.rules import extract_enums  # noqa: E402


def field(title: str, name: str) -> str | None:
    return extract_enums(title).get(name)


# --- role: Leadership Transition gates on seniority --------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("11:53 EDT BlackRock TCP Capital announces resignation of CEO Philip Tseng", "CEO"),
    ("September 02, 2026: Thales UK Appoints Victor Chavez as New CEO", "CEO"),
    ("National Armaments Director appoints new Chief Financial Officer", "CFO"),
    ("TekCor4 appoints COO to lead AI aftersales solution launch", "COO"),
    ("Expelled from the Party: Chairman of Hanoi Construction Corporation", "OTHER_EXECUTIVE"),
])
def test_role(title, expected):
    assert field(title, "role") == expected


def test_role_prefers_the_most_senior_office_named():
    # "UiPath splits CFO and COO roles" names two; first-match-wins resolves it to one, and the
    # order in ENUM_PATTERNS decides which. Pinned so a later reorder is a visible test failure.
    assert field("UiPath splits CFO and COO roles, names IT executive to board", "role") == "CFO"


def test_role_silent_when_no_office_is_named():
    assert field("Volkswagen to convert car plant for Israeli defense group", "role") is None


# --- incident_nature: Cyber Attack treats these five very differently ---------------------------

@pytest.mark.parametrize("title,expected", [
    ("Trezor data breach impact now reaches 81,000 customers", "CONFIRMED_ATTACK_OR_BREACH"),
    ("Hackers drain $320M in Bitcoin from Liquid Network", "CONFIRMED_ATTACK_OR_BREACH"),
    ("Minnesota County Hit by Second Ransomware Attack", "CONFIRMED_ATTACK_OR_BREACH"),
    ("Novocure Reports Patient Data Exposure in Cybersecurity Incident",
     "CONFIRMED_ATTACK_OR_BREACH"),
])
def test_incident_nature_confirmed(title, expected):
    assert field(title, "incident_nature") == expected


def test_allegation_outranks_the_attack_word_in_the_same_headline():
    # "Supposed White-Hat Hackers Withdraw 4,000 BTC" contains both an allegation and a confirmed
    # withdrawal. The slide treats an unconfirmed incident differently, so the qualifier wins.
    title = "Liquid Network Pauses Operations After Supposed White-Hat Hackers Withdraw 4,000 BTC"
    assert field(title, "incident_nature") == "ALLEGED_OR_UNCONFIRMED_INCIDENT"


@pytest.mark.parametrize("title,expected", [
    ("Cisco issues security advisory for CVE-2026-1234 in IOS XE",
     "VULNERABILITY_ADVISORY_NO_KNOWN_ATTACK"),
    ("Threat actors are targeting unpatched Fortinet devices in a phishing campaign",
     "ACTIVE_EXPLOITATION_CAMPAIGN_NO_NAMED_VICTIM"),
    ("EU banks run a cyber drill to test resilience", "CYBER_DRILL_OR_SIMULATION"),
])
def test_incident_nature_other_branches(title, expected):
    assert field(title, "incident_nature") == expected


# --- layoff_nature: an intention is future-scheduled, not a completed cut -----------------------

@pytest.mark.parametrize("title,expected", [
    ("JLR to cut 4,000 jobs globally, targets £1.7 billion in savings", "FUTURE_SCHEDULED"),
    ("More than 300 workers at Sun casinos may lose their jobs", "FUTURE_SCHEDULED"),
    ("next round of job cuts despite profit - union syndicom", "FUTURE_SCHEDULED"),
    ("Company furloughs 200 staff at its Ohio plant", "FURLOUGH"),
    ("Supplier laid off 150 workers last month", "PERMANENT"),
])
def test_layoff_nature(title, expected):
    assert field(title, "layoff_nature") == expected


def test_layoff_scope_reads_global_from_the_headline():
    assert field("JLR to cut 4,000 jobs globally", "layoff_scope") == "GLOBAL"


# --- weather_severity: deliberately silent in the middle ----------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Category 3 hurricane sparks panic buying in US", "MAJOR_NAMED_STORM"),
    ("KC storm leaves thousands without power, tears roof off arena", "HIGHLY_DISRUPTIVE"),
])
def test_weather_severity(title, expected):
    assert field(title, "weather_severity") == expected


@pytest.mark.parametrize("title", [
    "IMD forecasts heavy rainfall over Northeast region",
    "Widespread rainfall in Jharkhand likely for two days from September 9",
    "Weather Update: Several districts in eastern Rajasthan are experiencing good rainfall",
])
def test_weather_severity_stays_silent_on_a_plain_forecast(title):
    # A forecast of heavy rain is neither clearly disruptive nor clearly routine. Guessing either
    # way moves the verdict, so the row goes to review — which is the correct answer, not a gap.
    assert field(title, "weather_severity") is None


# --- operational_disruptions_reported: the NO patterns must beat the YES ones -------------------

def test_no_disruption_beats_the_word_disrupted():
    title = "Airport says no disruption to flights after drone sighting"
    assert field(title, "operational_disruptions_reported") == "NO"


def test_reported_disruption():
    title = "Flooding forces the plant to halt production at its Chennai site"
    assert field(title, "operational_disruptions_reported") == "YES"


# --- sale_stage / strike_status: phrasings the original patterns missed -------------------------

@pytest.mark.parametrize("title,expected", [
    ("Kirkland Advises Providence Equity Partners on Sale of ATG to MARI", "ANNOUNCED"),
    ("Bain Capital and Omnam Group announce the sale of the Lake Como Edition Hotel", "ANNOUNCED"),
    # Talks are checked first, so "sale of" does not read as a completed deal.
    ("Canadian pensions said to be entertaining a sale of Australia's Flow Power",
     "SIGNS_TALKS_OR_PLANS"),
])
def test_sale_stage(title, expected):
    assert field(title, "sale_stage") == expected


@pytest.mark.parametrize("title,expected", [
    ("Seattle mayor to join striking workers at Embassy Suites", "UNDERWAY"),
    ("Sitharaman Meets Bank Union Delegation Ahead Of Nationwide Strike", "FUTURE_DATED"),
    ("STAS denounces Vaersa for 'strikebreaking' during the wildfire prevention strike",
     "UNDERWAY"),
])
def test_strike_status(title, expected):
    assert field(title, "strike_status") == expected


def test_a_bare_strike_mention_says_nothing_about_its_stage():
    # "Strike at Dino? Union members put the matter on the cutting edge" establishes that a
    # dispute exists and nothing about whether anyone has walked out. Silence is correct.
    assert field("Strike at Dino? Union members put the matter on the cutting edge",
                 "strike_status") is None


# --- The derived-field bug: a resolved field must never be named as missing --------------------

def test_regional_gate_never_names_a_field_industry_relevance_already_answered():
    """`sites_mapped_in_region` is derived from industry relevance, not extracted.

    Reading the raw field when building `missing_fields` put 36 rows of the 7 Sept shift into
    review citing a question the pipeline had already answered — which is both a false backlog
    entry and an unanswerable ask for the human who picks the row up. The row still goes to
    review here, correctly: regional importance and reported disruptions are genuinely unread.
    """
    from logic import registry

    fields = {
        "event_type": "Flood",
        "story_nature": "DISRUPTION_OR_RISK_SIGNAL",
        "subject_identifiable": "YES",
        # NOT_RELEVANT derives sites_mapped_in_region=NO, so it is answered, not missing.
        "industry_relevance": "NOT_RELEVANT",
        "flood_alert_tier": "ACTUAL_FLOODING",
    }
    decision = registry.decide("Flood", fields)
    assert decision.classification == "Threshold Review"
    assert decision.missing_fields == (
        "region_industrially_important", "operational_disruptions_reported",
    )


def test_a_reported_disruption_with_no_regional_presence_does_not_fall_through():
    """Extreme Weather needs regional presence *and* a disruption, so NO+NO is Not Impactful.

    The `.NONE` branch used to require `disruptions in {NO, UNKNOWN}`, so a require_disruption
    event type with a reported disruption in a region we have no presence in matched no branch
    at all and dropped out of the bottom of the gate.
    """
    from logic import registry

    decision = registry.decide("Extreme Weather", {
        "event_type": "Extreme Weather",
        "story_nature": "DISRUPTION_OR_RISK_SIGNAL",
        "subject_identifiable": "YES",
        "industry_relevance": "NOT_RELEVANT",
        "weather_severity": "HIGHLY_DISRUPTIVE",
        "region_industrially_important": "NO",
        "operational_disruptions_reported": "YES",
    })
    assert decision.classification == "Not Impactful"
