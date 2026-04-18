# Channel Migration — Manual Budget Re-Entry

**Date:** 2026-04-18
**Migration script:** `migrate_channels.py`
**Designed by:** Fazi (original Google Sheets version)
**Applies to:** Both Sheets and PostgreSQL modes

---

## Context

The migration script (`migrate_channels.py`) collapses legacy orphan channels
into the new umbrella channel structure:

| Old (orphan) channel                              | New umbrella channel           |
|---------------------------------------------------|--------------------------------|
| `Performance Marketing (PM)`                      | `Performance Marketing`        |
| `Performance Marketing (PM)-Local Direct Deal (LDD)` | `Performance Marketing`     |
| `Paid Social`                                     | `Performance Marketing`        |
| `Affiliate` (exact match only)                    | `Affiliate - CPA & FF`         |

All **entries** (actual spend, invoices, notes) under the old channels are
safely re-pointed to the equivalent activity under the new umbrella channel.
No entry data is lost.

## Why budgets aren't auto-migrated

By Fazi's design, the **budget $ value set on the old channel** is NOT
carried over automatically. The script's docstring states:

> "Reports LDD channel's budget ($ amount) so admin can decide whether to
> add it to the umbrella's budget manually."

The reason is that the new umbrella channel may already have its own
independent budget. Blindly summing or replacing could double-count or
overwrite the admin's intended total. Instead, the script prints every
non-zero orphan-channel budget as a warning, leaving the decision to the
admin.

## Budget values requiring re-entry (from 2026-04-18 dry-run)

These 8 orphan channels had non-zero budgets. After the migration runs, the
channel records themselves are deleted — their $ amounts need to be
re-applied to the corresponding new umbrella channel.

| Market | Quarter | Source (old) channel                       | Budget ($) | Destination (new) channel   |
|--------|---------|--------------------------------------------|------------|-----------------------------|
| HKG    | Q4      | Performance Marketing (PM)                 | 155,000    | Performance Marketing       |
| CN     | Q4      | Performance Marketing (PM)                 | 328,000    | Performance Marketing       |
| TW     | Q4      | Performance Marketing (PM)                 | 150,000    | Performance Marketing       |
| TH     | Q4      | Performance Marketing (PM)                 | 100,500    | Performance Marketing       |
| VN     | Q4      | Performance Marketing (PM)                 |  63,900    | Performance Marketing       |
| CN     | Q4      | Performance Marketing (PM)-Local Direct Deal (LDD) | 60,000 | Performance Marketing |
| PH     | Q1      | Paid Social                                |  30,000    | Performance Marketing       |
| PH     | Q1      | Affiliate                                  |  20,000    | Affiliate - CPA & FF        |

**Total budget impact:** $907,400

> Note: the list above is from the **local** dry-run. The production dry-run
> (run against RDS just before `--commit`) should match closely, but verify
> the exact figures against the prod dry-run output before re-entering.

## Decisions the owner needs to make

For each row above, the admin must decide one of:

1. **Set** — the new umbrella channel has no budget set yet; use the value directly.
2. **Add** — the new umbrella channel already has a budget; add the old value on top (consolidated total).
3. **Skip** — the old value is no longer valid / already accounted for elsewhere (document why).

Recommended: verify each umbrella channel's current budget first via the
Config UI before deciding per row.

## Re-entry steps (Config UI)

For each row in the table above:

1. Open the app (https://budget.pepperstone-asia.live).
2. Log in with an admin account.
3. Go to **Config → Channels**.
4. Filter by the market and quarter listed.
5. Locate the destination channel (`Performance Marketing` or `Affiliate - CPA & FF`).
6. Click Edit, set/update the budget field using the decision above, save.
7. Verify the new value appears on the main dashboard's planned-vs-actual view.

## Verification after re-entry

- Market-level Q4 variance (planned - actual) for HKG/CN/TW/TH/VN should no
  longer be missing the old PM/LDD budget.
- PH/Q1 Paid Social + Affiliate budgets are accounted for under the new
  umbrella/Affiliate channels.
- Run a sanity check against the prior reporting snapshot (pre-migration
  planned totals per market/quarter) to confirm no drift.

## Rollback

If the manual budget re-entry causes issues, individual values can be
edited back through the same Config UI — no script rollback needed.

If the whole migration needs to be reverted (data-level rollback), restore
from the RDS snapshot `budget-flask-pre-migrate-2026-04-18` taken before
the migration ran.

## Questions to confirm with owner (Fazi)

- [ ] Is the design intent of "admin decides per row" still correct, or would a default behavior (e.g. always replace) be preferred going forward?
- [ ] Should the script auto-email or log these warnings to a durable location (not just stdout), so they aren't missed on rerun?
- [ ] For the $60,000 LDD budget on CN/Q4: should this be added to CN/Q4 Performance Marketing, or tracked as a separate `LDD` activity-level budget (if/when the schema supports activity budgets)?
