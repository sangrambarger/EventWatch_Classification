# Global Rules — apply to every row, regardless of event type

## 1. Generic Guidelines (source: Slide 58)

- Supplier Impact Confirmation - Global Rule:Send Supplier Impact Confirmation? - YES for all event types.Do NOT send Supplier Impact Confirmation for LOW severity events; it may be issued for MEDIUM, HIGH, and SEVERE events. Event-specific exceptions apply only where explicitly stated.
- Quoting Foreign-Language Articles:Use local media sources for faster, more accurate reporting; prioritize verified local sources that are reputable and independently confirmed.Use key excerpts only when necessary for context and clarity, and include both English and local media sources in the bulletin for reference.
- Sending an Update:Event classifications are based on the cause of disruption, not the outcome - a power outage caused by a hurricane remains under the Hurricane series.Only send updates for new developments, disruptions, or key insights that help risk mitigation: the event's status or impact changes significantly; verified updates suggest supply chain disruptions; news sources provide additional or confirmed insights; companies publicly announce disruptions.
- Using Non-Secure Source Links:Do not use links from non-secure or unverified sources; ensure all sources are reputable and authenticated. Avoid user-generated content unless corroborated by reliable sources.Non-secure links may only be used if no secure sites are available in the public domain to confirm the news, or if they are the only sources confirming the event.Issue notifications only for publicly available disruptions; always follow the Priority matrix when publishing events.

**Most important line above for this audit:** "Event classifications are based on the cause of disruption, not the outcome." Re-derive Event Type from what *caused* the disruption, not from how the story ultimately resolved.

## 2. Severity Gauge (source: Slide 60)

- LOW: Affected company is not mapped on Resilinc platform. There are No sites in the affected region. Minor FYI event just to keep the customers informed (or by nature low risk event e.g. leadership change)
- Medium: Affected company is mapped. Sites are mapped in the affected region. Potential disruptions expected but not confirmed yet
- High: Exact site is mapped and has confirmed disruption publicly. Sites mapped in the affected region has confirmed disruptions publicly. If storm, expected Category at landfall is 4 or 5. Damages have been confirmed. Disruption being reported and confirmed.
- Severe: Big "black swan" event with long-term Worldwide impact. Every industry, every company, every country is impacted one way or the other. Rare events but big e.g. COVID-19 " where recovery time is indefinite

Severity is not itself the binary impactful/not-impactful call, but it is diagnostic: if a row's own facts only support a LOW-severity read (company not mapped/not connected AND no sites in the affected region AND the item is a minor FYI by nature), that is consistent with Not Impactful. Any of Medium/High/Severe should be treated as Impactful.

## 3. Priority tiers are NOT the impact axis

`priority-matrix.md` (P0-P4, from the Event Prioritization Matrix docx) and Slide 59's Immediate-Impact / Mid-to-Long-Term-Impact split both describe **response urgency** — how fast a confirmed-impactful event should be turned around — not whether an event is impactful in the first place. Do not use "this event type is P3/P4" or "this is Mid-to-Long-Term" as a reason to lean toward Not Impactful. A P4 event (e.g. Leadership Transition) that meets its own reporting criteria is still Impactful; it just doesn't need to be notified within the hour.

## 4. Mapped/critical-company heuristic (no supplier-mapping database available)

The source guide constantly conditions on whether a company is a "mapped" supplier on the Resilinc platform (e.g. "if mapped, report straightaway"). This audit has no access to that mapping database, so apply this heuristic instead, per explicit process-owner instruction:
- If the company/site is well-known and clearly important to one of the 27 industries in `industries.md`, treat it as if it were mapped/critical — do not downgrade a major player just because mapped status can't be confirmed.
- Never dismiss a smaller or unfamiliar company purely because it isn't obviously "big." Check the product/commodity/service line for a plausible connection to one of the 27 industries instead — the guide repeatedly treats an unmapped company as a possible unmapped Tier-1/sub-tier supplier when the product line matches, and instructs reporting in that case too.
- If, after checking both company prominence and product/vertical connection, the case is genuinely ambiguous, classify **Impactful** (safe default) rather than Not Impactful.

