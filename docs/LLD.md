# Low-Level Design — APAC Marketing Budget Tracker

Detailed technical reference. Pair with [HLD.md](HLD.md) for context.

---

## 1. File Responsibilities

| File | Responsibility |
|---|---|
| [app.py](../app.py) | Flask entrypoint, session/auth, dashboard + analytics + reconciliation endpoints, CRUD for entries/budgets/channels/activities/categories/vendors |
| [api_pm.py](../api_pm.py) | PM sync blueprint — pulls actuals from BigQuery and writes entries under `Performance Marketing` / `Affiliate - CPA & FF` |
| [api_uploads.py](../api_uploads.py) | Upload blueprint — Planned Upload (BQ-shaped), Line-Item Upload (full manual), bulk delete, CSV templates |
| [auth.py](../auth.py) | Login decorators, role checks, seed defaults (users, categories, mapping) |
| [config.py](../config.py) | Constants, channel/country/category maps, normalisation helpers — **storage-agnostic** (no I/O) |
| [sheets_helper.py](../sheets_helper.py) | Google Sheets reads/writes + 30s cache. Single point to swap for a Postgres implementation |
| [export_xlsx.py](../export_xlsx.py) | XLSX export shaped to finance team format |
| [templates/app.html](../templates/app.html) | Single-page UI: vanilla JS, no framework. Hash-routing across Dashboard / Reconciliation / Analytics / Config / PM Sync / Data Uploads |
| `migrate_channels.py` | One-time orphan-channel migration tool (re-points entries + transfers budgets to umbrella) |
| `fix_*.py` | One-time data-fix scripts (HKG→HK, marketing categories, dropdown, stale channel names) — see [RELEASE_NOTES.md](RELEASE_NOTES.md) |

---

## 2. Data Model

### 2.1 Tables / Tabs

#### Budgets
| Col | Type | Notes |
|---|---|---|
| id | str | UUID prefix |
| country | str | Market code (HK, TH, …) |
| quarter | str | Q1–Q4 |
| total_budget | float | Top-level country budget |
| updated_at | iso datetime | |

#### Channels
| Col | Type | Notes |
|---|---|---|
| id | str | `ch_xxxxxxxx` |
| country | str | |
| quarter | str | |
| name | str | Channel display name (must be unique per country/quarter) |
| budget | float | Channel-level planned budget |
| sort_order | int | Display order |
| created_at | iso datetime | |

#### Activities
| Col | Type | Notes |
|---|---|---|
| id | str | `act_xxxxxxxx` |
| channel_id | str | FK → Channels.id |
| country, quarter, name, sort_order, created_at | | Same shape |

#### Entries (line items)
Defined by `ENTRY_HEADERS` in config.py:
```
id, country, quarter, month, channel_id, channel_name,
activity_id, activity_name,
bu, finance_cat, marketing_cat, description,
planned, confirmed, actual,
jira, vendor, notes,
approved, invoice_names, invoice_data,
entered_by, created_at, updated_at
```

- `month` is `YYYY-MM` (FY26 valid keys only).
- `channel_name` and `activity_name` are denormalised (stored on entry) so the entry survives if the channel record is deleted/renamed.
- `invoice_names` / `invoice_data` are JSON arrays — file metadata + base64 file blobs persisted to disk.

#### ChannelMapping
Auto-population rules: keyword → BU/finance_cat/marketing_cat. Used by manual-entry form and Line-Item Upload.

#### Vendors / Users / Categories
Standard reference tables.

### 2.2 Channel Map (PM_CHANNEL_MAP)
Maps a **BigQuery `Channel_Group`** to tracker channel + activity + categorisation. Defined in [config.py](../config.py).

Examples:
```python
'Meta':       → channel='Performance Marketing', activity='Meta',
                 finance_cat='Paid Social-Meta', marketing_cat='Performance Marketing'
'Affiliates': → channel='Affiliate - CPA & FF', activity='Affiliate',
                 finance_cat='Affiliate', marketing_cat='Affiliate - CPA & FF'
```

