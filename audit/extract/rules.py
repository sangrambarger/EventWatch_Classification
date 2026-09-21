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
                         r"strike action began",
                         # Added from the 7 Sept shift, where 33 Labor Disruption rows reached
                         # review with no status. Participial forms only — a bare "strike" in a
                         # headline says an event exists, not what stage it is at, so it stays
                         # silent and the row goes to review as before.
                         r"striking workers", r"workers (?:are )?striking",
                         r"strikebreaking", r"ongoing strike", r"during the .{0,20}strike")),
        ("VOTE_CONFIRMED", _rx(r"voted (?:to|in favou?r of) strike", r"strike vote (?:passed|approved)",
                               r"backed (?:a |the )?strike")),
        ("FUTURE_DATED", _rx(r"strike (?:on|from|scheduled for|planned for) \w+ \d",
                             r"will (?:go on )?strike", r"set to strike", r"strike next",
                             r"ahead of (?:a |the )?(?:nationwide |national |general )?strike",
                             r"(?:nationwide|national|general) strike (?:on|called)")),
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
        # Checked before ANNOUNCED, so "entertaining a sale of X" reads as talks rather than as a
        # done deal on the strength of the words "sale of".
        ("SIGNS_TALKS_OR_PLANS", _rx(r"in talks to sell", r"exploring a sale", r"considering a sale",
                                     r"nears? (?:a )?sale", r"plans to sell",
                                     r"entertaining a sale", r"weighing a sale",
                                     r"said to be .{0,30}sale", r"potential sale",
                                     r"put(?:s|ting)? .{0,30}up for sale")),
        # "sale of X to Y" is how a deal desk writes it and how 20 rows of the 7 Sept shift were
        # written; none of them contain the verb "sell".
        ("ANNOUNCED", _rx(r"(?:sold|sells|to sell|agreed to sell|divest)",
                          r"\bsale of\b", r"announce\w*\s+the sale", r"\bsale to\b",
                          r"\bexit\b.{0,30}\bsale\b", r"\bsale\b.{0,20}\bdeal\b")),
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

    # --- Added from the 7 Sept shift's own review backlog -------------------------------------
    # Each of the six fields below was the named reason a block of rows could not be decided.
    # They are here rather than in the model because every one of them is stated outright in the
    # headline: a story says "appoints new Chief Financial Officer", it does not imply it.

    # Leadership Transition gates on the seniority of the role. A headline that names a
    # transition names the office; nothing here infers seniority from context.
    "role": [
        ("CEO", _rx(r"\bceo\b", r"chief executive")),
        ("CFO", _rx(r"\bcfo\b", r"chief financial officer")),
        ("COO", _rx(r"\bcoo\b", r"chief operating officer")),
        ("OTHER_EXECUTIVE", _rx(r"\bchairman\b", r"\bchairperson\b", r"\bchairwoman\b",
                                r"managing director", r"\bpresident\b", r"chief \w+ officer",
                                r"\bct[oi]o?\b", r"\bcmo\b", r"\bchro\b", r"\bciso\b",
                                r"executive director", r"board member", r"general manager",
                                r"head of \w+", r"\bdirector\b")),
    ],

    # Cyber Attack's own slide separates a confirmed breach from an advisory, a campaign with no
    # named victim, a drill and an allegation, and treats them differently. Order is load-bearing:
    # a denial or an allegation qualifies an attack word that appears in the same sentence.
    "incident_nature": [
        ("CYBER_DRILL_OR_SIMULATION", _rx(r"cyber (?:drill|exercise|simulation)",
                                          r"tabletop exercise", r"simulated (?:attack|breach)",
                                          r"penetration test", r"red[- ]team exercise")),
        ("ALLEGED_OR_UNCONFIRMED_INCIDENT", _rx(r"\balleged(?:ly)?\b", r"\bunconfirmed\b",
                                                r"\bsupposed(?:ly)?\b", r"\bpurported(?:ly)?\b",
                                                r"denies? (?:a |any )?(?:breach|hack|attack)",
                                                r"claims? (?:to have )?(?:breached|hacked)",
                                                r"no evidence of (?:a )?(?:breach|compromise)")),
        ("ACTIVE_EXPLOITATION_CAMPAIGN_NO_NAMED_VICTIM", _rx(
            r"actively exploited", r"exploitation campaign", r"under active attack",
            r"threat actors? (?:are )?(?:targeting|exploiting)", r"in[- ]the[- ]wild attacks?",
            r"phishing campaign", r"malware campaign")),
        ("VULNERABILITY_ADVISORY_NO_KNOWN_ATTACK", _rx(
            r"\bcve-\d", r"security (?:advisory|bulletin|flaw)", r"\bvulnerabilit(?:y|ies)\b",
            r"zero[- ]day", r"patch(?:es|ed)? (?:a |the )?(?:flaw|bug|vulnerability)",
            r"issues? (?:a |an )?(?:security )?(?:update|patch)")),
        ("CONFIRMED_ATTACK_OR_BREACH", _rx(
            r"data breach", r"data (?:exposure|leak|theft)", r"ransomware", r"\bhacked\b",
            r"hackers? (?:drain|steal|stole|withdraw|withdrew|access)", r"cyber ?attack",
            r"cyber(?:security)? incident", r"breached (?:the |its )?", r"\bextortion\b",
            r"compromised (?:customer|user|patient|employee) data")),
    ],

    # Layoffs needs either nature or scope to decide, so one pattern firing clears the row.
    "layoff_nature": [
        ("FURLOUGH", _rx(r"\bfurlough")),
        ("TEMPORARY", _rx(r"temporar(?:y|ily) (?:lay ?off|laid off|job cut|suspend)",
                          r"lay ?offs? (?:are )?temporary")),
        # A stated intention is future-scheduled, and the slide reports it as such. Checked
        # before PERMANENT because "to cut 4,000 jobs" contains both readings.
        ("FUTURE_SCHEDULED", _rx(r"\bto cut\b.{0,30}\bjobs?\b", r"plans? to (?:cut|lay ?off|axe)",
                                 r"(?:will|set to|expected to) (?:cut|lay ?off|axe|shed)",
                                 r"may lose (?:their )?jobs", r"could lose (?:their )?jobs",
                                 r"(?:job cuts?|layoffs?) (?:planned|expected|looming|inevitable)",
                                 r"next round of job cuts")),
        ("PERMANENT", _rx(r"\blaid off\b", r"\bjob cuts?\b", r"\blayoffs?\b", r"redundanc",
                          r"(?:cuts|axes|slashes|sheds) \d[\d,]* jobs", r"workforce reduction")),
    ],
    "layoff_scope": [
        ("GLOBAL", _rx(r"\bglobal(?:ly)?\b", r"\bworldwide\b", r"across (?:all|its global)")),
        ("SPECIFIC_DIVISION", _rx(r"(?:at|in|from) its \w+ (?:division|unit|business|arm)",
                                  r"\b(?:division|unit|business arm) (?:will|to) (?:cut|shed|close)")),
    ],

    # Extreme Weather / Tornado. Deliberately silent on the middle ground: a forecast of heavy
    # rain is neither clearly disruptive nor clearly routine, and guessing either way moves a
    # verdict. Only the two ends are read.
    "weather_severity": [
        ("MAJOR_NAMED_STORM", _rx(r"\bhurricane\b", r"\btyphoon\b", r"\bcyclone\b",
                                  r"tropical storm", r"\bnamed storm\b")),
        ("HIGHLY_DISRUPTIVE", _rx(r"\bred alert\b", r"state of emergency", r"\bevacuat",
                                  r"record[- ](?:rain|heat|flood|snow)", r"\bdevastating\b",
                                  r"\btorrential\b", r"\bcatastrophic\b",
                                  r"(?:thousands|millions) (?:left )?(?:without power|powerless)",
                                  r"\bdeadly\b", r"\bkilled\b", r"\bdestroyed\b",
                                  r"\bsevere (?:weather|storm|flooding|heat)\b")),
        ("MINOR_OR_ROUTINE", _rx(r"no (?:damage|injuries|disruption) (?:was |were )?report",
                                 r"\blight (?:rain|snow)\b", r"\bpassed without\b",
                                 r"\bminor (?:flooding|damage|disruption)\b")),
    ],

    # The regional gate's third limb. A story either reports something stopping or it reports
    # that nothing did; the NO patterns run first because "no flights were disrupted" contains
    # "disrupted".
    "operational_disruptions_reported": [
        ("NO", _rx(r"no (?:disruption|impact|delays?|cancellations?)",
                   r"operations (?:were |are )?(?:un|not )affected",
                   r"(?:flights|services|production) (?:were |are )?(?:un|not )affected",
                   r"without (?:any )?disruption")),
        ("YES", _rx(r"(?:halt|suspend|cancel|close|shut)\w*\s+(?:its |the |all )?"
                    r"(?:operation|production|flight|service|plant|factory|port|terminal)",
                    r"(?:operations|production|flights|services|plant|factory|port|terminal)"
                    r"\s+(?:were |was |are |is )?(?:halted|suspended|cancelled|canceled|closed|shut)",
                    r"forced to (?:close|halt|suspend|evacuate)",
                    r"(?:road|rail|port|airport)s? (?:were |are )?(?:blocked|closed)",
                    r"supply (?:chain )?disruption", r"power (?:outage|cut) (?:hit|affect)")),
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
