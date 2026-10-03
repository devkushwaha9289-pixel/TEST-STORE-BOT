#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — admin_text.py
Admin text-input handler (handle_admin_text).
"""

import re
from html import escape
from telegram import InlineKeyboardMarkup
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# ============================================================
# ADMIN TEXT HANDLER
# ============================================================
async def handle_admin_text(update, context):
    msg = update.message; uid = update.effective_user.id
    text = msg.text or ""
    state = temp_data.get(uid)
    if not state: return
    act = state.get('admin_action')

    if text == "/cancel" or text.lower() == "cancel" or text == BTN_CANCEL:
        temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('❌')} Cancelled.", parse_mode="HTML",
                             reply_markup=main_reply_kb(uid)); return

    if act == 'manual_upi_set':
        v = text.strip()
        if "@" not in v:
            await msg.reply_text(f"{emo('❌')} Invalid UPI ID.", parse_mode="HTML"); return
        set_setting('manual_upi_id', v)
        temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} Manual UPI saved:\n<code>{escape(v)}</code>",
            parse_mode="HTML", reply_markup=main_reply_kb(uid))
        try: await log_admin_action(uid, "Set Manual UPI", v)
        except: pass
        return

    if act == 'osint_set_oid':
        v = text.strip()
        if not v:
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
        set_setting('osint_owner_id', v)
        osint_clear_cached_token()
        temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} Owner ID saved.", parse_mode="HTML",
            reply_markup=main_reply_kb(uid))
        try: await log_admin_action(uid, "OSINT Owner ID Set", v)
        except: pass
        try: await view_admin_osint_settings(update)
        except: pass
        return
    if act == 'osint_set_skey':
        v = text.strip()
        if not v:
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
        set_setting('osint_secret_key', v)
        osint_clear_cached_token()
        temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} Secret key saved.", parse_mode="HTML",
            reply_markup=main_reply_kb(uid))
        try: await log_admin_action(uid, "OSINT Secret Key Set", "***")
        except: pass
        try: await view_admin_osint_settings(update)
        except: pass
        return
    if act == 'osint_set_url':
        v = text.strip().rstrip('/')
        if not (v.startswith('http://') or v.startswith('https://')):
            await msg.reply_text(f"{emo('❌')} Invalid URL. Must start with http(s)://",
                parse_mode="HTML"); return
        set_setting('osint_base_url', v)
        osint_clear_cached_token()
        temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} Base URL saved.", parse_mode="HTML",
            reply_markup=main_reply_kb(uid))
        try: await log_admin_action(uid, "OSINT Base URL Set", v)
        except: pass
        try: await view_admin_osint_settings(update)
        except: pass
        return

    if act == 'zip_set_price':
        cn = state.get('zip_country')
        st = zip_staging.get(uid)
        if not st or cn not in st['country_groups']:
            await msg.reply_text(f"{emo('❌')} Session expired.", parse_mode="HTML")
            temp_data.pop(uid, None); return
        try:
            price = int(re.sub(r'[^\d]', '', text.strip()))
            if price <= 0: raise ValueError()
        except:
            await msg.reply_text(f"{emo('❌')} Invalid price.", parse_mode="HTML"); return
        st['prices'][cn] = price
        temp_data.pop(uid, None)
        await msg.reply_text(
            f"{emo('✅')} <b>{cn}</b> → <b>₹{price}</b>\n"
            f"All {len(st['country_groups'][cn])} accounts will get this price.",
            parse_mode="HTML", reply_markup=main_reply_kb(uid))
        await show_zip_price_ui(uid, context)
        return

    if act == 's2_add_phone':
        ph = text.replace(" ", "").replace("+", "")
        if not ph.isdigit():
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); temp_data.pop(uid, None); return
        cat = state.get('stock_cat', 'NORMAL ACCOUNT')
        temp_data[uid] = {'admin_action': 's2_add_otp', 'phone': ph,
                          'stock_server': 'SERVER2', 'stock_cat': cat}
        try:
            ctx = current_ctx()
            client = TelegramClient(f"{ctx.data_dir}/sessions/{ph}", API_ID, API_HASH)
            await client.connect()
            sreq = await client.send_code_request(ph)
            temp_data[uid]['phone_code_hash'] = sreq.phone_code_hash
            temp_data[uid]['client'] = client
            await msg.reply_text(f"{emo('📱')} OTP sent! Enter code:", parse_mode="HTML")
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML"); temp_data.pop(uid, None)
        return
    if act == 's2_add_otp':
        otp = text.strip()
        ph = state.get('phone'); client = state.get('client')
        cat = state.get('stock_cat', 'NORMAL ACCOUNT')
        try:
            await client.sign_in(ph, otp, phone_code_hash=state['phone_code_hash'])
            me = await client.get_me()
            cn, ci = get_country_info(getattr(me, 'phone', ph))
            year = now_ist().year - 1
            await client.disconnect()
            temp_data[uid] = {'admin_action': 's2_add_desc', 'phone': ph,
                              'c_name': cn, 'c_icon': ci, 'year': year,
                              'twofa': 'None', 'stock_server': 'SERVER2', 'stock_cat': cat}
            await msg.reply_text(f"{emo('✅')} Login OK! Send DESC (or /skip):", parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","s2_skip_desc",emoji="➖",style="primary")]]))
        except SessionPasswordNeededError:
            temp_data[uid]['admin_action'] = 's2_add_2fa'
            await msg.reply_text(f"{emo('🔐')} Enter 2FA:", parse_mode="HTML")
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML"); temp_data.pop(uid, None)
        return
    if act == 's2_add_2fa':
        ph = state.get('phone'); cat = state.get('stock_cat', 'NORMAL ACCOUNT')
        try:
            ctx = current_ctx()
            client = TelegramClient(f"{ctx.data_dir}/sessions/{ph}", API_ID, API_HASH)
            await client.connect()
            await client.sign_in(password=text.strip())
            me = await client.get_me()
            cn, ci = get_country_info(getattr(me, 'phone', ph))
            year = now_ist().year - 1
            await client.disconnect()
            temp_data[uid] = {'admin_action': 's2_add_desc', 'phone': ph,
                              'c_name': cn, 'c_icon': ci, 'year': year,
                              'twofa': text.strip(), 'stock_server': 'SERVER2', 'stock_cat': cat}
            await msg.reply_text(f"{emo('✅')} Login OK! DESC (or /skip):", parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","s2_skip_desc",emoji="➖",style="primary")]]))
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML"); temp_data.pop(uid, None)
        return
    if act == 's2_add_desc':
        desc = text.strip()[:200]
        st = temp_data[uid]
        st['s2_desc'] = desc
        st['admin_action'] = 's2_add_price'
        await msg.reply_text(
            f"<b>{emo('💰')} ENTER PRICE</b>\n\n"
            f"{emo('📱')} Phone: <code>{st['phone']}</code>\n"
            f"{emo('🎯')} Category: <code>{st.get('stock_cat')}</code>\n"
            f"{emo('📝')} Desc: <code>{(desc or '—')[:40]}</code>\n\n"
            f"{emo('👉')} Send price in ₹:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return
    if act == 's2_add_price':
        try:
            price = int(re.sub(r'[^\d]', '', text.strip()))
            if price <= 0: raise ValueError()
        except:
            await msg.reply_text(f"{emo('❌')} Invalid price. Send number.", parse_mode="HTML"); return
        st = temp_data[uid]
        try:
            cur.execute("""INSERT OR REPLACE INTO stock
                (phone, session_file, country_name, country_icon, account_year, category,
                 server, price, available, twofa, description)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (st['phone'], f"sessions/{st['phone']}.session", st['c_name'], st['c_icon'],
                 st['year'], st['stock_cat'], 'SERVER2', price, 1, st.get('twofa','None'),
                 st.get('s2_desc','')))
            db.commit()
            await msg.reply_text(
                f"{emo('✅')} <b>ADDED TO SERVER 2!</b>\n\n"
                f"{emo('📱')} Phone: <code>+{st['phone']}</code>\n"
                f"{emo('🌎')} Country: {st['c_icon']} {st['c_name']}\n"
                f"{emo('🎯')} Category: {st['stock_cat']}\n"
                f"{emo('💰')} Price: ₹{price}",
                parse_mode="HTML", reply_markup=main_reply_kb(uid))
            await log_new_stock(uid, st['phone'], f"{st['c_icon']} {st['c_name']}",
                                st['stock_cat'], price, 'SERVER2', st.get('s2_desc',''))
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
        temp_data.pop(uid, None); return
    if act.startswith('s2_edit_'):
        f = act.replace('s2_edit_', ''); ph = state.get('stock_phone')
        if f in ('price','available'):
            try: v = int(text.strip())
            except:
                await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
            cur.execute(f"UPDATE stock SET {f}=? WHERE phone=?", (v, ph)); db.commit()
            await log_stock_edited(uid, ph, {f: v})
        else:
            cur.execute(f"UPDATE stock SET {f}=? WHERE phone=?", (text.strip(), ph)); db.commit()
            await log_stock_edited(uid, ph, {f: text.strip()})
        await msg.reply_text(f"{emo('✅')} Updated.", parse_mode="HTML")
        temp_data.pop(uid, None); return

    if act == 's3_add_name':
        state['s3_name'] = text.strip()[:120]
        state['admin_action'] = 's3_add_price'
        await msg.reply_text(f"{emo('💰')} Send price (₹):", parse_mode="HTML"); return
    if act == 's3_add_price':
        try:
            state['s3_price'] = int(re.sub(r'[^\d]', '', text.strip()))
            if state.get('s3_section') == 'OSINT APIS':
                state['admin_action'] = 's3_add_endpoint'
                await msg.reply_text(
                    f"<b>{emo('🔗')} Send API endpoint</b>\n\n"
                    f"Example: <code>/pan</code> or <code>/voter_info</code>\n"
                    f"Must start with <code>/</code>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
            else:
                state['admin_action'] = 's3_add_link'
                await msg.reply_text(f"{emo('🔗')} Send link (URL or '-'):", parse_mode="HTML")
        except:
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML")
        return
    if act == 's3_add_endpoint':
        ep = text.strip()
        if not ep.startswith('/'):
            ep = '/' + ep
        if not re.match(r'^/[A-Za-z0-9_]+$', ep):
            await msg.reply_text(f"{emo('❌')} Invalid endpoint. Format: /pan",
                parse_mode="HTML"); return
        state['s3_endpoint'] = ep
        state['admin_action'] = 's3_add_desc'
        await msg.reply_text(f"{emo('📝')} Description (or /skip):", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","s3_skip_desc",emoji="➖",style="primary")]]))
        return
    if act == 's3_add_link':
        link = text.strip()
        if link == "-": link = ""
        if link and not link.startswith("http"):
            await msg.reply_text(f"{emo('❌')} Invalid URL.", parse_mode="HTML"); return
        state['s3_link'] = link
        state['admin_action'] = 's3_add_desc'
        await msg.reply_text(f"{emo('📝')} Description (or /skip):", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","s3_skip_desc",emoji="➖",style="primary")]]))
        return
    if act == 's3_add_desc':
        desc = text.strip()[:200] if text.strip() != "/skip" else ""
        sec = state.get('s3_section', 'PANNELS')
        name = state.get('s3_name', 'Item'); price = state.get('s3_price', 500)
        link = state.get('s3_link', '')
        endpoint = state.get('s3_endpoint', '')
        try:
            cur.execute("""INSERT INTO file_products
                (section, name, description, price, file_link, api_endpoint, active, item_code)
                VALUES (?,?,?,?,?,?,1,?)""",
                (sec, name, desc, price, link, endpoint, generate_item_code()))
            db.commit()
            extra = f"\n🔗 Endpoint: <code>{escape(endpoint)}</code>" if endpoint else ""
            await msg.reply_text(f"{emo('✅')} <b>ADDED to {sec}!</b>\n📦 {name}\n💰 ₹{price}{extra}",
                                  parse_mode="HTML")
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
        temp_data.pop(uid, None); return
    if act.startswith('s3_edit_'):
        f = act.replace('s3_edit_', ''); pid = state.get('s3_id')
        if f == 'price':
            try: v = int(re.sub(r'[^\d]', '', text.strip()))
            except:
                await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
            cur.execute("UPDATE file_products SET price=? WHERE id=?", (v, pid)); db.commit()
        elif f == 'api_endpoint':
            ep = text.strip()
            if not ep.startswith('/'): ep = '/' + ep
            if not re.match(r'^/[A-Za-z0-9_]+$', ep):
                await msg.reply_text(f"{emo('❌')} Invalid endpoint.", parse_mode="HTML"); return
            cur.execute("UPDATE file_products SET api_endpoint=? WHERE id=?", (ep, pid)); db.commit()
        else:
            cur.execute(f"UPDATE file_products SET {f}=? WHERE id=?", (text.strip(), pid)); db.commit()
        await msg.reply_text(f"{emo('✅')} Updated.", parse_mode="HTML")
        temp_data.pop(uid, None); return

    if act == 'adm_bot_add_token': await handle_add_bot_token(update, context, text); return
    if act == 'adm_bot_add_owner': await handle_add_bot_owner(update, context, text); return
    if act == 'userlog_set':
        try: cid = int(re.sub(r'[^\-\d]', '', text.strip()))
        except:
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
        set_user_log_channel(cid); temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} Set <code>{cid}</code>", parse_mode="HTML",
                              reply_markup=main_reply_kb(uid))
        try: await log_target_change(uid, "User Log Set", cid)
        except: pass
        return
    if act == 'gmail_set_email':
        ea = text.strip()
        if "@" not in ea or "." not in ea:
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
        set_setting('gmail_email', ea); temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} {escape(ea)}", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]))
        await log_admin_action(uid, "FamPay Email Set", ea); return
    if act == 'gmail_set_upi':
        upi = text.strip().replace(" ", "")
        if "@" not in upi:
            await msg.reply_text(f"{emo('❌')} Invalid UPI.", parse_mode="HTML"); return
        set_setting('fampay_upi_id', upi)
        try: set_global_payment_setting('fampay_upi_id', upi)
        except Exception as e: log.warning("global fampay upi save: %s", e)
        temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} {escape(upi)}", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]))
        await log_admin_action(uid, "Auto UPI Set", upi); return
    if act == 'paytm_set_upi':
        upi = re.sub(r'\s+', '', text.strip())
        if not re.fullmatch(r'[A-Za-z0-9._\-]{2,}@[A-Za-z0-9._\-]{2,}', upi):
            await msg.reply_text(
                f"{emo('❌')} Invalid UPI ID. Example: <code>name@paytm</code>\n"
                f"Send again or /cancel.", parse_mode="HTML"); return
        set_setting('paytm_upi_id', upi)
        try: set_global_payment_setting('paytm_upi_id', upi)
        except Exception as e: log.warning("global paytm upi save: %s", e)
        temp_data.pop(uid, None)
        await msg.reply_text(
            f"{emo('✅')} Paytm UPI saved:\n<code>{escape(upi)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]))
        try: await log_admin_action(uid, "Paytm UPI Set", upi)
        except Exception: pass
        return
    if act == 'paytm_set_mid':
        mid = re.sub(r'\s+', '', text.strip())
        if not re.fullmatch(r'[A-Za-z0-9_\-]{6,40}', mid):
            await msg.reply_text(
                f"{emo('❌')} Invalid MID. Send the Paytm Merchant ID only "
                f"(letters/digits, no spaces).\nSend again or /cancel.", parse_mode="HTML"); return
        set_setting('paytm_mid', mid)
        try: set_global_payment_setting('paytm_mid', mid)
        except Exception as e: log.warning("global paytm mid save: %s", e)
        temp_data.pop(uid, None)
        await msg.reply_text(
            f"{emo('✅')} Paytm MID saved:\n<code>{escape(mid)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]))
        try: await log_admin_action(uid, "Paytm MID Set", mid)
        except Exception: pass
        return
    if act == 'gmail_set_pw':
        pw = text.strip().replace(" ", "")
        if len(pw) < 8:
            await msg.reply_text(f"{emo('❌')} Too short.", parse_mode="HTML"); return
        set_setting('gmail_app_password', pw); temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} Saved.", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("BACK","adm_gmail_menu",emoji="🔙",style="primary")]]))
        await log_admin_action(uid, "Password Set", "***"); return
    if act == 'lzt_set_token':
        ti = text.strip()
        if ti.lower() == "remove":
            cur.execute("DELETE FROM settings WHERE key='lzt_token'"); db.commit()
            reset_lzt_missing_logged()
            await msg.reply_text(f"{emo('✅')} Removed.", parse_mode="HTML")
        else:
            set_setting('lzt_token', ti.replace("Bearer ", "").strip())
            reset_lzt_missing_logged()
            await msg.reply_text(f"{emo('✅')} Saved.", parse_mode="HTML")
        temp_data.pop(uid, None); return
    if act == 'lzt_set_markup':
        try:
            v = int(text.strip())
            if v < 0: raise ValueError()
            set_setting('lzt_global_markup', str(v)); clear_lzt_cache()
            await msg.reply_text(f"{emo('✅')} {v}%", parse_mode="HTML")
        except: await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
        temp_data.pop(uid, None); return
    if act in ('lzt_set_default_daybreak', 'edit_default_daybreak'):
        try:
            v = int(text.strip())
            if v not in DAYBREAK_OPTIONS: raise ValueError()
            set_setting("lzt_default_daybreak", str(v))
            await msg.reply_text(f"{emo('✅')} {v}d", parse_mode="HTML")
            await log_admin_action(uid, "Set Daybreak", str(v))
        except: await msg.reply_text(f"{emo('❌')} Use 1/7/14/30.", parse_mode="HTML"); return
        temp_data.pop(uid, None); return
    if act == 'lzt_set_cmark':
        p = text.strip().split()
        if len(p) != 2:
            await msg.reply_text(f"{emo('❌')} Format: country percent", parse_mode="HTML"); return
        c, ps = p[0], p[1]
        try: pct = int(ps)
        except:
            await msg.reply_text(f"{emo('❌')} Integer only.", parse_mode="HTML"); return
        if pct == 0:
            cur.execute("DELETE FROM lzt_settings WHERE LOWER(country)=LOWER(?)", (c,))
        else:
            cur.execute("INSERT OR REPLACE INTO lzt_settings (country, markup_percent) VALUES (?,?)", (c, pct))
        db.commit(); clear_lzt_cache()
        await msg.reply_text(f"{emo('✅')} Done.", parse_mode="HTML")
        temp_data.pop(uid, None); return
    if act == 'log_src_set':
        try: cid = int(re.sub(r'[^\-\d]', '', text.strip()))
        except:
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
        set_log_source_chat(cid); temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} Set.", parse_mode="HTML", reply_markup=main_reply_kb(uid))
        await log_target_change(uid, "Source Set", cid); return
    if act == 'log_add_id':
        try: cid = int(re.sub(r'[^\-\d]', '', text.strip()))
        except:
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
        if is_log_target(cid):
            await msg.reply_text(f"{emo('⚠️')} Already a target.", parse_mode="HTML")
            temp_data.pop(uid, None); return
        state['log_new_chat_id'] = cid
        state['admin_action'] = 'log_add_title'
        await msg.reply_text(f"{emo('📝')} Send title (or /skip):", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","log_add_skip",emoji="➖",style="primary")],
                                                [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return
    if act == 'log_add_title':
        cid = state.get('log_new_chat_id')
        title = text.strip()[:60] if text.strip() != "/skip" else f"Target {cid}"
        kind = "group" if str(cid).startswith("-") and not str(cid).startswith("-100") else "channel"
        add_log_target(cid, title, kind); temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} Added!", parse_mode="HTML", reply_markup=main_reply_kb(uid))
        await log_target_change(uid, "Added", cid, title); return
    if act == 'bal_add': await process_admin_balance(update, context, 'add', text); return
    if act == 'bal_reduce': await process_admin_balance(update, context, 'reduce', text); return
    if act == 'bal_set': await process_admin_balance(update, context, 'set', text); return
    if act == 'cat_add_name':
        srv = state.get('cat_server', 'SERVER2')
        raw = text.strip(); name = auto_premium(raw)[:200]
        em = re.findall(r'<tg-emoji[^>]*>([^<]+)</tg-emoji>|([\U0001F300-\U0001FAFF\u2600-\u26FF])', raw)
        ce_ = "⭐"
        if em:
            for m in em:
                e = m[0] or m[1]
                if e: ce_ = e; break
        try:
            cur.execute("INSERT INTO custom_categories (server, name, emoji, sort_order, active) VALUES (?,?,?,?,1)",
                        (srv, name, ce_, 999)); db.commit()
            temp_data.pop(uid, None)
            await msg.reply_text(f"{emo('✅')} Added to {srv}", parse_mode="HTML")
            await log_admin_action(uid, "Add Category", f"Server={srv}")
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML"); temp_data.pop(uid, None)
        return
    if act == 'cat_edit_name':
        cid = state.get('cat_id')
        if text.strip() and text != "/skip":
            cur.execute("UPDATE custom_categories SET name=? WHERE id=?",
                        (auto_premium(text.strip())[:200], cid)); db.commit()
        state['admin_action'] = 'cat_edit_emoji'
        await msg.reply_text(f"{emo('😀')} Send EMOJI (or /skip):", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","cat_edit_skip_emoji",emoji="➖",style="primary")]]))
        return
    if act == 'cat_edit_emoji':
        cid = state.get('cat_id')
        if text.strip() and text != "/skip":
            cur.execute("UPDATE custom_categories SET emoji=? WHERE id=?", (text.strip()[:4], cid)); db.commit()
        temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} Done.", parse_mode="HTML"); return
    if act == 'ch_add_id':
        v = text.strip()
        try:
            cid_int = int(re.sub(r'[^\-\d]', '', v))
            state['ch_new_id'] = str(cid_int)
        except:
            state['ch_new_id'] = v
        state['admin_action'] = 'ch_add_link'
        await msg.reply_text(f"{emo('2️⃣')} Send LINK:", parse_mode="HTML"); return
    if act == 'ch_add_link':
        link = text.strip()
        if not link.startswith("http"): link = "https://t.me/" + link.lstrip("@")
        cid = state.get('ch_new_id', '')
        cur.execute("INSERT OR REPLACE INTO channels (channel_id, channel_link) VALUES (?,?)",
                    (cid, link)); db.commit()
        _force_join_cache.clear()
        temp_data.pop(uid, None)
        await msg.reply_text(
            auto_premium(f"✅ <b>Channel added</b>\n\n🆔 <code>{escape(cid)}</code>\n🔗 {escape(link)}\n\n"
                         f"⚠️ Make sure this bot is <b>admin</b> in this channel so force-join checks work."),
            parse_mode="HTML", reply_markup=main_reply_kb(uid)); return
    if act == 'bc_wait_msg':
        state['bcast_text'] = auto_premium(msg.text or "")
        state['admin_action'] = 'bc_media_menu'
        await msg.reply_text(f"{emo('✅')} Saved. Add media?", parse_mode="HTML",
                              reply_markup=bcast_media_menu_kb()); return
    if act == 'bc_btn_name':
        state['bcast_temp_name'] = text.strip()[:64]
        if state.get('bcast_temp_type') == 'rich':
            state['admin_action'] = 'bc_btn_emoji_id'
            await msg.reply_text(
                f"<b>{emo('🎨')} Send PREMIUM CUSTOM EMOJI ID</b>\n\n"
                f"Example: <code>5961009436813167995</code>\n\nSend <code>0</code> for none.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [ibtn("NO EMOJI","bc_btn_no_emoji",emoji="➖",style="primary")],
                    [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
            return
        state['admin_action'] = 'bc_btn_link'
        await msg.reply_text(f"{emo('🔗')} Send LINK:", parse_mode="HTML"); return
    if act == 'bc_btn_emoji_id':
        eid = text.strip()
        if eid == "0":
            state['bcast_temp_emoji_id'] = None
            state['bcast_temp_alt_emoji'] = None
            state['admin_action'] = 'bc_btn_link'
            await msg.reply_text(f"{emo('🔗')} Send LINK:", parse_mode="HTML"); return
        if not (eid.isdigit() and len(eid) >= 5):
            await msg.reply_text(f"{emo('❌')} Invalid ID.", parse_mode="HTML"); return
        state['bcast_temp_emoji_id'] = eid
        state['admin_action'] = 'bc_btn_alt_emoji'
        await msg.reply_text(f"{emo('🙂')} Fallback emoji (e.g. 🔥):", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("DEFAULT 🔥","bc_btn_default_emoji",emoji="🔥",style="primary")]]))
        return
    if act == 'bc_btn_alt_emoji':
        state['bcast_temp_alt_emoji'] = text.strip()[:4] or "🔥"
        state['admin_action'] = 'bc_btn_link'
        await msg.reply_text(f"{emo('🔗')} Send LINK:", parse_mode="HTML"); return
    if act == 'bc_btn_link':
        link = text.strip()
        if not (link.startswith("http") or link.startswith("tg://")):
            await msg.reply_text(f"{emo('❌')} Invalid URL.", parse_mode="HTML"); return
        btn = {'name': state.get('bcast_temp_name','Button'), 'url': link,
               'style': state.get('bcast_temp_color','primary'),
               'type': state.get('bcast_temp_type','inline')}
        if btn['type'] == 'rich':
            btn['emoji_id'] = state.get('bcast_temp_emoji_id')
            btn['alternative_emoji'] = state.get('bcast_temp_alt_emoji') or '🔥'
        state.setdefault('bcast_buttons', []).append(btn)
        state['admin_action'] = 'bc_btn_menu'
        await msg.reply_text(f"{emo('✅')} Button added ({len(state['bcast_buttons'])}/6)",
                              parse_mode="HTML", reply_markup=bcast_btn_action_kb()); return
    if act == 'redeem':
        code = text.strip().upper()
        r = cur.execute("SELECT amount, max_uses, used, active FROM coupons WHERE code=?", (code,)).fetchone()
        if not r or not r[3] or r[2] >= r[1]:
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML",
                                 reply_markup=main_reply_kb(uid))
            temp_data.pop(uid, None); return
        cur.execute("UPDATE coupons SET used=used+1 WHERE code=?", (code,))
        r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        old = r2["balance"] if r2 else 0
        update_balance(uid, r[0]); db.commit()
        record_balance_history(uid, r[0], "coupon", "coupon", code, old, old + r[0])
        await msg.reply_text(f"{emo('🎉')} +₹{r[0]}", parse_mode="HTML",
                              reply_markup=main_reply_kb(uid))
        await log_coupon_used(uid, code, r[0])
        temp_data.pop(uid, None); return
    if act in ('stock_edit_phone', 'stock_del_phone'):
        ph = re.sub(r'[^\d]', '', text)
        if not ph:
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
        r = cur.execute("SELECT * FROM stock WHERE phone=?", (ph,)).fetchone()
        if not r:
            await msg.reply_text(f"{emo('❌')} Not found.", parse_mode="HTML")
            temp_data.pop(uid, None); return
        if act == 'stock_edit_phone':
            kb = InlineKeyboardMarkup([
                [ibtn("PRICE", f"stock_edit_field|price|{ph}", emoji="💰", style="primary")],
                [ibtn("CATEGORY", f"stock_edit_field|category|{ph}", emoji="🎯", style="primary")],
                [ibtn("SERVER", f"stock_edit_field|server|{ph}", emoji="🖥️", style="primary")],
                [ibtn("AVAILABLE", f"stock_edit_field|available|{ph}", emoji="📱", style="primary")],
                [ibtn("2FA", f"stock_edit_field|twofa|{ph}", emoji="🔐", style="primary")],
                [ibtn("DESC", f"stock_edit_field|description|{ph}", emoji="📝", style="primary")],
                [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])
            await msg.reply_text(f"<b>{emo('🔧')} EDIT</b>\n<code>{ph}</code>",
                                  parse_mode="HTML", reply_markup=kb)
        else:
            kb = InlineKeyboardMarkup([
                [ibtn("CONFIRM DELETE", f"stock_del_confirm|{ph}", emoji="🗑️", style="danger")],
                [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])
            await msg.reply_text(f"<b>⚠️ DELETE {ph}?</b>", parse_mode="HTML", reply_markup=kb)
        temp_data.pop(uid, None); return
    if act.startswith('stock_edit_'):
        f = act.replace('stock_edit_', ''); ph = state.get('stock_phone')
        if f in ('price','available'):
            try: v = int(text.strip())
            except:
                await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
            cur.execute(f"UPDATE stock SET {f}=? WHERE phone=?", (v, ph)); db.commit()
            await log_stock_edited(uid, ph, {f: v})
        else:
            cur.execute(f"UPDATE stock SET {f}=? WHERE phone=?", (text.strip(), ph)); db.commit()
            await log_stock_edited(uid, ph, {f: text.strip()})
        await msg.reply_text(f"{emo('✅')} Updated.", parse_mode="HTML")
        temp_data.pop(uid, None); return
    if act == 'user_info':
        try: await show_user_info_by_id(update, int(text.strip()))
        except: await msg.reply_text(f"{emo('❌')} Invalid", parse_mode="HTML")
        temp_data.pop(uid, None); return
    if act in ('disc_give','disc_remove','adm_ban_user','adm_unban_user'):
        try:
            if act == 'disc_give':
                tu, p = map(int, text.split())
                cur.execute("UPDATE users SET discount=? WHERE user_id=?", (p, tu))
                await msg.reply_text(f"{emo('✅')} {p}% for <code>{tu}</code>", parse_mode="HTML")
            elif act == 'disc_remove':
                tu = int(text.strip())
                cur.execute("UPDATE users SET discount=0 WHERE user_id=?", (tu,))
                await msg.reply_text(f"{emo('✅')} Removed.", parse_mode="HTML")
            elif act == 'adm_ban_user':
                tu = int(text.strip())
                cur.execute("UPDATE users SET banned=1 WHERE user_id=?", (tu,))
                await log_user_banned(uid, tu, banned=True)
                await msg.reply_text(f"{emo('🚫')} Banned <code>{tu}</code>", parse_mode="HTML")
            elif act == 'adm_unban_user':
                tu = int(text.strip())
                cur.execute("UPDATE users SET banned=0 WHERE user_id=?", (tu,))
                await log_user_banned(uid, tu, banned=False)
                await msg.reply_text(f"{emo('✅')} Unbanned <code>{tu}</code>", parse_mode="HTML")
            db.commit()
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
        temp_data.pop(uid, None); return
    if act in ('adm_usdtrate','edit_transferfee','edit_mindeposit','edit_c1','edit_c2',
               'edit_support','edit_updateurl','edit_maintimg'):
        try:
            if act == 'adm_usdtrate':
                set_setting('usdt_rate', float(text.strip()))
                await msg.reply_text(f"{emo('✅')} ₹{text.strip()}", parse_mode="HTML")
            elif act == 'edit_transferfee':
                set_setting('transfer_fee', int(text.strip()))
                await msg.reply_text(f"{emo('✅')} {text.strip()}%", parse_mode="HTML")
            elif act == 'edit_mindeposit':
                v = int(re.sub(r'[^\d]', '', text.strip()))
                if v < 1: raise ValueError("must be >= 1")
                set_setting('min_deposit', v)
                await msg.reply_text(f"{emo('✅')} ₹{v}", parse_mode="HTML")
                await log_admin_action(uid, "Set Min Deposit", f"₹{v}")
            elif act == 'edit_c1':
                set_setting('contact_1', text.strip())
                await msg.reply_text(f"{emo('✅')}", parse_mode="HTML")
            elif act == 'edit_c2':
                set_setting('contact_2', text.strip())
                await msg.reply_text(f"{emo('✅')}", parse_mode="HTML")
            elif act == 'edit_support':
                set_setting('support_url', text.strip())
                await msg.reply_text(f"{emo('✅')}", parse_mode="HTML")
            elif act == 'edit_updateurl':
                set_setting('update_url', text.strip())
                await msg.reply_text(f"{emo('✅')}", parse_mode="HTML")
            elif act == 'edit_maintimg':
                set_setting('maintenance_image', text.strip())
                await msg.reply_text(f"{emo('✅')}", parse_mode="HTML")
            await log_admin_action(uid, act, text[:60])
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
        temp_data.pop(uid, None); return
    if act == 'adm_addcoupon':
        try:
            parts = text.split()
            code = parts[0].upper(); amt = int(parts[1]); mx = int(parts[2]) if len(parts) > 2 else 1
            cur.execute("INSERT OR REPLACE INTO coupons (code,amount,max_uses,used,active) VALUES (?,?,?,0,1)",
                        (code, amt, mx)); db.commit()
            await msg.reply_text(f"{emo('✅')} '{code}' added!", parse_mode="HTML")
        except: await msg.reply_text(f"{emo('❌')} Format: CODE amount max_uses", parse_mode="HTML")
        temp_data.pop(uid, None); return
    if act == 'add_admin_id':
        if not is_owner(uid): return
        try:
            tu = int(text.strip())
            cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (tu,)); db.commit()
            await msg.reply_text(f"{emo('✅')} Admin <code>{tu}</code>", parse_mode="HTML")
        except: await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML")
        temp_data.pop(uid, None); return

    if act == 'addstock_phone':
        ph = text.replace(" ", "").replace("+", "")
        if not ph.isdigit():
            await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); temp_data.pop(uid, None); return
        sc = state.get('stock_server','SERVER2'); cat = state.get('stock_cat','NORMAL ACCOUNT')
        temp_data[uid] = {'admin_action': 'addstock_otp', 'phone': ph,
                          'stock_server': sc, 'stock_cat': cat}
        try:
            ctx = current_ctx()
            client = TelegramClient(f"{ctx.data_dir}/sessions/{ph}", API_ID, API_HASH)
            await client.connect()
            sreq = await client.send_code_request(ph)
            temp_data[uid]['phone_code_hash'] = sreq.phone_code_hash
            temp_data[uid]['client'] = client
            await msg.reply_text(f"{emo('📱')} OTP sent! Enter code:", parse_mode="HTML")
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML"); temp_data.pop(uid, None)
        return
    if act == 'addstock_otp':
        otp = text.strip()
        ph = state.get('phone'); client = state.get('client')
        sc = state.get('stock_server','SERVER2'); cat = state.get('stock_cat','NORMAL ACCOUNT')
        try:
            await client.sign_in(ph, otp, phone_code_hash=state['phone_code_hash'])
            me = await client.get_me()
            cn, ci = get_country_info(getattr(me, 'phone', ph))
            year = now_ist().year - 1
            await client.disconnect()
            temp_data[uid] = {'admin_action': 'addstock_desc', 'phone': ph,
                              'c_name': cn, 'c_icon': ci, 'year': year,
                              'twofa': 'None', 'stock_server': sc, 'stock_cat': cat}
            await msg.reply_text(f"{emo('✅')} Login OK! DESC (or /skip):", parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","addstock_skip_desc",emoji="➖",style="primary")]]))
        except SessionPasswordNeededError:
            temp_data[uid]['admin_action'] = 'addstock_2fa'
            await msg.reply_text(f"{emo('🔐')} Enter 2FA:", parse_mode="HTML")
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML"); temp_data.pop(uid, None)
        return
    if act == 'addstock_2fa':
        ph = state.get('phone'); sc = state.get('stock_server','SERVER2')
        cat = state.get('stock_cat','NORMAL ACCOUNT')
        try:
            ctx = current_ctx()
            client = TelegramClient(f"{ctx.data_dir}/sessions/{ph}", API_ID, API_HASH)
            await client.connect()
            await client.sign_in(password=text.strip())
            me = await client.get_me()
            cn, ci = get_country_info(getattr(me, 'phone', ph))
            year = now_ist().year - 1
            await client.disconnect()
            temp_data[uid] = {'admin_action': 'addstock_desc', 'phone': ph,
                              'c_name': cn, 'c_icon': ci, 'year': year,
                              'twofa': text.strip(), 'stock_server': sc, 'stock_cat': cat}
            await msg.reply_text(f"{emo('✅')} Login OK! DESC (or /skip):", parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("SKIP","addstock_skip_desc",emoji="➖",style="primary")]]))
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML"); temp_data.pop(uid, None)
        return
    if act == 'addstock_desc':
        desc = text.strip()[:200]
        st = temp_data[uid]
        st['s2_desc'] = desc
        st['admin_action'] = 'addstock_price'
        await msg.reply_text(
            f"<b>{emo('💰')} ENTER PRICE</b>\n\n"
            f"{emo('📱')} Phone: <code>{st['phone']}</code>\n"
            f"{emo('🎯')} Category: <code>{st.get('stock_cat')}</code>\n"
            f"{emo('🖥️')} Server: <code>{st.get('stock_server')}</code>\n\n"
            f"{emo('👉')} Send price in ₹:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
        return
    if act == 'addstock_price':
        try:
            price = int(re.sub(r'[^\d]', '', text.strip()))
            if price <= 0: raise ValueError()
        except:
            await msg.reply_text(f"{emo('❌')} Invalid price. Send number.", parse_mode="HTML"); return
        st = temp_data[uid]
        try:
            cur.execute("""INSERT OR REPLACE INTO stock
                (phone, session_file, country_name, country_icon, account_year, category,
                 server, price, available, twofa, description)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (st['phone'], f"sessions/{st['phone']}.session", st['c_name'], st['c_icon'],
                 st['year'], st['stock_cat'], st['stock_server'], price, 1,
                 st.get('twofa','None'), st.get('s2_desc','')))
            db.commit()
            await msg.reply_text(
                f"{emo('✅')} <b>ADDED!</b>\n\n"
                f"{emo('📱')} +{st['phone']}\n"
                f"{emo('💰')} ₹{price}\n"
                f"{emo('🖥️')} {st['stock_server']}",
                parse_mode="HTML", reply_markup=main_reply_kb(uid))
            await log_new_stock(uid, st['phone'], f"{st['c_icon']} {st['c_name']}",
                                st['stock_cat'], price, st['stock_server'], st.get('s2_desc',''))
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
        temp_data.pop(uid, None); return

    log.warning(f"Unhandled admin text act: {act}")


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from admin_panel import process_admin_balance, show_user_info_by_id
from bot_manager import handle_add_bot_owner, handle_add_bot_token
from broadcast import bcast_btn_action_kb, bcast_media_menu_kb
from buttons import BTN_CANCEL, ibtn, main_reply_kb
from config import API_HASH, API_ID, DAYBREAK_OPTIONS, log, now_ist
from context import cur, current_ctx, db
from countries import get_country_info
from database import is_owner, set_global_payment_setting, set_setting, update_balance
from emojis import auto_premium, emo
from force_join import _force_join_cache
from history import record_balance_history
from logs import (
    add_log_target, is_log_target, log_admin_action, log_coupon_used, log_new_stock,
    log_stock_edited, log_target_change, log_user_banned, set_log_source_chat,
    set_user_log_channel
)
from lzt_api import clear_lzt_cache, reset_lzt_missing_logged
from osint import osint_clear_cached_token, view_admin_osint_settings
from state import temp_data, zip_staging
from utils import generate_item_code, html_safe_error
from zip_upload import show_zip_price_ui