### 2.3 Normalisation Maps
- `COUNTRY_ALIAS_MAP` — `HKG→HK`, `THAILAND→TH`, etc.
- `CHANNEL_GROUP_ALIAS_MAP` — `FB→Meta`, `DOU YIN→Douyin`, `WECHAT→WeChat`, etc.
- `CHANNEL_GROUP_PREFIXES` — longest-prefix match for fuzzy normalisation (e.g. `Meta HK` → `Meta`).

---

## 3. API Endpoints

### Auth
| Method | Path | Notes |
|---|---|---|
| POST | `/login` | username + password form |
| GET | `/logout` | Clears session |

### Categories
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/categories` | login | Returns `{bu, finance, marketing}` lists |
| POST | `/api/categories` | admin | Add a category |
| DELETE | `/api/categories/<id>` | admin | Remove a category |

### Budgets / Channels / Activities
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/budget/<country>/<quarter>` | login + RBAC | Returns total + channels + activities + mapping |
| POST | `/api/budget/<country>/<quarter>` | admin | Set country total budget |
| POST | `/api/channels` | login + RBAC | Add channel |
| PUT | `/api/channels/<id>` | login + RBAC | Update name/budget |
| DELETE | `/api/channels/<id>` | login + RBAC | Delete channel |
| POST/PUT/DELETE | `/api/activities…` | login + RBAC | Same pattern |

### Entries
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/entries/<country>/<quarter>` | login + RBAC | All line items for filter |
| POST | `/api/entries` | login + RBAC | Create line item (auto-applies mapping if cats blank) |
| PUT | `/api/entries/<id>` | login + RBAC | Update line item |
| DELETE | `/api/entries/<id>` | login + RBAC | Delete line item |

### Analytics & Reconciliation
| Method | Path | Notes |
|---|---|---|
| GET | `/api/analytics?quarter=&country=` | Aggregations for cards + matrices |
| GET | `/api/reconciliation/<quarter>` | Multi-stage rollup |

### PM Sync
| Method | Path | Notes |
|---|---|---|
| POST | `/api/pm/sync` | Triggers BQ pull and writes entries |
| GET | `/api/pm/preview` | Preview sync without writing |

### Uploads
| Method | Path | Notes |
|---|---|---|
| POST | `/api/upload/planned` | 4-col BQ-shaped CSV |
| POST | `/api/upload/entries` | Up to 16-col line-item CSV |
| POST | `/api/upload/budgets` | Country + quarter + total |
| POST | `/api/upload/channels` | Country + quarter + channel + budget |
| POST | `/api/entries/bulk_delete` | Delete by ID list |
| GET | `/api/template/planned` | Download CSV template |
| GET | `/api/template/entries` | Download CSV template |
| GET | `/api/template/budgets`, `/api/channel_template`, `/api/budget_template` | Other templates |

### Export
| Method | Path | Notes |
|---|---|---|
| GET | `/api/export/csv` | Flat CSV |
| GET | `/api/export/xlsx` | Finance-shaped XLSX |
| GET | `/api/invoice/<entry_id>/<filename>` | Download stored invoice |

---

## 4. Key Algorithms

### 4.1 Channel-name normalisation (`normalise_channel_group`)
1. Exact match against `PM_CHANNEL_MAP` keys.
2. Exact alias match (case-insensitive) against `CHANNEL_GROUP_ALIAS_MAP`.
3. Longest-prefix match against `CHANNEL_GROUP_PREFIXES` (`Meta HK` → `Meta`).
4. Fall back to cleaned-up raw string.

### 4.2 PM Sync (api_pm.py)
1. Query BigQuery for `(country, month, channel_group, sum(spend))` in selected window.
2. For each row:
   - Normalise country (`PM_COUNTRY_MAP`) and channel_group.
   - Look up `PM_CHANNEL_MAP[channel_group]` → tracker channel + activity + cats.
   - **Skip** if the umbrella channel doesn't exist for that market/quarter (no auto-create).
   - Find existing entry by `(country, channel_id, activity_id, month)`. If found, overwrite `actual`. Else insert new `pm_xxx` entry with planned=0.
3. Return summary `{saved, overwrote, created, skipped, reasons}`.

### 4.3 Planned Upload (api_uploads.py)
Same matching as PM Sync, but writes the `planned` column instead of `actual`. Auto-creates the umbrella channel + activity if missing for the market/quarter.

### 4.4 Line-Item Upload
1. Parse CSV/XLSX, lower-case headers.
2. For each row: normalise country, derive quarter from month if missing, look up channel by **exact name match** for that country/quarter (creates new $0 channel if no match).
3. Auto-fill blank `bu`/`finance_cat`/`marketing_cat` via `_apply_keyword_mapping(channel_name)` against `DEFAULT_MAPPING`.
4. Dedup key: `country|month|channel|activity|vendor|description`. Existing match → update; else insert.

### 4.5 Analytics Aggregation (`/api/analytics`)
- Loads Entries, Budgets, Channels.
- Sums planned/actual by month, by marketing_cat, by country.
- **Budget distribution** (lines 437–449 of [app.py](../app.py)): each channel's budget is split across the marketing_cats its entries fall into, weighted by `actual` (preferred) or `planned` or entry count. This makes "By Marketing Cat" budget add up correctly across split channels.

---

## 5. Caching

- `_sheet_cache` in [sheets_helper.py](../sheets_helper.py) — 30-second TTL per tab.
- Invalidated immediately after any mutation via `invalidate_cache(tab)`.
- gspread client and Spreadsheet handle cached for 10 minutes (`_GC_TTL`).

---

## 6. Frontend State

[templates/app.html](../templates/app.html) holds all UI logic.

- Hash routing: `#dashboard`, `#analytics`, `#config`, `#recon`, `#pm`, `#uploads`.
- Global cache `_cache = {budget, entries, analytics, …}` keyed by `(country, quarter)` to avoid refetching on tab switches.
- `invalidateCache()` called after any mutation; subsequent renders re-fetch.
- All RBAC visible in UI (hidden buttons / disabled fields) and re-validated server-side.

