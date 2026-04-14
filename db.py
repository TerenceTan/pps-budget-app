"""
db.py — PostgreSQL data access layer for APAC Marketing Budget Tracker.
Drop-in replacement for Google Sheets operations when USE_POSTGRES=true.
All functions return lists of dicts (same shape as gspread get_all_records).
"""

import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool = None

def get_connection():
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.connect(DATABASE_URL)
        _pool.autocommit = True
    return _pool

def reset_connection():
    global _pool
    if _pool and not _pool.closed:
        try:
            _pool.close()
        except Exception:
            pass
    _pool = None

@contextmanager
def get_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        cur.close()
    except Exception:
        reset_connection()
        raise

# ── TABLE NAME MAP ────────────────────────────────────────────
# Maps Google Sheets tab names to PostgreSQL table names
TAB_TO_TABLE = {
    "Budgets":        "budgets",
    "Channels":       "channels",
    "Activities":     "activities",
    "Entries":        "entries",
    "ChannelMapping": "channel_mapping",
    "Vendors":        "vendors",
    "Users":          "users",
    "Categories":     "categories",
}

# ── GENERIC OPERATIONS ────────────────────────────────────────

def get_all(tab):
    """Get all records from a tab (equivalent to ws.get_all_records())."""
    table = TAB_TO_TABLE.get(tab, tab.lower())
    with get_cursor() as cur:
        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
    return [dict(r) for r in rows]

def get_filtered(tab, **filters):
    """Get records matching filters (equivalent to rows_for / rows_for_cached)."""
    table = TAB_TO_TABLE.get(tab, tab.lower())
    if not filters:
        return get_all(tab)
    conditions = []
    values = []
    for k, v in filters.items():
        conditions.append(f"{k} = %s")
        values.append(str(v))
    where = " AND ".join(conditions)
    with get_cursor() as cur:
        cur.execute(f"SELECT * FROM {table} WHERE {where}", values)
        rows = cur.fetchall()
    return [dict(r) for r in rows]

# ── BUDGETS ───────────────────────────────────────────────────

def upsert_budget(id, country, quarter, total_budget, updated_at):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO budgets (id, country, quarter, total_budget, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (country, quarter) DO UPDATE
            SET total_budget = EXCLUDED.total_budget, updated_at = EXCLUDED.updated_at
        """, (id, country, quarter, total_budget, updated_at))

def get_budget(country, quarter):
    rows = get_filtered("Budgets", country=country, quarter=quarter)
    return rows[0] if rows else None

# ── CHANNELS ──────────────────────────────────────────────────

def insert_channel(id, country, quarter, name, budget, sort_order, created_at):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO channels (id, country, quarter, name, budget, sort_order, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (id, country, quarter, name, budget, sort_order, created_at))

def update_channel(id, country, quarter, name, budget, sort_order, created_at):
    with get_cursor() as cur:
        cur.execute("""
            UPDATE channels SET country=%s, quarter=%s, name=%s, budget=%s,
            sort_order=%s, created_at=%s WHERE id=%s
        """, (country, quarter, name, budget, sort_order, created_at, id))

def delete_channel(id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM channels WHERE id = %s", (id,))

def count_channels(country, quarter):
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM channels WHERE country=%s AND quarter=%s", (country, quarter))
        return cur.fetchone()["count"]

# ── ACTIVITIES ────────────────────────────────────────────────

def insert_activity(id, channel_id, country, quarter, name, sort_order, created_at):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO activities (id, channel_id, country, quarter, name, sort_order, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (id, channel_id, country, quarter, name, sort_order, created_at))

def update_activity(id, channel_id, country, quarter, name, sort_order, created_at):
    with get_cursor() as cur:
        cur.execute("""
            UPDATE activities SET channel_id=%s, country=%s, quarter=%s, name=%s,
            sort_order=%s, created_at=%s WHERE id=%s
        """, (channel_id, country, quarter, name, sort_order, created_at, id))

def delete_activity(id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM activities WHERE id = %s", (id,))

def count_activities_for_channel(channel_id):
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM activities WHERE channel_id=%s", (channel_id,))
        return cur.fetchone()["count"]

def find_activity(channel_id, country, quarter, name):
    with get_cursor() as cur:
        cur.execute("""
            SELECT * FROM activities
            WHERE channel_id=%s AND country=%s AND quarter=%s AND TRIM(name)=%s
        """, (channel_id, country, quarter, name.strip()))
        row = cur.fetchone()
    return dict(row) if row else None

# ── ENTRIES ───────────────────────────────────────────────────

def insert_entry(row_list):
    """Insert entry from a list matching ENTRY_HEADERS order."""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO entries (id, country, quarter, month, channel_id, channel_name,
                activity_id, activity_name, bu, finance_cat, marketing_cat, description,
                planned, confirmed, actual, jira, vendor, notes, approved,
                invoice_names, invoice_data, entered_by, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, row_list)

def update_entry_full(id, row_list):
    """Update all columns of an entry (row_list excludes id, has 23 values)."""
    with get_cursor() as cur:
        cur.execute("""
            UPDATE entries SET country=%s, quarter=%s, month=%s, channel_id=%s,
                channel_name=%s, activity_id=%s, activity_name=%s, bu=%s,
                finance_cat=%s, marketing_cat=%s, description=%s,
                planned=%s, confirmed=%s, actual=%s, jira=%s, vendor=%s, notes=%s,
                approved=%s, invoice_names=%s, invoice_data=%s,
                entered_by=%s, created_at=%s, updated_at=%s
            WHERE id=%s
        """, row_list + [id])

def update_entry_cell(entry_id, column_name, value):
    """Update a single column of an entry (equivalent to ws.update_cell)."""
    allowed = {
        "channel_id", "channel_name", "activity_id", "activity_name",
        "planned", "confirmed", "actual", "vendor", "notes", "updated_at",
        "bu", "finance_cat", "marketing_cat", "description", "jira",
        "approved", "invoice_names", "invoice_data",
    }
    if column_name not in allowed:
        raise ValueError(f"Column {column_name} not allowed for cell update")
    with get_cursor() as cur:
        cur.execute(f"UPDATE entries SET {column_name} = %s WHERE id = %s", (value, entry_id))

def delete_entry(id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM entries WHERE id = %s", (id,))

def get_entry_by_id(id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM entries WHERE id = %s", (id,))
        row = cur.fetchone()
    return dict(row) if row else None

def get_pm_entries():
    """Get all PM-synced entries (id starts with 'pm_')."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM entries WHERE id LIKE 'pm_%%'")
        rows = cur.fetchall()
    return [dict(r) for r in rows]

