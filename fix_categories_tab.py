# -*- coding: utf-8 -*-
"""
DATA MIGRATION: Replace old granular marketing categories in the Categories tab
with the current DEFAULT_MKT_CATS list.

Finance and BU categories are left untouched.

Usage:
  python fix_categories_tab.py              # dry-run
  python fix_categories_tab.py --commit     # writes to Google Sheets
"""
import time
import argparse
from datetime import datetime

from config import TAB_CATEGORIES, DEFAULT_MKT_CATS
from sheets_helper import get_sheet, safe_get_records, invalidate_cache

THROTTLE = 1.1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    dry_run = not args.commit

    print("\n" + "=" * 60)
    print(f" MARKETING CATEGORIES TAB FIX {'(DRY-RUN)' if dry_run else '(COMMIT)'}")
    print("=" * 60)

    ws = get_sheet(TAB_CATEGORIES)
    records = safe_get_records(ws, TAB_CATEGORIES)

    # Separate rows by type
    mkt_rows = [(i, r) for i, r in enumerate(records) if str(r.get("type", "")).strip() == "marketing"]
    other_rows = [(i, r) for i, r in enumerate(records) if str(r.get("type", "")).strip() != "marketing"]

    existing_mkt_values = [str(r.get("value", "")).strip() for _, r in mkt_rows]
    print(f"\nExisting marketing categories ({len(existing_mkt_values)}):")
    for v in existing_mkt_values:
        mark = "  [keep]" if v in DEFAULT_MKT_CATS else "  [DELETE]"
        print(f"{mark}  '{v}'")

    to_add = [v for v in DEFAULT_MKT_CATS if v not in existing_mkt_values]
    to_delete = [(i, r) for i, r in mkt_rows if str(r.get("value", "")).strip() not in DEFAULT_MKT_CATS]

    print(f"\nWill delete {len(to_delete)} old entries:")
    for _, r in to_delete:
        print(f"  - '{r.get('value','')}'")

    print(f"\nWill add {len(to_add)} new entries:")
    for v in to_add:
        print(f"  + '{v}'")

    if dry_run:
        print("\nRun with --commit to apply.\n")
        return

    if not to_delete and not to_add:
        print("\nAlready up to date. Nothing to do.\n")
        return

    # Delete old rows (delete in reverse order so row numbers stay valid)
    if to_delete:
        fresh = safe_get_records(ws, TAB_CATEGORIES)
        old_ids = {str(r.get("id", "")) for _, r in to_delete}
        del_rows = sorted(
            [i + 2 for i, r in enumerate(fresh) if str(r.get("id", "")) in old_ids],
            reverse=True
        )
        print(f"\nDeleting {len(del_rows)} old marketing category rows...")
        for row_num in del_rows:
            try:
                ws.delete_rows(row_num)
                time.sleep(THROTTLE)
            except Exception as ex:
                print(f"  ERROR deleting row {row_num}: {ex}")

    # Add new entries
    if to_add:
        fresh = safe_get_records(ws, TAB_CATEGORIES)
        next_i = len(fresh)
        now = datetime.utcnow().isoformat()
        print(f"\nAdding {len(to_add)} new marketing category rows...")
        for v in to_add:
            cat_id = f"cat_{next_i}"
            try:
                ws.append_row([cat_id, "marketing", v, next_i, now])
                print(f"  + added '{v}'")
                next_i += 1
                time.sleep(THROTTLE)
            except Exception as ex:
                print(f"  ERROR adding '{v}': {ex}")

    invalidate_cache(TAB_CATEGORIES)
    print("\nDone. Restart Flask and hard-refresh the browser.\n")


if __name__ == "__main__":
    main()
