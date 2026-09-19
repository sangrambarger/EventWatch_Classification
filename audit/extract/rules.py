"""Deterministic field extraction — no model, no API call, microseconds per row.

This is the half of extraction that does not need judgement. A story either says "flood warning"
or it says "flood watch"; either it names a magnitude or it does not. Those are **facts on the
page**, and reading them with patterns is not the keyword classification that was ruled out —
nothing here decides Impactful. Every value produced goes into `logic/`, which applies the
thresholds.

The distinction worth holding onto:

- **Forbidden**: `if "fire" in title: impactful = True`. A keyword standing in for a judgement.
- **This file**: `if "flood warning" in text: flood_alert_tier = WARNING`. A pattern reading a
  fact the story states outright, which a rule then reasons about.

Where a pattern would be guessing rather than reading, it returns nothing and the field stays
UNKNOWN — the model layer or the escalation queue handles it. Silence is the correct output for
a pattern that is not sure.
"""

from __future__ import annotations

import re
from typing import Mapping

#: Compiled once; these run over every row of a 500k-row month.
def _rx(*patterns: str) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


# --- Numeric ----------------------------------------------------------------------------------

_MAGNITUDE = re.compile(
    r"\b(?:magnitude|mag\.?|M)\s*[-: ]?\s*(\d\.\d|\d)\b|\b(\d\.\d)\s*[- ]?magnitude\b",
    re.IGNORECASE,
)
_DEPTH = re.compile(r"\bdepth\s+(?:of\s+)?(\d{1,3}(?:\.\d)?)\s*(km|kilomet|mile)", re.IGNORECASE)
_HOURS = re.compile(
    r"\b(\d{1,3}(?:\.\d)?)\s*[- ]?(?:hour|hr)s?\b|\b(\d{1,2})\s*[- ]?day", re.IGNORECASE
)


def magnitude(text: str) -> str | None:
    m = _MAGNITUDE.search(text)
    if not m:
        return None
    value = m.group(1) or m.group(2)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # A "magnitude 12" is a typo or a different sense of the word, not an earthquake reading.
    return str(f) if 1.0 <= f <= 10.0 else None


def depth_miles(text: str) -> str | None:
    m = _DEPTH.search(text)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    return str(round(value / 1.609, 1)) if unit.startswith("km") else str(value)


def duration_hours(text: str) -> str | None:
    m = _HOURS.search(text)
    if not m:
        return None
    if m.group(1):
        return str(float(m.group(1)))
    if m.group(2):
        return str(float(m.group(2)) * 24)
    return None


# --- Lexical enums ------------------------------------------------------------------------------
# Each entry: field -> ordered list of (value, pattern). First match wins, so the more specific
# pattern must come first. Order is load-bearing: "flood watch" contains "flood", and
# "operations resumed" must beat "operations".

