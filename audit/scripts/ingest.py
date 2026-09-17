#!/usr/bin/env python3
"""Stage 0: load feed chunks into a period store, normalise titles, group exact duplicates.

Chunked uploads are the expected shape (week or fortnight at a time), and one rule matters more
than the rest: **deduplication runs on the union of all chunks, never per chunk.** A story
captured on the 14th and re-filed on the 16th sits in two different weekly files; deduping each
separately counts it twice, inflates the workload figures and corrupts every denominator on the
dashboard. So chunks are appended to a period store and every downstream stage reads the merged
period.

Re-uploading the same chunk is idempotent: rows are keyed on `RowID` + capture timestamp, so a
repeated file adds nothing and the run says so rather than silently doubling.

Usage:
    ingest.py --period 2026-09-07 --add path/to/batch_*.csv
    ingest.py --period 2026-09-07 --report
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

AUDIT_DIR = Path(__file__).resolve().parent.parent
PERIODS_DIR = AUDIT_DIR / "data" / "periods"

#: Logical field -> accepted header spellings, in preference order.
COLUMN_ALIASES = {
    "row_id": ["RowID", "Row ID", "Row_Id"],
    "cluster_title": ["Cluster Title"],
    "story_title": ["Story Title", "Feed Title", "Title"],
    "story_summary": ["Story Summary", "Summary", "Description"],
    "owner": ["Owner", "Assigned Analyst"],
    "captured_at": ["AI Captured Date & Time", "AI Captured Date and Time"],
    "assigned_at": ["Assigned Date & Time"],
    "moved_to_ni_owner": [
        "Moved to Not Impactful (Owner)", "Moved To Not Impactful (Owner)",
        "Moved to Not impactful (Owner)",
    ],
    "moved_to_ni_at": [
        "Date & Time when moved to Not Impactful",
        "Date and Time when moved to Not Impactful",
    ],
    "suppliers": ["Suppliers"],
    "linked_stories": ["Linked Stories"],
    "system_event_classification": ["Event Classification", "AI Event Classification"],
    "not_impactful_feedback": ["Not Impactful Feedback", "NI Feedback"],
    "feedback": ["Feedback"],
}

_WS = re.compile(r"\s+")
#: Punctuation that carries no meaning for identity. Deliberately narrow: company names,
#: locations, dates, numbers, product names and directional wording must survive normalisation,
#: because they are exactly what distinguishes two stories that look alike.
_NON_SEMANTIC = re.compile(r"[\"'“”‘’`´()\[\]{}<>|•·…,;:!?]+")
_DASHES = re.compile(r"[‐-―−]")


def normalise_title(raw: str) -> str:
    """Decode entities, standardise Unicode, lowercase, strip non-semantic punctuation, collapse
    whitespace. Everything that distinguishes one event from another is preserved."""
    text = html.unescape(raw or "")
    text = unicodedata.normalize("NFKC", text)
    text = _DASHES.sub("-", text)
    text = text.lower()
    text = _NON_SEMANTIC.sub(" ", text)
    text = text.replace("&", " and ")
    return _WS.sub(" ", text).strip()


def _find_column(header: list[str], aliases: list[str]) -> str | None:
    lookup = {h.strip().lower(): h for h in header if h}
    for alias in aliases:
        if alias.strip().lower() in lookup:
            return lookup[alias.strip().lower()]
    return None


def read_chunk(path: Path) -> tuple[list[dict], list[str]]:
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        index = {}
        for field, aliases in COLUMN_ALIASES.items():
            found = _find_column(header, aliases)
            if found:
                index[field] = header.index(found)
        if "story_title" not in index:
            raise SystemExit(
                f"ERROR: no Story Title column in {path.name}. Header was: {header}"
            )
        rows = []
        for raw in reader:
            def get(field):
                i = index.get(field)
                if i is None or i >= len(raw):
                    return ""
                return (raw[i] or "").strip()

            title = get("story_title")
            if not title:
                continue
            rows.append({field: get(field) for field in COLUMN_ALIASES})
        missing = sorted(set(COLUMN_ALIASES) - set(index))
        return rows, missing


def _key(row: dict) -> str:
    return hashlib.sha1(
        f"{row['row_id']}|{row['captured_at']}|{normalise_title(row['story_title'])}".encode()
    ).hexdigest()[:16]


def add_chunks(period: str, paths: list[Path]) -> dict:
    store = PERIODS_DIR / period
    store.mkdir(parents=True, exist_ok=True)
    manifest_path = store / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "period": period, "chunks": [], "rows": {}
    }

    added = duplicated = 0
    for path in sorted(paths):
        rows, missing = read_chunk(path)
        new_here = 0
        captures = []
        for row in rows:
            key = _key(row)
            if key in manifest["rows"]:
                duplicated += 1
                continue
            row["_key"] = key
            row["_chunk"] = path.name
            row["normalised_title"] = normalise_title(row["story_title"])
            manifest["rows"][key] = row
            new_here += 1
            if row["captured_at"]:
                captures.append(row["captured_at"])
        added += new_here
        manifest["chunks"].append({
            "file": path.name,
            "rows_in_file": len(rows),
            "rows_added": new_here,
            "rows_already_present": len(rows) - new_here,
            "captured_from": min(captures) if captures else None,
            "captured_to": max(captures) if captures else None,
            "missing_columns": missing,
            "ingested_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        })
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return {"added": added, "already_present": duplicated, "total": len(manifest["rows"])}


def load_period(period: str) -> dict:
    path = PERIODS_DIR / period / "manifest.json"
    if not path.exists():
        raise SystemExit(f"ERROR: no period store at {path}. Run --add first.")
    return json.loads(path.read_text())


def exact_duplicate_groups(manifest: dict) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for key, row in manifest["rows"].items():
        groups.setdefault(row["normalised_title"], []).append(key)
    return groups


def coverage_gaps(manifest: dict) -> list[str]:
    """Report gaps between chunk capture windows, so a missing week reads as missing."""
    spans = sorted(
        (c["captured_from"], c["captured_to"], c["file"])
        for c in manifest["chunks"] if c["captured_from"]
    )
    gaps = []
    for (_, prev_to, prev_file), (next_from, _, next_file) in zip(spans, spans[1:]):
        try:
            gap_days = (
                datetime.fromisoformat(next_from[:19]) - datetime.fromisoformat(prev_to[:19])
            ).days
        except ValueError:
            continue
        if gap_days >= 1:
            gaps.append(f"{gap_days}d between {prev_file} (to {prev_to}) and {next_file}")
    return gaps


def report(period: str) -> None:
    manifest = load_period(period)
    rows = manifest["rows"]
    groups = exact_duplicate_groups(manifest)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    dup_rows = sum(len(v) for v in dup_groups.values())
    captures = sorted(r["captured_at"] for r in rows.values() if r["captured_at"])

    print(f"period                 {period}")
    print(f"chunks                 {len(manifest['chunks'])}")
    for c in manifest["chunks"]:
        print(f"  {c['file']:<24} {c['rows_added']:>5} added, "
              f"{c['rows_already_present']:>4} already present")
    print(f"rows (union)           {len(rows)}")
    print(f"capture window         {captures[0]} -> {captures[-1]}" if captures else "")
    print(f"unique normalised      {len(groups)}")
    print(f"exact-duplicate groups {len(dup_groups)}  covering {dup_rows} rows")
    for gap in coverage_gaps(manifest):
        print(f"  GAP {gap}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--period", required=True)
    p.add_argument("--add", nargs="+", type=Path, default=[])
    p.add_argument("--report", action="store_true")
    args = p.parse_args()

    if args.add:
        result = add_chunks(args.period, args.add)
        print(f"added {result['added']} rows, "
              f"{result['already_present']} already present, "
              f"{result['total']} in period")
    if args.report or not args.add:
        report(args.period)
    return 0


if __name__ == "__main__":
    sys.exit(main())
