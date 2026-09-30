#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — backup.py
Full master ZIP backup/restore and single-bot JSON backup/restore.
"""

import os, json, time, shutil, sqlite3, zipfile, tempfile, io

# ============================================================
# FULL BACKUP / RESTORE (MASTER ONLY)
# ============================================================
def _copy_sqlite_to_path(src_db_path, dst_db_path):
    try:
        src = sqlite3.connect(src_db_path)
        dst = sqlite3.connect(dst_db_path)
        with dst:
            src.backup(dst)
        dst.close(); src.close()
        return True
    except Exception as e:
        log.warning(f"sqlite copy fail {src_db_path}: {e}")
        return False

def create_full_backup_zip():
    buf = io.BytesIO()
    tmp_files = []
    try:
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(BOTS_CONFIG_FILE):
                zf.write(BOTS_CONFIG_FILE, "bots_config.json")
            meta = {
                "created_at": now_ist().isoformat(),
                "master_owner_id": MASTER_OWNER_ID,
                "bot_count": len(BOT_CONTEXTS),
                "version": 3,
            }
            zf.writestr("meta.json", json.dumps(meta, indent=2))
            for ctx in BOT_CONTEXTS:
                un = ctx.username
                base_in_zip = f"bots/{un}"
                try:
                    tmpdb = tempfile.NamedTemporaryFile(delete=False, suffix=".db").name
                    tmp_files.append(tmpdb)
                    if _copy_sqlite_to_path(ctx.db_path, tmpdb):
                        zf.write(tmpdb, f"{base_in_zip}/otp_bot_final.db")
                except Exception as e:
                    log.warning(f"full backup db {un}: {e}")
                for ext in ('.session', '.session-wal', '.session-shm', '.session-journal'):
                    p = os.path.join(ctx.data_dir, f"bot_session_main{ext}")
                    if os.path.exists(p):
                        try: zf.write(p, f"{base_in_zip}/bot_session_main{ext}")
                        except Exception as e: log.warning(f"bak botsess {un} {ext}: {e}")
                sess_dir = os.path.join(ctx.data_dir, "sessions")
                if os.path.isdir(sess_dir):
                    for fn in os.listdir(sess_dir):
                        full = os.path.join(sess_dir, fn)
                        if os.path.isfile(full):
                            try: zf.write(full, f"{base_in_zip}/sessions/{fn}")
                            except Exception as e: log.warning(f"bak sess {un} {fn}: {e}")
        return buf.getvalue()
    finally:
        for f in tmp_files:
            try: os.remove(f)
            except: pass

async def restore_full_backup_zip(zip_bytes, admin_uid):
    counts = {"dbs": 0, "bot_sessions": 0, "user_sessions": 0, "bots_meta": 0}
    bot_names = set()
    tmp_dir = f"full_restore_{int(time.time())}"
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
            zf.extractall(tmp_dir)
        src_cfg = os.path.join(tmp_dir, "bots_config.json")
        if os.path.exists(src_cfg):
            try:
                with open(src_cfg, "r", encoding="utf-8") as f:
                    data = json.load(f)
                counts["bots_meta"] = len(data.get("bots", {}))
            except Exception:
                pass
            try: shutil.copy2(src_cfg, BOTS_CONFIG_FILE)
            except Exception as e: log.warning(f"restore cfg: {e}")
        src_bots_root = os.path.join(tmp_dir, "bots")
        if not os.path.isdir(src_bots_root):
            return counts, bot_names
        for bname in os.listdir(src_bots_root):
            src_bot = os.path.join(src_bots_root, bname)
            if not os.path.isdir(src_bot): continue
            dst_bot = os.path.join("bots", bname)
            os.makedirs(dst_bot, exist_ok=True)
            bot_names.add(bname)
            src_db = os.path.join(src_bot, "otp_bot_final.db")
            if os.path.exists(src_db):
                ctx = BOTS_BY_USERNAME.get(bname)
                try:
                    if ctx:
                        try: ctx.db.close()
                        except: pass
                    dst_db = os.path.join(dst_bot, "otp_bot_final.db")
                    shutil.copy2(src_db, dst_db)
                    for ext in ("-wal","-shm"):
                        try:
                            p = dst_db + ext
                            if os.path.exists(p): os.remove(p)
                        except: pass
                    if ctx:
                        ctx.reopen_db()
                    counts["dbs"] += 1
                except Exception as e:
                    log.warning(f"restore db {bname}: {e}")
            for ext in ('.session', '.session-wal', '.session-shm', '.session-journal'):
                sp = os.path.join(src_bot, f"bot_session_main{ext}")
                if os.path.exists(sp):
                    try:
                        shutil.copy2(sp, os.path.join(dst_bot, f"bot_session_main{ext}"))
                        counts["bot_sessions"] += 1
                    except Exception as e:
                        log.warning(f"restore botsess {bname} {ext}: {e}")
            src_sess = os.path.join(src_bot, "sessions")
            dst_sess = os.path.join(dst_bot, "sessions")
            if os.path.isdir(src_sess):
                os.makedirs(dst_sess, exist_ok=True)
                for fn in os.listdir(src_sess):
                    sp = os.path.join(src_sess, fn)
                    if os.path.isfile(sp):
                        try:
                            shutil.copy2(sp, os.path.join(dst_sess, fn))
                            counts["user_sessions"] += 1
                        except Exception as e:
                            log.warning(f"restore sess {bname} {fn}: {e}")
        return counts, bot_names
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# BACKUP / RESTORE (JSON single-bot)
# ============================================================
def create_backup():
    return {"version": 3, "created_at": now_ist().isoformat(),
            "bot": current_bot_username(), "owner_id": current_owner_id(),
            "users": [dict(r) for r in cur.execute("SELECT * FROM users").fetchall()],
            "stock": [dict(r) for r in cur.execute("SELECT * FROM stock").fetchall()],
            "orders": [dict(r) for r in cur.execute("SELECT * FROM orders").fetchall()],
            "deposits": [dict(r) for r in cur.execute("SELECT * FROM deposits").fetchall()],
            "settings": [dict(r) for r in cur.execute("SELECT * FROM settings").fetchall()],
            "channels": [dict(r) for r in cur.execute("SELECT * FROM channels").fetchall()],
            "admins": [dict(r) for r in cur.execute("SELECT * FROM admins").fetchall()],
            "coupons": [dict(r) for r in cur.execute("SELECT * FROM coupons").fetchall()],
            "custom_categories": [dict(r) for r in cur.execute("SELECT * FROM custom_categories").fetchall()],
            "file_products": [dict(r) for r in cur.execute("SELECT * FROM file_products").fetchall()],
            "balance_transfers": [dict(r) for r in cur.execute("SELECT * FROM balance_transfers").fetchall()],
            "balance_history": [dict(r) for r in cur.execute("SELECT * FROM balance_history").fetchall()],
            "log_targets": [dict(r) for r in cur.execute("SELECT * FROM log_targets").fetchall()],
            "upi_orders": [dict(r) for r in cur.execute("SELECT * FROM upi_orders").fetchall()],
            "fampay_emails": [dict(r) for r in cur.execute("SELECT * FROM fampay_emails").fetchall()],
            "lzt_settings": [dict(r) for r in cur.execute("SELECT * FROM lzt_settings").fetchall()]}

def restore_from_backup(data):
    counts = {}
    try:
        for tbl in ("settings","channels","admins","coupons","custom_categories",
                    "file_products","log_targets","lzt_settings","balance_history"):
            if tbl in data:
                for r in data[tbl]:
                    try:
                        keys = list(r.keys()); vals = [r[k] for k in keys]
                        ph = ",".join("?"*len(keys)); col = ",".join(keys)
                        cur.execute(f"INSERT OR REPLACE INTO {tbl} ({col}) VALUES ({ph})", vals)
                    except: pass
                counts[tbl] = len(data[tbl])
        if "users" in data:
            for r in data["users"]:
                try:
                    cur.execute("""INSERT OR REPLACE INTO users
                        (user_id, balance, referred_by, total_deposited, today_deposited, joined_date,
                         last_deposit_date, banned, discount, terms_accepted, first_name, last_name,
                         username, total_purchases, total_spent, referral_count, referral_earnings)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (r.get("user_id"), r.get("balance",0), r.get("referred_by"),
                         r.get("total_deposited",0), r.get("today_deposited",0), r.get("joined_date"),
                         r.get("last_deposit_date"), r.get("banned",0), r.get("discount",0),
                         r.get("terms_accepted",0), r.get("first_name"), r.get("last_name"),
                         r.get("username"), r.get("total_purchases",0), r.get("total_spent",0),
                         r.get("referral_count",0), r.get("referral_earnings",0)))
                except: pass
            counts["users"] = len(data["users"])
        if "stock" in data:
            for r in data["stock"]:
                try:
                    cur.execute("""INSERT OR REPLACE INTO stock
                        (phone, session_file, country_name, country_icon, account_year, category,
                         server, price, available, twofa, description, added_date)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (r.get("phone"), r.get("session_file"), r.get("country_name"),
                         r.get("country_icon"), r.get("account_year"), r.get("category"),
                         r.get("server","SERVER2"), r.get("price"), r.get("available",1),
                         r.get("twofa","None"), r.get("description",""), r.get("added_date")))
                except: pass
            counts["stock"] = len(data["stock"])
        db.commit(); return counts
    except Exception as e:
        log.error(f"restore: {e}"); return counts


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from config import log, now_ist
from context import (
    BOTS_BY_USERNAME, BOTS_CONFIG_FILE, BOT_CONTEXTS, MASTER_OWNER_ID, cur,
    current_bot_username, current_owner_id, db
)
