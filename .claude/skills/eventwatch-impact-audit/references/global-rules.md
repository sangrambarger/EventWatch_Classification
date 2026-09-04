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

