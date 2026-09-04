#!/usr/bin/env python3
"""Runtime script for the eventwatch-impact-audit skill.

Handles every mechanical step of the audit so Claude's own reasoning is reserved strictly for
the one genuinely subjective step: deciding, for a given row, whether the event is Impactful or
Not Impactful and why. This script never makes that call itself.

Modes:
  --extract INPUT.xlsx [--out records.json]
      Reads the analyst "Not Impactful" workbook, auto-detecting the confirmed column names (or
      close variants, since the real production schema was described but not yet delivered at
      build time), and emits one structured JSON record per row for Claude to reason over.

  --write VERDICTS.json OUTPUT.xlsx [--records records.json]
      Takes Claude's per-row verdicts (event_type, recommended_classification, rationale) and
      renders the final formatted output workbook per the plan's Output Table Spec, plus an
      aggregate summary sheet. All openpyxl/formatting mechanics live here, off the model's own
      token budget.

  --validate [--out records.json]
      Parses references/validation_cases.md into the same record JSON shape as --extract, so the
      8 known real historical misses can be run through the identical pipeline. Emits records.json
      for Claude to classify, exactly like a real run.

  --check-validate VERDICTS.json
      Deterministic pass/fail check: every validation case's expected outcome is Impactful, so
      this just confirms every verdict says so and reports which (if any) didn't, with the
      case's title, for investigation.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

SKILL_DIR = Path(__file__).resolve().parent.parent
VALIDATION_CASES_MD = SKILL_DIR / "references" / "validation_cases.md"

# Logical field -> acceptable column-header variants in the input workbook, in preference order.
COLUMN_ALIASES = {
    "feed_title": ["Story Title", "Feed Title", "Title"],
    "story_summary": ["Story Summary", "Summary", "Description"],
    "owner": ["Owner", "Assigned Analyst"],
    "moved_to_ni_owner": [
        "Moved to Not Impactful (Owner)", "Moved To Not Impactful (Owner)",
        "Moved to Not impactful (Owner)",
    ],
    "not_impactful_feedback": ["Not Impactful Feedback", "NI Feedback", "Feedback"],
    "upstream_event_classification": ["Event Classification", "AI Event Classification"],
    "captured_at": ["AI Captured Date & Time", "AI Captured Date and Time"],
    "moved_at": [
        "Date & Time when moved to Not Impactful",
        "Date and Time when moved to Not Impactful",
    ],
}

OUTPUT_COLUMNS = [
    "Feed Title",
    "Analyst Name",
    "Analyst's Original Classification",
    "Recommended Classification",
    "Event Type",
    "Rationale",
    "Analyst's Stated Reason",
    "Feedback for Next Run",
]


def _find_column(header_row: list[str], aliases: list[str]) -> str | None:
    normalized = {h.strip().lower(): h for h in header_row if h}
    for alias in aliases:
        if alias.strip().lower() in normalized:
            return normalized[alias.strip().lower()]
    return None


def extract_workbook(input_path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(input_path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(c) if c is not None else "" for c in rows[0]]
    col_index = {}
    for field, aliases in COLUMN_ALIASES.items():
        found = _find_column(header, aliases)
        if found:
            col_index[field] = header.index(found)

    missing_required = [f for f in ("feed_title",) if f not in col_index]
    if missing_required:
        raise SystemExit(
            f"ERROR: could not find a column for required field(s) {missing_required} in "
            f"{input_path.name}. Header row was: {header}"
        )

    records = []
    for i, row in enumerate(rows[1:], start=2):  # 1-indexed data rows, header is row 1
        def get(field):
            idx = col_index.get(field)
            if idx is None or idx >= len(row):
                return None
            val = row[idx]
            return str(val).strip() if val is not None else None

        feed_title = get("feed_title")
        if not feed_title:
            continue  # skip blank rows
        analyst_name = get("moved_to_ni_owner") or get("owner") or "(unknown)"
        records.append({
            "row_index": i,
            "feed_title": feed_title,
            "story_summary": get("story_summary") or "",
            "analyst_name": analyst_name,
            "analyst_original_classification": "Not Impactful",
            "analyst_stated_reason": get("not_impactful_feedback") or "",
            "upstream_event_classification": get("upstream_event_classification") or "",
        })
    return records


_CASE_HEADER_RE = re.compile(r"^## Case (\d+) — (.+)$", re.MULTILINE)


def extract_validation_cases(md_path: Path) -> list[dict]:
    text = md_path.read_text(encoding="utf-8")
    matches = list(_CASE_HEADER_RE.finditer(text))
    records = []
    for idx, m in enumerate(matches):
        case_num = m.group(1)
        title_label = m.group(2)
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end]

        def field(label: str) -> str:
            fm = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", body)
            return fm.group(1).strip() if fm else ""

        reconstructed_title = field("Reconstructed title").strip('"')
        customer_line = field("Customer")
        context = field("Context")
        failure = field("Analyst's actual failure (verbatim from tracker)") or \
            field("Analyst's actual failure (verbatim)")
        expected_type = field("Expected Event Type")
        rule = field("Rule that should catch it")

        story_summary = (
            f"Customer: {customer_line}. Context: {context} "
            f"Analyst's own note at the time this was marked Not Impactful (for you to weigh "
            f"critically, not defer to): {failure}"
        )
        records.append({
            "row_index": f"validation-case-{case_num}",
            "feed_title": reconstructed_title,
            "story_summary": story_summary,
            "analyst_name": "(historical case — analyst not individually named in source log)",
            "analyst_original_classification": "Not Impactful",
            "analyst_stated_reason": failure,
            "upstream_event_classification": "",
            "_expected_classification": "Impactful",
            "_expected_event_type_hint": expected_type,
            "_expected_rule_hint": rule,
        })
    return records


def write_output(records: list[dict], verdicts_by_row: dict, output_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Audit Results"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F4E78")
    overturn_fill = PatternFill("solid", fgColor="FFF2CC")
    wrap = Alignment(wrap_text=True, vertical="top")

    ws.append(OUTPUT_COLUMNS)
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill

    overturned = 0
    event_type_counts: dict[str, int] = {}
    pattern_notes: list[str] = []

    for rec in records:
        verdict = verdicts_by_row.get(str(rec["row_index"]), {})
        recommended = verdict.get("recommended_classification", "NEEDS REVIEW — no verdict supplied")
        event_type = verdict.get("event_type", "")
        rationale = verdict.get("rationale", "")
        is_overturn = recommended.strip().lower() == "impactful"
        if is_overturn:
            overturned += 1
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

        row = [
            rec["feed_title"],
            rec["analyst_name"],
            rec["analyst_original_classification"],
            recommended,
            event_type,
            rationale,
            rec["analyst_stated_reason"],
            "",  # Feedback for Next Run — left blank for QA/process-owner notes
        ]
        ws.append(row)
        if is_overturn:
            for cell in ws[ws.max_row]:
                cell.fill = overturn_fill
        for cell in ws[ws.max_row]:
            cell.alignment = wrap

    widths = [42, 20, 18, 20, 22, 60, 45, 30]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"

    # Summary sheet
    ws2 = wb.create_sheet("Summary & Feedback")
    ws2.append(["Metric", "Value"])
    for cell in ws2[1]:
        cell.font = header_font
        cell.fill = header_fill
    total = len(records)
    ws2.append(["Total rows audited", total])
    ws2.append(["Overturned to Impactful", overturned])
    ws2.append(["Confirmed still Not Impactful", total - overturned])
    ws2.append(["Overturn rate", f"{(overturned / total * 100):.1f}%" if total else "n/a"])
    ws2.append([])
    ws2.append(["Overturns by re-derived Event Type", ""])
    for et, count in sorted(event_type_counts.items(), key=lambda kv: -kv[1]):
        ws2.append([et or "(unspecified)", count])
    ws2.column_dimensions["A"].width = 40
    ws2.column_dimensions["B"].width = 20

    wb.save(output_path)
    print(f"wrote {output_path} ({total} rows, {overturned} overturned to Impactful)")


def check_validation(verdicts_path: Path, records: list[dict]) -> int:
    verdicts = json.loads(verdicts_path.read_text(encoding="utf-8"))
    verdicts_by_row = {str(v["row_index"]): v for v in verdicts}
    failures = []
    for rec in records:
        v = verdicts_by_row.get(str(rec["row_index"]))
        if not v:
            failures.append((rec["feed_title"], "no verdict supplied"))
            continue
        got = v.get("recommended_classification", "").strip().lower()
        expected = rec.get("_expected_classification", "Impactful").strip().lower()
        if got != expected:
            failures.append((rec["feed_title"], f"expected {expected}, got {got!r}"))
    total = len(records)
    passed = total - len(failures)
    print(f"Validation: {passed}/{total} known cases classified correctly.")
    for title, reason in failures:
        print(f"  FAIL: {title} — {reason}")
    return 0 if not failures else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--extract", metavar="INPUT.xlsx")
    p.add_argument("--write", nargs=2, metavar=("VERDICTS.json", "OUTPUT.xlsx"))
    p.add_argument("--validate", action="store_true")
    p.add_argument("--check-validate", metavar="VERDICTS.json")
    p.add_argument("--out", default="records.json")
    p.add_argument("--records", default="records.json", help="records.json to pair with --write/--check-validate")
    args = p.parse_args()

    if args.extract:
        records = extract_workbook(Path(args.extract))
        Path(args.out).write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(f"extracted {len(records)} rows -> {args.out}")
        return 0

    if args.validate:
        records = extract_validation_cases(VALIDATION_CASES_MD)
        Path(args.out).write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(f"extracted {len(records)} validation cases -> {args.out}")
        return 0

    if args.write:
        verdicts_path, output_path = args.write
        verdicts = json.loads(Path(verdicts_path).read_text(encoding="utf-8"))
        verdicts_by_row = {str(v["row_index"]): v for v in verdicts}
        records = json.loads(Path(args.records).read_text(encoding="utf-8"))
        write_output(records, verdicts_by_row, Path(output_path))
        return 0

    if args.check_validate:
        records = json.loads(Path(args.records).read_text(encoding="utf-8"))
        return check_validation(Path(args.check_validate), records)

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
