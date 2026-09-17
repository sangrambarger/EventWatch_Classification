"""The supply-chain connection cascade, shared by the event types that all ask the same question.

Roughly nineteen of the rulebook's event types phrase their reporting test in the same shape,
almost word for word — Business Spin-off, Company Split, Corporate Restructuring, Bankruptcy,
Compliance, Fine, Legal Action, Recall, Price Fluctuation, Supply Shortage, Profit Warning,
Bribery/Corruption, Counterfeit, Labor Violation, FDA/EMA/OSHA Action, Force Majeure,
Environmental Hazard, Factory Disruption and Mine Shutdown:

> "For a mapped company - Send an impact with the initial bulletin.
>  If the company is not mapped - Send a bulletin if products have applications in the industries
>  we cover. Possible sub-tier or Tier 1 yet to be mapped (decide based on product line)
>  Services sector? Check if serving into the verticals we cover"

Writing that out nineteen times would guarantee drift: one copy would grow an extra branch, one
would forget that UNKNOWN is not NO, and nobody would notice which. So the cascade lives here
once and each event type supplies its own verbatim source lines and its own extra gates.

What this helper deliberately does **not** do is decide anything an event type says differently.
It returns `None` when the cascade cannot answer, so the caller keeps control of its own quirks —
M&A's six strict sectors, Chemical Spill's "notify even if no sites are mapped", Leadership
Transition's closed role list. Those are real differences between slides, not noise to normalise.
"""

from __future__ import annotations

from typing import Mapping

from .base import (
    IMPACTFUL,
    NOT_IMPACTFUL,
    THRESHOLD_REVIEW,
    UNKNOWN,
    Decision,
    evidence,
    get,
)

YES_NO = frozenset({"YES", "NO"})
PRODUCT_CONNECTION = frozenset({"CONNECTED", "NOT_CONNECTED"})
SERVICE_APPLICABILITY = frozenset({"APPLICABLE", "NOT_APPLICABLE", "NOT_A_SERVICE_SECTOR"})

#: The field names every cascade-using module shares, so a row extracted for one event type can
#: be re-decided under another without re-extraction (which is what makes rerouting safe).
CASCADE_FIELDS = (
    "mapped_or_prominent_party_involved",
    "product_line_connection",
    "service_sector_applicability",
)

MAPPED_HEURISTIC = (
    "global-rules.md #4: If the company/site is well-known and clearly important to one of the 27 "
    "industries, treat it as if it were mapped/critical. Never dismiss a smaller or unfamiliar "
    "company purely because it isn't obviously 'big' — check the product/commodity/service line "
    "for a plausible connection instead."
)

INDUSTRY_RELEVANCE = frozenset({"RELEVANT", "NOT_RELEVANT"})

#: Process-owner decision, recorded here because it changes the meaning of "mapped" everywhere.
MAPPED_IS_INDUSTRY_RELEVANCE = (
    "Process-owner decision: a company relevant to one of the 27 covered industries counts as a "
    "mapped partner. No supplier-mapping database is available to this pipeline, so industry "
    "relevance is the operative test, not a proxy for one."
)


def mapped_party(fields: Mapping[str, object]) -> str:
    """Resolve mapped-partner status for any rule that gates on it.

    Per the process-owner decision above, **a company relevant to our covered industries is a
    mapped partner.** That is a sharper rule than `global-rules.md` #4's "treat it as if it were
    mapped" heuristic, and it deliberately supersedes it: #4 left mapped status as a separate
    unknown that could send a row to review even when industry relevance was perfectly clear, and
    those reviews were unanswerable because no mapping database exists to answer them.

    Resolution order:

    1. An explicit `mapped_or_prominent_party_involved` value, if extraction produced one.
    2. Otherwise `industry_relevance` — the direct expression of the rule.
    3. Otherwise `product_line_connection`, which is how relevance is judged when the industry is
       not named outright.

    The practical effect is a large reduction in review volume: a row whose industry connection is
    known no longer stalls on an unknowable mapping question. It also loosens the event types that
    gate hard on mapping (Leadership Transition, Power Outage, Bankruptcy's severity branch), so
    those will report more than they did under the earlier reading. That is the intended
    consequence of the decision, not a side effect — it is called out in each affected spec.
    """
    explicit = get(fields, "mapped_or_prominent_party_involved", allowed=YES_NO)
    if explicit != UNKNOWN:
        return explicit

    industry = get(fields, "industry_relevance", allowed=INDUSTRY_RELEVANCE)
    if industry == "RELEVANT":
        return "YES"
    if industry == "NOT_RELEVANT":
        return "NO"

    product = get(fields, "product_line_connection", allowed=PRODUCT_CONNECTION)
    if product == "CONNECTED":
        return "YES"
    if product == "NOT_CONNECTED":
        return "NO"

    service = get(fields, "service_sector_applicability", allowed=SERVICE_APPLICABILITY)
    if service == "APPLICABLE":
        return "YES"

    return UNKNOWN


