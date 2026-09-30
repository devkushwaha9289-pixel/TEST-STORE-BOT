#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — server2.py
SERVER 2 — user views, purchase flow, auto-OTP and admin stock (S2) views.
"""

import re, time, asyncio, traceback
from telegram import InlineKeyboardMarkup
from telethon import TelegramClient

async def view_buy2(update):
    uid = update.effective_user.id
    try:
        if not is_buy2_online() and not is_admin(uid):
            await show_maintenance(uid, "buy2"); return
        blocks = [make_heading(STORE_HEADER, 2), make_heading("🛒 SERVER 2", 3),
            make_table([["ℹ️ INFO","📋 DETAIL"],["🖥️ Server","SERVER 2"],["⚡ Status","Active"]])]
        kb = server2_kb()
        await send_rich_async(uid, blocks, reply_markup=kb.to_dict(),
                              fallback_text="🛒 SERVER 2", edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_buy2: {e}"); traceback.print_exc()
        try:
            kb = server2_kb()
            await _tg_post("sendMessage", {"chat_id": uid,
                "text": "🛒 <b>SERVER 2</b> — Select category:", "parse_mode": "HTML",
                "reply_markup": kb.to_dict()})
        except Exception as e2:
            log.error(f"view_buy2 fallback: {e2}")


async def view_server_section(update, server, category, page=1):
    uid = update.effective_user.id
    try:
        limit = 20; offset = (page-1) * limit
        srv_map = {"srv2":"SERVER2","srvwa":"WHATSAPP"}
        srv = srv_map.get(server, "SERVER2")
        rows = cur.execute("""SELECT country_icon, country_name, MIN(price) as mp, COUNT(*) as cnt
            FROM stock WHERE available=1 AND server=? AND category=?
            GROUP BY country_name ORDER BY country_name LIMIT ? OFFSET ?""",
            (srv, category, limit, offset)).fetchall()
        total = cur.execute("""SELECT COUNT(DISTINCT country_name) FROM stock
            WHERE available=1 AND server=? AND category=?""", (srv, category)).fetchone()[0]
        if not rows:
            back = {"SERVER2":"buy2","WHATSAPP":"buywa"}.get(srv,"buy2")
            kb = InlineKeyboardMarkup([[ibtn("BACK", back, emoji="🔙", style="primary")],
                                        [ibtn("HOME","home",emoji="🏠",style="primary")]])
            await send_rich_async(uid, [make_heading(STORE_HEADER, 2),
                make_heading(f"🎯 {category}", 3), make_paragraph("📦 No stock.")],
                reply_markup=kb.to_dict(), fallback_text=f"📦 No stock in {category}",
                edit_query=_edit_query_of(update)); return
        rate = get_rate()
        it = [["ℹ️ INFO","📋 DETAIL"],["🖥️ Server", srv],["🎯 Category", category],
              ["💲 Rate", f"1USDT ≈ ₹{rate}"]]
        ct = [["🌎 COUNTRY","💰 PRICE","📦 STOCK"]]; buttons = []
        for ic, cn, mp, cnt in rows:
            ct.append([f"{ic} {cn}", f"₹{mp:.1f}", str(cnt)])
            buttons.append([ibtn(f"{cn} • ₹{mp:.0f}", f"cnt:{server}:{category}:{cn}", raw_flag=ic, style="success")])
        tp = max(1, (total + limit - 1) // limit)
        nav = []
        if page > 1: nav.append(ibtn("Prev", f"pg_srv|{server}|{category}|{page-1}", emoji="🔙", style="primary"))
        if page < tp: nav.append(ibtn("Next", f"pg_srv|{server}|{category}|{page+1}", emoji="👉", style="primary"))
        if nav: buttons.append(nav)
        back = {"SERVER2":"buy2","WHATSAPP":"buywa"}.get(srv,"buy2")
        buttons.append([ibtn("BACK", back, emoji="🔙", style="danger"), ibtn("HOME","home",emoji="🏠",style="danger")])
        blocks = [make_heading(STORE_HEADER, 2),
                  make_heading(f"🎯 {srv} • {category} ({page}/{tp})", 3),
                  make_table(it), make_table(ct)]
        await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
                              fallback_text=f"🎯 {category} — {total} countries",
                              edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_server_section: {e}"); traceback.print_exc()
        try:
            await _tg_post("sendMessage", {"chat_id": uid,
                "text": "⚠️ Couldn't load stock. Try again.", "parse_mode": "HTML",
                "reply_markup": InlineKeyboardMarkup([[ibtn("HOME","home",emoji="🏠",style="primary")]]).to_dict()})
        except: pass


async def view_country_items(update, server, category, country, page=1):
    uid = update.effective_user.id
    try:
        limit = 10; offset = (page-1) * limit
        srv_map = {"srv2":"SERVER2","srvwa":"WHATSAPP"}
        srv = srv_map.get(server, "SERVER2")
        rows = cur.execute("""SELECT phone, country_icon, price FROM stock
            WHERE available=1 AND server=? AND category=? AND country_name LIKE ?
            ORDER BY phone ASC LIMIT ? OFFSET ?""",
            (srv, category, f"{country}%", limit, offset)).fetchall()
        total = cur.execute("""SELECT COUNT(*) FROM stock
            WHERE available=1 AND server=? AND category=? AND country_name LIKE ?""",
            (srv, category, f"{country}%")).fetchone()[0]
        if total == 0:
            back = {"SERVER2":"buy2","WHATSAPP":"buywa"}.get(srv,"buy2")
            kb = InlineKeyboardMarkup([[ibtn("BACK", back, emoji="🔙", style="primary")]])
            await send_rich_async(uid, [make_heading(STORE_HEADER, 2),
                make_paragraph(f"📦 No stock for {country}.")],
                reply_markup=kb.to_dict(), fallback_text="📦 No stock",
                edit_query=_edit_query_of(update)); return
        tp = (total + limit - 1) // limit
        blocks = [make_heading(STORE_HEADER, 2),
                  make_heading(f"🛒 {category} • {country.upper()} ({page}/{tp})", 3),
                  make_table([["ℹ️ INFO","📋 DETAIL"],
                              ["📊 Showing", f"{offset+1} to {min(offset+limit, total)} of {total}"]])]
        buttons = []
        items = [(i, r["phone"], r["country_icon"], r["price"]) for i, r in enumerate(rows, start=offset+1)]
        for i in range(0, len(items), 2):
            rb = []
            for j in range(2):
                if i+j < len(items):
                    idx, phone, ic, pr = items[i+j]
                    rb.append(ibtn(f"{idx}. | ₹{pr:.1f}", f"item:{phone}", raw_flag=ic, style="primary"))
            buttons.append(rb)
        nav = []
        if page > 1: nav.append(ibtn("Prev", f"pg_cnt|{server}|{category}|{country}|{page-1}",
                                       emoji="🔙", style="success"))
        else: nav.append(ibtn("Refresh", f"pg_cnt|{server}|{category}|{country}|{page}",
                                emoji="🔄", style="success"))
        if page < tp: nav.append(ibtn("Next", f"pg_cnt|{server}|{category}|{country}|{page+1}",
                                        emoji="👉", style="success"))
        else: nav.append(ibtn("—", "noop", emoji="⏳", style="primary"))
        buttons.append(nav)
        back = {"SERVER2":"buy2","WHATSAPP":"buywa"}.get(srv,"buy2")
        buttons.append([ibtn("BACK", back, emoji="🔙", style="danger"), ibtn("HOME","home",emoji="🏠",style="danger")])
        await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
                              fallback_text=f"🛒 {category} • {country} — {total}",
                              edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_country_items: {e}")

async def view_product_detail(update, phone):
    uid = update.effective_user.id
    try:
        row = cur.execute("""SELECT phone, country_name, country_icon, account_year, price,
            category, twofa, description FROM stock WHERE phone=? AND available=1""", (phone,)).fetchone()
        if not row:
            try: await update.callback_query.answer("❌ Sold out!", show_alert=True)
            except: pass
            return
        oid = generate_unique_order_id(uid)
        info = [["ℹ️ INFO","📋 DETAIL"],["🆔 Order ID", oid],
                ["🌎 Country", f"{row['country_icon']} {row['country_name'].upper()}"],
                ["💰 Price", f"₹{row['price']:.1f}"],["📦 Availability","1 Account"],
                ["⭐ Quality","Reliable • Good Quality"]]
        if row["description"]: info.append(["📝 Description", row["description"][:80]])
        info.extend(PURCHASE_WARNING_ROWS)
        kb = InlineKeyboardMarkup([
            [ibtn("CONFIRM BUY", f"buy_confirm:{phone}", emoji="✅", style="success")],
            [ibtn("BACK", "back_from_detail", emoji="🔙", style="danger")]])
        blocks = [
            make_heading(STORE_HEADER, 2),
            make_heading("📱 TELEGRAM ACCOUNT", 3),
            make_table(info),
        ]
        await send_rich_async(uid, blocks,
            reply_markup=kb.to_dict(),
            fallback_text=f"📱 {row['country_icon']} {row['country_name']} — ₹{row['price']}",
            edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_product_detail: {e}")

# ============================================================
# PURCHASE FLOW
# ============================================================
async def process_purchase(update, phone):
    uid = update.effective_user.id
    try:
        row = cur.execute("""SELECT phone, session_file, country_icon, country_name, account_year,
            twofa, price, category, server FROM stock WHERE phone=? AND available=1""", (phone,)).fetchone()
        if not row:
            try: await _tg_post("sendMessage", {"chat_id": uid, "parse_mode": "HTML",
                "text": f"{emo('❌')} <b>Sold out!</b>"})
            except: pass
            return
        r = get_user(uid); price = row["price"]
        d = safe_get(r, "discount", 0)
        final = price if d == 0 else int(price * (100 - d) / 100)
        bal = safe_get(r, "balance", 0)
        if bal < final:
            kb = InlineKeyboardMarkup([[ibtn("RECHARGE","recharge",emoji="💳",style="success")],
                                        [ibtn("HOME","home",emoji="🏠",style="primary")]])
            try:
                await _tg_post("sendMessage", {"chat_id": uid, "parse_mode": "HTML",
                    "text": (f"{emo('❌')} <b>INSUFFICIENT</b>\n\nNeed: <b>₹{final}</b>\nHave: ₹{bal}"),
                    "reply_markup": kb.to_dict()})
            except: pass
            return
        async with get_user_lock(uid):
            cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (final, uid, final))
            if cur.rowcount == 0: return
            db.commit()
            record_balance_history(uid, -final, "purchase", f"server2:{row['category']}",
                                   f"Item {phone}", bal, bal - final)
        cur.execute("UPDATE stock SET available=0 WHERE phone=?", (phone,)); db.commit()
        sess = row["session_file"] or f"sessions/{phone}.session"
        clean = sess.replace(".session", "")
        ctx = current_ctx()
        try:
            await _tg_post("sendMessage", {"chat_id": uid, "parse_mode": "HTML",
                "text": f"{emo('⏳')} <b>Processing...</b>\n📱 <code>{phone}</code>\n💰 ₹{final}"})
        except: pass
        try:
            asyncio.create_task(process_purchase_telethon(uid, phone, sess, clean,
                row["country_icon"], row["country_name"], row["account_year"],
                row["twofa"], final, ctx, row["category"], row["server"]))
        except Exception as e:
            log.error(f"purchase task: {e}")
            try:
                async with get_user_lock(uid):
                    r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
                    old = r2["balance"] if r2 else 0
                    cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (final, uid))
                    cur.execute("UPDATE stock SET available=1 WHERE phone=?", (phone,)); db.commit()
                    record_balance_history(uid, final, "refund", "purchase", "Task fail", old, old + final)
            except: pass
    except Exception as e:
        log.error(f"process_purchase: {e}")

async def process_purchase_telethon(uid, phone, sess, clean, c_icon, country, year, twofa, price, ctx,
                                    category="NORMAL ACCOUNT", server="SERVER2"):
    client = None
    try:
        client = TelegramClient(f"{ctx.data_dir}/{clean}", API_ID, API_HASH)
        try:
            await client.connect()
            if not await client.is_user_authorized(): raise Exception("dead session")
        except Exception as e:
            log.warning(f"session fail {phone}: {e}")
            try: await client.disconnect()
            except: pass
            async with get_user_lock(uid):
                cur.execute("DELETE FROM stock WHERE phone=?", (phone,))
                r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
                old = r2["balance"] if r2 else 0
                cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (price, uid)); db.commit()
                record_balance_history(uid, price, "refund", "purchase", "Dead session", old, old + price)
            try:
                await _tg_post("sendMessage", {"chat_id": uid, "parse_mode": "HTML",
                    "text": f"{emo('❌')} Invalid session. ₹{price} refunded."})
            except: pass
            return
        oid = generate_unique_order_id(uid)
        msg = (f"<b>{emo('✅')} ORDER ACTIVE!</b>\n\n"
               f"{emo('🆔')} Order ID: <code>{oid}</code>\n"
               f"{emo('📱')} Phone: <code>{phone}</code>\n"
               f"{emo('🏳️')} Country: {c_icon} {country}\n\n"
               f"<b>{emo('🔻')} INSTRUCTIONS:</b>\n"
               f"{emo('1️⃣')} Add account in Telegram\n"
               f"{emo('2️⃣')} Enter number\n{emo('3️⃣')} OTP auto-sent here.\n\n"
               f"<i>{emo('⏳')} Auto-refund in 10 min if no OTP.</i>")
        msg_id = None
        try:
            sent = await _tg_post("sendMessage", {"chat_id": uid, "text": msg, "parse_mode": "HTML"})
            msg_id = sent.json().get("result", {}).get("message_id")
        except: pass
        r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        await log_purchase_both(uid, oid, f"{c_icon} {country}", price, phone, "N/A", twofa,
                                r2["balance"] if r2 else 0, status="Pending", is_file=False,
                                deep_link=build_deep_link_s2(category, country))
        active_orders[phone] = {'uid': uid, 'client': client, 'sess': sess,
            'start': time.time(), 'paid': False, 'price': price, 'country': country,
            'year': year, 'c_icon': c_icon, 'twofa': twofa, 'msg_id': msg_id,
            'chat_id': uid, 'order_id': oid, 'category': category, 'server': server}
        asyncio.create_task(auto_otp_task(phone))
    except Exception as e:
        log.error(f"process_purchase_telethon: {e}"); traceback.print_exc()
        if client:
            try: await client.disconnect()
            except: pass
        try:
            async with get_user_lock(uid):
                r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
                old = r2["balance"] if r2 else 0
                cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (price, uid))
                cur.execute("UPDATE stock SET available=1 WHERE phone=?", (phone,)); db.commit()
                record_balance_history(uid, price, "refund", "purchase", "Exception", old, old + price)
        except: pass

async def auto_otp_task(phone):
    if phone not in active_orders: return
    o = active_orders[phone]
    client, st, uid = o['client'], o['start'], o['uid']
    while time.time() - st < AUTO_CANCEL_SECONDS:
        if phone not in active_orders: return
        try:
            msgs = await client.get_messages(777000, limit=5)
            code = None
            for m in msgs:
                if m.date.timestamp() > st - 10 and m.message:
                    if re.search(OTP_REGEX, m.message) and "Login detected" not in m.message:
                        code = re.search(OTP_REGEX, m.message).group(); break
            if code:
                if not o['paid']:
                    o['paid'] = True
                    async with get_user_lock(uid):
                        cur.execute("""INSERT INTO orders (user_id, country, year, price, phone, otp, section)
                                    VALUES (?,?,?,?,?,?,?)""",
                                    (uid, o['country'], o['year'], o['price'], phone, code,
                                     o.get('server', 'SERVER2')))
                        cur.execute("""UPDATE users SET total_purchases=total_purchases+1,
                                    total_spent=total_spent+? WHERE user_id=?""", (o['price'], uid))
                        cur.execute("DELETE FROM stock WHERE phone=?", (phone,)); db.commit()
                    r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
                    await log_purchase_both(uid, o.get('order_id', 'N/A'),
                                            f"{o['c_icon']} {o['country']}", o['price'], phone, code,
                                            o['twofa'], r2["balance"] if r2 else 0,
                                            status="Completed", is_file=False,
                                            deep_link=build_deep_link_s2(o.get('category', 'NORMAL ACCOUNT'),
                                                                         o['country']))
                try:
                    await send_otp_rich(uid, phone, o['country'], o['c_icon'], code, o['twofa'],
                                        edit_query=None, masked=False, title="✅ LATEST OTP")
                except Exception as e: log.warning(f"otp user: {e}")
                return
        except: pass
        await asyncio.sleep(6)
    if phone in active_orders and not active_orders[phone]['paid']:
        o = active_orders.pop(phone)
        try: await o['client'].disconnect()
        except: pass
        async with get_user_lock(uid):
            r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
            old = r2["balance"] if r2 else 0
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (o['price'], uid))
            cur.execute("UPDATE stock SET available=1 WHERE phone=?", (phone,)); db.commit()
            record_balance_history(uid, o['price'], "refund", "purchase", "Expired", old, old + o['price'])
        try:
            await _tg_post("sendMessage", {"chat_id": uid, "parse_mode": "HTML",
                "text": f"{emo('⏰')} Order expired. ₹{o['price']} refunded."})
        except: pass


async def view_admin_s2_menu(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    total = cur.execute("SELECT COUNT(*) FROM stock WHERE server='SERVER2'").fetchone()[0]
    avail = cur.execute("SELECT COUNT(*) FROM stock WHERE server='SERVER2' AND available=1").fetchone()[0]
    rows = [
        [ibtn("➕ ADD SINGLE","adm_s2_add_single",emoji="➕",style="success")],
        [ibtn("📦 ADD ZIP","adm_s2_add_zip",emoji="📦",style="success")],
        [ibtn("📋 VIEW ALL","adm_s2_list|1",emoji="📋",style="primary")],
        [ibtn("🗑️ DELETE","adm_s2_del_pick",emoji="🗑️",style="danger")],
        [ibtn("👑 VIEW SOLD","adm_s2_sold|1",emoji="👑",style="primary")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("📱 SERVER 2 — TELEGRAM", 2),
        make_table([["ℹ️ INFO","📋 VALUE"],["📦 Total", str(total)],
                    ["✅ Available", str(avail)],["🛒 Sold", str(total - avail)]])],
        reply_markup=InlineKeyboardMarkup(rows).to_dict(),
        fallback_text=f"S2 Total {total} | Avail {avail} | Sold {total - avail}",
        edit_query=_edit_query_of(update))

async def view_admin_s2_list(update, page=1, category=None, sf="SERVER2", title="📱 SERVER 2 STOCK"):
    uid = update.effective_user.id
    if not is_admin(uid): return
    limit = 10; offset = (page-1) * limit
    where = "server=?"; params = [sf]
    if category:
        where += " AND category=?"; params.append(category)
    total = cur.execute(f"SELECT COUNT(*) FROM stock WHERE {where}", params).fetchone()[0]
    rows = cur.execute(f"""SELECT phone, country_name, country_icon, category, price, available, twofa, added_date
        FROM stock WHERE {where} ORDER BY added_date DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]).fetchall()
    if total == 0:
        kb = InlineKeyboardMarkup([[ibtn("BACK","adm_s2_menu",emoji="🔙",style="primary")]])
        await send_rich_async(uid, [make_heading(title, 2), make_paragraph("📭 Empty.")],
                              reply_markup=kb.to_dict(), fallback_text="Empty",
                              edit_query=_edit_query_of(update)); return
    tp = max(1, (total + limit - 1) // limit)
    table = [["📱 PHONE","🌎 COUNTRY","🎯 CAT","💰 PRICE","📊"]]; buttons = []
    for r in rows:
        st = "✅" if r["available"] else "🔴"
        table.append([str(r["phone"])[:16], f"{r['country_icon']} {r['country_name']}"[:16],
                      str(r["category"])[:14], f"₹{r['price']:.0f}", st])
        buttons.append([ibtn(f"{st} {r['phone']} • ₹{r['price']:.0f}",
                             f"adm_s2_view|{r['phone']}", emoji="📱",
                             style="success" if r["available"] else "danger")])
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"adm_s2_list|{page-1}", emoji="🔙", style="primary"))
    if page < tp: nav.append(ibtn("Next", f"adm_s2_list|{page+1}", emoji="👉", style="primary"))
    if nav: buttons.append(nav)
    buttons.append([ibtn("BACK","adm_s2_menu",emoji="🔙",style="primary"),
                    ibtn("HOME","home",emoji="🏠",style="primary")])
    await send_rich_async(uid, [make_heading(title, 2),
        make_table([["ℹ️ INFO","📋 VALUE"],["📄 Page", f"{page}/{tp}"],["📦 Total", str(total)]]),
        make_table(table)],
        reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
        fallback_text=f"{title} {page}/{tp}",
        edit_query=_edit_query_of(update))