## 5. Resolved/over events — event-type-specific, never a blanket rule

Do not apply a blanket "if the disruption is over, mark Not Impactful" shortcut. The source guide is explicit that this varies by event type:
- Some types explicitly still report even after the acute event ends — e.g. Factory Fire: "We report a factory fire, even if the articles say it is a small fire or has been extinguished."
- Others explicitly stand down once resolved with no disruption — e.g. Labor Disruption: "Strike Called Off? Mark as Not Impactful." Airport Disruption: "Partial disruptions, no impact on cargo; Operations resumed - Avoid."
Always check the specific event type's own Reporting Guidelines in `event-types-*.md` for how it treats resolution, rather than assuming either way.

## 6. Materiality floor — a technical keyword match is not automatically Impactful

Some DO-report bullets are written broadly (e.g. Factory Disruption's Sub-Types list includes
"Future/scheduled shutdowns"). That bullet exists to catch shutdowns that are themselves the
disruptive event or a company's response to one — not routine, long-pre-announced, business-
as-usual maintenance windows (e.g. an annual planned maintenance shutdown at a plant, announced
months ahead, with no indication of extended duration or connection to any actual problem).
Before classifying Impactful on a "scheduled"/"future"/"planned" keyword match alone, check for
an actual materiality signal: unusual duration, a stated cause tied to a disruption (fire,
labor action, regulatory order, financial distress), or scope beyond ordinary operations. A
title that is purely "Company X's planned annual maintenance shutdown, dates announced," with
nothing else, is Not Impactful — this is a genuinely clear case, not one where the safe-default-
to-Impactful rule (#4) should apply, because "routine and pre-planned with no stated disruption"
is itself a clear signal, not ambiguity.

## 7. Near-duplicate wire stories about the same underlying event

Real-world data includes many near-identical wire-service copies of the same story (the same
factory fire or sabotage campaign reported by 3-9 different outlets, each captured as a separate
row). Every row must still receive its own verdict in the output — never silently drop a row —
but near-duplicate rows describing the *same* underlying event should reach the *same*
classification and, substantively, the same rationale (pointing to the shared underlying event).
Treating duplicates inconsistently (some flagged, some not, purely because different analysts or
different classification passes handled each copy independently) is itself a symptom of the
failure this audit exists to catch, not something to reproduce. Where the workflow includes a
deduplication step before classification, that step is a mechanical grouping by title/entity/date
similarity — it does not decide relevance, it only avoids re-litigating the same fact pattern
independently once per wire copy.

## 8. We report disruptions, not expansions, resumptions, or market commentary (process-owner decision)

EventWatch's job is to catch supply-chain **disruptions and risk signals** — not to report
positive/neutral corporate developments, and not to report the all-clear once a disruption is
over. Three concrete patterns to classify Not Impactful (Event Type: "Irrelevant / Not a
Disruption" — see #9) regardless of company size, industry connection, or dollar amounts
involved:
- **Expansion/growth/investment announcements with no disruption angle.** Example: "Chevron will
  allocate $7 billion over 5 years to double its production in Venezuela" / "Chevron Confirms
  Expansion of Operations in Venezuela." This is Chevron *growing* — a mapped, critical Oil & Gas
  company, a huge dollar figure, and still irrelevant, because nothing is being disrupted. Do not
  let company prominence or headline dollar amounts override the basic question of whether a
  disruption is being described at all.
  **This does NOT reach into Business Sale, Business Spin-off, Merger & Acquisition, or
  Corporate Restructuring** — those are their own explicitly-defined event types in
  `event-types-manmade.md` with their own DO-report criteria (a company being acquired, sold,
  split, or restructured is a real corporate-structure change worth tracking regardless of
  whether it reads as "positive" news), and are governed by that event type's own rules, not by
  this one. Rule #8's "expansion" carve-out is specifically for organic growth/capacity/
  investment announcements that don't correspond to any of the 43 event types at all — not a
  license to wave off an entire category the source guide already covers on its own terms.
- **Resumption/recovery-only follow-ups.** Once a previously-disruptive event is confirmed over
  and operations have resumed normally, a later story whose only content is "operations have now
  resumed" is not independently reportable — it has no new disruption information, only the
  all-clear. (This does not contradict rule #5: reporting the disruption itself, e.g. a factory
  fire, even after it's been extinguished, is about the disruptive event; this rule is about a
  separate, later "we're back to normal now" story with nothing else in it.)
- **Financial/crypto market commentary with no described physical or operational event.**
  Example: "Bitcoin August Rally Is Being Put to the Test With Higher Treasury Yields" — this is
  trading/market-sentiment analysis, not a report of anything happening to a supply chain. No
  company, asset, or price-movement story qualifies for Impactful unless it describes an actual
  physical/operational disruption, not just market reaction to one.

## 9. "Irrelevant" is a labeling convention within Not Impactful, not a third classification

The binary output contract (Impactful / Not Impactful) never changes — do not invent a third
value in the `recommended_classification` field. But content that fails rule #8, or belongs to an
industry/sector explicitly out of scope (see `industries.md`), is qualitatively different from a
genuine, real disruption that simply doesn't clear the bar (e.g. a routine scheduled maintenance
window, rule #6). Distinguish these in the `event_type` field and rationale instead:
- Use an Event Type like "Irrelevant / Not a Disruption" (rule #8 cases) or "Irrelevant / Out of
  Scope Industry" (rule #8/industries.md out-of-scope-sector cases) rather than forcing these into
  one of the 43 real event types.
- This keeps the aggregate Summary sheet able to separate "real events that were correctly/
  incorrectly judged not impactful" from "this was never a candidate event in the first place" —
  the second category should not count toward headline overturn-rate statistics the same way.

## 10. Out-of-scope sectors, expanded (process-owner decisions)

In addition to Tobacco/E-cigarettes (see `industries.md`) and the cannabis/education/municipal-
services/hospitality guidance already there: **Fishing** (commercial fishing/seafood harvesting)
and **hotels in general** (as a hospitality/lodging service, not any food-processing or
manufacturing activity a hotel group might separately run) are confirmed out of scope. As with
the other out-of-scope categories, a specific story that connects to one of the 27 industries
despite the sector label (e.g. a hotel construction project tied to Construction, a fishing
fleet's vessel-building tied to General Manufacturing) is judged on that connection, not
dismissed just for the sector label.

**Carve-in exception (process-owner decision, mirrors Uber in rule #11):** major global
restaurant/QSR chains — confirmed examples: Starbucks, McDonald's, KFC — are **in scope** despite
"restaurants" being a generally out-of-scope hospitality category. These operate at a scale where
their supply chains (coffee, beef, chicken, produce, packaging, franchise distribution networks)
are systemically significant, unlike a generic local restaurant. Treat comparably large, well-
known global restaurant/QSR chains the same way; a small independent restaurant or local chain
still falls under the general hospitality exclusion.

## 11. Uber — confirmed in scope (process-owner decision)

Uber (ride-hailing, Uber Eats delivery, and Uber Freight collectively) is confirmed **in scope** —
treat Uber-related stories as connected to a covered vertical (Freight/Public Transportation-
adjacent, and simply too large and systemically important a logistics/mobility platform to treat
as unconnected) regardless of which specific business line a story focuses on. Do not gate this
on whether a story explicitly names Uber Freight specifically — corporate-wide stories (layoffs,
restructuring, market exits) about Uber as a whole are in scope under this decision.

## 12. Legal Action materiality floor — a new filing vs. a recycled reminder (process-owner decision)

`event-types-manmade.md`'s Legal Action entry says to notify "even if it's a potential legal
action" and "as soon as the trial becomes public" — read literally, that also seems to cover a
law firm's templated "Levi & Korsinsky reminds shareholders of the [date] deadline in the [Company]
class action" press release. It does not. Those are recycled solicitation notices about a lawsuit
that was *already* reported (or should have been, under the original-filing rule) — they contain
no new legal development, just a deadline reminder. Confirmed: classify these Not Impactful
(Event Type: "Irrelevant / Not a Disruption," same as rule #8/#9) regardless of how large or
industry-connected the underlying defendant company is. The Legal Action rule's low bar
("even if potential," "as soon as public") governs *new* filings, settlements, or rulings — not
every subsequent procedural or marketing notice about a suit already in progress. The same logic
applies to any other recurring "reminder/recap of an already-known development" wire pattern
(e.g. a second or third press release restating the same settlement) — the *first* substantive
report of a new legal development is the reportable event; reminders of it are not.

## 13. "No stated industry connection" is not the same as "no information at all"

`industries.md`'s guidance that an absent vertical connection is itself grounds for Not Impactful
assumes the story's subject is actually identifiable — a named company or sector that simply
doesn't map to one of the 27 industries. It does not apply to a row that is just too thin to
identify *anything* (e.g. a bare "structure fire" headline with no company, location detail, or
industry named at all). That second case is not "confirmed unconnected," it's "unknown" — and
rule #4 already says genuine ambiguity defaults to **Impactful**, not Not Impactful. Two
independent classification passes made this exact mistake (collapsing "can't tell" into "no
connection, so Not Impactful") before this rule was added — watch for it specifically: before
citing "no industry connection" as your reason, confirm you actually know what the story is
*about* well enough to say that, not just that the text was short.

## 14. "How Company X Could Address Y Following Z" — check who the real defendant is

A recurring stock-analysis-mill template ("How [Company] Could/May Address [Allegations]
Following [Case]," "[Company] May Find Opportunities Following [Other Company]'s Lawsuit") shows
up constantly in real feed data. It resolves two different ways depending on one fact that
requires reading `story_summary`, not just the title:
- If the named company IS the actual defendant/litigant in a genuine, real legal action — this is
  Legal Action reporting as normal (rule #12's low bar: new filings/rulings are reportable).
- If the named company is an unrelated third party being speculated about in connection with
  *someone else's* case (a "beneficiary" or "cautionary tale" framing with no actual new legal
  action against the named company itself) — Not Impactful, Event Type "Irrelevant / Not a
  Disruption." There is no new legal development for the named company.
This distinction was validated as necessary (not a false-positive worry) via a real accuracy
test: a shallow pass that guessed from the title pattern alone was wrong roughly a third of the
time on this exact template. Reading the summary carefully here is not optional.

## 15. Market-reaction framing of a real event is not the same as market commentary

Rule #8 excludes pure financial/crypto market commentary ("Bitcoin rally tested by Treasury
yields") because no physical or operational event is described at all — the story is entirely
about trading/price movement. Do not over-apply that exclusion to a story that describes a real
geopolitical or physical event and merely *reports its market reaction* alongside it ("US-Iran
clashes drive oil surge, Dow drops 0.7%," a sanctions announcement noted alongside a currency
move). If a real conflict, attack, sanction, or disruption is being described and the market
reaction is color/context rather than the entire subject, classify by the underlying event
(Geopolitical, Regulatory Change, etc.), not by the fact that a price or index is mentioned.

## 16. Enforcement action against illicit actors is not a disruption to us

A law-enforcement or regulatory action *against* an illegitimate operation — an illegal-refinery
raid, a botnet takedown, a counterfeit-goods seizure, a bust of an unlicensed operator — is not a
supply-chain disruption to a legitimate supplier. It's the reverse: authorities disrupting an
illegitimate one. Classify Not Impactful for that specific reason (the "victim" here isn't a real
participant in a covered supply chain) rather than trying to force it into Oil & Gas/Cyber
Attack/etc. by surface keyword match.

