#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — commands.py
Commands (/start /cancel /admin /stock), deep-link handling, stock view.
"""

import re, asyncio, traceback
from datetime import datetime
from html import escape
from telegram import InlineKeyboardMarkup

# ============================================================
# TEST RICH
# ============================================================
async def test_rich_message(chat_id):
    await _send_log_rich([make_heading("🛒 PREMIUM EMOJI TEST", 2)], "TEST: Heading")
    await asyncio.sleep(1)
    rows = [["ℹ️ INFO","📋 DETAIL"],["🆔","Test ID"],["👤","Test User"],
            ["💰","₹100"],["📅","Test Date"],["✅","SUCCESS"]]
    await _send_log_rich([make_heading("🛒 TABLE TEST", 2),
        make_table(rows, bordered=True, striped=True, compact=False, header_row=True)], "TEST: Table")
    try:
        src = get_log_source_chat()
        sd = f"{src}" + ("" if is_source_explicitly_set() else " (default)")
        await _tg_post("sendMessage", {"chat_id": chat_id,
            "text": f"✅ Test sent.\nSource: <code>{sd}</code>\n{_now_str()}",
            "parse_mode": "HTML"})
    except: pass

# ============================================================
# COMMANDS
# ============================================================
async def _deeplink_unavailable(uid):
    try:
        await send_rich_async(uid, [make_heading(STORE_HEADER, 2),
            make_paragraph("❌ This stock is not available now, try again later..")],
            reply_markup=InlineKeyboardMarkup([
                [ibtn("BUY SERVER (1)","buy1",custom_id=SERVER_EMOJI_IDS["s1"],style="primary"),
                 ibtn("BUY SERVER (2)","buy2",custom_id=SERVER_EMOJI_IDS["s2"],style="primary")],
                [ibtn("HOME","home",emoji="🏠",style="primary")]]).to_dict(),
            fallback_text="❌ This stock is not available now, try again later..")
    except: pass

async def _fake_view_lzt_country(update, iso_code, country_name):
    try:
        flag = LZT_COUNTRY_CATALOG.get(country_name, ("","🌍",""))[1]
        kb = InlineKeyboardMarkup([
            [ibtn(f"View {country_button_label(country_name)}",
                  f"lzt_chk|{iso_code}|1", emoji="🎯", style="success")],
            [ibtn("All Countries","lzt_pg|1",emoji="📋",style="primary")],
            [ibtn("HOME","home",emoji="🏠",style="primary")]])
        await update.message.reply_text(
            f"✅ {flag} <b>{escape(country_name)}</b> — Server 1",
            parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        log.error(f"_fake_view_lzt_country: {e}")

async def _handle_item_deeplink(update, context, arg):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text(f"{emo('🚫')} BANNED", parse_mode="HTML"); return
    r = get_user(uid)
    if not safe_get(r, "terms_accepted", 0) and not is_admin(uid):
        kb = InlineKeyboardMarkup([
            [ibtn("READ TERMS", url=TERMS_URL, emoji="📃", style="primary")],
            [ibtn("ACCEPT","tc_accept",emoji="✅",style="success"),
             ibtn("REJECT","tc_reject",emoji="❌",style="danger")]])
        await update.message.reply_text(f"<b>{emo('📃')} TERMS</b>\nPlease accept first.",
                                          parse_mode="HTML", reply_markup=kb)
        return
    is_ok, miss = await check_user_in_channels(uid, use_cache=False)
    if not is_ok:
        await send_force_join_prompt(uid, miss); return

    try:
        m = re.match(r'^buy_item_(s[123])_(.+)$', arg)
        if not m:
            await _deeplink_unavailable(uid); return
        server = m.group(1)
        rest = m.group(2)

        if server == "s3":
            parts = rest.rsplit("_", 1)
            if len(parts) != 2:
                await _deeplink_unavailable(uid); return
            sec_slug, item_code = parts
            sec_slug = sec_slug.lower()
            section = None
            for s in ("PANNELS", "SOURCE CODE", "OSINT APIS"):
                if slugify_section(s) == sec_slug:
                    section = s; break
            if not section:
                for s in ("PANNELS", "SOURCE CODE", "OSINT APIS"):
                    if s.lower().replace(" ", "") == sec_slug:
                        section = s; break
            if not section:
                await _deeplink_unavailable(uid); return
            p = cur.execute("""SELECT * FROM file_products WHERE section=? AND item_code=?
                               AND active=1 LIMIT 1""", (section, item_code)).fetchone()
            if not p:
                await _deeplink_unavailable(uid); return
            kb = InlineKeyboardMarkup([
                [ibtn("CONFIRM BUY", f"fprod_buy:{p['id']}", emoji="✅", style="success")],
                [ibtn("BACK", f"srv3:{section}", emoji="🔙", style="danger")],
                [ibtn("HOME","home",emoji="🏠",style="danger")]])
            info = [["ℹ️ INFO","📋 DETAIL"],["🆔 Item Code", p["item_code"]],
                    ["📁 Section", p["section"]],["🎯 Name", p["name"]],
                    ["💰 Price", f"₹{p['price']}"],
                    ["📝 Desc", (p["description"] or "—")[:80]]]
            if p["section"] == "OSINT APIS":
                try: ep = p["api_endpoint"]
                except: ep = None
                ep = ep or p["file_link"] or "—"
                info.append(["🔗 Endpoint", str(ep)])
                info.append(["📦 Delivery", "API key + docs (30 days)"])
            elif p["section"] == "PANNELS":
                info.append(["📦 Delivery", "Access link (secret)"])
            else:
                info.append(["📦 Delivery", "Auto — link sent instantly"])
            await send_rich_async(uid, [make_heading(STORE_HEADER, 2),
                make_heading(f"📦 {p['name']}", 3), make_table(info)],
                reply_markup=kb.to_dict(),
                fallback_text=f"📦 {p['name']} — ₹{p['price']}")
            return

        if server == "s1":
            parts = rest.rsplit("_", 1)
            if len(parts) != 2:
                await _deeplink_unavailable(uid); return
            _cat_slug, cc = parts
            country = country_code_to_name(cc)
            if not country:
                await _deeplink_unavailable(uid); return
            iso = LZT_COUNTRY_CATALOG.get(country, ("US","🇺🇸","1"))[0]
            await _fake_view_lzt_country(update, iso, country)
            return

        if server == "s2":
            parts = rest.rsplit("_", 1)
            if len(parts) != 2:
                await _deeplink_unavailable(uid); return
            cat_slug, cc = parts
            country = country_code_to_name(cc)
            if not country:
                await _deeplink_unavailable(uid); return
            category = find_category_by_slug("SERVER2", cat_slug)
            if not category:
                rows = cur.execute("""SELECT name FROM custom_categories
                    WHERE server='SERVER2' AND active=1""").fetchall()
                for rr in rows:
                    if slugify_category(rr["name"]) == cat_slug.lower():
                        category = rr["name"]; break
            if not category:
                await _deeplink_unavailable(uid); return
            match = cur.execute("""SELECT country_name, country_icon FROM stock
                WHERE server='SERVER2' AND available=1 AND category=?
                AND LOWER(country_name) LIKE ? LIMIT 1""",
                (category, f"{country.lower()}%")).fetchone()
            if not match:
                match = cur.execute("""SELECT country_name, country_icon FROM stock
                    WHERE server='SERVER2' AND available=1 AND category=?
                    AND LOWER(country_name) LIKE ? LIMIT 1""",
                    (category, f"%{country.lower()[:3]}%")).fetchone()
            if not match:
                await view_server_section(update, "srv2", category, 1)
                return
            await view_country_items(update, "srv2", category, match["country_name"], 1)
            return

    except Exception as e:
        log.error(f"_handle_item_deeplink: {e}"); traceback.print_exc()
        await _deeplink_unavailable(uid)

async def cmd_start(update, context):
    u = update.effective_user
    ensure_user(u.id, u.first_name or "", u.username or "", u.last_name or "")
    if is_banned(u.id):
        await update.message.reply_text(f"{emo('🚫')} BANNED", parse_mode="HTML"); return
    if not is_bot_online() and not is_admin(u.id):
        await show_maintenance(u.id, "bot"); return
    is_new_user = False
    try:
        chk = cur.execute("SELECT joined_date FROM users WHERE user_id=?", (u.id,)).fetchone()
        if chk:
            jd = safe_get(chk, "joined_date", None)
            if jd:
                try:
                    jt = datetime.strptime(str(jd).split('.')[0], "%Y-%m-%d %H:%M:%S")
                    if (datetime.utcnow() - jt).total_seconds() < 20: is_new_user = True
                except: pass
    except: pass
    referred_by = None
    if context.args:
        arg = context.args[0]
        if re.match(r'^buy_item_s[123]_', arg):
            await _handle_item_deeplink(update, context, arg)
            return
        if arg.startswith("buy_item_"):
            phone = re.sub(r'[^0-9]', '', arg.replace("buy_item_", ""))
            if phone:
                row = cur.execute("SELECT category, country_name FROM stock WHERE phone=?", (phone,)).fetchone()
                if row:
                    await _handle_item_deeplink(update, context,
                        f"buy_item_s2_{slugify_category(row['category'])}_{country_name_to_code(row['country_name'])}")
                else:
                    await _deeplink_unavailable(u.id)
                return
        if arg.startswith("buy_file_"):
            try: pid = int(re.sub(r'[^0-9]', '', arg.replace("buy_file_", "")))
            except: pid = 0
            p = cur.execute("SELECT section, item_code FROM file_products WHERE id=?", (pid,)).fetchone()
            if p and p["item_code"]:
                await _handle_item_deeplink(update, context,
                    f"buy_item_s3_{slugify_section(p['section'])}_{p['item_code']}")
            else:
                await _deeplink_unavailable(u.id)
            return
        if arg.startswith("REF"):
            try:
                rid = int(arg[3:])
                if rid != u.id:
                    cur.execute("UPDATE users SET referred_by=? WHERE user_id=? AND referred_by IS NULL",
                                (rid, u.id))
                    if cur.rowcount:
                        cur.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id=?",
                                    (rid,)); referred_by = rid
                    db.commit()
            except: pass
        elif arg.startswith("server1-"):
            country = find_country_by_slug(arg.split("-", 1)[1])
            if country:
                iso = LZT_COUNTRY_CATALOG[country][0]
                kb = InlineKeyboardMarkup([
                    [ibtn(f"View {country_button_label(country)}", f"lzt_chk|{iso}|1", emoji="🎯", style="success")],
                    [ibtn("All S1","lzt_pg|1",emoji="📋",style="primary")],
                    [ibtn("HOME","home",emoji="🏠",style="primary")]])
                await update.message.reply_text(
                    f"✅ {LZT_COUNTRY_CATALOG[country][1]} <b>{escape(country)}</b>",
                    parse_mode="HTML", reply_markup=kb)
                return
        elif arg == "AllServer1":
            await view_lzt_all_countries(update); return
        elif arg.startswith("buy_s2_"):
            try: await view_buy2(update)
            except: pass
            return
        elif arg.startswith("s3_"):
            try: await view_buy3(update)
            except: pass
            return
    if is_new_user:
        try:
            await log_new_user(u.id, u.first_name or "User", u.last_name or "",
                                u.username or "", referred_by)
            if referred_by:
                await log_new_referral(referred_by, u.id, u.first_name or "User",
                                        u.last_name or "", u.username or "")
        except: pass
    is_ok, miss = await check_user_in_channels(u.id, use_cache=False)
    if not is_ok:
        await send_force_join_prompt(u.id, miss); return
    r = get_user(u.id)
    if not safe_get(r, "terms_accepted", 0) and not is_admin(u.id):
        kb = InlineKeyboardMarkup([
            [ibtn("READ TERMS", url=TERMS_URL, emoji="📃", style="primary")],
            [ibtn("ACCEPT","tc_accept",emoji="✅",style="success"),
             ibtn("REJECT","tc_reject",emoji="❌",style="danger")]])
        await update.message.reply_text(f"<b>{emo('📃')} TERMS</b>\nPlease accept.",
                                          parse_mode="HTML", reply_markup=kb)
        return
    try:
        await update.message.reply_text(
            f"<b>{emo('👋')} Welcome to {STORE_HEADER}</b>\n\n{emo('👉')} Use buttons below:",
            parse_mode="HTML", reply_markup=main_reply_kb(u.id))
    except: pass
    await view_home(update)

async def cmd_cancel(update, context):
    uid = update.effective_user.id
    if user_has_active_operation(uid):
        clear_user_operations(uid)
        manual_upi_pending.pop(uid, None)
        await update.message.reply_text(f"<b>{emo('✅')} Cancelled</b>",
                                          parse_mode="HTML", reply_markup=main_reply_kb(uid))
    else:
        await update.message.reply_text(f"<b>{emo('ℹ️')} NO ACTIVE SESSION</b>",
                                          parse_mode="HTML", reply_markup=main_reply_kb(uid))

async def cmd_admin(update, context):
    if is_admin(update.effective_user.id): await view_admin_panel(update)
    else: await update.message.reply_text(f"{emo('❌')} Not authorized.", parse_mode="HTML")

async def cmd_stock(update, context):
    u = update.effective_user
    ensure_user(u.id, u.first_name or "", u.username or "", u.last_name or "")
    if not is_bot_online() and not is_admin(u.id): return
    if not await enforce_force_join(update): return
    await view_all_stock(update, 1)

async def view_all_stock(update, page=1):
    uid = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    limit = 10; offset = (page - 1) * limit
    tg = cur.execute("SELECT COUNT(*) FROM stock WHERE available=1").fetchone()[0]
    trs = cur.execute("""SELECT phone, country_name, country_icon, category, server, price
        FROM stock WHERE available=1 ORDER BY added_date DESC LIMIT ? OFFSET ?""",
        (limit, offset)).fetchall()
    fp = cur.execute("SELECT COUNT(*) FROM file_products WHERE active=1").fetchone()[0]
    frs = cur.execute("""SELECT id, name, section, price FROM file_products WHERE active=1
        ORDER BY id DESC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
    items = []
    for r in trs:
        items.append({'type':'tg','title':f"{r['country_icon']} {r['country_name']}",
                      'sub':f"{r['category']} • {r['server']}",'price':r['price'],
                      'cb': f"item:{r['phone']}"})
    for r in frs:
        items.append({'type':'fp','title':f"📦 {r['name']}",'sub':r['section'],
                      'price':r['price'],'cb': f"fprod:{r['id']}"})
    gt = tg + fp; tp = max(1, (gt + limit - 1) // limit)
    table = [["#","📦 ITEM","🎯 TYPE","💰 PRICE"]]; buttons = []
    for idx, it in enumerate(items, 1):
        table.append([str(idx), it['title'][:30], it['sub'][:20], f"₹{it['price']:.0f}"])
        buttons.append([ibtn(f"{idx}. {it['title'][:25]} • ₹{it['price']:.0f}", it['cb'], emoji="📦",
                             style="primary" if it['type']=='tg' else "success")])
    blocks = [make_heading(STORE_HEADER, 2),
              make_heading(f"📦 ALL STOCK ({page}/{tp})", 3),
              make_table([["ℹ️ INFO","📋 VALUE"],["📦 TG", str(tg)],["📁 Files", str(fp)],
                          ["📄 Page", f"{page}/{tp}"]]),
              make_table(table) if items else make_paragraph("📦 Empty.")]
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"stock_pg|{page-1}", emoji="🔙", style="success"))
    else: nav.append(ibtn("Refresh", f"stock_pg|{page}", emoji="🔄", style="success"))
    if page < tp: nav.append(ibtn("Next", f"stock_pg|{page+1}", emoji="👉", style="success"))
    else: nav.append(ibtn("—", "noop", emoji="⏳", style="primary"))
    buttons.append(nav)
    buttons.append([ibtn("BUY SERVER (1)","buy1",custom_id=SERVER_EMOJI_IDS["s1"],style="primary"),
                    ibtn("HOME","home",emoji="🏠",style="primary")])
    await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
                          fallback_text=f"ALL STOCK {page}/{tp}",
                          edit_query=_edit_query_of(update), show_placeholder=False)


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from admin_panel import view_admin_panel
from buttons import ibtn, main_reply_kb
from config import STORE_HEADER, TERMS_URL, log
from context import cur, db
from countries import country_code_to_name, country_name_to_code
from database import ensure_user, get_user, is_admin, is_banned, is_bot_online, safe_get
from emojis import SERVER_EMOJI_IDS, emo
from force_join import check_user_in_channels, enforce_force_join, send_force_join_prompt
from logs import (
    _now_str, get_log_source_chat, is_source_explicitly_set, log_new_referral, log_new_user
)
from lzt_api import LZT_COUNTRY_CATALOG, country_button_label, find_country_by_slug
from rich_ui import (
    _edit_query_of, _send_log_rich, _tg_post, make_heading, make_paragraph, make_table,
    send_rich_async
)
from server1 import view_lzt_all_countries
from server2 import view_buy2, view_country_items, view_server_section
from server3 import view_buy3
from state import clear_user_operations, manual_upi_pending, user_has_active_operation
from utils import find_category_by_slug, slugify_category, slugify_section
from views import show_maintenance, view_home
