#!/usr/bin/env python3
"""Apply the decision logic to teacher-pass labels and print the workload-reduction funnel.

This is the deliverable the whole project points at: of N raw rows, how many are removed at each
stage, and at what risk. Every stage reports rows removed, % of raw, % of what reached it — and
the number that decides whether the stage can be trusted at all.

Two disciplines the numbers depend on:

**Only `Not Impactful` removes a row from the analyst queue.** `Impactful` means a bulletin is
owed and a review outcome means a human is owed; counting either as a saving is how a reduction
funnel starts lying. `Decision.removes_from_queue` enforces that.

**The stage counts must sum to the raw row count.** A row is removed exactly once, at the first
stage that removes it, and everything else lands in the residual queue. `--check` asserts this;
a funnel whose arithmetic does not close is reporting a bug, not a saving.

Usage:
    funnel.py --period 2026-09-07 [--json out.json] [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logic import registry  # noqa: E402
from logic.base import (  # noqa: E402
    IMPACTFUL,
    NOT_IMPACTFUL,
    REVIEW_OUTCOMES,
    RuleConflict,
    priority_for,
)
from scripts.ingest import PERIODS_DIR, exact_duplicate_groups, load_period  # noqa: E402

#: `story_nature` values the global gate removes as never-a-candidate. Tracked separately from
#: threshold rejections because `global-rules.md` #9 is explicit that "this was never a candidate
#: event" must not count toward overturn statistics the same way a real event below its bar does.
GATE_NATURES = {
    "ORGANIC_EXPANSION_OR_INVESTMENT",
    "RESUMPTION_OR_ALL_CLEAR_ONLY",
    "MARKET_COMMENTARY_NO_PHYSICAL_EVENT",
    "ENFORCEMENT_AGAINST_ILLICIT_ACTOR",
    "RECYCLED_REMINDER_OF_KNOWN_DEVELOPMENT",
}


def load_labels(period: str) -> dict[str, dict]:
    teacher = PERIODS_DIR / period / "teacher"
    labels: dict[str, dict] = {}
    files = sorted(teacher.glob("labels_*.json"))
    if not files:
        raise SystemExit(f"ERROR: no labels_*.json in {teacher}. Run the teacher pass first.")
    for path in files:
        for row in json.loads(path.read_text()):
            labels[row["key"]] = row
    return labels


def decide_all(manifest: dict, labels: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, row in manifest["rows"].items():
        label = labels.get(key)
        if label is None:
            out[key] = {"stage": "unlabelled", "row": row}
            continue
        event_type = label.get("event_type")
        fields = label.get("fields") or {}
        record = {
            "row": row, "event_type": event_type, "fields": fields,
            "event_type_reason": label.get("event_type_reason", ""),
        }
        if not event_type:
            # No event type at all. The global gate still gets to remove obvious non-events.
            nature = fields.get("story_nature", "UNKNOWN")
            record["stage"] = "no_event_type"
            record["classification"] = (
                NOT_IMPACTFUL if nature in GATE_NATURES else "Needs Context Review"
            )
            record["rule_id"] = "GATE" if nature in GATE_NATURES else "NO_EVENT_TYPE"
            out[key] = record
            continue
        try:
            decision = registry.decide(event_type, fields)
        except RuleConflict as exc:
            record["stage"] = "rule_conflict"
            record["classification"] = "Needs Context Review"
            record["rule_id"] = "RULE_CONFLICT"
            record["error"] = str(exc)[:160]
            out[key] = record
            continue
        except ValueError as exc:
            # A label used a value outside the module's schema — an extraction fault, not a
            # decision. Surfaced rather than swallowed, because silently coercing it would make
            # the funnel look cleaner than the data is.
            record["stage"] = "invalid_label"
            record["classification"] = "Needs Context Review"
            record["rule_id"] = "INVALID_LABEL"
            record["error"] = str(exc)[:160]
            out[key] = record
            continue
        record["stage"] = "decided"
        record["classification"] = decision.classification
        record["rule_id"] = decision.rule_id
        record["rule_text"] = decision.rule_text
        record["source"] = decision.source
        record["threshold_met"] = decision.threshold_met
        record["missing_fields"] = list(decision.missing_fields)
        record["reroute_to"] = decision.reroute_to
        record["severity"] = decision.severity
        record["warroom_eligible"] = decision.warroom_eligible
        record["removes_from_queue"] = decision.removes_from_queue
        record["evidence"] = list(decision.evidence)
        record["notes"] = list(decision.notes)
        try:
            record["priority"] = priority_for(event_type)
        except RuleConflict:
            record["priority"] = None
        out[key] = record
    return out


def build_funnel(manifest: dict, decisions: dict[str, dict], near_dup: dict) -> dict:
    total = len(manifest["rows"])

    exact_groups = exact_duplicate_groups(manifest)
    exact_removable = sum(len(v) - 1 for v in exact_groups.values() if len(v) > 1)

    nd_groups = near_dup.get("groups", [])
    nd_rows = sum(g["size"] for g in nd_groups)
    nd_removable = nd_rows - len(nd_groups) if nd_groups else 0
    nd_confirmed = sum(g["size"] - 1 for g in nd_groups
                       if g["human_confirmation_required"] == "NO")

    gate_removed = [
        k for k, d in decisions.items()
        if d.get("classification") == NOT_IMPACTFUL
        and (d.get("rule_id", "").startswith("GLOBAL") or d.get("rule_id") == "GATE")
    ]
    threshold_removed = [
        k for k, d in decisions.items()
        if d.get("classification") == NOT_IMPACTFUL and k not in set(gate_removed)
    ]
    impactful = [k for k, d in decisions.items() if d.get("classification") == IMPACTFUL]
    review = [k for k, d in decisions.items()
              if d.get("classification") in REVIEW_OUTCOMES]

    by_type = Counter(d.get("event_type") or "(none)" for d in decisions.values())
    by_outcome_and_type: dict[str, Counter] = defaultdict(Counter)
    for d in decisions.values():
        by_outcome_and_type[d.get("event_type") or "(none)"][d.get("classification")] += 1

    removal_rules = Counter(
        d.get("rule_id") for d in decisions.values()
        if d.get("classification") == NOT_IMPACTFUL
    )
    missing_field_counts = Counter(
        f for d in decisions.values() for f in d.get("missing_fields", [])
    )

    return {
        "period": manifest["period"],
        "raw_rows": total,
        "stages": [
            {"stage": "0  exact duplicates", "removable": exact_removable,
             "note": "deterministic, zero risk"},
            {"stage": "0b near-duplicate groups", "removable": nd_removable,
             "auto_confirmed": nd_confirmed,
             "note": "candidates only — never auto-merged"},
            {"stage": "1  not a candidate event (global gate)", "removed": len(gate_removed),
             "note": "global-rules #8/#9/#12/#16 — never-a-candidate, not a missed bar"},
            {"stage": "2  below the event type's own threshold", "removed": len(threshold_removed),
             "note": "a real event that does not clear its bar"},
        ],
        "residual": {
            "impactful": len(impactful),
            "review_queue": len(review),
            "total": len(impactful) + len(review),
        },
        "by_event_type": dict(by_type.most_common()),
        "outcome_by_event_type": {k: dict(v) for k, v in by_outcome_and_type.items()},
        "top_removal_rules": dict(removal_rules.most_common(15)),
        "top_missing_fields": dict(missing_field_counts.most_common(15)),
        "unlabelled": sum(1 for d in decisions.values() if d.get("stage") == "unlabelled"),
        "invalid_labels": sum(1 for d in decisions.values() if d.get("stage") == "invalid_label"),
        "rule_conflicts": sum(1 for d in decisions.values() if d.get("stage") == "rule_conflict"),
    }


def render(f: dict) -> None:
    total = f["raw_rows"]

    def pct(n):
        return f"{n / total:6.1%}" if total else "   n/a"

    print(f"\n  EventWatch workload-reduction funnel — period {f['period']}")
    print(f"  {'=' * 66}")
    print(f"  Raw rows uploaded{'':>31}{total:>7}")
    for s in f["stages"]:
        n = s.get("removed", s.get("removable", 0))
        label = "removed" if "removed" in s else "removable"
        print(f"    {s['stage']:<44}{n:>6}  {pct(n)}  ({label})")
        print(f"      {s['note']}")
    r = f["residual"]
    print(f"  {'-' * 66}")
    print(f"  Residual analyst queue{'':>26}{r['total']:>7}  {pct(r['total'])}")
    print(f"      bulletin owed (Impactful){'':>20}{r['impactful']:>6}  {pct(r['impactful'])}")
    print(f"      human owed (review queue){'':>20}{r['review_queue']:>6}  {pct(r['review_queue'])}")

    if f["unlabelled"] or f["invalid_labels"] or f["rule_conflicts"]:
        print(f"\n  data quality: {f['unlabelled']} unlabelled, "
              f"{f['invalid_labels']} invalid labels, {f['rule_conflicts']} rule conflicts")

    print("\n  Rules doing the removing:")
    for rule, n in list(f["top_removal_rules"].items())[:10]:
        print(f"    {rule:<22}{n:>5}")
    print("\n  Evidence most often missing (drives the review queue):")
    for field, n in list(f["top_missing_fields"].items())[:8]:
        print(f"    {field:<44}{n:>5}")
    print("\n  Event types by volume:")
    for et, n in list(f["by_event_type"].items())[:12]:
        outcomes = f["outcome_by_event_type"].get(et, {})
        ni = outcomes.get(NOT_IMPACTFUL, 0)
        print(f"    {et[:44]:<46}{n:>5}   removed {ni:>4} ({ni / n:.0%})" if n else "")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--period", required=True)
    p.add_argument("--json", type=Path)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()

    manifest = load_period(args.period)
    labels = load_labels(args.period)
    nd_path = PERIODS_DIR / args.period / "near_dup_groups.json"
    near_dup = json.loads(nd_path.read_text()) if nd_path.exists() else {}

    decisions = decide_all(manifest, labels)
    funnel = build_funnel(manifest, decisions, near_dup)

    (PERIODS_DIR / args.period / "decisions.json").write_text(json.dumps(decisions, indent=1))
    render(funnel)

    if args.json:
        args.json.write_text(json.dumps(funnel, indent=1))
    (PERIODS_DIR / args.period / "funnel.json").write_text(json.dumps(funnel, indent=1))

    if args.check:
        gate = funnel["stages"][2]["removed"]
        thresh = funnel["stages"][3]["removed"]
        residual = funnel["residual"]["total"]
        accounted = gate + thresh + residual
        if accounted != funnel["raw_rows"]:
            print(f"\nFAIL: stages sum to {accounted}, raw rows are {funnel['raw_rows']}")
            return 1
        print(f"\nOK: {gate} + {thresh} + {residual} = {funnel['raw_rows']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
