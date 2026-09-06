# Validation Cases — 8 real historical "wrongly marked Not Impactful" misses

These are hand-transcribed (not build-script-generated) from
`EventWatch_Customer_Complaints/customer_tracker.csv`, where they exist today only as free-text
narrative buried in the `Comments` / `Automation Opportunity` columns of a downstream complaints
log — not as a structured classification dataset. All 8 share `Standard Automation Focus =
"WarRoom & Decision Validation"`, i.e. Resilinc's own team has already recognized these as the
same failure pattern this skill exists to catch.

**Honesty note on evidentiary basis:** the complaints tracker records the *outcome* of each miss
(a customer complained, RCA was shared, the event was re-evaluated) via retrospective comments,
not the original `Story Title` + `Story Summary` the analyst actually saw at decision time. Run
`scripts/run_audit.py --validate` using the reconstructed title + context below as a stand-in for
that missing original summary. This is a reasonable proxy for regression-testing whether the
ruleset in `references/*.md` would flag the right *kind* of story, but it is not a substitute for
validating against the real `NotImpctful Events.xlsx` once it's supplied — say so plainly in any
validation report rather than treating this as end-to-end proof.

Expected outcome for all 8: **Impactful**.

---

## Case 1 — GM / OFAC Hormuz sanctions alert

- **Reconstructed title:** "OFAC Alert: Sanctions Risks of Iranian Demands for Strait of Hormuz Passage"
- **Customer:** GM (2026-05-07)
- **Context:** An OFAC (US sanctions body) alert concerning Iranian threats to close/restrict the
  Strait of Hormuz — a critical global shipping chokepoint for oil/gas and general cargo.
- **Analyst's actual failure (verbatim from tracker):** "Feeds captured but classified as not
  impactful; NI review missed. Re-evaluated and published."
- **Expected Event Type:** Geopolitical (sanctions/strait-passage risk affecting shipping lanes).
- **Rule that should catch it:** `event-types-manmade.md` Geopolitical — "Notify major trade
  deals and agreements," unrest/economic-crisis triggers; the Strait of Hormuz is a major
  shipping chokepoint feeding Oil & Gas, Freight, and virtually every other vertical downstream —
  this is exactly the "important region even without a mapped site" case global-rules.md #4
  describes. A regulatory/sanctions alert on a chokepoint this significant should never resolve
  to Not Impactful regardless of whether any single company is confirmed mapped.

## Case 2 — Eaton / Burnstein von Seelen precision casting disruption

- **Reconstructed title:** "Burnstein von Seelen Precision Casting Operational Disruption"
- **Customer:** Eaton (2026-06-05)
- **Context:** An operational disruption at a precision-casting supplier (metal
  casting/components manufacturer — General Manufacturing / Automotive-adjacent vertical).
- **Analyst's actual failure (verbatim):** "RCA shared; analyst classified event as Not
  Impactful. Event was successfully received and reviewed but incorrectly classified and
  therefore not escalated."
- **Expected Event Type:** Factory Disruption (or Factory Fire if the disruption was fire-caused
  — insufficient detail survives in the tracker to distinguish; either resolves the same way).
- **Rule that should catch it:** `event-types-manmade.md` Factory Disruption — "If a non-mapped
  partner announces closure, report if the product line and applications match our verticals.
  Assume it's a possible sub-tier or a T1 yet to be mapped." Precision casting feeds directly
  into Automotive/General Manufacturing supply chains; global-rules.md #4's product-connection
  check should override any uncertainty about mapped status.

## Case 3 — Western Digital / Nidec Chaun Choung Technology ransomware attack