# Column index (1-based, matching Google Sheets) → column name mapping for update_cell
ENTRY_COL_MAP = {
    5: "channel_id", 6: "channel_name", 7: "activity_id", 8: "activity_name",
    9: "bu", 10: "finance_cat", 11: "marketing_cat", 12: "description",
    13: "planned", 14: "confirmed", 15: "actual",
    16: "jira", 17: "vendor", 18: "notes",
    24: "updated_at",
}

def update_entry_by_col(entry_id, col_num, value):
    """Update entry by 1-based column number (compatible with ws.update_cell)."""
    col_name = ENTRY_COL_MAP.get(col_num)
    if not col_name:
        raise ValueError(f"Column number {col_num} not mapped")
    update_entry_cell(entry_id, col_name, value)

# ── CHANNEL MAPPING ───────────────────────────────────────────

def replace_all_mappings(mappings, updated_by, updated_at):
    """Replace all mappings (equivalent to ws.clear() + append_rows)."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM channel_mapping")
        for m in mappings:
            cur.execute("""
                INSERT INTO channel_mapping (channel_keyword, bu, finance_cat, marketing_cat, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (m.get("channel_keyword",""), m.get("bu",""), m.get("finance_cat",""),
                  m.get("marketing_cat",""), updated_by, updated_at))

def insert_mapping(channel_keyword, bu, finance_cat, marketing_cat, updated_by, updated_at):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO channel_mapping (channel_keyword, bu, finance_cat, marketing_cat, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (channel_keyword) DO UPDATE
            SET bu=EXCLUDED.bu, finance_cat=EXCLUDED.finance_cat,
                marketing_cat=EXCLUDED.marketing_cat, updated_by=EXCLUDED.updated_by,
                updated_at=EXCLUDED.updated_at
        """, (channel_keyword, bu, finance_cat, marketing_cat, updated_by, updated_at))

# ── VENDORS ───────────────────────────────────────────────────

def insert_vendor(id, name, country, added_by, created_at):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO vendors (id, name, country, added_by, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (id, name, country, added_by, created_at))

def delete_vendor(id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM vendors WHERE id = %s", (id,))

# ── USERS ─────────────────────────────────────────────────────

def insert_user(username, password_hash, display_name, role, markets, created_at):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO users (username, password_hash, display_name, role, markets, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (username, password_hash, display_name, role, markets, created_at))

def update_user(username, password_hash, display_name, role, markets, created_at):
    with get_cursor() as cur:
        cur.execute("""
            UPDATE users SET password_hash=%s, display_name=%s, role=%s, markets=%s, created_at=%s
            WHERE username=%s
        """, (password_hash, display_name, role, markets, created_at, username))

def delete_user(username):
    with get_cursor() as cur:
        cur.execute("DELETE FROM users WHERE username = %s", (username,))

def get_user(username):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (username,))
        row = cur.fetchone()
    return dict(row) if row else None

def get_all_users():
    return get_all("Users")

# ── CATEGORIES ────────────────────────────────────────────────

def insert_category(id, type, value, sort_order, created_at):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO categories (id, type, value, sort_order, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (id, type, value, sort_order, created_at))

def update_category(id, type, value, sort_order, created_at):
    with get_cursor() as cur:
        cur.execute("""
            UPDATE categories SET type=%s, value=%s, sort_order=%s, created_at=%s
            WHERE id=%s
        """, (type, value, sort_order, created_at, id))

def delete_category(id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM categories WHERE id = %s", (id,))

def find_channel(country, quarter, name):
    with get_cursor() as cur:
        cur.execute("""
            SELECT * FROM channels
            WHERE country=%s AND quarter=%s AND TRIM(name)=%s
        """, (country, quarter, name.strip()))
        row = cur.fetchone()
    return dict(row) if row else None
