#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — database.py
SQLite schema/migrations plus settings, user, admin and ban helpers.
"""

import os, time, sqlite3

# ============================================================
# DB HELPERS + SCHEMA
# ============================================================
def safe_get(row, key, default=0):
    try: return row[key]
    except (IndexError, KeyError): return default

def _ensure_col(table, col, typ):
    try:
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"); db.commit()
    except: pass

def _purge_legacy_dummy_stock():
    d = ("919000000001","919000000002","919000000003","919000000004",
         "919000000005","919000000006","919000000007","919000000008")
    try:
        ph = ",".join("?" * len(d))
        cur.execute(f"DELETE FROM stock WHERE phone IN ({ph})", d)
        cur.execute("DELETE FROM stock WHERE UPPER(server)='SERVER1'"); db.commit()
    except Exception as e: log.warning(f"dummy purge: {e}")

def _init_schema():
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, referred_by INTEGER,
        total_deposited INTEGER DEFAULT 0, today_deposited INTEGER DEFAULT 0,
        joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_deposit_date TEXT,
        banned INTEGER DEFAULT 0, discount INTEGER DEFAULT 0, terms_accepted INTEGER DEFAULT 0,
        first_name TEXT, last_name TEXT, username TEXT,
        total_purchases INTEGER DEFAULT 0, total_spent INTEGER DEFAULT 0,
        referral_count INTEGER DEFAULT 0, referral_earnings REAL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS stock (
        phone TEXT PRIMARY KEY, session_file TEXT, country_name TEXT,
        country_icon TEXT DEFAULT '🌍', account_year INTEGER,
        category TEXT DEFAULT 'NORMAL ACCOUNT', server TEXT DEFAULT 'SERVER2',
        price INTEGER, available INTEGER DEFAULT 1, twofa TEXT DEFAULT 'None',
        description TEXT DEFAULT '', added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
        method_name TEXT, status TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS upi_orders (
        order_id TEXT PRIMARY KEY, user_id INTEGER, amount INTEGER,
        status TEXT, qr_msg_id INTEGER DEFAULT 0, utr TEXT, txn_id TEXT,
        verified_via TEXT, created_ts REAL, paid_amount REAL,
        provider TEXT DEFAULT 'fampay',
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS gmail_processed (
        msg_id TEXT PRIMARY KEY, processed_ts REAL, matched_order_id TEXT, amount REAL
    );
    CREATE TABLE IF NOT EXISTS fampay_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT, msg_id TEXT UNIQUE, amount REAL,
        utr TEXT, txn_id TEXT, order_id TEXT, sender_name TEXT, receiver_name TEXT,
        purpose TEXT, raw_summary TEXT, received_ts REAL, matched_order_id TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, country TEXT,
        year INTEGER, price INTEGER, phone TEXT, otp TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, twofa TEXT, section TEXT DEFAULT 'SERVER2'
    );
    CREATE TABLE IF NOT EXISTS balance_transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, from_uid INTEGER, to_uid INTEGER,
        amount INTEGER, fee INTEGER, received INTEGER,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        p_add_stock INTEGER DEFAULT 0, p_manage_stock INTEGER DEFAULT 0,
        p_stats INTEGER DEFAULT 0, p_bal INTEGER DEFAULT 0, p_settings INTEGER DEFAULT 0,
        p_users INTEGER DEFAULT 0, p_broadcast INTEGER DEFAULT 0,
        p_products INTEGER DEFAULT 0, p_admin_mgmt INTEGER DEFAULT 0,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS coupons (
        code TEXT PRIMARY KEY, amount INTEGER, max_uses INTEGER DEFAULT 1,
        used INTEGER DEFAULT 0, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS channels (channel_id TEXT PRIMARY KEY, channel_link TEXT);
    CREATE TABLE IF NOT EXISTS custom_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, server TEXT NOT NULL,
        name TEXT NOT NULL, emoji TEXT DEFAULT '⭐',
        sort_order INTEGER DEFAULT 0, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS file_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, section TEXT NOT NULL,
        name TEXT NOT NULL, description TEXT DEFAULT '', price INTEGER DEFAULT 500,
        file_link TEXT DEFAULT '', sort_order INTEGER DEFAULT 0, active INTEGER DEFAULT 1,
        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS log_targets (
        chat_id TEXT PRIMARY KEY, title TEXT DEFAULT '',
        kind TEXT DEFAULT 'channel',
        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS lzt_settings (
        country TEXT PRIMARY KEY, markup_percent INTEGER DEFAULT 20
    );
    CREATE TABLE IF NOT EXISTS balance_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
        action TEXT, source TEXT, note TEXT, old_balance INTEGER, new_balance INTEGER,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS referral_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER NOT NULL,
        referred_user_id INTEGER NOT NULL, bonus_amount INTEGER DEFAULT 0,
        deposit_amount INTEGER DEFAULT 0, percent REAL DEFAULT 0,
        event_type TEXT DEFAULT 'bonus',
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS manual_upi_orders (
        order_id TEXT PRIMARY KEY, user_id INTEGER, amount INTEGER,
        utr TEXT, proof_file_id TEXT, status TEXT DEFAULT 'pending',
        reject_reason TEXT, owner_msg_id INTEGER DEFAULT 0,
        created_ts REAL, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    db.commit()
    _ensure_col("orders", "section", "TEXT DEFAULT 'SERVER2'")
    _ensure_col("upi_orders", "provider", "TEXT DEFAULT 'fampay'")
    _ensure_col("file_products", "added_date", "TIMESTAMP")
    _ensure_col("file_products", "item_code", "TEXT")
    _ensure_col("file_products", "api_endpoint", "TEXT")

    # Old pending orders (bot restarted before their timer fired) must not block new ones.
    try:
        cur.execute("UPDATE upi_orders SET status='expired' WHERE status='pending' AND created_ts < ?",
                    (time.time() - 1800,))
        db.commit()
    except Exception:
        pass

    # Prevent concurrent/repeated button taps from creating multiple live
    # orders for the same user/provider/amount. Keep the newest pending row.
    try:
        dup_rows = cur.execute("""
            SELECT user_id, LOWER(COALESCE(provider,'fampay')) AS provider, amount,
                   GROUP_CONCAT(order_id) AS ids, COUNT(*) AS n
            FROM upi_orders
            WHERE status IN ('pending','manual_pending')
            GROUP BY user_id, LOWER(COALESCE(provider,'fampay')), amount
            HAVING COUNT(*) > 1
        """).fetchall()
        for g in dup_rows:
            ids = [x for x in str(g['ids']).split(',') if x]
            keep = cur.execute(
                "SELECT order_id FROM upi_orders WHERE user_id=? AND LOWER(COALESCE(provider,'fampay'))=LOWER(?) AND amount=? AND status IN ('pending','manual_pending') ORDER BY created_ts DESC LIMIT 1",
                (g['user_id'], g['provider'], g['amount'])
            ).fetchone()
            keep_id = keep['order_id'] if keep else ids[-1]
            for oid in ids:
                if oid != keep_id:
                    cur.execute("UPDATE upi_orders SET status='superseded' WHERE order_id=? AND status IN ('pending','manual_pending')", (oid,))
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_upi_one_live_order
            ON upi_orders(user_id, provider, amount)
            WHERE status IN ('pending','manual_pending')
        """)
    except Exception as e:
        log.warning(f"upi live-order uniqueness setup: {e}")
    db.commit()

    if cur.execute("SELECT COUNT(*) FROM log_targets").fetchone()[0] == 0:
        cur.execute("INSERT OR IGNORE INTO log_targets (chat_id, title, kind) VALUES (?,?,?)",
                    (str(LOG_CHANNEL_ID), "Main Log Channel", "channel")); db.commit()

    if cur.execute("SELECT COUNT(*) FROM custom_categories WHERE server='SERVER2'").fetchone()[0] == 0:
        for srv in [("SERVER2","NORMAL ACCOUNT","✅",1),("SERVER2","OLD ACCOUNT","✅",2),
                    ("SERVER2","SPAM ACCOUNT","❌",3),("SERVER2","RARE ACCOUNT","💎",4),
                    ("SERVER2","SCAM TAG ACCOUNT","⚠️",5),("SERVER2","FAKE TAG ACCOUNT","✅",6),
                    ("SERVER2","OLD SCAM FAKE TAG ACCOUNT","⚠️",7)]:
            cur.execute("INSERT INTO custom_categories (server, name, emoji, sort_order) VALUES (?,?,?,?)", srv)
        db.commit()
    if cur.execute("SELECT COUNT(*) FROM custom_categories WHERE server='PANNELS'").fetchone()[0] == 0:
        for p in [("PANNELS","CHEAPEST PHISHING ACCOUNT PANEL","🎯"),
                  ("PANNELS","CHEAPEST NUMBER SWAP PANEL","✈️"),
                  ("PANNELS","CHEAPEST VIRTUAL NO. PANEL","📱"),
                  ("PANNELS","CHEAPEST SMM PANEL","📊")]:
            cur.execute("INSERT INTO custom_categories (server, name, emoji, sort_order) VALUES (?,?,?,?)",
                        (p[0], p[1], p[2], 0))
        db.commit()
    if cur.execute("SELECT COUNT(*) FROM custom_categories WHERE server='SOURCE CODE'").fetchone()[0] == 0:
        for s in [("SOURCE CODE","BOT SRC","🤖"),("SOURCE CODE","APIs SRC","🔗")]:
            cur.execute("INSERT INTO custom_categories (server, name, emoji, sort_order) VALUES (?,?,?,?)",
                        (s[0], s[1], s[2], 0))
        db.commit()
    if cur.execute("SELECT COUNT(*) FROM custom_categories WHERE server='OSINT APIS'").fetchone()[0] == 0:
        for o in [("OSINT APIS","NUMBER INFO","📱"),("OSINT APIS","AADHAR INFO","🆔"),
                  ("OSINT APIS","NAME 2 INFO","👤"),("OSINT APIS","PAN INFO","💳"),
                  ("OSINT APIS","PAN TO GST","🔗"),("OSINT APIS","GST TO PAN","🔗"),
                  ("OSINT APIS","AADHAR TO MASKED PAN","💳"),("OSINT APIS","VOTER EPIC TO INFO","🎯"),
                  ("OSINT APIS","TELEGRAM TO NUMBER","✈️"),("OSINT APIS","PAN NUMBER TO INFO","💳"),
                  ("OSINT APIS","CNIC TO INFO","🆔"),("OSINT APIS","AADHAR TO FAMILY","👥"),
                  ("OSINT APIS","RATION TO FAMILY","👥"),("OSINT APIS","AADHAR TO RATION NUMBER","🔗"),
                  ("OSINT APIS","VEHICLE TO CHALLAN INFO","🚗"),("OSINT APIS","VEHICLE INFO","🚗"),
                  ("OSINT APIS","VEHICLE TO OWNER MOBILE","📱"),
                  ("OSINT APIS","IFSC CODE INFO","🏦"),
                  ("OSINT APIS","ALL LPG GAS INFO","🔥"),
                  ("OSINT APIS","MOBILE TO RC","🚗")]:
            cur.execute("INSERT INTO custom_categories (server, name, emoji, sort_order) VALUES (?,?,?,?)",
                        (o[0], o[1], o[2], 0))
        db.commit()
    if cur.execute("SELECT COUNT(*) FROM custom_categories WHERE server='WHATSAPP'").fetchone()[0] == 0:
        for w in [("WHATSAPP","WA NORMAL ACCOUNT","✅",1),("WHATSAPP","WA OLD ACCOUNT","✅",2),
                  ("WHATSAPP","WA BUSINESS ACCOUNT","💼",3),("WHATSAPP","WA RARE ACCOUNT","💎",4)]:
            cur.execute("INSERT INTO custom_categories (server, name, emoji, sort_order) VALUES (?,?,?,?)", w)
        db.commit()

    if cur.execute("SELECT COUNT(*) FROM file_products WHERE section='PANNELS'").fetchone()[0] == 0:
        for sec, name, price, link in [
            ("PANNELS","CHEAPEST PHISHING ACCOUNT PANEL",500,"https://lzt.market/"),
            ("PANNELS","CHEAPEST VIRTUAL NO. PANEL",1000,"https://grizzlysms.com"),
            ("PANNELS","CHEAPEST NUMBER SWAP PANEL",500,""),
            ("PANNELS","CHEAPEST SMM PANEL",500,"")]:
            cur.execute("""INSERT INTO file_products
                (section, name, price, file_link, description, item_code)
                VALUES (?,?,?,?,?,?)""",
                (sec, name, price, link, f"Premium {name}", generate_item_code()))
        db.commit()
    if cur.execute("SELECT COUNT(*) FROM file_products WHERE section='OSINT APIS'").fetchone()[0] == 0:
        for o in cur.execute("SELECT name FROM custom_categories WHERE server='OSINT APIS'").fetchall():
            ep = OSINT_NAME_TO_ENDPOINT.get(o["name"], "")
            cur.execute("""INSERT INTO file_products
                (section, name, price, file_link, description, item_code, api_endpoint)
                VALUES (?,?,?,?,?,?,?)""",
                ("OSINT APIS", o["name"], 300, "", f"{o['name']} API", generate_item_code(), ep))
        db.commit()

    try:
        for name, ep in OSINT_NAME_TO_ENDPOINT.items():
            cur.execute("""UPDATE file_products SET api_endpoint=?
                WHERE section='OSINT APIS' AND name=?
                AND (api_endpoint IS NULL OR api_endpoint='')""", (ep, name))
        db.commit()
    except Exception as e:
        log.warning(f"backfill osint endpoints: {e}")

    for k, v in [('bot_status','on'),('buy1_status','on'),('buy2_status','on'),('buy3_status','on'),
                 ('wa_status','soon'),('usdt_rate','90.0'),('ref_percent','1.5'),
                 ('support_url',DEFAULT_SUPPORT_URL),('contact_1',DEFAULT_CONTACT_1),
                 ('contact_2',DEFAULT_CONTACT_2),('update_url',DEFAULT_UPDATE_URL),
                 ('upi_revenue','0'),('maintenance_image',MAINTENANCE_IMAGE),('transfer_fee','10'),
                 ('log_source_chat_id',''),('user_log_channel_id',''),('upi_status','on'),
                 ('gmail_email',DEFAULT_GMAIL_EMAIL),('gmail_app_password',DEFAULT_GMAIL_APP_PASSWORD),
                 ('gmail_verify_enabled','on'),('fampay_upi_id',DEFAULT_UPI_PAY_ID),
                 ('lzt_global_markup','20'),('server1_status','on'),
                 ('lzt_default_daybreak', str(DEFAULT_DAYBREAK)),
                 ('min_deposit', str(DEFAULT_MIN_DEPOSIT)),('lzt_token',''),
                 ('osint_owner_id',''),('osint_secret_key',''),
                 ('osint_base_url', OSINT_DEFAULT_BASE_URL),('osint_docs_file_id',''),
                 ('manual_upi_id', DEFAULT_MANUAL_UPI_ID),('fampay_status','on'),('paytm_status','on'),('manual_upi_status','on')]:
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    db.commit()

    try:
        for r in cur.execute("SELECT id FROM file_products WHERE item_code IS NULL OR item_code=''").fetchall():
            cur.execute("UPDATE file_products SET item_code=? WHERE id=?",
                        (generate_item_code(), r["id"]))
        db.commit()
    except Exception as e:
        log.warning(f"backfill item_code: {e}")

    _purge_legacy_dummy_stock()


