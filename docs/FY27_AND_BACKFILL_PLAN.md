# FY27 Support + Q1–Q3 FY26 Backfill — Working Plan

Two independent workstreams, split across two sessions.
Created 2026-07-09. Owner: Terence.

- **Session A — FY27 support**: app code change (feature branch). Makes the app
  fiscal-year-aware instead of hardcoded to FY26.
- **Session B — Q1–Q3 FY26 backfill**: data operation (one-time script). Loads
  the FY26 Tracking-tab line items into the `entries` table.

They are decoupled by one rule (see **Coupling** below), so either can land first.
Recommended order: **A then B**.

---

## Background: why both are needed

- Today is in **FY27** (Pepperstone FY = Jul–Jun; FY27 = Jul 2026 → Jun 2027).
- The app is **hardcoded to FY26** in several places, so FY27 data entry currently
  fails or would collide with FY26. → Session A.
- Q1–Q3 FY26 line-item detail lives only in the Excel tracker, not fully in the DB
  (the DB has PM-synced actual-only rows for Q1–Q3). → Session B.

---

## Source data (for Session B backfill)

File: `~/Downloads/APAC (ALL)_Regional_Marketing Budget Tracker.xlsx`

- **`Tracking` tab — THE source of truth.** 625 flat line-items, header on **row 28**,
  data rows 29–655. FY26 (Jul 2025–Jun 2026), 12 countries.
  Columns: A=Country, B=Month (datetime), C=Quarter, D=BU, E=Finance Category,
  F=Marketing Category, G=Description, H=Planned&Approved, I=Confirmed&Estimated,
  J=Actual, K=Description/Notes, L=JIRA task, M=Vendor name.
  Maps ~1:1 onto the `entries` table.
  - Planned by quarter: Q1 2,752,401 · Q2 2,958,085 · Q3 2,511,459 · Q4 2,677,405 (total 10.9M)
  - Actual by quarter:  Q1 2,349,742 · Q2 1,640,043 · Q3 1,652,189 · Q4 172,682 (total 5.81M)
  - Cross-check: Tracking Q4 planned (2,677,405) == current `budgets` Q4 in RDS. Confirms
    this tab is the source the DB budgets came from.
- **`Confirmed and approved budget` tab** — a pivot summary (category × quarter, all
  countries). Aggregate only → use as a reconciliation check-total, not a data source.
- `~/Downloads/FY26_Marketing_Budget_Overview (Final).html` — a standalone interactive
  dashboard (editable cells, session-save, CSV export). An **output artifact, not data.**

### Backfill obstacles (decisions already made / to resolve)
1. **No channel/activity structure** in the sheet (89 distinct marketing cats). Entries
   need Country→Channel→Activity. Reuse the upload logic (`api_uploads._apply_keyword_mapping`
   + auto-create channel/activity) or map explicitly.
2. **Existing Q1–Q3 rows in DB** = PM-synced actual-only (planned=0). Naive insert would
   duplicate actuals and re-trigger the BUC/PM dedup problem. → **Decision: inspect prod
   read-only first**, then choose wipe-reload vs merge.
3. **`HKG` → `HK`** normalization (118 HKG rows in the sheet). Same trap that caused past dupes.
4. **Category mapping** — 89 marketing cats → app `DEFAULT_MKT_CATS` / `DEFAULT_FIN_CATS`
   (see `config.py`).

### Session B first step (READ-ONLY audit)
- Connect to RDS per `docs/INFRASTRUCTURE.md` "Temporary public access"
  (and memory `reference_rds_access.md`). DATABASE_URL in Secrets Manager
  `budget-flask/database-url`.
- Report: row counts per quarter in `entries`; which Q1–Q3 rows are PM-synced actual-only;
  any HKG rows; **and whether `budgets.fiscal_year` column actually exists in prod**
  (see Coupling / Session A note — the code requires it but `ensure_schema` doesn't add it).
- Then propose reconcile plan + backup CSV, get approval, run the script.

---

## Session A: FY27 support (code)

Branch: `feat/fy-aware` (off `main`; note working branch may currently be `feat/shared-portal-db`).

Hardcoded-FY26 spots to fix:
- `config.py`
  - `MONTH_TO_QUARTER` (year-agnostic dict, fine) but `MONTH_KEY_MAP`, `MONTH_SHORT`,
    `VALID_MONTH_KEYS` only cover Jul 2025–Jun 2026. → generate from a `CURRENT_FY`
    (or support a set of active FYs) instead of a fixed dict.
  - Add `CURRENT_FY` + helper to derive FY from a month key (Jul→Jun boundary).
- `db.py`
  - `upsert_budget` hardcodes `'FY26'` and uses `ON CONFLICT (country, quarter, fiscal_year)`.
    Replace hardcoded FY with the passed/derived FY.
  - `ensure_schema()` does **not** add `fiscal_year` anywhere. Add idempotent ALTERs:
    `fiscal_year` on `budgets` (already needed by upsert!), `channels`, `activities`,
    `entries` — all `DEFAULT 'FY26'` so existing rows backfill to FY26.
  - channels/activities/entries currently key on bare `quarter` (Q1–Q4). Include
    `fiscal_year` in inserts/queries/unique keys so FY27 Q1 ≠ FY26 Q1.
- `schema.sql` — add `fiscal_year` columns + update unique keys so a fresh DB matches prod.
- `api_uploads.py` — month validation rejects anything outside FY26 (`VALID_MONTH_KEYS`,
  message "expected YYYY-MM in FY26 range"). Generalize to active FY range.
- `export_xlsx.py` / `app.py` — export filenames & headers say `FY26`; derive from FY.
- `apply_pm_fix.py` — activity auto-naming `"{Country} FY26 {Quarter}"` → derive FY.
- Verify end-to-end: enter an FY27 (e.g. 2026-07) entry; confirm it saves, is quartered
  correctly, and does not collide with FY26 rows.

### ⚠️ Known loose end to confirm in prod
`db.py:upsert_budget` already references `budgets.fiscal_year`, but neither `schema.sql`
nor `ensure_schema()` creates it. So the column exists in prod only if it was added to RDS
by hand. Session A's `ensure_schema` ALTER (IF NOT EXISTS) makes this safe & reproducible.

---

## Coupling (keeps A and B safe in any order)
- Session A's `entries.fiscal_year` migration **must default existing rows to `'FY26'`**.
- Session B's backfill sets `fiscal_year='FY26'` on inserted rows **if the column exists**,
  else ignores it.
- With this, neither session corrupts the other regardless of order.

## Infra / access
- RDS temp access SOP: `docs/INFRASTRUCTURE.md` + memory `reference_rds_access.md`.
- Deploy: ECS Fargate (see memory `project_ecs_deployment.md`). App runs PostgreSQL mode.
- One-off data ops: direct DB script, not a new endpoint (per project convention).