ENUM_PATTERNS: dict[str, list[tuple[str, re.Pattern]]] = {
    # Flood: three tiers that read alike in a headline and mean different things. Only WARNING is
    # reportable, so mixing them up changes the verdict.
    "flood_alert_tier": [
        ("WATCH", _rx(r"flood watch")),
        ("ADVISORY", _rx(r"flood advisor")),
        ("WARNING", _rx(r"flood warning", r"flash flood warning")),
        ("ACTUAL_FLOODING", _rx(r"\bflood(?:ed|ing|s|waters)?\b", r"inundat", r"submerged")),
    ],
    "tornado_status": [
        ("TOUCHDOWN", _rx(r"tornado (?:hit|struck|touch(?:ed)? down|damage|destroyed|ripped)",
                          r"touchdown", r"(?:hit|struck) by a tornado")),
        ("WARNING_ONLY", _rx(r"tornado warning", r"tornado watch", r"tornado alert")),
    ],
    "volcanic_activity": [
        ("ALERT_OR_EVACUATION", _rx(r"volcan\w* (?:alert|warning)", r"evacuat\w+.{0,40}volcan",
                                    r"volcan\w+.{0,40}evacuat")),
        ("ERUPTING", _rx(r"erupt(?:ed|ing|ion)", r"ash (?:cloud|plume|fall)", r"lava")),
        ("SIGNS_OF_ERUPTION", _rx(r"signs of (?:an? )?erupt", r"volcanic (?:activity|unrest|tremor)",
                                  r"seismic activity.{0,30}volcan")),
    ],
    "fire_status": [
        ("EXTINGUISHED", _rx(r"extinguish", r"put out", r"brought under control", r"doused")),
        ("RECOVERED", _rx(r"reopen", r"resumed (?:operation|production)")),
        ("UNDER_INVESTIGATION", _rx(r"under investigation", r"investigat\w+ (?:the |into )?(?:cause|fire|blaze)")),
        ("ACTIVE", _rx(r"still burning", r"blaze", r"\bfire (?:broke out|erupted|rages)",
                       r"battling the")),
    ],
    "fire_scale": [
        ("EXPLOSION", _rx(r"explosion", r"blast", r"exploded")),
        ("MINOR", _rx(r"\bminor\b", r"\bsmall\b(?:.{0,20})fire", r"no (?:injuries|casualties|damage)")),
        ("SIGNIFICANT", _rx(r"\bmajor\b", r"\bmassive\b", r"\bhuge\b", r"destroyed", r"gutted")),
    ],
    "cargo_impact": [
        ("NO_FLIGHT_DISRUPTION", _rx(r"no (?:flight|flights) (?:were )?(?:affected|disrupted|cancel)",
                                     r"flights (?:were )?(?:un|not )affected",
                                     r"operations (?:were )?(?:un|not )affected")),
        ("CARGO_DISRUPTED", _rx(r"\bcargo\b", r"\bfreight\b", r"air (?:cargo|freight)")),
        ("PASSENGER_ONLY", _rx(r"passenger", r"travell?ers", r"holidaymakers")),
    ],
    "disruption_scale": [
        ("COMPLETE_HALT", _rx(r"(?:completely|fully) (?:halted|closed|shut)",
                              r"suspend(?:ed)? all (?:flights|operations)",
                              r"(?:airport|port) (?:closed|shut down)", r"all flights (?:were )?(?:cancel|halt)")),
        ("MINOR_RESOLVED_QUICKLY", _rx(r"briefly", r"quickly (?:resolved|restored|reopened)",
                                       r"resumed (?:within|after) \d+ (?:minute|hour)")),
        ("HIGH_CANCELLATIONS", _rx(r"(?:hundreds|dozens|scores) of (?:flights|services)",
                                   r"\d{2,} flights (?:were )?cancel", r"mass cancellation")),
        ("PARTIAL", _rx(r"partial", r"some (?:flights|services)", r"delays?")),
    ],
    "strike_status": [
        ("CALLED_OFF", _rx(r"strike (?:has been |was )?(?:called off|cancell?ed|averted|suspended)",
                           r"called off (?:the |their )?strike", r"deal (?:reached|struck).{0,30}avert")),
        ("UNDERWAY", _rx(r"strike (?:began|started|entered|continues|is underway|enters)",
                         r"(?:workers|staff|employees) (?:are )?(?:on strike|walked out)",
                         r"strike action began")),
        ("VOTE_CONFIRMED", _rx(r"voted (?:to|in favou?r of) strike", r"strike vote (?:passed|approved)",
                               r"backed (?:a |the )?strike")),
        ("FUTURE_DATED", _rx(r"strike (?:on|from|scheduled for|planned for) \w+ \d",
                             r"will (?:go on )?strike", r"set to strike", r"strike next")),
        ("CONTRACT_NEGOTIATIONS_ON", _rx(r"(?:contract|wage|pay) (?:talks|negotiations)",
                                         r"collective bargaining")),
        ("INTENTION_OR_BALLOT_PENDING", _rx(r"threaten(?:ed|ing)? (?:to|a) strike", r"strike ballot",
                                            r"could strike", r"may strike", r"strike notice")),
    ],
    "smog_alert_tier": [
        ("RED_HIGHEST", _rx(r"red alert", r"severe (?:smog|pollution|air quality)",
                            r"hazardous air")),
        ("LOWER", _rx(r"(?:orange|yellow|amber) alert", r"moderate (?:smog|pollution)",
                      r"air quality (?:alert|advisory|warning)")),
    ],
    "action_kind": [
        ("FORM_483", _rx(r"form 483", r"\b483\b")),
        ("OTHER_ACTION", _rx(r"warning letter", r"citation", r"\bosha\b", r"\bfda\b", r"\bema\b",
                             r"regulator")),
    ],
    "force_majeure_declared": [
        ("YES", _rx(r"force majeure")),
    ],
    "counterfeit_subject": [
        ("CURRENCY_NOTES", _rx(r"counterfeit (?:currency|notes|banknotes|money|cash)",
                               r"fake (?:currency|notes|banknotes)")),
        ("LUXURY_GOODS", _rx(r"counterfeit (?:luxury|handbag|watch|jewel)",
                             r"fake (?:luxury|handbag|designer)")),
        ("FASHION_ITEMS", _rx(r"counterfeit (?:fashion|apparel|clothing|sneaker|shoe)",
                              r"fake (?:fashion|apparel|clothing)")),
        ("RAW_MATERIALS_PARTS_COMPONENTS", _rx(r"counterfeit (?:part|component|chip|semiconductor|"
                                               r"material|drug|medicine|pharmaceutical)")),
    ],
    "commodity_is_coal": [
        ("YES", _rx(r"\bcoal\b|\bcoking coal\b|\bthermal coal\b")),
    ],
    "legislative_stage": [
        ("SIGNED_INTO_LAW", _rx(r"signed into law", r"enacted", r"became law")),
        ("PASSED_LOWER_HOUSE", _rx(r"passed the (?:house|assembly|lower house|lok sabha)",
                                   r"approved by (?:the )?(?:house|parliament|congress)")),
        ("PROPOSAL", _rx(r"\bbill\b", r"\bproposal\b", r"\bproposed\b", r"\bdraft\b",
                         r"introduced legislation")),
        ("IN_FORCE_OR_CHANGE_ANNOUNCED", _rx(r"takes effect", r"comes into force", r"new (?:rule|tariff|duty)",
                                             r"tariff", r"announced (?:new )?regulation")),
    ],
    "bankruptcy_stage": [
        ("FILED", _rx(r"filed for (?:bankruptcy|chapter 11|chapter 7|insolvency|administration)",
                      r"(?:enters?|entered) administration", r"declared bankrupt")),
        ("PROCEEDING_UNDERWAY", _rx(r"bankruptcy (?:proceeding|process|court|hearing)",
                                    r"insolvency (?:proceeding|administrator)", r"receivership")),
        ("MISSED_OR_DEFAULT_PAYMENTS", _rx(r"missed (?:a )?payment", r"defaulted", r"default on")),
        ("REBRANDING_AFTER_BANKRUPTCY", _rx(r"emerged from (?:bankruptcy|chapter 11)", r"rebrand")),
        ("SIGNS_OR_TALKS", _rx(r"(?:possible|potential|may file for|considering) (?:bankruptcy|insolvency)",
                               r"bankruptcy (?:risk|fears|talks|warning)", r"on the brink")),
    ],
    "disruption_nature": [
        ("ROUTINE_PLANNED_MAINTENANCE", _rx(r"(?:annual|routine|scheduled|planned) maintenance",
                                            r"maintenance shutdown", r"planned (?:outage|turnaround)")),
        ("EVACUATION_OR_LOCKDOWN", _rx(r"evacuat", r"lockdown")),
        ("INDUSTRIAL_ACCIDENT", _rx(r"(?:worker|employee) (?:died|killed|injured)", r"industrial accident",
                                    r"workplace (?:accident|death)")),
        ("SECURITY_INCIDENT", _rx(r"shooting", r"terror", r"bomb threat", r"explosive device")),
        ("BLOCKED_ACCESS", _rx(r"blocked (?:access|road|entrance)", r"road block")),
        ("PRODUCTION_HALT_OR_CUT", _rx(r"(?:halt|suspend|pause|cut)\w* production",
                                       r"production (?:halt|suspend|cut|freeze)")),
        ("PARTIAL_OR_FULL_CLOSURE", _rx(r"(?:close|closure|shut)\w*.{0,20}(?:plant|factory|site|facility)",
                                        r"(?:plant|factory|site).{0,20}(?:close|closure|shut)")),
        ("FUTURE_OR_SCHEDULED_SHUTDOWN", _rx(r"will (?:close|shut)", r"to close in", r"slated to close")),
        ("UNPLANNED_SHUTDOWN", _rx(r"unplanned", r"unexpected(?:ly)? (?:halt|shut|stop)", r"emergency shutdown")),
    ],
    "outage_kind": [
        ("SOFTWARE_OR_INTERNET", _rx(r"internet outage", r"cloud (?:outage|disruption)",
                                     r"\bsaas\b", r"\berp\b", r"data cent(?:er|re) outage",
                                     r"(?:aws|azure|gcp) (?:outage|down)", r"telecom outage")),
        ("POWER", _rx(r"power (?:outage|cut|failure)", r"blackout", r"electricity (?:cut|outage)",
                      r"grid (?:failure|collapse)")),
    ],
    "operations_already_resumed": [
        ("YES", _rx(r"operations (?:have )?resumed", r"back (?:to )?normal", r"service restored",
                    r"fully restored")),
    ],
    "sale_stage": [
        ("COMPLETED", _rx(r"completed the (?:sale|acquisition)", r"sale (?:has )?closed",
                          r"deal (?:has )?closed")),
        ("SIGNS_TALKS_OR_PLANS", _rx(r"in talks to sell", r"exploring a sale", r"considering a sale",
                                     r"nears? (?:a )?sale", r"plans to sell")),
        ("ANNOUNCED", _rx(r"(?:sold|sells|to sell|agreed to sell|divest)")),
    ],
    "deal_stage": [
        ("COMPLETED", _rx(r"completed the (?:merger|acquisition)", r"deal (?:has )?closed",
                          r"acquisition (?:is )?complete")),
        ("REGULATORY_APPROVAL_PENDING", _rx(r"(?:regulatory|antitrust) (?:approval|clearance)",
                                            r"awaiting approval", r"subject to approval")),
        ("SIGNS_TALKS_OR_PLANS", _rx(r"in talks to (?:acquire|buy|merge)", r"exploring (?:a )?(?:merger|acquisition)",
                                     r"nears? (?:a )?(?:deal|acquisition)")),
        ("ANNOUNCED", _rx(r"(?:acquire|acquisition|merger|merge|buy(?:s|out)?|takeover)")),
    ],
}