---

## 7. Migrations & Maintenance Scripts

| Script | When to run |
|---|---|
| `migrate_channels.py` | After config.py changes that restructure channels (collapse old → umbrella) |
| `fix_hkg_to_hk.py` | After HKG → HK rename (one-time, done in v1.6) |
| `fix_marketing_categories.py` | After marketing_cat values change (one-time, done in v1.6) |
| `fix_categories_tab.py` | After `DEFAULT_MKT_CATS` changes — replaces dropdown options |
| `fix_pm_channel_names.py` | After channel renaming if entries still hold stale `channel_name` |
| `fix_stale_channel_names.py` | Periodic check — fixes entries whose `channel_name` doesn't match the canonical channel record |

All scripts are **dry-run by default**. Pass `--commit` to write. All include throttle (1.1s/write) and 429 backoff for Sheets quota.

---

## 8. Environment Variables

| Var | Purpose |
|---|---|
| `SECRET_KEY` | Flask session secret |
| `GOOGLE_CREDS` | Path to GCP service account JSON (default: `credentials.json`) |
| `SHEET_ID` | Google Sheet ID |
| `BQ_PROJECT_ID`, `BQ_DATASET`, `BQ_TABLE`, `BQ_LOCATION` | BigQuery PM source |

For Postgres production deployment, the equivalent connection vars (`DATABASE_URL` etc.) live in the parallel `sheets_helper` implementation maintained by the config manager.

---

## 9. Known Constraints

- Google Sheets API write quota: 60 writes/min. Bulk operations batch where possible (`batch_update` in 50-row chunks).
- Single Sheet → single FY. Each new fiscal year requires either a new Sheet or extending `MONTH_SHORT` / `VALID_MONTH_KEYS` in [config.py](../config.py).
- Invoice files stored on disk (`invoices/`). Not synced to S3 — local-only. Persistent volume required for AWS deployment.
- No multi-currency support. AUD only.
