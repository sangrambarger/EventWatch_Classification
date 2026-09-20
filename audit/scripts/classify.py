#!/usr/bin/env python3
"""Classify a feed file end to end, with no network call and no API key.

One code path, shared by the CLI and the dashboard's upload page, so a result produced by
`streamlit run audit/app.py` is byte-identical to one produced here. Two artefacts come out:

- **results** — every row with its verdict, the verbatim rule it fired on, and the provenance of
  every extracted field, so any number can be traced back without re-running anything.
- **escalation queue** — the rows the deterministic path could not resolve. This is the only
  thing an LLM ever needs to see, and the only question worth asking it is the cheap binary one:
  *is this plausibly a supply-chain event at all?*

The split matters for cost. On the 2026-09-07 shift, 80% of rows resolve here for free and 20%
land in the queue — so an LLM fallback is a fifth of the volume at a fraction of the depth,
rather than every row read in full.

Usage:
    classify.py --in feed.csv --out results.csv [--escalations queue.csv]
    classify.py --period 2026-09-07                 # classify an ingested period
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extract.model import Extractor  # noqa: E402
from extract.pipeline import extract, to_decision_fields  # noqa: E402
from logic import registry  # noqa: E402
from logic.base import NOT_IMPACTFUL, REVIEW_OUTCOMES, RuleConflict, priority_for  # noqa: E402
from scripts.ingest import COLUMN_ALIASES, load_period, normalise_title, read_chunk  # noqa: E402

RESULT_COLUMNS = [
    "row_id", "story_title", "classification", "event_type", "priority", "severity",
    "rule_id", "threshold_met", "missing_fields", "reroute_to", "escalate",
    "escalation_reasons", "rule_text", "source", "evidence", "field_provenance", "owner",
    "captured_at",
]

ESCALATION_COLUMNS = [
    "row_id", "story_title", "story_summary", "escalation_reasons",
    "best_guess_event_type", "event_type_confidence", "industry_relevance",
    "question_for_review",
]

#: The single question an escalated row needs answered. Deliberately binary and cheap — the
#: expensive per-event-type threshold reasoning already lives in `logic/` and does not need to be
#: repeated by a model.
ESCALATION_QUESTION = (
    "Is this story plausibly a supply-chain event — does it describe a disruption, risk signal or "
    "corporate-structure change affecting a company, site, commodity or route in a covered "
    "industry? Answer YES or NO."
)


@dataclass
class Row:
    row_id: str
    title: str
    summary: str
    owner: str = ""
    captured_at: str = ""


def _as_csv(path: Path) -> Path:
    """Spreadsheet uploads are converted to CSV, so there is one reader, not two.

    `read_chunk` owns column-alias resolution — the header on these feeds varies by export tool —
    and duplicating that for openpyxl would mean two places to keep in step.
    """
    if path.suffix.lower() not in {".xlsx", ".xls"}:
        return path
    import tempfile

    import pandas as pd

    out = Path(tempfile.mkdtemp()) / f"{path.stem}.csv"
    pd.read_excel(path).to_csv(out, index=False)
    return out


def rows_from_file(path: Path) -> list[Row]:
    records, _ = read_chunk(_as_csv(path))
    return [
        Row(r.get("row_id") or str(i + 1), r.get("story_title", ""), r.get("story_summary", ""),
            r.get("owner", ""), r.get("captured_at", ""))
        for i, r in enumerate(records)
    ]


def rows_from_period(period: str) -> list[Row]:
    manifest = load_period(period)
    return [
        Row(r.get("row_id", ""), r.get("story_title", ""), r.get("story_summary", ""),
            r.get("owner", ""), r.get("captured_at", ""))
        for r in manifest["rows"].values()
    ]


def classify_rows(rows: list[Row], extractor: Extractor | None = None) -> list[dict]:
    """Extract, decide, and record how each answer was reached."""
    if extractor is None:
        extractor = Extractor.load()

    out = []
    for row in rows:
        result = extract(row.title, row.summary, extractor)
        fields = to_decision_fields(result)
        event_type = result.fields.get("event_type")

        record = {
            "row_id": row.row_id,
            "story_title": row.title,
            "story_summary": row.summary,
            "owner": row.owner,
            "captured_at": row.captured_at,
            "event_type": event_type or "",
            "escalate": "YES" if result.needs_escalation else "NO",
            "escalation_reasons": "; ".join(result.escalation_reasons),
            "field_provenance": "; ".join(f"{k}={v}" for k, v in sorted(result.provenance.items())),
            "event_type_confidence": result.confidence.get("event_type", ""),
            "industry_relevance": result.fields.get("industry_relevance", "UNKNOWN"),
            "classification": "", "priority": "", "severity": "", "rule_id": "",
            "threshold_met": "", "missing_fields": "", "reroute_to": "",
            "rule_text": "", "source": "", "evidence": "",
        }

        if not event_type:
            # No event type means no rulebook entry applies, so there is nothing to decide. The
            # row is reported as unresolved rather than given a manufactured verdict.
            record["classification"] = "Needs Context Review"
            record["rule_id"] = "NO_EVENT_TYPE"
            record["missing_fields"] = "event_type"
            out.append(record)
            continue

        try:
            decision = registry.decide(event_type, fields)
        except (RuleConflict, ValueError) as exc:
            record["classification"] = "Needs Context Review"
            record["rule_id"] = "UNDECIDABLE"
            record["missing_fields"] = str(exc)[:120]
            record["escalate"] = "YES"
            record["escalation_reasons"] = (
                record["escalation_reasons"] + "; rule could not be applied").strip("; ")
            out.append(record)
            continue

        record.update({
            "classification": decision.classification,
            "rule_id": decision.rule_id,
            "rule_text": decision.rule_text,
            "source": decision.source,
            "threshold_met": "" if decision.threshold_met is None else str(decision.threshold_met),
            "missing_fields": ", ".join(decision.missing_fields),
            "reroute_to": decision.reroute_to or "",
            "severity": decision.severity or "",
            "evidence": " · ".join(decision.evidence),
        })
        try:
            record["priority"] = priority_for(event_type)
        except RuleConflict:
            record["priority"] = ""

        # A row the rules could not resolve is escalated even when extraction was confident —
        # the missing evidence is the reason, and it is named on the row.
        if decision.classification in REVIEW_OUTCOMES:
            record["escalate"] = "YES"
            reason = f"rules need: {', '.join(decision.missing_fields)}"
            record["escalation_reasons"] = "; ".join(
                filter(None, [record["escalation_reasons"], reason]))
        out.append(record)
    return out


def escalation_queue(records: list[dict]) -> list[dict]:
    return [
        {
            "row_id": r["row_id"],
            "story_title": r["story_title"],
            "story_summary": r["story_summary"][:900],
            "escalation_reasons": r["escalation_reasons"],
            "best_guess_event_type": r["event_type"],
            "event_type_confidence": r["event_type_confidence"],
            "industry_relevance": r["industry_relevance"],
            "question_for_review": ESCALATION_QUESTION,
        }
        for r in records if r["escalate"] == "YES"
    ]


def summarise(records: list[dict]) -> dict:
    total = len(records)
    escalated = sum(1 for r in records if r["escalate"] == "YES")
    removed = sum(1 for r in records if r["classification"] == NOT_IMPACTFUL)
    impactful = sum(1 for r in records if r["classification"] == "Impactful")
    review = sum(1 for r in records if r["classification"] in REVIEW_OUTCOMES)
    return {
        "rows": total, "escalated": escalated, "auto_resolved": total - escalated,
        "not_impactful": removed, "impactful": impactful, "review": review,
    }


def blocking_fields(records: list[dict]) -> list[tuple[str, int]]:
    """Which named missing field parked the most rows in review, most-frequent first.

    This is the improvement backlog, read straight off the run: every entry is a field some rule
    asked for and extraction could not supply, so the next extraction pattern to write is the top
    line. It is deliberately per-field rather than per-row — one row blocked on three fields
    counts once against each, because clearing any one of them is separate work.
    """
    tally: dict[str, int] = {}
    for r in records:
        for name in (f.strip() for f in r["missing_fields"].split(",")):
            if name:
                tally[name] = tally.get(name, 0) + 1
    return sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="infile", type=Path)
    ap.add_argument("--period")
    ap.add_argument("--out", type=Path, default=Path("results.csv"))
    ap.add_argument("--escalations", type=Path)
    args = ap.parse_args()

    if not args.infile and not args.period:
        raise SystemExit("ERROR: pass --in <file.csv> or --period <name>")

    rows = rows_from_file(args.infile) if args.infile else rows_from_period(args.period)
    extractor = Extractor.load()
    if extractor is None:
        print("NOTE: no trained model found — running rules and gazetteer only. "
              "More rows will escalate. Train with scripts/train.py.")

    records = classify_rows(rows, extractor)
    write_csv(args.out, records, RESULT_COLUMNS)

    queue = escalation_queue(records)
    if args.escalations:
        write_csv(args.escalations, queue, ESCALATION_COLUMNS)

    s = summarise(records)
    print(f"\n  rows                 {s['rows']}")
    print(f"  resolved with no LLM {s['auto_resolved']} ({s['auto_resolved'] / s['rows']:.1%})")
    print(f"  escalated            {s['escalated']} ({s['escalated'] / s['rows']:.1%})")
    print(f"\n  Impactful            {s['impactful']}")
    print(f"  Not Impactful        {s['not_impactful']}  <- removed from the analyst queue")
    print(f"  needs review         {s['review']}")
    blockers = blocking_fields(records)
    if blockers:
        print("\n  What is parking rows in review (the extraction backlog, biggest first):")
        for name, n in blockers[:12]:
            print(f"    {name:<44}{n:>5}")

    print(f"\n  results     -> {args.out}")
    if args.escalations:
        print(f"  escalations -> {args.escalations}  ({len(queue)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