# ============================================================
# SETTINGS HELPERS
# ============================================================
def get_setting(key, default=""):
    r = cur.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default

def set_setting(key, value):
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value))); db.commit()

def is_bot_online(): return get_setting('bot_status','on') == 'on'
def is_buy1_online(): return get_setting('buy1_status','on') == 'on'
def is_buy2_online(): return get_setting('buy2_status','on') == 'on'
def is_buy3_online(): return get_setting('buy3_status','on') == 'on'
def is_wa_online(): return get_setting('wa_status','soon') == 'on'
def is_upi_online(): return get_setting('upi_status','on') == 'on'
def is_gmail_verify_enabled(): return get_setting('gmail_verify_enabled','on') == 'on'
def is_server1_online(): return get_setting('server1_status','on') == 'on'

# GLOBAL PAYMENT SETTINGS
_GLOBAL_PAYMENT_FILE = "global_payment_settings.json"
def _global_payment_get():
    import json
    try:
        with open(_GLOBAL_PAYMENT_FILE, "r", encoding="utf-8") as f:
            d=json.load(f); return d if isinstance(d,dict) else {}
    except Exception: return {}
def set_global_payment_setting(key, value):
    import json, os
    d=_global_payment_get(); d[key]=str(value).strip()
    tmp=_GLOBAL_PAYMENT_FILE+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(d,f,indent=2,ensure_ascii=False)
    os.replace(tmp,_GLOBAL_PAYMENT_FILE)
