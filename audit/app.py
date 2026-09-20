"""EventWatch workload-reduction audit dashboard.

Upload one or more feed chunks, run the pipeline in-process, and read where the analyst queue
actually goes. No API key, no network call: dedup and every threshold decision are deterministic
Python, and the only step that ever read prose (the teacher pass) has already run and is loaded
from disk.

Three disciplines this app holds to, because each is a way a reduction funnel starts lying:

1. **Only `Not Impactful` is a saving.** Impactful means a bulletin is owed; a review outcome
   means a human is owed. Neither is removed work, and neither is counted as such.
2. **Every percentage shows its denominator.** `n / N` on the face of the number, not in a
   caption. Unresolved rows are excluded from accuracy figures and that exclusion is stated.
3. **A number nobody can drill into is not evidence.** Every figure here has a table behind it,
   and every decision carries the verbatim source line it fired on.

Run:  streamlit run audit/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

AUDIT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AUDIT_DIR))

from logic import registry  # noqa: E402
from logic.base import IMPACTFUL, NOT_IMPACTFUL, REVIEW_OUTCOMES, RuleConflict  # noqa: E402
from scripts import funnel as funnel_mod  # noqa: E402
from scripts import ingest as ingest_mod  # noqa: E402
from scripts import near_dup as near_dup_mod  # noqa: E402
from theme import OUTCOME_ORDER, plotly_layout, tokens  # noqa: E402

st.set_page_config(page_title="EventWatch Audit", page_icon="📉", layout="wide")


# ---------------------------------------------------------------- data loading

@st.cache_data(show_spinner=False)
def available_periods() -> list[str]:
    if not ingest_mod.PERIODS_DIR.exists():
        return []
    return sorted(p.name for p in ingest_mod.PERIODS_DIR.iterdir() if p.is_dir())


@st.cache_data(show_spinner="Deciding every row…")
def load_period_frame(period: str, _stamp: float) -> tuple[pd.DataFrame, dict, dict]:
    """Return one frame every page filters, plus the funnel and near-duplicate results.

    One frame, one source of truth — the pages cannot disagree with each other because there is
    nothing for them to disagree about.
    """
    manifest = ingest_mod.load_period(period)
    try:
        labels = funnel_mod.load_labels(period)
    except SystemExit:
        labels = {}
    decisions = funnel_mod.decide_all(manifest, labels) if labels else {}

    nd_path = ingest_mod.PERIODS_DIR / period / "near_dup_groups.json"
    near_dup = json.loads(nd_path.read_text()) if nd_path.exists() else {"groups": []}

    group_of: dict[str, str] = {}
    for g in near_dup.get("groups", []):
        for key in g["members"]:
            group_of[key] = g["group_id"]

    rows = []
    for key, row in manifest["rows"].items():
        d = decisions.get(key, {})
        rows.append({
            "key": key,
            "row_id": row.get("row_id"),
            "title": row.get("story_title", ""),
            "summary": row.get("story_summary", ""),
            "cluster_title": row.get("cluster_title", ""),
            "owner": row.get("owner", ""),
            "captured_at": row.get("captured_at", ""),
            "system_class": row.get("system_event_classification", ""),
            "near_dup_group": group_of.get(key, ""),
            "event_type": d.get("event_type") or "(none)",
            "classification": d.get("classification", "(unlabelled)"),
            "rule_id": d.get("rule_id", ""),
            "rule_text": d.get("rule_text", ""),
            "source": d.get("source", ""),
            "priority": d.get("priority") or "",
            "severity": d.get("severity") or "",
            "missing_fields": ", ".join(d.get("missing_fields", [])),
            "reroute_to": d.get("reroute_to") or "",
            "evidence": " · ".join(d.get("evidence", [])),
            "stage": d.get("stage", "unlabelled"),
        })
    frame = pd.DataFrame(rows)
    fun = funnel_mod.build_funnel(manifest, decisions, near_dup) if decisions else {}
    return frame, fun, near_dup


def period_stamp(period: str) -> float:
    """Cache key that changes when any input file changes."""
    base = ingest_mod.PERIODS_DIR / period
    return max((p.stat().st_mtime for p in base.rglob("*.json")), default=0.0)


# ---------------------------------------------------------------- helpers

def pct(n: int, total: int) -> str:
    """Always `n / N (x%)`. A bare percentage hides how many rows it rests on."""
    if not total:
        return f"{n} / 0"
    return f"{n} / {total}  ({n / total:.1%})"


def outcome_bar(counts: dict, tok: dict, dark: bool, title: str) -> go.Figure:
    labels = [o for o in OUTCOME_ORDER if counts.get(o)]
    values = [counts[o] for o in labels]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker={"color": [tok["outcome"][o] for o in labels],
                "line": {"width": 2, "color": tok["ink"]["surface"]}},
        text=[str(v) for v in values], textposition="outside",
        textfont={"color": tok["ink"]["primary"]},
        hovertemplate="%{y}: %{x} rows<extra></extra>",
        width=0.55,
    ))
    fig.update_layout(**plotly_layout(dark), title=title, showlegend=False,
                      height=60 + 44 * len(labels))
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


def table_of(frame: pd.DataFrame, columns: list[str]) -> None:
    st.dataframe(frame[columns], width='stretch', hide_index=True)


# ---------------------------------------------------------------- upload page

UPLOAD_PAGE = "0 · Classify an upload"


def render_upload_page(tok: dict, dark: bool) -> None:
    """Upload a feed file, classify it here, download the results and the escalation queue.

    This is the whole product in one screen: a file in, a verdict per row out, no API key and no
    network call. It deliberately does **not** write into the period store — a classification run
    is a read of a file, and mixing it with ingestion would let an ad-hoc upload silently move the
    audited denominators on every other page.
    """
    st.title("Classify an upload")
    st.caption(
        "Runs the same code path as `scripts/classify.py`, in this process. No API key, no "
        "network call: extraction is patterns plus a local model, and every threshold decision "
        "is deterministic Python."
    )

    upload = st.file_uploader("Feed export (.csv or .xlsx)", type=["csv", "xlsx", "xls"])
    if upload is None:
        st.info(
            "The file needs a story-title column; everything else is matched by alias "
            "(`Story Title`, `Summary`, `Owner`, `RowID`, capture timestamp). A column that is "
            "not found is left empty rather than guessed at."
        )
        return

    import tempfile

    from scripts import classify as classify_mod

    tmp = Path(tempfile.mkdtemp()) / upload.name
    tmp.write_bytes(upload.getvalue())
    try:
        rows = classify_mod.rows_from_file(tmp)
    except SystemExit as exc:
        st.error(str(exc))
        return
    if not rows:
        st.error("No rows with a story title were found in that file.")
        return

    extractor = classify_mod.Extractor.load()
    if extractor is None:
        st.warning(
            "No trained extractor on disk, so this is running on patterns and the industry "
            "gazetteer alone. More rows will escalate. Train with `scripts/train.py`."
        )
    with st.spinner(f"Deciding {len(rows)} rows…"):
        records = classify_mod.classify_rows(rows, extractor)
    summary = classify_mod.summarise(records)
    results = pd.DataFrame(records)

    n = summary["rows"]
    a, b, c, d = st.columns(4)
    a.metric("Rows", n)
    b.metric("Decided with no LLM", pct(summary["auto_resolved"], n))
    c.metric("Not Impactful — removed", pct(summary["not_impactful"], n))
    d.metric("Escalated", pct(summary["escalated"], n))

    st.markdown(
        f"**{pct(summary['not_impactful'], n)}** comes off the analyst queue. "
        f"**{pct(summary['impactful'], n)}** is Impactful and **{pct(summary['review'], n)}** "
        "needs a human — neither is a saving, and neither is counted as one."
    )

    counts = results["classification"].value_counts().to_dict()
    st.plotly_chart(outcome_bar(counts, tok, dark, "Outcome"), width='stretch')

    blockers = classify_mod.blocking_fields(records)
    if blockers:
        st.subheader("What is parking rows in review")
        st.caption(
            "Each line is a field a rule asked for and extraction could not supply. This is the "
            "improvement backlog in priority order — write the extraction pattern at the top and "
            "that many rows stop needing a human. A row blocked on three fields counts against "
            "each, because clearing any one of them is separate work."
        )
        st.dataframe(
            pd.DataFrame(blockers, columns=["missing field", "rows blocked"]).head(20),
            width='stretch', hide_index=True,
        )

    queue = classify_mod.escalation_queue(records)
    st.subheader("Downloads")
    st.caption(
        f"The escalation queue is **{pct(len(queue), n)}** of the upload, and it is the only "
        "thing a model ever needs to see. One binary question per row, not a re-read of every "
        "threshold: *“{}”*".format(classify_mod.ESCALATION_QUESTION)
    )
    left, right = st.columns(2)
    left.download_button(
        "Download results (every row, with its rule)",
        results.reindex(columns=classify_mod.RESULT_COLUMNS).to_csv(index=False),
        file_name=f"{Path(upload.name).stem}_results.csv", mime="text/csv",
        width='stretch',
    )
    right.download_button(
        f"Download escalation queue ({len(queue)} rows)",
        pd.DataFrame(queue).reindex(columns=classify_mod.ESCALATION_COLUMNS).to_csv(index=False)
        if queue else "",
        file_name=f"{Path(upload.name).stem}_escalations.csv", mime="text/csv",
        disabled=not queue, width='stretch',
    )

    st.subheader("Every row")
    st.caption("Each verdict carries the verbatim rule line it fired on and where each field "
               "came from, so any number here can be traced without re-running anything.")
    st.dataframe(
        results[["row_id", "story_title", "classification", "event_type", "priority",
                 "rule_id", "missing_fields", "escalate", "field_provenance", "rule_text"]],
        width='stretch', hide_index=True,
    )


# ---------------------------------------------------------------- sidebar

st.sidebar.title("EventWatch audit")
dark = st.sidebar.toggle("Dark mode", value=False)
tok = tokens(dark)

periods = available_periods()
if not periods:
    # Classification does not need an ingested period, so the app still does its main job with
    # an empty store. Only the audit pages, which reconcile against the teacher pass, need one.
    st.sidebar.caption("No period ingested — classification only.")
    render_upload_page(tok, dark)
    with st.expander("…or ingest a period to unlock the nine audit pages"):
        st.markdown(
            "```bash\n"
            "python3 audit/scripts/ingest.py --period <name> --add <files.csv>\n"
            "python3 audit/scripts/near_dup.py --period <name>\n"
            "```"
        )
    st.stop()

period = st.sidebar.selectbox("Period", periods)
frame, fun, near_dup = load_period_frame(period, period_stamp(period))

manifest = ingest_mod.load_period(period)
st.sidebar.markdown("**Chunks loaded**")
for c in manifest["chunks"]:
    st.sidebar.caption(
        f"`{c['file']}` — {c['rows_added']} added"
        + (f", {c['rows_already_present']} already present" if c["rows_already_present"] else "")
    )
captures = sorted(r["captured_at"] for r in manifest["rows"].values() if r["captured_at"])
if captures:
    st.sidebar.caption(f"Covers {captures[0][:16]} → {captures[-1][:16]}")
for gap in ingest_mod.coverage_gaps(manifest):
    st.sidebar.warning(f"Gap: {gap}")

# Filters, in one row of the sidebar rather than scattered through the pages.
st.sidebar.markdown("---")
owners = sorted(o for o in frame["owner"].unique() if o)
MANAGERS = {"Sangram Barge", "Nitin Rindhe"}
exclude_managers = st.sidebar.checkbox("Exclude managers", value=True)
picked_owners = st.sidebar.multiselect("Analyst", owners, default=[])
picked_types = st.sidebar.multiselect(
    "Event type", sorted(frame["event_type"].unique()), default=[]
)

view = frame.copy()
if exclude_managers:
    view = view[~view["owner"].isin(MANAGERS)]
if picked_owners:
    view = view[view["owner"].isin(picked_owners)]
if picked_types:
    view = view[view["event_type"].isin(picked_types)]

st.sidebar.markdown("---")
st.sidebar.caption(f"{len(view)} of {len(frame)} rows after filters")

PAGES = [
    "1 · Reduction funnel",
    "2 · Analyst workload",
    "3 · Deduplication",
    "4 · Event vs Non-Event",
    "5 · Impactful vs Not",
    "6 · Event type & priority",
    "7 · Review queues",
    "8 · Rules & evidence",
    "9 · Methodology",
]
page = st.sidebar.radio("Page", [UPLOAD_PAGE] + PAGES, label_visibility="collapsed")

if page == UPLOAD_PAGE:
    render_upload_page(tok, dark)
    st.stop()

total = len(view)
labelled = int((view["stage"] != "unlabelled").sum())
if not fun:
    st.warning(
        "No teacher-pass labels for this period yet, so no row has been decided. "
        "Run the teacher pass, then `scripts/validate_labels.py --period <p> --strict`."
    )


# ---------------------------------------------------------------- pages

if page == PAGES[0]:
    st.title("Where the analyst queue goes")
    st.caption(f"Period {period} · {total} rows after filters")

    if labelled < total:
        st.warning(
            f"**{total - labelled} of {total} rows are unlabelled** and are shown as a separate "
            "band below rather than being quietly dropped — a funnel that silently narrows its "
            "own denominator is the thing this page exists to prevent."
        )

    removed = view[view["classification"] == NOT_IMPACTFUL]
    gate_removed = removed[removed["rule_id"].str.startswith(("GLOBAL", "GATE"))]
    thresh_removed = removed[~removed["rule_id"].str.startswith(("GLOBAL", "GATE"))]
    impactful = view[view["classification"] == IMPACTFUL]
    review = view[view["classification"].isin(REVIEW_OUTCOMES)]
    unlabelled = view[view["stage"] == "unlabelled"]

    nd_groups = near_dup.get("groups", [])
    nd_removable = sum(g["size"] for g in nd_groups) - len(nd_groups) if nd_groups else 0
    nd_confirmed = sum(g["size"] - 1 for g in nd_groups
                       if g["human_confirmation_required"] == "NO")

    stages = [
        ("Near-duplicate copies of one event", nd_removable,
         f"{nd_confirmed} auto-confirmed · {nd_removable - nd_confirmed} need human confirmation"),
        ("Not a candidate event (global gate)", len(gate_removed),
         "expansions, resumptions, market commentary, enforcement, recycled reminders"),
        ("Below the event type's own threshold", len(thresh_removed),
         "a real event that does not clear its bar"),
        ("Bulletin owed (Impactful)", len(impactful), "stays with the analyst"),
        ("Human owed (review queue)", len(review), "evidence missing — named per row"),
    ]
    if len(unlabelled):
        stages.append(("Unlabelled", len(unlabelled), "no teacher-pass label yet"))

    c1, c2 = st.columns([3, 2])
    with c1:
        fig = go.Figure(go.Bar(
            x=[s[1] for s in stages], y=[s[0] for s in stages], orientation="h",
            marker={"color": (tok["funnel"] + [tok["ink"]["muted"]] * 3)[:len(stages)],
                    "line": {"width": 2, "color": tok["ink"]["surface"]}},
            text=[f"{s[1]}" for s in stages], textposition="outside",
            textfont={"color": tok["ink"]["primary"]},
            hovertemplate="%{y}<br>%{x} rows<extra></extra>", width=0.6,
        ))
        fig.update_layout(**plotly_layout(dark), showlegend=False, height=90 + 52 * len(stages),
                          title="Rows by stage")
        fig.update_yaxes(autorange="reversed", showgrid=False)
        st.plotly_chart(fig, width='stretch')
    with c2:
        st.metric("Rows removed from the queue", pct(len(removed), total))
        st.metric("Bulletin owed", pct(len(impactful), total))
        st.metric("Human owed", pct(len(review), total))
        st.caption(
            "Only **Not Impactful** removes a row. Impactful means a bulletin is owed and a "
            "review outcome means a human is owed — counting either as a saving is how a "
            "reduction funnel starts lying."
        )

    st.markdown("#### Stage detail")
    st.dataframe(pd.DataFrame(
        [{"Stage": s[0], "Rows": s[1], "% of period": f"{s[1] / total:.1%}" if total else "n/a",
          "Note": s[2]} for s in stages],
    ), width='stretch', hide_index=True)

    if nd_removable:
        st.info(
            f"The near-duplicate band is an **opportunity, not a realised saving**: "
            f"{nd_removable - nd_confirmed} of {nd_removable} rows still await human "
            "confirmation, because the spec forbids auto-merging. See page 3."
        )

elif page == PAGES[1]:
    st.title("Analyst workload")
    st.caption("Factual volume only — no ranking, no scoring, no performance judgement.")
    if exclude_managers:
        st.caption(f"Managers excluded: {', '.join(sorted(MANAGERS))}")

    per = view.groupby("owner").agg(
        rows=("key", "count"),
        removed=("classification", lambda s: int((s == NOT_IMPACTFUL).sum())),
        impactful=("classification", lambda s: int((s == IMPACTFUL).sum())),
        review=("classification", lambda s: int(s.isin(REVIEW_OUTCOMES).sum())),
    ).reset_index().sort_values("rows", ascending=False)
    per["removable %"] = (per["removed"] / per["rows"]).map("{:.0%}".format)

    fig = go.Figure()
    for name, colour in [("removed", tok["outcome"]["Not Impactful"]),
                         ("impactful", tok["outcome"]["Impactful"]),
                         ("review", tok["outcome"]["Threshold Review"])]:
        fig.add_bar(y=per["owner"], x=per[name], orientation="h", name=name,
                    marker={"color": colour, "line": {"width": 2,
                                                      "color": tok["ink"]["surface"]}})
    fig.update_layout(**plotly_layout(dark), barmode="stack",
                      height=90 + 48 * len(per), title="Rows handled, by outcome")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    st.plotly_chart(fig, width='stretch')
    st.dataframe(per, width='stretch', hide_index=True)

    ne = view[view["system_class"] == "Non-Event"]
    if len(ne):
        st.warning(
            f"**{len(ne)} of {total} rows were already labelled `Non-Event` by the system, and "
            "still reached an analyst.** That is a routing problem, not a model problem, and it "
            "is recoverable without any new model."
        )

elif page == PAGES[2]:
    st.title("Deduplication")
    groups = near_dup.get("groups", [])
    grouped_rows = sum(g["size"] for g in groups)
    c1, c2, c3 = st.columns(3)
    c1.metric("Exact duplicates", pct(0, len(frame)),
              help="Zero in this period — near-duplicate grouping is the whole dedup story.")
    c2.metric("Near-duplicate groups", str(len(groups)))
    c3.metric("Rows removable if merged",
              pct(grouped_rows - len(groups) if groups else 0, len(frame)))

    st.caption(
        "Candidates only — **nothing is auto-merged**. Auto-merging is how two genuinely "
        "different subjects get one verdict; the documented false-merge case is a templated "
        "headline sent to five different manufacturers."
    )
    if groups:
        gdf = pd.DataFrame([{
            "Group": g["group_id"], "Size": g["size"], "Decision": g["decision"],
            "Confidence": g["confidence"], "Confirm?": g["human_confirmation_required"],
            "Reason": g["reason"], "First title": g["titles"][0][:90],
        } for g in groups])
        st.dataframe(gdf, width='stretch', hide_index=True)
        pick = st.selectbox("Inspect a group", [g["group_id"] for g in groups])
        chosen = next(g for g in groups if g["group_id"] == pick)
        st.caption(chosen["reason"])
        for t in chosen["titles"]:
            st.write(f"- {t}")

elif page == PAGES[3]:
    st.title("Event vs Non-Event")
    st.caption(
        "The system's own label against the independent re-derivation. Rows the pipeline could "
        "not resolve are excluded from the accuracy figures and counted separately."
    )
    resolved = view[view["classification"].isin([IMPACTFUL, NOT_IMPACTFUL])]
    ours_event = resolved["classification"] == IMPACTFUL
    theirs_event = resolved["system_class"] == "Event"

    tp = int((ours_event & theirs_event).sum())
    fp = int((~ours_event & theirs_event).sum())
    fn = int((ours_event & ~theirs_event).sum())
    tn = int((~ours_event & ~theirs_event).sum())
    n = tp + fp + fn + tn

    st.dataframe(pd.DataFrame(
        [{"": "System: Event", "Audit: reportable": tp, "Audit: not reportable": fp},
         {"": "System: Non-Event", "Audit: reportable": fn, "Audit: not reportable": tn}],
    ), width='stretch', hide_index=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Agreement", pct(tp + tn, n))
    c2.metric("System said Event, audit says no", pct(fp, n))
    c3.metric("System said Non-Event, audit says report", pct(fn, n))
    st.caption(
        f"Denominator excludes {len(view) - len(resolved)} unresolved rows of {len(view)}."
    )

elif page == PAGES[4]:
    st.title("Impactful vs Not Impactful")
    st.error(
        "**This dataset has one class only.** Every row in it was already moved to Not "
        "Impactful by an analyst, so false negatives are measurable and precision, recall and a "
        "false-positive rate are not. No confusion matrix is shown, because half of it would be "
        "empty by construction rather than by finding."
    )
    counts = view["classification"].value_counts().to_dict()
    st.plotly_chart(outcome_bar(counts, tok, dark, "Independent verdicts"),
                    width='stretch')
    overturns = view[view["classification"] == IMPACTFUL]
    st.metric("Rows the audit would have reported", pct(len(overturns), total))
    st.caption("Every one of these is a row an analyst cleared and the rules say is reportable.")
    table_of(overturns.sort_values("event_type"),
             ["row_id", "event_type", "priority", "rule_id", "title"])

elif page == PAGES[5]:
    st.title("Event type & priority")
    by_type = (view.groupby("event_type")
               .agg(rows=("key", "count"),
                    removed=("classification", lambda s: int((s == NOT_IMPACTFUL).sum())))
               .reset_index().sort_values("rows", ascending=False))
    by_type["removed %"] = (by_type["removed"] / by_type["rows"]).map("{:.0%}".format)
    st.dataframe(by_type, width='stretch', hide_index=True)
    st.caption(
        "Chemical Spill, Volcano and Airworthiness are near notify-always by rule, so a high "
        "removal rate for those indicates an extraction fault rather than a saving."
    )
    prio = view[view["priority"] != ""]["priority"].value_counts().sort_index()
    if len(prio):
        fig = go.Figure(go.Bar(
            x=prio.index.tolist(), y=prio.values.tolist(),
            marker={"color": tok["funnel"][2],
                    "line": {"width": 2, "color": tok["ink"]["surface"]}},
            text=prio.values.tolist(), textposition="outside",
            textfont={"color": tok["ink"]["primary"]},
            hovertemplate="%{x}: %{y} rows<extra></extra>", width=0.55))
        fig.update_layout(**plotly_layout(dark), title="Priority tier (urgency, not impact)",
                          showlegend=False, height=320)
        st.plotly_chart(fig, width='stretch')
        st.caption(
            "Priority is response urgency for an already-impactful event. It is never an input "
            "to the impact decision — a P4 event meeting its criteria is still Impactful."
        )

elif page == PAGES[6]:
    st.title("Review queues")
    review = view[view["classification"].isin(REVIEW_OUTCOMES)]
    st.metric("Rows awaiting a human", pct(len(review), total))
    st.caption(
        "A review outcome fires **only on missing evidence in the row**, never because a rule is "
        "unclear, and every one names the field it is missing."
    )
    if len(review):
        missing = (review["missing_fields"].str.split(", ").explode()
                   .value_counts().head(12))
        fig = go.Figure(go.Bar(
            x=missing.values.tolist(), y=missing.index.tolist(), orientation="h",
            marker={"color": tok["outcome"]["Threshold Review"],
                    "line": {"width": 2, "color": tok["ink"]["surface"]}},
            text=missing.values.tolist(), textposition="outside",
            textfont={"color": tok["ink"]["primary"]},
            hovertemplate="%{y}: %{x} rows<extra></extra>", width=0.6))
        fig.update_layout(**plotly_layout(dark), title="Evidence most often missing",
                          showlegend=False, height=90 + 40 * len(missing))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        st.plotly_chart(fig, width='stretch')
        table_of(review, ["row_id", "event_type", "classification", "missing_fields",
                          "rule_id", "title"])
    reroutes = view[view["reroute_to"] != ""]
    if len(reroutes):
        st.markdown("#### Rerouted to another event type")
        st.caption("Sent to a different rulebook entry rather than decided under the wrong one.")
        table_of(reroutes, ["row_id", "event_type", "reroute_to", "rule_id", "title"])

elif page == PAGES[7]:
    st.title("Rules & evidence")
    st.caption("Every verdict cites the verbatim source line it fired on.")
    rules = (view[view["rule_id"] != ""]
             .groupby(["rule_id", "classification"]).size()
             .reset_index(name="rows").sort_values("rows", ascending=False))
    st.dataframe(rules, width='stretch', hide_index=True)
    pick = st.selectbox("Inspect a rule", rules["rule_id"].unique().tolist())
    rows = view[view["rule_id"] == pick]
    if len(rows):
        st.markdown(f"**Source** — {rows.iloc[0]['source']}")
        st.info(rows.iloc[0]["rule_text"])
        table_of(rows, ["row_id", "event_type", "classification", "evidence", "title"])

else:
    st.title("Methodology & data dictionary")
    st.markdown(f"""
