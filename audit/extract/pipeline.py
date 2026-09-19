"""End-to-end extraction: rules → gazetteer → model → escalate. No LLM at runtime.

The order is not arbitrary. Each layer is preferred over the next because it is more defensible,
not merely cheaper:

1. **`rules.py`** reads facts the story states outright ("flood warning", "magnitude 6.2"). A
   pattern that fires here is a reading, and it beats any statistical guess about the same fact.
2. **`industries.py`** resolves industry relevance against the 27 official definitions. The
   measured reason this outranks the model: on held-out rows the gazetteer answered 61.9% of rows
   at **76.0%** accuracy while the trained model managed **71.8%** across all rows — the
   definitional lookup is simply better at the thing it was built for.
3. **`model.py`** handles what is left — chiefly event type and story nature, where the model
   clearly earns its place (story_nature: 89.1% against the rules' 70.6% on 16.8% coverage).
4. **Escalation.** Anything still unresolved, or resolved below its confidence floor, is written
   to a queue rather than guessed. That queue is the only thing an LLM ever sees, and the only
   question it is asked is the cheap one: *is this likely to affect a supply chain at all?*

The contract that makes this safe: extraction produces **facts**, `logic/` applies **rules**. A
model can be wrong about the event type and the wrong module still applies that type's real rule —
which shows up as a type-distribution anomaly on the dashboard rather than as a silent wrong
verdict. That is the difference between this and the keyword classifier the project ruled out.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _field
from typing import Mapping

from . import industries as ind
from . import rules as rules_mod
from .model import LEARNED_FIELDS, Extractor

#: Fields `logic/` derives from industry relevance and must never be extracted.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from logic.connection import DERIVED_FROM_RELEVANCE  # noqa: E402


@dataclass
class ExtractionResult:
    fields: dict[str, str]
    #: field -> which layer produced it, so any value can be traced without re-running anything.
    provenance: dict[str, str] = _field(default_factory=dict)
    #: field -> confidence, for the learned ones only.
    confidence: dict[str, float] = _field(default_factory=dict)
    #: Why this row needs a human or an LLM, empty when it is fully resolved.
    escalation_reasons: tuple[str, ...] = ()

    @property
    def needs_escalation(self) -> bool:
        return bool(self.escalation_reasons)


def extract(
    title: str,
    summary: str = "",
    extractor: Extractor | None = None,
) -> ExtractionResult:
    """Extract every field `logic/` needs, without calling anything external."""
    text = f"{title}. {summary}"
    fields: dict[str, str] = {}
    provenance: dict[str, str] = {}
    confidence: dict[str, float] = {}

    # --- Layer 1: deterministic patterns --------------------------------------------------
    for name, value in rules_mod.extract_all(title, summary).items():
        fields[name] = value
        provenance[name] = "rules"

    # --- Layer 2: the industry gazetteer --------------------------------------------------
    relevance, reason = ind.industry_relevance(title, summary)
    if relevance != "UNKNOWN":
        fields["industry_relevance"] = relevance
        provenance["industry_relevance"] = f"gazetteer: {reason}"

    nature = rules_mod.story_nature_signal(text)
    if nature:
        fields["story_nature"] = nature
        provenance["story_nature"] = "rules"

    # --- Layer 3: the trained model, only where the layers above stayed silent -------------
    if extractor is not None:
        predictions = extractor.predict(title, summary)
        for name in LEARNED_FIELDS:
            if name in fields:
                continue  # a reading always beats a guess about the same fact
            prediction = predictions[name]
            confidence[name] = round(prediction.confidence, 3)
            if prediction.accepted and prediction.value not in ("(none)", "UNKNOWN"):
                fields[name] = prediction.value
                provenance[name] = f"model p={prediction.confidence:.2f}"

    # --- Layer 4: fields the rules themselves say are the same question -------------------
    # Under the process-owner decision that industry relevance IS mapped-partner status,
    # `product_line_connection` asks the same thing in different words: "do this company's
    # products/services connect to a covered industry?". `logic/connection.py` already resolves
    # mapped status through either, so deriving one from the other is applying the rule, not
    # guessing. Before this, the pipeline knew a story was about a covered industry and still
    # stalled in Threshold Review for want of a field it had already answered -- that single gap
    # was the largest block of disagreements with the teacher pass (116 Impactful rows landing in
    # review).
    relevance_value = fields.get("industry_relevance", "UNKNOWN")
    if relevance_value != "UNKNOWN" and "product_line_connection" not in fields:
        fields["product_line_connection"] = (
            "CONNECTED" if relevance_value == "RELEVANT" else "NOT_CONNECTED"
        )
        provenance["product_line_connection"] = "derived from industry_relevance"

    # A services business has no product line to assess, and the rules check the service vertical
    # before the product test precisely for that case. With relevance known, the service question
    # is answered the same way.
    if relevance_value != "UNKNOWN" and "service_sector_applicability" not in fields:
        fields["service_sector_applicability"] = (
            "APPLICABLE" if relevance_value == "RELEVANT" else "NOT_APPLICABLE"
        )
        provenance["service_sector_applicability"] = "derived from industry_relevance"

    # --- Defaults that are readings, not guesses ------------------------------------------
    # `story_nature` gates the whole pipeline, and its carve-out categories (expansion,
    # resumption, market commentary, enforcement, recycled reminder) all carry strong explicit
    # patterns handled above. What is left is overwhelmingly the ordinary case: 675 of 859
    # teacher-labelled rows (79%) are DISRUPTION_OR_RISK_SIGNAL. Defaulting to it when no
    # carve-out pattern fired is reading that base rate, and the failure direction is safe --
    # a wrongly-defaulted row proceeds to its event type's own threshold test rather than being
    # dropped by the gate.
    if fields.get("story_nature", "UNKNOWN") == "UNKNOWN":
        fields["story_nature"] = "DISRUPTION_OR_RISK_SIGNAL"
        provenance["story_nature"] = "default (no carve-out pattern; 79% base rate)"

    # A story that identifies its subject is the overwhelming norm; `subject_identifiable=NO` is
    # for rows too thin to tell what they are about, which is detectable by length rather than by
    # inference. global-rules #13 is explicit that short is not the same as unidentifiable, so
    # the bar is deliberately low.
    if "subject_identifiable" not in fields:
        informative = len(f"{title} {summary}".strip())
        fields["subject_identifiable"] = "YES" if informative >= 40 else "NO"
        provenance["subject_identifiable"] = "length heuristic"

    # --- Escalation ------------------------------------------------------------------------
    reasons: list[str] = []
    if "event_type" not in fields:
        reasons.append("event type undetermined")
    if fields.get("industry_relevance", "UNKNOWN") == "UNKNOWN":
        reasons.append("industry relevance undetermined")
    # story_nature no longer escalates: the carve-outs are pattern-detected and the remainder
    # defaults to the dominant class, so an UNKNOWN here is not reachable.

    return ExtractionResult(
        fields=fields,
        provenance=provenance,
        confidence=confidence,
        escalation_reasons=tuple(reasons),
    )


def to_decision_fields(result: ExtractionResult) -> dict[str, str]:
    """The field map `logic/` consumes — derived fields stripped, never fabricated."""
    return {k: v for k, v in result.fields.items() if k not in DERIVED_FROM_RELEVANCE}