def get_global_payment_setting(key, default=""):
    return _global_payment_get().get(key, default)

def get_fampay_upi_id():
    v = get_global_payment_setting('fampay_upi_id', '').strip()
    if v: return v
    v = get_setting('fampay_upi_id', DEFAULT_UPI_PAY_ID).strip()
    return v or DEFAULT_UPI_PAY_ID

def get_manual_upi_id():
    v = get_setting('manual_upi_id', DEFAULT_MANUAL_UPI_ID).strip()
    return v or DEFAULT_MANUAL_UPI_ID

def get_paytm_upi_id():
    v = get_global_payment_setting('paytm_upi_id', '').strip()
    if v: return v
    v = get_setting('paytm_upi_id', '').strip()
    return v or os.getenv('PAYTM_UPI_ID', '').strip()

def get_paytm_mid():
    v = get_global_payment_setting('paytm_mid', '').strip()
    if v: return v
    v = get_setting('paytm_mid', '').strip()
    return v or os.getenv('PAYTM_MID', '').strip()

def get_transfer_fee():
    try: return int(get_setting('transfer_fee', '10'))
    except: return 10

def get_min_deposit():
    try: return max(1, int(float(get_setting('min_deposit', str(DEFAULT_MIN_DEPOSIT)))))
    except: return DEFAULT_MIN_DEPOSIT

