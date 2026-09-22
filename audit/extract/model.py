"""The learned half of extraction: event type, story nature, industry relevance.

These three fields need to read a story rather than scan it, so they are learned from the teacher
pass's labels rather than pattern-matched. Everything else is handled deterministically in
`rules.py` and `industries.py`.

**This is not the keyword classifier that was ruled out.** The distinction is what the thing
predicts and what happens next: this predicts *what kind of story it is*, and a hand-written rule
module then decides whether it is reportable. A keyword classifier skips that middle step and
jumps from words to a verdict, which is the failure the whole project exists to avoid. A model
here can be wrong about the event type and the wrong module will still apply the right rule for
that type, and the funnel will show it as a type-distribution anomaly rather than a silent
misclassification.

Character n-grams rather than words, deliberately: feed titles are multilingual (the 7 Sept shift
carried Spanish, German, Portuguese, Turkish and Indonesian headlines), riddled with wire-service
noise, and full of company names no word vocabulary will have seen. Character 3-5 grams degrade
gracefully on all three where a word model simply misses.

Every prediction carries a calibrated probability. Below the floor the field is left UNKNOWN,
which sends the row to review or escalation rather than into a confident wrong answer.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "extractor.pkl"

#: Fields this layer predicts. Everything else comes from rules.py / industries.py.
LEARNED_FIELDS = ("event_type", "story_nature", "industry_relevance")

#: Below these, the prediction is discarded and the field stays UNKNOWN. Set from the measured
#: coverage/accuracy curve in `scripts/train.py --report`, not guessed.
#: Chosen by sweeping the END-TO-END objective (verdict agreement, removal recall, and
#: over-removals) rather than per-field accuracy. A 95%-per-field target sounded rigorous and was
#: the wrong objective: it pushed industry_relevance to a 0.80 floor covering 19% of rows, which
#: starved the connection cascade and parked 116 reportable rows in Threshold Review. Optimising
#: what the funnel actually measures moved agreement from 36% to 51% and removal recall from 9%
#: to 26%, at a cost of 9 over-removals in 859 rows.
#: Re-swept after the teacher pass completed (1,079 labels, 44 event types). The full table,
#: measured end to end on all 1,079 rows, is a clean monotone trade with no free lunch:
#:
#:   event_type floor | agreement | removal recall | over-removals | % of removals wrong
#:   -----------------|-----------|----------------|---------------|--------------------
#:   0.15             |   59.0%   |     28.4%      |      19       |        22%
#:   0.25             |   56.3%   |     25.9%      |      13       |        18%
#:   0.30             |   55.7%   |     25.0%      |      13       |        17%
#:   0.40             |   50.6%   |     21.1%      |       7       |        13%
#:   0.45             |   45.8%   |     16.4%      |       6       |        12%
#:
#: 0.25 is the knee, chosen on the *marginal* trade rather than on any single column: moving
#: 0.40 -> 0.25 buys 11 extra correct removals for 6 extra misses, while 0.25 -> 0.15 buys 6 for
#: 6 -- at that point the marginal removal is a coin flip, and an over-removal is a missed
#: bulletin while a forgone removal is only analyst time. Raising the floor is safe in direction:
#: a row below it gets no event type and lands in Needs Context Review, never in a silent drop.
#: `industry_relevance` at 0.45 is never worse than 0.35 at any event_type floor and leans less
#: on the weaker of the two layers (the gazetteer beats the model on that field outright).
#:
#: Re-sweep with the loop in this file's git history after any retrain. Do NOT set these from
#: `train.py`'s per-field curve: a 95%-per-field target sounded rigorous and was the wrong
#: objective, pushing industry_relevance to 0.80, covering 19% of rows, starving the connection
#: cascade and parking 116 reportable rows in Threshold Review.
DEFAULT_FLOORS = {
    "event_type": 0.25,
    "story_nature": 0.40,
    "industry_relevance": 0.45,
}


@dataclass
class Prediction:
    value: str
    confidence: float
    accepted: bool


class Extractor:
    """Three one-vs-rest classifiers over shared character n-gram features."""

    def __init__(self, models: dict, floors: dict[str, float] | None = None):
        self.models = models
        self.floors = dict(DEFAULT_FLOORS, **(floors or {}))

    # -- prediction -----------------------------------------------------------------------

    def predict_field(self, field: str, text: str) -> Prediction:
        model = self.models.get(field)
        if model is None:
            return Prediction("UNKNOWN", 0.0, False)
        probs = model.predict_proba([text])[0]
        best = probs.argmax()
        value = str(model.classes_[best])
        confidence = float(probs[best])
        return Prediction(value, confidence, confidence >= self.floors[field])

    def predict(self, title: str, summary: str = "") -> dict[str, Prediction]:
        text = _feature_text(title, summary)
        return {f: self.predict_field(f, text) for f in LEARNED_FIELDS}

    # -- persistence ----------------------------------------------------------------------

    def save(self, path: Path = MODEL_PATH) -> None:
        """Persist the fitted models only — never the floors.

        A floor is a policy decision about how much risk to accept; a model is an artefact. The
        pickle used to carry both, so `load()` silently overrode DEFAULT_FLOORS with whatever was
        in effect at training time and editing this file changed nothing until someone retrained.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump({"models": self.models}, fh)

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "Extractor | None":
        """Return None rather than raising when no model is trained yet.

        The dashboard must still run — showing the rules-only result and an honest note — rather
        than refusing to start because a training artefact is missing.
        """
        if not path.exists():
            return None
        with path.open("rb") as fh:
            blob = pickle.load(fh)
        # `blob.get("floors")` is deliberately ignored: an older pickle carries the floors that
        # were in effect when it was trained, and honouring them would make this file's
        # DEFAULT_FLOORS advisory.
        return cls(blob["models"])


def _feature_text(title: str, summary: str = "") -> str:
    """Title carries the signal; the summary carries the detail that disambiguates it.

    The title is repeated so it outweighs a long summary — a 1,400-character wire summary would
    otherwise drown the eight words that actually name the event.
    """
    title = (title or "").strip()
    summary = (summary or "").strip()[:600]
    return f"{title} {title} {summary}".lower()


def build_pipeline():
    """A fresh untrained pipeline. Imported lazily so the app starts without scikit-learn."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=2,
            max_features=120_000,
            sublinear_tf=True,
        )),
        ("clf", LogisticRegression(
            max_iter=2000,
            C=4.0,
            class_weight="balanced",
            n_jobs=-1,
        )),
    ])
