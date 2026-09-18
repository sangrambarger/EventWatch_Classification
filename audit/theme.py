"""Validated colour tokens for the audit dashboard.

Every palette below was checked with the dataviz validator rather than chosen by eye, and the
results are recorded so a future change can be re-checked rather than re-argued:

- Outcome categories (4 categorical slots, adjacent pairlist) — PASS light and dark. Worst
  adjacent CVD ΔE 9.1 light / 8.4 dark against an ≥8 target; worst normal-vision ΔE 22.9 / 19.8
  against a ≥15 floor. Light mode WARNs on contrast for aqua (2.74:1) and yellow (2.11:1), so the
  **relief rule applies**: every chart using them ships visible direct labels and a table view.

- Funnel stages (ordinal single-hue ramp) — the first attempt FAILED: steps 450 and 550 sat
  ΔL 0.048 apart against a 0.06 minimum, which would have made two adjacent funnel bars
  indistinguishable. Re-stepped to 250/350/450/550/650 on light and 100/200/300/400/500 on dark,
  both PASS.

Status colours are reserved for pipeline health (unlabelled rows, invalid labels) and never
reused as a series, so a red bar never means "category 4".
"""

from __future__ import annotations

# --- Categorical: classification outcomes (fixed order, never cycled) -------------------------
OUTCOME_LIGHT = {
    "Impactful": "#2a78d6",
    "Not Impactful": "#eb6834",
    "Threshold Review": "#1baf7a",
    "Needs Context Review": "#eda100",
}
OUTCOME_DARK = {
    "Impactful": "#3987e5",
    "Not Impactful": "#d95926",
    "Threshold Review": "#199e70",
    "Needs Context Review": "#c98500",
}

#: Reading order for every outcome chart and table, so colour follows the entity and a filter
#: that drops one outcome never repaints the survivors.
OUTCOME_ORDER = [
    "Impactful",
    "Not Impactful",
    "Threshold Review",
    "Needs Context Review",
]

# --- Ordinal: funnel stages (single hue, light -> dark) ---------------------------------------
FUNNEL_LIGHT = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
FUNNEL_DARK = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf"]

# --- Status (reserved — never a series colour) ------------------------------------------------
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# --- Chrome -----------------------------------------------------------------------------------
INK_LIGHT = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781",
             "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#fcfcfb", "plane": "#f9f9f7"}
INK_DARK = {"primary": "#ffffff", "secondary": "#c3c2b7", "muted": "#898781",
            "grid": "#2c2c2a", "axis": "#383835", "surface": "#1a1a19", "plane": "#0d0d0d"}


def tokens(dark: bool) -> dict:
    """Return every colour role for the active mode.

    Dark is a *selected* set of steps validated against the dark surface, not an automatic flip
    of the light values.
    """
    return {
        "outcome": OUTCOME_DARK if dark else OUTCOME_LIGHT,
        "funnel": FUNNEL_DARK if dark else FUNNEL_LIGHT,
        "status": STATUS,
        "ink": INK_DARK if dark else INK_LIGHT,
    }


def plotly_layout(dark: bool) -> dict:
    """Shared Plotly layout: recessive grid and axes, text in ink tokens never series colour."""
    ink = INK_DARK if dark else INK_LIGHT
    return {
        "paper_bgcolor": ink["surface"],
        "plot_bgcolor": ink["surface"],
        "font": {"color": ink["secondary"], "size": 13},
        # No `title` key: every caller passes its own title to update_layout(), and having both
        # collides with a TypeError that only surfaces when the page actually renders.
        "title_font": {"color": ink["primary"], "size": 15},
        "xaxis": {"gridcolor": ink["grid"], "linecolor": ink["axis"],
                  "zerolinecolor": ink["axis"], "tickfont": {"color": ink["muted"]}},
        "yaxis": {"gridcolor": ink["grid"], "linecolor": ink["axis"],
                  "zerolinecolor": ink["axis"], "tickfont": {"color": ink["muted"]}},
        "margin": {"l": 8, "r": 8, "t": 40, "b": 8},
        "hoverlabel": {"bgcolor": ink["surface"], "font": {"color": ink["primary"]}},
        "legend": {"font": {"color": ink["secondary"]}},
    }
