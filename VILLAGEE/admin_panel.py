#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — admin_panel.py
Admin panel views: main panel, transactions, settings, users, gmail/log/stock menus.
"""

from datetime import datetime, timedelta, timezone
from telegram import InlineKeyboardMarkup

# ============================================================
# TX HISTORY
# ============================================================
def _ts_to_ist(ds):
    if not ds: return "—"
    try:
        dt = datetime.strptime(str(ds).split('.')[0], "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
        return dt.strftime("%d-%m-%Y %I:%M:%S %p")
    except:
        try: return str(ds)
        except: return "—"

def _ist_day_bounds_utc():
    now = now_ist()
    s = now.replace(hour=0, minute=0, second=0, microsecond=0)
    e = s + timedelta(days=1)
    return (s.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            e.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

def _ist_month_bounds_utc():
    now = now_ist()
    s = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if s.month == 12: nm = s.replace(year=s.year+1, month=1)
    else: nm = s.replace(month=s.month+1)
    return (s.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            nm.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

def _fetch_tx_rows(su, eu):
    rows = []
    try:
        for r in cur.execute("""SELECT order_id, user_id, amount, status, utr, txn_id,
            verified_via, paid_amount, date FROM upi_orders
            WHERE date >= ? AND date < ? ORDER BY date DESC""", (su, eu)).fetchall():
            rows.append({"source":"UPI","order_id":r["order_id"],"user_id":r["user_id"],
                         "amount":r["amount"],"paid_amount":r["paid_amount"],"utr":r["utr"],
                         "txn_id":r["txn_id"],"method":(r["verified_via"] or "fampay"),
                         "status":r["status"],"date":r["date"]})
    except: pass
    try:
        for r in cur.execute("""SELECT id, user_id, amount, method_name, status, date FROM deposits
            WHERE date >= ? AND date < ? ORDER BY date DESC""", (su, eu)).fetchall():
            rows.append({"source":"DEPOSIT","order_id":f"DEP-{r['id']}","user_id":r["user_id"],
                         "amount":r["amount"],"paid_amount":r["amount"],"utr":None,"txn_id":None,
                         "method":r["method_name"] or "manual","status":r["status"],"date":r["date"]})
    except: pass
    rows.sort(key=lambda x: str(x["date"] or ""), reverse=True)
    return rows

async def view_admin_tx_today(update, page=1):
    if not is_admin(update.effective_user.id): return
    s, e = _ist_day_bounds_utc()
    await _render_tx_page(update, update.effective_user.id, page, s, e, "📅 TODAY TRANSACTIONS", "today")

async def view_admin_tx_month(update, page=1):
    if not is_admin(update.effective_user.id): return
    s, e = _ist_month_bounds_utc()
    await _render_tx_page(update, update.effective_user.id, page, s, e, "📆 MONTH TRANSACTIONS", "month")

async def _render_tx_page(update, uid, page, s, e, title, kind):
    limit = 10
    rows = _fetch_tx_rows(s, e)
    total = len(rows); tot = 0; ok = 0
    for r in rows:
        try: amt = float(r.get("paid_amount") or r.get("amount") or 0)
        except: amt = 0
        if str(r.get("status") or "").lower() in ("success","approved","completed"):
            tot += amt; ok += 1
    tp = max(1, (total + limit - 1) // limit)
    page = min(max(1, int(page)), tp)
    off = (page - 1) * limit
    pr = rows[off:off + limit]
    tb = [["🆔 ORDER","👤 USER","💰 AMT","🔢 UTR/TXN","📍 METHOD","📊 STATUS","📅 IST"]]
    if not pr: tb.append(["—"]*7)
    for r in pr:
        oid = str(r.get("order_id") or "—")[:16]
        usr = str(r.get("user_id") or "—")
        try: amt = float(r.get("paid_amount") or r.get("amount") or 0)
        except: amt = 0
        utr = str(r.get("utr") or r.get("txn_id") or "—")[:14]
        m = str(r.get("method") or "—")[:14]
        st = str(r.get("status") or "—").upper()[:10]
        tb.append([oid, usr, f"₹{amt:.0f}", utr, m, st, _ts_to_ist(r.get("date"))])
    blocks = [make_heading(title, 2),
              make_table([["ℹ️ SUMMARY","📋 VALUE"],["📄 Page", f"{page}/{tp}"],["📊 Total", str(total)],
                          ["✅ OK", str(ok)],["💰 Amount", f"₹{tot:.0f}"],["🕒 TZ", "IST (UTC+5:30)"]]),
              make_table(tb)]
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"tx_page|{kind}|{page-1}", emoji="🔙", style="primary"))
    if page < tp: nav.append(ibtn("Next", f"tx_page|{kind}|{page+1}", emoji="👉", style="primary"))
    btns = []
    if nav: btns.append(nav)
    btns.append([ibtn("BACK", "adm_gmail_menu", emoji="🔙", style="primary")])
    fb = f"{title} | Page {page}/{tp} | Total {total} | ₹{tot:.0f}"
    await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(btns).to_dict(),
                          fallback_text=fb, edit_query=_edit_query_of(update))


# ============================================================
# PAYMENT METHODS
# ============================================================
async def view_admin_payment_methods(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    fs = get_setting('fampay_status', 'on') == 'on'
    ps = get_setting('paytm_status', 'on') == 'on'
    ms = get_setting('manual_upi_status', 'on') == 'on'
    rows = [
        [ibtn(f"FAMPAY AUTOMATIC: {'ON' if fs else 'OFF'}", "adm_toggle_fampay", emoji="⚡", style="success" if fs else "danger")],
        [ibtn(f"PAYTM AUTOMATIC: {'ON' if ps else 'OFF'}", "adm_toggle_paytm", emoji="💳", style="success" if ps else "danger")],
        [ibtn(f"UPI MANUAL: {'ON' if ms else 'OFF'}", "adm_toggle_manual_upi", emoji="📄", style="success" if ms else "danger")],
        [ibtn("SET FAMPAY UPI", "adm_gmail_set_upi", emoji="🏦", style="primary")],
        [ibtn("SET PAYTM UPI", "adm_paytm_set_upi", emoji="💳", style="primary"),
         ibtn("SET PAYTM MID", "adm_paytm_set_mid", emoji="🆔", style="primary")],
        [ibtn("SET MANUAL UPI", "adm_manual_upi_set", emoji="📄", style="primary")],
        [ibtn("FAMPAY SETTINGS", "adm_gmail_menu", emoji="⚙️", style="primary")],
        [ibtn("BACK", "admin_panel", emoji="🔙", style="primary")],
    ]
    blocks = [make_heading("💳 PAYMENT METHODS", 2),
              make_table([["METHOD", "STATUS"],
                          ["⚡ FamPay Automatic", "ON" if fs else "OFF"],
                          ["💳 Paytm Automatic", "ON" if ps else "OFF"],
                          ["📄 UPI Manual", "ON" if ms else "OFF"],
                          ["🏦 FamPay UPI", (get_fampay_upi_id() or "NOT SET")[:32]],
                          ["💳 Paytm UPI", (get_paytm_upi_id() or "NOT SET")[:32]],
                          ["🆔 Paytm MID", (get_paytm_mid() or "NOT SET")[:32]],
                          ["📄 Manual UPI", (get_manual_upi_id() or "NOT SET")[:32]]])]
    await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                          fallback_text="💳 PAYMENT METHODS", edit_query=_edit_query_of(update))


# ============================================================
# ADMIN PANEL
# ============================================================
async def view_admin_panel(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    try:
        users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        o = cur.execute("SELECT COUNT(*), COALESCE(SUM(price),0) FROM orders").fetchone()
        log_count = len(get_log_targets())
        src = get_log_source_chat(); src_ex = is_source_explicitly_set()
        src_disp = f"{src} {'(set)' if src_ex else '(default)'}"
        gmail = get_setting('gmail_email', '') or "NOT SET"
        gmail_pw = "✅" if get_setting('gmail_app_password','').strip() else "❌"
        gmail_on = "ON" if is_gmail_verify_enabled() else "OFF"
        fampay_upi = get_fampay_upi_id()
        manual_upi = get_manual_upi_id()
        mm = cur.execute("SELECT COUNT(*) FROM upi_orders WHERE status='mismatch'").fetchone()[0]
        dup = cur.execute("SELECT COUNT(*) FROM upi_orders WHERE status='duplicate'").fetchone()[0]
        qr_local = "✅" if QR_AVAILABLE else "❌"
        lzt_t = "✅" if resolve_lzt_token() else "❌"
        osint_cfg = "✅" if osint_is_configured() else "❌"
        osint_docs = "✅" if get_osint_docs_file_id() else "❌"
        min_d = get_min_deposit()
        ulc = get_user_log_channel()
        s2 = cur.execute("SELECT COUNT(*) FROM stock WHERE available=1 AND server='SERVER2'").fetchone()[0]
        s3 = cur.execute("SELECT COUNT(*) FROM file_products WHERE active=1").fetchone()[0]
        force_ch = len(get_all_channels())
        blocks = [make_heading("🛠️ ADMIN PANEL", 2),
            make_table([["📊 STAT","📋 VALUE"],["👥 Users", str(users)],["📦 S2 Stock", str(s2)],
                ["📁 S3 Items", str(s3)],["🛒 Orders", str(o[0])],["💰 Revenue", f"₹{o[1]}"],
                ["📋 Log Targets", str(log_count)],["📤 Source", src_disp[:40]],
                ["📢 User Log", (str(ulc) if ulc else "❌")[:30]],["📧 FamPay", gmail[:30]],
                ["🏦 UPI Auto", fampay_upi[:30]],["📄 UPI Manual", manual_upi[:30]],
                ["🔑 Pwd", gmail_pw],["🌐 Auto", gmail_on],
                ["🔲 QR", qr_local],["🔑 LZT", lzt_t],
                ["🔍 OSINT", f"{osint_cfg} / docs:{osint_docs}"],
                ["📢 ForceJoin", str(force_ch)],
                ["📉 Min ₹", str(min_d)],
                ["🖥️ S1", "ON" if is_server1_online() else "OFF"],
                ["⚠️ Mism", str(mm)],["🚫 Dup", str(dup)],["🟢 Bot", "ON" if is_bot_online() else "OFF"],
                ["🟢 S2", "ON" if is_buy2_online() else "OFF"],["🟢 S3", "ON" if is_buy3_online() else "OFF"]])]
        rows = [
            [ibtn("USERS","adm_users_menu",emoji="👥",style="primary"),
             ibtn("STATS","adm_stats",emoji="📊",style="primary")],
            [ibtn("SERVER 2 STOCK","adm_s2_menu",custom_id=SERVER_EMOJI_IDS["s2"],style="success"),
             ibtn("SERVER 3 STOCK","adm_s3_menu",custom_id=SERVER_EMOJI_IDS["s3"],style="success")],
            [ibtn("ALL STOCK","adm_stock_all",emoji="📦",style="primary"),
             ibtn("CATEGORIES","adm_cat_server_select",emoji="🗂️",style="primary")],
            [ibtn("🔍 OSINT APIs","adm_osint_settings",emoji="🔍",style="success")],
            [ibtn("⚙️ SETTINGS","adm_settings",emoji="⚙️",style="primary"),
             ibtn("💰 BALANCE","adm_bal_menu",custom_id=BALANCE_PREMIUM_EMOJI_ID,style="success")],
            [ibtn("📢 BROADCAST","adm_broadcast",emoji="📢",style="danger"),
             ibtn("📌 BCAST+PIN","adm_broadcast_pin",emoji="📌",style="danger")],
            [ibtn("🎁 COUPONS","adm_coupon_menu",emoji="🎁",style="primary"),
             ibtn("📢 CHANNELS","adm_channels",emoji="📢",style="primary")],
            [ibtn("📋 LOG TARGETS","adm_log_menu",emoji="📋",style="success"),
             ibtn("📢 USER LOGS","adm_userlog_menu",emoji="📢",style="primary")],
            [ibtn("💳 PAYMENT METHODS","admin_payment_methods",emoji="💳",style="success")],
            [ibtn("📧 FAMPAY AUTO","adm_gmail_menu",emoji="📧",style="primary")],
            [ibtn("🖥️ SERVER 1 (LZT)","adm_lzt_settings",emoji="🖥️",style="primary")],
            [ibtn("🔧 MAINTENANCE","adm_maintenance",emoji="🔧",style="danger"),
             ibtn("💾 BACKUP","adm_backup",emoji="💾",style="success")],
            [ibtn("📥 RESTORE","adm_restore",emoji="📥",style="danger")],
        ]
        if is_master_owner(uid):
            rows.append([ibtn("💾 FULL BACKUP","adm_full_backup",emoji="💾",style="danger")])
            rows.append([ibtn("📥 FULL RESTORE","adm_full_restore",emoji="📥",style="danger")])
            rows.append([ibtn("🤖 BOT MANAGER","adm_bots_menu",emoji="🤖",style="danger")])
            rows.append([ibtn("🌍 GLOBAL BROADCAST","adm_global_broadcast",emoji="📢",style="danger")])
        if is_owner(uid):
            rows.append([ibtn("👑 ADMIN MGMT","adm_admin_menu",emoji="👑",style="danger")])
        rows.append([ibtn("🏠 MAIN MENU","home",emoji="🏠",style="primary")])
        fb = f"🛠️ ADMIN — Users {users} | S2 {s2} | S3 {s3}"
        await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                              fallback_text=fb, edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_admin_panel: {e}")


async def view_userlog_menu(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    ulc = get_user_log_channel()
    ud = f"<code>{ulc}</code>" if ulc else "❌ NOT SET"
    blocks = [make_heading("📢 USER PUBLIC LOG", 2),
              make_paragraph("Public logs policy:\n"
                             "• 🆕 New user joined — FULL\n"
                             "• 🎗️ New referral — FULL\n"
                             "• 🛒 Purchase — ID/username MASKED\n"
                             "• 💰 Deposit — ID/username MASKED\n"
                             "• 📦 New stock — MASKED phone"),
              make_table([["ℹ️ INFO","📋 VALUE"],["📢 Channel", ud],
                          ["🟢 Status", "ACTIVE" if ulc else "DISABLED"]])]
    rows = [
        [ibtn("SET CHANNEL","adm_userlog_set",emoji="➕",style="success")],
        [ibtn("USE MY DM","adm_userlog_use_me",emoji="👤",style="primary")],
        [ibtn("TEST","adm_userlog_test",emoji="🧪",style="success")],
        [ibtn("CLEAR","adm_userlog_clear",emoji="❌",style="danger")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                          fallback_text=f"📢 USER LOG",
                          edit_query=_edit_query_of(update))


# ============================================================
# ADMIN SUB-VIEWS
# ============================================================
async def view_admin_gmail_menu(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    ea = get_setting('gmail_email','') or "NOT SET"
    upi = get_fampay_upi_id()
    manual_upi = get_manual_upi_id()
    paytm_upi = get_paytm_upi_id()
    paytm_mid = get_paytm_mid()
    pw = get_setting('gmail_app_password','')
    pwd = "✅ SET" if pw.strip() else "❌ NOT SET"
    en = is_gmail_verify_enabled()
    try:
        te = cur.execute("SELECT COUNT(*) FROM fampay_emails").fetchone()[0]
        mt = cur.execute("SELECT COUNT(*) FROM fampay_emails WHERE matched_order_id IS NOT NULL AND matched_order_id != ''").fetchone()[0]
        mm = cur.execute("SELECT COUNT(*) FROM upi_orders WHERE status='mismatch'").fetchone()[0]
        dp = cur.execute("SELECT COUNT(*) FROM upi_orders WHERE status='duplicate'").fetchone()[0]
        le = cur.execute("SELECT date FROM fampay_emails ORDER BY id DESC LIMIT 1").fetchone()
        ls = le["date"] if le else "Never"
    except: te = mt = mm = dp = 0; ls = "N/A"
    rows = [
        [ibtn("📅 TODAY TX","adm_tx_today",emoji="📅",style="success")],
        [ibtn("📆 MONTH TX","adm_tx_month",emoji="📆",style="success")],
        [ibtn("SET EMAIL","adm_gmail_set_email",emoji="📧",style="primary")],
        [ibtn("SET FAMPAY UPI","adm_gmail_set_upi",emoji="🏦",style="primary"),
         ibtn("SET MANUAL UPI","adm_manual_upi_set",emoji="📄",style="success")],
        [ibtn("SET PAYTM UPI","adm_paytm_set_upi",emoji="💳",style="primary"),
         ibtn("SET PAYTM MID","adm_paytm_set_mid",emoji="🆔",style="primary")],
        [ibtn("SET PWD","adm_gmail_set_pw",emoji="🔑",style="primary")],
        [ibtn(f"{'DISABLE' if en else 'ENABLE'}","adm_gmail_toggle",emoji="🟢",
              style="danger" if en else "success")],
        [ibtn("TEST","adm_gmail_test",emoji="🧪",style="success")],
        [ibtn("RECENT","adm_gmail_recent",emoji="📜",style="primary")],
        [ibtn("MISMATCH","adm_gmail_mismatches",emoji="⚠️",style="danger"),
         ibtn("DUPES","adm_gmail_duplicates",emoji="🚫",style="danger")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("📧 FAMPAY + 💳 PAYTM AUTOMATIC + MANUAL UPI", 2),
        make_paragraph("Payment IDs and Paytm MID are GLOBAL and shared by every configured bot."),
        make_table([["⚙️ SETTING","📋 VALUE"],["📧 Email", ea[:35]],["🏦 FamPay UPI", upi[:35]],
                    ["💳 Paytm UPI", paytm_upi[:35] if paytm_upi else "❌ NOT SET"],
                    ["🆔 Paytm MID", paytm_mid[:35] if paytm_mid else "❌ NOT SET"],
                    ["📄 UPI Manual", manual_upi[:35]],
                    ["🔑 Pwd", pwd],["🟢 Auto", "YES" if en else "NO"],
                    ["📥 Stored", str(te)],["✅ Matched", str(mt)],["⚠️ Mism", str(mm)],
                    ["🚫 Dup", str(dp)],["📅 Last", str(ls)[:19]]])],
        reply_markup=InlineKeyboardMarkup(rows).to_dict(),
        fallback_text="📧 FAMPAY", edit_query=_edit_query_of(update))

async def view_admin_log_menu(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    rd = get_log_targets_full()
    src = get_log_source_chat(); se = is_source_explicitly_set()
    table = [["#","📋 TITLE","🆔 CHAT ID","📦 KIND"]]
    for i, r in enumerate(rd, 1):
        table.append([str(i), (r["title"] or "—")[:22], str(r["chat_id"]), (r["kind"] or "channel").upper()])
    if not rd: table.append(["—","—","—","—"])
    sl = f"🟢 {src}" if se else f"⚪ Default: {src}"
    kb = InlineKeyboardMarkup([
        [ibtn("ADD","adm_log_add",emoji="➕",style="success")],
        [ibtn("REMOVE","adm_log_rem",emoji="🗑️",style="danger"),
         ibtn("REFRESH","adm_log_menu",emoji="🔄",style="primary")],
        [ibtn("SET SOURCE","adm_log_src_set",emoji="📤",style="primary")],
        [ibtn("TEST RICH","adm_log_test",emoji="🧪",style="success")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]])
    await send_rich_async(uid, [make_heading("📋 LOG TARGETS", 2),
        make_paragraph(f"📤 Source: {sl}"), make_table(table)],
        reply_markup=kb.to_dict(), fallback_text="📋 LOG TARGETS",
        edit_query=_edit_query_of(update))

async def view_admin_stock_menu(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    rows = [
        [ibtn("📱 SERVER 2","adm_s2_menu",custom_id=SERVER_EMOJI_IDS["s2"],style="success")],
        [ibtn("📁 SERVER 3","adm_s3_menu",custom_id=SERVER_EMOJI_IDS["s3"],style="success")],
        [ibtn("📦 ALL STOCK","adm_stock_all",emoji="📦",style="primary")],
        [ibtn("🎯 CATEGORIES","adm_cat_server_select",emoji="🗂️",style="primary")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("📦 STOCK MANAGEMENT", 2)],
                          reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                          fallback_text="📦 STOCK", edit_query=_edit_query_of(update))

async def view_admin_stock_all(update, page=1):
    uid = update.effective_user.id
    if not is_admin(uid): return
    limit = 10; offset = (page-1) * limit
    tg = cur.execute("SELECT COUNT(*) FROM stock WHERE available=1").fetchone()[0]
    fp = cur.execute("SELECT COUNT(*) FROM file_products WHERE active=1").fetchone()[0]
    trs = cur.execute("""SELECT phone, country_name, country_icon, category, server, price
        FROM stock WHERE available=1 ORDER BY added_date DESC LIMIT ? OFFSET ?""",
        (limit, offset)).fetchall()
    frs = cur.execute("""SELECT id, name, section, price FROM file_products WHERE active=1
        ORDER BY id DESC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
    items = []
    for r in trs:
        items.append({'type':'tg','title':f"{r['country_icon']} {r['country_name']}",
                      'sub':f"{r['category']} • {r['server']}",'price':r['price'],
                      'cb': f"adm_s2_view|{r['phone']}" if r['server']=='SERVER2' else None})
    for r in frs:
        items.append({'type':'fp','title':f"📦 {r['name']}",'sub':r['section'],
                      'price':r['price'],'cb': f"adm_s3_item|{r['id']}"})
    gt = tg + fp; tp = max(1, (gt + limit - 1) // limit)
    table = [["#","📦 ITEM","🎯 TYPE","💰 PRICE"]]; buttons = []
    for idx, it in enumerate(items, 1):
        table.append([str(idx), it['title'][:30], it['sub'][:20], f"₹{it['price']:.0f}"])
        if it['cb']:
            buttons.append([ibtn(f"{idx}. {it['title'][:25]} • ₹{it['price']:.0f}",
                                 it['cb'], emoji="📦",
                                 style="primary" if it['type']=='tg' else "success")])
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"adm_stock_all|{page-1}", emoji="🔙", style="success"))
    if page < tp: nav.append(ibtn("Next", f"adm_stock_all|{page+1}", emoji="👉", style="success"))
    if nav: buttons.append(nav)
    buttons.append([ibtn("BACK","admin_panel",emoji="🔙",style="primary"),
                    ibtn("HOME","home",emoji="🏠",style="primary")])
    await send_rich_async(uid, [make_heading("📦 ALL STOCK", 2),
        make_table([["ℹ️ INFO","📋 VALUE"],["📦 TG", str(tg)],["📁 Files", str(fp)],
                    ["📄 Page", f"{page}/{tp}"]]),
        make_table(table) if items else make_paragraph("📦 Empty.")],
        reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
        fallback_text=f"ALL STOCK {page}/{tp}", edit_query=_edit_query_of(update))

