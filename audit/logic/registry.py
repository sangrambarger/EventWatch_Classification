"""Event type → decision module dispatch, and the coverage ledger.

Canonical event-type names are read **fresh from the rules files** on every call rather than kept
in a second hardcoded list, so a rename in the approved source cannot silently diverge from what
this package dispatches on. `resolve()` fails closed: an unrecognised name raises rather than
fuzzy-matching to the nearest module, because a near-miss match would apply the wrong event
type's threshold and produce a confident, wrong, auditable-looking verdict.

`coverage()` reports which event types have a decision module, which have a supplied extraction
schema, and which have neither. That ledger is the honest answer to "is this done yet", and it is
what the dashboard's methodology page should render rather than a claim of completeness.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from types import ModuleType

from .base import RuleConflict

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas" / "extraction_fields"

RULE_FILES = (
    "event-types-manmade.md",
    "event-types-natural.md",
    "event-types-other.md",
)

#: Canonical name -> module in this package. Adding an event type means adding one row here and
#: writing the module; nothing else in the pipeline changes.
MODULES: dict[str, str] = {
    "Merger & Acquisition": "merger_acquisition",
    "Business Sale": "business_sale",
    "Cyber Attack": "cyber_attack",
    "Factory Fire": "factory_fire",
    "Chemical Spill": "chemical_spill",
    "Leadership Transition": "leadership_transition",
    "Earthquake (Japan/Taiwan/S.Korea/Philippines/Indonesia/China)": "earthquake",
    "Earthquake (Rest of the World)": "earthquake",
    "Power Outage": "power_outage",
    "Layoffs": "layoffs",
    "Airworthiness": "airworthiness",
    "Mail/Postal/Package Delivery Services Disruptions": "mail_postal_delivery",
    "Others": "others",
}

#: Entries in the rules files that are redirects to a canonical type, not types in their own
#: right. Resolving one returns the target's module, so a row labelled with the redirect name is
#: decided by the rules that actually govern it.
REDIRECTS: dict[str, str] = {
    "Military Drills": "Geopolitical",
    "Container Ship Accidents": "Port Disruption",
    "Software/Internet Outage": "Power Outage",
}

#: Not an event type at all — a cross-cutting sourcing rule. Never dispatched.
NOT_EVENT_TYPES = frozenset({"Restricted Access"})


def canonical_event_types() -> list[str]:
    """Every `### ` heading across the three rules files, source of truth for valid names."""
    names: list[str] = []
    for filename in RULE_FILES:
        for line in (RULES_DIR / filename).read_text(encoding="utf-8").splitlines():
            if line.startswith("### "):
                names.append(re.sub(r"\s*_\(source.*$", "", line[4:]).strip())
    if not names:  # pragma: no cover
        raise RuleConflict(f"no event-type headings parsed from {RULES_DIR}")
    return names


def _strip_annotation(name: str) -> str:
    """'Military Drills (redirect -> Geopolitical)' -> 'Military Drills'."""
    return re.sub(r"\s*\((redirect|cross-cutting)[^)]*\)\s*$", "", name).strip()


def resolve(event_type: str) -> ModuleType:
    """Return the decision module for an event type, or raise.

    Fails closed on an unrecognised name — no fuzzy matching. A wrong-but-plausible match would
    apply another event type's threshold and produce a verdict that looks fully audited and is
    simply wrong.
    """
    name = _strip_annotation(event_type)
    name = REDIRECTS.get(name, name)
    if name in NOT_EVENT_TYPES:
        raise RuleConflict(
            f"{event_type!r} is a cross-cutting sourcing rule, not an event type; it has no "
            "reporting threshold to apply"
        )
    module_name = MODULES.get(name)
    if module_name is None:
        known = ", ".join(sorted(MODULES))
        raise RuleConflict(
            f"no decision module for event type {event_type!r}. Built so far: {known}. "
            "Add a module and register it rather than dispatching to an approximate match."
        )
    return importlib.import_module(f"{__package__}.{module_name}")


def _schema_stems() -> dict[str, str]:
    out = {}
    for path in SCHEMA_DIR.iterdir():
        if path.suffix == ".json":
            stem = path.name.replace("_Extraction_Only_Fields.json", "")
            out[re.sub(r"[^a-z0-9]+", "", stem.lower())] = path.name
    return out


def coverage() -> dict[str, list[str]]:
    """Report module and schema coverage across the full rulebook taxonomy."""
    schemas = _schema_stems()
    has_module: list[str] = []
    no_module: list[str] = []
    module_no_schema: list[str] = []
    for raw in canonical_event_types():
        name = _strip_annotation(raw)
        if name in NOT_EVENT_TYPES:
            continue
        target = REDIRECTS.get(name, name)
        if target in MODULES:
            has_module.append(raw)
            key = re.sub(r"[^a-z0-9]+", "", target.lower())
            if not any(key.startswith(s) or s in key for s in schemas):
                module_no_schema.append(target)
        else:
            no_module.append(raw)
    return {
        "with_module": sorted(set(has_module)),
        "without_module": sorted(set(no_module)),
        "module_but_no_supplied_schema": sorted(set(module_no_schema)),
    }


def decide(event_type: str, fields):
    """Convenience: resolve the module and apply it."""
    return resolve(event_type).decide(fields)
