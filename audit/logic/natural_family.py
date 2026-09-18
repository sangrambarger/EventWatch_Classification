"""Geopolitical, Protest/Riot and the nine natural-hazard event types.

Sources: `event-types-manmade.md` §§ Geopolitical (26), Protest/Riot (40);
`event-types-natural.md` §§ Environmental Hazard (16), Extreme Weather (17), Flood (23), Forest
Fire (25), Human Health (28), Hurricane/Typhoon Pre-Landfall (29) and Post-Landfall (30), Tornado
(44), Volcano (45).

These eleven are **regional** rather than company-centric: their gate is "do we have sites in the
region of impact", not "is this company one of ours". So they share a different helper from the
corporate cascade — `_regional_gate` — which asks, in the order the slides use:

1. partner/mapped sites in the affected region
2. failing that, is the region industrially important (manufacturing hubs, ports, airports, roads,
   mining, utilities)
3. failing that, are operational disruptions actually reported

Two members break the pattern deliberately, and those are the interesting ones:

**Volcano ignores the gate entirely.** "Notify even if no sites in the region" — the only natural
hazard that says so, because ash disrupts aviation far beyond the eruption. It is the natural-
hazard counterpart of Chemical Spill and should be expected to remove almost nothing.

**Extreme Weather has the strictest bar of the group and an explicit DO-NOT.** "Report only highly
disruptive weather scenarios", "DO NOT REPORT thunderstorms and minor frequent weather
disruptions", "Notify extreme weather situations only if partner sites are in the region", and
"Notify only if infrastructure damage, transportation disruptions, flight cancellations, or
utility service disruptions are reported". Three "only"s and a DO-NOT — both the regional gate and
a reported-disruption test must pass. In a real feed this is a large, clean removal: routine storm
and rainfall-warning rows fail it.

**Flood carries a warning-tier distinction that is easy to lose**: "We can report Flood Warning
but DO NOT report Flood Watch or Flood Advisory." Three tiers that read alike in a headline and
mean different things.

**Hurricane splits into two event types by lifecycle**, and the split is the rule: Pre-Landfall
reports when "the storm starts shaping and landfall is certain"; Post-Landfall is the update
stream once it lands. Neither carries a company-connection test at all — the storm's path is the
scope.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    IMPACTFUL,
    LOW,
    NEEDS_CONTEXT_REVIEW,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    evidence,
    get,
)
from .connection import derived_or_given
from .global_gate import apply_global_gate

YES_NO = frozenset({"YES", "NO"})

REGIONAL_FIELDS = (
    "sites_mapped_in_region",
    "region_industrially_important",
    "operational_disruptions_reported",
)


def _regional_gate(
    fields: Mapping[str, object],
    *,
    prefix: str,
    source: str,
    sites_line: str,
    importance_line: str,
    disruption_line: str,
    require_disruption: bool = False,
    severity_when_importance_only: str | None = None,
) -> Decision | None:
    """The shared regional test: mapped sites → regional importance → reported disruptions.

    `require_disruption=True` implements the event types whose slides say *both* a regional
    presence and a reported disruption are needed (Extreme Weather, Tornado), rather than either.
    """
    sites = derived_or_given(fields, "sites_mapped_in_region")
    important = get(fields, "region_industrially_important", allowed=YES_NO)
    disruptions = get(fields, "operational_disruptions_reported", allowed=YES_NO)
    trail = evidence(fields, *REGIONAL_FIELDS)

    if require_disruption:
        if disruptions == "NO":
            return Decision(
                classification=NOT_IMPACTFUL, rule_id=f"{prefix}.NODISRUPT",
                rule_text=disruption_line, source=source, threshold_met=False,
                warroom_eligible=False, evidence=trail,
            )
        if disruptions == UNKNOWN:
            return Decision(
                classification=THRESHOLD_REVIEW, rule_id=f"{prefix}.DISRUPT_REVIEW",
                rule_text=disruption_line, source=source,
                missing_fields=("operational_disruptions_reported",), evidence=trail,
            )

    if sites == "YES":
        return Decision(
            classification=IMPACTFUL, rule_id=f"{prefix}.SITES", rule_text=sites_line,
            source=source, threshold_met=True, warroom_eligible=True, evidence=trail,
        )
    if important == "YES":
        return Decision(
            classification=IMPACTFUL, rule_id=f"{prefix}.REGION", rule_text=importance_line,
            source=source, threshold_met=True, warroom_eligible=True,
            severity=severity_when_importance_only, evidence=trail,
        )
    if disruptions == "YES" and not require_disruption:
        return Decision(
            classification=IMPACTFUL, rule_id=f"{prefix}.DISRUPT", rule_text=disruption_line,
            source=source, threshold_met=True, warroom_eligible=True, evidence=trail,
        )
    if sites == "NO" and important == "NO" and disruptions in {"NO", UNKNOWN}:
        return Decision(
            classification=NOT_IMPACTFUL, rule_id=f"{prefix}.NONE",
            rule_text=sites_line + "  ||  " + importance_line, source=source,
            threshold_met=False, warroom_eligible=False, evidence=trail,
        )
    missing = tuple(n for n in REGIONAL_FIELDS if get(fields, n) == UNKNOWN)
    if missing:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id=f"{prefix}.REVIEW",
            rule_text=sites_line + "  ||  " + importance_line, source=source,
            missing_fields=missing, evidence=trail,
            notes=("Fail-closed operational default under global-rules #4 is Impactful.",),
        )
    return None


def _regional_type(fields, *, event_type, prefix, source, sites_line, importance_line,
                   disruption_line, require_disruption=False, severity=None):
    gate = apply_global_gate(fields, candidate_event_type=event_type)
    if gate is not None:
        return gate
    decision = _regional_gate(
        fields, prefix=prefix, source=source, sites_line=sites_line,
        importance_line=importance_line, disruption_line=disruption_line,
        require_disruption=require_disruption, severity_when_importance_only=severity,
    )
    return decision or Decision(
        classification=THRESHOLD_REVIEW, rule_id=f"{prefix}.UNRESOLVED",
        rule_text=sites_line, source=source, missing_fields=("sites_mapped_in_region",),
        evidence=evidence(fields, *REGIONAL_FIELDS),
    )


# --- Geopolitical ------------------------------------------------------------------------------

GEO_EVENT_TYPE = "Geopolitical"
GEO_SOURCE = "rules/event-types-manmade.md § Geopolitical (slide 26)"
_GEO_SITES = "Notify if sites mapped in the country/City/State involved"
_GEO_TRADE = "Notify major trade deals and agreements"
_GEO_INFRA = (
    "Check if the Partner site(s) in the region of impact | Major roads/ports/airports in the "
    "region | Transportation/Freight disruptions expected | Subsequent Unrest/protests/riots "
    "reported"
)


def decide_geopolitical(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=GEO_EVENT_TYPE)
    if gate is not None:
        return gate
    # Major trade deals and agreements are reportable without a regional site test.
    if get(fields, "major_trade_deal_or_agreement", allowed=YES_NO) == "YES":
        return Decision(
            classification=IMPACTFUL, rule_id="GEO.TRADE", rule_text=_GEO_TRADE,
            source=GEO_SOURCE, threshold_met=True, warroom_eligible=True,
            evidence=evidence(fields, "major_trade_deal_or_agreement"),
        )
    return _regional_type(
        fields, event_type=GEO_EVENT_TYPE, prefix="GEO", source=GEO_SOURCE,
        sites_line=_GEO_SITES, importance_line=_GEO_INFRA, disruption_line=_GEO_INFRA,
    )


# --- Protest/Riot ------------------------------------------------------------------------------

PROTEST_EVENT_TYPE = "Protest/Riot"
PROTEST_SOURCE = "rules/event-types-manmade.md § Protest/Riot (slide 40)"
_PR_REGION = "Regional level event - Notify if sites are mapped in the region."
_PR_IMPORTANT = (
    "Check if important manufacturing regions/major roads/ports/airports/business parks/utility "
    "providers are potentially impacted"
)
_PR_SITE = "Site Level Event - Notify if the partner site involved"
_PR_MARTIAL = (
    "If Martial Law is introduced, we should create a new series under Geopolitical"
)


def decide_protest_riot(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=PROTEST_EVENT_TYPE)
    if gate is not None:
        return gate
    if get(fields, "martial_law_introduced", allowed=YES_NO) == "YES":
        return Decision(
            classification=NEEDS_CONTEXT_REVIEW,
            rule_id="PR.MARTIAL", rule_text=_PR_MARTIAL, source=PROTEST_SOURCE,
            missing_fields=("event_type_reassignment",),
            evidence=evidence(fields, "martial_law_introduced"),
            reroute_to="Geopolitical",
            notes=("Martial law opens a new series under Geopolitical, so this module does not "
                   "decide it.",),
        )
    return _regional_type(
        fields, event_type=PROTEST_EVENT_TYPE, prefix="PR", source=PROTEST_SOURCE,
        sites_line=_PR_REGION + "  ||  " + _PR_SITE, importance_line=_PR_IMPORTANT,
        disruption_line=_PR_IMPORTANT,
    )


# --- Environmental Hazard -----------------------------------------------------------------------

ENV_EVENT_TYPE = "Environmental Hazard"
ENV_SOURCE = "rules/event-types-natural.md § Environmental Hazard (slide 16)"
_ENV_SMOG = (
    "Smog Alert - Notify highest level (Red) smog/pollution alerts if sites mapped in the region "
    "of impact (send impact)"
)
_ENV_PARTNER = (
    "Partner site(s) involved in air, water, or river pollution, high emissions rate observed at "
    "the site, etc.? Notify straightaway (send customer impact)"
)
_ENV_UNMAPPED = (
    "If the company is not mapped - Send a bulletin if products have applications in the "
    "industries, we cover. Possible sub-tier or Tier 1 yet to be mapped (decide based on product "
    "line)"
)


def decide_environmental_hazard(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=ENV_EVENT_TYPE)
    if gate is not None:
        return gate
    # Only the highest (Red) smog tier qualifies; lower alert levels do not.
    tier = get(fields, "smog_alert_tier", allowed=frozenset({"RED_HIGHEST", "LOWER", "NOT_A_SMOG_ALERT"}))
    if tier == "LOWER":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="ENV.SMOG_LOW", rule_text=_ENV_SMOG,
            source=ENV_SOURCE, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "smog_alert_tier"),
            notes=("The source qualifies smog alerts to the highest (Red) level only.",),
        )
    return _regional_type(
        fields, event_type=ENV_EVENT_TYPE, prefix="ENV", source=ENV_SOURCE,
        sites_line=_ENV_PARTNER, importance_line=_ENV_UNMAPPED, disruption_line=_ENV_PARTNER,
    )


# --- Extreme Weather ------------------------------------------------------------------------------

WEATHER_EVENT_TYPE = "Extreme Weather"
WEATHER_SOURCE = "rules/event-types-natural.md § Extreme Weather (slide 17)"
_EW_ONLY = "Notify extreme weather situations only if partner sites are in the region."
_EW_DISRUPT = (
    "Notify only if infrastructure damage, transportation disruptions, flight cancellations, or "
    "utility service disruptions are reported."
)
_EW_DONT = "DO NOT REPORT thunderstorms and minor frequent weather disruptions."
_EW_NAMED = (
    "Major Named Snowstorms: Notify proactively as soon as they are identified before the storm "
    "reaches the region."
)

WEATHER_SEVERITY = frozenset({"HIGHLY_DISRUPTIVE", "MAJOR_NAMED_STORM", "MINOR_OR_ROUTINE"})


def decide_extreme_weather(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=WEATHER_EVENT_TYPE)
    if gate is not None:
        return gate

    severity = get(fields, "weather_severity", allowed=WEATHER_SEVERITY)
    if severity == "MINOR_OR_ROUTINE":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="EW.R1", rule_text=_EW_DONT,
            source=WEATHER_SOURCE, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "weather_severity"),
            notes=("Thunderstorms and routine weather are excluded outright — the strictest "
                   "natural-hazard bar in the ruleset.",),
        )
    if severity == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="EW.R2",
            rule_text=_EW_DONT + "  ||  " + "Report only highly disruptive weather scenarios",
            source=WEATHER_SOURCE, missing_fields=("weather_severity",),
            evidence=evidence(fields, *REGIONAL_FIELDS),
        )
    # A major named storm is notified proactively, before disruptions are reported.
    return _regional_type(
        fields, event_type=WEATHER_EVENT_TYPE, prefix="EW", source=WEATHER_SOURCE,
        sites_line=_EW_ONLY + "  ||  " + _EW_NAMED, importance_line=_EW_ONLY,
        disruption_line=_EW_DISRUPT,
        require_disruption=severity != "MAJOR_NAMED_STORM",
    )


# --- Flood -----------------------------------------------------------------------------------------

FLOOD_EVENT_TYPE = "Flood"
FLOOD_SOURCE = "rules/event-types-natural.md § Flood (slide 23)"
_FL_SITES = "We notify flooding events if we have supplier sites(s) in the region of impact"
_FL_SERVICES = (
    "Other than supplier sites, we also check if any services or any of the following operations "
    "are affected: Logistics providers, cargo shipping, utility provider, farming, ports, "
    "airports, postal services, train & freight, mining, data centers, power grids, nuclear power "
    "plants and more"
)
_FL_PROACTIVE = (
    "We should be notifying flooding events pro-actively if there are warnings and evacuations in "
    "the region."
)
_FL_TIER = "We can report Flood Warning but DO NOT report Flood Watch or Flood Advisory"

FLOOD_ALERT_TIER = frozenset({"WARNING", "WATCH", "ADVISORY", "ACTUAL_FLOODING"})


def decide_flood(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=FLOOD_EVENT_TYPE)
    if gate is not None:
        return gate
    tier = get(fields, "flood_alert_tier", allowed=FLOOD_ALERT_TIER)
    if tier in {"WATCH", "ADVISORY"}:
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="FL.TIER", rule_text=_FL_TIER,
            source=FLOOD_SOURCE, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "flood_alert_tier"),
            notes=("Warning, Watch and Advisory read alike in a headline and mean different "
                   "things; only Warning is reportable.",),
        )
    if tier == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="FL.TIER_REVIEW", rule_text=_FL_TIER,
            source=FLOOD_SOURCE, missing_fields=("flood_alert_tier",),
            evidence=evidence(fields, *REGIONAL_FIELDS),
        )
    return _regional_type(
        fields, event_type=FLOOD_EVENT_TYPE, prefix="FL", source=FLOOD_SOURCE,
        sites_line=_FL_SITES + "  ||  " + _FL_PROACTIVE, importance_line=_FL_SERVICES,
        disruption_line=_FL_SERVICES,
    )


# --- Forest Fire -------------------------------------------------------------------------------------

FOREST_EVENT_TYPE = "Forest Fire"
FOREST_SOURCE = "rules/event-types-natural.md § Forest Fire (slide 25)"
_FF_ONLY = "Notify only if partner site(s) in the region of impact"
_FF_INFRA = (
    "Check if any industrial parks, mines, major roads, port(s) and airport(s), etc. are "
    "potentially affected and notify"
)
_FF_CONSEQ = (
    "Check if evacuations, power outages, road closures, or flight cancelations are announced "
    "because of the wildfire. | Notify if potential freight/cargo disruptions expected"
)


def decide_forest_fire(fields: Mapping[str, object]) -> Decision:
    return _regional_type(
        fields, event_type=FOREST_EVENT_TYPE, prefix="FRF", source=FOREST_SOURCE,
        sites_line=_FF_ONLY, importance_line=_FF_INFRA, disruption_line=_FF_CONSEQ,
    )


# --- Human Health --------------------------------------------------------------------------------------

HEALTH_EVENT_TYPE = "Human Health"
HEALTH_SOURCE = "rules/event-types-natural.md § Human Health (slide 28)"
_HH_MAJOR = "Major outbreak, pandemic, or epidemic declared"
_HH_SITES = "Partner site(s) in the region of impact"
_HH_REGION = "The important manufacturing region, travel restrictions, labor disruptions, etc."
_HH_LEADER = "Notify if a leader of a supplier company is severely sick"


def decide_human_health(fields: Mapping[str, object]) -> Decision:
    gate = apply_global_gate(fields, candidate_event_type=HEALTH_EVENT_TYPE)
    if gate is not None:
        return gate
    if get(fields, "supplier_leader_severely_ill", allowed=YES_NO) == "YES":
        return Decision(
            classification=IMPACTFUL, rule_id="HH.LEADER", rule_text=_HH_LEADER,
            source=HEALTH_SOURCE, threshold_met=True, warroom_eligible=True, severity=LOW,
            evidence=evidence(fields, "supplier_leader_severely_ill"),
        )
    return _regional_type(
        fields, event_type=HEALTH_EVENT_TYPE, prefix="HH", source=HEALTH_SOURCE,
        sites_line=_HH_SITES + "  ||  " + _HH_MAJOR, importance_line=_HH_REGION,
        disruption_line=_HH_REGION,
    )


# --- Hurricane / Typhoon -----------------------------------------------------------------------------------

HURRICANE_PRE_EVENT_TYPE = "Hurricane/Typhoon (Pre-Landfall)"
HURRICANE_PRE_SOURCE = "rules/event-types-natural.md § Hurricane/Typhoon (Pre-Landfall) (slide 29)"
HURRICANE_POST_EVENT_TYPE = "Hurricane/Typhoon (Post-Landfall)"
HURRICANE_POST_SOURCE = (
    "rules/event-types-natural.md § Hurricane/Typhoon (Post-Landfall) (slide 30)"
)

_HU_INITIAL = (
    "INITIAL BULLETIN: When the storm starts shaping and landfall is certain | Possibly a named "
    "major storm | Threatening important manufacturing region | Sites/Ports/airports in its path"
)
_HU_POST = (
    "UPDATE: when it makes landfall (send supplier impact) | UPDATE: Post-landfall destruction "
    "reported - Evacuations | Structural damages | Transportation/Cargo Disruptions | "
    "Manufacturing Disruptions | Power outages | Flight disruptions | Port disruptions and more"
)

LANDFALL_CERTAINTY = frozenset({"CERTAIN", "UNCERTAIN_OR_DEVELOPING"})


def decide_hurricane_pre_landfall(fields: Mapping[str, object]) -> Decision:
    """Pre-Landfall. No company-connection test at all — the storm's projected path is the scope."""
    gate = apply_global_gate(fields, candidate_event_type=HURRICANE_PRE_EVENT_TYPE)
    if gate is not None:
        return gate
    certainty = get(fields, "landfall_certainty", allowed=LANDFALL_CERTAINTY)
    if certainty == "UNCERTAIN_OR_DEVELOPING":
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="HUP.R1", rule_text=_HU_INITIAL,
            source=HURRICANE_PRE_SOURCE, missing_fields=("landfall_certainty",),
            evidence=evidence(fields, "landfall_certainty", *REGIONAL_FIELDS),
            notes=("The initial bulletin is triggered by landfall becoming certain; a developing "
                   "system is monitored, not yet notified.",),
        )
    return _regional_type(
        fields, event_type=HURRICANE_PRE_EVENT_TYPE, prefix="HUP",
        source=HURRICANE_PRE_SOURCE, sites_line=_HU_INITIAL, importance_line=_HU_INITIAL,
        disruption_line=_HU_INITIAL,
    )


