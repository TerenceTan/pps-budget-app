#!/usr/bin/env python3
"""
migrate_data.py — One-time migration from Google Sheets to PostgreSQL.

Usage:
  DATABASE_URL=postgresql://... \
  GOOGLE_CREDS_JSON='...' \
  SHEET_ID=13TMeZ3pqdUQr2WRMG5G70xchZKfmiPVOShZChqbUsv4 \
  python migrate_data.py

Or with credentials file:
  DATABASE_URL=postgresql://... \
  SHEET_ID=13TMeZ3pqdUQr2WRMG5G70xchZKfmiPVOShZChqbUsv4 \
  python migrate_data.py
"""

import os, json, sys
import psycopg2
import psycopg2.extras
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_ID = os.environ.get("SHEET_ID", "13TMeZ3pqdUQr2WRMG5G70xchZKfmiPVOShZChqbUsv4")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

# ── Connect to Google Sheets ──────────────────────────────────
def get_gc():
    raw = os.environ.get("GOOGLE_CREDS_JSON")
    if raw:
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(
            os.environ.get("GOOGLE_CREDS", "credentials.json"), scopes=SCOPES
        )
    return gspread.authorize(creds)

def safe_records(ws, expected_headers=None):
    try:
        if expected_headers:
            return ws.get_all_records(expected_headers=expected_headers)
        return ws.get_all_records(numericise_ignore=['all'])
    except Exception:
        try:
            return ws.get_all_records(numericise_ignore=['all'])
        except Exception:
            return []

