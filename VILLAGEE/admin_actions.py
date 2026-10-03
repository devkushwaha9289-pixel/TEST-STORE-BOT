#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — admin_actions.py
Admin callback-action handler (handle_admin_action).
"""

import json, time, asyncio, io, imaplib
from html import escape
from telegram import InlineKeyboardMarkup, InputFile

# ============================================================
# ADMIN ACTION HANDLER
# ============================================================
async def handle_admin_action(update, context):
    q = update.callback_query; data = q.data; uid = update.effective_user.id
    if not is_admin(uid): return

    # ---------- MANUAL UPI OWNER ACTIONS ----------
    if data.startswith("manup_approve|"):
        oid = data.split("|", 1)[1]
        try:
            row = cur.execute("""SELECT user_id, amount, status FROM manual_upi_orders
                WHERE order_id=?""", (oid,)).fetchone()
        except: row = None
        if not row:
            try: await q.answer("Not found.", show_alert=True)
            except: pass
            return
        if row["status"] == "approved":
            try: await q.answer("Already approved.", show_alert=True)
            except: pass
            return
        tu = row["user_id"]; amt = int(row["amount"])
        await complete_manual_upi_order(oid, tu, amt)
        try:
            await q.answer("✅ Approved!", show_alert=True)
        except: pass
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except: pass
        try:
            await log_admin_action(uid, "Manual UPI Approve", f"order={oid} amount={amt}")
        except: pass
        return

    if data.startswith("manup_reject|"):
        oid = data.split("|", 1)[1]
        manual_upi_owner_state[uid] = {'order_id': oid, 'action': 'reject_reason'}
        await q.message.reply_text(
            f"<b>{emo('❌')} Rejection Reason (optional)</b>\n\n"
            f"Send reason as text, or tap SKIP for no reason:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [ibtn("SKIP REASON", f"manup_reason_skip|{oid}", emoji="➖", style="primary")],
                [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return

    if data.startswith("manup_reason_skip|"):
        oid = data.split("|", 1)[1]
        manual_upi_owner_state.pop(uid, None)
        await reject_manual_upi_order(oid, uid, "")
        try: await q.answer("❌ Rejected (no reason)")
        except: pass
        return

    if data.startswith("manup_amount|"):
        oid = data.split("|", 1)[1]
        manual_upi_owner_state[uid] = {'order_id': oid, 'action': 'change_amount', 'val': '0'}
        await q.message.reply_text(
            f"<b>{emo('💰')} CHANGE AMOUNT</b>\n\n"
            f"Enter new amount in ₹:\n\n"
            f"<code>₹0</code>",
            parse_mode="HTML",
            reply_markup=keypad_kb("oakp_"))
        return

    # Owner change amount keypad
    if data.startswith("oakp_"):
        st = manual_upi_owner_state.get(uid)
        if not st or st.get('action') != 'change_amount':
            return
        a = data.replace("oakp_", "")
        cv = st.get('val', "0")
        if a.isdigit():
            cv = a if cv == "0" else cv + a
            if len(cv) > 7: cv = cv[:7]
        elif a == "del":
            cv = cv[:-1] or "0"
        elif a == "done":
            new_amt = int(cv)
            if new_amt < 1:
                try: await q.answer("Invalid amount.", show_alert=True)
                except: pass
                return
            oid = st.get('order_id')
            manual_upi_owner_state.pop(uid, None)
            try:
                cur.execute("UPDATE manual_upi_orders SET amount=? WHERE order_id=?", (new_amt, oid))
                cur.execute("UPDATE upi_orders SET amount=? WHERE order_id=?", (new_amt, oid))
                db.commit()
            except: pass
            try: await q.answer(f"✅ Amount → ₹{new_amt}", show_alert=True)
            except: pass
            # Re-send same request with updated amount + same buttons
            await reshow_manual_upi_request(oid)
            return
        st['val'] = cv
        try:
            await q.edit_message_text(
                f"<b>{emo('💰')} CHANGE AMOUNT</b>\n\n"
                f"Enter new amount in ₹:\n\n"
                f"<code>₹{cv}</code>",
                parse_mode="HTML",
                reply_markup=keypad_kb("oakp_"))
        except: pass
        return

    # ---------- ADMIN SET MANUAL UPI ID ----------
    if data == "adm_manual_upi_set":
        temp_data[uid] = {'admin_action': 'manual_upi_set'}
        await q.message.reply_text(
            f"{emo('📄')} Send new MANUAL UPI ID:\n\n"
            f"Current: <code>{escape(get_manual_upi_id())}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return

    # ---------- MASTER FULL BACKUP / RESTORE ----------
    if data == "adm_full_backup":
        if not is_master_owner(uid):
            try: await q.answer("Master only!", show_alert=True)
            except: pass
            return
        try: await q.answer("💾 Building full backup...")
        except: pass
        msg = await q.message.reply_text(
            auto_premium(f"⏳ <b>Creating FULL BACKUP (all bots + DBs + sessions)...</b>\n"
                         f"This may take a few seconds."),
            parse_mode="HTML")
        try:
            zip_bytes = await asyncio.to_thread(create_full_backup_zip)
            fname = f"full_backup_{int(time.time())}.zip"
            bio = io.BytesIO(zip_bytes); bio.name = fname
            cap_txt = (
                f"✅ <b>FULL BACKUP</b>\n\n"
                f"📁 <code>{escape(fname)}</code>\n"
                f"💾 {len(zip_bytes)/1024:.1f} KB\n"
                f"🤖 Bots: {len(BOT_CONTEXTS)}\n"
                f"📦 Includes: config, all DBs, bot sessions, user sessions"
            )
            await context.bot.send_document(
                chat_id=uid, document=InputFile(bio, filename=fname),
                caption=auto_premium(cap_txt),
                parse_mode="HTML")
            try: await msg.delete()
            except: pass
            try: await log_admin_action(uid, "Full Backup", f"Size={len(zip_bytes)} bots={len(BOT_CONTEXTS)}")
            except: pass
        except Exception as e:
            log.error(f"full backup: {e}")
            try:
                await msg.edit_text(auto_premium(f"❌ <b>Backup failed</b>\n\n<code>{html_safe_error(e)}</code>"),
                                    parse_mode="HTML")
            except: pass
        return

    if data == "adm_full_restore":
        if not is_master_owner(uid):
            try: await q.answer("Master only!", show_alert=True)
            except: pass
            return
        temp_data[uid] = {'admin_action': 'full_restore_wait'}
        await q.message.reply_text(
            auto_premium(
                f"📥 <b>FULL RESTORE</b>\n\n"
                f"Send the full_backup ZIP file.\n\n"
                f"⚠️ This will OVERWRITE all bot DBs, sessions and config.\n"
                f"🔄 Bot DBs will be reopened automatically.\n"
                f"👉 Make sure you have a fresh backup before restoring!"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return

    # ---------- OSINT settings callbacks ----------
    if data == "adm_osint_settings":
        await view_admin_osint_settings(update); return
    if data == "adm_osint_set_oid":
        temp_data[uid] = {'admin_action': 'osint_set_oid'}
        await q.message.reply_text(f"{emo('👤')} Send OSINT owner ID:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_osint_set_skey":
        temp_data[uid] = {'admin_action': 'osint_set_skey'}
        await q.message.reply_text(f"{emo('🔑')} Send OSINT secret key:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_osint_set_url":
        temp_data[uid] = {'admin_action': 'osint_set_url'}
        await q.message.reply_text(
            f"{emo('🌐')} Send base URL\n\nCurrent: <code>{escape(get_osint_base_url())}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_osint_upload_docs":
        temp_data[uid] = {'admin_action': 'osint_upload_docs'}
        await q.message.reply_text(
            f"{emo('📤')} Send the OSINT docs file (any document).\n"
            f"Old file will be replaced.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_osint_view_docs":
        fid = get_osint_docs_file_id()
        if not fid:
            try: await q.answer("No docs uploaded", show_alert=True)
            except: pass
            return
        try:
            await _tg_post("sendDocument", {"chat_id": uid, "document": fid,
                "caption": f"{emo('📖')} Current OSINT docs file"})
        except Exception as e:
            try: await q.answer(f"Error: {str(e)[:60]}", show_alert=True)
            except: pass
        return
    if data == "adm_osint_del_docs":
        set_setting('osint_docs_file_id', '')
        try: await q.answer("✅ Docs cleared", show_alert=True)
        except: pass
        await view_admin_osint_settings(update); return
    if data == "adm_osint_test":
        try: await q.answer("Testing...")
        except: pass
        token, err = await osint_admin_login(force=True)
        if token:
            await q.message.reply_text(
                f"{emo('✅')} <b>Login OK!</b>\n🔑 Token: <code>{escape(token[:40])}...</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_osint_settings",emoji="🔙",style="primary")]]))
        else:
            await q.message.reply_text(
                f"{emo('❌')} <b>Login failed</b>\n\n<code>{escape(str(err)[:200])}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_osint_settings",emoji="🔙",style="primary")]]))
        return
    if data == "adm_osint_clear_token":
        osint_clear_cached_token()
        try: await q.answer("✅ Token cleared", show_alert=True)
        except: pass
        await view_admin_osint_settings(update); return

    # ---------- ZIP staging callbacks ----------
    if data.startswith("zip_price_set|"):
        cn = data.split("|", 1)[1]
        st = zip_staging.get(uid)
        if not st or cn not in st['country_groups']:
            try: await q.answer("Session expired", show_alert=True)
            except: pass
            return
        temp_data[uid] = {'admin_action': 'zip_set_price', 'zip_country': cn}
        await q.message.reply_text(
            f"<b>{emo('💰')} SET PRICE</b>\n\n"
            f"{emo('🌎')} Country: <b>{cn}</b>\n"
            f"{emo('📦')} Accounts: {len(st['country_groups'][cn])}\n\n"
            f"{emo('👉')} Send price in ₹ (all accounts of this country):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return
    if data == "zip_upload_all":
        await zip_finalize_upload(uid, context, q); return
    if data == "zip_cancel":
        zip_staging.pop(uid, None)
        temp_data.pop(uid, None)
        try: await q.message.reply_text(f"{emo('❌')} ZIP upload cancelled.", parse_mode="HTML")
        except: pass
        return

    if data == "adm_global_broadcast":
        if not is_master_owner(uid):
            try: await q.answer("Master only.", show_alert=True)
            except: pass
            return
        await view_global_broadcast(update); return
    if data in ("gb_start", "gb_start_pin"):
        if not is_master_owner(uid):
            try: await q.answer("Master only.", show_alert=True)
            except: pass
            return
        pin = data == "gb_start_pin"
        temp_data[uid] = {'admin_action': 'bc_wait_msg', 'bcast_buttons': [],
                          'bcast_pin': pin, 'bcast_text': '',
                          'bcast_media_type': None, 'bcast_media_id': None,
                          'bcast_global': True,
                          'bcast_button_position': 'below_center'}
        await q.message.reply_text(
            f"<b>{emo('🌍')} GLOBAL BROADCAST{' + PIN' if pin else ''}</b>\n\n"
            f"{emo('📝')} Send message:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return

    if data == "adm_s2_menu": await view_admin_s2_menu(update); return
    if data.startswith("adm_s2_list|"): await view_admin_s2_list(update, int(data.split("|")[1])); return
    if data.startswith("adm_s2_view|"): await view_admin_s2_item(update, data.split("|", 1)[1]); return
    if data == "adm_s2_add_single":
        temp_data[uid] = {'admin_action': 's2_add_cat'}
        await q.message.reply_text(f"<b>{emo('📱')} ADD SERVER 2</b>\n\n{emo('🎯')} Select category:",
            parse_mode="HTML", reply_markup=category_select_kb("s2_add_cat_pick")); return
    if data == "adm_s2_add_zip":
        temp_data[uid] = {'admin_action': 's2_add_zip_cat'}
        await q.message.reply_text(f"<b>{emo('📦')} ADD ZIP S2</b>\n\n{emo('🎯')} Select category:",
            parse_mode="HTML", reply_markup=category_select_kb("s2_add_zip_pick")); return
    if data.startswith("s2_add_cat_pick|"):
        cd = data.split("|", 1)[1]
        try: _s, cn = cd.split("|", 1)
        except: cn = cd
        temp_data[uid] = {'admin_action': 's2_add_phone', 'stock_server': 'SERVER2', 'stock_cat': cn}
        await q.message.reply_text(f"<b>{emo('📞')} Enter phone</b>\n\n{emo('🎯')} {cn}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data.startswith("s2_add_zip_pick|"):
        cd = data.split("|", 1)[1]
        try: _s, cn = cd.split("|", 1)
        except: cn = cd
        temp_data[uid] = {'admin_action': 's2_add_zip', 'stock_server': 'SERVER2', 'stock_cat': cn}
        await q.message.reply_text(f"<b>{emo('📤')} Send ZIP</b>\n\n{emo('🎯')} {cn}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_s2_del_pick":
        rows = cur.execute("""SELECT phone, country_icon, country_name, price FROM stock
            WHERE server='SERVER2' AND available=1 ORDER BY added_date DESC LIMIT 30""").fetchall()
        if not rows:
            try: await q.answer("No available stock", show_alert=True)
            except: pass
            return
        kbr = []
        for r in rows:
            kbr.append([ibtn(f"🗑️ {r['country_icon']} {r['phone']} • ₹{r['price']:.0f}",
                             f"adm_s2_del_confirm|{r['phone']}", emoji="🗑️", style="danger")])
        kbr.append([ibtn("CANCEL","adm_s2_menu",emoji="🚫",style="danger")])
        await q.message.reply_text(
            f"<b>{emo('🗑️')} CHOOSE S2 STOCK TO DELETE</b>\n\n"
            f"{emo('📋')} {len(rows)} available\n{emo('👉')} Tap to delete:",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kbr)); return
    if data.startswith("adm_s2_edit|"):
        p = data.split("|"); f = p[1]; ph = p[2]
        temp_data[uid] = {'admin_action': f's2_edit_{f}', 'stock_phone': ph}
        await q.message.reply_text(f"<b>{emo('✏️')} New {f}:</b>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data.startswith("adm_s2_toggle|"):
        ph = data.split("|", 1)[1]
        r = cur.execute("SELECT available FROM stock WHERE phone=?", (ph,)).fetchone()
        if r:
            nv = 0 if r["available"] else 1
            cur.execute("UPDATE stock SET available=? WHERE phone=?", (nv, ph)); db.commit()
            try: await q.answer(f"{'SOLD' if not nv else 'AVAILABLE'}")
            except: pass
            await view_admin_s2_item(update, ph)
        return
    if data.startswith("adm_s2_del_confirm|"):
        ph = data.split("|", 1)[1]
        r = cur.execute("SELECT country_name, country_icon, server FROM stock WHERE phone=?", (ph,)).fetchone()
        cur.execute("DELETE FROM stock WHERE phone=?", (ph,)); db.commit()
        await log_stock_removed(uid, ph, f"{r['country_icon']} {r['country_name']}" if r else "—",
                                r['server'] if r else "SERVER2")
        try: await q.answer("✅ Deleted", show_alert=True)
        except: pass
        await view_admin_s2_list(update, 1); return
    if data.startswith("adm_s2_sold|"):
        await view_admin_s2_sold(update, int(data.split("|")[1])); return

    if data == "adm_s3_menu": await view_admin_s3_menu(update); return
    if data.startswith("adm_s3_view|"):
        p = data.split("|"); await view_admin_s3_section(update, p[1], int(p[2])); return
    if data.startswith("adm_s3_item|"):
        await view_admin_s3_item(update, int(data.split("|")[1])); return
    if data == "adm_s3_add_panel":
        temp_data[uid] = {'admin_action': 's3_add_name', 's3_section': 'PANNELS'}
        await q.message.reply_text(f"{emo('📦')} ADD PANEL — Send name:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_s3_add_src":
        temp_data[uid] = {'admin_action': 's3_add_name', 's3_section': 'SOURCE CODE'}
        await q.message.reply_text(f"{emo('💻')} ADD SOURCE — Send name:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_s3_add_osint":
        temp_data[uid] = {'admin_action': 's3_add_name', 's3_section': 'OSINT APIS'}
        await q.message.reply_text(
            f"{emo('🔍')} ADD OSINT API — Send name:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_s3_del_pick":
        rows = cur.execute("""SELECT id, section, name, price FROM file_products
            WHERE active=1 ORDER BY section, id DESC LIMIT 30""").fetchall()
        if not rows:
            try: await q.answer("No S3 items", show_alert=True)
            except: pass
            return
        kbr = []
        for r in rows:
            kbr.append([ibtn(f"🗑️ {r['section'][:6]} • {r['name'][:25]} • ₹{r['price']}",
                             f"adm_s3_del_confirm|{r['id']}", emoji="🗑️", style="danger")])
        kbr.append([ibtn("CANCEL","adm_s3_menu",emoji="🚫",style="danger")])
        await q.message.reply_text(
            f"<b>{emo('🗑️')} CHOOSE S3 ITEM TO DELETE</b>\n\n{emo('📋')} {len(rows)} items",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kbr)); return
    if data.startswith("adm_s3_edit|"):
        p = data.split("|"); f = p[1]; pid = p[2]
        temp_data[uid] = {'admin_action': f's3_edit_{f}', 's3_id': int(pid)}
        await q.message.reply_text(f"<b>{emo('✏️')} New {f}:</b>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data.startswith("adm_s3_toggle|"):
        pid = int(data.split("|")[1])
        r = cur.execute("SELECT active FROM file_products WHERE id=?", (pid,)).fetchone()
        if r:
            nv = 0 if r["active"] else 1
            cur.execute("UPDATE file_products SET active=? WHERE id=?", (nv, pid)); db.commit()
            try: await q.answer(f"{'INACTIVE' if not nv else 'ACTIVE'}")
            except: pass
            await view_admin_s3_item(update, pid)
        return
    if data.startswith("adm_s3_del_confirm|"):
        pid = int(data.split("|")[1])
        r = cur.execute("SELECT name, section FROM file_products WHERE id=?", (pid,)).fetchone()
        cur.execute("DELETE FROM file_products WHERE id=?", (pid,)); db.commit()
        try: await q.answer("✅ Deleted", show_alert=True)
        except: pass
        if r: await view_admin_s3_section(update, r["section"], 1)
        return

    if data == "adm_stock_all": await view_admin_stock_all(update, 1); return
    if data.startswith("adm_stock_all|"): await view_admin_stock_all(update, int(data.split("|")[1])); return

    if data == "adm_userlog_menu": await view_userlog_menu(update); return
    if data == "adm_userlog_set":
        temp_data[uid] = {'admin_action': 'userlog_set'}
        await q.message.reply_text(f"{emo('📢')} Send chat ID:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_userlog_use_me":
        set_user_log_channel(uid)
        try: await q.answer("✅ Using your DM", show_alert=True)
        except: pass
        await view_userlog_menu(update); return
    if data == "adm_userlog_clear":
        set_user_log_channel(None)
        try: await q.answer("✅ Cleared", show_alert=True)
        except: pass
        await view_userlog_menu(update); return
    if data == "adm_userlog_test":
        try: await q.answer("🧪 Testing...")
        except: pass
        if not has_user_log_channel():
            try: await q.answer("Set channel first!", show_alert=True)
            except: pass
            return
        await log_purchase_public(uid, "TEST123", "🇲🇾 Malaysia", 100, "60187681761",
                                   "59826", "VILLAGEE@121", 9799, status="Completed", is_file=False)
        try: await q.message.reply_text(f"{emo('✅')} Test sent!", parse_mode="HTML")
        except: pass
        return

    if data == "adm_bots_menu": await view_bot_manager(update); return
    if data == "adm_bot_add":
        if not is_master_owner(uid): return
        temp_data[uid] = {'admin_action': 'adm_bot_add_token'}
        await q.message.reply_text(f"{emo('➕')} Send bot token:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data.startswith("adm_bot_view|"): await view_bot_detail(update, data.split("|", 1)[1]); return
    if data.startswith("adm_bot_stop|"):
        if not is_master_owner(uid): return
        ok, msg = await stop_bot_by_token_prefix(data.split("|", 1)[1])
        try: await q.answer(f"{'✅' if ok else '❌'} {msg}", show_alert=True)
        except: pass
        return
    if data.startswith("adm_bot_start|"):
        if not is_master_owner(uid): return
        ok, msg = await start_bot_by_token_prefix(data.split("|", 1)[1])
        try: await q.answer(f"{'✅' if ok else '❌'} {msg}", show_alert=True)
        except: pass
        return
    if data.startswith("adm_bot_remove_ask|"):
        if not is_master_owner(uid): return
        kb = InlineKeyboardMarkup([
            [ibtn("YES, REMOVE", f"adm_bot_remove_do|{data.split('|',1)[1]}", emoji="🗑️", style="danger")],
            [ibtn("CANCEL","adm_bots_menu",emoji="🔙",style="primary")]])
        await q.message.reply_text(f"<b>⚠️ Confirm removal?</b>", parse_mode="HTML", reply_markup=kb); return
    if data.startswith("adm_bot_remove_do|"):
        if not is_master_owner(uid): return
        ok, msg = await remove_bot_by_token_prefix(data.split("|", 1)[1])
        try: await q.answer(f"{'✅' if ok else '❌'} {msg}", show_alert=True)
        except: pass
        await view_bot_manager(update); return

    if data == "adm_gmail_menu": await view_admin_gmail_menu(update); return
    if data == "adm_tx_today": await view_admin_tx_today(update, 1); return
    if data == "adm_tx_month": await view_admin_tx_month(update, 1); return
    if data.startswith("tx_page|"):
        p = data.split("|")
        if p[1] == "today": await view_admin_tx_today(update, int(p[2]))
        else: await view_admin_tx_month(update, int(p[2]))
        return
    if data == "adm_gmail_set_email":
        temp_data[uid] = {'admin_action': 'gmail_set_email'}
        await q.message.reply_text(f"{emo('📧')} Send Gmail address:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_gmail_set_upi":
        temp_data[uid] = {'admin_action': 'gmail_set_upi'}
        await q.message.reply_text(f"{emo('🏦')} Send AUTO UPI ID:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_paytm_set_upi":
        temp_data[uid] = {'admin_action': 'paytm_set_upi'}
        await q.message.reply_text(f"{emo('💳')} Send GLOBAL PAYTM UPI ID:\n\nCurrent: <code>{escape(get_paytm_upi_id() or 'NOT SET')}</code>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_paytm_set_mid":
        temp_data[uid] = {'admin_action': 'paytm_set_mid'}
        await q.message.reply_text(f"{emo('🆔')} Send GLOBAL PAYTM MID:\n\nCurrent: <code>{escape(get_paytm_mid() or 'NOT SET')}</code>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_gmail_set_pw":
        temp_data[uid] = {'admin_action': 'gmail_set_pw'}
        await q.message.reply_text(f"{emo('🔑')} Send App Password:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_gmail_toggle":
        ns = 'off' if is_gmail_verify_enabled() else 'on'
        set_setting('gmail_verify_enabled', ns)
        try: await q.answer(f"FamPay {ns.upper()}", show_alert=True)
        except: pass
        await log_admin_action(uid, "Toggle FamPay", ns.upper())
        await view_admin_gmail_menu(update); return
    if data == "adm_gmail_test":
        try: await q.answer("Testing...")
        except: pass
        ea = get_setting('gmail_email','').strip(); ap = get_setting('gmail_app_password','').strip()
        if not ea or not ap:
            await q.message.reply_text(f"{emo('❌')} Not configured.", parse_mode="HTML"); return
        try:
            def _t():
                c = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
                c.login(ea, ap); c.select("INBOX")
                _, d = c.search(None, f'(FROM "{FAMPAY_SENDER}")')
                n = len(d[0].split()) if d[0] else 0
                c.close(); c.logout(); return n
            n = await asyncio.to_thread(_t)
            await q.message.reply_text(f"{emo('✅')} IMAP OK\n📧 {ea}\n📥 {n} FamPay emails",
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                    [ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]))
        except Exception as e:
            await q.message.reply_text(f"{emo('❌')} {escape(str(e))}", parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]))
        return
    if data == "adm_gmail_recent":
        rs = cur.execute("""SELECT msg_id, amount, utr, txn_id, matched_order_id
            FROM fampay_emails ORDER BY id DESC LIMIT 15""").fetchall()
        if not rs:
            await q.message.reply_text(f"{emo('❌')} No emails.", parse_mode="HTML"); return
        tb = [["💵 AMT","🔢 UTR","🆔 TXN","🎯"]]
        for r in rs:
            tb.append([f"₹{r['amount'] or 0:.0f}", (r["utr"] or "—")[:14],
                       (r["txn_id"] or "—")[:14], "✅" if r["matched_order_id"] else "—"])
        await send_rich_async(uid, [make_heading("📜 RECENT EMAILS", 2), make_table(tb)],
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]).to_dict(),
            edit_query=_edit_query_of(update)); return
    if data == "adm_gmail_mismatches":
        rs = cur.execute("""SELECT order_id, user_id, amount, paid_amount FROM upi_orders
            WHERE status='mismatch' ORDER BY date DESC LIMIT 20""").fetchall()
        tb = [["🆔 ORDER","👤 USER","💰 EXP","💵 PAID"]]
        for r in rs: tb.append([str(r["order_id"])[:20], str(r["user_id"]),
                                 f"₹{r['amount'] or 0:.0f}", f"₹{r['paid_amount'] or 0:.0f}"])
        if not rs: tb.append(["—","—","—","—"])
        await send_rich_async(uid, [make_heading("⚠️ MISMATCH", 2), make_table(tb)],
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]).to_dict(),
            edit_query=_edit_query_of(update)); return
    if data == "adm_gmail_duplicates":
        rs = cur.execute("""SELECT order_id, user_id, amount, paid_amount, utr, txn_id
            FROM upi_orders WHERE status='duplicate' ORDER BY date DESC LIMIT 20""").fetchall()
        tb = [["🆔 ORDER","👤 USER","🔢 UTR","🆔 TXN"]]
        for r in rs: tb.append([str(r["order_id"])[:18], str(r["user_id"]),
                                 (r["utr"] or "—")[:12], (r["txn_id"] or "—")[:12]])
        if not rs: tb.append(["—","—","—","—"])
        await send_rich_async(uid, [make_heading("🚫 DUP", 2), make_table(tb)],
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]).to_dict(),
            edit_query=_edit_query_of(update)); return

    if data == "adm_lzt_settings": await view_admin_lzt_settings(update); return
    if data == "adm_setlzt_token":
        temp_data[uid] = {'admin_action': 'lzt_set_token'}
        await q.message.reply_text(f"{emo('🔑')} Send token or 'remove':", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_set_lzt_markup":
        temp_data[uid] = {'admin_action': 'lzt_set_markup'}
        await q.message.reply_text(f"{emo('💹')} Send integer % (e.g. 20):", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_set_default_daybreak":
        temp_data[uid] = {'admin_action': 'lzt_set_default_daybreak'}
        await q.message.reply_text(f"{emo('🗓️')} Send: 1/7/14/30", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [ibtn("1","db_set|1",emoji="1️⃣",style="primary"), ibtn("7","db_set|7",emoji="7️⃣",style="primary")],
                [ibtn("14","db_set|14",emoji="🔢",style="primary"), ibtn("30","db_set|30",emoji="3️⃣",style="primary")],
                [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data.startswith("db_set|"):
        try:
            v = int(data.split("|", 1)[1])
            if v not in DAYBREAK_OPTIONS: raise ValueError()
            set_setting("lzt_default_daybreak", str(v))
            try: await q.answer(f"✅ {v}d", show_alert=True)
            except: pass
            await log_admin_action(uid, "Set Daybreak", str(v))
        except:
            try: await q.answer("Invalid", show_alert=True)
            except: pass
        try: await view_admin_lzt_settings(update)
        except: pass
        return
    if data == "adm_lzt_cmark_list":
        rs = cur.execute("SELECT country, markup_percent FROM lzt_settings ORDER BY country").fetchall()
        tb = [["🌎 COUNTRY","💹 MARKUP %"]]
        for r in rs: tb.append([r["country"], f"{r['markup_percent']}%"])
        if not rs: tb.append(["—","—"])
        kb = InlineKeyboardMarkup([
            [ibtn("SET","adm_lzt_set_cmark",emoji="➕",style="success")],
            [ibtn("BACK","adm_lzt_settings",emoji="🔙",style="primary")]])
        await send_rich_async(uid, [make_heading("🌍 COUNTRY MARKUPS", 2), make_table(tb)],
                              reply_markup=kb.to_dict(), edit_query=_edit_query_of(update)); return
    if data == "adm_lzt_set_cmark":
        temp_data[uid] = {'admin_action': 'lzt_set_cmark'}
        await q.message.reply_text(f"{emo('🌍')} Format: <code>country_name percent</code>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_lzt_clear_cache":
        clear_lzt_cache()
        try: await q.answer("✅ Cleared", show_alert=True)
        except: pass
        await view_admin_lzt_settings(update); return

    if data == "adm_log_menu": await view_admin_log_menu(update); return
    if data == "adm_log_add":
        temp_data[uid] = {'admin_action': 'log_add_id'}
        await q.message.reply_text(f"{emo('➕')} Send chat ID:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_log_rem":
        rd = get_log_targets_full()
        if not rd:
            try: await q.answer("No targets", show_alert=True)
            except: pass
            return
        kbr = [[ibtn((r["title"] or str(r["chat_id"]))[:30],
                     f"adm_log_del|{r['chat_id']}", emoji="🗑️", style="danger")] for r in rd]
        kbr.append([ibtn("BACK","adm_log_menu",emoji="🔙",style="primary")])
        await q.message.reply_text(f"<b>{emo('🗑️')} REMOVE</b>", parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup(kbr)); return
    if data.startswith("adm_log_del|"):
        cid = data.split("|", 1)[1]
        if len(get_log_targets()) <= 1:
            try: await q.answer("Cannot remove last!", show_alert=True)
            except: pass
            return
        remove_log_target(cid)
        try: await q.answer("✅ Removed", show_alert=True)
        except: pass
        await log_target_change(uid, "Removed", cid)
        await view_admin_log_menu(update); return
    if data == "adm_log_test":
        try: await q.answer("🧪 Testing...")
        except: pass
        await test_rich_message(uid); return
    if data == "adm_log_src_set":
        temp_data[uid] = {'admin_action': 'log_src_set'}
        cs = get_log_source_chat()
        await q.message.reply_text(f"<b>{emo('📤')} SOURCE</b>\n\nCurrent: <code>{cs}</code>\n\n{emo('📝')} Send chat ID:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [ibtn("USE MY ID","log_src_use_me",emoji="👤",style="success")],
                [ibtn("CLEAR","log_src_clear",emoji="❌",style="danger")],
                [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "log_src_use_me":
        set_log_source_chat(uid); temp_data.pop(uid, None)
        try: await q.answer("✅ Set to your DM", show_alert=True)
        except: pass
        await log_target_change(uid, "Source Set (DM)", uid, "Owner DM")
        await view_admin_log_menu(update); return
    if data == "log_src_clear":
        set_log_source_chat(None); temp_data.pop(uid, None)
        try: await q.answer("✅ Cleared", show_alert=True)
        except: pass
        await view_admin_log_menu(update); return

    if data == "adm_toggle_bot":
        ns = 'off' if is_bot_online() else 'on'; set_setting('bot_status', ns)
        try: await q.answer(f"Bot {ns.upper()}", show_alert=True)
        except: pass
        await view_admin_maintenance(update); return
    if data == "adm_toggle_buy1":
        ns = 'off' if is_buy1_online() else 'on'
        set_setting('buy1_status', ns); set_setting('server1_status', ns)
        try: await q.answer(f"S1 {ns.upper()}", show_alert=True)
        except: pass
        try: await view_admin_lzt_settings(update)
        except: await view_admin_maintenance(update)
        return
    if data == "adm_toggle_buy2":
        ns = 'off' if is_buy2_online() else 'on'; set_setting('buy2_status', ns)
        try: await q.answer(f"S2 {ns.upper()}", show_alert=True)
        except: pass
        await view_admin_maintenance(update); return
    if data == "adm_toggle_buy3":
        ns = 'off' if is_buy3_online() else 'on'; set_setting('buy3_status', ns)
        try: await q.answer(f"S3 {ns.upper()}", show_alert=True)
        except: pass
        await view_admin_maintenance(update); return
    if data == "adm_toggle_wa":
        cs = get_setting('wa_status', 'soon')
        ns = 'on' if cs != 'on' else 'soon'; set_setting('wa_status', ns)
        try: await q.answer(f"WA {ns.upper()}", show_alert=True)
        except: pass
        await view_admin_maintenance(update); return
    if data == "adm_toggle_upi":
        ns = 'off' if is_upi_online() else 'on'; set_setting('upi_status', ns)
        try: await q.answer(f"UPI {ns.upper()}", show_alert=True)
        except: pass
        await view_admin_maintenance(update); return

    if data == "adm_users_menu":
        rows = [
            [ibtn("USERS LIST","adm_users_list",emoji="📋",style="primary")],
            [ibtn("USER INFO","adm_user_info",emoji="🔍",style="primary")],
            [ibtn("BALANCE","adm_bal_menu",custom_id=BALANCE_PREMIUM_EMOJI_ID,style="success")],
            [ibtn("DISCOUNT","adm_discount_menu",emoji="🎯",style="success")],
            [ibtn("BAN","adm_ban_user",emoji="🚫",style="danger"),
             ibtn("UNBAN","adm_unban_user",emoji="✅",style="success")],
            [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
        await send_rich_async(uid, [make_heading("👥 USER MGMT", 2)],
                              reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                              fallback_text="👥 USER MGMT", edit_query=_edit_query_of(update)); return

    if data == "adm_stock_menu": await view_admin_stock_menu(update); return
    if data == "adm_cat_server_select": await view_admin_cat_server_select(update); return
    if data == "adm_settings": await view_admin_settings(update); return
    if data == "adm_maintenance": await view_admin_maintenance(update); return
    if data == "adm_bal_menu":
        rows = [[ibtn("ADD BALANCE","adm_bal_add",emoji="➕",style="success")],
                [ibtn("REDUCE","adm_bal_reduce",emoji="➖",style="danger")],
                [ibtn("SET","adm_bal_set",custom_id=BALANCE_PREMIUM_EMOJI_ID,style="primary")],
                [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
        await send_rich_async(uid, [make_heading("💰 BALANCE MGR", 2),
            make_paragraph("Format: user_id amount")],
            reply_markup=InlineKeyboardMarkup(rows).to_dict(),
            fallback_text="💰 BALANCE", edit_query=_edit_query_of(update)); return
    if data == "adm_discount_menu":
        rows = [[ibtn("GIVE","adm_disc_give",emoji="🎯",style="success")],
                [ibtn("REMOVE","adm_disc_remove",emoji="❌",style="danger")],
                [ibtn("BACK","adm_users_menu",emoji="🔙",style="primary")]]
        await send_rich_async(uid, [make_heading("🎯 DISCOUNT", 2)],
                              reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                              fallback_text="🎯 DISCOUNT", edit_query=_edit_query_of(update)); return
    if data == "adm_coupon_menu":
        rows = [[ibtn("ADD","adm_addcoupon",emoji="➕",style="success")],
                [ibtn("LIST","adm_list_coupons",emoji="📋",style="primary")],
                [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
        await send_rich_async(uid, [make_heading("🎁 COUPONS", 2)],
                              reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                              fallback_text="🎁 COUPONS", edit_query=_edit_query_of(update)); return

    if data == "adm_users_list": await view_admin_users_list(update); return
    if data.startswith("adm_usr_pg|"): await view_admin_users_list(update, int(data.split("|")[1])); return

    if data == "adm_channels":
        rc = get_all_channels()
        tb = [["📢 ID","🔗 LINK"]]
        for r in rc: tb.append([r["channel_id"], r["channel_link"]])
        if not rc: tb.append(["—","None"])
        kb = InlineKeyboardMarkup([
            [ibtn("ADD","adm_ch_add",emoji="➕",style="success"),
             ibtn("REMOVE","adm_ch_remove",emoji="➖",style="danger")],
            [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]])
        await send_rich_async(uid, [make_heading("📢 FORCE-JOIN", 2),
            make_paragraph("Bot must be admin in these channels for force-join checks to work."),
            make_table(tb)],
            reply_markup=kb.to_dict(),
            fallback_text="📢 CHANNELS", edit_query=_edit_query_of(update)); return
    if data.startswith("adm_cat|"): await view_cat_manage(update, data.split("|", 1)[1]); return
    if data.startswith("adm_cat_add|"):
        srv = data.split("|", 1)[1]
        temp_data[uid] = {'admin_action': 'cat_add_name', 'cat_server': srv}
        await q.message.reply_text(f"{emo('➕')} ADD to {srv} — Send name:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data.startswith("cat_view|"):
        cid = int(data.split("|")[1])
        r = cur.execute("SELECT * FROM custom_categories WHERE id=?", (cid,)).fetchone()
        if not r: return
        await send_rich_async(uid, [make_heading("🗂️ CATEGORY", 2),
              make_table([["ℹ️ INFO","📋 VALUE"],["🆔 ID", str(cid)],["📁 Server", r["server"]],
                          ["🎯 Name", r["name"]],["😀 Emoji", r["emoji"]],
                          ["📊 Status", "Active" if r["active"] else "Inactive"]])],
            reply_markup=InlineKeyboardMarkup([
                [ibtn("EDIT","cat_edit|"+str(cid),emoji="🔧",style="success")],
                [ibtn("BACK",f"adm_cat|{r['server']}",emoji="🔙",style="primary")]]).to_dict(),
            edit_query=_edit_query_of(update)); return
    if data.startswith("cat_edit|"):
        cid = int(data.split("|")[1])
        r = cur.execute("SELECT * FROM custom_categories WHERE id=?", (cid,)).fetchone()
        if not r: return
        temp_data[uid] = {'admin_action': 'cat_edit_name', 'cat_id': cid}
        await q.message.reply_text(f"<b>{emo('✏️')} EDIT</b>\nCurrent: <code>{r['name']}</code>\n\nSend NAME (or /skip):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","cat_edit_skip_name",emoji="➖",style="primary")],
                                                [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "cat_edit_skip_name":
        st = temp_data.get(uid)
        if st and 'cat_id' in st:
            st['admin_action'] = 'cat_edit_emoji'
            await q.message.reply_text(f"Send EMOJI (or /skip):", parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","cat_edit_skip_emoji",emoji="➖",style="primary")]]))
        return
    if data == "cat_edit_skip_emoji":
        st = temp_data.get(uid)
        if st and 'cat_id' in st:
            temp_data.pop(uid, None)
            await q.message.reply_text(f"{emo('✅')} Done.", parse_mode="HTML"); return
    if data.startswith("cat_del_ask|"):
        cid = int(data.split("|")[1])
        r = cur.execute("SELECT * FROM custom_categories WHERE id=?", (cid,)).fetchone()
        if not r: return
        kb = InlineKeyboardMarkup([
            [ibtn("YES, DELETE", f"cat_del|{cid}", emoji="🗑️", style="danger")],
            [ibtn("BACK", f"adm_cat|{r['server']}", emoji="🔙", style="primary")]])
        await q.message.reply_text(f"<b>⚠️ Delete '{r['name']}'?</b>", parse_mode="HTML", reply_markup=kb); return
    if data.startswith("cat_del|"):
        cid = int(data.split("|")[1])
        r = cur.execute("SELECT server FROM custom_categories WHERE id=?", (cid,)).fetchone()
        cur.execute("DELETE FROM custom_categories WHERE id=?", (cid,)); db.commit()
        try: await q.answer("✅ Deleted", show_alert=True)
        except: pass
        if r: await view_cat_manage(update, r["server"])
        return

    if data == "adm_ch_add":
        temp_data[uid] = {'admin_action': 'ch_add_id'}
        await q.message.reply_text(f"{emo('➕')} Send channel ID (e.g. -1001234567890):", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_ch_remove":
        rc = get_all_channels()
        if not rc: return
        kbr = [[ibtn(r["channel_link"][:50], f"adm_ch_del|{r['channel_id']}", emoji="🗑️", style="danger")] for r in rc]
        kbr.append([ibtn("BACK","adm_channels",emoji="🔙",style="primary")])
        await q.message.reply_text(f"<b>{emo('➖')} REMOVE</b>", parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup(kbr)); return
    if data.startswith("adm_ch_del|"):
        cid = data.split("|", 1)[1]
        cur.execute("DELETE FROM channels WHERE channel_id=?", (cid,)); db.commit()
        _force_join_cache.clear()
        try: await q.answer("✅ Removed", show_alert=True)
        except: pass
        return

    if data in ("adm_broadcast", "adm_broadcast_pin"):
        pin = data == "adm_broadcast_pin"
        temp_data[uid] = {'admin_action': 'bc_wait_msg', 'bcast_buttons': [],
                          'bcast_pin': pin, 'bcast_text': '',
                          'bcast_media_type': None, 'bcast_media_id': None,
                          'bcast_global': False,
                          'bcast_button_position': 'below_center'}
        await q.message.reply_text(f"<b>{emo('📢')} BROADCAST{' + PIN' if pin else ''}</b>\n\n"
            f"{emo('📝')} Send message:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return

    if data == "adm_backup":
        try: await q.answer("💾 Creating...")
        except: pass
        try:
            backup = create_backup()
            fname = f"villagee_{current_bot_username()}_{int(time.time())}.json"
            bbytes = json.dumps(backup, indent=2, default=str).encode('utf-8')
            bio = io.BytesIO(bbytes); bio.name = fname
            cap_txt = (f"✅ <b>Backup</b>\n"
                       f"📁 <code>{escape(fname)}</code>\n"
                       f"💾 {len(bbytes)/1024:.1f} KB")
            await context.bot.send_document(chat_id=uid, document=InputFile(bio, filename=fname),
                caption=auto_premium(cap_txt),
                parse_mode="HTML")
            try: await log_admin_action(uid, "Backup Created", f"Size={len(bbytes)}")
            except: pass
        except Exception as e:
            log.error(f"Backup: {e}")
            try: await q.message.reply_text(f"{emo('❌')} <code>{html_safe_error(e)}</code>", parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]))
            except: pass
        return
    if data == "adm_restore":
        temp_data[uid] = {'admin_action': 'restore_wait'}
        await q.message.reply_text(f"{emo('📥')} Send JSON backup:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return

    if data.startswith("addcat|"):
        cd = data.split("|", 1)[1]
        try: sc, cn = cd.split("|", 1)
        except: sc = "SERVER2"; cn = cd
        if sc != "SERVER2": sc = "SERVER2"
        temp_data[uid] = {'admin_action': 'addstock_phone', 'stock_server': sc, 'stock_cat': cn}
        await q.message.reply_text(f"<b>{emo('📞')} Enter phone:</b>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data.startswith("addcat_zip|"):
        cd = data.split("|", 1)[1]
        try: sc, cn = cd.split("|", 1)
        except: sc = "SERVER2"; cn = cd
        if sc != "SERVER2": sc = "SERVER2"
        temp_data[uid] = {'admin_action': 'addzip', 'stock_server': sc, 'stock_cat': cn}
        await q.message.reply_text(f"<b>{emo('📤')} Send ZIP:</b>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return

    prompts = {
        'adm_bal_add': ('bal_add', '➕ ADD BALANCE\n\nFormat: <code>user_id amount</code>'),
        'adm_bal_reduce': ('bal_reduce', '➖ REDUCE\n\nFormat: <code>user_id amount</code>'),
        'adm_bal_set': ('bal_set', '💰 SET\n\nFormat: <code>user_id amount</code>'),
        'adm_user_info': ('user_info', '🔍 Send User ID:'),
        'adm_disc_give': ('disc_give', '🎯 Format: <code>user_id percent</code>'),
        'adm_disc_remove': ('disc_remove', '❌ Send user_id:'),
        'adm_ban_user': ('adm_ban_user', '🚫 Send User ID:'),
        'adm_unban_user': ('adm_unban_user', '✅ Send User ID:'),
        'adm_usdtrate': ('adm_usdtrate', '💲 New USDT Rate (₹):'),
        'adm_edit_transferfee': ('edit_transferfee', '📤 New Fee (%):'),
        'adm_edit_mindeposit': ('edit_mindeposit', '📉 New Min Deposit (₹):'),
        'adm_edit_c1': ('edit_c1', '📞 New Contact 1:'),
        'adm_edit_c2': ('edit_c2', '📢 New Contact 2:'),
        'adm_edit_support': ('edit_support', '🔗 New Support URL:'),
        'adm_edit_updateurl': ('edit_updateurl', '🔗 New Update URL:'),
        'adm_edit_maintimg': ('edit_maintimg', '🖼️ New Maint Image URL:'),
        'adm_edit_default_daybreak': ('edit_default_daybreak', '🗓️ Send: 1/7/14/30'),
        'adm_addcoupon': ('adm_addcoupon', '🎁 Send: <code>CODE amount max_uses</code>'),
    }
    if data in prompts:
        act, txt = prompts[data]
        temp_data[uid] = {'admin_action': act}
        await q.message.reply_text(f"<b>{txt}</b>", parse_mode="HTML"); return

    if data == "adm_list_coupons":
        rs = cur.execute("SELECT * FROM coupons").fetchall()
        if not rs:
            await q.message.reply_text(f"{emo('❌')} No coupons.", parse_mode="HTML"); return
        tb = [["🎫 CODE","💰 AMOUNT","📊 USED/MAX"]]
        for r in rs: tb.append([r['code'], f"₹{r['amount']}", f"{r['used']}/{r['max_uses']}"])
        await send_rich_async(uid, [make_heading("🎁 COUPONS", 2), make_table(tb)],
                              edit_query=_edit_query_of(update)); return

    if data == "adm_stats":
        u = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        s2 = cur.execute("SELECT COUNT(*) FROM stock WHERE available=1 AND server='SERVER2'").fetchone()[0]
        f = cur.execute("SELECT COUNT(*) FROM file_products WHERE active=1").fetchone()[0]
        o = cur.execute("SELECT COUNT(*), COALESCE(SUM(price),0) FROM orders").fetchone()
        tb = cur.execute("SELECT SUM(balance) FROM users").fetchone()[0] or 0
        mm = cur.execute("SELECT COUNT(*) FROM upi_orders WHERE status='mismatch'").fetchone()[0]
        dp = cur.execute("SELECT COUNT(*) FROM upi_orders WHERE status='duplicate'").fetchone()[0]
        await send_rich_async(uid, [make_heading("📊 STATISTICS", 2),
            make_table([["📊 STAT","📋 VALUE"],["👥 Users", str(u)],["📦 S2", str(s2)],
                        ["📁 S3", str(f)],["🛒 Orders", str(o[0])],["💰 Sales", f"₹{o[1]}"],
                        ["💼 Balances", f"₹{tb}"],["⚠️ Mism", str(mm)],["🚫 Dup", str(dp)],
                        ["🕒 TZ", "IST (UTC+5:30)"]])],
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]).to_dict(),
            fallback_text="📊 STATS", edit_query=_edit_query_of(update)); return

    if data == "adm_stock_edit_menu":
        temp_data[uid] = {'admin_action': 'stock_edit_phone'}
        await q.message.reply_text(f"{emo('🔧')} Send phone:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data == "adm_stock_del_menu":
        temp_data[uid] = {'admin_action': 'stock_del_phone'}
        await q.message.reply_text(f"{emo('🗑️')} Send phone:", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data.startswith("stock_edit_field|"):
        p = data.split("|"); f = p[1]; ph = p[2]
        temp_data[uid] = {'admin_action': f'stock_edit_{f}', 'stock_phone': ph}
        await q.message.reply_text(f"<b>{emo('✏️')} New {f}:</b>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])); return
    if data.startswith("stock_del_confirm|"):
        ph = data.split("|", 1)[1]
        r = cur.execute("SELECT country_name, country_icon, server FROM stock WHERE phone=?", (ph,)).fetchone()
        cur.execute("DELETE FROM stock WHERE phone=?", (ph,)); db.commit()
        await log_stock_removed(uid, ph, f"{r['country_icon']} {r['country_name']}" if r else "—",
                                r['server'] if r else "—")
        await q.message.reply_text(f"{emo('✅')} Deleted: <code>{ph}</code>", parse_mode="HTML"); return

    if data.startswith("dep_acc|"):
        p = data.split("|"); did, tu = p[1], int(p[2]); amt = int(p[5])
        r = cur.execute("SELECT status FROM deposits WHERE id=?", (did,)).fetchone()
        if not r or r[0] != 'pending':
            try: await q.answer("Already done", show_alert=True)
            except: pass
            return
        async with get_user_lock(tu):
            r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (tu,)).fetchone()
            old = r2["balance"] if r2 else 0
            update_balance(tu, amt)
            cur.execute("UPDATE deposits SET status='approved' WHERE id=?", (did,))
            cur.execute("UPDATE users SET total_deposited=total_deposited+? WHERE user_id=?", (amt, tu))
            db.commit()
            record_balance_history(tu, amt, "deposit_approved", "manual", f"By {uid}", old, old + amt)
        await log_deposit(tu, amt, p[3], "approved", dep_id=did, extra=f"👑 By <code>{uid}</code>")
        await process_referral_bonus(tu, amt)
        try: await context.bot.send_message(tu, f"<b>{emo('✅')} Deposit Approved!</b>\n₹{amt} added.", parse_mode="HTML")
        except: pass
        try: await q.edit_message_text(f"✅ Approved ₹{amt}")
        except: pass
        return
    if data.startswith("dep_rej|"):
        p = data.split("|"); did, tu = p[1], int(p[2])
        r = cur.execute("SELECT amount, method_name FROM deposits WHERE id=?", (did,)).fetchone()
        amt = r["amount"] if r else 0; m = r["method_name"] if r else "—"
        cur.execute("UPDATE deposits SET status='rejected' WHERE id=?", (did,)); db.commit()
        await log_deposit(tu, amt, m, "rejected", dep_id=did, extra=f"👑 By <code>{uid}</code>")
        try: await context.bot.send_message(tu, f"{emo('❌')} Deposit Rejected.", parse_mode="HTML")
        except: pass
        try: await q.edit_message_text("❌ Rejected")
        except: pass
        return

    if data == "bc_add_video" and uid in temp_data:
        temp_data[uid]['admin_action'] = 'bc_wait_video'
        await q.message.reply_text(f"{emo('🎬')} Send video:", parse_mode="HTML"); return
    if data == "bc_add_image" and uid in temp_data:
        temp_data[uid]['admin_action'] = 'bc_wait_image'
        await q.message.reply_text(f"{emo('🎥')} Send image:", parse_mode="HTML"); return
    if data == "bc_no_media" and uid in temp_data:
        temp_data[uid]['bcast_media_type'] = None; temp_data[uid]['bcast_media_id'] = None
        temp_data[uid]['admin_action'] = 'bc_btn_menu'
        await q.message.reply_text(f"{emo('✅')} Media skipped.", parse_mode="HTML",
                                    reply_markup=bcast_btn_action_kb()); return
    if data == "bc_add_btn" and uid in temp_data:
        if len(temp_data[uid].get('bcast_buttons', [])) >= 6:
            try: await q.answer("Max 6!", show_alert=True)
            except: pass
            return
        temp_data[uid]['admin_action'] = 'bc_btn_type'
        await q.message.reply_text(f"<b>{emo('🔘')} Type</b>", parse_mode="HTML",
                                    reply_markup=bcast_btn_type_kb()); return
    if data == "bc_btn_pos_menu" and uid in temp_data:
        cur_pos = temp_data[uid].get('bcast_button_position', 'below_center')
        await q.message.reply_text(
            f"<b>📍 BUTTON POSITION</b>\n\nCurrent: <code>{cur_pos}</code>\n\nChoose placement:",
            parse_mode="HTML", reply_markup=bcast_position_kb(cur_pos))
        return
    if data.startswith("bc_pos|") and uid in temp_data:
        pos = data.split("|", 1)[1]
        if pos not in ("above_left","above_center","above_right",
                       "below_left","below_center","below_right"):
            try: await q.answer("Invalid", show_alert=True)
            except: pass
            return
        temp_data[uid]['bcast_button_position'] = pos
        try: await q.answer(f"✅ {pos}")
        except: pass
        await q.message.reply_text(
            f"<b>✅ Position set</b>\n<code>{pos}</code>\n\nBack to button menu.",
            parse_mode="HTML", reply_markup=bcast_btn_action_kb())
        return
    if data == "bc_btn_inline" and uid in temp_data:
        temp_data[uid]['bcast_temp_type'] = 'inline'
        temp_data[uid]['admin_action'] = 'bc_btn_color'
        await q.message.reply_text(f"<b>{emo('🎨')} Color</b>", parse_mode="HTML",
                                    reply_markup=bcast_color_kb()); return
    if data == "bc_btn_rich" and uid in temp_data:
        temp_data[uid]['bcast_temp_type'] = 'rich'
        temp_data[uid]['bcast_temp_color'] = 'primary'
        temp_data[uid]['bcast_temp_emoji_id'] = None
        temp_data[uid]['bcast_temp_alt_emoji'] = None
        temp_data[uid]['admin_action'] = 'bc_btn_name'
        await q.message.reply_text(f"{emo('📝')} Send NAME:", parse_mode="HTML"); return
    if data == "bc_btn_no_emoji" and uid in temp_data:
        temp_data[uid]['bcast_temp_emoji_id'] = None
        temp_data[uid]['bcast_temp_alt_emoji'] = None
        temp_data[uid]['admin_action'] = 'bc_btn_link'
        await q.message.reply_text(f"{emo('🔗')} Send LINK:", parse_mode="HTML"); return
    if data == "bc_btn_default_emoji" and uid in temp_data:
        temp_data[uid]['bcast_temp_alt_emoji'] = "🔥"
        temp_data[uid]['admin_action'] = 'bc_btn_link'
        await q.message.reply_text(f"{emo('🔗')} Send LINK:", parse_mode="HTML"); return
    if data in ("bc_color_primary","bc_color_success","bc_color_danger") and uid in temp_data:
        cm = {"bc_color_primary":"primary","bc_color_success":"success","bc_color_danger":"danger"}
        temp_data[uid]['bcast_temp_color'] = cm[data]
        temp_data[uid]['admin_action'] = 'bc_btn_name'
        await q.message.reply_text(f"{emo('📝')} Send NAME:", parse_mode="HTML"); return
    if data == "bc_done":
        if uid not in temp_data:
            try: await q.answer("Expired", show_alert=True)
            except: pass
            return
        state = temp_data.pop(uid)
        is_global = state.get('bcast_global', False)
        if is_global and not is_master_owner(uid):
            try: await q.answer("Master only!", show_alert=True)
            except: pass
            return
        await q.message.reply_text(f"{emo('⏳')} Starting {'GLOBAL ' if is_global else ''}broadcast...",
                                     parse_mode="HTML")
        if is_global:
            asyncio.create_task(do_global_broadcast_full(uid, context, state))
        else:
            asyncio.create_task(do_broadcast(context, uid, state))
        return

    if data == "adm_admin_menu":
        if not is_owner(uid): return
        rows = [[ibtn("ADD ADMIN","adm_add_admin",emoji="➕",style="success")],
                [ibtn("LIST","adm_list_admins",emoji="📋",style="primary")],
                [ibtn("REMOVE","adm_rem_admin",emoji="🗑️",style="danger")],
                [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
        await send_rich_async(uid, [make_heading("👑 ADMIN MGMT", 2)],
                              reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                              fallback_text="👑 ADMIN MGMT", edit_query=_edit_query_of(update)); return
    if data == "adm_add_admin":
        if not is_owner(uid): return
        temp_data[uid] = {'admin_action': 'add_admin_id'}
        await q.message.reply_text(f"{emo('➕')} Send user ID:", parse_mode="HTML"); return
    if data == "adm_list_admins":
        if not is_owner(uid): return
        ra = get_admins()
        if not ra:
            await q.message.reply_text(f"{emo('❌')} None.", parse_mode="HTML"); return
        tb = [["👤 USER ID","📊 PERMS"]]
        for r in ra:
            ps = [p.replace("p_","") for p in ["p_add_stock","p_manage_stock","p_stats","p_bal",
                "p_settings","p_users","p_broadcast","p_products","p_admin_mgmt"] if r[p]]
            tb.append([str(r["user_id"]), ",".join(ps) or "none"])
        kbr = [[ibtn(str(r["user_id"]), f"adm_perm_edit|{r['user_id']}", emoji="👤", style="primary")] for r in ra]
        kbr.append([ibtn("BACK","adm_admin_menu",emoji="🔙",style="primary")])
        await send_rich_async(uid, [make_heading("👑 ADMINS", 2), make_table(tb)],
                              reply_markup=InlineKeyboardMarkup(kbr).to_dict(),
                              edit_query=_edit_query_of(update)); return
    if data == "adm_rem_admin":
        if not is_owner(uid): return
        ra = get_admins()
        if not ra:
            await q.message.reply_text(f"{emo('❌')} None.", parse_mode="HTML"); return
        kbr = [[ibtn(str(r["user_id"]), f"adm_rem_admin_conf|{r['user_id']}", emoji="🗑️", style="danger")] for r in ra]
        kbr.append([ibtn("BACK","adm_admin_menu",emoji="🔙",style="primary")])
        await q.message.reply_text(f"<b>🗑️ REMOVE</b>", parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup(kbr)); return
    if data.startswith("adm_rem_admin_conf|"):
        if not is_owner(uid): return
        tu = int(data.split("|")[1])
        cur.execute("DELETE FROM admins WHERE user_id=?", (tu,)); db.commit()
        try: await q.answer(f"✅ Removed", show_alert=True)
        except: pass
        return
    if data.startswith("adm_perm_edit|"):
        if not is_owner(uid): return
        tu = int(data.split("|")[1])
        r = cur.execute("SELECT * FROM admins WHERE user_id=?", (tu,)).fetchone()
        if not r: return
        ps = ["p_add_stock","p_manage_stock","p_stats","p_bal","p_settings",
              "p_users","p_broadcast","p_products","p_admin_mgmt"]
        kbr = []
        for p in ps:
            st = "✅" if r[p] else "❌"
            kbr.append([ibtn(p, f"adm_perm_toggle|{tu}|{p}", emoji=st,
                             style="primary" if r[p] else "danger")])
        kbr.append([ibtn("BACK","adm_list_admins",emoji="🔙",style="primary")])
        await q.message.reply_text(f"<b>👑 PERMS — {tu}</b>", parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup(kbr)); return
    if data.startswith("adm_perm_toggle|"):
        if not is_owner(uid): return
        p = data.split("|"); tu = int(p[1]); perm = p[2]
        if perm not in ("p_add_stock","p_manage_stock","p_stats","p_bal","p_settings",
                        "p_users","p_broadcast","p_products","p_admin_mgmt"): return
        cur.execute(f"UPDATE admins SET {perm} = 1 - {perm} WHERE user_id=?", (tu,)); db.commit()
        try: await q.answer("✅ Toggled")
        except: pass
        return

    log.warning(f"Unhandled admin callback: {data}")


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from admin_panel import (
    view_admin_cat_server_select, view_admin_gmail_menu, view_admin_log_menu,
    view_admin_lzt_settings, view_admin_maintenance, view_admin_settings,
    view_admin_stock_all, view_admin_stock_menu, view_admin_tx_month, view_admin_tx_today,
    view_admin_users_list, view_cat_manage, view_userlog_menu
)
from backup import create_backup, create_full_backup_zip
from bot_manager import (
    remove_bot_by_token_prefix, start_bot_by_token_prefix, stop_bot_by_token_prefix,
    view_bot_detail, view_bot_manager
)
from broadcast import (
    bcast_btn_action_kb, bcast_btn_type_kb, bcast_color_kb, bcast_position_kb, do_broadcast,
    do_global_broadcast_full, view_global_broadcast
)
from buttons import category_select_kb, ibtn
from commands import test_rich_message
from config import DAYBREAK_OPTIONS, FAMPAY_SENDER, IMAP_PORT, IMAP_SERVER, log
from context import BOT_CONTEXTS, cur, current_bot_username, db
from database import (
    get_admins, get_manual_upi_id, get_setting, is_admin,
    get_fampay_upi_id, get_paytm_upi_id, get_paytm_mid, set_global_payment_setting, is_bot_online, is_buy1_online,
    is_buy2_online, is_buy3_online, is_gmail_verify_enabled, is_master_owner, is_owner,
    is_upi_online, set_setting, update_balance
)
from emojis import BALANCE_PREMIUM_EMOJI_ID, auto_premium, emo
from force_join import _force_join_cache, get_all_channels
from history import record_balance_history
from logs import (
    get_log_source_chat, get_log_targets, get_log_targets_full, has_user_log_channel,
    log_admin_action, log_deposit, log_purchase_public, log_stock_removed,
    log_target_change, remove_log_target, set_log_source_chat, set_user_log_channel
)
from lzt_api import clear_lzt_cache
from manual_upi import complete_manual_upi_order, reject_manual_upi_order, reshow_manual_upi_request
from osint import (
    get_osint_base_url, get_osint_docs_file_id, osint_admin_login, osint_clear_cached_token,
    view_admin_osint_settings
)
from payments import keypad_kb, process_referral_bonus
from rich_ui import (
    _edit_query_of, _tg_post, make_heading, make_paragraph, make_table, send_rich_async
)
from server2 import view_admin_s2_item, view_admin_s2_list, view_admin_s2_menu, view_admin_s2_sold
from server3 import view_admin_s3_item, view_admin_s3_menu, view_admin_s3_section
from state import get_user_lock, manual_upi_owner_state, temp_data, zip_staging
from utils import html_safe_error
from zip_upload import zip_finalize_upload