def is_master_owner(uid): return uid == MASTER_OWNER_ID

def is_owner(uid):
    if uid == MASTER_OWNER_ID: return True
    c = _current_bot.get()
    return bool(c and uid == c.owner_id)

def is_admin(uid):
    if uid == MASTER_OWNER_ID: return True
    c = _current_bot.get()
    if c and uid == c.owner_id: return True
    try: return bool(cur.execute("SELECT user_id FROM admins WHERE user_id=?", (uid,)).fetchone())
    except: return False

def get_admins(): return cur.execute("SELECT * FROM admins ORDER BY added_at").fetchall()

def ensure_user(uid, fn="", un="", ln=""):
    db.execute("INSERT OR IGNORE INTO users (user_id, first_name, username, last_name) VALUES (?,?,?,?)",
               (uid, fn, un, ln))
    db.execute("UPDATE users SET first_name=?, username=?, last_name=? WHERE user_id=?", (fn, un, ln, uid))
    db.commit()

def get_user(uid): return cur.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()

def get_rate():
    try:
        r = cur.execute("SELECT value FROM settings WHERE key='usdt_rate'").fetchone()
        return float(r[0]) if r else 90.0
    except: return 90.0

def is_banned(uid):
    r = cur.execute("SELECT banned FROM users WHERE user_id=?", (uid,)).fetchone()
    return bool(r and r[0] == 1)