### What this measures

Of **{len(frame)}** raw rows in period `{period}`, how many can come off the analyst queue, at
which stage, and at what risk.

### The four outcomes

| Outcome | Meaning | Removes work? |
|---|---|---|
| **Impactful** | A bulletin is owed | No |
| **Not Impactful** | A real event below its bar, or never a candidate | **Yes** |
| **Threshold Review** | Event type known, evidence missing | No — a human is owed |
| **Needs Context Review** | Cannot even establish the event | No — a human is owed |

### Denominators

Every percentage is shown as `n / N`. Unresolved rows are excluded from accuracy figures and
reported separately. The Impactful-vs-Not page shows **no confusion matrix**, because this
dataset contains one class only.

### Mapped-partner rule

A company **relevant to one of the 27 covered industries counts as a mapped partner**. No
supplier-mapping database is available, so industry relevance is the operative test. Fields that
are pure mapping lookups (`sites_mapped_in_region`, `partner_site_involved`,
`indirect_supplier`, …) are **derived**, not extracted — asking for them produced 80–100%
UNKNOWN and a review queue nobody could clear.

### Priority

P0–P4 is response urgency for an already-impactful event, never an input to the impact decision.
Four event types have no row in the Prioritization Matrix and inherit a tier from the type their
own slide files them under.

### Sources

| File | Role |
|---|---|
| `rules/global-rules.md` | 16 cross-cutting process-owner decisions |
| `rules/event-types-*.md` | Verbatim reporting guidelines, all 52 entries |
| `rules/industries.md` | The 27 industries |
| `rules/priority-matrix.md` | P0–P4 |
| `logic/*.py` | One decision module per event type — pure functions, no model, no keywords |

Coverage: **{len(registry.MODULES)}** registered event types; `registry.coverage()` reports any
rulebook entry without a module, and a test fails the build if one appears.
""")
