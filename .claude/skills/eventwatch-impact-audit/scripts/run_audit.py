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

  --expand-verdicts CLUSTER_VERDICTS.json CLUSTERS.json [--out verdicts.json]
      Takes verdicts keyed by cluster representative row_index (from classifying
      dedup_rows.py's output) plus the cluster map, and expands them into one verdict per
      *original* row_index — every row in a cluster inherits its representative's verdict, with
      the rationale annotated to say so. Feeds the result straight into --write.

  --triage-split TRIAGE.json --records dedup_records.json
      [--out-verdicts triage_verdicts.json] [--out-candidates candidate_records.json]
      Splits a completed triage pass (see references/triage-checklist.md) two ways: IRRELEVANT
      and THIN rows become fully-formed verdicts directly (no further reasoning needed — this is
      the whole point of triage), written to triage_verdicts.json; CANDIDATE rows are filtered
      out of dedup_records.json unchanged, written to candidate_records.json, ready to feed into
      the normal full classification pass. Purely mechanical — the triage_result field decides
      everything, no judgment happens here.

  --merge-verdicts A.json B.json [C.json ...] --out verdicts.json
      Concatenates any number of verdict-shaped JSON arrays into one (e.g. triage_verdicts.json +
      the full classification pass's output on candidate_records.json). Errors if any row_index
      appears in more than one input file, since that means something was double-processed.
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


def expand_verdicts(cluster_verdicts_path: Path, clusters_path: Path, out_path: Path) -> None:
    cluster_verdicts = json.loads(cluster_verdicts_path.read_text(encoding="utf-8"))
    cluster_map = json.loads(clusters_path.read_text(encoding="utf-8"))
    verdicts_by_rep = {str(v["row_index"]): v for v in cluster_verdicts}

    expanded = []
    missing = []
    for rep_row_index, member_row_indices in cluster_map.items():
        verdict = verdicts_by_rep.get(rep_row_index)
        if not verdict:
            missing.append(rep_row_index)
            continue
        for member in member_row_indices:
            if str(member) == str(rep_row_index):
                expanded.append(verdict)
            else:
                note = (
                    f"[Deduplicated: near-identical wire coverage of the same underlying event "
                    f"as row {rep_row_index}, classified there.] {verdict.get('rationale', '')}"
                )
                expanded.append({
                    "row_index": member,
                    "event_type": verdict.get("event_type", ""),
                    "recommended_classification": verdict.get("recommended_classification", ""),
                    "rationale": note,
                })

    out_path.write_text(json.dumps(expanded, indent=2), encoding="utf-8")
    print(f"expanded {len(cluster_verdicts)} cluster verdicts -> {len(expanded)} row verdicts -> {out_path}")
    if missing:
        print(f"WARNING: {len(missing)} cluster representative(s) had no verdict supplied: {missing[:10]}")


# ---------------------------------------------------------------------------
# Mechanical pre-resolution of machine-generated feed templates.
#
# These are NOT judgment shortcuts (the triage-checklist experiment tried that and failed at
# 71.8% accuracy — see SKILL.md). The difference: these patterns are machine-generated feed
# artifacts whose text carries no company, site, or disruption detail by construction, and every
# instance of them in a 3,088-row production run received the same verdict from the full
# reasoning pass. Measured consistency is recorded next to each pattern; anything below 100% on a
# meaningful sample does not belong here and must go to the LLM instead. A pattern that starts
# producing exceptions should be deleted from this list, not patched.
# ---------------------------------------------------------------------------

AUTO_TEMPLATES = [
    {
        "name": "GDACS Green auto-alert",
        # e.g. "Overall Green Forest fire in Mozambique from 27 Aug 2026 00:00 UTC to 02 Sep 2026 00:00 UTC"
        # GDACS's own lowest alert tier, emitted on a schedule; the title format never names a
        # company or site. 66/66 rows in the production run -> Not Impactful (100%).
        # Deliberately Green-only: no Orange/Red examples existed in that run, so there is no
        # evidence for them and they must go to the LLM.
        "pattern": re.compile(r"^\s*Overall Green .+\bUTC\b", re.I),
        "classification": "Not Impactful",
        "event_type": "Irrelevant / Not a Disruption",
        "reason": "GDACS Green scheduled auto-alert; no company, site, or confirmed disruption in the feed text (LOW severity per global-rules #2).",
    },
    {
        "name": "eClips placeholder",
        # Literal wire-service placeholder rows with no story content. 8/8 -> Not Impactful (100%).
        "pattern": re.compile(r"^\s*NLA\s*\|\s*eClips Web\s*$", re.I),
        "classification": "Not Impactful",
        "event_type": "Irrelevant / Not a Disruption",
        "reason": "Wire-service placeholder entry containing no story content.",
    },
]


def prefilter(records_path: Path, out_verdicts: Path, out_remaining: Path) -> None:
    records = json.loads(records_path.read_text(encoding="utf-8"))
    resolved, remaining = [], []
    hits: dict[str, int] = {}
    for rec in records:
        title = rec.get("feed_title", "")
        for tpl in AUTO_TEMPLATES:
            if tpl["pattern"].search(title):
                resolved.append({
                    "row_index": rec["row_index"],
                    "event_type": tpl["event_type"],
                    "recommended_classification": tpl["classification"],
                    "rationale": f"[Auto-template: {tpl['name']}] {tpl['reason']}",
                })
                hits[tpl["name"]] = hits.get(tpl["name"], 0) + 1
                break
        else:
            remaining.append(rec)

    out_verdicts.write_text(json.dumps(resolved, indent=2), encoding="utf-8")
    out_remaining.write_text(json.dumps(remaining, indent=2), encoding="utf-8")
    print(f"prefilter: {len(resolved)} rows auto-resolved, {len(remaining)} need classification")
    for name, n in hits.items():
        print(f"  {name}: {n}")


def write_classification_input(records: list[dict], out_path: Path, fmt: str) -> None:
    """Serialize ONLY what the classifier actually needs: row_index, title, summary.

    The other stored fields are dead weight in the classification prompt — measured at ~44% of
    the input payload across a 3,088-row file once pretty-print whitespace is included:
      - analyst_original_classification is the constant "Not Impactful" on every row (that's what
        this file IS), repeated thousands of times;
      - analyst_name is only needed when Python assembles the output workbook, which reads it back
        from the original records anyway;
      - upstream_event_classification is the binary Event/Non-Event feed tag that global-rules
        explicitly says not to trust — including it is worse than useless, it's a bias risk;
      - analyst_stated_reason was populated on 2 of 3,088 rows in the real file (kept when
        present, since when it IS there it's the analyst's own reasoning to weigh critically).
    """
    if fmt == "tsv":
        lines = ["row_index\tfeed_title\tstory_summary\tanalyst_stated_reason"]
        for r in records:
            def clean(v):
                return str(v or "").replace("\t", " ").replace("\n", " ").replace("\r", " ")
            lines.append(
                f"{r['row_index']}\t{clean(r.get('feed_title'))}\t{clean(r.get('story_summary'))}"
                f"\t{clean(r.get('analyst_stated_reason'))}"
            )
        out_path.write_text("\n".join(lines), encoding="utf-8")
    else:  # jsonl
        lines = []
        for r in records:
            obj = {"row_index": r["row_index"], "feed_title": r.get("feed_title", ""),
                   "story_summary": r.get("story_summary", "")}
            if str(r.get("analyst_stated_reason") or "").strip():
                obj["analyst_stated_reason"] = r["analyst_stated_reason"]
            lines.append(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
        out_path.write_text("\n".join(lines), encoding="utf-8")


def make_batches(records_path: Path, out_dir: Path, batch_size: int, fmt: str) -> None:
    records = json.loads(records_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "tsv" if fmt == "tsv" else "jsonl"
    n_batches = 0
    for i in range(0, len(records), batch_size):
        chunk = records[i:i + batch_size]
        path = out_dir / f"batch_{i // batch_size:02d}.{ext}"
        write_classification_input(chunk, path, fmt)
        n_batches += 1
        approx_tok = path.stat().st_size / 4
        print(f"  {path.name}: {len(chunk)} rows, ~{approx_tok:.0f} tok")
    print(f"wrote {n_batches} batch files to {out_dir} (format={fmt}, batch_size={batch_size})")


def build_reference_bundle(skill_dir: Path, out_path: Path) -> None:
    """One file the classifier reads once, instead of 4-6 separate reads per batch.

    Excludes triage-checklist.md (rejected, see SKILL.md) and validation_cases.md (test fixture,
    not needed for a production run)."""
    parts = []
    for name in ["global-rules.md", "industries.md", "priority-matrix.md",
                 "event-types-manmade.md", "event-types-natural.md", "event-types-other.md"]:
        p = skill_dir / "references" / name
        parts.append(f"\n\n{'=' * 78}\n=== {name} ===\n{'=' * 78}\n\n" + p.read_text(encoding="utf-8"))
    out_path.write_text("".join(parts), encoding="utf-8")
    print(f"wrote reference bundle -> {out_path} (~{out_path.stat().st_size / 4:.0f} tok, one read instead of 6)")


def triage_split(triage_path: Path, records_path: Path, out_verdicts: Path, out_candidates: Path) -> None:
    triage_results = json.loads(triage_path.read_text(encoding="utf-8"))
    records = json.loads(records_path.read_text(encoding="utf-8"))
    triage_by_row = {str(t["row_index"]): t for t in triage_results}

    resolved_verdicts = []
    candidate_records = []
    missing = []
    for rec in records:
        t = triage_by_row.get(str(rec["row_index"]))
        if not t:
            missing.append(rec["row_index"])
            continue
        result = t.get("triage_result", "").strip().upper()
        if result == "CANDIDATE":
            candidate_records.append(rec)
        elif result in ("IRRELEVANT", "THIN"):
            classification = "Not Impactful" if result == "IRRELEVANT" else "Impactful"
            resolved_verdicts.append({
                "row_index": rec["row_index"],
                "event_type": t.get("event_type", "Irrelevant / Not a Disruption"),
                "recommended_classification": classification,
                "rationale": f"[Triage: {result}] {t.get('reason', '')}",
            })
        else:
            missing.append(rec["row_index"])

    out_verdicts.write_text(json.dumps(resolved_verdicts, indent=2), encoding="utf-8")
    out_candidates.write_text(json.dumps(candidate_records, indent=2), encoding="utf-8")
    print(
        f"triage split: {len(resolved_verdicts)} resolved directly (IRRELEVANT/THIN), "
        f"{len(candidate_records)} candidates need full classification"
        + (f", {len(missing)} rows had no usable triage result (treated as unresolved)" if missing else "")
    )
    if missing:
        print(f"  unresolved row_index sample: {missing[:10]}")


def merge_verdicts(input_paths: list[Path], out_path: Path) -> None:
    combined = []
    seen: dict[str, Path] = {}
    for p in input_paths:
        verdicts = json.loads(p.read_text(encoding="utf-8"))
        for v in verdicts:
            key = str(v["row_index"])
            if key in seen:
                raise SystemExit(
                    f"ERROR: row_index {key!r} appears in both {seen[key]} and {p} — "
                    f"a row was double-processed, refusing to silently pick one."
                )
            seen[key] = p
            combined.append(v)
    out_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(f"merged {len(input_paths)} files -> {len(combined)} verdicts -> {out_path}")


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
    p.add_argument("--expand-verdicts", nargs=2, metavar=("CLUSTER_VERDICTS.json", "CLUSTERS.json"))
    p.add_argument("--triage-split", metavar="TRIAGE.json")
    p.add_argument("--out-verdicts", default="triage_verdicts.json")
    p.add_argument("--out-candidates", default="candidate_records.json")
    p.add_argument("--merge-verdicts", nargs="+", metavar="VERDICTS.json")
    p.add_argument("--prefilter", metavar="RECORDS.json",
                   help="auto-resolve machine-generated feed templates (GDACS Green, eClips placeholders)")
    p.add_argument("--out-remaining", default="remaining_records.json")
    p.add_argument("--make-batches", metavar="RECORDS.json",
                   help="split records into lean per-batch files for the classification pass")
    p.add_argument("--batch-size", type=int, default=250)
    p.add_argument("--format", choices=["tsv", "jsonl"], default="tsv",
                   help="lean serialization format for classification input (default tsv, the leanest)")
    p.add_argument("--out-dir", default="batches")
    p.add_argument("--reference-bundle", action="store_true",
                   help="concatenate the production reference docs into one file (one read per batch)")
    p.add_argument("--out", default="records.json")
    p.add_argument("--records", default="records.json", help="records.json to pair with --write/--check-validate/--triage-split")
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

    if args.expand_verdicts:
        cluster_verdicts_path, clusters_path = args.expand_verdicts
        expand_verdicts(Path(cluster_verdicts_path), Path(clusters_path), Path(args.out))
        return 0

    if args.triage_split:
        triage_split(
            Path(args.triage_split), Path(args.records),
            Path(args.out_verdicts), Path(args.out_candidates),
        )
        return 0

    if args.merge_verdicts:
        merge_verdicts([Path(p_) for p_ in args.merge_verdicts], Path(args.out))
        return 0

    if args.prefilter:
        prefilter(Path(args.prefilter), Path(args.out_verdicts), Path(args.out_remaining))
        return 0

    if args.make_batches:
        make_batches(Path(args.make_batches), Path(args.out_dir), args.batch_size, args.format)
        return 0

    if args.reference_bundle:
        build_reference_bundle(SKILL_DIR, Path(args.out))
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