- **Reconstructed title:** "Nidec Chaun Choung Technology Suffers Ransomware Attack"
- **Customer:** Western Digital (2026-06-24)
- **Context:** A ransomware attack at a precision component manufacturer supplying High
  Tech/Consumer Electronics (Nidec Chaun Choung makes thermal/mechanical components for hard
  drives and electronics — directly in Western Digital's supply chain).
- **Analyst's actual failure (verbatim):** "RCA prepared; analyst impact-assessment failure
  identified... incorrectly assessed as Not Impactful during analyst review and therefore not
  escalated."
- **Expected Event Type:** Cyber Attack.
- **Rule that should catch it:** `event-types-manmade.md` Cyber Attack — "Notify if the affected
  company(s) serves our customer industries. Possible unmapped sub-tier/T1 site yet to be mapped
  by the customers... Notify all kinds of hacks, breaches, ransomware, attacks." This is a
  textbook example of the exact rule the analyst missed.

## Case 4 — Ford / FXI Foam Manufacturing fire (Cuautitlan, Mexico)

- **Reconstructed title:** "Fire at FXI Foam Manufacturing Plant in Cuautitlan, Mexico"
- **Customer:** Ford (2026-07-06)
- **Context:** A fire at a Tier-2 foam manufacturing supplier triggering a Force Majeure
  declaration; customer reported it, no matching EventWatch WarRoom/notification was found at all
  (a capture/notification gap, not just a misclassification, per the tracker comment).
- **Analyst's actual failure (verbatim):** "Customer reported fire at FXI (Tier 2 supplier)
  causing Force Majeure... No matching EventWatch notification/WarRoom found."
- **Expected Event Type:** Factory Fire (with a Force Majeure angle once FM is declared).
- **Rule that should catch it:** `event-types-manmade.md` Factory Fire — "Report factory fires
  proactively... even if the articles say it is a small fire or has been extinguished... If a
  fire breaks out at a non-mapped factory/warehouse, notify if the product line of the company is
  relevant to our industrial verticals. Assume it's a possible sub-tier or a T1 yet to be
  mapped." Foam manufacturing feeds directly into Automotive interiors/seating.

## Case 5 — Ford / New World International Co. factory fire (Thailand)

- **Reconstructed title:** "New World International Co. Factory Fire, Thailand"
- **Customer:** Ford (2026-07-08)
- **Context:** A factory fire destroying production/storage facilities at a supplier.
- **Analyst's actual failure (verbatim):** "Feeds were received and event was reportedly marked
  Not Impactful despite destruction of production/storage facility. Investigation ongoing."
- **Expected Event Type:** Factory Fire.
- **Rule that should catch it:** Same Factory Fire rule as Case 4. "Destruction of
  production/storage facility" is about as unambiguous a High-severity signal (per
  `global-rules.md` #2 Severity Gauge: "confirmed disruption publicly... Damages have been
  confirmed") as exists in the entire ruleset — there is no reading of the guide under which this
  resolves to Not Impactful.

## Case 6 — Ford / China MOFCOM Announcement No. 30 of 2026

- **Reconstructed title:** "China MOFCOM Announcement No. 30 of 2026"
- **Customer:** Ford (2026-08-11)
- **Context:** A Chinese Ministry of Commerce regulatory announcement (export-control /
  trade-regulation class of event, given the source and framing).
- **Analyst's actual failure (verbatim):** "EAO-23: News was captured but initially classified
  as Not Impactful by AI. Human-in-the-loop review did not escalate the event."
- **Expected Event Type:** Regulatory Change.
- **Rule that should catch it:** `event-types-manmade.md` Regulatory Change — "We notify
  regulatory changes when there are reports of: New laws, rules, or regulations... Changes in
  import-export regulations... Bans on commodities, companies, and regions." Also note this is
  the one case in the 8 where the *upstream* AI tag itself was wrong (Not Impactful, not just the
  human reviewer) — directly supporting the plan decision to have this skill independently
  re-derive Event Type/classification rather than trust either the upstream tag or the analyst.

## Case 7 — Ford / Nemak factory fire (Monterrey, Mexico)

- **Reconstructed title:** "Fire at Nemak Factory in Monterrey, Mexico"
- **Customer:** Ford (2026-08-24)
- **Context:** A fire at Nemak, a major automotive aluminum-components manufacturer (engine
  blocks, cylinder heads, structural components) — a well-known Tier-1 automotive supplier.
- **Analyst's actual failure (verbatim):** "EAO-25: ...The event was later marked Not Impactful
  by the analyst. RCA shared based on the investigation trail."
- **Expected Event Type:** Factory Fire.
- **Rule that should catch it:** Same Factory Fire rule as Cases 4-5. Nemak is a large,
  well-known Tier-1 automotive supplier — `global-rules.md` #4's "well-known and clearly
  important to one of the 27 industries -> treat as mapped/critical" applies directly, independent
  of whether platform-mapped status could be confirmed.

## Case 8 — Merck / Baxter International cybersecurity incident

- **Reconstructed title:** "Baxter International Reports a Cybersecurity Incident"
- **Customer:** Merck (2026-08-31)
- **Context:** A cybersecurity incident at Baxter International, a major medical
  devices/healthcare products manufacturer.
- **Analyst's actual failure (verbatim):** "...human review incorrectly marked it Not Impactful;
  the event was re-evaluated, a WarRoom was created, and an NC was raised."
- **Expected Event Type:** Cyber Attack.
- **Rule that should catch it:** `event-types-manmade.md` Cyber Attack, same rule as Case 3.
  Baxter is a large, well-known Healthcare/Life Sciences manufacturer — again
  `global-rules.md` #4 applies directly regardless of confirmed mapping status.