def decide_hurricane_post_landfall(fields: Mapping[str, object]) -> Decision:
    """Post-Landfall. The storm has landed, so this is an update stream rather than a threshold."""
    gate = apply_global_gate(fields, candidate_event_type=HURRICANE_POST_EVENT_TYPE)
    if gate is not None:
        return gate
    return _regional_type(
        fields, event_type=HURRICANE_POST_EVENT_TYPE, prefix="HUS",
        source=HURRICANE_POST_SOURCE, sites_line=_HU_POST, importance_line=_HU_POST,
        disruption_line=_HU_POST,
    )


# --- Tornado ---------------------------------------------------------------------------------------------

TORNADO_EVENT_TYPE = "Tornado"
TORNADO_SOURCE = "rules/event-types-natural.md § Tornado (slide 44)"
_TO_HITS = (
    "Tornado hits, cause structural damages? Notify if the site(s) mapped in the exact "
    "vicinity/village/community"
)
_TO_CONSEQ = (
    "Notify if road closures, business closures, power outages, airport/port disruptions, or "
    "utility disruptions reported"
)
_TO_WARNING = (
    "Warnings issued? Check if the site(s) are mapped in the region and keep an eye (Monitor)"
)
_TO_SCOPE = (
    "Unlike major storms, tornadoes affect smaller vicinities. We cannot flag an entire state or "
    "city for a Tornado event"
)


