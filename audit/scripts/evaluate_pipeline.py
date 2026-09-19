#!/usr/bin/env python3
"""Measure the zero-LLM pipeline against the teacher labels it was trained from.

The headline question this answers: **of N rows uploaded, how many get a verdict with no model
API call at all, and how often does that verdict match what the LLM said?**

The comparison is deliberately end-to-end — extracted fields fed through `logic/` to a final
classification — rather than field-by-field. Field accuracy flatters the pipeline: several fields
never change the verdict for a given row, so getting them wrong costs nothing, while one wrong
`event_type` routes to a different rulebook entry entirely. Only the verdict matters.

The teacher labels are the yardstick, not truth. They are one careful LLM pass, they carry their
own errors, and rows where the two disagree are as likely to be a teacher mistake as a pipeline
one. Treat the agreement rate as "does the cheap path reproduce the expensive path", which is the
real question, not as accuracy against ground truth.

Usage:
    evaluate_pipeline.py --period 2026-09-07 [--sample 20]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extract.model import Extractor  # noqa: E402
from extract.pipeline import extract, to_decision_fields  # noqa: E402
from logic import registry  # noqa: E402
from logic.base import IMPACTFUL, NOT_IMPACTFUL, REVIEW_OUTCOMES, RuleConflict  # noqa: E402
from scripts.ingest import PERIODS_DIR, load_period  # noqa: E402


def decide(event_type: str | None, fields: dict) -> str:
    if not event_type or event_type == "(none)":
        return "(no event type)"
    try:
        return registry.decide(event_type, fields).classification
    except (RuleConflict, ValueError):
        return "(undecidable)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", required=True)
    ap.add_argument("--sample", type=int, default=12, help="disagreements to print")
    args = ap.parse_args()

    manifest = load_period(args.period)
    teacher = PERIODS_DIR / args.period / "teacher"
    labels = {}
    for path in sorted(teacher.glob("labels_*.json")):
        for row in json.loads(path.read_text()):
            labels[row["key"]] = row

    extractor = Extractor.load()
    if extractor is None:
        raise SystemExit("ERROR: no trained model. Run scripts/train.py first.")

    agree = 0
    escalated = 0
    both_removed = 0
    confusion: Counter = Counter()
    provenance_counts: Counter = Counter()
    escalation_reasons: Counter = Counter()
    disagreements = []

    for key, label in labels.items():
        source = manifest["rows"].get(key)
        if not source:
            continue
        title = source.get("story_title", "")
        summary = source.get("story_summary", "")

        result = extract(title, summary, extractor)
        for f, p in result.provenance.items():
            provenance_counts[p.split(":")[0].split(" p=")[0]] += 1

        ours = decide(result.fields.get("event_type"), to_decision_fields(result))
        theirs = decide(label.get("event_type"), label.get("fields") or {})

        if result.needs_escalation:
            escalated += 1
            for r in result.escalation_reasons:
                escalation_reasons[r] += 1

        confusion[(theirs, ours)] += 1
        if ours == theirs:
            agree += 1
        else:
            disagreements.append((title[:88], theirs, ours,
                                  result.fields.get("event_type"), label.get("event_type")))

        # The funnel's actual question: does the cheap path remove the same rows?
        if ours == NOT_IMPACTFUL and theirs == NOT_IMPACTFUL:
            both_removed += 1

    total = sum(confusion.values())
    auto = total - escalated

    print(f"\n  Zero-LLM pipeline vs the teacher pass — period {args.period}")
    print(f"  {'=' * 70}")
    print(f"  rows compared                    {total}")
    print(f"  decided with NO model call       {auto} ({auto / total:.1%})")
    print(f"  escalated (needs LLM or human)   {escalated} ({escalated / total:.1%})")
    print(f"  verdict agrees with teacher      {agree} ({agree / total:.1%})")

    teacher_removed = sum(n for (t, _), n in confusion.items() if t == NOT_IMPACTFUL)
    ours_removed = sum(n for (_, o), n in confusion.items() if o == NOT_IMPACTFUL)
    print(f"\n  rows the teacher removed         {teacher_removed}")
    print(f"  rows the pipeline removes        {ours_removed}")
    print(f"  removed by both (safe savings)   {both_removed}")
    if teacher_removed:
        print(f"  recall on removals               {both_removed / teacher_removed:.1%}")
    if ours_removed:
        over = ours_removed - both_removed
        print(f"  removed by pipeline only         {over}"
              f"  <- the risk number: rows dropped the teacher kept")

    print("\n  Where each field came from:")
    for source, n in provenance_counts.most_common():
        print(f"    {source:<22}{n:>6}")

    if escalation_reasons:
        print("\n  Why rows escalate:")
        for reason, n in escalation_reasons.most_common():
            print(f"    {reason:<36}{n:>5}")

    print("\n  Verdict confusion (teacher -> pipeline):")
    for (t, o), n in confusion.most_common(12):
        mark = "  " if t == o else " *"
        print(f"   {mark} {t:<22} -> {o:<22}{n:>5}")

    if disagreements:
        print(f"\n  Sample disagreements ({min(args.sample, len(disagreements))} of "
              f"{len(disagreements)}):")
        for title, t, o, ours_type, their_type in disagreements[:args.sample]:
            print(f"    teacher {t:<20} pipeline {o:<20}")
            print(f"      type: {their_type} -> {ours_type}")
            print(f"      {title}")

    out = PERIODS_DIR / args.period / "pipeline_evaluation.json"
    out.write_text(json.dumps({
        "rows": total, "auto_decided": auto, "escalated": escalated, "agree": agree,
        "agreement_rate": round(agree / total, 4) if total else None,
        "teacher_removed": teacher_removed, "pipeline_removed": ours_removed,
        "removed_by_both": both_removed,
        "escalation_reasons": dict(escalation_reasons),
    }, indent=1))
    print(f"\n  written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
