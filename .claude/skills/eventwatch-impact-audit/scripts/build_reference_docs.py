#!/usr/bin/env python3
"""Build-time script: regenerates references/*.md from the raw source-of-truth documents.

This is a maintenance tool, not part of the runtime audit path. Run it by hand whenever
Resilinc ships a new version of the Thresholds & Guide / Prioritization Matrix / Industry
Definitions, then review and commit the regenerated references/*.md files.

Design principle: this script only does MECHANICAL work — extracting text from the source
files and re-organizing/re-labeling it (grouping by event-type category, splitting into
Sub-Types / Reporting Guidelines / WarRoom Guidelines sections, stripping the repeated
navigation table). It never paraphrases or summarizes rule wording; every sentence that ends
up in references/*.md is copied verbatim from the source document. That is a deliberate
fidelity requirement, not an oversight: an LLM-guessed paraphrase of a threshold rule is
exactly the kind of "invented rule" the process owner explicitly ruled out.

.pptx and .docx are zip archives of OOXML, so python's stdlib zipfile + xml.etree parse them
directly with no third-party dependency. The Industry Definitions PDF is the one exception:
no working PDF text library was available in the build sandbox (pypdf / pdfminer.six both
failed to import due to a broken system `cryptography`/`cffi` binding, and apt's poppler-utils
mirror 404'd), so its text was extracted once via direct PDF reading and checked in as
raw_sources/industry_definitions_pdf.txt. Everything downstream of that file is, again, pure
mechanical parsing.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SKILL_DIR = Path(__file__).resolve().parent.parent
CLASSIFICATION_DIR = SKILL_DIR.parent.parent.parent  # .../EventWatch_Classification
RAW_SOURCES = SKILL_DIR / "raw_sources"
REFERENCES = SKILL_DIR / "references"

PPTX_PATH = CLASSIFICATION_DIR / "EventWatch Thresholds and Guide V6.5.pptx"
MATRIX_DOCX_PATH = CLASSIFICATION_DIR / "Event Prioritization Matrix (1).docx"
INDUSTRIES_TXT_PATH = RAW_SOURCES / "industry_definitions_pdf.txt"

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# ---------------------------------------------------------------------------
# PPTX extraction (mechanical): one ordered list of paragraph-lines per slide,
# tables kept separate and returned as list-of-rows.
# ---------------------------------------------------------------------------

def _slide_xml_names(zf: zipfile.ZipFile) -> list[str]:
    names = [n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)]
    names.sort(key=lambda n: int(re.search(r"slide(\d+)\.xml", n).group(1)))
    return names


def _extract_table_rows(tbl_elem) -> list[list[str]]:
    rows = []
    for tr in tbl_elem.findall(f"{{{A_NS}}}tr"):
        cells = []
        for tc in tr.findall(f"{{{A_NS}}}tc"):
            cell_text = "".join(t.text or "" for t in tc.iter(f"{{{A_NS}}}t"))
            cells.append(cell_text.strip())
        rows.append(cells)
    return rows


def _walk_slide_tree(elem, lines: list[str], tables: list[list[list[str]]]) -> None:
    """Recursive walk that does NOT double-count: a table's own paragraphs are only ever
    captured as part of its table (via _extract_table_rows), never as loose `lines` too."""
    tag = elem.tag.split("}")[-1]
    if tag == "tbl":
        tables.append(_extract_table_rows(elem))
        return  # do not recurse into a table's own <a:p> paragraphs as loose lines
    if tag == "p":
        text = "".join(t.text or "" for t in elem.iter(f"{{{A_NS}}}t"))
        if text.strip():
            lines.append(text)
        return  # a paragraph's own runs are already captured above; nothing more to walk
    for child in elem:
        _walk_slide_tree(child, lines, tables)


def extract_pptx_slides(path: Path) -> list[dict]:
    """Returns list of {slide_num, lines: [str], tables: [[[str,...],...]]} in slide order."""
    slides = []
    with zipfile.ZipFile(path) as zf:
        for name in _slide_xml_names(zf):
            slide_num = int(re.search(r"slide(\d+)\.xml", name).group(1))
            root = ET.fromstring(zf.read(name))
            lines: list[str] = []
            tables: list[list[list[str]]] = []
            _walk_slide_tree(root, lines, tables)
            slides.append({"slide_num": slide_num, "lines": lines, "tables": tables})
    return slides


def is_home_nav_table(rows: list[list[str]]) -> bool:
    """The ~41-43 row event-type index table repeated on nearly every slide."""
    if len(rows) < 35:
        return False
    flat = " ".join(c for row in rows for c in row)
    return "Airport Disruption" in flat and "Bankruptcy" in flat and "Volcano" in flat


# ---------------------------------------------------------------------------
# DOCX extraction (mechanical): paragraphs + tables from word/document.xml
# ---------------------------------------------------------------------------

def extract_docx(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(f"{{{W_NS}}}body")
    blocks: list[dict] = []  # {"type": "para"|"table", ...}
    for child in body:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            text = "".join(t.text or "" for t in child.iter(f"{{{W_NS}}}t"))
            if text.strip():
                blocks.append({"type": "para", "text": text})
        elif tag == "tbl":
            rows = []
            for tr in child.findall(f"{{{W_NS}}}tr"):
                cells = []
                for tc in tr.findall(f"{{{W_NS}}}tc"):
                    cell_text = "".join(t.text or "" for t in tc.iter(f"{{{W_NS}}}t"))
                    cells.append(cell_text.strip())
                rows.append(cells)
            blocks.append({"type": "table", "rows": rows})
    return {"blocks": blocks}


# ---------------------------------------------------------------------------
# Event-type -> category mapping (data derived from Slide 2's own taxonomy;
# slide numbers verified against the extracted deck this session).
# ---------------------------------------------------------------------------

# slide_num -> (canonical event type name, category). Categories mirror Slide 2's own
# Man Made / Naturally Caused / Others grouping; cross-cutting redirect slides (Military
# Drills, Mad Cow Disease, Restricted Access, Software/Internet Outage, Deforestation) are
# filed under "other" since none of the 3 core lists on Slide 2 contains them.
SLIDE_TO_EVENT_TYPE: dict[int, tuple[str, str]] = {
    3: ("Airport Disruption", "manmade"), 4: ("Bankruptcy", "manmade"),
    5: ("Business Spin-off", "manmade"), 6: ("Business Sale", "manmade"),
    7: ("Bribery/Corruption", "manmade"), 8: ("Chemical Spill", "manmade"),
    9: ("Company Split", "manmade"), 10: ("Compliance", "manmade"),
    11: ("Corporate Restructuring", "manmade"), 12: ("Cyber Attack", "manmade"),
    13: ("Counterfeit (CFSI)", "manmade"),
    14: ("Earthquake (Japan/Taiwan/S.Korea/Philippines/Indonesia/China)", "natural"),
    15: ("Earthquake (Rest of the World)", "natural"),
    16: ("Environmental Hazard", "natural"), 17: ("Extreme Weather", "natural"),
    18: ("FDA/EMA/OSHA Action", "manmade"), 19: ("Factory Fire", "manmade"),
    20: ("Factory Disruption", "manmade"), 21: ("Fine", "manmade"),
    22: ("Financial Distress", "manmade"), 23: ("Flood", "natural"),
    24: ("Force Majeure", "manmade"), 25: ("Forest Fire", "natural"),
    26: ("Geopolitical", "manmade"),
    27: ("Military Drills (redirect -> Geopolitical)", "other"),
    28: ("Human Health", "natural"),
    29: ("Hurricane/Typhoon (Pre-Landfall)", "natural"),
    30: ("Hurricane/Typhoon (Post-Landfall)", "natural"),
    31: ("Labor Disruption", "manmade"), 32: ("Labor Violation", "manmade"),
    33: ("Leadership Transition", "manmade"), 34: ("Legal Action", "manmade"),
    35: ("Merger & Acquisition", "manmade"), 36: ("Mine Shutdown", "manmade"),
    37: ("Power Outage", "natural"), 38: ("Port Disruption", "manmade"),
    39: ("Price Fluctuation", "manmade"), 40: ("Protest/Riot", "manmade"),
    41: ("Recall", "manmade"), 42: ("Regulatory Change", "manmade"),
    43: ("Supply Shortage", "manmade"), 44: ("Tornado", "natural"),
    45: ("Volcano", "natural"), 46: ("Profit Warning", "manmade"),
    47: ("Mail/Postal/Package Delivery Services Disruptions", "other"),
    48: ("Airworthiness", "other"), 49: ("Layoffs", "other"),
    50: ("Container Ship Accidents (redirect -> Port Disruption)", "other"),
    51: ("Others", "other"),
    53: ("Mad Cow Disease (redirect -> Regulatory Change / Human Health)", "other"),
    54: ("Restricted Access (cross-cutting sourcing rule, not an event type)", "other"),
    55: ("Software/Internet Outage (redirect -> Power Outage)", "other"),
    56: ("Deforestation (redirect -> Forest Fire / Regulatory Change / "
         "Environmental Hazard / Protest-Riot)", "other"),
}


SECTION_HEADERS = [
    "Sub-Types", "Sub-Type", "Reporting Guidelines", "Reporting Guideline",
    "WarRoom Guidelines", "Send Supplier Impact Confirmation",
]


_HEADER_PATTERNS = [
    (h, re.compile(r"^\s*" + re.escape(h) + r"\s*[\?:]*\s*[-–—]?\s*"))
    for h in SECTION_HEADERS
]

_NOISE_LINES = {"home", "back to home"}


def _is_noise_line(line: str, event_name: str) -> bool:
    stripped = line.strip().strip("-").strip()
    if stripped.lower() in _NOISE_LINES:
        return True
    bare_name = event_name.split(" (")[0].upper()
    return stripped.upper() == bare_name


def split_into_sections(lines: list[str], event_name: str) -> dict[str, list[str]]:
    """Mechanical split: a new section starts whenever a line begins with one of the known
    headers — allowing for trailing "?"/":"/"-" punctuation and, in a few source slides, the
    next sentence running on in the same paragraph as the header (e.g. "Reporting
    Guidelines:We notify..." or "Send Supplier Impact Confirmation? – YES..."). Pure
    navigation chrome ("Home", the slide's own all-caps title repeated as a footer) is dropped
    since it carries no rule content. Everything until the next header is that section's body."""
    sections: dict[str, list[str]] = {"preamble": []}
    current = "preamble"
    for raw in lines:
        line = raw.strip()
        if _is_noise_line(line, event_name):
            continue
        header_hit, remainder = None, ""
        for h, pattern in _HEADER_PATTERNS:
            m = pattern.match(line)
            if m:
                header_hit, remainder = h, line[m.end():].strip()
                break
        if header_hit:
            current = header_hit
            sections.setdefault(current, [])
            if remainder:
                sections[current].append(remainder)
            continue
        sections.setdefault(current, []).append(raw)
    return sections


def render_event_type_md(slide_num: int, event_name: str, slide: dict) -> str:
    sections = split_into_sections(slide["lines"], event_name)
    out = [f"### {event_name}  _(source: slide {slide_num})_", ""]
    if sections.get("preamble"):
        # First non-empty preamble line is usually the event-type heading itself; keep the rest.
        body = [l for l in sections["preamble"] if l.strip() and l.strip() != event_name.split(" (")[0].upper()]
        if body:
            out.append("**Sub-Types / context:**")
            out.extend(f"- {l.strip()}" for l in body)
            out.append("")
    for h in ["Sub-Types", "Sub-Type"]:
        if sections.get(h):
            out.append("**Sub-Types:**")
            out.extend(f"- {l.strip()}" for l in sections[h] if l.strip())
            out.append("")
    for h in ["Reporting Guidelines", "Reporting Guideline"]:
        if sections.get(h):
            out.append("**Reporting Guidelines (verbatim from source):**")
            out.extend(f"- {l.strip()}" for l in sections[h] if l.strip())
            out.append("")
    if sections.get("WarRoom Guidelines"):
        out.append("**WarRoom Guidelines (context; not the impact call itself):**")
        out.extend(f"- {l.strip()}" for l in sections["WarRoom Guidelines"] if l.strip())
        out.append("")
    if sections.get("Send Supplier Impact Confirmation"):
        out.append("**Send Supplier Impact Confirmation?** " +
                    " ".join(l.strip() for l in sections["Send Supplier Impact Confirmation"] if l.strip()))
        out.append("")
    for rows in slide.get("tables", []):
        if is_home_nav_table(rows) or not rows:
            continue
        out.append("**Additional table from this slide (verbatim):**")
        out.append("")
        widths = max(len(r) for r in rows)
        for row in rows:
            padded = row + [""] * (widths - len(row))
            out.append("| " + " | ".join(c.replace("\n", " ") for c in padded) + " |")
            if row is rows[0]:
                out.append("|" + "---|" * widths)
        out.append("")
    return "\n".join(out)


def build_event_type_files(slides_by_num: dict[int, dict]) -> None:
    buckets = {"manmade": [], "natural": [], "other": []}
    toc = {"manmade": [], "natural": [], "other": []}
    for slide_num, (event_name, category) in sorted(SLIDE_TO_EVENT_TYPE.items()):
        slide = slides_by_num.get(slide_num)
        if not slide:
            continue
        buckets[category].append(render_event_type_md(slide_num, event_name, slide))
        toc[category].append(f"- {event_name}")

    titles = {
        "manmade": "Event Types — Man Made",
        "natural": "Event Types — Naturally Caused",
        "other": "Event Types — Others / Cross-Cutting / Redirects",
    }
    notes = {
        "other": (
            "\n> Several entries here are explicit **redirects**: the source guide instructs "
            "analysts to classify the story under a *different* canonical event type based on "
            "the specific cause (e.g. Deforestation -> Forest Fire / Regulatory Change / "
            "Environmental Hazard / Protest-Riot depending on what's actually disrupting supply "
            "chains; Military Drills -> Geopolitical; Container Ship Accidents -> Port "
            "Disruption; Software/Internet Outage -> Power Outage). When re-deriving Event Type "
            "for a row, resolve to the underlying canonical type via these redirects rather than "
            "stopping at the redirect label itself.\n"
        )
    }
    for category, entries in buckets.items():
        path = REFERENCES / f"event-types-{category}.md"
        content = [f"# {titles[category]}", ""]
        content.append("## Contents")
        content.extend(toc[category])
        content.append("")
        if notes.get(category):
            content.append(notes[category])
        content.append("---")
        content.append("")
        content.append("\n---\n\n".join(entries))
        path.write_text("\n".join(content) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(CLASSIFICATION_DIR)} ({len(entries)} event types)")


# ---------------------------------------------------------------------------
# Global rules: slides 58 (generic guidelines table), 59 (immediate vs mid/long
# priority split), 60 (severity gauge table) are hand-pinned by slide number
# since they're one-off structured tables, not part of the per-event-type loop.
# ---------------------------------------------------------------------------

def build_global_rules_md(slides_by_num: dict[int, dict]) -> None:
    lines = ["# Global Rules — apply to every row, regardless of event type", ""]

    lines.append("## 1. Generic Guidelines (source: Slide 58)")
    lines.append("")
    slide58 = slides_by_num.get(58)
    if slide58 and slide58["tables"]:
        for row in slide58["tables"][0]:
            for cell in row:
                if cell.strip():
                    lines.append(f"- {cell.strip()}")
    lines.append("")
    lines.append(
        "**Most important line above for this audit:** \"Event classifications are based on "
        "the cause of disruption, not the outcome.\" Re-derive Event Type from what *caused* "
        "the disruption, not from how the story ultimately resolved.\n"
    )

    lines.append("## 2. Severity Gauge (source: Slide 60)")
    lines.append("")
    slide60 = slides_by_num.get(60)
    if slide60 and slide60["tables"]:
        for row in slide60["tables"][0]:
            for cell in row:
                if cell.strip():
                    lines.append(f"- {cell.strip()}")
    lines.append("")
    lines.append(
        "Severity is not itself the binary impactful/not-impactful call, but it is diagnostic: "
        "if a row's own facts only support a LOW-severity read (company not mapped/not "
        "connected AND no sites in the affected region AND the item is a minor FYI by nature), "
        "that is consistent with Not Impactful. Any of Medium/High/Severe should be treated as "
        "Impactful.\n"
    )

    lines.append("## 3. Priority tiers are NOT the impact axis")
    lines.append("")
    lines.append(
        "`priority-matrix.md` (P0-P4, from the Event Prioritization Matrix docx) and Slide 59's "
        "Immediate-Impact / Mid-to-Long-Term-Impact split both describe **response urgency** — "
        "how fast a confirmed-impactful event should be turned around — not whether an event is "
        "impactful in the first place. Do not use \"this event type is P3/P4\" or \"this is "
        "Mid-to-Long-Term\" as a reason to lean toward Not Impactful. A P4 event (e.g. Leadership "
        "Transition) that meets its own reporting criteria is still Impactful; it just doesn't "
        "need to be notified within the hour.\n"
    )

    lines.append("## 4. Mapped/critical-company heuristic (no supplier-mapping database available)")
    lines.append("")
    lines.append(
        "The source guide constantly conditions on whether a company is a \"mapped\" supplier "
        "on the Resilinc platform (e.g. \"if mapped, report straightaway\"). This audit has no "
        "access to that mapping database, so apply this heuristic instead, per explicit process-"
        "owner instruction:\n"
        "- If the company/site is well-known and clearly important to one of the 27 industries "
        "in `industries.md`, treat it as if it were mapped/critical — do not downgrade a major "
        "player just because mapped status can't be confirmed.\n"
        "- Never dismiss a smaller or unfamiliar company purely because it isn't obviously "
        "\"big.\" Check the product/commodity/service line for a plausible connection to one of "
        "the 27 industries instead — the guide repeatedly treats an unmapped company as a "
        "possible unmapped Tier-1/sub-tier supplier when the product line matches, and instructs "
        "reporting in that case too.\n"
        "- If, after checking both company prominence and product/vertical connection, the case "
        "is genuinely ambiguous, classify **Impactful** (safe default) rather than Not Impactful.\n"
    )

    lines.append("## 5. Resolved/over events — event-type-specific, never a blanket rule")
    lines.append("")
    lines.append(
        "Do not apply a blanket \"if the disruption is over, mark Not Impactful\" shortcut. The "
        "source guide is explicit that this varies by event type:\n"
        "- Some types explicitly still report even after the acute event ends — e.g. Factory "
        "Fire: \"We report a factory fire, even if the articles say it is a small fire or has "
        "been extinguished.\"\n"
        "- Others explicitly stand down once resolved with no disruption — e.g. Labor "
        "Disruption: \"Strike Called Off? Mark as Not Impactful.\" Airport Disruption: \"Partial "
        "disruptions, no impact on cargo; Operations resumed - Avoid.\"\n"
        "Always check the specific event type's own Reporting Guidelines in "
        "`event-types-*.md` for how it treats resolution, rather than assuming either way.\n"
    )

    (REFERENCES / "global-rules.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {(REFERENCES / 'global-rules.md').relative_to(CLASSIFICATION_DIR)}")


# ---------------------------------------------------------------------------
# Priority matrix (docx)
# ---------------------------------------------------------------------------

def build_priority_matrix_md(docx_data: dict) -> None:
    lines = [
        "# Priority Matrix (P0-P4) — urgency only, NOT the impact axis",
        "",
        "> See `global-rules.md` #3. This table tells you how fast a *confirmed-impactful* "
        "event should be turned around. It must never be used as a reason to call something "
        "Not Impactful.",
        "",
    ]
    table_found = False
    for block in docx_data["blocks"]:
        if block["type"] == "table" and not table_found:
            rows = block["rows"]
            if rows and rows[0][:2] == ["Event Type", "Priority Level"]:
                lines.append("| Event Type | Priority |")
                lines.append("|---|---|")
                for row in rows[1:]:
                    if len(row) >= 2 and row[0].strip():
                        lines.append(f"| {row[0].strip()} | {row[1].strip()} |")
                table_found = True
                lines.append("")
    lines.append("## Instructions for Analysts (verbatim)")
    lines.append("")
    started = False
    for block in docx_data["blocks"]:
        if block["type"] == "para":
            if block["text"].strip().startswith("Instructions for Analysts"):
                started = True
                continue
            if started:
                lines.append(f"- {block['text'].strip()}")
    (REFERENCES / "priority-matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {(REFERENCES / 'priority-matrix.md').relative_to(CLASSIFICATION_DIR)}")


# ---------------------------------------------------------------------------
# Industries (from the checked-in PDF text dump)
# ---------------------------------------------------------------------------

def build_industries_md(txt_path: Path) -> None:
    raw = txt_path.read_text(encoding="utf-8")
    # Cut off the header block above "1. Aerospace"
    start = raw.index("1. Aerospace")
    body = raw[start:]
    entries = re.split(r"\n(?=\d+\. )", body)
    lines = [
        "# Industry Definitions (27 industries — authoritative list)",
        "",
        "Source: Resilinc EventWatch Industry Definitions_2026_1.pdf (27 industries, richer "
        "sub-sector detail than the companion docx summary; both list the same 27 industries).",
        "",
        "> **Decision (process owner, confirmed):** \"Tobacco and E-cigarettes\", which appears "
        "only in the Thresholds & Guide pptx's Slide 62 coverage table and has no formal "
        "definition in this document or its docx companion, is **excluded**. A title touching "
        "only tobacco/e-cigarette products with no other vertical connection does not by itself "
        "make an event Impactful. Do not invent a 28th industry.",
        "",
        "## Contents",
    ]
    parsed = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        header_match = re.match(r"\d+\.\s+(.+)", entry.splitlines()[0])
        if not header_match:
            continue
        name = header_match.group(1).strip()
        parsed.append((name, entry))
        lines.append(f"- {name}")
    lines.append("")
    lines.append("---")
    lines.append("")
    for name, entry in parsed:
        body_lines = entry.splitlines()[1:]  # drop the "N. Name" header line
        lines.append(f"### {name}")
        lines.append("")
        lines.extend(body_lines)
        lines.append("")
    (REFERENCES / "industries.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {(REFERENCES / 'industries.md').relative_to(CLASSIFICATION_DIR)} ({len(parsed)} industries)")


def main() -> int:
    if not PPTX_PATH.exists():
        print(f"ERROR: missing {PPTX_PATH}", file=sys.stderr)
        return 1
    if not MATRIX_DOCX_PATH.exists():
        print(f"ERROR: missing {MATRIX_DOCX_PATH}", file=sys.stderr)
        return 1
    if not INDUSTRIES_TXT_PATH.exists():
        print(f"ERROR: missing {INDUSTRIES_TXT_PATH}", file=sys.stderr)
        return 1

    REFERENCES.mkdir(parents=True, exist_ok=True)

    slides = extract_pptx_slides(PPTX_PATH)
    slides_by_num = {s["slide_num"]: s for s in slides}
    print(f"extracted {len(slides)} slides from {PPTX_PATH.name}")

    build_event_type_files(slides_by_num)
    build_global_rules_md(slides_by_num)

    docx_data = extract_docx(MATRIX_DOCX_PATH)
    build_priority_matrix_md(docx_data)

    build_industries_md(INDUSTRIES_TXT_PATH)

    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
