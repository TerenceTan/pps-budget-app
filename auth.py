# -*- coding: utf-8 -*-
"""Authentication helpers, decorators, user/category seeding."""
import os
from datetime import datetime
from functools import wraps
from flask import session, jsonify
from werkzeug.security import generate_password_hash as _gen_ph

def generate_password_hash(password):
    return _gen_ph(password, method='pbkdf2:sha256')
from config import *
from sheets_helper import get_sheet, safe_get_records, invalidate_cache

if USE_POSTGRES:
    import db as pgdb

def _bootstrap_admin():
    """Return (username, password) for the bootstrap admin, or None if disabled.

    Reads BOOTSTRAP_ADMIN_PASSWORD from the environment. Never uses a hardcoded
    fallback — if the env var is not set, seeding is skipped and an existing
    admin must already be present in the database.
    """
    pwd = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "").strip()
    if not pwd:
        return None
    return ("pepper", pwd)

def seed_users():
    """Create a single bootstrap admin if the users table is empty.

    Historical behavior (seeding 9 hardcoded-password accounts) was removed in
    2026-04; those credentials are considered permanently compromised. All
    non-admin users must now be created through the admin UI.
    """
    if USE_POSTGRES:
        if pgdb.get_all_users():
            return
        bootstrap = _bootstrap_admin()
        if not bootstrap:
            print("[SEED] users table is empty and BOOTSTRAP_ADMIN_PASSWORD not set — skipping")
            return
        uname, pwd = bootstrap
        pgdb.insert_user(uname, generate_password_hash(pwd), "Pepper (Admin)", "admin", "ALL", datetime.utcnow().isoformat())
        print(f"[SEED] Created bootstrap admin '{uname}' (PostgreSQL)")
        return

    ws = get_sheet(TAB_USERS)
    all_vals = ws.get_all_values()
    expected = USER_HEADERS
    has_header = len(all_vals) > 0 and all_vals[0] == expected
    has_data = len(all_vals) > 1 if has_header else len(all_vals) > 0

    if has_data and not has_header:
        ws.insert_row(expected, 1)
        ws.format("1:1", {"backgroundColor":{"red":0.11,"green":0.31,"blue":0.24},"textFormat":{"foregroundColor":{"red":1,"green":1,"blue":1},"bold":True}})
        print("[SEED] Inserted missing Users header row")
        return

    if has_data:
        return

    if not has_header:
        ws.append_row(expected)
        ws.format("1:1", {"backgroundColor":{"red":0.11,"green":0.31,"blue":0.24},"textFormat":{"foregroundColor":{"red":1,"green":1,"blue":1},"bold":True}})

    bootstrap = _bootstrap_admin()
    if not bootstrap:
        print("[SEED] users sheet is empty and BOOTSTRAP_ADMIN_PASSWORD not set — skipping")
        return
    uname, pwd = bootstrap
    ws.append_row([uname, generate_password_hash(pwd), "Pepper (Admin)", "admin", "ALL", datetime.utcnow().isoformat()])
    print(f"[SEED] Created bootstrap admin '{uname}'")

def seed_categories():
    if USE_POSTGRES:
        existing = pgdb.get_all(TAB_CATEGORIES)
        if existing: return
        now = datetime.utcnow().isoformat(); i = 0
        for val in DEFAULT_BU_LIST: pgdb.insert_category(f"cat_{i}", "bu", val, i, now); i+=1
        for val in DEFAULT_FIN_CATS: pgdb.insert_category(f"cat_{i}", "finance", val, i, now); i+=1
        for val in DEFAULT_MKT_CATS: pgdb.insert_category(f"cat_{i}", "marketing", val, i, now); i+=1
        print(f"[SEED] Created {i} default categories (PostgreSQL)")
        return
    ws = get_sheet(TAB_CATEGORIES)
    if safe_get_records(ws, TAB_CATEGORIES): return
    now = datetime.utcnow().isoformat()
    i = 0
    for val in DEFAULT_BU_LIST: ws.append_row([f"cat_{i}", "bu", val, i, now]); i+=1
    for val in DEFAULT_FIN_CATS: ws.append_row([f"cat_{i}", "finance", val, i, now]); i+=1
    for val in DEFAULT_MKT_CATS: ws.append_row([f"cat_{i}", "marketing", val, i, now]); i+=1
    print(f"[SEED] Created {i} default categories")

def seed_mapping():
    if USE_POSTGRES:
        now = datetime.utcnow().isoformat()
        for kw,bu,fc,mc in DEFAULT_MAPPING:
            pgdb.insert_mapping(kw,bu,fc,mc,"system",now)
        return
    ws = get_sheet(TAB_MAPPING)
    now = datetime.utcnow().isoformat()
    for kw,bu,fc,mc in DEFAULT_MAPPING:
        ws.append_row([kw,bu,fc,mc,"system",now])

def get_user(username):
    if USE_POSTGRES:
        return pgdb.get_user(username)
    ws = get_sheet(TAB_USERS)
    all_vals = ws.get_all_values()
    if len(all_vals) < 2: return None
    headers = all_vals[0]
    for row in all_vals[1:]:
        user = dict(zip(headers, row))
        if str(user.get("username","")).lower() == username.lower():
            return user
    return None

def get_all_users():
    if USE_POSTGRES:
        return pgdb.get_all_users()
    ws = get_sheet(TAB_USERS)
    all_vals = ws.get_all_values()
    if len(all_vals) < 2: return []
    headers = all_vals[0]
    return [dict(zip(headers, row)) for row in all_vals[1:] if any(cell.strip() for cell in row)]

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("username"):
            return jsonify({"error":"Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            return jsonify({"error":"Admin required"}), 403
        return f(*args, **kwargs)
    return decorated

def check_country_access(country):
    role = session.get("role","")
    if role in ("admin","editor"): return True
    markets = session.get("markets","")
    if markets == "ALL": return True
    return country in [m.strip() for m in markets.split(",")]
