#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — logs.py
Log-channel targets and every log_* function (users, deposits, purchases, admin).
"""

import re
from html import escape

# ============================================================
# LOG TARGETS
# ============================================================
def get_log_targets():
    out = []
    for r in cur.execute("SELECT chat_id FROM log_targets ORDER BY added_date").fetchall():
        try: out.append(int(r[0]))
        except: pass
    return out

def get_log_targets_full():
    return cur.execute("SELECT chat_id, title, kind, added_date FROM log_targets ORDER BY added_date").fetchall()

def add_log_target(chat_id, title="", kind="channel"):
    cur.execute("INSERT OR REPLACE INTO log_targets (chat_id, title, kind) VALUES (?,?,?)",
                (str(chat_id), title, kind)); db.commit()

def remove_log_target(chat_id):
    cur.execute("DELETE FROM log_targets WHERE chat_id=?", (str(chat_id),)); db.commit()

def is_log_target(chat_id):
    return bool(cur.execute("SELECT chat_id FROM log_targets WHERE chat_id=?", (str(chat_id),)).fetchone())

def get_log_source_chat():
    v = get_setting('log_source_chat_id', '').strip()
    if not v: return current_owner_id()
    try: return int(v)
    except: return current_owner_id()

def is_source_explicitly_set(): return bool(get_setting('log_source_chat_id', '').strip())
def set_log_source_chat(chat_id): set_setting('log_source_chat_id', str(chat_id) if chat_id else '')

def get_user_log_channel():
    v = get_setting('user_log_channel_id', '').strip()
    if not v: return None
    try: return int(v)
    except: return None

def set_user_log_channel(chat_id): set_setting('user_log_channel_id', str(chat_id) if chat_id else '')
def has_user_log_channel(): return get_user_log_channel() is not None

def mask_phone_public(phone):
    p = str(phone or "").strip()
    if not p: return "—"
    d = re.sub(r'\D', '', p)
    if len(d) <= 5: return d
    return f"{d[:3]}{'*' * (len(d) - 5)}{d[-2:]}"

def mask_otp_public(otp):
    o = str(otp or "").strip()
    if not o or o == "N/A": return "N/A"
    if len(o) <= 2: return o
    return f"{o[0]}{'*' * (len(o) - 2)}{o[-1]}"

def mask_2fa_public(twofa):
    t = str(twofa or "").strip()
    if not t or t in ("None","N/A","Disabled"): return t or "None"
    if len(t) <= 4: return t
    return f"{t[:2]}{'*' * (len(t) - 4)}{t[-2:]}"


# ============================================================
# LOG FUNCTIONS
# ============================================================
def _now_str(): return now_ist().strftime('%d-%m-%Y %I:%M:%S %p IST')
def _full_name(f, l=""): return f"{f or ''} {l or ''}".strip() or "User"

async def log_new_user(uid, fn, ln, un, referred_by=None):
    un_s = f"@{un}" if un else "—"
    full = _full_name(fn, ln)
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 Name", full],["🆔 User ID", str(uid)],["🔗 Username", un_s]]
    if referred_by:
        rr = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (referred_by,)).fetchone()
        rn = _full_name(rr["first_name"] if rr else "—", rr["last_name"] if rr else "")
        ru = f"@{rr['username']}" if rr and rr['username'] else "—"
        rows.append(["🎗️ Referred By", f"{rn} ({referred_by}) {ru}"])
    rows.append(["📅 Time", _now_str()])
    blocks = [make_heading("🆕 NEW USER JOINED", 2), make_table(rows)]
    fb = f"<b>🆕 NEW USER</b>\n👤 {escape(full)}\n🆔 <code>{uid}</code>"
    await _send_log_rich(blocks, fb)
    if has_user_log_channel():
        try: await _send_user_log_rich(blocks, fb)
        except Exception as e: log.warning(f"log_new_user public: {e}")

async def log_new_referral(ref_uid, new_uid, nfn, nln, nun):
    rr = cur.execute("SELECT first_name, last_name, username, referral_count FROM users WHERE user_id=?", (ref_uid,)).fetchone()
    rn = _full_name(rr["first_name"] if rr else "—", rr["last_name"] if rr else "")
    ru = f"@{rr['username']}" if rr and rr['username'] else "—"
    nfull = _full_name(nfn, nln)
    nus = f"@{nun}" if nun else "—"
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 Referrer", f"{rn} (ID: {ref_uid})"],["🔗 Ref. Username", ru],
            ["🆕 New User ID", f"{nfull} (ID: {new_uid})"],["🔗 New User Username", nus],
            ["📊 Total Referrals", str(rr["referral_count"] if rr else 0)],["📅 Time", _now_str()]]
    blocks = [make_heading("🎗️ NEW REFERRAL JOINED", 2), make_table(rows)]
    fb = f"<b>🎗️ Referral</b> {nfull}"
    await _send_log_rich(blocks, fb)
    if has_user_log_channel():
        try: await _send_user_log_rich(blocks, fb)
        except: pass

async def log_deposit(uid, amount, method, status, dep_id=None, extra=None, photo_file_id=None, utr=None):
    r = cur.execute("SELECT first_name, last_name, username, balance FROM users WHERE user_id=?", (uid,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r['username'] else "—"
    bal = r["balance"] if r else 0
    ic = {"pending":"⏳","approved":"✅","rejected":"❌","mismatch":"⚠️"}.get(status,"ℹ️")
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 Name", nm],["🆔 User", f"{uid} ({un})"],
            ["💰 Amount", f"₹{amount}"],["💳 Method", method]]
    if utr: rows.append(["🔢 UTR / TXID", utr])
    rows.append(["📊 Status", f"{ic} {status.title()}"])
    if dep_id: rows.append(["🆔 Ref ID", str(dep_id)])
    rows.append(["💼 New Balance", f"₹{bal}"]); rows.append(["📅 Time", _now_str()])
    blocks = [make_heading(f"{ic} DEPOSIT {status.upper()}", 2), make_table(rows)]
    fb = f"<b>{ic} DEPOSIT {status.upper()}</b>\n{nm} | ₹{amount}"
    if photo_file_id: await _send_log_photo_rich(photo_file_id, blocks, fb)
    else: await _send_log_rich(blocks, fb)
    if has_user_log_channel():
        try:
            pub_rows = [["ℹ️ INFO","📋 DETAIL"],
                        ["👤 Name", nm],
                        ["🆔 User", mask_user_id_public(uid)],
                        ["🔗 Username", mask_username_public(un)],
                        ["💰 Amount", f"₹{amount}"],
                        ["💳 Method", method]]
            if utr: pub_rows.append(["🔢 UTR / TXID", utr])
            pub_rows.append(["📊 Status", f"{ic} {status.title()}"])
            if dep_id: pub_rows.append(["🆔 Ref ID", str(dep_id)])
            pub_rows.append(["💼 New Balance", f"₹{bal}"])
            pub_rows.append(["📅 Time", _now_str()])
            pub_blocks = [make_heading(f"{ic} DEPOSIT {status.upper()}", 2), make_table(pub_rows)]
            pub_fb = f"<b>{ic} DEPOSIT {status.upper()}</b>\n{nm} | ₹{amount}"
            if photo_file_id:
                await _deliver_rich_photo_to_target(get_user_log_channel(), photo_file_id, pub_blocks, pub_fb)
            else:
                await _send_user_log_rich(pub_blocks, pub_fb)
        except Exception as e: log.warning(f"log_deposit public: {e}")

async def log_purchase(uid, oid, country, price, phone, otp, twofa, rem_bal,
                       status="Completed", is_file=False, deep_link=None):
    r = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (uid,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r['username'] else "—"
    ic = "✅" if status == "Completed" else "⏳"
    if is_file:
        rows = [["ℹ️ INFO","📋 DETAIL"],["👤 User", f"{nm} (ID: {uid})"],["❗ Username", un],
                ["🆔 Order ID", oid],["📦 Item", country],["💀 Price", f"₹{price}"],
                ["💼 Remaining", f"₹{rem_bal}"],["📊 Status", f"{ic} {status}"],["📅 Time", _now_str()]]
        blocks = [make_heading("📖 FILE PRODUCT SOLD", 2), make_table(rows)]
        fb = f"<b>📖 FILE SOLD</b>\n{nm} | {country} | ₹{price}"
    else:
        otp_d = otp if otp and otp != "N/A" else "N/A"
        rows = [["ℹ️ INFO","📋 DETAIL"],["👤 User", f"{nm} (ID: {uid})"],["❗ Username", un],
                ["🆔 Order ID", oid],["🌎 Country", country],["💰 Account Price", f"₹{price}"],
                ["💼 Remaining", f"₹{rem_bal}"],["📱 Number", phone],["🔢 Code", otp_d],
                ["🔐 2FA", twofa],["📊 Status", f"{ic} {status}"],["📅 Time", _now_str()]]
        blocks = [make_heading("🛒 PURCHASE LOG", 2), make_table(rows)]
        fb = f"<b>🛒 PURCHASE</b>\n{nm} | {country} | ₹{price}"
    try:
        btn_block = _purchase_button_block_from_link(deep_link)
        if btn_block: blocks.append(btn_block)
    except Exception as e: log.warning(f"log_purchase btn: {e}")
    await _send_log_rich(blocks, fb)

async def log_purchase_public(uid, oid, country, price, phone, otp, twofa, rem_bal,
                              status="Completed", is_file=False, deep_link=None):
    if not has_user_log_channel(): return
    r = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (uid,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un_raw = f"@{r['username']}" if r and r['username'] else "—"
    un_masked = mask_username_public(un_raw)
    uid_masked = mask_user_id_public(uid)
    ic = "✅" if status == "Completed" else "⏳"
    if is_file:
        rows = [["ℹ️ INFO","📋 DETAIL"],["👤 User", nm],["🆔 User", uid_masked],
                ["🔗 Username", un_masked],["🆔 Order ID", oid],
                ["📦 Item", country],["💰 Price", f"₹{price}"],
                ["📊 Status", f"{ic} {status}"],["📅 Time", _now_str()]]
    else:
        rows = [["ℹ️ INFO","📋 DETAIL"],["👤 User", nm],["🆔 User", uid_masked],
                ["🔗 Username", un_masked],["🆔 Order ID", oid],
                ["🌎 Country", country],["💰 Account Price", f"₹{price}"],
                ["📱 Number", mask_phone_public(phone)],
                ["🔢 Code", mask_otp_public(otp)],
                ["🔐 2FA", mask_2fa_public(twofa)],
                ["📊 Status", f"{ic} {status}"],["📅 Time", _now_str()]]
    blocks = [make_heading("🛒 PURCHASE LOG", 2), make_table(rows)]
    try:
        btn_block = _purchase_button_block_from_link(deep_link)
        if btn_block: blocks.append(btn_block)
    except Exception as e: log.warning(f"log_purchase_public btn: {e}")
    await _send_user_log_rich(blocks, f"<b>🛒 PURCHASE</b>\n{nm} | {country} | ₹{price}")

async def log_purchase_both(uid, oid, country, price, phone, otp, twofa, rem_bal,
                            status="Completed", is_file=False, deep_link=None):
    await log_purchase(uid, oid, country, price, phone, otp, twofa, rem_bal, status, is_file, deep_link)
    try:
        await log_purchase_public(uid, oid, country, price, phone, otp, twofa, rem_bal, status, is_file, deep_link)
    except Exception as e:
        log.warning(f"log_purchase_public: {e}")

async def log_balance_transfer(fr_uid, to_uid, amount, fee, received):
    fr = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (fr_uid,)).fetchone()
    tr = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (to_uid,)).fetchone()
    fn = _full_name(fr["first_name"] if fr else "—", fr["last_name"] if fr else "")
    fu = f"@{fr['username']}" if fr and fr['username'] else "—"
    tn = _full_name(tr["first_name"] if tr else "—", tr["last_name"] if tr else "")
    tu = f"@{tr['username']}" if tr and tr['username'] else "—"
    rows = [["ℹ️ INFO","📋 DETAIL"],["📤 From", f"{fn} ({fr_uid}) {fu}"],
            ["📥 To", f"{tn} ({to_uid}) {tu}"],["💰 Amount", f"₹{amount}"],
            ["💸 Fee", f"₹{fee}"],["✅ Received", f"₹{received}"],["📅 Time", _now_str()]]
    await _send_log_rich([make_heading("📤 BALANCE TRANSFER", 2), make_table(rows)],
                         f"<b>📤 TRANSFER</b> {fn} → {tn}")

async def log_coupon_used(uid, code, amount):
    r = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (uid,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r['username'] else "—"
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 User", f"{nm} (ID: {uid})"],["🔗 Username", un],
            ["🎫 Coupon", code],["💰 Amount", f"+₹{amount}"],["📅 Time", _now_str()]]
    await _send_log_rich([make_heading("🎁 COUPON REDEEMED", 2), make_table(rows)],
                         f"<b>🎁 {code}</b> used")
    if has_user_log_channel():
        pub = [["ℹ️ INFO","📋 DETAIL"],["👤 User", nm],["🎫 Coupon", code],
               ["💰 Amount", f"+₹{amount}"],["📅 Time", _now_str()]]
        try: await _send_user_log_rich([make_heading("🎁 COUPON REDEEMED", 2), make_table(pub)],
                                       f"<b>🎁 {code}</b> redeemed")
        except: pass

async def log_referral_bonus(ref_uid, fr_uid, bonus, ref_amt):
    r = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (ref_uid,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r['username'] else "—"
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 Referrer", f"{nm} (ID: {ref_uid}) {un}"],
            ["🆔 From", str(fr_uid)],["💰 Commission", f"₹{bonus}"],
            ["💳 On Deposit", f"₹{ref_amt}"],["📅 Time", _now_str()]]
    await _send_log_rich([make_heading("🎗️ REFERRAL BONUS", 2), make_table(rows)],
                         f"<b>🎗️ Bonus ₹{bonus}</b>")

async def log_balance_change(admin_uid, t_uid, action, amount, old_bal, new_bal):
    r = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (t_uid,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r['username'] else "—"
    at = {"add":"➕ BALANCE ADDED","reduce":"➖ BALANCE REDUCED","set":"💰 BALANCE SET"}.get(action,"BALANCE CHANGE")
    sign = "+" if action == 'add' else ("-" if action == 'reduce' else "")
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 User", f"{nm} (ID: {t_uid})"],["🔗 Username", un],
            ["🔐 By Admin", str(admin_uid)],["💰 Old Balance", f"₹{old_bal}"],
            ["💵 Change", f"{sign}{amount}"],["💼 New Balance", f"₹{new_bal}"],["📅 Time", _now_str()]]
    await _send_log_rich([make_heading(at, 2), make_table(rows)], f"<b>{at}</b> User={t_uid}")
    if has_user_log_channel():
        pub = [["ℹ️ INFO","📋 DETAIL"],["👤 User", nm],
               ["🆔 User", mask_user_id_public(t_uid)],
               ["💼 New Balance", f"₹{new_bal}"],["📅 Time", _now_str()]]
        try: await _send_user_log_rich([make_heading(at, 2), make_table(pub)], f"<b>{at}</b> {nm}")
        except: pass

async def log_admin_action(admin_uid, action, details=""):
    r = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (admin_uid,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r['username'] else "—"
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 Admin", f"{nm} (ID: {admin_uid})"],
            ["❗ Username", un],["⚡ Action", action]]
    if details: rows.append(["📋 Details", details])
    rows.append(["📅 Time", _now_str()])
    await _send_log_rich([make_heading("🔒 ADMIN ACTION", 2), make_table(rows)], f"<b>🔒 {action}</b>")

async def log_new_stock(admin_uid, phone, country, category, price, server="SERVER2", description=""):
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 By", str(admin_uid)],["📱 Phone", phone],
            ["🌎 Country", country],["🎯 Category", category],["🖥️ Server", server],
            ["💰 Price", f"₹{price}"]]
    if description: rows.append(["📝 Desc", description[:60]])
    rows.append(["📅 Time", _now_str()])
    await _send_log_rich([make_heading("📦 NEW STOCK ADDED", 2), make_table(rows)], f"<b>📦 {phone}</b>")

    if has_user_log_channel():
        try:
            phone_disp = phone
            if phone and str(phone).replace("+", "").isdigit():
                phone_disp = mask_phone_public(phone)
            pub_rows = [["ℹ️ INFO","📋 DETAIL"],
                        ["🌎 Country", country],
                        ["🎯 Category", category],
                        ["🖥️ Server", server],
                        ["💰 Price", f"₹{price}"]]
            if phone and not str(phone).strip().startswith(("Zip","ZIP")):
                pub_rows.append(["📱 Item", str(phone_disp)[:22]])
            pub_rows.append(["📅 Time", _now_str()])
            pub_blocks = [make_heading("📦 NEW STOCK ADDED", 2), make_table(pub_rows)]
            pub_fb = f"<b>📦 NEW STOCK</b>\n{country} | ₹{price}"
            await _send_user_log_rich(pub_blocks, pub_fb)
        except Exception as e:
            log.warning(f"log_new_stock public: {e}")

async def log_stock_removed(admin_uid, phone, country, server):
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 By", str(admin_uid)],["📱 Phone", phone],
            ["🌎 Country", country],["🖥️ Server", server],["📅 Time", _now_str()]]
    await _send_log_rich([make_heading("🗑️ STOCK REMOVED", 2), make_table(rows)], f"<b>🗑️ {phone}</b>")

async def log_stock_edited(admin_uid, phone, changes):
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 By", str(admin_uid)],["📱 Phone", phone]]
    for k, v in changes.items(): rows.append([f"🔧 {k}", str(v)])
    rows.append(["📅 Time", _now_str()])
    await _send_log_rich([make_heading("🔧 STOCK EDITED", 2), make_table(rows)], f"<b>🔧 {phone}</b>")

async def log_user_banned(admin_uid, t_uid, banned=True):
    r = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (t_uid,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r['username'] else "—"
    act = "🚫 BANNED" if banned else "✅ UNBANNED"
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 Target", f"{nm} ({t_uid}) {un}"],
            ["🔐 By", str(admin_uid)],["📊 Status", act],["📅 Time", _now_str()]]
    await _send_log_rich([make_heading(act + " USER", 2), make_table(rows)], f"<b>{act}</b>: {t_uid}")

async def log_target_change(admin_uid, action, chat_id, title=""):
    rows = [["ℹ️ INFO","📋 DETAIL"],["👤 Admin", str(admin_uid)],["⚡ Action", action],
            ["🆔 Chat ID", str(chat_id)],["📝 Title", title or "—"],["📅 Time", _now_str()]]
    await _send_log_rich([make_heading("📋 LOG TARGET UPDATED", 2), make_table(rows)],
                         f"<b>📋 {action}</b>: {chat_id}")


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from config import log, now_ist
from context import cur, current_owner_id, db
from database import get_setting, set_setting
from rich_ui import (
    _deliver_rich_photo_to_target, _purchase_button_block_from_link, _send_log_photo_rich,
    _send_log_rich, _send_user_log_rich, make_heading, make_table
)
from utils import mask_user_id_public, mask_username_public
