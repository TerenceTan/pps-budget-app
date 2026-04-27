# Release Notes — APAC Marketing Budget Tracker

All notable changes per release. Most recent first.

---

## v1.6 — 2026-04-22

**Theme:** Upload UX, analytics alignment, channel restructure cleanup.

### Added
- Yellow warning banner on the Line-Item Upload panel: *"Channel names must match exactly. If a name does not match, a new channel will be created with $0 budget."*
- New PM channel aliases for planned upload normalisation: `Dou Yin → Douyin`, `Wechat / We Chat / Weixin → WeChat`, `Kuaishou / Kwai → Kuaishou`, `TA Media / TAMedia → TA Media`.
- New PM activities: `WeChat`, `Kuaishou`, `TA Media`.
- `migrate_channels.py` now automatically transfers budgets from old PM-style channels (Paid Social, Performance Marketing (PM), LDD) to the umbrella `Performance Marketing` channel during commit.

### Fixed
- **Delete bug** — entries failed to delete for editors with `markets="ALL"`. RBAC check switched from raw `session["user"]` comparison to `check_country_access()`. ([app.py](../app.py))
- **Upload UX** — buttons now show in-flight `⏳ Uploading…` state, disable during request, and clear/scroll the result panel on success or error. ([templates/app.html](../templates/app.html))
- **HKG → HK migration** — country code unified across all backend code, normalisation maps, default users, and PM_COUNTRY_MAP.
- **Analytics alignment** — `By Marketing Cat` and `By Channel` views now both use the same canonical category names (Performance Marketing, Affiliate - CPA & FF, Campaign / Promotions, Events, Influencer / KOL, Partner Marketing Support, Consultant Fee, Other).

### Data Migrations (one-time scripts)
| Script | Purpose |
|---|---|
| `fix_hkg_to_hk.py` | Renames HKG → HK in Budgets, Channels, Activities, Entries, Vendors, Users tabs |
| `fix_marketing_categories.py` | Remaps old granular `marketing_cat` values on Entries + ChannelMapping to new high-level categories |
| `fix_categories_tab.py` | Replaces marketing rows in the Categories tab with the new `DEFAULT_MKT_CATS` |
| `fix_pm_channel_names.py` | Re-points entries with stale `channel_name` (e.g. "Performance Marketing (PM)") to the umbrella channel |
| `migrate_channels.py` | Re-points entries from orphan channels and transfers budgets to umbrella channels |

### Production SQL
For AWS Postgres backend — see `RELEASE_NOTES_SQL.md` (or send the queries below to config manager):
```sql
UPDATE entries SET country='HK' WHERE country='HKG';
UPDATE budgets SET country='HK' WHERE country='HKG';
UPDATE channels SET country='HK' WHERE country='HKG';
UPDATE entries SET marketing_cat='Performance Marketing'
  WHERE marketing_cat IN ('Paid Social','PPC / Search','PPC','PMAX','Programmatic','Bing','Display','YouTube','Local Direct Deals','Baidu-Display','Baidu-PPC');
UPDATE entries SET marketing_cat='Affiliate - CPA & FF' WHERE marketing_cat='Affiliate';
UPDATE entries SET marketing_cat='Campaign / Promotions' WHERE marketing_cat IN ('Campaigns/Promotions','Brand / OOH','Content');
UPDATE entries SET marketing_cat='Events' WHERE marketing_cat IN ('Events & Sponsorship','Event');
UPDATE entries SET marketing_cat='Influencer / KOL' WHERE marketing_cat='Influencer/KOL';
UPDATE entries SET marketing_cat='Partner Marketing Support' WHERE marketing_cat IN ('Premium Partners','Partner','AMF1 Activation','AMF1 Race Tickets','AMF1');
```

---

## v1.5 — 2026-04-21 (`3edec5c`)
**Added** — Config page access for editors (previously admin-only). Editors can now manage channels and activities for markets they have access to.

---

## v1.4 — 2026-04-17 (`67ccc1a`)
**Theme:** Channel restructure into umbrella model.

- Introduced `Performance Marketing` (umbrella) and `Affiliate - CPA & FF` channels.
- Added `api_uploads.py` blueprint — Planned Upload (BQ-shaped, 4 cols) and Line-Item Upload (full manual, up to 16 cols).
- Added bulk delete feature.
- Added `migrate_channels.py` — migration tool to collapse orphan channels into the umbrella structure.

---

## v1.3 — 2026-04-09 (`2b7be23`, `b0452f7`)
- Added market dropdown for `roapac_sales` (multi-market user covering ID, IN, MY, SG, MN, PH, TW).
- Added new modules and fixed misc issues.
- Modularised `app.py` — split out `api_pm.py`, `auth.py`, `sheets_helper.py`.

---

## v1.2 — 2026-04-01 (`311a067`, `48c2d9e`)
- Switched all currency display from USD → AUD.
- Updated config schema for new fields.

---

## v1.1 — 2026-03-31 (`7cb086e`)
**Theme:** Analytics + PM data sync.

- New Analytics page with summary cards, by-marketing-cat and by-channel matrices, country/quarter/marketing-cat filters.
- PM data sync from BigQuery `pepperstone_apac.ad_performance` table — pulls actuals into the tracker automatically per country/month/channel.

---

## v1.0 — 2026-03-24 to 2026-03-27 (`a940a35` and earlier)
**Initial production release.**

- Core dashboard: country/quarter selection, channel and activity hierarchy, line-item entry form with invoice attachments.
- Reconciliation tab with stages, filters, XLSX export.
- Login/role system: admin, editor, country-specific users.
- Activity management for editors.

---

## Versioning Notes
- Versions are retroactively numbered for clarity; commits are the source of truth.
- All dates are commit dates from `git log`.
- For deeper change-by-change diff, run: `git log --stat --oneline`.
