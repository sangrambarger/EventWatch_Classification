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
DEFAULT_FLOORS = {
    "event_type": 0.15,
    "story_nature": 0.40,
    "industry_relevance": 0.35,
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
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump({"models": self.models, "floors": self.floors}, fh)

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
        return cls(blob["models"], blob.get("floors"))


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
