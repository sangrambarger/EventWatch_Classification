#!/usr/bin/env python3
"""Check teacher-pass labels against the schema the decision modules actually enforce.

Runs at the boundary between the one step that reads prose and the steps that are deterministic.
Without it, a label carrying a value no module accepts becomes a `Needs Context Review` row that
looks like missing evidence — when the evidence was present and merely misspelled. The first
teacher batch had 95 of 220 rows in that state (43%), which would have quietly halved the funnel's
decided population and shown up as a review backlog rather than as the extraction bug it was.

Reports, per field, which values were invented and how often, so the fix goes into the cheatsheet
or the prompt rather than into a coercion table here. Deliberately does NOT repair anything:
silently mapping `CONNECTED` onto `YES` would hide exactly the signal this exists to surface.

Usage:
    validate_labels.py --period 2026-09-07 [--strict]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logic import registry  # noqa: E402
from scripts.ingest import PERIODS_DIR, load_period  # noqa: E402


def load_labels(period: str) -> list[dict]:
    teacher = PERIODS_DIR / period / "teacher"
    rows: list[dict] = []
    for path in sorted(teacher.glob("labels_*.json")):
        rows.extend(json.loads(path.read_text()))
    return rows


def validate(period: str) -> dict:
    cheatsheet = json.loads(
        (PERIODS_DIR / period / "teacher" / "field_cheatsheet.json").read_text()
    )
    manifest = load_period(period)
    labels = load_labels(period)

    known_keys = set(manifest["rows"])
    seen_keys: set[str] = set()
    bad_values: dict[str, Counter] = defaultdict(Counter)
    unknown_types: Counter = Counter()
    missing_fields: dict[str, Counter] = defaultdict(Counter)
    unknown_rate: Counter = Counter()
    field_total: Counter = Counter()
    duplicate_keys = 0
    orphan_keys = 0

    for row in labels:
        key = row.get("key")
        if key in seen_keys:
            duplicate_keys += 1
        seen_keys.add(key)
        if key not in known_keys:
            orphan_keys += 1

        event_type = row.get("event_type")
        if not event_type:
            continue
        spec = cheatsheet["event_types"].get(event_type)
        if spec is None:
            unknown_types[event_type] += 1
            continue

        wanted = spec["fields_to_extract"]
        given = row.get("fields") or {}
        for field, allowed in wanted.items():
            field_total[field] += 1
            if field not in given or given[field] in (None, ""):
                missing_fields[event_type][field] += 1
                continue
            value = str(given[field])
            if value == "UNKNOWN":
                # Legal everywhere, including numeric fields — a story that does not state a
                # duration has not stated it, and demanding a float there would push honest
                # UNKNOWNs into the invalid pile.
                unknown_rate[field] += 1
                continue
            if allowed == ["<number>"]:
                try:
                    float(value)
                except ValueError:
                    bad_values[field][value] += 1
                continue
            if value not in allowed:
                bad_values[field][value] += 1

    return {
        "period": period,
        "rows_in_period": len(known_keys),
        "rows_labelled": len(seen_keys),
        "rows_unlabelled": len(known_keys - seen_keys),
        "duplicate_keys": duplicate_keys,
        "orphan_keys": orphan_keys,
        "unknown_event_types": dict(unknown_types),
        "invalid_values": {f: dict(c.most_common()) for f, c in bad_values.items()},
        "invalid_value_count": sum(sum(c.values()) for c in bad_values.values()),
        "fields_omitted": {t: dict(c.most_common(6)) for t, c in missing_fields.items()},
        "unknown_rate": {
            f: round(unknown_rate[f] / field_total[f], 3)
            for f in sorted(field_total, key=lambda f: -unknown_rate[f])[:12]
            if field_total[f]
        },
    }


def render(r: dict) -> None:
    print(f"\n  Teacher-label validation — period {r['period']}")
    print(f"  {'=' * 60}")
    print(f"  rows in period        {r['rows_in_period']}")
    print(f"  rows labelled         {r['rows_labelled']}")
    print(f"  rows UNLABELLED       {r['rows_unlabelled']}")
    print(f"  duplicate keys        {r['duplicate_keys']}")
    print(f"  keys not in period    {r['orphan_keys']}")
    print(f"  invalid field values  {r['invalid_value_count']}")

    if r["unknown_event_types"]:
        print("\n  Event-type names no module recognises:")
        for name, n in r["unknown_event_types"].items():
            print(f"    {name!r:<50}{n:>5}")

    if r["invalid_values"]:
        print("\n  Values outside the schema (fix the cheatsheet or the prompt, not the data):")
        for field, values in sorted(
            r["invalid_values"].items(), key=lambda kv: -sum(kv[1].values())
        )[:12]:
            total = sum(values.values())
            examples = ", ".join(list(values)[:3])
            print(f"    {field:<42}{total:>5}   e.g. {examples[:70]}")

    if r["unknown_rate"]:
        print("\n  Highest UNKNOWN rates (a high rate means the row genuinely does not say,")
        print("  or the field is being asked of stories that cannot answer it):")
        for field, rate in list(r["unknown_rate"].items())[:8]:
            print(f"    {field:<42}{rate:>6.0%}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--period", required=True)
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero if any label is invalid or any row is unlabelled")
    args = p.parse_args()

    result = validate(args.period)
    render(result)
    (PERIODS_DIR / args.period / "label_validation.json").write_text(
        json.dumps(result, indent=1)
    )

    if args.strict and (
        result["invalid_value_count"] or result["rows_unlabelled"]
        or result["unknown_event_types"] or result["orphan_keys"]
    ):
        print("\nFAIL: labels are not clean enough to build a funnel from.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
