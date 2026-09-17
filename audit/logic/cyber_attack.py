"""Cyber Attack threshold logic.

Source: `audit/rules/event-types-manmade.md` § Cyber Attack (slide 12).
Priority: P1.

**First schema-backed module.** Unlike M&A and Business Sale, Cyber Attack has a supplied
extraction schema (`audit/schemas/extraction_fields/Cyber_Attack_Extraction_Only_Fields.json`,
39 `must_have` fields). Field names and enum values below are taken **verbatim** from it, so the
extraction pass and this decision cannot drift apart. Only a handful of the 39 fields feed the
threshold; the rest exist for bulletin drafting and are deliberately not read here.

The rule that shapes this module, and the reason `warroom_eligible` exists on `Decision`:

> "Incase of Cyber vulnerabilities, send news alerts but DO NOT create a WarRoom. Create a
> WarRoom only when a Cyber Attack actually happens."

A vulnerability advisory with no known attack is therefore **still reportable** — it is a news
alert, so it is Impactful — while being WarRoom-ineligible. Collapsing the impact call and the
WarRoom call into one boolean would either suppress a reportable alert or open WarRooms the
guidelines forbid, so the two are kept separate.

The second shaping fact is how **low** this bar is. "Notify all kinds of hacks, breaches,
ransomware, attacks, and service interruptions" plus "Notify glitches in software or hardware
that are vulnerable to cyber attacks" means the event-type test alone removes almost nothing.
What actually removes rows here is the industry-connection test and the global gate — in the
216-row feed sample the Cyber Attack group was dominated by crypto-theft stories, which fail on
industry connection (blockchain/crypto is not one of the 27 industries), not on the cyber rules.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    IMPACTFUL,
    NEEDS_CONTEXT_REVIEW,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    evidence,
    get,
)
from .global_gate import apply_global_gate

EVENT_TYPE = "Cyber Attack"
SOURCE = "rules/event-types-manmade.md § Cyber Attack (slide 12)"
SCHEMA = "schemas/extraction_fields/Cyber_Attack_Extraction_Only_Fields.json"

# --- Field schema (verbatim from the supplied extraction schema) -----------------------------

#: `incident_nature`, must_have, verbatim enum.
INCIDENT_NATURE = frozenset(
    {
        "CONFIRMED_ATTACK_OR_BREACH",
        "VULNERABILITY_ADVISORY_NO_KNOWN_ATTACK",
        "ACTIVE_EXPLOITATION_CAMPAIGN_NO_NAMED_VICTIM",
        "ALLEGED_OR_UNCONFIRMED_INCIDENT",
        "CYBER_DRILL_OR_SIMULATION",
    }
)

#: `named_victim_status`, must_have, verbatim enum.
NAMED_VICTIM_STATUS = frozenset(
    {
        "SPECIFIC_VICTIM_NAMED",
        "MULTIPLE_VICTIMS_NAMED",
        "NO_NAMED_VICTIM_VENDOR_OR_PRODUCT_ONLY",
    }
)

#: `confirmation_status`, must_have, verbatim enum.
CONFIRMATION_STATUS = frozenset(
    {
        "CONFIRMED_BY_COMPANY",
        "CONFIRMED_BY_AUTHORITY",
        "REPORTED_BY_THREAT_ACTOR_OR_THIRD_PARTY",
        "ALLEGED_OR_UNDER_INVESTIGATION",
        "DENIED_BY_COMPANY",
    }
)

YES_NO = frozenset({"YES", "NO"})

#: AUTHOR-DERIVED. The schema's `entity_sector_or_service_role` is a free-text string, which a
#: decision cannot branch on, so the source line's own list is enumerated here:
#: "Report data breaches at a service provider, manufacturer, utility services, data centers,
#: financial institutions, communication services, cargo/freight services, etc."
#: The trailing "etc." is honoured by `OTHER_SECTOR`, which falls through to the general
#: industry-connection test rather than being treated as a rejection.
ENTITY_ROLE = frozenset(
    {
        "SERVICE_PROVIDER",
        "MANUFACTURER",
        "UTILITY_SERVICES",
        "DATA_CENTER",
        "FINANCIAL_INSTITUTION",
        "COMMUNICATION_SERVICES",
        "CARGO_OR_FREIGHT_SERVICES",
        "OTHER_SECTOR",
    }
)

#: AUTHOR-DERIVED from "Notify if the affected company(s) serves our customer industries",
#: evaluated against the 27 industries in `rules/industries.md`.
INDUSTRY_CONNECTION = frozenset({"CONNECTED", "NOT_CONNECTED"})

MUST_HAVE_FIELDS = (
    "incident_nature",
    "named_victim_status",
    "confirmation_status",
    "partner_software_attacked",
    "entity_role",
    "industry_connection",
)

# --- Verbatim source lines --------------------------------------------------------------------

_PARTNER_SW = "Partner's software attacked? Notify with impact attached"
_INDUSTRY = (
    "Notify if the affected company(s) serves our customer industries. Possible unmapped "
    "sub-tier/T1 site yet to be mapped by the customers."
)
_SECTORS = (
    "Report data breaches at a service provider, manufacturer, utility services, data centers, "
    "financial institutions, communication services, cargo/freight services, etc."
)
_ALL_KINDS = "Notify all kinds of hacks, breaches, ransomware, attacks, and service interruptions"
_GLITCHES = "Notify glitches in software or hardware that are vulnerable to cyber attacks"
_NO_WARROOM = (
    "Incase of Cyber vulnerabilities, send news alerts but DO NOT create a WarRoom. Create a "
    "WarRoom only when a Cyber Attack actually happens."
)


def decide(fields: Mapping[str, object]) -> Decision:
    """Apply the Cyber Attack reporting threshold to one row's extracted evidence."""
    gate = apply_global_gate(fields, candidate_event_type=EVENT_TYPE)
    if gate is not None:
        return gate

    nature = get(fields, "incident_nature", allowed=INCIDENT_NATURE)
    victim = get(fields, "named_victim_status", allowed=NAMED_VICTIM_STATUS)
    confirmation = get(fields, "confirmation_status", allowed=CONFIRMATION_STATUS)
    partner_sw = get(fields, "partner_software_attacked", allowed=YES_NO)
    role = get(fields, "entity_role", allowed=ENTITY_ROLE)
    industry = get(fields, "industry_connection", allowed=INDUSTRY_CONNECTION)

    if nature == UNKNOWN:
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="CY.R0",
            rule_text=_ALL_KINDS,
            source=SOURCE,
            missing_fields=("incident_nature",),
            evidence=evidence(fields, "incident_nature"),
        )

    # R1 — a drill or simulation is not an incident. Not in the source's DO-NOT list because the
    # source does not contemplate it, but the schema enumerates it, so it needs an answer: a
    # planned exercise is not a "hack, breach, ransomware, attack or service interruption".
    if nature == "CYBER_DRILL_OR_SIMULATION":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="CY.R1",
            rule_text=_ALL_KINDS,
            source=SOURCE,
            threshold_met=False,
            warroom_eligible=False,
            evidence=evidence(fields, "incident_nature"),
            notes=(
                "A scheduled exercise is not an incident. The source enumerates no such case; "
                "this reading is author-derived and flagged in the spec.",
            ),
        )

    # R2 — a partner's software being attacked is reportable on its own, ahead of every other
    # test: the source attaches an impact without asking anything further.
    if partner_sw == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id="CY.R2",
            rule_text=_PARTNER_SW,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=nature == "CONFIRMED_ATTACK_OR_BREACH",
            evidence=evidence(fields, "partner_software_attacked", "incident_nature"),
        )

    # R3 — a company denial is still a reported incident, but it is not a confirmed one, and the
    # source gives no instruction for it. Routed to review rather than decided either way, per
    # plan guardrail 15 (mark the gap, do not invent).
    if confirmation == "DENIED_BY_COMPANY":
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id="CY.R3",
            rule_text=_ALL_KINDS,
            source=SOURCE,
            missing_fields=("independent_confirmation",),
            evidence=evidence(fields, "confirmation_status", "incident_nature"),
            notes=(
                "Company denies the incident and the source rules do not cover a denial; "
                "needs a human rather than a guessed reading.",
            ),
        )

    # R4 — vulnerabilities and exploitation campaigns with no named victim. Reportable as a news
    # alert, explicitly NOT WarRoom-eligible. This is the rule that forces the two-axis Decision.
    if nature in {
        "VULNERABILITY_ADVISORY_NO_KNOWN_ATTACK",
        "ACTIVE_EXPLOITATION_CAMPAIGN_NO_NAMED_VICTIM",
    }:
        if industry == "NOT_CONNECTED":
            return Decision(
                classification=NOT_IMPACTFUL,
                rule_id="CY.R4a",
                rule_text=_INDUSTRY,
                source=SOURCE,
                threshold_met=False,
                warroom_eligible=False,
                evidence=evidence(fields, "incident_nature", "industry_connection"),
            )
        if industry == UNKNOWN and role == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW,
                rule_id="CY.R4b",
                rule_text=_GLITCHES + "  ||  " + _INDUSTRY,
                source=SOURCE,
                missing_fields=("industry_connection",),
                evidence=evidence(fields, "incident_nature", "named_victim_status"),
            )
        return Decision(
            classification=IMPACTFUL,
            rule_id="CY.R4c",
            rule_text=_GLITCHES + "  ||  " + _NO_WARROOM,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=False,
            evidence=evidence(fields, "incident_nature", "industry_connection"),
            notes=(
                "News alert only — the source forbids a WarRoom for a vulnerability with no "
                "actual attack.",
            ),
        )

    # R5 — the named sectors. The source lists them for data breaches specifically, but its
    # "notify all kinds" line makes the list a sufficient condition for any incident type.
    if role in ENTITY_ROLE and role not in {"OTHER_SECTOR", UNKNOWN}:
        return Decision(
            classification=IMPACTFUL,
            rule_id="CY.R5",
            rule_text=_SECTORS,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=nature == "CONFIRMED_ATTACK_OR_BREACH",
            evidence=evidence(fields, "entity_role", "incident_nature", "named_victim_status"),
        )

    # R6 — the general industry-connection test. This is what actually removes rows.
    if industry == "CONNECTED":
        return Decision(
            classification=IMPACTFUL,
            rule_id="CY.R6a",
            rule_text=_INDUSTRY,
            source=SOURCE,
            threshold_met=True,
            warroom_eligible=nature == "CONFIRMED_ATTACK_OR_BREACH",
            evidence=evidence(fields, "industry_connection", "incident_nature"),
        )
    if industry == "NOT_CONNECTED":
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id="CY.R6b",
            rule_text=_INDUSTRY,
            source=SOURCE,
            threshold_met=False,
            warroom_eligible=False,
            evidence=evidence(fields, "industry_connection", "entity_role"),
            notes=(
                "The cyber rules themselves are near-universal; industry connection is the test "
                "that removes the row.",
            ),
        )

    return Decision(
        classification=THRESHOLD_REVIEW,
        rule_id="CY.R7",
        rule_text=_INDUSTRY,
        source=SOURCE,
        missing_fields=("industry_connection",),
        evidence=evidence(fields, "incident_nature", "entity_role", "named_victim_status"),
        notes=("Fail-closed operational default under global-rules #4 is Impactful.",),
    )