def connection_cascade(
    fields: Mapping[str, object],
    *,
    rule_prefix: str,
    source: str,
    mapped_line: str,
    product_line: str,
    service_line: str,
    warroom_when_impactful: bool = True,
    severity_when_mapped: str | None = None,
) -> Decision | None:
    """Run the shared mapped → product → service test.

    Returns a `Decision` when the cascade answers, or `None` when the caller must decide (which
    happens only when every input is `UNKNOWN`, so the caller can add its own fallbacks before
    falling through to review).

    Ordering follows the source slides: mapped status first (it reports without further tests),
    then the service-vertical check, then the general product test. Service is checked before
    product because a pure services business frequently has no product line to assess at all, so
    asking the product question first would produce a spurious NOT_CONNECTED.
    """
    mapped = mapped_party(fields)
    product = get(fields, "product_line_connection", allowed=PRODUCT_CONNECTION)
    service = get(fields, "service_sector_applicability", allowed=SERVICE_APPLICABILITY)

    if mapped == "YES":
        return Decision(
            classification=IMPACTFUL,
            rule_id=f"{rule_prefix}.MAPPED",
            rule_text=mapped_line + "  ||  " + MAPPED_IS_INDUSTRY_RELEVANCE,
            source=source,
            threshold_met=True,
            severity=severity_when_mapped,
            warroom_eligible=warroom_when_impactful,
            evidence=evidence(
                fields,
                "mapped_or_prominent_party_involved",
                "industry_relevance",
                "product_line_connection",
            ),
        )

    if service == "APPLICABLE":
        return Decision(
            classification=IMPACTFUL,
            rule_id=f"{rule_prefix}.SERVICE",
            rule_text=service_line,
            source=source,
            threshold_met=True,
            warroom_eligible=warroom_when_impactful,
            evidence=evidence(fields, "service_sector_applicability"),
        )

    if product == "CONNECTED":
        return Decision(
            classification=IMPACTFUL,
            rule_id=f"{rule_prefix}.PRODUCT",
            rule_text=product_line,
            source=source,
            threshold_met=True,
            warroom_eligible=warroom_when_impactful,
            evidence=evidence(fields, "product_line_connection"),
        )

    # Only reject once the cascade has actually been answered. A NOT_CONNECTED product line with
    # an unanswered service question is not a negative result (global-rules #13) — for a services
    # business the product test is the wrong question, so its answer cannot close the cascade.
    if product == "NOT_CONNECTED" and service in {"NOT_APPLICABLE", "NOT_A_SERVICE_SECTOR"}:
        return Decision(
            classification=NOT_IMPACTFUL,
            rule_id=f"{rule_prefix}.NONE",
            rule_text=product_line + "  ||  " + service_line,
            source=source,
            threshold_met=False,
            warroom_eligible=False,
            evidence=evidence(fields, *CASCADE_FIELDS),
        )

    if service == "NOT_APPLICABLE" and product == UNKNOWN:
        return Decision(
            classification=THRESHOLD_REVIEW,
            rule_id=f"{rule_prefix}.REVIEW",
            rule_text=product_line,
            source=source,
            missing_fields=("product_line_connection",),
            evidence=evidence(fields, "mapped_or_prominent_party_involved",
                              "service_sector_applicability"),
        )

    return None


def unresolved_cascade(
    fields: Mapping[str, object],
    *,
    rule_prefix: str,
    source: str,
    rule_text: str,
    extra_fields: tuple[str, ...] = (),
) -> Decision:
    """The standard fall-through: name every cascade field still unanswered.

    Used by callers after `connection_cascade` returns None and their own extra gates have also
    failed to answer. Records the fail-closed operational default so Ops keeps an actionable
    verdict while the row waits in the review queue.
    """
    candidates = CASCADE_FIELDS + extra_fields
    missing = tuple(name for name in candidates if get(fields, name) == UNKNOWN)
    return Decision(
        classification=THRESHOLD_REVIEW,
        rule_id=f"{rule_prefix}.UNRESOLVED",
        rule_text=rule_text + "  ||  " + MAPPED_HEURISTIC,
        source=source,
        missing_fields=missing or ("product_line_connection",),
        evidence=evidence(fields, *(n for n in candidates if get(fields, n) != UNKNOWN)),
        notes=("Fail-closed operational default under global-rules #4 is Impactful.",),
    )
