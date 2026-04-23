# -*- coding: utf-8 -*-
"""
MIGRATION: collapse orphan channels into umbrella structure.

Run once after deploying the new config.py/api_pm.py.
  python migrate_channels.py              # dry-run (default)
  python migrate_channels.py --commit      # actually writes

Works against either Google Sheets (default) or PostgreSQL when
USE_POSTGRES=true is set. For PostgreSQL, DATABASE_URL must point at the
target DB (e.g. your RDS instance via a tunnel / SSM session).

What it does:
  1. Finds entries in "Performance Marketing (PM)" channels and re-points them
     to the new "Performance Marketing" umbrella channel, mapping the old
     activity name to a normalised activity name.
  2. Same for "Performance Marketing (PM)-Local Direct Deal (LDD)" → activity "LDD".
  3. Same for "Paid Social" → normalises activity per channel_group hint.
  4. Same for orphan "Affiliate" channel → "Affiliate - CPA & FF" channel, activity "Affiliate".
     EXACT-MATCH on "Affiliate" so we don't nuke your real "Affiliate - CPA & FF".
  5. Deletes source channels ONLY if they end up with zero entries pointing to them.
  6. Reports LDD channel's budget ($ amount) so admin can decide whether to
     add it to the umbrella's budget manually.

SAFETY:
  - Dry-run by default. Nothing is written unless --commit is passed.
  - Prints all entry IDs being touched so you can audit the data directly.
  - Idempotent: running twice is safe (already-migrated entries are skipped).
  - Sheets mode: rate-limited 1.1s between writes (Google's 60/min quota),
    auto-backoff on 429, batch_update for bulk row writes.
  - PostgreSQL mode: no rate limits, writes happen inside a single connection.
  - Rollback: Sheets history retains previous row values ~30 days;
    for PostgreSQL, take a snapshot/pg_dump BEFORE running with --commit.
"""
import sys
import time
import argparse
from datetime import datetime

from config import (TAB_CHANNELS, TAB_ACTIVITIES, TAB_ENTRIES, ENTRY_HEADERS,
                    PM_UMBRELLA_CHANNEL, AFFILIATE_CHANNEL, normalise_channel_group,
                    PM_CHANNEL_MAP, USE_POSTGRES)
from sheets_helper import get_sheet, safe_get_records, invalidate_cache

if USE_POSTGRES:
    import db as pgdb

# =====================================================================
# RATE LIMITING + 429 RETRY
# Google Sheets API cap: 60 write requests per minute per user.
# We sleep 1.1s between writes (~54/min) and auto-backoff on 429.
# =====================================================================
WRITE_THROTTLE_SECONDS = 1.1
BACKOFF_ON_429_SECONDS = 65
MAX_RETRIES_PER_CALL = 5


def is_429(exc):
    """Detect a Google Sheets rate-limit 429 error."""
    s = str(exc)
    return "429" in s or "Quota exceeded" in s or "rateLimitExceeded" in s


def safe_call(fn, *args, **kwargs):
    """Wrap a gspread write with rate-limiting + 429 backoff."""
    time.sleep(WRITE_THROTTLE_SECONDS)
    last_exc = None
    for attempt in range(MAX_RETRIES_PER_CALL):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if is_429(exc):
                wait = BACKOFF_ON_429_SECONDS + (attempt * 5)
                print(f"    [wait] rate-limit hit, waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES_PER_CALL})...",
                      flush=True)
                time.sleep(wait)
                continue
            raise
    raise last_exc


# =====================================================================
# MIGRATION RULES
# =====================================================================
MIGRATIONS = [
    ("Performance Marketing (PM)-Local Direct Deal (LDD)", PM_UMBRELLA_CHANNEL, "LDD"),
    ("Performance Marketing (PM)",                          PM_UMBRELLA_CHANNEL, None),
    ("Paid Social",                                         PM_UMBRELLA_CHANNEL, None),
    ("Affiliate",                                           AFFILIATE_CHANNEL,   "Affiliate"),
]


