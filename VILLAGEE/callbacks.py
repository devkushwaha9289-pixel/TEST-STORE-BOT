#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — callbacks.py
Main inline-button callback router (on_callback).
"""

import re, time
from telegram import InlineKeyboardMarkup

# ============================================================
# CALLBACK HANDLER
# ============================================================
def _late_answer(data):
    """Buttons whose handler may show an alert (must be the FIRST q.answer)."""
    return (data in ("noop", "wa_notify", "verify_join", "osint_show_docs", "dep_upi", "dep_paytm",
                     "dep_manual_upi", "bc_done", "lzt_all_countries", "lzt_refresh")
            or data.startswith(("pkp_", "mkp_", "kp_", "bc_", "adm_", "manup_", "oakp_", "dep_acc|", "dep_rej|")))


async def on_callback(update, context):
    """Wrapper: guarantees the button spinner is always cleared."""
    q = update.callback_query
    data = (q.data or "") if q else ""
    try:
        await _on_callback_impl(update, context)
    finally:
        if q is not None and _late_answer(data):
            try: await q.answer()
            except Exception: pass


async def _on_callback_impl(update, context):
    q = update.callback_query
    data = q.data or ""
    u = update.effective_user; uid = u.id
    ensure_user(uid, u.first_name or "", u.username or "", u.last_name or "")
    if is_banned(uid):
        try: await q.answer()
        except: pass
        return
    now = time.time()
    if uid in user_spam and now - user_spam[uid] < 0.3:
        try: await q.answer()
        except: pass
        return
    user_spam[uid] = now
    if not is_bot_online() and not is_admin(uid):
        try: await q.answer("Maintenance", show_alert=True)
        except: pass
        return
    # Alerts below must be the FIRST answer to a query, so only
    # acknowledge up-front when no alert can follow.
    if not _late_answer(data):
        try: await q.answer()
        except: pass

    # ⭐ FORCE JOIN HARD ENFORCEMENT (v28.0)
    force_join_bypass = (
        data == "verify_join" or
        data == "cancel" or
        data == "home" or
        data.startswith("manup_") or
        data.startswith("oakp_")
    )
    if not force_join_bypass and not is_admin(uid):
        if get_all_channels():
            ok, miss = await check_user_in_channels(uid, use_cache=False)
            if not ok:
                try: await q.answer("⚠️ Join all channels first!", show_alert=True)
                except: pass
                await send_force_join_prompt(uid, miss)
                return

    if data.startswith("manage_devices|"):
        await show_manage_devices(update, data.split("|", 1)[1]); return
    if data.startswith("logout_device|"):
        p = data.split("|")
        if len(p) >= 3:
            await handle_logout_device(update, p[1], p[2])
        return
    if data.startswith("back_to_otp|"):
        await back_to_otp_view(update, data.split("|", 1)[1]); return

    if data == "noop":
        try: await q.answer("⏳ Not available.")
        except: pass
        return
    if data == "wa_notify":
        try: await q.answer("🔔 Notify enabled!", show_alert=True)
        except: pass
        return
    if data == "verify_join":
        _force_join_cache.pop(uid, None)
        is_ok, miss = await check_user_in_channels(uid, use_cache=False)
        if is_ok:
            try:
                await q.message.reply_text(
                    auto_premium(f"✅ <b>Verified!</b>\n👉 Use /start to continue."),
                    parse_mode="HTML", reply_markup=main_reply_kb(uid))
            except: pass
        else:
            try: await q.answer("❌ Not joined yet. Join all channels then tap Verify.", show_alert=True)
            except: pass
            await send_force_join_prompt(uid, miss)
        return

    if data == "home": await view_home(update); return
    if data == "profile": await view_profile(update); return
    if data == "balance": await view_balance(update); return
    if data == "recharge": await view_recharge(update); return
    if data == "refer": await view_refer(update); return
    if data == "support": await view_support(update); return
    if data == "buy1": await view_buy1_lzt(update, 1); return
    if data == "buy2": await view_buy2(update); return
    if data == "buy3": await view_buy3(update); return
    if data == "buywa": await view_buywa(update); return
    if data == "admin_panel":
        if is_admin(uid):
            try:
                await view_admin_panel(update)
            except Exception as e:
                log.exception("admin panel callback failed", exc_info=e)
                try: await q.answer("Admin panel error. Check bot logs.", show_alert=True)
                except: pass
        return
    if data == "admin_payment_methods":
        if is_admin(uid):
            try:
                await view_admin_payment_methods(update)
            except Exception as e:
                log.exception("payment methods callback failed", exc_info=e)
                try: await q.answer("Payment Methods error. Check bot logs.", show_alert=True)
                except: pass
        return
    if data.startswith("stock_pg|"): await view_all_stock(update, int(data.split("|")[1])); return

    if data == "osint_show_docs":
        fid = get_osint_docs_file_id()
        if not fid:
            try: await q.answer("Docs not available. Contact support.", show_alert=True)
            except: pass
            return
        try:
            await _tg_post("sendDocument", {"chat_id": uid, "document": fid,
                "caption": f"{emo('📖')} <b>OSINT API Documentation</b>",
                "parse_mode": "HTML"})
            try: await q.answer("✅ Sent!")
            except: pass
        except Exception as e:
            try: await q.answer(f"Error: {str(e)[:60]}", show_alert=True)
            except: pass
        return

    if data == "send_balance":
        r = get_user(uid)
        temp_data[uid] = {'step': 'balance_transfer_uid'}
        await q.message.reply_text(f"<b>{emo('💳')} SEND BALANCE — 1/2</b>\n\n"
            f"{emo('💰')} Balance: <code>₹{safe_get(r,'balance',0)}</code>\n"
            f"{emo('📤')} Fee: <b>{get_transfer_fee()}%</b>\n\n{emo('👉')} Receiver ID:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return
    if data == "redeem":
        temp_data[uid] = {'admin_action': 'redeem'}
        await q.message.reply_text(f"<b>{emo('🔥')} Redeem</b>\n\n{emo('🎁')} Enter code:",
                                    parse_mode="HTML", reply_markup=redeem_reply_kb())
        return
    if data == "tc_accept":
        cur.execute("UPDATE users SET terms_accepted=1 WHERE user_id=?", (uid,)); db.commit()
        try: await q.message.reply_text("🏠", reply_markup=main_reply_kb(uid))
        except: pass
        await view_home(update); return
    if data == "tc_reject": return
    if data == "cancel":
        clear_user_operations(uid)
        manual_upi_pending.pop(uid, None)
        manual_upi_owner_state.pop(uid, None)
        try: await q.message.reply_text(f"<b>{emo('✅')} Cancelled</b>",
                                          parse_mode="HTML", reply_markup=main_reply_kb(uid))
        except: pass
        return
    if data == "log_add_skip":
        st = temp_data.get(uid)
        if st and st.get('admin_action') == 'log_add_title':
            cid = st.get('log_new_chat_id'); title = f"Target {cid}"
            kind = "group" if str(cid).startswith("-") and not str(cid).startswith("-100") else "channel"
            add_log_target(cid, title, kind); temp_data.pop(uid, None)
            try: await q.message.reply_text(f"{emo('✅')} Added!\n<code>{cid}</code>", parse_mode="HTML")
            except: pass
            await log_target_change(uid, "Added", cid, title)
        return
    if data == "s2_skip_desc":
        st = temp_data.get(uid)
        if st and st.get('admin_action') == 's2_add_desc':
            st['s2_desc'] = ""
            st['admin_action'] = 's2_add_price'
            await q.message.reply_text(
                f"<b>{emo('💰')} ENTER PRICE</b>\n\n"
                f"{emo('📱')} Phone: <code>{st['phone']}</code>\n\n"
                f"{emo('👉')} Send price in ₹:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return
    if data == "s3_skip_desc":
        st = temp_data.get(uid)
        if st and st.get('admin_action') == 's3_add_desc':
            sec = st.get('s3_section', 'PANNELS')
            name = st.get('s3_name', 'Item'); price = st.get('s3_price', 500)
            link = st.get('s3_link', '')
            endpoint = st.get('s3_endpoint', '')
            try:
                cur.execute("""INSERT INTO file_products
                    (section, name, description, price, file_link, api_endpoint, active, item_code)
                    VALUES (?,?,?,?,?,?,1,?)""",
                    (sec, name, "", price, link, endpoint, generate_item_code()))
                db.commit()
                await q.message.reply_text(f"{emo('✅')} Added to {sec}: {name}", parse_mode="HTML")
            except Exception as e:
                await q.message.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
            temp_data.pop(uid, None)
        return
    if data == "addstock_skip_desc":
        st = temp_data.get(uid)
        if st and st.get('admin_action') == 'addstock_desc':
            st['s2_desc'] = ""
            st['admin_action'] = 'addstock_price'
            await q.message.reply_text(
                f"<b>{emo('💰')} ENTER PRICE</b>\n\n"
                f"{emo('📱')} Phone: <code>{st['phone']}</code>\n\n"
                f"{emo('👉')} Send price in ₹:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return
    if data.startswith("bal_hist_"):
        try: page = int(data.split("_")[-1])
        except: page = 1
        await view_balance_history(update, page); return
    if data == "sec_hist_menu":
        await view_section_history_menu(update); return
    if data.startswith("sec_hist|"):
        p = data.split("|"); await view_section_history(update, p[1], int(p[2])); return
    if data.startswith("purch_hist_"):
        try: page = int(data.split("_")[-1])
        except: page = 1
        await view_purchase_history(update, page); return

    if data.startswith("srv2:"):
        await view_server_section(update, "srv2", data.split(":", 1)[1], 1); return
    if data.startswith("srv3:"): await view_server3_section(update, data.split(":", 1)[1]); return
    if data.startswith("srvwa:"): await view_server_section(update, "srvwa", data.split(":", 1)[1], 1); return
    if data.startswith("cnt:"):
        p = data.split(":", 3)
        if len(p) == 4:
            await view_country_items(update, p[1], p[2], p[3], 1)
        return
    if data.startswith("pg_srv|"):
        p = data.split("|"); await view_server_section(update, p[1], p[2], int(p[3])); return
    if data.startswith("pg_cnt|"):
        p = data.split("|"); await view_country_items(update, p[1], p[2], p[3], int(p[4])); return
    if data.startswith("item:"): await view_product_detail(update, data.split(":", 1)[1]); return
    if data == "back_from_detail": await view_buy2(update); return
    if data.startswith("buy_confirm:"): await process_purchase(update, data.split(":", 1)[1]); return
    if data.startswith("fprod_buy:"): await process_file_purchase(update, int(data.split(":")[1])); return
    if data.startswith("fprod:"): await view_file_product(update, int(data.split(":")[1])); return

    if data.startswith("lzt_pg|"):
        try: page = int(data.split("|")[1])
        except: page = 1
        await _render_lzt_country_page(update, uid, page); return
    if data.startswith("lzt_chk|"):
        p = data.split("|"); await view_lzt_country(update, p[1], int(p[2]) if len(p) > 2 else 1); return
    if data.startswith("lzt_view|"):
        p = data.split("|"); await view_lzt_product(update, p[1], p[2] if len(p) > 2 else None); return
    if data.startswith("lzt_buy|"):
        p = data.split("|"); await process_lzt_buy(update, p[1], p[2], p[3]); return
    if data.startswith("lzt_mass_buy|"):
        p = data.split("|"); await process_lzt_mass_buy(update, p[1], p[2], p[3]); return
    if data.startswith("lzt_get_otp|"): await handle_lzt_get_otp(update, data.split("|", 1)[1]); return
    if data == "lzt_all_countries":
        try: await q.answer("Sending...")
        except: pass
        await view_lzt_all_countries(update); return
    if data == "lzt_search_country":
        lzt_search_state[uid] = True
        await q.message.reply_text(f"<b>{emo('🔍')} SEARCH COUNTRY</b>\n\nSend name/code/+91:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","buy1",emoji="🔙",style="primary")]]))
        return
    if data == "lzt_toggle_filters":
        flt = get_user_filters(uid)
        ss = "🟢 NO SPAM" if flt["spam"]=="no" else ("🔴 SPAM" if flt["spam"]=="yes" else "🔵 ANY")
        gs = "🟢 NO GEO" if flt["geoblock"]=="no" else ("🔴 GEO" if flt["geoblock"]=="yes" else "🔵 ANY")
        ms = "🟢 MAIL" if flt["login_mail"]=="yes" else ("🔴 NO MAIL" if flt["login_mail"]=="no" else "🔵 ANY")
        ds = f"🗓️ ≥{_safe_daybreak(flt.get('offline'))}d"
        ps = "🟢 PREM" if flt["premium"]=="yes" else ("🔴 NO PREM" if flt["premium"]=="no" else "🔵 ANY")
        kb = InlineKeyboardMarkup([
            [ibtn(f"Spam: {ss}","lzt_flt|spam",emoji="🚫",style="primary")],
            [ibtn(f"Geo: {gs}","lzt_flt|geoblock",emoji="🌍",style="primary")],
            [ibtn(f"Mail: {ms}","lzt_flt|login_mail",emoji="📧",style="primary")],
            [ibtn(f"Prem: {ps}","lzt_flt|premium",emoji="💎",style="primary")],
            [ibtn(f"Daybreak: {ds}","lzt_flt|offline",emoji="🗓️",style="primary")],
            [ibtn("✅ Apply","buy1",emoji="✅",style="success"),
             ibtn("🔄 Refresh","lzt_refresh",emoji="🔄",style="primary")],
            [ibtn("HOME","home",emoji="🏠",style="primary")]])
        try: await q.edit_message_text("<b>⚙️ Filters</b>", parse_mode="HTML", reply_markup=kb)
        except: pass
        return
    if data.startswith("lzt_flt|"):
        at = data.split("|", 1)[1]
        flt = get_user_filters(uid)
        if at == "spam": flt["spam"] = "yes" if flt["spam"]=="no" else ("any" if flt["spam"]=="yes" else "no")
        elif at == "geoblock": flt["geoblock"] = "yes" if flt["geoblock"]=="no" else ("any" if flt["geoblock"]=="yes" else "no")
        elif at == "login_mail": flt["login_mail"] = "no" if flt["login_mail"]=="yes" else ("any" if flt["login_mail"]=="no" else "yes")
        elif at == "premium": flt["premium"] = "no" if flt["premium"]=="yes" else ("any" if flt["premium"]=="no" else "yes")
        elif at == "offline":
            cv = _safe_daybreak(flt.get("offline"))
            idx = DAYBREAK_OPTIONS.index(cv)
            nx = DAYBREAK_OPTIONS[(idx + 1) % len(DAYBREAK_OPTIONS)]
            flt["offline"] = str(nx); set_user_daybreak(uid, nx)
        active_filter_keys.add(get_filter_key(flt))
        ss = "🟢 NO SPAM" if flt["spam"]=="no" else ("🔴 SPAM" if flt["spam"]=="yes" else "🔵 ANY")
        gs = "🟢 NO GEO" if flt["geoblock"]=="no" else ("🔴 GEO" if flt["geoblock"]=="yes" else "🔵 ANY")
        ms = "🟢 MAIL" if flt["login_mail"]=="yes" else ("🔴 NO MAIL" if flt["login_mail"]=="no" else "🔵 ANY")
        ds = f"🗓️ ≥{_safe_daybreak(flt.get('offline'))}d"
        ps = "🟢 PREM" if flt["premium"]=="yes" else ("🔴 NO PREM" if flt["premium"]=="no" else "🔵 ANY")
        kb = InlineKeyboardMarkup([
            [ibtn(f"Spam: {ss}","lzt_flt|spam",emoji="🚫",style="primary")],
            [ibtn(f"Geo: {gs}","lzt_flt|geoblock",emoji="🌍",style="primary")],
            [ibtn(f"Mail: {ms}","lzt_flt|login_mail",emoji="📧",style="primary")],
            [ibtn(f"Prem: {ps}","lzt_flt|premium",emoji="💎",style="primary")],
            [ibtn(f"Daybreak: {ds}","lzt_flt|offline",emoji="🗓️",style="primary")],
            [ibtn("✅ Apply","buy1",emoji="✅",style="success"),
             ibtn("🔄 Refresh","lzt_refresh",emoji="🔄",style="primary")]])
        try: await q.edit_message_text("<b>⚙️ Filters</b>", parse_mode="HTML", reply_markup=kb)
        except: pass
        return
    if data == "lzt_sort_menu":
        flt = get_user_filters(uid); cur_ = flt.get("sort", "az")
        lb = {"az":"A-Z","price_low":"Price ↑","price_high":"Price ↓",
              "stock_low":"Stock ↑","stock_high":"Stock ↓"}
        def mk(m): return "✅ " if cur_ == m else ""
        kb = InlineKeyboardMarkup([
            [ibtn(f"{mk('az')}A-Z","lzt_sort|az",style="primary")],
            [ibtn(f"{mk('price_low')}Price ↑","lzt_sort|price_low",style="primary")],
            [ibtn(f"{mk('price_high')}Price ↓","lzt_sort|price_high",style="primary")],
            [ibtn(f"{mk('stock_low')}Stock ↑","lzt_sort|stock_low",style="primary")],
            [ibtn(f"{mk('stock_high')}Stock ↓","lzt_sort|stock_high",style="primary")],
            [ibtn("BACK","buy1",emoji="🔙",style="primary")]])
        try: await q.edit_message_text(f"<b>↕️ Sort — {lb.get(cur_,'A-Z')}</b>",
                                        parse_mode="HTML", reply_markup=kb)
        except: pass
        return
    if data.startswith("lzt_sort|"):
        m = data.split("|", 1)[1]
        if m not in ("az","price_low","price_high","stock_low","stock_high"): return
        get_user_filters(uid)["sort"] = m
        await _render_lzt_country_page(update, uid, 1); return
    if data == "lzt_refresh":
        active_filter_keys.add(get_filter_key(get_user_filters(uid)))
        active_lzt_cache_targets.update(list(LZT_COUNTRY_CATALOG.keys())[:20])
        try: await q.answer("Refresh queued")
        except: pass
        await _render_lzt_country_page(update, uid, 1); return

    if data == "dep_upi":
        if get_setting('fampay_status', 'on') != 'on':
            try: await q.answer("FamPay Automatic is disabled.", show_alert=True)
            except: pass
            return
        if not is_upi_online():
            try: await q.answer("UPI disabled.", show_alert=True)
            except: pass
            return
        min_d = get_min_deposit()
        deposit_input[uid] = {'step': 'upi_keypad', 'val': '0'}
        await q.message.reply_text(f"<b>{emo('🔑')} AMOUNT</b>\n\n{emo('💰')} <code>₹0</code>\n\n"
            f"{emo('📉')} Min ₹{min_d}", parse_mode="HTML", reply_markup=keypad_kb("kp_"))
        return

    # ⭐ PAYTM AUTOMATIC — START (keypad)
    if data == "dep_paytm":
        if get_setting('paytm_status', 'on') != 'on':
            try: await q.answer("Paytm Automatic is disabled.", show_alert=True)
            except: pass
            return
        if not is_upi_online():
            try: await q.answer("UPI disabled.", show_alert=True)
            except: pass
            return
        if not get_paytm_mid() or not get_paytm_upi_id():
            try: await q.answer("Paytm is not configured.", show_alert=True)
            except: pass
            return
        min_d = get_min_deposit()
        deposit_input[uid] = {'step': 'paytm_keypad', 'val': '0'}
        await q.message.reply_text(
            f"<b>{emo('💳')} PAYTM AUTOMATIC — AMOUNT</b>\n\n"
            f"{emo('💰')} <code>₹0</code>\n\n"
            f"{emo('📉')} Min ₹{min_d}\n\n"
            "Payment will be checked automatically.",
            parse_mode="HTML", reply_markup=keypad_kb("pkp_"))
        return

    if data.startswith("pkp_"):
        st = deposit_input.get(uid)
        if not st or st.get('step') != 'paytm_keypad':
            return
        a = data.replace("pkp_", "")
        cv = st.get('val', "0")
        if a.isdigit():
            cv = a if cv == "0" else cv + a
            if len(cv) > 7: cv = cv[:7]
        elif a == "del":
            cv = cv[:-1] or "0"
        elif a == "done":
            amt = int(cv); min_d = get_min_deposit()
            if amt < min_d:
                try: await q.answer(f"Min ₹{min_d}", show_alert=True)
                except: pass
                return
            deposit_input.pop(uid, None)
            await show_paytm_qr(q.message.chat_id, uid, amt)
            return
        st['val'] = cv
        try:
            await q.edit_message_text(
                f"<b>{emo('💳')} PAYTM AUTOMATIC — AMOUNT</b>\n\n"
                f"{emo('💰')} <code>₹{cv}</code>\n\n"
                f"{emo('👉')} Tap ✅ to continue.",
                parse_mode="HTML", reply_markup=keypad_kb("pkp_"))
        except: pass
        return

    # ⭐ MANUAL UPI — START (keypad)
    if data == "dep_manual_upi":
        if get_setting('manual_upi_status', 'on') != 'on':
            try: await q.answer("Manual UPI is disabled.", show_alert=True)
            except: pass
            return
        if not is_upi_online():
            try: await q.answer("UPI disabled.", show_alert=True)
            except: pass
            return
        min_d = get_min_deposit()
        deposit_input[uid] = {'step': 'manual_upi_keypad', 'val': '0'}
        await q.message.reply_text(
            f"<b>{emo('📄')} MANUAL UPI — AMOUNT</b>\n\n"
            f"{emo('💰')} <code>₹0</code>\n\n"
            f"{emo('📉')} Min ₹{min_d}\n\n"
            f"Enter amount to pay:",
            parse_mode="HTML", reply_markup=keypad_kb("mkp_"))
        return

    if data.startswith("mkp_"):
        st = deposit_input.get(uid)
        if not st or st.get('step') != 'manual_upi_keypad':
            return
        a = data.replace("mkp_", "")
        cv = st.get('val', "0")
        if a.isdigit():
            cv = a if cv == "0" else cv + a
            if len(cv) > 7: cv = cv[:7]
        elif a == "del":
            cv = cv[:-1] or "0"
        elif a == "done":
            amt = int(cv); min_d = get_min_deposit()
            if amt < min_d:
                try: await q.answer(f"Min ₹{min_d}", show_alert=True)
                except: pass
                return
            deposit_input.pop(uid, None)
            await show_manual_upi_qr(q.message.chat_id, uid, amt)
            return
        st['val'] = cv
        try:
            await q.edit_message_text(
                f"<b>{emo('📄')} MANUAL UPI — AMOUNT</b>\n\n"
                f"{emo('💰')} <code>₹{cv}</code>\n\n"
                f"{emo('👉')} Tap ✅ to continue.",
                parse_mode="HTML", reply_markup=keypad_kb("mkp_"))
        except: pass
        return

    # Auto UPI keypad
    if data.startswith("kp_"):
        a = data.replace("kp_", "")
        cv = deposit_input.get(uid, {}).get('val', "0")
        if a.isdigit():
            cv = a if cv == "0" else cv + a
            if len(cv) > 5: cv = cv[:5]
        elif a == "del": cv = cv[:-1] or "0"
        elif a == "done":
            amt = int(cv); min_d = get_min_deposit()
            if amt < min_d:
                try: await q.answer(f"Min ₹{min_d}", show_alert=True)
                except: pass
                return
            deposit_input.pop(uid, None)
            await show_upi_qr(q.message.chat_id, uid, amt); return
        deposit_input[uid] = {'step': 'upi_keypad', 'val': cv}
        try:
            await q.edit_message_text(f"<b>{emo('🔑')} AMOUNT</b>\n\n{emo('💰')} <code>₹{cv}</code>",
                parse_mode="HTML", reply_markup=keypad_kb("kp_"))
        except: pass
        return
    if data.startswith("check_upi_"): await handle_upi_check(update, context); return
    if data.startswith("check_paytm_"): await handle_paytm_check(update, context); return
    if data.startswith("utr_enter|"): await handle_utr_enter(update, context); return
    if data.startswith("depm_"):
        m = data.replace("depm_", "")
        deposit_input[uid] = {'step': 'wait_amt', 'method': m}
        min_d = get_min_deposit(); rate = get_rate()
        await q.message.reply_text(
            f"<b>{emo('💳')} {m} — Enter Amount</b>\n\n{emo('💰')} INR (₹):\n\n"
            f"{emo('📉')} Min ₹{min_d}\n{emo('💱')} 1 USDT ≈ ₹{rate}\n\n{emo('🔄')} Auto-converts.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return

    if data.startswith("get_otp|"):
        ph = data.split("|")[1]
        if ph not in active_orders: return
        o = active_orders[ph]
        try:
            msgs = await o['client'].get_messages(777000, limit=5)
            code = None
            for m in msgs:
                if m.date.timestamp() > o['start'] - 10 and m.message:
                    mm = re.search(OTP_REGEX, m.message)
                    if mm and "Login detected" not in m.message:
                        code = mm.group(); break
            if code:
                await send_otp_rich(uid, ph, o['country'], o['c_icon'], code, o['twofa'],
                                    edit_query=None, masked=False, title="✅ OTP")
        except: pass
        return
    if data.startswith("logout_bot|"):
        ph = data.split("|")[1]
        if ph in active_orders:
            o = active_orders.pop(ph)
            try: await o['client'].log_out(); await o['client'].disconnect()
            except: pass
            await q.message.reply_text(f"{emo('✅')} Finished.", parse_mode="HTML")
        return

    if (data.startswith("adm_") or data.startswith("dep_acc|") or data.startswith("dep_rej|") or
        data.startswith("bc_") or data.startswith("fp_") or data.startswith("cat_") or
        data.startswith("stock_") or data.startswith("addcat|") or data.startswith("addcat_zip|") or
        data.startswith("log_src_") or data.startswith("tx_page|") or data.startswith("db_set|") or
        data.startswith("gb_") or data.startswith("s2_") or data.startswith("s3_") or
        data.startswith("zip_") or
        data.startswith("manup_") or data.startswith("oakp_") or
        data.startswith("setcat|")):
        await handle_admin_action(update, context); return

    log.warning(f"Unhandled callback: {data}")


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from admin_actions import handle_admin_action
from admin_panel import view_admin_panel, view_admin_payment_methods
from buttons import ibtn, main_reply_kb, redeem_reply_kb
from commands import view_all_stock
from config import DAYBREAK_OPTIONS, OTP_REGEX, log
from context import cur, db
from database import (
    ensure_user, get_min_deposit, get_rate, get_transfer_fee, get_user, get_setting, is_admin, is_banned,
    is_bot_online, is_upi_online, safe_get, get_paytm_mid, get_paytm_upi_id
)
from devices import back_to_otp_view, handle_logout_device, send_otp_rich, show_manage_devices
from emojis import auto_premium, emo
from force_join import (
    _force_join_cache, check_user_in_channels, get_all_channels, send_force_join_prompt
)
from history import view_balance_history, view_section_history, view_section_history_menu
from logs import add_log_target, log_target_change
from lzt_api import (
    LZT_COUNTRY_CATALOG, _safe_daybreak, get_filter_key, get_user_filters, set_user_daybreak
)
from manual_upi import show_manual_upi_qr
from osint import get_osint_docs_file_id
from payments import handle_upi_check, handle_utr_enter, keypad_kb, show_upi_qr
from paytm import handle_paytm_check, show_paytm_qr
from rich_ui import _tg_post
from server1 import (
    _render_lzt_country_page, handle_lzt_get_otp, process_lzt_buy, process_lzt_mass_buy,
    view_buy1_lzt, view_lzt_all_countries, view_lzt_country, view_lzt_product
)
from server2 import (
    process_purchase, view_buy2, view_country_items, view_product_detail,
    view_server_section
)
from server3 import process_file_purchase, view_buy3, view_file_product, view_server3_section
from state import (
    active_filter_keys, active_lzt_cache_targets, active_orders, clear_user_operations,
    deposit_input, lzt_search_state, manual_upi_owner_state, manual_upi_pending, temp_data,
    user_spam
)
from utils import generate_item_code, html_safe_error
from views import (
    view_balance, view_buywa, view_home, view_profile, view_purchase_history, view_recharge,
    view_refer, view_support
)