# ── Migrate ───────────────────────────────────────────────────
def migrate():
    print("Connecting to Google Sheets...")
    gc = get_gc()
    sh = gc.open_by_key(SHEET_ID)

    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # ── Budgets ──
    try:
        ws = sh.worksheet("Budgets")
        rows = safe_records(ws, ["id","country","quarter","total_budget","updated_at"])
        print(f"  Budgets: {len(rows)} rows")
        for r in rows:
            cur.execute("""
                INSERT INTO budgets (id, country, quarter, total_budget, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (str(r["id"]), str(r["country"]), str(r["quarter"]),
                  float(r.get("total_budget") or 0), str(r.get("updated_at",""))))
        conn.commit()
    except gspread.WorksheetNotFound:
        print("  Budgets: tab not found, skipping")

    # ── Channels ──
    try:
        ws = sh.worksheet("Channels")
        rows = safe_records(ws, ["id","country","quarter","name","budget","sort_order","created_at"])
        print(f"  Channels: {len(rows)} rows")
        for r in rows:
            cur.execute("""
                INSERT INTO channels (id, country, quarter, name, budget, sort_order, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (str(r["id"]), str(r["country"]), str(r["quarter"]),
                  str(r["name"]), float(r.get("budget") or 0),
                  int(r.get("sort_order") or 0), str(r.get("created_at",""))))
        conn.commit()
    except gspread.WorksheetNotFound:
        print("  Channels: tab not found, skipping")

    # ── Activities ──
    try:
        ws = sh.worksheet("Activities")
        rows = safe_records(ws, ["id","channel_id","country","quarter","name","sort_order","created_at"])
        print(f"  Activities: {len(rows)} rows")
        for r in rows:
            cur.execute("""
                INSERT INTO activities (id, channel_id, country, quarter, name, sort_order, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (str(r["id"]), str(r["channel_id"]), str(r["country"]),
                  str(r["quarter"]), str(r["name"]),
                  int(r.get("sort_order") or 0), str(r.get("created_at",""))))
        conn.commit()
    except gspread.WorksheetNotFound:
        print("  Activities: tab not found, skipping")

    # ── Entries ──
    ENTRY_HEADERS = [
        "id","country","quarter","month","channel_id","channel_name",
        "activity_id","activity_name",
        "bu","finance_cat","marketing_cat","description",
        "planned","confirmed","actual",
        "jira","vendor","notes",
        "approved","invoice_names","invoice_data",
        "entered_by","created_at","updated_at"
    ]
    try:
        ws = sh.worksheet("Entries")
        rows = safe_records(ws, ENTRY_HEADERS)
        print(f"  Entries: {len(rows)} rows")
        for r in rows:
            cur.execute("""
                INSERT INTO entries (id, country, quarter, month, channel_id, channel_name,
                    activity_id, activity_name, bu, finance_cat, marketing_cat, description,
                    planned, confirmed, actual, jira, vendor, notes, approved,
                    invoice_names, invoice_data, entered_by, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """, (
                str(r["id"]), str(r["country"]), str(r["quarter"]), str(r.get("month","")),
                str(r.get("channel_id","")), str(r.get("channel_name","")),
                str(r.get("activity_id","")), str(r.get("activity_name","")),
                str(r.get("bu","")), str(r.get("finance_cat","")), str(r.get("marketing_cat","")),
                str(r.get("description","")),
                float(r.get("planned") or 0), float(r.get("confirmed") or 0), float(r.get("actual") or 0),
                str(r.get("jira","")), str(r.get("vendor","")), str(r.get("notes","")),
                str(r.get("approved","False")),
                str(r.get("invoice_names","[]")), str(r.get("invoice_data","[]")),
                str(r.get("entered_by","")), str(r.get("created_at","")), str(r.get("updated_at",""))
            ))
        conn.commit()
    except gspread.WorksheetNotFound:
        print("  Entries: tab not found, skipping")

    # ── ChannelMapping ──
    MAPPING_HEADERS = ["channel_keyword","bu","finance_cat","marketing_cat","updated_by","updated_at"]
    try:
        ws = sh.worksheet("ChannelMapping")
        rows = safe_records(ws, MAPPING_HEADERS)
        print(f"  ChannelMapping: {len(rows)} rows")
        for r in rows:
            kw = str(r.get("channel_keyword","")).strip()
            if not kw:
                continue
            cur.execute("""
                INSERT INTO channel_mapping (channel_keyword, bu, finance_cat, marketing_cat, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (channel_keyword) DO NOTHING
            """, (kw, str(r.get("bu","")), str(r.get("finance_cat","")),
                  str(r.get("marketing_cat","")), str(r.get("updated_by","")),
                  str(r.get("updated_at",""))))
        conn.commit()
    except gspread.WorksheetNotFound:
        print("  ChannelMapping: tab not found, skipping")

    # ── Vendors ──
    VENDOR_HEADERS = ["id","name","country","added_by","created_at"]
    try:
        ws = sh.worksheet("Vendors")
        rows = safe_records(ws, VENDOR_HEADERS)
        print(f"  Vendors: {len(rows)} rows")
        for r in rows:
            cur.execute("""
                INSERT INTO vendors (id, name, country, added_by, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (str(r["id"]), str(r["name"]), str(r.get("country","GLOBAL")),
                  str(r.get("added_by","")), str(r.get("created_at",""))))
        conn.commit()
    except gspread.WorksheetNotFound:
        print("  Vendors: tab not found, skipping")

    # ── Users ──
    try:
        ws = sh.worksheet("Users")
        rows = safe_records(ws)
        print(f"  Users: {len(rows)} rows")
        for r in rows:
            # Handle both old format (Username/Password) and new format (username/password_hash)
            uname = str(r.get("username", r.get("Username", ""))).strip()
            pwd = str(r.get("password_hash", r.get("Password", ""))).strip()
            display = str(r.get("display_name", uname))
            role = str(r.get("role", r.get("Role", "country")))
            markets = str(r.get("markets", r.get("Markets", "ALL")))
            created = str(r.get("created_at", ""))
            if not uname:
                continue
            # If Password is plaintext (old format), hash it
            if pwd and not pwd.startswith("scrypt:") and not pwd.startswith("pbkdf2:"):
                from werkzeug.security import generate_password_hash
                pwd = generate_password_hash(pwd, method='pbkdf2:sha256')
            cur.execute("""
                INSERT INTO users (username, password_hash, display_name, role, markets, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            """, (uname, pwd, display, role, markets, created))
        conn.commit()
    except gspread.WorksheetNotFound:
        print("  Users: tab not found, skipping")

    # ── Categories ──
    CATEGORY_HEADERS = ["id","type","value","sort_order","created_at"]
    try:
        ws = sh.worksheet("Categories")
        rows = safe_records(ws, CATEGORY_HEADERS)
        print(f"  Categories: {len(rows)} rows")
        for r in rows:
            cur.execute("""
                INSERT INTO categories (id, type, value, sort_order, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (str(r["id"]), str(r["type"]), str(r["value"]),
                  int(r.get("sort_order") or 0), str(r.get("created_at",""))))
        conn.commit()
    except gspread.WorksheetNotFound:
        print("  Categories: tab not found, skipping")

    # ── Validate ──
    print("\nValidation:")
    for table in ["budgets","channels","activities","entries","channel_mapping","vendors","users","categories"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count} rows")

    cur.close()
    conn.close()
    print("\nMigration complete!")

if __name__ == "__main__":
    migrate()