#: Fields whose only meaningful pattern is a positive hit; absence is NOT evidence of "NO",
#: so they stay UNKNOWN rather than being defaulted.
POSITIVE_ONLY = frozenset({
    "force_majeure_declared", "commodity_is_coal", "operations_already_resumed",
})


def extract_enums(text: str) -> dict[str, str]:
    """Return every field a pattern can read off the text. Silent where unsure."""
    out: dict[str, str] = {}
    for field, candidates in ENUM_PATTERNS.items():
        for value, pattern in candidates:
            if pattern.search(text):
                out[field] = value
                break
    return out


def extract_numeric(text: str) -> dict[str, str]:
    out = {}
    for field, fn in (("magnitude", magnitude), ("depth_miles", depth_miles),
                      ("duration_hours", duration_hours)):
        value = fn(text)
        if value is not None:
            out[field] = value
    return out


# --- Cross-cutting signals ----------------------------------------------------------------------

_RESUMPTION = _rx(r"operations (?:have )?resumed", r"back to normal", r"all[- ]clear",
                  r"service (?:has been )?restored", r"reopened after")
_EXPANSION = _rx(r"\bexpan(?:d|sion)\b", r"new (?:plant|factory|facility) (?:in|at)",
                 r"\binvest(?:ment|ing)?\b.{0,30}(?:billion|million)", r"to double",
                 r"break(?:s|ing)? ground", r"capacity (?:increase|expansion)")
