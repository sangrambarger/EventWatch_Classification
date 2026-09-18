#!/usr/bin/env python3
"""Prepare the teacher pass: emit row batches plus the field cheatsheet the labeller must fill.

The teacher pass is the only step that reads prose. It produces, per row, the extracted evidence
that the deterministic `logic/` modules then decide over — so its output is *facts about the
story*, never a verdict. Keeping that separation is what makes the pass reusable: a rule change
re-runs `logic/` for free and does not require re-reading 1,079 stories.

The cheatsheet is generated from the decision modules themselves (their enum constants and
`MUST_HAVE_FIELDS`), so a labeller can never be told to produce a value the decider would reject.

Usage:
    build_batches.py --period 2026-09-07 [--size 250]
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logic import registry  # noqa: E402
from logic.connection import DERIVED_FROM_RELEVANCE  # noqa: E402
from scripts.ingest import PERIODS_DIR, load_period  # noqa: E402

#: Fields every row needs regardless of event type — the global gate plus the shared cascade.
UNIVERSAL_FIELDS = {
    "story_nature": [
        "DISRUPTION_OR_RISK_SIGNAL", "ORGANIC_EXPANSION_OR_INVESTMENT",
        "RESUMPTION_OR_ALL_CLEAR_ONLY", "MARKET_COMMENTARY_NO_PHYSICAL_EVENT",
        "ENFORCEMENT_AGAINST_ILLICIT_ACTOR", "CORPORATE_STRUCTURE_CHANGE",
        "RECYCLED_REMINDER_OF_KNOWN_DEVELOPMENT", "UNKNOWN",
    ],
    "subject_identifiable": ["YES", "NO", "UNKNOWN"],
    "industry_relevance": ["RELEVANT", "NOT_RELEVANT", "UNKNOWN"],
    "product_line_connection": ["CONNECTED", "NOT_CONNECTED", "UNKNOWN"],
    "service_sector_applicability": [
        "APPLICABLE", "NOT_APPLICABLE", "NOT_A_SERVICE_SECTOR", "UNKNOWN",
    ],
    "mapped_or_prominent_party_involved": ["YES", "NO", "UNKNOWN"],
}


#: `get(fields, "name", allowed=ENUM)` — captures the field AND the enum guarding it, so the
#: cheatsheet can state each field's own allowed values instead of leaving the labeller to guess
#: which constant applies. Leaving that to inference cost 43% of the first teacher batch: fields
#: guarded by YES_NO were answered "CONNECTED", and free-form stages were invented wholesale.
FIELD_READ = re.compile(
    r'get\(\s*fields\s*,\s*"([a-z0-9_]+)"(?:\s*,\s*allowed=([A-Za-z_][A-Za-z0-9_]*))?'
)
FLOAT_READ = re.compile(r'_as_float\(\s*fields\s*,\s*"([a-z0-9_]+)"')
CALL = re.compile(r'\b([a-z_][a-z0-9_]*)\s*\(')


def fields_read_by(module) -> dict[str, list[str]]:
    """Extract the field names this event type's decision path actually reads.

    Walks the real call graph from `module.decide` rather than scanning whole files, because the
    family modules hold several event types side by side — a file-level scan asked Flood for
    `tornado_status` and `volcanic_activity`, which would have had the labeller extracting
    evidence no flood decision ever consults.

    Derived rather than hand-declared: a maintained field list drifts the moment a rule gains a
    branch, and a cheatsheet missing a field the decider needs sends every affected row to review
    for want of evidence nobody was asked for.
    """
    found: list[tuple[str, list[str]]] = []
    seen: set[str] = set()

    def walk(fn) -> None:
        ident = f"{getattr(fn, '__module__', '')}.{getattr(fn, '__qualname__', '')}"
        if ident in seen or not getattr(fn, "__module__", "").startswith("logic."):
            return
        seen.add(ident)
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):  # pragma: no cover
            return
        namespace = sys.modules[fn.__module__].__dict__
        for field, enum_name in FIELD_READ.findall(src):
            values: list[str] = []
            if enum_name:
                enum = namespace.get(enum_name)
                if isinstance(enum, (frozenset, set)):
                    values = sorted(enum)
            found.append((field, values))
        for field in FLOAT_READ.findall(src):
            found.append((field, ["<number>"]))
        for called in set(CALL.findall(src)):
            target = namespace.get(called)
            if inspect.isfunction(target):
                walk(target)

    walk(module.decide)

    out: dict[str, list[str]] = {}
    for field, values in found:
        # Never ask for a field the pipeline derives. These are supplier-mapping lookups no news
        # story can answer; asking produced 80-100% UNKNOWN and a review queue nobody could clear.
        if field in DERIVED_FROM_RELEVANCE:
            continue
        if field not in out or (not out[field] and values):
            out[field] = values
    # UNKNOWN is always a legal answer and is the correct one whenever the row does not say.
    for field, values in out.items():
        if values and values != ["<number>"] and "UNKNOWN" not in values:
            out[field] = values + ["UNKNOWN"]
        elif not values:
            out[field] = sorted(UNIVERSAL_FIELDS.get(field, ["YES", "NO", "UNKNOWN"]))
    return out


def build_cheatsheet() -> dict:
    sheet = {"universal": UNIVERSAL_FIELDS, "event_types": {}}
    for event_type in sorted(registry.MODULES):
        module = registry.resolve(event_type)
        sheet["event_types"][event_type] = {
            "module": module.__name__.rsplit(".", 1)[-1],
            "fields_to_extract": fields_read_by(module),
            "priority": None,
        }
        try:
            from logic.base import priority_for
            sheet["event_types"][event_type]["priority"] = priority_for(event_type)
        except Exception:  # noqa: BLE001
            pass
    return sheet


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--period", required=True)
    p.add_argument("--size", type=int, default=250)
    args = p.parse_args()

    manifest = load_period(args.period)
    out_dir = PERIODS_DIR / args.period / "teacher"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "field_cheatsheet.json").write_text(json.dumps(build_cheatsheet(), indent=1))

    rows = sorted(
        manifest["rows"].values(),
        key=lambda r: int(r["row_id"]) if r["row_id"].isdigit() else 0,
    )
    batches = [rows[i:i + args.size] for i in range(0, len(rows), args.size)]
    for n, batch in enumerate(batches, start=1):
        payload = [
            {
                "key": r["_key"],
                "row_id": r["row_id"],
                "story_title": r["story_title"],
                "story_summary": (r.get("story_summary") or "")[:1400],
                "cluster_title": r.get("cluster_title", ""),
                "suppliers_field": (r.get("suppliers") or "")[:200],
                "system_event_classification": r.get("system_event_classification", ""),
            }
            for r in batch
        ]
        (out_dir / f"batch_{n:02d}.json").write_text(json.dumps(payload, indent=1))

    print(f"{len(rows)} rows -> {len(batches)} batches of <= {args.size} in {out_dir}")
    print(f"cheatsheet covers {len(registry.MODULES)} event types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
