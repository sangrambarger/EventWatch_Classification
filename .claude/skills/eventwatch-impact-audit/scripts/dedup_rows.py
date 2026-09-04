#!/usr/bin/env python3
"""Deterministic, mechanical near-duplicate detection — no LLM judgment involved.

The pilot run against real production data found the same underlying event (a factory fire, a
sabotage campaign) fed in as 3-9 near-identical wire-service copies, each an independent row.
Classifying each copy independently both wastes reasoning effort and — worse — risks
inconsistent verdicts across copies of the same fact pattern, which is exactly the kind of
inconsistency this whole audit exists to catch, not reproduce.

This script only clusters rows that are textually near-identical (title + summary token overlap
above a conservative threshold). It never judges relevance or drops a row — every input row ends
up in exactly one cluster, clusters of size 1 are just "no duplicate found." The actual
impactful/not-impactful classification still happens per cluster (via the skill's normal
per-row judgment against references/*.md); this script's only job is to avoid re-doing that
judgment once per wire copy of the same story.

Usage:
    dedup_rows.py records.json --out-representatives dedup_records.json --out-clusters clusters.json

`dedup_records.json` has one record per cluster (the longest-summary member, as the most complete
version of the story) with the same shape as the input, for classification. `clusters.json` maps
each cluster's representative row_index to the full list of row_indices (including itself) that
share that cluster, for run_audit.py's --expand-verdicts step to propagate verdicts back out to
every original row.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

# Tokens too generic to be useful for blocking/similarity (would create enormous false-positive
# clusters if included) — ordinary English stopwords plus a few domain-generic words that show up
# in nearly every EventWatch title regardless of the underlying event.
STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "has", "have", "had", "its", "it", "as", "after",
    "over", "amid", "amid", "into", "new", "update", "report", "reports", "reported", "news",
    "says", "said", "company", "companies", "inc", "corp", "ltd", "co",
}

_WORD_RE = re.compile(r"[a-z0-9]+")

_MONTHS = {
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "january", "february", "march", "april", "june", "july", "august", "september", "october",
    "november", "december",
}


def _is_date_or_number_noise(word: str) -> bool:
    # Auto-generated feed titles (e.g. GDACS hazard-monitoring titles) repeat a
    # "from <date> to <date> UTC" template that, left in, dominates title-similarity scoring with
    # pure boilerplate — two totally different hazards in the same country can look "similar"
    # purely because they share the same date format and UTC timestamp. None of that is a signal
    # of "same underlying event," so strip it before computing similarity.
    if word.isdigit():
        return True
    if word in _MONTHS or word == "utc":
        return True
    return False


def tokenize(text: str) -> set[str]:
    words = _WORD_RE.findall((text or "").lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2 and not _is_date_or_number_noise(w)}


# If a title mentions any of these hazard/event-type words, the two titles being compared must
# share at least one such word to be allowed to merge — this is a hard safety net independent of
# overall token-overlap scoring, specifically to stop "same template, different hazard type"
# titles (e.g. a Forest-Fire auto-alert and an Earthquake auto-alert for the same country, which
# otherwise share heavy date/boilerplate overlap) from merging just because everything else
# around the hazard word matches.
HAZARD_KEYWORDS = {
    "fire", "wildfire", "earthquake", "flood", "flooding", "hurricane", "typhoon", "cyclone",
    "tornado", "volcano", "eruption", "drought", "tsunami", "landslide", "strike", "protest",
    "riot", "bankruptcy", "insolvency", "cyberattack", "ransomware", "breach", "hack", "recall",
    "spill", "explosion", "blast", "shooting", "outage", "blackout", "shutdown", "closure",
    "layoff", "layoffs", "lawsuit", "acquisition", "merger", "spinoff", "sanctions", "tariff",
    "tariffs", "embargo", "coup", "unrest",
}


def hazard_tokens(tokens: set[str]) -> set[str]:
    return tokens & HAZARD_KEYWORDS


# Boilerplate capitalized tokens that recur across many DIFFERENT underlying stories (regulatory
# bodies, wire-service names, generic template words) — these must not count as the "shared
# entity" signal that licenses a merge, or template titles about different companies (e.g. "FDA
# ... Issues Warning Letter to <Company X>" repeated with a different company each time) get
# wrongly merged just because they share the regulatory-body/template wording.
ENTITY_BOILERPLATE = {
    "FDA", "EMA", "OSHA", "MOFCOM", "GDACS", "USGS", "JMA", "OFAC", "CEO", "CFO", "COO",
    "Bloomberg", "Reuters", "AP", "BREAKING", "Center", "Drug", "Evaluation", "Research",
    "Issues", "Issued", "Warning", "Letter", "Letters", "Company", "Companies", "Global",
    "Update", "Report", "Reports", "News", "Says", "Confirms", "Announces", "Announcement",
    # Generic corporate-name suffixes: these combine with a genuinely distinguishing word to
    # form a company name (e.g. "NuScience Peptides" vs "Royal Peptides" vs "Tex Peptides" are
    # three different companies that all end in "Peptides"). Treating the suffix alone as a
    # shared-entity signal causes false merges across unrelated template titles (e.g. a batch of
    # FDA warning letters to different peptide/chemical/pharma companies). The distinguishing
    # word (NuScience/Royal/Tex/...) is what should have to match, not the shared suffix.
    "Peptides", "Pharma", "Pharmaceutical", "Pharmaceuticals", "Chem", "Chemical", "Chemicals",
    "Industries", "International", "Holdings", "Group", "Technologies", "Technology", "Systems",
    "Solutions", "Innovations", "Corp", "Corporation", "LLC", "Inc", "Ltd", "Enterprises",
    "Partners", "Capital", "Motors", "Motor", "Labs", "Laboratories", "Biosciences", "Bio",
    # Generic institutional/template phrases that recur across many different real locations —
    # found via the Riyadh-vs-Rabigh false merge (both described as "<City> Civil Defense
    # extinguishes fire ... Industrial District"); the city name is the actual distinguishing
    # entity, not the agency/facility-type name that happens to also be capitalized.
    "Civil", "Defense", "District", "Industrial", "Brigade", "Department", "Authority", "Agency",
    "Ministry", "Municipality", "Municipal",
}

_ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9&']*\b")


def entity_tokens(text: str) -> set[str]:
    """Capitalized-word candidates for the title's actual subject (company/place/person name),
    excluding common boilerplate that would falsely link different subjects using the same
    template phrasing."""
    found = _ENTITY_RE.findall(text or "")
    return {w for w in found if w not in ENTITY_BOILERPLATE and len(w) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster_records(
    records: list[dict],
    title_thresh: float = 0.55,
    summary_thresh: float = 0.30,
    min_shared_tokens_for_candidacy: int = 2,
) -> list[list[int]]:
    """Returns a list of clusters, each a list of indices into `records`.

    Honest limitation: the entity-overlap gate relies on a hand-curated boilerplate word list
    (ENTITY_BOILERPLATE), which can never fully enumerate every recurring institutional/template
    phrase in arbitrary news text ("Civil Defense", "Industrial District", ...). A document-
    frequency-based (data-driven) version of this gate was tried and rejected: it fragmented the
    genuine 100+-row Uber duplicate cluster (because "Uber" itself is common enough in this
    dataset to look like boilerplate) while still failing to catch the Riyadh/Rabigh case (those
    words are individually rare dataset-wide, just not distinctive of the underlying event). Given
    that a false merge (wrongly propagating one row's verdict onto an unrelated row) is worse than
    an under-merge (a few redundant but individually-correct classifications), this function is
    deliberately biased toward precision over recall — expect it to catch most, not all,
    near-duplicate template stories, and treat every dedup-inherited verdict in the final output
    (tagged "[Deduplicated: ...]" in its rationale) as spot-checkable, not infallible.
    """
    n = len(records)
    title_tokens = [tokenize(r.get("feed_title", "")) for r in records]
    summary_tokens = [tokenize(r.get("story_summary", "")) for r in records]
    title_entities = [entity_tokens(r.get("feed_title", "")) for r in records]

    # Blocking: only compare pairs that share at least `min_shared_tokens_for_candidacy`
    # title tokens, via an inverted index. This avoids an O(n^2) full scan while still finding
    # every genuine near-duplicate (true duplicates share many title tokens by definition).
    token_to_rows: dict[str, list[int]] = defaultdict(list)
    for i, toks in enumerate(title_tokens):
        for t in toks:
            token_to_rows[t].append(i)

    candidate_pairs: set[tuple[int, int]] = set()
    for rows in token_to_rows.values():
        if len(rows) < 2 or len(rows) > 60:
            # A token shared by >60 rows is itself too generic to be a useful signal, and
            # comparing all pairs in a huge block would be wasted work for near-certain non-dupes.
            continue
        for a_idx in range(len(rows)):
            for b_idx in range(a_idx + 1, len(rows)):
                i, j = rows[a_idx], rows[b_idx]
                candidate_pairs.add((i, j) if i < j else (j, i))

    uf = UnionFind(n)
    for i, j in candidate_pairs:
        shared = title_tokens[i] & title_tokens[j]
        if len(shared) < min_shared_tokens_for_candidacy:
            continue
        # Hard gate: the two titles must share at least one non-boilerplate capitalized entity
        # (company/place/person name). Without this, template titles that differ only in the
        # subject entity (e.g. "FDA ... Warning Letter to <Company>" for five different
        # companies) get merged on shared boilerplate wording alone — a false merge that would
        # silently propagate one company's verdict onto an unrelated one.
        ei, ej = title_entities[i], title_entities[j]
        if ei and ej and not (ei & ej):
            continue
        hi, hj = hazard_tokens(title_tokens[i]), hazard_tokens(title_tokens[j])
        if hi and hj and not (hi & hj):
            continue
        # If NEITHER title has any extractable entity token (e.g. both are entity-free generic
        # headlines), fall back to requiring a stronger title/summary match rather than skipping
        # the entity check entirely.
        entity_free = not ei and not ej
        t_sim = jaccard(title_tokens[i], title_tokens[j])
        if t_sim < (title_thresh + 0.15 if entity_free else title_thresh):
            continue
        s_sim = jaccard(summary_tokens[i], summary_tokens[j])
        if s_sim < summary_thresh:
            continue
        uf.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)
    return list(groups.values())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records_json")
    p.add_argument("--out-representatives", default="dedup_records.json")
    p.add_argument("--out-clusters", default="clusters.json")
    p.add_argument("--title-thresh", type=float, default=0.55)
    p.add_argument("--summary-thresh", type=float, default=0.30)
    args = p.parse_args()

    records = json.loads(Path(args.records_json).read_text(encoding="utf-8"))
    clusters = cluster_records(records, args.title_thresh, args.summary_thresh)

    representatives = []
    cluster_map = {}  # representative row_index -> [all row_indices in cluster]
    multi = 0
    for idx_group in clusters:
        # Representative = the member with the longest summary (most complete version of the story).
        rep_i = max(idx_group, key=lambda i: len(records[i].get("story_summary") or ""))
        rep_record = records[rep_i]
        row_indices = [records[i]["row_index"] for i in idx_group]
        cluster_map[str(rep_record["row_index"])] = row_indices
        representatives.append(rep_record)
        if len(idx_group) > 1:
            multi += 1

    Path(args.out_representatives).write_text(json.dumps(representatives, indent=2), encoding="utf-8")
    Path(args.out_clusters).write_text(json.dumps(cluster_map, indent=2), encoding="utf-8")

    total_rows = len(records)
    print(
        f"{total_rows} input rows -> {len(representatives)} unique-event clusters "
        f"({multi} clusters had 2+ duplicate rows; "
        f"{total_rows - len(representatives)} rows will be classified via inherited verdicts)."
    )
    sizes = sorted((len(g) for g in clusters), reverse=True)
    if sizes and sizes[0] > 1:
        print(f"Largest clusters (row counts): {sizes[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
