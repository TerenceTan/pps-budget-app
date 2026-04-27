# High-Level Design — APAC Marketing Budget Tracker

## 1. Purpose
A Flask-based web application that lets the APAC marketing team plan, track, and reconcile quarterly marketing budgets across 12 markets (CN, HK, ID, IN, MN, MY, PH, SG, TH, TW, VN, APAC). Outputs feed directly into finance reconciliation in the standard finance Excel format.

## 2. Users & Roles

| Role | Access |
|---|---|
| **admin** | Full read/write across all markets, config management, user management |
| **editor** | Read/write for assigned markets (or `ALL`); can manage channels and activities |
| **country** | Read/write for one or more specific markets only |

Examples: `pepper` (admin), `affiliate` / `performance` / `campaigns` (editors with ALL), `th_sales` / `cn_sales` / `roapac_sales` (country users).

## 3. System Context

```
                    ┌─────────────────┐
                    │   BigQuery      │
                    │  ad_performance │ ←── Performance Marketing actuals
                    └────────┬────────┘
                             │
          ┌──────────────────┴────────────────┐
          │                                   │
   ┌──────▼──────┐                    ┌───────▼────────┐
   │  Flask App  │ ←── manual entry ──│   End Users    │
   │  (Python)   │                    │  (Browser UI)  │
   └──────┬──────┘                    └────────────────┘
          │
   ┌──────▼──────────────────────────────────┐
   │  Storage (storage-agnostic abstraction) │
   │   ├── Local dev: Google Sheets          │
   │   └── Production (AWS): PostgreSQL      │
   └──────┬──────────────────────────────────┘
          │
   ┌──────▼──────┐
   │  Finance    │ ←── monthly/quarterly XLSX export
   │  Excel      │
   └─────────────┘
```

## 4. Core Concepts

### 4.1 Channel Structure
Two **auto-managed umbrella channels**:
- **Performance Marketing** — all paid digital (Meta, TikTok, Bing, Apple Search Ads, Douyin, RedNote, BiliBili, WeChat, Kuaishou, TA Media, AdRoll, TradingView, Others, LDD)
- **Affiliate - CPA & FF** — all affiliate spend

Plus **manual channels** created per market by admins/editors for non-PM activity:
- Campaign / Promotions, Events, Influencer / KOL, Partner Marketing Support, Consultant Fee, Premium Program, Gift-Seasonal, etc.

### 4.2 Two-Field Categorisation Model
Every line item carries both:
- **`marketing_cat`** — high-level business category (~8 values) → drives analytics aggregation
- **`finance_cat`** — granular sub-category (~25 values) → drives finance billing reconciliation

Example: a Meta ad spend has `marketing_cat = "Performance Marketing"` (for management reporting) and `finance_cat = "Paid Social-Meta"` (for billing).

### 4.3 Data Flow

| Source | Path | Frequency |
|---|---|---|
| BigQuery PM actuals | Auto-sync → Performance Marketing channel entries | Daily/on-demand |
| Planned Upload (BQ-shaped CSV) | 4-col CSV → matched/overwrite PM planned entries | As needed |
| Line-Item Upload (manual CSV) | Up to 16-col CSV → manual entries (campaigns, events, etc.) | As needed |
| Manual entry form | UI → single entry | Continuous |

## 5. Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Flask + Blueprints |
| Auth | werkzeug `check_password_hash` + Flask sessions |
| Storage (dev) | Google Sheets via `gspread` |
| Storage (prod) | PostgreSQL (parallel implementation of `sheets_helper`) |
| BigQuery | `google-cloud-bigquery` SDK, table `pepperstone_apac.ad_performance` |
| Frontend | Single-page app in [templates/app.html](../templates/app.html) — vanilla JS, no framework |
| Excel export | `openpyxl` |

## 6. Page Structure (single-page app, hash routing)

| Page | Purpose |
|---|---|
| **Dashboard** | Country + quarter view; budget summary; channel & activity tree; entry list; entry CRUD |
| **Reconciliation** | Multi-quarter rollup; stages (planned/confirmed/actual); JIRA + invoice tracking; XLSX export |
| **Analytics** | Filters (country/quarter/channel/marketing cat); summary cards; by-marketing-cat and by-channel matrices |
| **Config** | Markets, channels, activities, vendors, categories, mappings, users; bulk uploads |
| **PM Sync** | Trigger BigQuery sync for selected markets/months |
| **Data Uploads** | Planned and Line-Item CSV uploads (visible to all users; RBAC enforced) |

## 7. Fiscal Year

FY26 runs **July 2025 → June 2026**:
- Q1 = Jul, Aug, Sep
- Q2 = Oct, Nov, Dec
- Q3 = Jan, Feb, Mar
- Q4 = Apr, May, Jun

## 8. RBAC Enforcement

Two layers:
- **Backend**: every endpoint validates `check_country_access(country)` against session role + assigned markets. Returns 403 on violation.
- **Upload-specific**: bulk uploads silently filter rows to the user's allowed markets and report rejections back in the upload result.

## 9. Storage Abstraction

[sheets_helper.py](../sheets_helper.py) is the **only** module that touches the data store. All other code calls these functions:

- `get_sheet(tab)` → opens/creates a worksheet (or table)
- `safe_get_records(ws, tab=None)` → returns list of row dicts
- `get_records_cached(tab)` → 30s in-memory cache
- `rows_for_cached(tab, **filters)` → filtered slice
- `invalidate_cache(tab)` → forces re-read

To swap storage backends (Sheets → Postgres), implement the same function signatures in a parallel module and import that instead.

## 10. Currency

All amounts displayed and stored in **AUD** (Australian Dollars). No currency conversion in the app — uploads must already be in AUD.

## 11. Critical Constraints

- Channel names must match **exactly** when uploading line items (whitespace, slashes, hyphens). Mismatches create new $0-budget channels.
- Months must fall within the FY26 valid range (`VALID_MONTH_KEYS` in [config.py](../config.py)).
- PM sync may not create new channels — if `Performance Marketing` or `Affiliate - CPA & FF` is missing for a market, the sync skips that market with a clear reason.