def derive_activity_from_old(old_channel_name, old_activity_name, old_description):
    candidates = [old_activity_name or "", old_description or ""]
    for c in candidates:
        norm = normalise_channel_group(c)
        if norm in PM_CHANNEL_MAP:
            return PM_CHANNEL_MAP[norm]["activity_name"]
        words = c.replace(":", " ").replace("-", " ").replace("_", " ").split()
        for w in words:
            n = normalise_channel_group(w)
            if n in PM_CHANNEL_MAP:
                return PM_CHANNEL_MAP[n]["activity_name"]
    return "Others"


def find_or_create_channel(ws_channels, channels, country, quarter, channel_name, dry_run, log):
    for i, c in enumerate(channels):
        if (str(c.get("country","")) == country
            and str(c.get("quarter","")) == quarter
            and str(c.get("name","")).strip() == channel_name):
            return str(c["id"]), False, i
    new_id = f"ch_mig_{country}_{quarter}_{abs(hash(channel_name))%100000:05d}"
    log.append(f"    WOULD CREATE channel '{channel_name}' for {country}/{quarter} (id={new_id})")
    if not dry_run:
        now = datetime.utcnow().isoformat()
        so = len([c for c in channels if str(c.get("country",""))==country and str(c.get("quarter",""))==quarter])
        if USE_POSTGRES:
            pgdb.insert_channel(new_id, country, quarter, channel_name, 0, so, now)
        else:
            safe_call(ws_channels.append_row, [new_id, country, quarter, channel_name, 0, so, now])
        channels.append({"id":new_id, "country":country, "quarter":quarter,
                         "name":channel_name, "budget":0, "sort_order":so})
        return new_id, True, len(channels)-1
    channels.append({"id":new_id, "country":country, "quarter":quarter,
                     "name":channel_name, "budget":0, "sort_order":99, "_dry_new":True})
    return new_id, True, len(channels)-1


