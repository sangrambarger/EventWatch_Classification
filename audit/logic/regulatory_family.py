"""Compliance, FDA/EMA/OSHA Action, Regulatory Change, Counterfeit, Recall, Legal Action,
Bribery/Corruption and Labor Violation.

Sources: `event-types-manmade.md` §§ Compliance (10), Counterfeit/CFSI (13), FDA/EMA/OSHA Action
(18), Legal Action (34), Recall (41), Regulatory Change (42), Bribery/Corruption (7), Labor
Violation (32).

Eight event types that all ask "is the company one of ours?" and then report. They share the
connection cascade; what differs is the DO-NOT list each one carries, and those exclusions are
where the workload reduction actually comes from.

**Counterfeit has the only explicit product-category exclusion in the ruleset.** "Notify when
related to raw materials, parts, components, etc. Do not report alerts for currency notes, fake
luxury goods, counterfeit fashion items, etc." — so a counterfeit-handbags seizure is out however
large the brand. Note this sits alongside `global-rules.md` #16 (enforcement against illicit
actors is not a disruption to us), which the global gate already applies, so most counterfeit
rows never reach this module at all.

**Legal Action carries the lowest bar and the most dangerous one.** "Do not wait till the
outcome, notify as soon as the trial becomes public. Notify even if it's a potential legal
action." Left literal, that reports every law-firm deadline-reminder press release. `global-rules`
#12 and #14 exist precisely to stop that, and they run in the global gate before this module — so
the recycled-reminder and third-party-speculation patterns are removed upstream, and what reaches
here is a genuine new legal development.

**Regulatory Change has a legislative-stage gate.** "Initial bulletin to be shared when the bill
passes by simple majority and moves to the Senate (or equivalent)", with proposal-stage bills
reportable only "if reputable sources indicate significant impact". So an early-stage bill needs
a significance finding that a later-stage one does not.

**FDA/EMA/OSHA Form 483 is narrower than the rest of its own slide.** "Notify any citation by any
regulatory agency in the world" is near-universal, but "FDA Form 483 - Notify only if a partner is
involved" carves one document type back out.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    IMPACTFUL,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    evidence,
    get,
)
from .connection import connection_cascade, mapped_party, unresolved_cascade
from .global_gate import apply_global_gate

YES_NO = frozenset({"YES", "NO"})

MUST_HAVE_FIELDS = (
    "mapped_or_prominent_party_involved",
    "industry_relevance",
    "product_line_connection",
    "service_sector_applicability",
)


def _plain(fields, *, event_type, prefix, source, mapped_line, product_line, service_line):
    gate = apply_global_gate(fields, candidate_event_type=event_type)
    if gate is not None:
        return gate
    decision = connection_cascade(
        fields, rule_prefix=prefix, source=source,
        mapped_line=mapped_line, product_line=product_line, service_line=service_line,
    )
    return decision or unresolved_cascade(
        fields, rule_prefix=prefix, source=source, rule_text=product_line,
    )


# --- Compliance ---------------------------------------------------------------------------------

COMPLIANCE_EVENT_TYPE = "Compliance"
COMPLIANCE_SOURCE = "rules/event-types-manmade.md § Compliance (slide 10)"
_CMP_ALL = (
    "Like FDA/EMA/OSHA, we notify all kinds of warnings/citations/safety & compliance changes "
    "issued for products with applications in our verticals."
)
_CMP_MAPPED = (
    "If the manufacturer of the affected product(s) is mapped, notify with impact. If not mapped, "
    "notify based on product applications"
)


def decide_compliance(fields: Mapping[str, object]) -> Decision:
    return _plain(
        fields, event_type=COMPLIANCE_EVENT_TYPE, prefix="CMP", source=COMPLIANCE_SOURCE,
        mapped_line=_CMP_MAPPED, product_line=_CMP_ALL, service_line=_CMP_ALL,
    )


# --- FDA/EMA/OSHA Action ------------------------------------------------------------------------

FDA_EVENT_TYPE = "FDA/EMA/OSHA Action"
FDA_SOURCE = "rules/event-types-manmade.md § FDA/EMA/OSHA Action (slide 18)"
_FDA_ANY = "Notify any citation by any regulatory agency in the world"
_FDA_MAPPED = "If mapped sites/company, we notify with the impact attached"
_FDA_UNMAPPED = (
    "If the affected company is not mapped, still notify based on Product applications, including "
    "petrochemicals, healthcare, specialty chemicals, APIs, plastics, glass, coatings, resins, "
    "adhesives, packaging, metals, mining, and more"
)
_FDA_483 = "FDA Form 483 - Notify only if a partner is involved - Send impact if the site is mapped"


def decide_fda_ema_osha(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=FDA_EVENT_TYPE)
    if gate is not None:
        return gate

    # Form 483 is carved back out of the otherwise near-universal "any citation" rule.
    if get(fields, "action_kind", allowed=frozenset({"FORM_483", "OTHER_ACTION"})) == "FORM_483":
        partner = mapped_party(fields)
        if partner == "NO":
            return Decision(
                classification=NOT_IMPACTFUL, rule_id="FDA.R483_NO", rule_text=_FDA_483,
                source=FDA_SOURCE, threshold_met=False, warroom_eligible=False,
                evidence=evidence(fields, "action_kind", "industry_relevance"),
                notes=("Form 483 is narrower than the rest of this slide: partner only.",),
            )
        if partner == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW, rule_id="FDA.R483_REVIEW", rule_text=_FDA_483,
                source=FDA_SOURCE, missing_fields=("industry_relevance",),
                evidence=evidence(fields, "action_kind"),
            )
        return Decision(
            classification=IMPACTFUL, rule_id="FDA.R483_OK", rule_text=_FDA_483,
            source=FDA_SOURCE, threshold_met=True, warroom_eligible=True,
            evidence=evidence(fields, "action_kind", "industry_relevance"),
        )

    return _plain(
        fields, event_type=FDA_EVENT_TYPE, prefix="FDA", source=FDA_SOURCE,
        mapped_line=_FDA_MAPPED, product_line=_FDA_UNMAPPED, service_line=_FDA_ANY,
    )


# --- Regulatory Change ---------------------------------------------------------------------------

REGCHANGE_EVENT_TYPE = "Regulatory Change"
REGCHANGE_SOURCE = "rules/event-types-manmade.md § Regulatory Change (slide 42)"

LEGISLATIVE_STAGE = frozenset(
    {"PROPOSAL", "PASSED_LOWER_HOUSE", "SIGNED_INTO_LAW", "IN_FORCE_OR_CHANGE_ANNOUNCED"}
)

_RC_TRIGGERS = (
    "New laws, rules, or regulations | Changes in existing rules or regulations | Changes in "
    "product compliance | Changes in tax laws/labor laws/trade laws | Changes in customs duty | "
    "Changes in import-export regulations | Changes in tariffs, duties, and levied | Bans on "
    "commodities, companies, and regions"
)
_RC_INITIAL = (
    "Initial bulletin to be shared when the bill passes by simple majority and moves to the Senate "
    "(or equivalent)"
)
_RC_PROPOSAL = (
    "Bills during proposal stage - Report bills during the proposal stage if reputable sources "
    "indicate significant impact on the supply chain and business operations."
)
_RC_APPLICATIONS = (
    "NOTE: Always check products and applications made by the company involved and notify if "
    "applications match our verticals"
)


def decide_regulatory_change(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=REGCHANGE_EVENT_TYPE)
    if gate is not None:
        return gate

    stage = get(fields, "legislative_stage", allowed=LEGISLATIVE_STAGE)
    if stage == "PROPOSAL":
        significant = get(fields, "reputable_sources_indicate_significant_impact", allowed=YES_NO)
        if significant == "NO":
            return Decision(
                classification=NOT_IMPACTFUL, rule_id="RC.R1", rule_text=_RC_PROPOSAL,
                source=REGCHANGE_SOURCE, threshold_met=False, warroom_eligible=False,
                evidence=evidence(fields, "legislative_stage"),
                notes=("A proposal-stage bill needs a significance finding the later stages do "
                       "not.",),
            )
        if significant == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW, rule_id="RC.R2", rule_text=_RC_PROPOSAL,
                source=REGCHANGE_SOURCE,
                missing_fields=("reputable_sources_indicate_significant_impact",),
                evidence=evidence(fields, "legislative_stage"),
            )

    return _plain(
        fields, event_type=REGCHANGE_EVENT_TYPE, prefix="RC", source=REGCHANGE_SOURCE,
        mapped_line=_RC_TRIGGERS + "  ||  " + _RC_INITIAL,
        product_line=_RC_APPLICATIONS, service_line=_RC_APPLICATIONS,
    )


# --- Counterfeit ----------------------------------------------------------------------------------

COUNTERFEIT_EVENT_TYPE = "Counterfeit"
COUNTERFEIT_SOURCE = "rules/event-types-manmade.md § Counterfeit (CFSI) (slide 13)"

#: The only explicit product-category exclusion in the whole ruleset.
COUNTERFEIT_SUBJECT = frozenset(
    {"RAW_MATERIALS_PARTS_COMPONENTS", "CURRENCY_NOTES", "LUXURY_GOODS", "FASHION_ITEMS", "OTHER"}
)
EXCLUDED_SUBJECTS = frozenset({"CURRENCY_NOTES", "LUXURY_GOODS", "FASHION_ITEMS"})

_CF_SCOPE = "Notify when related to raw materials, parts, components, etc."
_CF_EXCLUDE = (
    "Do not report alerts for currency notes, fake luxury goods, counterfeit fashion items, etc."
)
_CF_MONITOR = (
    "A supplier has been found guilty of using a counterfeit part/component in its manufacturing "
    "or products | A supplier is warning customers of counterfeit products circulating in the "
    "market | Regulatory agencies warning of counterfeit products | Customs capture counterfeit "
    "products and announce the company involved"
)


def decide_counterfeit(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=COUNTERFEIT_EVENT_TYPE)
    if gate is not None:
        return gate
    subject = get(fields, "counterfeit_subject", allowed=COUNTERFEIT_SUBJECT)
    if subject in EXCLUDED_SUBJECTS:
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="CF.R1", rule_text=_CF_EXCLUDE,
            source=COUNTERFEIT_SOURCE, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "counterfeit_subject"),
            notes=("The ruleset's only explicit product-category exclusion.",),
        )
    if subject == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="CF.R2",
            rule_text=_CF_SCOPE + "  ||  " + _CF_EXCLUDE, source=COUNTERFEIT_SOURCE,
            missing_fields=("counterfeit_subject",),
            evidence=evidence(fields, "industry_relevance"),
        )
    return _plain(
        fields, event_type=COUNTERFEIT_EVENT_TYPE, prefix="CF", source=COUNTERFEIT_SOURCE,
        mapped_line=_CF_MONITOR, product_line=_CF_SCOPE, service_line=_CF_MONITOR,
    )


# --- Recall ----------------------------------------------------------------------------------------

RECALL_EVENT_TYPE = "Recall"
RECALL_SOURCE = "rules/event-types-manmade.md § Recall (slide 41)"
_RCL_APPLICATIONS = (
    "We notify recalls based on applications and industrial connections (supplier recalling a "
    "faulty part, company recalling a product with applications in our verticals)"
)
_RCL_MAJOR = "A major recall by a company that operates in our verticals, notify"
_RCL_PART = (
    "A product recalled due to a faulty part/component used in it? Find out who supplied the "
    "faulty part and send the impact if it's a mapped supplier"
)


def decide_recall(fields: Mapping[str, object]) -> Decision:
    return _plain(
        fields, event_type=RECALL_EVENT_TYPE, prefix="RCL", source=RECALL_SOURCE,
        mapped_line=_RCL_PART + "  ||  " + _RCL_MAJOR,
        product_line=_RCL_APPLICATIONS, service_line=_RCL_APPLICATIONS,
    )


# --- Legal Action ------------------------------------------------------------------------------------

LEGAL_EVENT_TYPE = "Legal Action"
LEGAL_SOURCE = "rules/event-types-manmade.md § Legal Action (slide 34)"
_LA_NOTIFY = "We notify a lawsuit, legal proceeding, litigation, court case, or trial."
_LA_MAPPED = (
    "We notify when a mapped company (supplier) is involved in a lawsuit, getting sued, settling a "
    "claim or lawsuit, paying a fine due to the legal action, etc."
)
_LA_EARLY = (
    "Do not wait till the outcome, notify as soon as the trial becomes public | Notify even if "
    "it's a potential legal action"
)
_LA_T1 = "Notify if a possible T1 is involved. Not mapped but a big supplier company"


def decide_legal_action(fields: Mapping[str, object]) -> Decision:
    """Legal Action. The `global-rules` #12/#14 exclusions run upstream in the global gate.

    Left to itself this slide is close to notify-always — "notify even if it's a potential legal
    action" — which would report every law-firm deadline-reminder wire release. Those are removed
    by the global gate as `RECYCLED_REMINDER_OF_KNOWN_DEVELOPMENT`, so what arrives here is a
    genuine new development and the cascade is the only remaining test.
    """
    return _plain(
        fields, event_type=LEGAL_EVENT_TYPE, prefix="LA", source=LEGAL_SOURCE,
        mapped_line=_LA_MAPPED, product_line=_LA_T1 + "  ||  " + _LA_NOTIFY,
        service_line=_LA_EARLY,
    )


# --- Bribery/Corruption -------------------------------------------------------------------------------

BRIBERY_EVENT_TYPE = "Bribery/Corruption"
BRIBERY_SOURCE = "rules/event-types-manmade.md § Bribery/Corruption (slide 7)"
_BC_MONITOR = (
    "A supplier has been found guilty of corruption or bribery | A leader of a supplier company is "
    "involved in a scandal | General inspections and investigations where relevant companies are "
    "involved | Signs of poor practices / potential brand impact | Credit rating fluctuates due to "
    "corruption scandals"
)
_BC_REGIONAL = (
    "We also notify state and country level scandals that can potentially impact manufacturing and "
    "supply chain"
)


def decide_bribery_corruption(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=BRIBERY_EVENT_TYPE)
    if gate is not None:
        return gate
    # A state or country level scandal is reportable on regional impact, without a company test.
    if get(fields, "state_or_country_level_scandal", allowed=YES_NO) == "YES":
        if get(fields, "potential_manufacturing_or_supply_chain_impact", allowed=YES_NO) != "NO":
            return Decision(
                classification=IMPACTFUL, rule_id="BC.REGIONAL", rule_text=_BC_REGIONAL,
                source=BRIBERY_SOURCE, threshold_met=True, warroom_eligible=True,
                evidence=evidence(fields, "state_or_country_level_scandal",
                                  "potential_manufacturing_or_supply_chain_impact"),
            )
    return _plain(
        fields, event_type=BRIBERY_EVENT_TYPE, prefix="BC", source=BRIBERY_SOURCE,
        mapped_line=_BC_MONITOR, product_line=_BC_MONITOR, service_line=_BC_MONITOR,
    )


# --- Labor Violation -----------------------------------------------------------------------------------

LABOR_VIOLATION_EVENT_TYPE = "Labor Violation"
LABOR_VIOLATION_SOURCE = "rules/event-types-manmade.md § Labor Violation (slide 32)"
_LV_SCOPE = (
    "We notify child labor, underage labor, slave labor, forced labor, criminal violations, human "
    "trafficking, poor labor conditions, illegal workforce, undocumented workforce, hyper "
    "overtime, health & safety violations, etc."
)
_LV_PARTNER = "We notify if a partner involved or a major company from our verticals is involved"
_LV_SECTORS = "Cargo/Freight Companies, Utility providers, Mining Companies, etc. involved"
_LV_STATE = "A state/country is involved"


def decide_labor_violation(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=LABOR_VIOLATION_EVENT_TYPE)
    if gate is not None:
        return gate
    if get(fields, "state_or_country_involved", allowed=YES_NO) == "YES":
        return Decision(
            classification=IMPACTFUL, rule_id="LV.STATE", rule_text=_LV_STATE,
            source=LABOR_VIOLATION_SOURCE, threshold_met=True, warroom_eligible=True,
            evidence=evidence(fields, "state_or_country_involved"),
        )
    return _plain(
        fields, event_type=LABOR_VIOLATION_EVENT_TYPE, prefix="LV",
        source=LABOR_VIOLATION_SOURCE,
        mapped_line=_LV_PARTNER, product_line=_LV_SCOPE, service_line=_LV_SECTORS,
    )