async def view_admin_cat_server_select(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    rows = [
        [ibtn("SERVER 2","adm_cat|SERVER2",custom_id=SERVER_EMOJI_IDS["s2"],style="primary")],
        [ibtn("PANNELS","adm_cat|PANNELS",emoji="🎯",style="primary")],
        [ibtn("SOURCE CODE","adm_cat|SOURCE CODE",emoji="💻",style="primary")],
        [ibtn("OSINT APIS","adm_cat|OSINT APIS",custom_id=SERVER_EMOJI_IDS["osint"],style="primary")],
        [ibtn("WHATSAPP","adm_cat|WHATSAPP",custom_id=SERVER_EMOJI_IDS["wa"],style="primary")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("🗂️ SELECT SERVER", 2)],
                          reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                          fallback_text="🗂️ SELECT", edit_query=_edit_query_of(update))

async def view_cat_manage(update, server):
    uid = update.effective_user.id
    if not is_admin(uid): return
    rows = cur.execute("SELECT id, name, emoji FROM custom_categories WHERE server=? ORDER BY sort_order, id",
                       (server,)).fetchall()
    table = [["#","🎯 NAME","😀 EMOJI"]]
    for i, r in enumerate(rows, 1): table.append([str(i), r["name"], r["emoji"]])
    kbr = []
    for r in rows:
        kbr.append([ibtn(f"{r['emoji']} {r['name'][:25]}", f"cat_view|{r['id']}", emoji="🎯", style="primary"),
                    ibtn("EDIT", f"cat_edit|{r['id']}", emoji="🔧", style="success"),
                    ibtn("DEL", f"cat_del_ask|{r['id']}", emoji="🗑️", style="danger")])
    kbr.append([ibtn("ADD","adm_cat_add|"+server,emoji="➕",style="success")])
    kbr.append([ibtn("BACK","adm_cat_server_select",emoji="🔙",style="primary")])
    await send_rich_async(uid, [make_heading(f"🗂️ CATEGORIES — {server}", 2),
        make_table([["ℹ️ INFO","📋 VALUE"],["📁 Server", server],["📦 Total", str(len(rows))]]),
        make_table(table) if rows else make_paragraph("No categories.")],
        reply_markup=InlineKeyboardMarkup(kbr).to_dict(),
        fallback_text=f"CATEGORIES {server}", edit_query=_edit_query_of(update))

async def view_admin_settings(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    s = {r["key"]: r["value"] for r in cur.execute("SELECT * FROM settings").fetchall()}
    rows = [
        [ibtn("USDT RATE","adm_usdtrate",emoji="💲",style="primary"),
         ibtn("XFER FEE","adm_edit_transferfee",emoji="📤",style="primary")],
        [ibtn("MIN DEP","adm_edit_mindeposit",emoji="📉",style="primary"),
         ibtn("C1","adm_edit_c1",emoji="📞",style="primary")],
        [ibtn("C2","adm_edit_c2",emoji="📢",style="primary"),
         ibtn("SUPPORT","adm_edit_support",emoji="🔗",style="primary")],
        [ibtn("UPDATE URL","adm_edit_updateurl",emoji="🔗",style="primary")],
        [ibtn("MAINT IMG","adm_edit_maintimg",emoji="🖼️",style="primary")],
        [ibtn("DAYBREAK","adm_edit_default_daybreak",emoji="🗓️",style="primary")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("⚙️ SETTINGS", 2),
        make_table([["⚙️ KEY","📋 VALUE"],["💲 USDT", s.get('usdt_rate','90')],
                    ["📤 Fee", f"{s.get('transfer_fee','10')}%"],
                    ["📉 Min ₹", f"{get_min_deposit()}"],
                    ["🏦 UPI Auto", s.get('fampay_upi_id', DEFAULT_UPI_PAY_ID)],
                    ["📄 UPI Manual", s.get('manual_upi_id', DEFAULT_MANUAL_UPI_ID)],
                    ["📞 C1", s.get('contact_1', DEFAULT_CONTACT_1)],
                    ["🗓️ Daybreak", f"≥{s.get('lzt_default_daybreak', str(DEFAULT_DAYBREAK))}d"],
                    ["📢 C2", s.get('contact_2', DEFAULT_CONTACT_2)]])],
        reply_markup=InlineKeyboardMarkup(rows).to_dict(),
        fallback_text="⚙️ SETTINGS", edit_query=_edit_query_of(update))

async def view_admin_maintenance(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    rows = [
        [ibtn(f"BOT: {'ON' if is_bot_online() else 'OFF'}","adm_toggle_bot",emoji="🤖",
              style="success" if is_bot_online() else "danger")],
        [ibtn(f"SERVER 1: {'ON' if is_server1_online() else 'OFF'}","adm_toggle_buy1",emoji="🖥️",
              style="success" if is_server1_online() else "danger")],
        [ibtn(f"SERVER 2: {'ON' if is_buy2_online() else 'OFF'}","adm_toggle_buy2",emoji="🖥️",
              style="success" if is_buy2_online() else "danger")],
        [ibtn(f"SERVER 3: {'ON' if is_buy3_online() else 'OFF'}","adm_toggle_buy3",emoji="🖥️",
              style="success" if is_buy3_online() else "danger")],
        [ibtn(f"WHATSAPP: {get_setting('wa_status','soon').upper()}","adm_toggle_wa",emoji="🟢",
              style="success" if is_wa_online() else "primary")],
        [ibtn(f"UPI: {'ON' if is_upi_online() else 'OFF'}","adm_toggle_upi",emoji="💳",
              style="success" if is_upi_online() else "danger")],
        [ibtn(f"FAMPAY: {'ON' if is_gmail_verify_enabled() else 'OFF'}","adm_gmail_toggle",emoji="📧",
              style="success" if is_gmail_verify_enabled() else "danger")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("🔧 MAINTENANCE", 2),
        make_paragraph("Toggle Bot & Server status")],
        reply_markup=InlineKeyboardMarkup(rows).to_dict(),
        fallback_text="🔧 MAINTENANCE", edit_query=_edit_query_of(update))

async def view_admin_users_list(update, page=1):
    u = update.effective_user
    if not is_admin(u.id): return
    limit = 20; offset = (page-1) * limit
    total = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    rows = cur.execute("""SELECT user_id, first_name, last_name, username, balance, banned
        FROM users ORDER BY joined_date DESC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
    if not rows:
        try: await update.callback_query.answer("No users", show_alert=True)
        except: pass
        return
    table = [["👤 NAME","🆔 ID","🔗 USERNAME","💰 BAL","🚫"]]
    for r in rows:
        table.append([_full_name(r["first_name"] or "—", r["last_name"] or ""),
                      str(r["user_id"]), f"@{r['username']}" if r["username"] else "—",
                      f"₹{r['balance']:.0f}", "🚫" if r["banned"] else "✅"])
    tp = (total + limit - 1) // limit
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"adm_usr_pg|{page-1}", emoji="🔙", style="primary"))
    if page < tp: nav.append(ibtn("Next", f"adm_usr_pg|{page+1}", emoji="👉", style="primary"))
    kbr = []
    if nav: kbr.append(nav)
    kbr.append([ibtn("BACK","admin_panel",emoji="🔙",style="primary")])
    await send_rich_async(u.id, [make_heading("👥 USERS LIST", 2),
        make_table([["ℹ️ INFO","📋 VALUE"],["👥 Total", str(total)],["📄 Page", f"{page}/{tp}"]]),
        make_table(table)],
        reply_markup=InlineKeyboardMarkup(kbr).to_dict(),
        fallback_text=f"USERS {total}", edit_query=_edit_query_of(update))

async def show_user_info_by_id(update, t_uid):
    u = update.effective_user
    if not is_admin(u.id): return
    r = cur.execute("SELECT * FROM users WHERE user_id=?", (t_uid,)).fetchone()
    if not r:
        try: await u.send_message(f"{emo('❌')} Not found: <code>{t_uid}</code>", parse_mode="HTML")
        except: pass
        return
    name = _full_name(safe_get(r, "first_name", "") or "", safe_get(r, "last_name", "") or "")
    un = f"@{safe_get(r,'username')}" if safe_get(r,'username') else "—"
    rows = [["ℹ️ INFO","📋 DETAILS"],["👤 Name", name],["🆔 ID", str(t_uid)],["🔗 Username", un],
            ["📅 Joined", str(safe_get(r, 'joined_date', 'N/A'))],
            ["💰 Balance", f"₹{safe_get(r,'balance',0)}"],
            ["💳 Deposit", f"₹{safe_get(r, 'total_deposited', 0)}"],
            ["📦 Purchases", str(safe_get(r, 'total_purchases', 0))],
            ["💸 Spent", f"₹{safe_get(r, 'total_spent', 0)}"],
            ["👥 Referrals", str(safe_get(r, 'referral_count', 0))],
            ["🎁 Ref Earn", f"₹{safe_get(r, 'referral_earnings', 0)}"],
            ["🎯 Discount", f"{safe_get(r, 'discount', 0)}%"],
            ["🚫 Status", "🚫 BANNED" if safe_get(r,'banned') else "✅ ACTIVE"]]
    await send_rich_async(u.id, [make_heading(f"👤 {name}", 2), make_table(rows)],
                          fallback_text=f"👤 {name} ({t_uid})")

async def view_admin_lzt_settings(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    ts = "✅ SET" if resolve_lzt_token() else "❌ NOT SET"
    gm = get_setting('lzt_global_markup', '20')
    s1 = "ON" if is_server1_online() else "OFF"
    db = get_setting("lzt_default_daybreak", str(DEFAULT_DAYBREAK))
    try:
        me = await lzt_request('GET', '/me')
        lb = "—"
        if me and 'user' in me: lb = me['user'].get('balance', '—')
    except: lb = "—"
    rows = [
        [ibtn("SET TOKEN","adm_setlzt_token",emoji="🔑",style="primary")],
        [ibtn("GLOBAL MARKUP","adm_set_lzt_markup",custom_id=SERVER_EMOJI_IDS["lzt_markup"],style="primary")],
        [ibtn("DAYBREAK","adm_set_default_daybreak",emoji="🗓️",style="primary")],
        [ibtn("COUNTRY MARKUP","adm_lzt_cmark_list",emoji="🌍",style="primary")],
        [ibtn(f"SERVER 1: {'ON' if is_server1_online() else 'OFF'}","adm_toggle_buy1",emoji="🖥️",
              style="success" if is_server1_online() else "danger")],
        [ibtn("CLEAR CACHE","adm_lzt_clear_cache",emoji="🗑️",style="danger")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("🖥️ SERVER 1 (LZT)", 2),
        make_table([["⚙️ KEY","📋 VALUE"],["🔑 Token", ts],["🟢 Server 1", s1],
                    ["💰 Balance", str(lb)],["💹 Markup", f"{gm}%"],
                    ["🗓️ Daybreak", f"≥{db}d"],["⏱️ Age", f"{ELIGIBILITY_MIN_AGE_SECONDS}s"]])],
        reply_markup=InlineKeyboardMarkup(rows).to_dict(),
        fallback_text="🖥️ S1 SETTINGS", edit_query=_edit_query_of(update))

# ============================================================
# ADMIN BALANCE
# ============================================================
async def process_admin_balance(update, context, action, text):
    uid = update.effective_user.id
    try:
        parts = text.split()
        if len(parts) != 2: raise ValueError("Format: user_id amount")
        t_uid = int(parts[0]); amt = int(parts[1])
        r = cur.execute("SELECT user_id, first_name, last_name, balance FROM users WHERE user_id=?",
                        (t_uid,)).fetchone()
        if not r:
            await update.message.reply_text(f"{emo('❌')} Not found: <code>{t_uid}</code>", parse_mode="HTML")
            temp_data.pop(uid, None); return
        old = r["balance"]
        if action == 'add': new = old + amt
        elif action == 'reduce': new = max(0, old - amt)
        else: new = amt
        cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new, t_uid)); db.commit()
        record_balance_history(t_uid, new - old, f"admin_{action}", "admin", f"By {uid}", old, new)
        aw = {"add":"ADDED","reduce":"REDUCED","set":"UPDATED"}[action]
        sign = f"+{amt}" if action == 'add' else (f"-{amt}" if action == 'reduce' else f"Set ₹{amt}")
        try:
            await context.bot.send_message(t_uid, f"<b>{emo('💰')} BALANCE {aw}</b>\n\n"
                f"{emo('👤')} <code>{t_uid}</code>\n{emo('💰')} Old: ₹{old}\n"
                f"{emo('💵')} {sign}\n{emo('💼')} New: ₹{new}", parse_mode="HTML")
        except: pass
        await update.message.reply_text(f"{emo('✅')} Success!\n\n👤 <code>{t_uid}</code>\n"
            f"💰 Old: ₹{old}\n💼 New: ₹{new}", parse_mode="HTML", reply_markup=main_reply_kb(uid))
        await log_balance_change(uid, t_uid, action, amt, old, new)
    except ValueError as e:
        await update.message.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
    temp_data.pop(uid, None)


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn, main_reply_kb
from config import (
    DEFAULT_CONTACT_1, DEFAULT_CONTACT_2, DEFAULT_DAYBREAK, DEFAULT_MANUAL_UPI_ID,
    DEFAULT_UPI_PAY_ID, ELIGIBILITY_MIN_AGE_SECONDS, IST, log, now_ist
)
from context import cur, db
from database import (
    get_fampay_upi_id, get_manual_upi_id, get_min_deposit, get_setting, is_admin,
    get_paytm_upi_id, get_paytm_mid,
    is_bot_online, is_buy2_online, is_buy3_online, is_gmail_verify_enabled, is_master_owner,
    is_owner, is_server1_online, is_upi_online, is_wa_online, safe_get
)
from emojis import BALANCE_PREMIUM_EMOJI_ID, SERVER_EMOJI_IDS, emo
from force_join import get_all_channels
from history import record_balance_history
from logs import (
    _full_name, get_log_source_chat, get_log_targets, get_log_targets_full,
    get_user_log_channel, is_source_explicitly_set, log_balance_change
)
from lzt_api import lzt_request, resolve_lzt_token
from osint import get_osint_docs_file_id, osint_is_configured
from rich_ui import _edit_query_of, make_heading, make_paragraph, make_table, send_rich_async
from state import temp_data
from utils import QR_AVAILABLE, html_safe_error