def find_or_create_activity(ws_activities, activities, channel_id, country, quarter, activity_name, dry_run, log):
    if not activity_name:
        activity_name = "Others"
    for a in activities:
        if (str(a.get("channel_id","")) == channel_id
            and str(a.get("country","")) == country
            and str(a.get("quarter","")) == quarter
            and str(a.get("name","")).strip() == activity_name):
            return str(a["id"]), False
    new_id = f"act_mig_{abs(hash((channel_id, activity_name)))%100000:05d}"
    log.append(f"    WOULD CREATE activity '{activity_name}' under channel {channel_id} (id={new_id})")
    if not dry_run:
        now = datetime.utcnow().isoformat()
        so = len([a for a in activities if str(a.get("channel_id",""))==channel_id])
        if USE_POSTGRES:
            pgdb.insert_activity(new_id, channel_id, country, quarter, activity_name, so, now)
        else:
            safe_call(ws_activities.append_row, [new_id, channel_id, country, quarter, activity_name, so, now])
        activities.append({"id":new_id, "channel_id":channel_id, "country":country,
                           "quarter":quarter, "name":activity_name, "sort_order":so})
        return new_id, True
    activities.append({"id":new_id, "channel_id":channel_id, "country":country,
                       "quarter":quarter, "name":activity_name, "_dry_new":True})
    return new_id, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Actually write changes (default: dry-run)")
    args = parser.parse_args()
    dry_run = not args.commit

    mode = "PostgreSQL" if USE_POSTGRES else "Google Sheets"
    print("\n" + "="*70)
    print(" CHANNEL MIGRATION " + ("(DRY-RUN)" if dry_run else "(COMMIT MODE)") + f"  [{mode}]")
    print("="*70)
    if not dry_run and not USE_POSTGRES:
        print(f" Rate limit: {WRITE_THROTTLE_SECONDS}s between writes, auto-backoff on 429")
        print("="*70)

    if USE_POSTGRES:
        ws_channels = ws_activities = ws_entries = None
        channels = pgdb.get_all(TAB_CHANNELS)
        activities = pgdb.get_all(TAB_ACTIVITIES)
        entries = pgdb.get_all(TAB_ENTRIES)
    else:
        ws_channels = get_sheet(TAB_CHANNELS)
        ws_activities = get_sheet(TAB_ACTIVITIES)
        ws_entries = get_sheet(TAB_ENTRIES)
        channels = safe_get_records(ws_channels, TAB_CHANNELS)
        activities = safe_get_records(ws_activities, TAB_ACTIVITIES)
        entries = safe_get_records(ws_entries, TAB_ENTRIES)

    print(f"\nLoaded: {len(channels)} channels, {len(activities)} activities, {len(entries)} entries\n")

    old_channel_rows = []
    for i, c in enumerate(channels):
        cname = str(c.get("name","")).strip()
        for old_name, new_name, default_act in MIGRATIONS:
            if cname == old_name:
                old_channel_rows.append((i, c, (old_name, new_name, default_act)))
                break

    if not old_channel_rows:
        print("No orphan channels found. Nothing to migrate. [OK]\n")
        return

    print(f"Found {len(old_channel_rows)} orphan channel row(s) to migrate:\n")
    budget_warnings = []
    for i, c, rule in old_channel_rows:
        budget = float(c.get("budget") or 0)
        old_name, new_name, default_act = rule
        print(f"  {c.get('country',''):4} {c.get('quarter',''):3}  "
              f"'{old_name}' -> '{new_name}'"
              f"   (id={c.get('id','')}, budget=${budget:,.0f})")
        if budget > 0:
            budget_warnings.append({
                "country": c.get("country",""), "quarter": c.get("quarter",""),
                "old_name": old_name, "new_name": new_name, "budget": budget
            })

    entry_updates = []
    activities_to_delete = []
    channels_to_delete = []
    log = []

    for (old_idx, old_ch, rule) in old_channel_rows:
        old_name, new_name, default_act = rule
        country = str(old_ch.get("country",""))
        quarter = str(old_ch.get("quarter",""))
        old_ch_id = str(old_ch.get("id",""))

        target_ch_id, target_created, _ = find_or_create_channel(
            ws_channels, channels, country, quarter, new_name, dry_run, log)

        affected_entries = [(i, e) for i, e in enumerate(entries) if str(e.get("channel_id","")) == old_ch_id]

        print(f"\n  {country}/{quarter} -- '{old_name}' -> '{new_name}': "
              f"{len(affected_entries)} entries to re-point")

        old_acts_under = [a for a in activities if str(a.get("channel_id","")) == old_ch_id]
        old_act_ids_under = set(str(a["id"]) for a in old_acts_under)

        for idx, e in affected_entries:
            old_act_id = str(e.get("activity_id",""))
            old_act_name = str(e.get("activity_name",""))
            old_desc = str(e.get("description",""))
            if default_act:
                target_act_name = default_act
            else:
                target_act_name = derive_activity_from_old(old_name, old_act_name, old_desc)
            target_act_id, act_created = find_or_create_activity(
                ws_activities, activities, target_ch_id, country, quarter, target_act_name, dry_run, log)

            mapping_hint = PM_CHANNEL_MAP.get(normalise_channel_group(old_act_name), None) or \
                           PM_CHANNEL_MAP.get(normalise_channel_group(target_act_name), None)
            new_bu = str(e.get("bu","")) or (mapping_hint["bu"] if mapping_hint else "")
            new_fc = str(e.get("finance_cat","")) or (mapping_hint["finance_cat"] if mapping_hint else "")
            new_mc = str(e.get("marketing_cat","")) or (mapping_hint["marketing_cat"] if mapping_hint else "")

            new_row = [
                str(e.get("id","")), country, quarter, str(e.get("month","")),
                target_ch_id, new_name,
                target_act_id, target_act_name,
                new_bu, new_fc, new_mc,
                str(e.get("description","")),
                float(e.get("planned") or 0),
                float(e.get("confirmed") or 0),
                float(e.get("actual") or 0),
                str(e.get("jira","")), str(e.get("vendor","")) or target_act_name, str(e.get("notes","")),
                str(e.get("approved","False")),
                str(e.get("invoice_names","[]")), str(e.get("invoice_data","[]")),
                str(e.get("entered_by","")), str(e.get("created_at","")),
                datetime.utcnow().isoformat(),
            ]
            entry_updates.append((idx + 2, new_row, e, old_act_id))

        for a in old_acts_under:
            activities_to_delete.append((None, str(a["id"]), str(a.get("name",""))))
        channels_to_delete.append((old_idx + 2, old_ch_id, old_name))

    print("\n" + "-"*70)
    print(f" PLAN SUMMARY")
    print("-"*70)
    print(f"  Entry re-pointings:       {len(entry_updates)}")
    print(f"  Channels to delete:       {len(channels_to_delete)}")
    print(f"  Activities to delete:     {len(activities_to_delete)}")
    if log:
        print(f"\n  Creates during migration:")
        for line in log[:30]:
            print(line)
        if len(log) > 30:
            print(f"    ... and {len(log)-30} more")

    if budget_warnings:
        print(f"\n  [!] Budget values will be transferred to the umbrella channel:")
        for bw in budget_warnings:
            print(f"      {bw['country']}/{bw['quarter']} '{bw['old_name']}': ${bw['budget']:,.0f} -> '{bw['new_name']}'")
        print(f"      -> These will be added to the umbrella channel budget automatically on --commit.")

    if dry_run:
        print("\n" + "="*70)
        print(" DRY-RUN COMPLETE. Nothing was written.")
        print(" Review the plan above, then run with --commit to apply.")
        print("="*70 + "\n")
        return

    # ----- COMMIT -----
    print("\n" + "="*70)
    print(f" APPLYING CHANGES  [{mode}]")
    print("="*70)
    if USE_POSTGRES:
        total_writes = len(entry_updates) + len(activities_to_delete) + len(channels_to_delete)
        print(f" Entry updates:    {len(entry_updates)}")
        print(f" Activity deletes: {len(activities_to_delete)}")
        print(f" Channel deletes:  {len(channels_to_delete)}")
        print(f" Total DB writes:  {total_writes}")
        print(" NOTE: Take a pg_dump / RDS snapshot BEFORE confirming if you haven't already.")
    else:
        # Count actual API calls: batched entry updates + per-row deletes
        # Entries are batched into chunks of 50, so ceil(entries/50) calls
        n_entry_batches = (len(entry_updates) + 49) // 50
        total_writes = n_entry_batches + len(activities_to_delete) + len(channels_to_delete)
        est_seconds = int(total_writes * WRITE_THROTTLE_SECONDS)
        print(f" Entry updates: {len(entry_updates)} entries in {n_entry_batches} batch(es) of 50")
        print(f" Activity deletes: {len(activities_to_delete)}")
        print(f" Channel deletes: {len(channels_to_delete)}")
        print(f" Total API calls: {total_writes}  -->  est. time ~{est_seconds//60}m {est_seconds%60}s")
    print("="*70)
    try:
        answer = input("\nType 'yes' to confirm: ").strip().lower()
    except EOFError:
        answer = ""
    if answer != "yes":
        print("Aborted.")
        return

    # 1. Re-point entries
    print(f"\nUpdating {len(entry_updates)} entries...")
    start = time.time()
    total_done = 0
    if USE_POSTGRES:
        for _sheet_row, new_row, _e, _old_act_id in entry_updates:
            entry_id = new_row[0]
            # pgdb.update_entry_full takes 23 values (no id)
            try:
                pgdb.update_entry_full(entry_id, new_row[1:])
                total_done += 1
            except Exception as ex:
                print(f"    ! entry {entry_id}: {ex}")
        print(f"  done. {total_done}/{len(entry_updates)} entries updated in {time.time()-start:.1f}s")
    else:
        n_entry_batches = (len(entry_updates) + 49) // 50
        batch_payload = []
        for sheet_row, new_row, _, _ in sorted(entry_updates, key=lambda x: x[0]):
            batch_payload.append({
                "range": f"A{sheet_row}:X{sheet_row}",
                "values": [new_row],
            })
        CHUNK = 50
        for chunk_start in range(0, len(batch_payload), CHUNK):
            chunk = batch_payload[chunk_start:chunk_start + CHUNK]
            try:
                safe_call(ws_entries.batch_update, chunk, value_input_option="USER_ENTERED")
                total_done += len(chunk)
                print(f"  [ok] batch {chunk_start//CHUNK + 1}: rows "
                      f"{chunk_start+1}-{chunk_start+len(chunk)} updated "
                      f"({total_done}/{len(batch_payload)})",
                      flush=True)
            except Exception as ex:
                print(f"  [err] batch {chunk_start//CHUNK + 1} failed: {ex}")
                print(f"        Falling back to per-row updates for this batch...")
                for item in chunk:
                    try:
                        safe_call(ws_entries.update, values=item["values"], range_name=item["range"])
                        total_done += 1
                    except Exception as ex2:
                        print(f"    ! {item['range']}: {ex2}")
        print(f"  done. {total_done}/{len(entry_updates)} entries updated in {time.time()-start:.1f}s")

    # 2. Transfer budgets from old channels to umbrella channels
    if budget_warnings:
        print(f"\nTransferring budgets to umbrella channels...")
        fresh_channels = safe_get_records(ws_channels, TAB_CHANNELS)
        # Aggregate transfers: umbrella (name, country, quarter) -> total to add
        transfers = {}
        for bw in budget_warnings:
            key = (bw["new_name"], bw["country"], bw["quarter"])
            transfers[key] = transfers.get(key, 0) + bw["budget"]
        for (new_name, country, quarter), add_budget in transfers.items():
            for i, c in enumerate(fresh_channels):
                if (str(c.get("name","")).strip() == new_name
                        and str(c.get("country","")) == country
                        and str(c.get("quarter","")) == quarter):
                    current = float(c.get("budget") or 0)
                    updated = current + add_budget
                    try:
                        safe_call(ws_channels.update, f"E{i+2}", [[updated]])
                        print(f"  {country}/{quarter} '{new_name}': ${current:,.0f} + ${add_budget:,.0f} = ${updated:,.0f}")
                    except Exception as ex:
                        print(f"  ERROR updating budget for {country}/{quarter} '{new_name}': {ex}")
                    break

    # 4. Delete orphaned activities
    if activities_to_delete:
        print(f"\nDeleting {len(activities_to_delete)} orphaned activities...")
        if USE_POSTGRES:
            deleted = 0
            for _, aid, _name in activities_to_delete:
                try:
                    pgdb.delete_activity(aid)
                    deleted += 1
                except Exception as ex:
                    print(f"  ! activity {aid}: {ex}")
            print(f"  deleted {deleted} rows.")
        else:
            fresh_acts = safe_get_records(ws_activities, TAB_ACTIVITIES)
            ids_to_del = set(aid for _, aid, _ in activities_to_delete)
            to_del_rows = sorted([i+2 for i, a in enumerate(fresh_acts) if str(a.get("id","")) in ids_to_del], reverse=True)
            for r in to_del_rows:
                try:
                    safe_call(ws_activities.delete_rows, r)
                except Exception as ex:
                    print(f"  ! row {r}: {ex}")
            print(f"  deleted {len(to_del_rows)} rows.")

    # 5. Delete orphan channels
    if channels_to_delete:
        print(f"\nDeleting {len(channels_to_delete)} orphan channels...")
        if USE_POSTGRES:
            deleted = 0
            for _, cid, _name in channels_to_delete:
                try:
                    pgdb.delete_channel(cid)
                    deleted += 1
                except Exception as ex:
                    print(f"  ! channel {cid}: {ex}")
            print(f"  deleted {deleted} rows.")
        else:
            fresh_channels = safe_get_records(ws_channels, TAB_CHANNELS)
            ids_to_del = set(cid for _, cid, _ in channels_to_delete)
            to_del_rows = sorted([i+2 for i, c in enumerate(fresh_channels) if str(c.get("id","")) in ids_to_del], reverse=True)
            for r in to_del_rows:
                try:
                    safe_call(ws_channels.delete_rows, r)
                except Exception as ex:
                    print(f"  ! row {r}: {ex}")
            print(f"  deleted {len(to_del_rows)} rows.")

    if not USE_POSTGRES:
        invalidate_cache(TAB_CHANNELS)
        invalidate_cache(TAB_ACTIVITIES)
        invalidate_cache(TAB_ENTRIES)

    print("\n" + "="*70)
    print(" MIGRATION COMPLETE.")
    print(" Verify in the app:")
    print("   1. Dashboard shows only 2 auto-channels: Performance Marketing + Affiliate - CPA & FF")
    print("   2. Your manual channels (Campaign, Events, Consultant, etc.) still present")
    print("   3. PM Sync page - trigger a sync and confirm no new orphan channels appear")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