async def view_admin_s2_item(update, phone):
    uid = update.effective_user.id
    if not is_admin(uid): return
    r = cur.execute("SELECT * FROM stock WHERE phone=?", (phone,)).fetchone()
    if not r:
        try: await update.callback_query.answer("Not found", show_alert=True)
        except: pass
        return
    rows = [["ℹ️ INFO","📋 VALUE"],["📱 Phone", str(r["phone"])],
            ["🌎 Country", f"{r['country_icon']} {r['country_name']}"],
            ["🎯 Category", str(r["category"])],["🖥️ Server", str(r["server"])],
            ["💰 Price", f"₹{r['price']}"],["📊 Status", "✅ Available" if r["available"] else "🔴 Sold"],
            ["🔐 2FA", str(r["twofa"])],["📝 Desc", (r["description"] or "—")[:60]]]
    buttons = [
        [ibtn("EDIT PRICE", f"adm_s2_edit|price|{phone}", emoji="💰", style="primary"),
         ibtn("EDIT CAT", f"adm_s2_edit|category|{phone}", emoji="🎯", style="primary")],
        [ibtn("EDIT 2FA", f"adm_s2_edit|twofa|{phone}", emoji="🔐", style="primary"),
         ibtn("EDIT DESC", f"adm_s2_edit|description|{phone}", emoji="📝", style="primary")],
        [ibtn(f"🔁 SET {'SOLD' if r['available'] else 'AVAILABLE'}",
              f"adm_s2_toggle|{phone}", emoji="🔁", style="primary")],
        [ibtn("🗑️ DELETE", f"adm_s2_del_confirm|{phone}", emoji="🗑️", style="danger")],
        [ibtn("BACK","adm_s2_list|1",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading(f"📱 {phone}", 2), make_table(rows)],
                          reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
                          fallback_text=f"📱 {phone}", edit_query=_edit_query_of(update))

async def view_admin_s2_sold(update, page=1):
    uid = update.effective_user.id
    if not is_admin(uid): return
    limit = 15; offset = (page-1) * limit
    total = cur.execute("""SELECT COUNT(*) FROM orders o WHERE
        (o.section='SERVER2' OR o.section IS NULL OR o.section='')""").fetchone()[0]
    rows = cur.execute("""SELECT o.user_id, o.phone, o.otp, o.price, o.date,
        u.first_name, u.last_name FROM orders o LEFT JOIN users u ON u.user_id=o.user_id
        WHERE (o.section='SERVER2' OR o.section IS NULL OR o.section='')
        ORDER BY o.id DESC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
    if total == 0:
        kb = InlineKeyboardMarkup([[ibtn("BACK","adm_s2_menu",emoji="🔙",style="primary")]])
        await send_rich_async(uid, [make_heading("👑 S2 SOLD", 2), make_paragraph("📭 None.")],
                              reply_markup=kb.to_dict(), fallback_text="Empty",
                              edit_query=_edit_query_of(update)); return
    tp = max(1, (total + limit - 1) // limit)
    table = [["👤 USER","📱 PHONE","🔢 OTP","💰","📅"]]
    for r in rows:
        nm = _full_name(r["first_name"] or "—", r["last_name"] or "")[:16]
        ph = str(r["phone"] or "—")[:16]; otp = str(r["otp"] or "—")[:8]
        pr = f"₹{r['price']:.0f}" if r["price"] else "—"
        dt = str(r["date"] or "—")[:10]
        table.append([nm, ph, otp, pr, dt])
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"adm_s2_sold|{page-1}", emoji="🔙", style="primary"))
    if page < tp: nav.append(ibtn("Next", f"adm_s2_sold|{page+1}", emoji="👉", style="primary"))
    kbr = []
    if nav: kbr.append(nav)
    kbr.append([ibtn("BACK","adm_s2_menu",emoji="🔙",style="primary")])
    await send_rich_async(uid, [make_heading("👑 S2 SOLD", 2),
        make_table([["ℹ️ INFO","📋 VALUE"],["📄 Page", f"{page}/{tp}"],["📦 Total", str(total)]]),
        make_table(table)],
        reply_markup=InlineKeyboardMarkup(kbr).to_dict(),
        fallback_text=f"S2 SOLD {page}/{tp}", edit_query=_edit_query_of(update))


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn, server2_kb
from config import (
    API_HASH, API_ID, AUTO_CANCEL_SECONDS, OTP_REGEX, PURCHASE_WARNING_ROWS, STORE_HEADER,
    log
)
from context import cur, current_ctx, db
from database import get_rate, get_user, is_admin, is_buy2_online, safe_get
from devices import send_otp_rich
from emojis import emo
from history import record_balance_history
from logs import _full_name, log_purchase_both
from rich_ui import (
    _edit_query_of, _tg_post, build_deep_link_s2, make_heading, make_paragraph, make_table,
    send_rich_async
)
from state import active_orders, get_user_lock
from utils import generate_unique_order_id
from views import show_maintenance
