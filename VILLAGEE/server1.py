#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — server1.py
SERVER 1 (LZT) — country/product views, buy, mass-buy, get-OTP.
"""

import time, traceback
from html import escape
from telegram import InlineKeyboardMarkup

# ============================================================
# SERVER 1 VIEW
# ============================================================
async def view_buy1_lzt(update, page=1):
    uid = update.effective_user.id
    try:
        if not is_buy1_online() and not is_admin(uid):
            await show_maintenance(uid, "buy1"); return
        if not resolve_lzt_token():
            if is_admin(uid):
                kb = InlineKeyboardMarkup([[ibtn("SET SERVER 1 TOKEN","adm_setlzt_token",emoji="🔑",style="primary")],
                                           [ibtn("MAIN MENU","home",emoji="🏠",style="primary")]])
                await send_rich_async(uid, [make_heading(STORE_HEADER, 2),
                    make_paragraph("Server 1 token is not set.")], reply_markup=kb.to_dict(),
                    edit_query=_edit_query_of(update))
            else:
                await send_rich_async(uid, [make_heading(STORE_HEADER, 2),
                    make_paragraph("Server 1 unavailable.")],
                    reply_markup=InlineKeyboardMarkup([[ibtn("MAIN MENU","home",emoji="🏠",style="primary")]]).to_dict(),
                    edit_query=_edit_query_of(update))
            return
        if not is_server1_online() and not is_admin(uid):
            await show_maintenance(uid, "buy1"); return
        await _render_lzt_country_page(update, uid, page)
    except Exception as e:
        log.error(f"view_buy1_lzt: {e}"); traceback.print_exc()
        try:
            await _tg_post("sendMessage", {"chat_id": uid,
                "text": "⚠️ Couldn't open Server 1. Please try again.", "parse_mode": "HTML",
                "reply_markup": InlineKeyboardMarkup([[ibtn("HOME","home",emoji="🏠",style="primary")]]).to_dict()})
        except: pass

async def _render_lzt_country_page(update, uid, page):
    limit = 20
    flt = get_user_filters(uid); fkey = get_filter_key(flt)
    active_filter_keys.add(fkey)
    sd = cached_lzt_stock.get(fkey, cached_lzt_stock.get(DEFAULT_FILTER_FKEY, {}))
    sc = sorted(LZT_COUNTRY_CATALOG.keys())
    sm = flt.get("sort", "az")
    if sm == "stock_high": sc.sort(key=lambda n: (sd.get(n,(0,0))[0], n), reverse=True)
    elif sm == "stock_low": sc.sort(key=lambda n: (sd.get(n,(0,0))[0], n))
    elif sm == "price_low": sc.sort(key=lambda n: (sd.get(n,(0,0))[1] or 10**9, n))
    elif sm == "price_high": sc.sort(key=lambda n: (sd.get(n,(0,0))[1], n), reverse=True)
    total = len(sc); tp = max(1, (total + limit - 1) // limit)
    page = min(max(1, page), tp)
    off = (page - 1) * limit
    pc = sc[off:off + limit]
    now = time.monotonic(); cts = cached_lzt_stock_at.get(fkey, {})
    active_lzt_cache_targets.update(n for n in pc if n not in sd or now - cts.get(n, 0.0) > STOCK_CACHE_TTL)
    r = get_user(uid); bal = safe_get(r, "balance", 0)
    all_link = f"https://t.me/{current_ctx().username}?start=AllServer1"
    blocks = [make_heading(STORE_HEADER, 2),
              make_table([["ℹ️ INFO","📋 DETAIL"],["💰 Balance", f"₹{bal:.1f}"],
                          ["🖥️ Server", "SERVER 1"],["📄 Page", f"{page}/{tp}"],
                          ["🗓️ Daybreak", daybreak_label(flt['offline'])]])]
    try:
        view_all_block = build_rich_buttons_block([{
            "name": "View All Countries",
            "url": all_link,
            "style": "primary",
            "type": "rich",
            "emoji_id": VIEW_ALL_EMOJI_ID,
            "alternative_emoji": "🌎"
        }], align="center")
        if view_all_block: blocks.append(view_all_block)
    except Exception as e: log.warning(f"view all btn: {e}")
    slb = {"az":"A-Z","stock_high":"Stock ↓","stock_low":"Stock ↑","price_low":"Price ↑","price_high":"Price ↓"}
    buttons = [[ibtn("⚙️ Filters","lzt_toggle_filters",emoji="⚙️",style="primary"),
                ibtn(f"↕️ {slb.get(sm,'A-Z')}","lzt_sort_menu",emoji="🔄",style="primary")]]
    row = []
    for name in pc:
        iso, flag, ccode = LZT_COUNTRY_CATALOG[name]
        ce_ = sd.get(name)
        cnt, mnp = ce_ or (0, 0.0)
        pt = f"₹{int(mnp)}" if cnt else ("…" if ce_ is None else "0")
        label = country_button_label(name, pt)
        row.append(ibtn(label, f"lzt_chk|{iso}|1", raw_flag=flag, style="success"))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    prow = []
    ws = max(1, min(page - 2, tp - 4)); we = min(tp, ws + 4)
    for pg in range(ws, we + 1):
        t = f"[{pg}]" if pg != page else f"·{pg}·"
        prow.append(ibtn(t, f"lzt_pg|{pg}", style="primary"))
    if prow: buttons.append(prow)
    buttons.append([ibtn("⛶ Show All","lzt_all_countries",emoji="📋",style="danger"),
                    ibtn("🔍 Search","lzt_search_country",emoji="🔍",style="primary")])
    buttons.append([ibtn("MAIN MENU","home",emoji="🏠",style="primary")])
    fb = f"SERVER 1 — Page {page}/{tp} — ₹{bal:.0f} — Daybreak {daybreak_label(flt['offline'])}"
    await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
                          fallback_text=fb, edit_query=_edit_query_of(update))

async def view_lzt_country(update, iso_code, page=1):
    uid = update.effective_user.id
    try:
        wait = resolve_lzt_user_refresh(uid, f"stock:{iso_code}:{page}")
        if wait > 0:
            try: await update.callback_query.answer(f"Wait {int(wait)+1}s", show_alert=True)
            except: pass
            return
        country = next((k for k, v in LZT_COUNTRY_CATALOG.items() if v[0] == iso_code), "United States")
        flag = LZT_COUNTRY_CATALOG.get(country, ("US","🇺🇸","1"))[1]
        flt = get_user_filters(uid)
        dbv = _safe_daybreak(flt.get("offline", DEFAULT_DAYBREAK))
        params = {"country[]":iso_code,"spam":flt["spam"] if flt["spam"] != "any" else None,
                  "nsb":1,"pmin":0.01,"pmax":1000,"page":page,"per_page":40,
                  "password":"no","currency":LZT_PRICE_CURRENCY}
        if flt["premium"] != "any": params["premium"] = flt["premium"]
        res = await fetch_lzt_stock_response(params, timeout_total=LZT_STOCK_TIMEOUT, max_retries=LZT_STOCK_RETRIES)
        if lzt_is_rate_limited_response(res):
            try:
                await update.callback_query.edit_message_text(lzt_rate_limited_message(res), parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [ibtn("Try Later", f"lzt_chk|{iso_code}|1", emoji="🔄", style="primary")],
                        [ibtn("Change Country","buy1",emoji="🔙",style="danger")]]))
            except: pass
            return
        if isinstance(res, dict) and 'items' in res and not res['items'] and params["country[]"] != country:
            params["country[]"] = country
            res = await fetch_lzt_stock_response(params, timeout_total=LZT_STOCK_TIMEOUT, max_retries=1)
        if not res or 'items' not in res or not res['items']:
            kb = InlineKeyboardMarkup([[ibtn("🔄 Refresh", f"lzt_chk|{iso_code}|1", emoji="🔄", style="success")],
                                        [ibtn("Change","buy1",emoji="🔙",style="danger")]])
            try:
                await update.callback_query.edit_message_text(f"{emo('❌')} <b>Stock Empty</b> for <b>{country} {flag}</b>.",
                    parse_mode="HTML", reply_markup=kb)
            except: pass
            return
        matched = filter_lzt_items(res.get('items', []), flt)
        if not matched:
            kb = InlineKeyboardMarkup([[ibtn("⚙️ Filters","lzt_toggle_filters",emoji="⚙️",style="primary")],
                                        [ibtn("🔄 Refresh", f"lzt_chk|{iso_code}|1", emoji="🔄", style="success")],
                                        [ibtn("Change","buy1",emoji="🔙",style="danger")]])
            try:
                await update.callback_query.edit_message_text(f"{emo('❌')} No eligible listings.", parse_mode="HTML", reply_markup=kb)
            except: pass
            return
        items = sorted(matched, key=lambda x: float(x.get('price_with_fee') or x.get('price') or 99999))[:40]
        ti = len(matched); tp = max(1, (ti + 39) // 40)
        markup = get_lzt_markup(country)
        sp = lzt_final_inr_price(items[0], markup) if items else 0
        buttons = [[ibtn("⚙️ Filters","lzt_toggle_filters",emoji="⚙️",style="primary")]]
        gr = []
        sh_m = (flt.get("login_mail") == "any"); sh_p = (flt.get("premium") == "any"); sh_s = (flt.get("spam") == "any")
        for idx, item in enumerate(items, 1):
            fp = lzt_final_inr_price(item, markup)
            gi = (page - 1) * 40 + idx
            iid = int(item.get('item_id') or item.get('id'))
            bd = ""
            if sh_m and lzt_item_has_mail(item): bd += "📧"
            if sh_p and lzt_item_has_premium(item): bd += "💎"
            if sh_s and lzt_item_has_spam(item): bd += "🚫"
            bt = f" {bd}" if bd else ""
            gr.append(ibtn(f"✅{bt} #{gi} • ₹{fp}", f"lzt_view|{iid}|{country}|{fp}", raw_flag=flag, style="success"))
            if len(gr) == 2: buttons.append(gr); gr = []
        if gr: buttons.append(gr)
        nav = []
        if page > 1: nav.append(ibtn("⬅️", f"lzt_chk|{iso_code}|{page-1}", emoji="🔙", style="primary"))
        if ti > (page * 40): nav.append(ibtn("➡️", f"lzt_chk|{iso_code}|{page+1}", emoji="👉", style="primary"))
        if nav: buttons.append(nav)
        buttons.append([ibtn("Change","buy1",emoji="🔙",style="danger"),
                        ibtn("HOME","home",emoji="🏠",style="primary")])
        fb = f"<b>{country} {flag}</b> — {ti} accounts | Page {page}/{tp} | From ₹{sp}"
        try:
            await update.callback_query.edit_message_text(fb, parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        except:
            await send_rich_async(uid, [make_heading(STORE_HEADER, 2), make_paragraph(fb)],
                                  reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
                                  fallback_text=fb, edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_lzt_country: {e}"); traceback.print_exc()

async def view_lzt_product(update, item_id, country=None):
    uid = update.effective_user.id
    try:
        res = await lzt_request('GET', f"/{item_id}", params={"currency": LZT_PRICE_CURRENCY})
        if not res or 'item' not in res:
            try: await update.callback_query.answer("Unable to load.", show_alert=True)
            except: pass
            return
        item = res['item']
        country = country or lzt_item_country_name(item, "Unknown")
        info = lzt_price_breakdown(item, get_lzt_markup(country)); fp = info["final_inr"]
        hs = lzt_item_has_spam(item); hp = lzt_item_has_premium(item)
        hm = lzt_item_has_mail(item); hg = lzt_item_has_geoblock(item)
        chats = item.get("telegram_chats_count", 0); channels = item.get("telegram_channels_count", 0)
        contacts = item.get("telegram_contacts_count", 0)
        r = get_user(uid); bal = safe_get(r, "balance", 0); diff = fp - bal
        pwd = lzt_item_requires_password(item)
        eligible, age = lzt_item_is_eligible(item, get_user_filters(uid).get("offline", "any"))
        iso = LZT_COUNTRY_CATALOG.get(country, ("US","🇺🇸","1"))[0]
        buttons = []
        if pwd: buttons.append([ibtn("🔐 Password Account","noop",style="danger")])
        elif diff > 0: buttons.append([ibtn("Recharge","recharge",emoji="💳",style="success")])
        else:
            buttons.append([ibtn("✅ Purchase", f"lzt_buy|{item_id}|{fp}|{country}", emoji="✅", style="success")])
            buttons.append([ibtn("🛒 Mass Buy", f"lzt_mass_buy|{item_id}|{fp}|{country}", emoji="🛒", style="primary")])
        buttons.append([ibtn("Back", f"lzt_chk|{iso}|1", emoji="🔙", style="primary")])
        buttons.append([ibtn("HOME","home",emoji="🏠",style="primary")])
        info_rows = [["ℹ️ INFO","📋 DETAIL"],["💰 Price", f"₹{fp}"],["💳 Balance", f"₹{bal}"],
                     ["🌎 Country", str(country)],["🆔 Item ID", str(item_id)],
                     ["⏱️ Age", (f"{age/86400:.1f}d ({int(age)}s)" if age else "—")],
                     ["🚫 Spam", "YES" if hs else "NO"],["💎 Premium", "YES" if hp else "NO"],
                     ["📧 Mail", "YES" if hm else "NO"],["🌍 Geo", "YES" if hg else "NO"],
                     ["💬 Chats", str(chats)],["📣 Channels", str(channels)],["👥 Contacts", str(contacts)]]
        info_rows.extend(PURCHASE_WARNING_ROWS)
        blocks = [
            make_heading(STORE_HEADER, 2),
            make_heading(f"📱 TELEGRAM ACCOUNT — {country}", 3),
            make_table(info_rows),
        ]
        fb = f"{country} | ₹{fp} | Balance ₹{bal} | {item_id}"
        await send_rich_async(uid, blocks,
            reply_markup=InlineKeyboardMarkup(buttons).to_dict(),
            fallback_text=fb, edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_lzt_product: {e}"); traceback.print_exc()

async def _show_status_rich(uid, text_line, edit_query=None, reply_markup=None):
    try:
        await send_rich_async(uid, [make_paragraph(text_line)], reply_markup=reply_markup,
                              fallback_text=text_line, edit_query=edit_query, show_placeholder=False)
    except:
        try:
            if edit_query:
                await _tg_post("editMessageText", {
                    "chat_id": uid, "message_id": edit_query.message.message_id,
                    "text": text_line, "parse_mode": "HTML"})
        except: pass

async def process_lzt_buy(update, item_id, price_str, country):
    uid = update.effective_user.id; q = update.callback_query
    if uid in user_lzt_purchases:
        try: await q.answer("Wait...", show_alert=True)
        except: pass
        return
    user_lzt_purchases[uid] = time.time()
    iso = LZT_COUNTRY_CATALOG.get(country, ("US","",""))[0]
    try:
        lr = await lzt_request('GET', f"/{item_id}", params={"currency": LZT_PRICE_CURRENCY})
        li = lr.get('item') if isinstance(lr, dict) else None
        mp = lzt_market_price(li)
        if not li or mp is None:
            try: await q.answer("Unable to load price.", show_alert=True)
            except: pass
            return
        if lzt_item_requires_password(li):
            try: await q.answer("Password account.", show_alert=True)
            except: pass
            return
        fp = lzt_final_inr_price(li, get_lzt_markup(country))
        async with get_user_lock(uid):
            r = get_user(uid); bal = safe_get(r, "balance", 0)
            if bal < fp:
                try: await q.answer(f"Need ₹{fp}", show_alert=True)
                except: pass
                return
            cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (fp, uid, fp))
            if cur.rowcount == 0: return
            db.commit()
            record_balance_history(uid, -fp, "purchase", "server1", f"SERVER 1 {item_id}", bal, bal - fp)
        await _show_status_rich(uid, f"{emo('⏳')} <b>Purchasing...</b>", edit_query=q)

        br = await lzt_fast_buy_item(item_id, mp)
        if lzt_purchase_has_error(br):
            async with get_user_lock(uid):
                r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
                old = r2["balance"] if r2 else 0
                cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (fp, uid)); db.commit()
                record_balance_history(uid, fp, "refund", "server1", "Failed refund", old, old + fp)
            err_text = lzt_error_text(br) or "Purchase failed."
            kb = InlineKeyboardMarkup([[ibtn("Back", f"lzt_chk|{iso}|1", emoji="🔙", style="primary")],
                                       [ibtn("HOME","home",emoji="🏠",style="primary")]])
            low = str(err_text).lower()
            if "password" in low:
                msg = f"{emo('⚠️')} <b>Purchase skipped and refunded.</b>\nThis Server 1 listing requires a seller login password."
            elif "balance" in low or "средств" in low or "not enough" in low:
                msg = f"{emo('⚠️')} <b>Server 1 Maintenance.</b>\nServer 1 reported insufficient API balance. Your ₹{fp} was refunded."
            elif "timeout" in low:
                msg = f"{emo('⚠️')} <b>Server 1 is slow right now.</b>\nYour ₹{fp} was refunded. Please retry shortly."
            else:
                msg = f"{emo('❌')} <b>Purchase Failed.</b>\nYour ₹{fp} was refunded."
            await _show_status_rich(uid, msg, edit_query=q, reply_markup=kb.to_dict())
            return
        pid = lzt_purchase_item_id(br, item_id)

        await _show_status_rich(uid, f"{emo('⏳')} <b>Resetting account authorizations...</b>", edit_query=q)
        ok_reset, reset_err = await try_lzt_reset_authorizations(pid)

        phone_num = f"LZT_{pid}"
        try:
            res2 = await lzt_request('GET', f"/{pid}", params={"currency": LZT_PRICE_CURRENCY})
            if res2 and 'item' in res2:
                it = res2['item']
                phone_num = it.get('phone') or it.get('telegram_phone') or phone_num
        except: phone_num = f"LZT_{pid}"
        dp = normalize_lzt_phone(phone_num, pid)

        cur.execute("""INSERT INTO orders (user_id, country, year, price, phone, otp, section)
                    VALUES (?,?,?,?,?,?,?)""", (uid, country, 2024, fp, dp, None, "SERVER1"))
        db.commit()
        r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        await log_purchase_both(uid, f"S1{pid}", country, fp, dp, "N/A", "None",
                                r2["balance"] if r2 else 0, status="Completed", is_file=False,
                                deep_link=build_deep_link_s1("Telegram", country))

        active_orders[f"LZT_{pid}"] = {
            'uid': uid, 'client': None, 'sess': None,
            'start': time.time(), 'paid': True, 'price': fp,
            'country': country, 'year': 2024,
            'c_icon': LZT_COUNTRY_CATALOG.get(country, ("", "🌍", ""))[1],
            'twofa': 'None', 'msg_id': None, 'chat_id': uid,
            'order_id': f"S1{pid}", 'category': 'Telegram', 'server': 'SERVER1',
            'phone_num': dp,
        }

        if ok_reset:
            reset_line = "✅ Authorizations reset — other sessions kicked out."
        else:
            reset_line = f"⚠️ Reset auth failed: {escape(str(reset_err)[:80])}"
        msg = (f"{emo('✅')} <b>Purchased!</b>\n\n"
               f"📱 <code>{dp}</code>\n🌎 {country}\n🆔 <code>{pid}</code>\n\n"
               f"{reset_line}")
        kb = InlineKeyboardMarkup([
            [ibtn("🔄 Get OTP", f"lzt_get_otp|LZT_{pid}", emoji="🔄", style="success")],
            [ibtn("Back", f"lzt_chk|{iso}|1", emoji="🔙", style="primary"),
             ibtn("HOME","home",emoji="🏠",style="primary")]])
        await _show_status_rich(uid, msg, edit_query=q, reply_markup=kb.to_dict())
    finally:
        user_lzt_purchases.pop(uid, None)

async def process_lzt_mass_buy(update, first_item_id, price_str, country):
    uid = update.effective_user.id; q = update.callback_query
    if uid in user_lzt_purchases:
        try: await q.answer("Wait...", show_alert=True)
        except: pass
        return
    user_lzt_purchases[uid] = time.time()
    target = int(float(price_str))
    iso = LZT_COUNTRY_CATALOG.get(country, ("US","",""))[0]
    reserved = False; tried = 0; skipped = 0; last_err = "No candidates."
    try:
        async with get_user_lock(uid):
            r = get_user(uid); bal = safe_get(r, "balance", 0)
            if bal < target:
                try: await q.answer(f"Need ₹{target}", show_alert=True)
                except: pass
                return
            cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (target, uid, target))
            if cur.rowcount == 0: return
            db.commit(); reserved = True
            record_balance_history(uid, -target, "mass_buy_reserve", "server1", f"₹{target}", bal, bal - target)
        await _show_status_rich(uid, f"{emo('⏳')} <b>Mass Buy...</b>", edit_query=q)
        pb = {"country[]":iso,"nsb":1,"pmin":0.01,"pmax":1000,"per_page":40,
              "password":"no","currency":LZT_PRICE_CURRENCY}
        cands = []; seen = set()
        user_flt = get_user_filters(uid)
        for p in range(1, 4):
            res = await fetch_lzt_stock_response(dict(pb, page=p),
                                                  timeout_total=LZT_STOCK_TIMEOUT, max_retries=LZT_STOCK_RETRIES)
            for item in (res or {}).get('items', [])[:40]:
                cid = str(item.get('item_id') or item.get('id') or '')
                if not cid or cid in seen: continue
                seen.add(cid)
                if lzt_final_inr_price(item, get_lzt_markup(country)) == target \
                        and lzt_item_matches_filters(item, user_flt):
                    cands.append(item)
        for item in cands:
            cid = str(item.get('item_id') or item.get('id') or '')
            lr = await lzt_request('GET', f"/{cid}", params={"currency": LZT_PRICE_CURRENCY})
            li = lr.get('item') if isinstance(lr, dict) else item
            if not li or lzt_item_requires_password(li): skipped += 1; continue
            cp = lzt_final_inr_price(li, get_lzt_markup(country))
            if cp != target: skipped += 1; continue
            mp = lzt_market_price(li)
            if mp is None: skipped += 1; continue
            tried += 1
            br = await lzt_fast_buy_item(cid, mp)
            if br and not lzt_purchase_has_error(br):
                pid = lzt_purchase_item_id(br, cid)

                await _show_status_rich(uid, f"{emo('⏳')} <b>Resetting authorizations...</b>", edit_query=q)
                ok_reset, reset_err = await try_lzt_reset_authorizations(pid)

                pn = f"LZT_{pid}"
                try:
                    res2 = await lzt_request('GET', f"/{pid}", params={"currency": LZT_PRICE_CURRENCY})
                    if res2 and 'item' in res2:
                        it = res2['item']
                        pn = it.get('phone') or it.get('telegram_phone') or pn
                except: pn = f"LZT_{pid}"
                dp = normalize_lzt_phone(pn, pid)
                cur.execute("""INSERT INTO orders (user_id, country, year, price, phone, otp, section)
                            VALUES (?,?,?,?,?,?,?)""", (uid, country, 2024, target, dp, None, "SERVER1"))
                db.commit()
                r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
                await log_purchase_both(uid, f"S1{pid}", country, target, dp, "N/A", "None",
                                        r2["balance"] if r2 else 0, status="Completed", is_file=False,
                                        deep_link=build_deep_link_s1("Telegram", country))
                active_orders[f"LZT_{pid}"] = {
                    'uid': uid, 'client': None, 'sess': None,
                    'start': time.time(), 'paid': True, 'price': target,
                    'country': country, 'year': 2024,
                    'c_icon': LZT_COUNTRY_CATALOG.get(country, ("", "🌍", ""))[1],
                    'twofa': 'None', 'msg_id': None, 'chat_id': uid,
                    'order_id': f"S1{pid}", 'category': 'Telegram', 'server': 'SERVER1',
                    'phone_num': dp,
                }
                reserved = False
                reset_line = ("✅ Authorizations reset — other sessions kicked out."
                              if ok_reset else
                              f"⚠️ Reset auth failed: {escape(str(reset_err)[:80])}")
                msg = (f"{emo('✅')} <b>Mass Buy OK!</b>\n\n"
                       f"📱 <code>{dp}</code>\n🌎 {country}\n🆔 <code>{pid}</code>\n\n"
                       f"{reset_line}")
                kb = InlineKeyboardMarkup([
                    [ibtn("🔄 Get OTP", f"lzt_get_otp|LZT_{pid}", emoji="🔄", style="success")],
                    [ibtn("Back", f"lzt_chk|{iso}|1", emoji="🔙", style="primary"),
                     ibtn("HOME","home",emoji="🏠",style="primary")]])
                await _show_status_rich(uid, msg, edit_query=q, reply_markup=kb.to_dict())
                return
            last_err = lzt_error_text(br) or "Purchase failed."
        if reserved:
            async with get_user_lock(uid):
                r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
                old = r2["balance"] if r2 else 0
                cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (target, uid)); db.commit()
                record_balance_history(uid, target, "mass_buy_refund", "server1", "Refund", old, old + target)
            reserved = False
        kb = InlineKeyboardMarkup([[ibtn("Back", f"lzt_chk|{iso}|1", emoji="🔙", style="primary")]])
        await _show_status_rich(uid,
            f"{emo('❌')} Mass Buy Failed. Tried: {tried} | Skipped: {skipped}\nRefunded ₹{target}.",
            edit_query=q, reply_markup=kb.to_dict())
    finally:
        if reserved:
            async with get_user_lock(uid):
                r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
                old = r2["balance"] if r2 else 0
                cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (target, uid)); db.commit()
                record_balance_history(uid, target, "mass_buy_refund", "server1", "Refund", old, old + target)
        user_lzt_purchases.pop(uid, None)

async def handle_lzt_get_otp(update, phone):
    uid = update.effective_user.id; q = update.callback_query
    if phone not in active_orders:
        try: await q.answer("Session expired.", show_alert=True)
        except: pass
        return
    order = active_orders[phone]
    iid = phone.split("_")[1]
    country = order.get('country', 'Unknown')
    try: await q.answer("Fetching...")
    except: pass
    code, _, _ = await get_verified_lzt_otp(iid, attempts=3, delay=1.5)
    dp = order.get('phone_num') or normalize_lzt_phone(None, iid)
    ci = order.get('c_icon', '🌍')
    if code:
        async with get_user_lock(uid):
            cur.execute("UPDATE orders SET otp=? WHERE phone=? AND user_id=?", (code, dp, uid)); db.commit()
        await send_otp_rich(uid, dp, country, ci, code, order.get('twofa', 'None'),
                            edit_query=q, masked=False, title="✅ LATEST OTP")
    else:
        try: await q.answer("OTP not available yet. Wait a moment and retry.", show_alert=True)
        except: pass

async def view_lzt_all_countries(update):
    uid = update.effective_user.id
    fkey = get_filter_key(get_user_filters(uid))
    sd = cached_lzt_stock.get(fkey, cached_lzt_stock.get(DEFAULT_FILTER_FKEY, {}))
    bu = current_ctx().username
    rows = []
    for name, (iso, flag, ccode) in LZT_COUNTRY_CATALOG.items():
        cnt, mp = sd.get(name, (0, 0.0))
        rows.append((cnt, name, iso, flag, ccode, mp, country_slug(name)))
    rows.sort(key=lambda i: (-i[0], i[1]))
    lines = ["<b>All Server 1 countries</b>"]
    for cnt, name, iso, flag, ccode, mp, slug in rows:
        lbl = f"{flag} +{ccode} {get_country_button_code(name)} ({iso}) ₹{int(mp)} → {cnt}"
        lines.append(f'<a href="https://t.me/{bu}?start=server1-{slug}">{escape(lbl)}</a>')
    chunks = []; cur_ = []
    for l in lines:
        p = "\n".join(cur_ + [l])
        if len(p) > 3500 and cur_:
            chunks.append("\n".join(cur_)); cur_ = [l]
        else: cur_.append(l)
    if cur_: chunks.append("\n".join(cur_))
    for i, ch in enumerate(chunks, 1):
        text = f"<b>Server 1 countries P{i}/{len(chunks)}</b>\n<blockquote expandable>{ch}</blockquote>"
        try:
            await _tg_post("sendMessage", {"chat_id": uid, "text": text, "parse_mode": "HTML",
                                            "disable_web_page_preview": True})
        except: pass


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn
from config import (
    DEFAULT_DAYBREAK, daybreak_label, LZT_PRICE_CURRENCY, LZT_STOCK_RETRIES, LZT_STOCK_TIMEOUT,
    PURCHASE_WARNING_ROWS, STOCK_CACHE_TTL, STORE_HEADER, log
)
from context import cur, current_ctx, db
from database import get_user, is_admin, is_buy1_online, is_server1_online, safe_get
from devices import send_otp_rich
from emojis import VIEW_ALL_EMOJI_ID, emo
from history import record_balance_history
from logs import log_purchase_both
from lzt_api import (
    LZT_COUNTRY_CATALOG, _safe_daybreak, country_button_label, country_slug,
    fetch_lzt_stock_response, filter_lzt_eligible, filter_lzt_items,
    get_country_button_code, get_filter_key, get_lzt_markup, get_user_filters,
    get_verified_lzt_otp, lzt_error_text, lzt_fast_buy_item, lzt_final_inr_price,
    lzt_is_rate_limited_response, lzt_item_country_name, lzt_item_has_geoblock,
    lzt_item_has_mail, lzt_item_has_premium, lzt_item_has_spam, lzt_item_is_eligible, lzt_item_matches_filters,
    lzt_item_requires_password, lzt_market_price, lzt_price_breakdown,
    lzt_purchase_has_error, lzt_purchase_item_id, lzt_rate_limited_message, lzt_request,
    normalize_lzt_phone, resolve_lzt_token, resolve_lzt_user_refresh,
    try_lzt_reset_authorizations
)
from rich_ui import (
    _edit_query_of, _tg_post, build_deep_link_s1, build_rich_buttons_block, make_heading,
    make_paragraph, make_table, send_rich_async
)
from state import (
    DEFAULT_FILTER_FKEY, active_filter_keys, active_lzt_cache_targets, active_orders,
    cached_lzt_stock, cached_lzt_stock_at, get_user_lock, user_lzt_purchases
)
from views import show_maintenance
