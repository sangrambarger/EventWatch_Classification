"""Industry relevance — the field the whole mapped-partner cascade hangs on.

Under the process-owner decision that **a company relevant to one of the 27 covered industries
counts as a mapped partner**, this single field drives `mapped_party()` and therefore most of
every event type's connection test. It was also the field the teacher pass answered most
confidently (12% UNKNOWN, against 80-100% for the mapping lookups it replaced), which is why it
is worth resolving deterministically wherever possible.

Two layers, in order:

1. **Gazetteer.** Terms drawn from `rules/industry_definitions.json` — the authoritative 27
   industries and their official definitions — plus the commodity and sector vocabulary the
   EventWatch rules themselves name. A hit here is a *reading*, not a guess: the definition for
   Freight literally says "ocean carriers, air cargo operators, trucking companies", so a story
   about an air-cargo operator is in Freight by definition.
2. **Out-of-scope list.** The sectors `global-rules.md` #10 and `industries.md` put outside the
   27, with their documented carve-ins (Uber is in scope; major global QSR chains are in scope).

Where neither fires, this returns UNKNOWN and the trained model decides. That ordering matters:
the gazetteer is checked first because a definitional match should never be overridden by a
statistical one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

#: The authoritative 27, loaded rather than hardcoded so a change to the approved document is
#: picked up rather than silently diverging.
INDUSTRY_DEFINITIONS: dict[str, str] = json.loads(
    (RULES_DIR / "industry_definitions.json").read_text(encoding="utf-8")
)
INDUSTRIES = tuple(INDUSTRY_DEFINITIONS)

#: Terms that place a story in a covered industry. Drawn from the official definitions above and
#: from the commodity lists the event-type rules name (petrochemicals, APIs, resins, and so on).
#: This is vocabulary, not a verdict: matching "semiconductor" says the story is about High Tech,
#: it does not say the story is reportable.
GAZETTEER: dict[str, tuple[str, ...]] = {
    "Aerospace": ("aircraft", "aerospace", "aviation", "satellite", "spacecraft", "boeing",
                  "airbus", "jet engine", "avionics", "airworthiness"),
    "Agrochemicals": ("fertiliser", "fertilizer", "pesticide", "herbicide", "crop protection",
                      "agrochemical", "ammonia", "urea", "potash"),
    "Automotive": ("automaker", "car maker", "carmaker", "vehicle", "automotive", "auto parts",
                   "toyota", "volkswagen", "ford", "stellantis", "nissan", "hyundai",
                   "jaguar land rover", "\\bjlr\\b", "tyre", "tire plant", "ev battery"),
    "Biotechnology": ("biotech", "genetic engineering", "gene therapy", "cell therapy",
                      "bio-manufactur", "biomanufactur"),
    "Construction": ("construction", "infrastructure project", "cement", "concrete",
                     "civil engineering", "contractor"),
    "Consumer Electronics": ("consumer electronics", "smartphone", "laptop", "wearable",
                             "smart appliance", "television manufactur"),
    "Cosmetics & Skincare": ("cosmetic", "skincare", "personal care", "beauty product", "toiletr"),
    "Defense": ("defen[cs]e (?:contractor|firm|manufactur|group)", "military hardware",
                "munition", "weapons manufactur", "rafael", "lockheed", "raytheon"),
    "Food & Beverage": ("food (?:processing|manufactur|producer|plant)", "beverage", "brewery",
                        "dairy", "meat (?:plant|processing|packer)", "bakery", "nestl",
                        "distiller", "bottling"),
    "Freight": ("freight", "cargo", "logistics", "shipping line", "ocean carrier", "trucking",
                "haulage", "container ship", "air cargo", "courier", "\\bport\\b", "maersk",
                "supply chain"),
    "Furnishing Goods": ("furniture", "furnishing", "interior decor", "fixtures and fittings"),
    "General Manufacturing": ("manufactur", "factory", "\\bplant\\b", "industrial assembl",
                              "heavy machinery", "machine tool", "foundry", "steel mill",
                              "smelter"),
    "Healthcare": ("hospital", "healthcare", "clinic", "diagnostic lab", "patient care",
                   "medical cent"),
    "High Tech": ("semiconductor", "chipmaker", "chip plant", "microelectronic", "foundry fab",
                  "\\bfab\\b", "robotics", "data cent", "tsmc", "intel", "samsung electronics",
                  "nvidia", "wafer"),
    "Industrial Chemicals": ("chemical", "petrochemical", "polymer", "solvent", "synthetic rubber",
                             "specialty gas", "resin", "adhesive", "coating", "acetone",
                             "\\bipa\\b", "\\bnmp\\b", "caustic soda", "chlorine"),
    "Insurance & Finance": ("\\bbank\\b", "insurer", "insurance", "underwrit", "asset manager",
                            "financial institution", "brokerage", "securities"),
    "Life Sciences": ("pharmaceutical", "\\bpharma\\b", "drug (?:maker|manufactur|plant)",
                      "medical device", "clinical trial", "\\bapi\\b", "vaccine", "biomedical",
                      "novartis", "pfizer", "\\bfda\\b", "\\bema\\b"),
    "Natural Resources & Mining": ("\\bmine\\b", "\\bmining\\b", "quarry", "ore", "smelting",
                                   "timber", "bauxite", "lithium", "cobalt", "copper",
                                   "iron ore", "gold mine", "rare earth"),
    "Oil & Gas": ("refinery", "refiner", "crude", "oil (?:field|rig|pipeline|terminal)",
                  "natural gas", "\\blng\\b", "petroleum", "upstream", "downstream",
                  "chevron", "shell plc", "exxon", "dangote"),
    "Packaging": ("packaging", "corrugated", "container board", "flexible film", "glass bottle",
                  "carton"),
    "Power & Energy": ("power (?:plant|station|grid|utility)", "electricity", "\\bgrid\\b",
                       "renewable energy", "nuclear (?:plant|power)", "solar farm", "wind farm",
                       "utility provider", "transmission line"),
    "Public Transportation": ("public transport", "metro (?:system|rail)", "passenger rail",
                              "transit (?:system|authority)", "municipal bus"),
    "Research & Development (R&D)": ("research institute", "\\br&d\\b", "laborator",
                                     "material testing"),
    "Retail": ("retailer", "supermarket", "e-commerce", "storefront", "shopping centre",
               "shopping center", "walmart", "amazon", "costco"),
    "Software as a Service (SaaS)": ("\\bsaas\\b", "cloud (?:service|platform|provider)",
                                     "enterprise software", "\\berp\\b", "\\bcrm\\b",
                                     "salesforce", "\\bsap\\b", "oracle", "\\baws\\b", "azure"),
    "Telecommunications": ("telecom", "broadband", "mobile network", "fibre optic",
                           "fiber optic", "satellite communication", "\\b5g\\b"),
    "Textile": ("textile", "garment", "apparel manufactur", "fabric", "yarn", "spinning mill",
                "leather (?:export|tannery)"),
}

_COMPILED: dict[str, re.Pattern] = {
    name: re.compile("|".join(f"(?:{t})" for t in terms), re.IGNORECASE)
    for name, terms in GAZETTEER.items()
}

#: Sectors outside the 27, per `industries.md` and `global-rules.md` #10. A story whose ONLY
#: subject is one of these is NOT_RELEVANT.
OUT_OF_SCOPE = re.compile(
    "|".join([
        r"\bhotel\b", r"\bresort\b", r"hospitality group",
        r"commercial fishing", r"fishing (?:fleet|boat|vessel|industry)", r"seafood harvest",
        r"\bcannabis\b", r"\bmarijuana\b",
        r"\bschool\b", r"\buniversity\b", r"\bcollege\b",
        r"\btobacco\b", r"e-cigarette", r"\bvaping\b",
        r"\bcasino\b", r"\bgambling\b",
        r"football|soccer|cricket|basketball|olympic",
        r"\bmovie\b|\bfilm\b|celebrity|entertainment industry",
    ]),
    re.IGNORECASE,
)

#: Documented carve-ins that beat the out-of-scope list (`global-rules.md` #10 and #11).
CARVE_IN = re.compile(
    r"\buber\b|\bstarbucks\b|mcdonald|\bkfc\b|\bqsr\b", re.IGNORECASE
)


def industries_mentioned(text: str) -> list[str]:
    """Every covered industry the text names. Order follows the official list, not match order."""
    return [name for name in INDUSTRIES if _COMPILED[name].search(text)]


def industry_relevance(title: str, summary: str = "") -> tuple[str, str]:
    """Return (RELEVANT | NOT_RELEVANT | UNKNOWN, a one-line reason).

    UNKNOWN is returned rather than guessed whenever nothing definitional fires — the trained
    model handles those, and genuinely ambiguous ones escalate.
    """
    text = f"{title}. {summary}"

    if CARVE_IN.search(text):
        return "RELEVANT", "carve-in (global-rules #10/#11: Uber, major global QSR chains)"

    hits = industries_mentioned(text)
    if hits:
        return "RELEVANT", f"names covered {'industries' if len(hits) > 1 else 'industry'}: " + ", ".join(hits[:3])

    if OUT_OF_SCOPE.search(text):
        return "NOT_RELEVANT", "subject is an explicitly out-of-scope sector"

    return "UNKNOWN", "no covered industry named"