def decide_tornado(fields: Mapping[str, object]) -> Decision:
    """Tornado. A warning alone is a monitor state, not a notification.

    The source distinguishes "Warnings issued? ... keep an eye (Monitor)" from "Tornado hits,
    cause structural damages? Notify" — so, like Earthquake's rest-of-world monitor band, a
    warning with no touchdown is watched rather than reported.
    """
    gate = apply_global_gate(fields, candidate_event_type=TORNADO_EVENT_TYPE)
    if gate is not None:
        return gate
    status = get(fields, "tornado_status", allowed=frozenset({"WARNING_ONLY", "TOUCHDOWN"}))
    if status == "WARNING_ONLY":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="TO.WARN", rule_text=_TO_WARNING,
            source=TORNADO_SOURCE, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "tornado_status", *REGIONAL_FIELDS),
            notes=("Monitor state, not a notification — the source reserves notification for a "
                   "touchdown causing damage.",),
        )
    return _regional_type(
        fields, event_type=TORNADO_EVENT_TYPE, prefix="TO", source=TORNADO_SOURCE,
        sites_line=_TO_HITS + "  ||  " + _TO_SCOPE, importance_line=_TO_CONSEQ,
        disruption_line=_TO_CONSEQ, require_disruption=False,
    )


# --- Volcano ---------------------------------------------------------------------------------------------