def update_balance(uid, amt):
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid)); db.commit()

def get_support_url():
    url = get_setting('support_url', DEFAULT_SUPPORT_URL)
    if not url.startswith("http"): url = "https://" + url.replace("@", "t.me/")
    return url

def get_contact_1(): return get_setting('contact_1', DEFAULT_CONTACT_1)
def get_contact_2(): return get_setting('contact_2', DEFAULT_CONTACT_2)

def reserve_upi_order(uid, provider, amount, qr_msg_id=0):
    """Create (or reuse) the single live pending order for user/provider/amount.
    NEVER raises because of the 'one live order' unique index: stale pending rows
    are expired automatically and the insert is retried.
    Returns (order_id, reused)."""
    from utils import generate_unique_order_id
    provider = str(provider).lower()
    existing = get_active_upi_order(uid, provider, amount)
    if existing:
        try:
            cur.execute("UPDATE upi_orders SET qr_msg_id=0 WHERE order_id=?", (existing["order_id"],))
            db.commit()
        except Exception:
            pass
        return existing["order_id"], True
    for attempt in range(4):
        oid = generate_unique_order_id(uid)
        try:
            cur.execute("""INSERT INTO upi_orders
                (order_id, user_id, amount, status, qr_msg_id, created_ts, provider)
                VALUES (?,?,?,?,?,?,?)""",
                (oid, uid, amount, "pending", qr_msg_id, time.time(), provider))
            db.commit()
            return oid, False
        except sqlite3.IntegrityError:
            db.rollback()
            # A stale/old live row blocks the unique index -> expire it and retry.
            try:
                cur.execute("""UPDATE upi_orders SET status='expired'
                    WHERE user_id=? AND LOWER(COALESCE(provider,'fampay'))=? AND amount=?
                      AND status IN ('pending','manual_pending')""", (uid, provider, amount))
                db.commit()
            except Exception:
                db.rollback()
    raise RuntimeError("could not create UPI order")

