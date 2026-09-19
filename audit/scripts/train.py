#!/usr/bin/env python3
"""Train the extractor on the teacher-pass labels and report what it can actually do.

The point of this script is the *report*, not the artefact. A trained model with no measured
accuracy is an opinion; this prints held-out precision per field and the coverage/accuracy
tradeoff at each confidence floor, so the decision about how much to automate is made on numbers
rather than on my say-so.

Deliberately reports on a held-out split, never on training data. Deliberately reports the
rules-only baseline alongside the model, so the model has to earn its place rather than be
assumed to help.

Usage:
    train.py --period 2026-09-07            # train, evaluate, save
    train.py --period 2026-09-07 --report   # evaluate only, no save
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extract import industries as ind  # noqa: E402
from extract import rules as rules_mod  # noqa: E402
from extract.model import LEARNED_FIELDS, Extractor, _feature_text, build_pipeline  # noqa: E402
from scripts.ingest import PERIODS_DIR, load_period  # noqa: E402

#: A class with fewer than this many examples cannot be learned or fairly evaluated; those rows
#: are held out of training and reported separately rather than silently inflating accuracy.
MIN_EXAMPLES = 4

#: Kept for reference: the per-field accuracy bar this script used to select floors against.
#: It was abandoned because it optimises the wrong thing -- see the note printed at the end of a
#: run, and DEFAULT_FLOORS in extract/model.py.
ACCURACY_TARGET = 0.95


def load_training_rows(period: str) -> list[dict]:
    manifest = load_period(period)
    teacher = PERIODS_DIR / period / "teacher"
    rows = []
    for path in sorted(teacher.glob("labels_*.json")):
        for label in json.loads(path.read_text()):
            source = manifest["rows"].get(label["key"])
            if not source:
                continue
            rows.append({
                "key": label["key"],
                "title": source.get("story_title", ""),
                "summary": source.get("story_summary", ""),
                "event_type": label.get("event_type") or "(none)",
                "story_nature": (label.get("fields") or {}).get("story_nature", "UNKNOWN"),
                "industry_relevance": (label.get("fields") or {}).get(
                    "industry_relevance", "UNKNOWN"),
            })
    return rows


def split(rows: list[dict], holdout: float = 0.25, seed: int = 20260907):
    """Deterministic split by row key, so a re-run compares like with like."""
    import hashlib

    train, test = [], []
    for r in rows:
        digest = hashlib.sha1(f"{seed}:{r['key']}".encode()).hexdigest()
        (test if int(digest[:8], 16) / 0xFFFFFFFF < holdout else train).append(r)
    return train, test


def train_field(field: str, train_rows: list[dict]):
    counts = Counter(r[field] for r in train_rows)
    usable = {k for k, n in counts.items() if n >= MIN_EXAMPLES}
    rows = [r for r in train_rows if r[field] in usable]
    if len({r[field] for r in rows}) < 2:
        return None, counts, usable
    pipeline = build_pipeline()
    pipeline.fit([_feature_text(r["title"], r["summary"]) for r in rows],
                 [r[field] for r in rows])
    return pipeline, counts, usable


def rules_baseline(field: str, row: dict) -> str:
    """What the deterministic layer alone would say — the bar the model must clear."""
    if field == "industry_relevance":
        return ind.industry_relevance(row["title"], row["summary"])[0]
    if field == "story_nature":
        return rules_mod.story_nature_signal(f"{row['title']}. {row['summary']}") or "UNKNOWN"
    return "UNKNOWN"


def evaluate(extractor: Extractor, test_rows: list[dict], usable: dict) -> dict:
    report = {}
    for field in LEARNED_FIELDS:
        rows = [r for r in test_rows if r[field] in usable[field]]
        if not rows:
            report[field] = {"n": 0}
            continue

        preds = [extractor.predict_field(field, _feature_text(r["title"], r["summary"]))
                 for r in rows]
        truths = [r[field] for r in rows]

        correct_all = sum(p.value == t for p, t in zip(preds, truths))
        accepted = [(p, t) for p, t in zip(preds, truths) if p.accepted]
        correct_acc = sum(p.value == t for p, t in accepted)

        # Coverage/accuracy curve: what you buy at each floor.
        curve = []
        for floor in (0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80):
            kept = [(p, t) for p, t in zip(preds, truths) if p.confidence >= floor]
            if not kept:
                continue
            curve.append({
                "floor": floor,
                "coverage": round(len(kept) / len(rows), 3),
                "accuracy": round(sum(p.value == t for p, t in kept) / len(kept), 3),
            })

        base = [rules_baseline(field, r) for r in rows]
        base_answered = [(b, t) for b, t in zip(base, truths) if b != "UNKNOWN"]

        report[field] = {
            "n": len(rows),
            "classes": len(usable[field]),
            "accuracy_all": round(correct_all / len(rows), 3),
            "accepted": len(accepted),
            "coverage_at_floor": round(len(accepted) / len(rows), 3),
            "accuracy_at_floor": round(correct_acc / len(accepted), 3) if accepted else None,
            "floor": extractor.floors[field],
            "curve": curve,
            "rules_only_coverage": round(len(base_answered) / len(rows), 3),
            "rules_only_accuracy": (
                round(sum(b == t for b, t in base_answered) / len(base_answered), 3)
                if base_answered else None
            ),
        }
    return report


def render(report: dict, train_n: int, test_n: int, skipped: dict) -> None:
    print(f"\n  Extractor training report")
    print(f"  {'=' * 68}")
    print(f"  train rows {train_n} · held-out rows {test_n}\n")
    for field, r in report.items():
        if not r.get("n"):
            print(f"  {field}: no evaluable rows")
            continue
        print(f"  {field}  ({r['classes']} classes, {r['n']} held-out rows)")
        print(f"    accuracy, every row                {r['accuracy_all']:.1%}")
        print(f"    at floor {r['floor']:.2f}: covers {r['coverage_at_floor']:.1%} "
              f"at {r['accuracy_at_floor']:.1%} accuracy"
              if r["accuracy_at_floor"] is not None else "    nothing clears the floor")
        if r["rules_only_accuracy"] is not None:
            print(f"    rules alone: covers {r['rules_only_coverage']:.1%} "
                  f"at {r['rules_only_accuracy']:.1%} accuracy   <- the bar to beat")
        print("    coverage / accuracy by floor:")
        for c in r["curve"]:
            print(f"      {c['floor']:.2f}   {c['coverage']:>6.1%}   {c['accuracy']:>6.1%}")
        if skipped.get(field):
            print(f"    classes too rare to learn (<{MIN_EXAMPLES} examples): "
                  f"{len(skipped[field])}")
        print()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--period", required=True)
    p.add_argument("--report", action="store_true", help="evaluate only, do not save the model")
    p.add_argument("--holdout", type=float, default=0.25)
    args = p.parse_args()

    rows = load_training_rows(args.period)
    if not rows:
        raise SystemExit("ERROR: no teacher labels found. Run the teacher pass first.")
    train_rows, test_rows = split(rows, args.holdout)

    models, usable, skipped = {}, {}, {}
    for field in LEARNED_FIELDS:
        model, counts, keep = train_field(field, train_rows)
        if model is None:
            print(f"skipping {field}: not enough labelled variety")
            usable[field] = set()
            continue
        models[field] = model
        usable[field] = keep
        skipped[field] = {k for k in counts if k not in keep}

    extractor = Extractor(models)
    report = evaluate(extractor, test_rows, usable)
    print("  floors come from DEFAULT_FLOORS in extract/model.py, chosen by sweeping the")
    print("  END-TO-END objective in scripts/evaluate_pipeline.py -- not from the per-field")
    print("  curve below, which is reported for information only. Per-field accuracy is a")
    print("  proxy: a floor that maximises it starved the connection cascade and parked")
    print("  reportable rows in review. Re-sweep end-to-end after retraining.")
    render(report, len(train_rows), len(test_rows), skipped)

    out = PERIODS_DIR / args.period / "training_report.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"  report written to {out}")

    if not args.report:
        extractor.save()
        from extract.model import MODEL_PATH
        print(f"  model saved to {MODEL_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