VOLCANO_EVENT_TYPE = "Volcano"
VOLCANO_SOURCE = "rules/event-types-natural.md § Volcano (slide 45)"
_VO_EVEN_IF = "Notify even if no sites in the region"
_VO_SIGNS = "Notify as soon as Signs of Eruptions reported"
_VO_AVIATION = "Possible aviation disruptions"


def decide_volcano(fields: Mapping[str, object]) -> Decision:
    """Volcano. The only natural hazard with no regional gate at all.

    "Notify even if no sites in the region" — ash disrupts aviation far beyond the eruption, so
    there is nothing for a site test to reject. Like Chemical Spill, this type should be expected
    to remove almost nothing; a high Not Impactful rate here indicates an extraction fault.
    """
    gate = apply_global_gate(fields, candidate_event_type=VOLCANO_EVENT_TYPE)
    if gate is not None:
        return gate
    activity = get(
        fields, "volcanic_activity",
        allowed=frozenset({"SIGNS_OF_ERUPTION", "ERUPTING", "ALERT_OR_EVACUATION", "NONE_REPORTED"}),
    )
    if activity == "NONE_REPORTED":
        return Decision(
            classification=NOT_IMPACTFUL, rule_id="VO.NONE", rule_text=_VO_SIGNS,
            source=VOLCANO_SOURCE, threshold_met=False, warroom_eligible=False,
            evidence=evidence(fields, "volcanic_activity"),
        )
    if activity == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW, rule_id="VO.REVIEW", rule_text=_VO_SIGNS,
            source=VOLCANO_SOURCE, missing_fields=("volcanic_activity",),
            evidence=evidence(fields, *REGIONAL_FIELDS),
        )
    return Decision(
        classification=IMPACTFUL, rule_id="VO.R1",
        rule_text=_VO_EVEN_IF + "  ||  " + _VO_SIGNS + "  ||  " + _VO_AVIATION,
        source=VOLCANO_SOURCE, threshold_met=True, warroom_eligible=True,
        evidence=evidence(fields, "volcanic_activity", *REGIONAL_FIELDS),
        notes=("No regional gate: the source notifies even with no sites in the region.",),
    )