def expire_stale_upi_orders(max_age=1800):
    try:
        cur.execute("UPDATE upi_orders SET status='expired' WHERE status IN ('pending','manual_pending') AND created_ts < ?",
                    (time.time() - max_age,))
        db.commit()
    except Exception:
        pass

def get_active_upi_order(user_id, provider, amount, max_age=1800):
    """Return an existing active order for this user/provider/amount.

    This prevents double-clicks/retries from creating multiple live orders for
    the same payment request. Only a recent pending order is reusable.
    """
    try:
        cutoff = time.time() - float(max_age)
        return cur.execute(
            """SELECT * FROM upi_orders
               WHERE user_id=? AND LOWER(COALESCE(provider,'fampay'))=LOWER(?)
                 AND amount=? AND status IN ('pending','manual_pending') AND created_ts>=?
               ORDER BY created_ts DESC LIMIT 1""",
            (user_id, provider, amount, cutoff),
        ).fetchone()
    except Exception:
        return None

def is_utr_used_by_other_order(utr, cur_oid=None):
    """Return the previous order using this UTR/BANKTXNID.

    For Paytm, BANKTXNID is the UTR and is the authoritative duplicate
    key. Keep previously accepted/rejected payment records so the same
    bank reference cannot later be credited on another order.
    """
    if not utr: return None
    c = str(utr).strip()
    if not c: return None
    blocked = ("success", "duplicate", "mismatch")
    marks = ",".join("?" for _ in blocked)
    if cur_oid:
        r = cur.execute(
            f"""SELECT order_id FROM upi_orders
                WHERE UPPER(utr)=UPPER(?) AND status IN ({marks}) AND order_id != ?
                ORDER BY created_ts ASC LIMIT 1""",
            (c, *blocked, cur_oid),
        ).fetchone()
    else:
        r = cur.execute(
            f"""SELECT order_id FROM upi_orders
                WHERE UPPER(utr)=UPPER(?) AND status IN ({marks})
                ORDER BY created_ts ASC LIMIT 1""",
            (c, *blocked),
        ).fetchone()
    return r["order_id"] if r else None

def is_txn_used_by_other_order(txn, cur_oid=None):
    if not txn: return None
    c = str(txn).strip()
    if not c: return None
    if cur_oid:
        r = cur.execute("""SELECT order_id FROM upi_orders WHERE UPPER(txn_id)=UPPER(?)
            AND status='success' AND order_id != ?""", (c, cur_oid)).fetchone()
    else:
        r = cur.execute("SELECT order_id FROM upi_orders WHERE UPPER(txn_id)=UPPER(?) AND status='success'",
                        (c,)).fetchone()
    return r["order_id"] if r else None


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from config import (
    DEFAULT_CONTACT_1, DEFAULT_CONTACT_2, DEFAULT_DAYBREAK, DEFAULT_GMAIL_APP_PASSWORD,
    DEFAULT_GMAIL_EMAIL, DEFAULT_MANUAL_UPI_ID, DEFAULT_MIN_DEPOSIT, DEFAULT_SUPPORT_URL,
    DEFAULT_UPDATE_URL, DEFAULT_UPI_PAY_ID, LOG_CHANNEL_ID, MAINTENANCE_IMAGE,
    OSINT_DEFAULT_BASE_URL, OSINT_NAME_TO_ENDPOINT, log
)
from context import MASTER_OWNER_ID, _current_bot, cur, db
from utils import generate_item_code
