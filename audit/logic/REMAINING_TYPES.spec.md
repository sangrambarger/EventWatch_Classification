# Decision specs — the 34 event types completing the rulebook

Companion to the per-type specs already written (`merger_acquisition`, `business_sale`,
`cyber_attack`, `factory_fire`, `chemical_spill`, `leadership_transition`, `earthquake`,
`power_outage`, `tail_types`). Grouped by the family module each type lives in, because members of
a family share a rule shape and what matters for review is where each one **differs**.

**Coverage is now complete: 52 of 52 rulebook entries have a decision module**, and
`registry.coverage()["without_module"]` is asserted empty by a test, so a new event type added to
the approved rules fails the build until it has one.

---

## The shared connection cascade — `connection.py`

Nineteen event types phrase their test almost identically: mapped company → product line →
service vertical. That cascade lives in one function rather than nineteen copies, because
nineteen copies would drift and nobody would notice which.

**Order matters and is taken from the slides:** mapped first (it reports without further tests),
then **service**, then product. Service precedes product because a pure services business often
has no product line to assess, so asking the product question first yields a spurious
`NOT_CONNECTED`.

**A `NOT_CONNECTED` product line alone never drops a row.** The cascade rejects only when the
service question has also been answered — an unanswered limb is not a negative result
(`global-rules.md` #13).

### Mapped = industry relevance (process-owner decision)

> A company relevant to one of the 27 covered industries **counts as a mapped partner.**

This is sharper than `global-rules.md` #4's "treat it as if it were mapped" heuristic and
deliberately supersedes it. #4 left mapped status as a separate unknown that could send a row to
review even when industry relevance was perfectly clear — and those reviews were unanswerable,
because no mapping database exists to answer them. `mapped_party()` resolves in order: an explicit
value → `industry_relevance` → `product_line_connection` → `service_sector_applicability`.

**Two consequences, both intended and both flagged rather than buried:**

1. **Review volume falls sharply.** A row whose industry connection is known no longer stalls on
   an unknowable mapping question.
2. **Hard-mapping event types loosen.** Leadership Transition, Power Outage, Earthquake and
   Bankruptcy's severity branch all gate on mapping, so they now report more than before.
3. **M&A's six-sector bar is genuinely narrowed.** Its point was that a connected product line
   must *not* rescue a retail/hospitality/finance deal — but a connected product line now makes
   the company "mapped", so `MA.R4a` reports it. The bar still bites when the company is not
   industry-relevant, which is the common case, but the distinction the slide drew can no longer
   fire. `test_strict_sector_bar_is_narrowed_by_the_mapped_is_industry_relevance_decision` pins
   this so it cannot regress silently. **This one is worth your explicit ruling.**

---

## Corporate family — Business Spin-off, Company Split, Corporate Restructuring

Standard cascade. Company Split and Corporate Restructuring carry a commodity rider that M&A
words differently, and the difference is preserved:

| | M&A (slide 35) | Company Split / Corporate Restructuring (9, 11) |
|---|---|---|
| Steel | "only if applications match **or a partner is involved**" | "strong product application **or** a partner" |
| Mining | one of six sectors needing mapped/partner | "**only if a partner is involved**" |
| Crude oil | same six-sector bar | "**only if a partner is involved**" |
| Retail / consulting / hospitality / finance / insurance | mapped or partner required | **no such bar** |

So a retail restructuring is reportable on product connection alone; a retail acquisition is not.
Mining and crude have **no product-connection escape** — partner or nothing.

Business Spin-off has no rider and reports completion ("Send updates on completion news"), like
Business Sale and unlike M&A.

**Open question:** Corporate Restructuring's sub-types include "Workforce/employee restructuring",
while Layoffs has its own slide with a far stricter bar ("only notify if a supplier is making
layoffs"). A job-cuts story reaching Corporate Restructuring gets the permissive cascade; reaching
Layoffs it gets the strict one. Real source ambiguity — **needs a ruling.**

---

## Financial family — Bankruptcy, Financial Distress, Profit Warning, Fine, Price Fluctuation

| Type | The qualifier that changes the answer |
|---|---|
| **Bankruptcy** (P1) | Reports at "signs or talks" — earlier than M&A, which sends a rumour to review. Mapped branch pins **HIGH severity**, which matters because Supplier Impact Confirmation is suppressed only for LOW. |
| **Profit Warning** (P3) | **Supplier-only.** Every DO-report bullet says "a supplier". No product-line fallback, so a profit warning from an unconnected listed company is Not Impactful however large. |
| **Financial Distress** (P3) | Also supplier-only, and gated on three named triggers (shareholder withdrawal, rights-issue cancellation/debt refinancing, credit-rating downgrade). |
| **Fine** (P3) | A **settlement** carries a higher bar than a fine: "only for mapped partners or major companies from our verticals", with no plain product-connection route. |
| **Price Fluctuation** (P3) | "Report **only** significant increase or decrease" — a routine price move is out before any connection test runs. |

**Unresolved source conflict, flagged not fixed:** Financial Distress's own slide ends "Classify
it as 'Other.'" while it is a named event type with its own Prioritization Matrix row. Every
verdict from that module carries a note saying so. Plan guardrail 15 says mark a conflict rather
than invent a resolution.

---

## Regulatory family — Compliance, FDA/EMA/OSHA, Regulatory Change, Counterfeit, Recall, Legal Action, Bribery/Corruption, Labor Violation

Eight types on the shared cascade. The exclusions are where the reduction comes from:

- **Counterfeit** has the ruleset's **only explicit product-category exclusion**: "Do not report
  alerts for currency notes, fake luxury goods, counterfeit fashion items." A counterfeit-handbags
  seizure is out however large the brand.
- **Legal Action** has the lowest and most dangerous bar — "notify even if it's a potential legal
  action". Left literal it reports every law-firm deadline-reminder wire release. `global-rules`
  #12 and #14 remove those **upstream in the global gate**, so what reaches this module is a
  genuine new development.
- **Regulatory Change** gates by legislative stage: a proposal-stage bill needs "reputable sources
  indicate significant impact"; a bill past the lower house does not.
- **FDA/EMA/OSHA** is near-universal ("notify any citation by any regulatory agency in the world")
  except **Form 483**, which is carved back out to partners only.
- **Bribery/Corruption** and **Labor Violation** both report state/country-level cases without a
  company test.

---

## Operations family — Factory Disruption, Force Majeure, Supply Shortage, Mine Shutdown

**Factory Disruption is where `global-rules` #6's materiality floor bites.** Its "Future/scheduled
shutdowns" sub-type, read literally, matches any announced maintenance window. #6 narrows it:
routine, long-pre-announced maintenance with no stated cause and no unusual duration is Not
Impactful — and #6 is explicit that this is a **clear** case, not one where safe-default-to-
Impactful applies.

**Force Majeure does the opposite**: "Notify FMs due to maintenance activities or preplanned
activities." A declared FM is itself the reportable act. The difference from Factory Disruption is
whether the source names the planned case explicitly — it does here, it does not there.

**Supply Shortage's multi-tier question runs before the cascade can reject.** "Connect the dots to
multi-tier verticals" with the worked semiconductor/petroleum example. A commodity that looks
unconnected at first tier may connect a tier down, so `multi_tier_connection` is a separate field
and an unanswered one blocks the drop.

**Mine Shutdown** gates coal separately: notify only if power-industry disruption or vertical
disruption is expected.

---

## Transport family — Airport Disruption, Port Disruption, Labor Disruption

The most explicit DO-NOT lists in the ruleset, and they interlock. **Labor Disruption reroutes
port and airport strikes rather than deciding them**, because both destinations apply stricter
tests — an airport strike still has to clear the cargo bar, so deciding it under Labor
Disruption's permissive pre-alert rules would over-report.

**Airport Disruption is cargo-centric, and that removes most of its rows.** Out: passenger-only
disruption, domestic airport with no cargo, minor quickly-resolved disruption, hangar/parking fire
with no flight impact, and a strike ballot with no date set.

**Port Disruption answers the dateless-ballot case the opposite way**: reportable as a bulletin,
but **not WarRoom-eligible**. Same fact pattern, two slides, two answers — both encoded, with a
test asserting the divergence.

**Labor Disruption reports at the earliest possible signal** — intention, pending ballot,
undisclosed locations, future date all qualify. Its only hard exits are a called-off strike (which
inverts to Not Impactful; `global-rules` #5 names this type as one that *does* stand down once
resolved, unlike Factory Fire) and commuter-only disruption.

---

## Natural family — Geopolitical, Protest/Riot and the nine hazards

These eleven gate **regionally** rather than on a company: mapped sites in the region → regional
industrial importance → reported disruptions. Where they differ:

| Type | Difference |
|---|---|
| **Volcano** | **No regional gate at all** — "Notify even if no sites in the region", because ash disrupts aviation far beyond the eruption. Expect near-zero removal; a high Not Impactful rate here means an extraction fault. |
| **Extreme Weather** | The strictest bar in the group. Three "only"s plus "DO NOT REPORT thunderstorms and minor frequent weather disruptions". Needs **both** a regional presence and a reported disruption — except a major named storm, notified proactively. |
| **Flood** | "We can report Flood **Warning** but DO NOT report Flood **Watch** or Flood **Advisory**." Three tiers that read alike in a headline. |
| **Tornado** | A warning alone is a **monitor** state, not a notification; the source reserves notification for a touchdown causing damage. |
| **Environmental Hazard** | Only the **highest (Red)** smog tier qualifies. |
| **Hurricane Pre/Post-Landfall** | Split by lifecycle, and the split is the rule. Neither carries a company-connection test — the storm's projected path is the scope. Pre-Landfall waits for landfall to be certain. |
| **Protest/Riot** | Martial law **reroutes to Geopolitical** ("create a new series under Geopolitical"). |
| **Geopolitical** | Major trade deals and agreements report without a regional site test. |

---

## Verification

143 tests, all passing. Every module was additionally smoke-tested against sparse input (empty
fields, and each `story_nature` value) across all 47 registered names: **zero crashes**, and every
review outcome named a missing field.
