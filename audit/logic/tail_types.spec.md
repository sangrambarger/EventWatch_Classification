# Layoffs · Airworthiness · Mail/Postal · Others — decision specs

Four low-volume event types with no supplied extraction schema. Grouped in one document because
each has a single governing rule; code in `logic/{layoffs,airworthiness,mail_postal_delivery,others}.py`.

## Layoffs — `event-types-other.md` slide 49 · priority inherited from Labor Disruption (P2)

| # | Rule | Condition | Outcome |
|---|---|---|---|
| 1 | `LO.R1` | `supplier_making_layoffs` = `NO` | **Not Impactful** |
| 2 | `LO.R2` | unknown | **Threshold Review** |
| 4 | `LO.R4` | a supplier is making layoffs, any nature | **Impactful** |

> "**Only** notify if a supplier is making layoffs"

No product-connection fallback, no industry test, no unmapped-sub-tier rescue of the kind Factory
Fire and M&A both offer. **A famous company laying off thousands is Not Impactful unless it is a
supplier.** In the feed sample this type was mostly automaker job-cut stories, so the strictness
matters to the funnel.

Counterweight: "Notify even if layoffs are scheduled for future." `global-rules.md` #6's
materiality floor deliberately does **not** apply here — this slide names future layoffs as
reportable outright, so applying #6 would contradict the source.

## Airworthiness — slide 48 · priority inherited from Compliance (P3)

**The only notify-always type. It has no Not Impactful branch, and that absence is the rule.**

> "Notify every AD on a daily basis" · "Notify even if the company receiving the AD is not mapped"

| # | Rule | Condition | Outcome |
|---|---|---|---|
| 1 | `AW.R1` | unclear whether an AD was issued | **Threshold Review** |
| 2 | `AW.R2` | no AD issued | **Reroute to Compliance** — not rejected |
| 3 | `AW.R3` | AD issued | **Impactful**, `warroom_eligible=False` |

Two operational facts that matter to the funnel: "Notify via 1 consolidated bulletin ... around
midday PST", so **N rows produce one artefact** and counting them as N units of analyst work
overstates the burden (`CONSOLIDATES_INTO` marks this); and "Customer Impact is not needed", so
every row is reportable yet none is WarRoom-eligible.

## Mail/Postal/Package Delivery — slide 47 · priority inherited from Labor Disruption (P2)

| # | Rule | Condition | Outcome |
|---|---|---|---|
| 1 | `MP.R1` | `sites_in_country` = `NO` | **Not Impactful** |
| 4a | `MP.R4a` | bankruptcy/sale of a **non-major** operator | **Not Impactful** |
| 5 | `MP.R5` | `disruption_kind` = `NONE_OF_THESE` | **Not Impactful** |
| 6 | `MP.R6` | any listed disruption, sites in country | **Impactful** |

The gate is **country-level**, unusually coarse — every other event type gates on a site, region
or company. The slide expects overlap with Labor Disruption, Port Disruption and Factory
Disruption rather than exclusive ownership of the row, so `decide()` claims no exclusivity; an
overlapping row gets the same Impactful answer from either module. Only "Major postal service
going bankrupt or getting sold" carries a size qualifier; a minor operator's sale may still
qualify under Business Sale on its own criteria, and `MP.R4a` says so on the verdict.

## Others — slide 51 · P4

**Resolves nothing. Every surviving row goes to `Needs Context Review`.**

The source gives no DO-report criteria beyond "we had nowhere else to put it", so there is no
threshold to apply and no automatic verdict would be honest. Two reasons this matters more than
its volume suggests:

1. `Others` is an attractive dumping ground. With no rejecting criteria, every row landing here
   would come out Impactful and the funnel would grow an unexplained bulge of low-value events.
2. **The size of this queue is a quality signal for the event-type classifier**, not a backlog to
   clear by auto-reporting. The dashboard should surface it that way.

The global gate still runs first, so plain non-events (market commentary, expansions, enforcement
against illicit actors) are still removed here rather than parked in the queue.
