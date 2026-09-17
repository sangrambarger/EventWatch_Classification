# Leadership Transition — decision spec

**Source:** `audit/rules/event-types-manmade.md` § Leadership Transition (slide 33) · **Priority:** P4
**Schema:** none supplied — fields author-derived · **Code:** `logic/leadership_transition.py`

## The strictest event type built so far — the mirror of Chemical Spill

The word "only" appears three times on this slide:

> "Notify **only** when a partner is involved, and sites are mapped"
> "Notify **only** CEO/CFO/COO change"
> "Notify **only** for mapped companies"

| # | Rule | Condition | Outcome | Severity |
|---|---|---|---|---|
| 1 | `LT.R1` | `partner_involved` = `NO` **or** `sites_mapped` = `NO` | **Not Impactful** | LOW |
| 2 | `LT.R2` | either `UNKNOWN` | **Threshold Review** | — |
| 3a | `LT.R3a` | role `OTHER_EXECUTIVE` **and** `supply_chain_department_consequence` = `YES` | **Impactful** | LOW |
| 3b | `LT.R3b` | role `OTHER_EXECUTIVE`, no supply-chain consequence | **Not Impactful** | LOW |
| 3c | `LT.R3c` | role `OTHER_EXECUTIVE`, consequence `UNKNOWN` | **Threshold Review** | — |
| 4 | `LT.R4` | role `UNKNOWN` | **Threshold Review** | — |
| 5 | `LT.R5` | `announced` = `NO` | **Threshold Review** | — |
| 6 | `LT.R6` | CEO/CFO/COO at a mapped partner, announced | **Impactful** | LOW |

Consequences worth confirming:

- **A CEO change at an unmapped company is Not Impactful**, however famous the company.
- **A General Counsel, CMO, CTO or division-head change is Not Impactful even at a mapped
  partner.** The role list is closed. The only way in for another title is rule 3a's explicit
  conditional — "Executive level changes (only if it can lead to changes in the supply chain
  department)" — which turns on a demonstrated supply-chain consequence, never on seniority.
- **Severity is pinned LOW by the source** ("FYI event. Always gauged Low."), which suppresses
  Supplier Impact Confirmation under the global rule. That is a real downstream effect, so it is
  set here rather than guessed later.

This type was ~5% of the feed sample, nearly all appointment announcements at companies with no
mapped-partner relationship — a large, clean removal. Loosening the role list would take most of
that saving back.
