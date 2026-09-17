# Power Outage — decision spec (includes the Software/Internet variant)

**Sources:** `event-types-natural.md` § Power Outage slide 37; `event-types-other.md`
§ Software/Internet Outage slide 55 ("We notify it under Power Outages") · **Priority:** P1
**Schema:** none supplied — fields author-derived · **Code:** `logic/power_outage.py`

The only duration-based bar in the ruleset, and it has three different durations:

| Case | Threshold |
|---|---|
| Semiconductor-fab regions (Taiwan, South Korea, China, Japan, USA, Singapore, Germany, Israel, Netherlands, Malaysia, …) | report **all** outages, even under 6 h |
| Rest of world | longer than **6 h**, or expected to be |
| Software/Internet variant, tech/industrial zones | longer than **3 h** |

## Base Power Outage

| # | Rule | Condition | Outcome |
|---|---|---|---|
| 1 | `PO.R1b` | no mapped sites **and** not an important manufacturing region | **Not Impactful** |
| 2 | `PO.R2` | `semiconductor_fab_region` = `YES` | **Impactful** — duration never consulted |
| 3 | `PO.R3` | `expected_recovery_time_provided` = `NO` | **Impactful** |
| 4 | `PO.R4` | ERT said to be provided but no duration extracted | **Threshold Review** |
| 5 | `PO.R5` | duration > 6 h | **Impactful** |
| 6 | `PO.R6` | duration ≤ 6 h | **Not Impactful** |

## Software/Internet variant

| # | Rule | Condition | Outcome |
|---|---|---|---|
| S1 | `PO.S1` | residential/local user issue | **Not Impactful** |
| S2 | `PO.S2` | mapped site confirms operational impact | **Impactful** |
| S3 | `PO.S3` | resumed within 1–2 h, no confirmed business impact | **Not Impactful** |
| S4 | `PO.S4` | duration > 3 h | **Impactful** |
| S5 | `PO.S5` | duration ≤ 3 h | **Not Impactful** |

## The one place missing data means "notify"

> "We notify if Expected Recovery Time is not provided"

Rule `PO.R3` encodes this literally. It is the **only** rule in the whole ruleset where UNKNOWN
resolves toward Impactful by explicit instruction rather than by the fail-closed default, so it
is deliberately distinguished from `PO.R4`, where a recovery time was said to exist but the
extractor failed to produce a number — that is an extraction gap and goes to review.

What actually removes rows here is rule 1's hard mapped-region gate ("We notify power outages
**only** in a region with sites mapped"), not the duration tests.
