#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — server3.py
SERVER 3 — file/panel products: views, purchase, admin (S3) views.
"""

import asyncio
from telegram import InlineKeyboardMarkup

async def view_buy3(update):
    uid = update.effective_user.id
    try:
        if not is_buy3_online() and not is_admin(uid):
            await show_maintenance(uid, "buy3"); return
        blocks = [make_heading(STORE_HEADER, 2), make_heading("🛒 SERVER 3", 3),
            make_table([["ℹ️ INFO","📋 DETAIL"],["🖥️ Server","SERVER 3"],["⚡ Status","Active"]])]
        await send_rich_async(uid, blocks, reply_markup=server3_kb().to_dict(),
                              fallback_text="🛒 SERVER 3", edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_buy3: {e}")
        try:
            await _tg_post("sendMessage", {"chat_id": uid,
                "text": "🛒 <b>SERVER 3</b>", "parse_mode": "HTML",
                "reply_markup": server3_kb().to_dict()})
        except: pass


async def view_server3_section(update, section):
    uid = update.effective_user.id
    try:
        products = get_file_products(section)
        if not products:
            kb = InlineKeyboardMarkup([[ibtn("BACK","buy3",emoji="🔙",style="primary")],
                                        [ibtn("HOME","home",emoji="🏠",style="danger")]])
            await send_rich_async(uid, [make_heading(STORE_HEADER, 2),
                make_heading(section, 3), make_paragraph(f"📦 No items.")],
                reply_markup=kb.to_dict(), fallback_text="📦 No items",
                edit_query=_edit_query_of(update)); return
        blocks = [make_heading(STORE_HEADER, 2), make_heading(f"📁 {section}", 3),
                  make_table([["ℹ️ INFO","📋 DETAIL"],["📁 Section", section],
                              ["🎯 Items", str(len(products))],["⚡ Status","Active"]])]
        buttons = []
        for i in range(0, len(products), 2):
            row = []
            for j in range(2):
                if i+j < len(products):
                    p = products[i+j]
                    row.append(ibtn(f"{p['name'][:20]} • ₹{p['price']}", f"fprod:{p['id']}",
                                     emoji="📦", style="primary"))
            buttons.append(row)
        buttons.append([ibtn("BACK","buy3",emoji="🔙",style="danger"),
                        ibtn("HOME","home",emoji="🏠",style="danger")])
        await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
                              fallback_text=f"📁 {section} — {len(products)} items",
                              edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_server3_section: {e}")

async def view_file_product(update, prod_id):
    uid = update.effective_user.id
    try:
        p = cur.execute("SELECT * FROM file_products WHERE id=? AND active=1", (prod_id,)).fetchone()
        if not p:
            try: await update.callback_query.answer("Not found", show_alert=True)
            except: pass
            return
        info = [["ℹ️ INFO","📋 DETAIL"],["🏷️ Item Code", p["item_code"] or "—"],
                ["📁 Section", p["section"]],["🎯 Name", p["name"]],
                ["💰 Price", f"₹{p['price']}"],
                ["📝 Desc", (p["description"] or "—")[:60]]]
        if p["section"] == "OSINT APIS":
            try: ep = p["api_endpoint"]
            except: ep = None
            ep = ep or p["file_link"] or "—"
            info.append(["🔗 Endpoint", str(ep)])
            info.append(["📦 Delivery", "API key + docs (30 days)"])
            info.append(["📖 Docs", "Included with purchase"])
        elif p["section"] == "PANNELS":
            info.append(["📦 Delivery", "Access link (secret)"])
        else:
            info.append(["📦 Delivery", "Auto link"])
        kb = InlineKeyboardMarkup([
            [ibtn("BUY NOW", f"fprod_buy:{prod_id}", emoji="✅", style="success")],
            [ibtn("BACK", f"srv3:{p['section']}", emoji="🔙", style="primary")],
            [ibtn("HOME","home",emoji="🏠",style="danger")]])
        await send_rich_async(uid, [make_heading(STORE_HEADER, 2),
            make_heading(f"📦 {p['name']}", 3), make_table(info)],
            reply_markup=kb.to_dict(),
            fallback_text=f"📦 {p['name']} — ₹{p['price']}", edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_file_product: {e}")


async def view_admin_s3_menu(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    pn = cur.execute("SELECT COUNT(*) FROM file_products WHERE section='PANNELS' AND active=1").fetchone()[0]
    src = cur.execute("SELECT COUNT(*) FROM file_products WHERE section='SOURCE CODE' AND active=1").fetchone()[0]
    oi = cur.execute("SELECT COUNT(*) FROM file_products WHERE section='OSINT APIS' AND active=1").fetchone()[0]
    rows = [
        [ibtn("📦 PANELS","adm_s3_view|PANNELS|1",emoji="📦",style="primary")],
        [ibtn("💻 SOURCE CODE","adm_s3_view|SOURCE CODE|1",emoji="💻",style="primary")],
        [ibtn("🔍 OSINT APIS","adm_s3_view|OSINT APIS|1",custom_id=SERVER_EMOJI_IDS["osint"],style="primary")],
        [ibtn("➕ ADD PANEL","adm_s3_add_panel",emoji="➕",style="success")],
        [ibtn("➕ ADD SRC","adm_s3_add_src",emoji="➕",style="success")],
        [ibtn("➕ ADD API","adm_s3_add_osint",emoji="➕",style="success")],
        [ibtn("🗑️ DELETE ANY","adm_s3_del_pick",emoji="🗑️",style="danger")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("📁 SERVER 3 — FILE PRODUCTS", 2),
        make_table([["ℹ️ SECTION","📦 COUNT"],["📦 PANELS", str(pn)],
                    ["💻 SOURCE CODE", str(src)],["🔍 OSINT APIS", str(oi)]])],
        reply_markup=InlineKeyboardMarkup(rows).to_dict(),
        fallback_text=f"S3: Panels {pn} | Src {src} | API {oi}",
        edit_query=_edit_query_of(update))

async def view_admin_s3_section(update, section, page=1):
    uid = update.effective_user.id
    if not is_admin(uid): return
    limit = 10; offset = (page-1) * limit
    total = cur.execute("SELECT COUNT(*) FROM file_products WHERE section=?", (section,)).fetchone()[0]
    rows = cur.execute("""SELECT id, name, price, file_link, description, active, added_date,
        item_code, api_endpoint
        FROM file_products WHERE section=? ORDER BY id DESC LIMIT ? OFFSET ?""",
        (section, limit, offset)).fetchall()
    if total == 0:
        kb = InlineKeyboardMarkup([[ibtn("BACK","adm_s3_menu",emoji="🔙",style="primary")]])
        await send_rich_async(uid, [make_heading(f"📁 {section}", 2), make_paragraph("📭 Empty.")],
                              reply_markup=kb.to_dict(), fallback_text="Empty",
                              edit_query=_edit_query_of(update)); return
    tp = max(1, (total + limit - 1) // limit)
    buttons = []
    for r in rows:
        st = "✅" if r["active"] else "🔴"
        ep_txt = ""
        try:
            if section == 'OSINT APIS' and r["api_endpoint"]:
                ep_txt = f" ({r['api_endpoint']})"
        except: pass
        buttons.append([ibtn(f"{st} #{r['id']} {r['name'][:25]}{ep_txt} • ₹{r['price']}",
                             f"adm_s3_item|{r['id']}", emoji="📦",
                             style="success" if r["active"] else "danger")])
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"adm_s3_view|{section}|{page-1}", emoji="🔙", style="primary"))
    if page < tp: nav.append(ibtn("Next", f"adm_s3_view|{section}|{page+1}", emoji="👉", style="primary"))
    if nav: buttons.append(nav)
    buttons.append([ibtn("BACK","adm_s3_menu",emoji="🔙",style="primary")])
    await send_rich_async(uid, [make_heading(f"📁 {section}", 2),
        make_table([["ℹ️ INFO","📋 VALUE"],["📄 Page", f"{page}/{tp}"],["📦 Total", str(total)]])],
        reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
        fallback_text=f"{section} {page}/{tp}", edit_query=_edit_query_of(update))

async def view_admin_s3_item(update, pid):
    uid = update.effective_user.id
    if not is_admin(uid): return
    p = cur.execute("SELECT * FROM file_products WHERE id=?", (pid,)).fetchone()
    if not p:
        try: await update.callback_query.answer("Not found", show_alert=True)
        except: pass
        return
    rows = [["ℹ️ INFO","📋 VALUE"],["🆔 ID", str(p["id"])],
            ["🏷️ Item Code", p["item_code"] or "—"],
            ["📁 Section", p["section"]],
            ["🎯 Name", p["name"]],["💰 Price", f"₹{p['price']}"]]
    try:
        ae = p["api_endpoint"]
        if ae: rows.append(["🔗 Endpoint", ae])
    except: pass
    rows.append(["🔗 Link", (p["file_link"] or "—")[:60]])
    rows.append(["📝 Desc", (p["description"] or "—")[:80]])
    rows.append(["📊 Active", "✅" if p["active"] else "🔴"])
    buttons = [
        [ibtn("EDIT NAME", f"adm_s3_edit|name|{pid}", emoji="📝", style="primary"),
         ibtn("EDIT PRICE", f"adm_s3_edit|price|{pid}", emoji="💰", style="primary")],
        [ibtn("EDIT LINK", f"adm_s3_edit|file_link|{pid}", emoji="🔗", style="primary"),
         ibtn("EDIT DESC", f"adm_s3_edit|description|{pid}", emoji="📝", style="primary")],
    ]
    if p["section"] == "OSINT APIS":
        buttons.insert(1, [ibtn("EDIT ENDPOINT",
                                f"adm_s3_edit|api_endpoint|{pid}",
                                emoji="🎯", style="success")])
    buttons.append([ibtn(f"🔁 SET {'INACTIVE' if p['active'] else 'ACTIVE'}",
                         f"adm_s3_toggle|{pid}", emoji="🔁", style="primary")])
    buttons.append([ibtn("🗑️ DELETE", f"adm_s3_del_confirm|{pid}", emoji="🗑️", style="danger")])
    buttons.append([ibtn("BACK", f"adm_s3_view|{p['section']}|1", emoji="🔙", style="primary")])
    await send_rich_async(uid, [make_heading(f"📦 {p['name']}", 2), make_table(rows)],
                          reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
                          fallback_text=f"📦 {p['name']}", edit_query=_edit_query_of(update))


async def process_file_purchase_from_miniapp(uid, prod_id):
    """Real SERVER3 purchase worker for the Mini App (non-OSINT products)."""
    p = cur.execute("SELECT * FROM file_products WHERE id=? AND active=1", (prod_id,)).fetchone()
    if not p:
        raise RuntimeError("Product not found")
    if p['section'] == 'OSINT APIS':
        from osint import process_osint_purchase_from_miniapp
        return await process_osint_purchase_from_miniapp(uid, prod_id)

    r = get_user(uid)
    price = int(p['price'])
    d = int(safe_get(r, 'discount', 0) or 0)
    final = price if d == 0 else int(price * (100 - d) / 100)
    bal = int(safe_get(r, 'balance', 0) or 0)
    if bal < final:
        raise RuntimeError(f"Insufficient balance. Need ₹{final}")

    link = (p['file_link'] or '').strip()
    brand = get_panel_brand_name(p['name'], link) if p['section'] == 'PANNELS' else p['name']
    async with get_user_lock(uid):
        cur.execute("UPDATE users SET balance=balance-?, total_purchases=COALESCE(total_purchases,0)+1, total_spent=COALESCE(total_spent,0)+? WHERE user_id=? AND balance>=?",
                    (final, final, uid, final))
        if cur.rowcount != 1:
            raise RuntimeError("Insufficient balance")
        oid = generate_unique_order_id(uid)
        cur.execute("""INSERT INTO orders (user_id, country, year, price, phone, otp, section)
                    VALUES (?,?,?,?,?,?,?)""",
                    (uid, p['section'], now_ist().year, final, brand, 'FILE', p['section']))
        db.commit()
        record_balance_history(uid, -final, 'purchase', f"server3:{p['section']}",
                               f"Mini App {p['name']}", bal, bal - final)
        r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()

    await log_purchase_both(uid, oid, p['name'], final, 'N/A', 'N/A', 'N/A',
                            r2['balance'] if r2 else 0, status='Completed', is_file=True,
                            deep_link=build_deep_link_s3(p['section'], p['item_code']))
    try: asyncio.create_task(process_referral_bonus(uid, final))
    except Exception: pass
    return {'ok': True, 'order_id': oid, 'amount': final, 'name': p['name'],
            'link': link, 'api_endpoint': p['api_endpoint'] or '',
            'item_code': p['item_code'] or '', 'message': 'Purchase successful.'}


async def process_file_purchase(update, prod_id):
    uid = update.effective_user.id
    p = cur.execute("SELECT * FROM file_products WHERE id=? AND active=1", (prod_id,)).fetchone()
    if not p: return

    if p['section'] == 'OSINT APIS':
        await _process_osint_api_purchase(update, p)
        return

    if p['section'] == 'PANNELS':
        await _process_panel_purchase(update, p)
        return

    r = get_user(uid); price = p['price']
    d = safe_get(r, "discount", 0)
    final = price if d == 0 else int(price * (100 - d) / 100)
    if safe_get(r, "balance", 0) < final:
        kb = InlineKeyboardMarkup([[ibtn("RECHARGE","recharge",emoji="💳",style="success")],
                                    [ibtn("HOME","home",emoji="🏠",style="primary")]])
        try: await update.callback_query.message.reply_text(f"<b>{emo('❌')} INSUFFICIENT</b>\nNeed: ₹{final}",
                                                             parse_mode="HTML", reply_markup=kb)
        except: pass
        return
    async with get_user_lock(uid):
        old = safe_get(r, "balance", 0)
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (final, uid, final))
        if cur.rowcount == 0: return
        oid = generate_unique_order_id(uid)
        cur.execute("""INSERT INTO orders (user_id, country, year, price, phone, otp, section)
                    VALUES (?,?,?,?,?,?,?)""",
                    (uid, p['section'], now_ist().year, final, p['name'], "FILE", p['section']))
        cur.execute("""UPDATE users SET total_purchases=total_purchases+1,
                    total_spent=total_spent+? WHERE user_id=?""", (final, uid))
        db.commit()
        record_balance_history(uid, -final, "purchase", f"server3:{p['section']}",
                               f"Item {p['name']}", old, old - final)
        r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
    await log_purchase_both(uid, oid, p['name'], final, "N/A", "N/A", "N/A",
                            r2["balance"] if r2 else 0, status="Completed", is_file=True,
                            deep_link=build_deep_link_s3(p['section'], p['item_code']))
    link = p['file_link'] or ""
    txt = (f"<b>{emo('✅')} PURCHASE SUCCESSFUL!</b>\n\n{emo('📦')} <b>{p['name']}</b>\n"
           f"{emo('💰')} Paid: ₹{final}\n{emo('🆔')} Order ID: <code>{oid}</code>\n"
           f"{emo('🔗')} Link:\n<code>{link}</code>")
    kb = InlineKeyboardMarkup([
        [ibtn("DOWNLOAD", url=link, emoji="📥", style="success")] if link else
        [ibtn("CONTACT SUPPORT", url=get_support_url(), emoji="📞", style="primary")],
        [ibtn("HOME","home",emoji="🏠",style="primary")]])
    try: await update.callback_query.message.reply_text(txt, parse_mode="HTML", reply_markup=kb)
    except: pass
    try: asyncio.create_task(process_referral_bonus(uid, final))
    except: pass

async def _process_panel_purchase(update, p):
    uid = update.effective_user.id
    r = get_user(uid)
    price = p['price']
    d = safe_get(r, "discount", 0)
    final = price if d == 0 else int(price * (100 - d) / 100)

    if safe_get(r, "balance", 0) < final:
        kb = InlineKeyboardMarkup([
            [ibtn("RECHARGE","recharge",emoji="💳",style="success")],
            [ibtn("HOME","home",emoji="🏠",style="primary")]])
        try:
            await update.callback_query.message.reply_text(
                f"<b>{emo('❌')} INSUFFICIENT BALANCE</b>\n\n"
                f"Need: <b>₹{final}</b>\nHave: ₹{safe_get(r,'balance',0)}",
                parse_mode="HTML", reply_markup=kb)
        except: pass
        return

    link = (p['file_link'] or "").strip()
    brand = get_panel_brand_name(p['name'], link)

    async with get_user_lock(uid):
        old = safe_get(r, "balance", 0)
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
                    (final, uid, final))
        if cur.rowcount == 0: return
        oid = generate_unique_order_id(uid)
        cur.execute("""INSERT INTO orders (user_id, country, year, price, phone, otp, section)
                    VALUES (?,?,?,?,?,?,?)""",
                    (uid, p['section'], now_ist().year, final, brand, "PANEL", p['section']))
        cur.execute("""UPDATE users SET total_purchases=total_purchases+1,
                    total_spent=total_spent+? WHERE user_id=?""", (final, uid))
        db.commit()
        record_balance_history(uid, -final, "purchase", f"server3:{p['section']}",
                               f"Panel {brand}", old, old - final)
        r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()

    await log_purchase_both(uid, oid, brand, final, "N/A", "N/A", "N/A",
                            r2["balance"] if r2 else 0, status="Completed", is_file=True,
                            deep_link=build_deep_link_s3(p['section'], p['item_code']))

    rows_main = [
        ["ℹ️ INFO", "📋 DETAIL"],
        ["📦 PANEL", str(brand)],
        ["💰 Paid", f"₹{final}"],
        ["🆔 Order ID", str(oid)],
    ]
    rows_link = [
        ["🔗 ACCESS LINK", str(link or "—")],
    ]
    rows_footer = [
        ["⚠️ IMPORTANT", "Save this link. Do not share it."],
    ]

    kb = InlineKeyboardMarkup([
        [ibtn("HOME", "home", emoji="🏠", style="primary")],
    ])

    blocks = [
        make_heading(STORE_HEADER, 2),
        make_heading("✅ PANEL PURCHASE SUCCESSFUL!", 3),
        make_table(rows_main),
        make_table(rows_link),
        make_table(rows_footer),
    ]

    fallback = (
        f"✅ PANEL PURCHASE SUCCESSFUL!\n"
        f"📦 {brand}\n💰 ₹{final}\n🆔 {oid}\n"
        f"🔗 {link or '—'}\n"
        f"⚠️ Save this link. Do not share it."
    )

    try:
        await send_rich_async(uid, blocks, reply_markup=kb.to_dict(),
                              fallback_text=fallback, show_placeholder=False)
    except Exception as e:
        log.warning(f"panel rich delivery: {e}")
        try:
            await _tg_post("sendMessage", {"chat_id": uid, "text": fallback,
                "parse_mode": "HTML", "reply_markup": kb.to_dict(),
                "disable_web_page_preview": True})
        except: pass

    try: asyncio.create_task(process_referral_bonus(uid, final))
    except: pass


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import get_file_products, ibtn, server3_kb
from config import STORE_HEADER, log, now_ist
from context import cur, db
from database import get_support_url, get_user, is_admin, is_buy3_online, safe_get
from emojis import SERVER_EMOJI_IDS, emo
from history import record_balance_history
from logs import log_purchase_both
from osint import _process_osint_api_purchase
from payments import process_referral_bonus
from rich_ui import (
    _edit_query_of, _tg_post, build_deep_link_s3, make_heading, make_paragraph, make_table,
    send_rich_async
)
from state import get_user_lock
from utils import generate_unique_order_id, get_panel_brand_name
from views import show_maintenance
