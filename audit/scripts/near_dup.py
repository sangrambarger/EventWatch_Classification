#!/usr/bin/env python3
"""Stage 0b: near-duplicate **candidate** detection. Never merges.

Exact duplicates are rare in real feed data (zero in the 2026-09-07 shift), so near-duplicate
grouping is the whole deduplication story — the Amazon cargo-crash wire copies were ~17 rows of
one event in a 216-row sample.

This groups rows that are *probably* the same underlying occurrence and assigns a confidence and
a reason. It does **not** merge them: per the audit spec, a near-duplicate is a candidate for
human confirmation, and the decision field takes Same Event / Likely Same Event / Different Event
/ Unclear. Auto-merging is how two genuinely different subjects get one verdict — the documented
false-merge case being a templated headline ("FDA Warning Letter to <Company>") sent to five
different manufacturers.

The scoring is deliberately biased toward under-merging: it requires agreement on distinctive
tokens, not just surface similarity, and it strips the date/number boilerplate that makes
auto-generated hazard feeds look alike regardless of subject.

Usage:
    near_dup.py --period 2026-09-07 [--out near_dup_groups.json] [--show 10]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.ingest import PERIODS_DIR, load_period  # noqa: E402

STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "has", "have", "had", "its", "it", "as", "after",
    "over", "amid", "into", "new", "update", "report", "reports", "reported", "news", "says",
    "said", "company", "companies", "inc", "corp", "ltd", "co", "plc", "group", "s", "will",
    "more", "than", "that", "this", "their", "his", "her", "they", "we", "us", "you", "but",
    "not", "no", "all", "some", "may", "could", "can", "up", "down", "out", "about", "near",
    "live", "now", "what", "how", "why", "who", "when", "latest", "video",
}

MONTHS = {
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "january", "february", "march", "april", "june", "july", "august", "september", "october",
    "november", "december", "utc", "gmt", "edt", "est", "pst",
}

_WORD = re.compile(r"[a-z0-9]+")

#: Similarity at or above this is a candidate at all.
CANDIDATE_FLOOR = 0.34
#: Mean intra-group similarity at or above this is called Same Event; above LIKELY_SAME it is a
#: Likely Same Event awaiting human confirmation.
SAME_EVENT = 0.62
LIKELY_SAME = 0.44
#: Pair similarity needed to actually link two rows into one group.
LINK_THRESHOLD = 0.46


def tokens(text: str) -> set[str]:
    out = set()
    for word in _WORD.findall(text.lower()):
        if word in STOPWORDS or word in MONTHS:
            continue
        if word.isdigit():
            continue  # dates and counts dominate auto-generated feed titles
        if len(word) < 3:
            continue
        out.add(word)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def weighted_overlap(a: set[str], b: set[str], idf: dict[str, float]) -> float:
    """IDF-weighted containment, symmetrised.

    Plain Jaccard treats every shared word alike, so two wire copies of one crash score no higher
    than two unrelated stories that share "plant" and "fire". Weighting by inverse document
    frequency fixes that without a hand-tuned "rare word" cutoff: a token shared by 20 of 1,079
    rows still carries far more weight than one shared by 400, which a binary threshold would
    throw away. That cutoff was the first version's bug -- it found 2 groups where the true answer
    was dozens, because `amazon` and `miami` were common enough to be discarded as unremarkable.
    """
    if not a or not b:
        return 0.0
    shared = sum(idf.get(w, 1.0) for w in a & b)
    return shared / min(
        sum(idf.get(w, 1.0) for w in a),
        sum(idf.get(w, 1.0) for w in b),
    )


def build_groups(manifest: dict) -> dict:
    rows = manifest["rows"]
    toks = {k: tokens(r["normalised_title"]) for k, r in rows.items()}
    summ = {k: tokens(r.get("story_summary", "")[:400]) for k, r in rows.items()}

    # Document frequency -> IDF, so a shared distinctive token outweighs a shared common one.
    df: dict[str, int] = defaultdict(int)
    for t in toks.values():
        for w in t:
            df[w] += 1
    total = max(len(rows), 1)
    idf = {w: math.log(total / n) for w, n in df.items()}
    #: Still used for the human-readable reason, not for the decision itself.
    distinctive = {w for w, n in df.items() if n <= max(3, total // 50)}

    # Block on shared tokens so this stays near-linear rather than quadratic over 500k rows.
    blocks: dict[str, list[str]] = defaultdict(list)
    for key, t in toks.items():
        for w in sorted(t, key=lambda w: df[w])[:4]:  # the 4 rarest tokens in the title
            blocks[w].append(key)

    parent: dict[str, str] = {k: k for k in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    reasons: dict[tuple[str, str], tuple[float, str]] = {}
    seen: set[tuple[str, str]] = set()
    for members in blocks.values():
        if len(members) > 60:
            continue  # a token this common is not evidence of a shared event
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                pair = (a, b) if a < b else (b, a)
                if pair in seen:
                    continue
                seen.add(pair)
                title_sim = weighted_overlap(toks[a], toks[b], idf)
                if title_sim < CANDIDATE_FLOOR:
                    continue
                summary_sim = weighted_overlap(summ[a], summ[b], idf)
                shared_distinctive = (toks[a] & toks[b]) & distinctive
                score = 0.75 * title_sim + 0.25 * summary_sim
                if score < CANDIDATE_FLOOR:
                    continue
                reasons[pair] = (
                    score,
                    f"title {title_sim:.2f}, summary {summary_sim:.2f}"
                    + (f", shared distinctive terms: "
                       f"{', '.join(sorted(shared_distinctive, key=lambda w: -idf[w])[:5])}"
                       if shared_distinctive else ", no distinctive term in common"),
                )
                if score >= LINK_THRESHOLD:
                    union(a, b)

    clusters: dict[str, list[str]] = defaultdict(list)
    for key in rows:
        clusters[find(key)].append(key)

    groups = []
    for gid, (root, members) in enumerate(
        sorted((c for c in clusters.items() if len(c[1]) > 1), key=lambda c: -len(c[1])), start=1
    ):
        pair_scores = [
            reasons[(a, b) if a < b else (b, a)][0]
            for i, a in enumerate(members) for b in members[i + 1:]
            if ((a, b) if a < b else (b, a)) in reasons
        ]
        best = max(pair_scores) if pair_scores else 0.0
        mean = sum(pair_scores) / len(pair_scores) if pair_scores else 0.0
        if mean >= SAME_EVENT:
            decision, confirm = "Same Event", "NO"
        elif mean >= LIKELY_SAME:
            decision, confirm = "Likely Same Event", "YES"
        else:
            decision, confirm = "Unclear", "YES"
        sample_pair = next(
            (reasons[(a, b) if a < b else (b, a)][1]
             for i, a in enumerate(members) for b in members[i + 1:]
             if ((a, b) if a < b else (b, a)) in reasons), "")
        groups.append({
            "group_id": f"ND-{gid:04d}",
            "size": len(members),
            "members": members,
            "titles": [rows[k]["story_title"] for k in members],
            "decision": decision,
            "confidence": round(mean, 3),
            "best_pair": round(best, 3),
            "reason": sample_pair,
            "human_confirmation_required": confirm,
        })
    return {"period": manifest["period"], "groups": groups}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--period", required=True)
    p.add_argument("--out", default="near_dup_groups.json")
    p.add_argument("--show", type=int, default=5)
    args = p.parse_args()

    manifest = load_period(args.period)
    result = build_groups(manifest)
    out = PERIODS_DIR / args.period / args.out
    out.write_text(json.dumps(result, indent=1))

    groups = result["groups"]
    grouped_rows = sum(g["size"] for g in groups)
    total = len(manifest["rows"])
    print(f"rows                       {total}")
    print(f"near-duplicate groups      {len(groups)}")
    print(f"rows inside a group        {grouped_rows}")
    print(f"rows removable if merged   {grouped_rows - len(groups)} "
          f"({(grouped_rows - len(groups)) / total:.1%} of the period)")
    print(f"  of which auto-confirmed  "
          f"{sum(g['size'] - 1 for g in groups if g['human_confirmation_required'] == 'NO')}")
    print(f"  awaiting human decision  "
          f"{sum(g['size'] - 1 for g in groups if g['human_confirmation_required'] == 'YES')}")
    print(f"written to                 {out}")
    for g in groups[:args.show]:
        print(f"\n{g['group_id']}  size {g['size']}  {g['decision']} "
              f"(conf {g['confidence']})  [{g['reason']}]")
        for t in g["titles"][:4]:
            print(f"    - {t[:104]}")
        if g["size"] > 4:
            print(f"    ... {g['size'] - 4} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