_MARKET_ONLY = _rx(r"\b(?:stock|shares|bitcoin|crypto|index|yields?)\b.{0,40}"
                   r"\b(?:rally|surge|slump|fall|rise|gain|drop|tumble)\b",
                   r"price target", r"analyst (?:rating|upgrade|downgrade)")
_ENFORCEMENT = _rx(r"\b(?:raid|bust|seiz(?:ed|ure)|crackdown|takedown)\b",
                   r"police (?:arrest|detain|seiz)", r"illegal (?:refinery|mining|operation)",
                   r"smuggl")
_REMINDER = _rx(r"reminds? (?:investors|shareholders)", r"deadline (?:reminder|approaching)",
                r"class action.{0,40}deadline", r"lead plaintiff deadline")
_CORPORATE = _rx(r"\b(?:acquisition|acquire|merger|merge|takeover|divest|spin[- ]?off|"
                 r"restructur|sells?|sold|stake)\b")


def story_nature_signal(text: str) -> str | None:
    """A conservative read of `story_nature`, or None to defer to the model.

    Order matters and follows `global-rules.md`: the corporate carve-out is checked before the
    expansion pattern, because rule #8 explicitly does not reach corporate-structure stories and
    "acquires a plant" would otherwise read as expansion.
    """
    if _REMINDER.search(text):
        return "RECYCLED_REMINDER_OF_KNOWN_DEVELOPMENT"
    if _CORPORATE.search(text):
        return "CORPORATE_STRUCTURE_CHANGE"
    if _ENFORCEMENT.search(text):
        return "ENFORCEMENT_AGAINST_ILLICIT_ACTOR"
    if _MARKET_ONLY.search(text):
        return "MARKET_COMMENTARY_NO_PHYSICAL_EVENT"
    if _EXPANSION.search(text):
        return "ORGANIC_EXPANSION_OR_INVESTMENT"
    if _RESUMPTION.search(text):
        return "RESUMPTION_OR_ALL_CLEAR_ONLY"
    return None


def extract_all(title: str, summary: str = "") -> dict[str, str]:
    """Every field the deterministic layer can read. The model fills the rest."""
    text = f"{title}. {summary}"
    out: dict[str, str] = {}
    out.update(extract_enums(text))
    out.update(extract_numeric(text))
    for field in POSITIVE_ONLY:
        out.pop(field, None) if field not in out else None
    return out
