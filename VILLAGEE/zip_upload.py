#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — zip_upload.py
ZIP session upload staging, document handler and Telethon ZIP import.
"""

import os, json, time, shutil, asyncio, zipfile, traceback
from html import escape
from telegram import InlineKeyboardMarkup
from telethon import TelegramClient

# ============================================================
# ZIP staging helpers
# ============================================================
async def show_zip_price_ui(chat_id, context, edit_msg_id=None):
    st = zip_staging.get(chat_id)
    if not st: return
    cg = st['country_groups']; prices = st['prices']
    total = len(st['accounts'])
    rows = [["🌎 COUNTRY","📦 COUNT","💰 PRICE"]]
    buttons = []
    for cn in sorted(cg.keys()):
        accounts = cg[cn]
        pr = prices.get(cn)
        pr_disp = f"₹{pr}" if pr else "❌ NOT SET"
        rows.append([f"{accounts[0]['c_icon']} {cn}", str(len(accounts)), pr_disp])
        style = "success" if pr else "primary"
        emoji = "✏️" if pr else "💰"
        buttons.append([ibtn(
            f"{accounts[0]['c_icon']} {cn} ({len(accounts)}) — {pr_disp}",
            f"zip_price_set|{cn}", emoji=emoji, style=style)])
    all_set = all(cn in prices for cn in cg.keys())
    if all_set:
        buttons.append([ibtn("✅ UPLOAD ALL", "zip_upload_all", emoji="✅", style="success")])
    buttons.append([ibtn("❌ CANCEL", "zip_cancel", emoji="❌", style="danger")])
    blocks = [
        make_heading("📦 ZIP UPLOAD — SET COUNTRY PRICES", 2),
        make_paragraph(
            f"🎯 Category: {st['category']}\n"
            f"🖥️ Server: {st['server']}\n"
            f"📦 Total: {total} accounts\n"
            f"🌎 Countries: {len(cg)}"),
        make_table(rows),
    ]
    if all_set:
        blocks.append(make_paragraph("✅ All prices set! Click UPLOAD ALL to save."))
    else:
        blocks.append(make_paragraph(
            "💰 Tap a country to set its price.\n"
            "All accounts of same country get same price."))
    kb = InlineKeyboardMarkup(buttons)
    fb = f"📦 ZIP — {total} accounts | {len(cg)} countries"
    if edit_msg_id:
        try:
            await _tg_post("editMessageText", {
                "chat_id": chat_id, "message_id": edit_msg_id,
                "text": fb, "parse_mode": "HTML", "reply_markup": kb.to_dict()})
            return
        except: pass
    try:
        await send_rich_async(chat_id, blocks, reply_markup=kb.to_dict(), fallback_text=fb)
    except Exception as e:
        log.error(f"show_zip_price_ui: {e}")

async def zip_finalize_upload(uid, context, q):
    st = zip_staging.get(uid)
    if not st:
        try: await q.answer("Session expired.", show_alert=True)
        except: pass
        return
    prices = st['prices']; cg = st['country_groups']
    missing = [cn for cn in cg.keys() if cn not in prices]
    if missing:
        try: await q.answer(f"Set price for: {', '.join(missing[:3])}", show_alert=True)
        except: pass
        return
    try: await q.answer("⏳ Uploading...")
    except: pass
    added = 0
    for acc in st['accounts']:
        cn = acc['c_name']
        price = int(prices.get(cn, DEFAULT_STOCK_PRICE))
        try:
            cur.execute("""INSERT OR REPLACE INTO stock
                (phone, session_file, country_name, country_icon, account_year, category,
                 server, price, available, twofa, description)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (acc['phone'], acc['session_file'], acc['c_name'], acc['c_icon'],
                 acc['year'], st['category'], st['server'], price, 1, "None", ""))
            added += 1
        except Exception as e:
            log.warning(f"zip insert {acc['phone']}: {e}")
    db.commit()
    for cn, accounts in cg.items():
        try:
            await log_new_stock(
                uid,
                f"{len(accounts)} accounts",
                f"{accounts[0]['c_icon']} {cn}",
                st['category'], int(prices[cn]), st['server'],
                f"ZIP bulk upload")
        except Exception as e:
            log.warning(f"zip log_new_stock: {e}")
    total_countries = len(cg)
    zip_staging.pop(uid, None)
    try:
        await q.message.reply_text(
            f"{emo('✅')} <b>ZIP UPLOAD COMPLETE!</b>\n\n"
            f"{emo('📦')} Added: {added}\n"
            f"{emo('🌎')} Countries: {total_countries}\n"
            f"{emo('🎯')} Category: {st['category']}",
            parse_mode="HTML", reply_markup=main_reply_kb(uid))
    except: pass


# ============================================================
# DOCUMENT HANDLER
# ============================================================
async def handle_document(update, context):
    msg = update.message; uid = update.effective_user.id
    if uid not in temp_data: return
    act = temp_data[uid].get('admin_action')

    if act in ('bc_wait_msg', 'bc_wait_file'):
        try: _cap = msg.caption_html or msg.caption or ""
        except: _cap = msg.caption or ""
        if _cap.strip() or act == 'bc_wait_msg':
            temp_data[uid]['bcast_text'] = auto_premium(_cap)
        temp_data[uid]['bcast_media_type'] = 'document'
        temp_data[uid]['bcast_media_id'] = msg.document.file_id
        temp_data[uid]['admin_action'] = 'bc_btn_menu'
        from broadcast import bcast_btn_action_kb
        await msg.reply_text(f"{emo('✅')} File attached: <code>{(msg.document.file_name or 'file')[:60]}</code>",
                             parse_mode="HTML", reply_markup=bcast_btn_action_kb())
        return

    if act == 'full_restore_wait':
        if not is_master_owner(uid):
            return
        fname = (msg.document.file_name or "").lower()
        if not fname.endswith(".zip"):
            await msg.reply_text(f"{emo('❌')} Send a ZIP file (full_backup_*.zip).",
                                  parse_mode="HTML"); return
        temp_data.pop(uid, None)
        st = await msg.reply_text(auto_premium(f"⏳ <b>Downloading ZIP...</b>"), parse_mode="HTML")
        try:
            fi = await msg.document.get_file()
            tmp_zip = f"restore_full_{int(time.time())}.zip"
            await fi.download_to_drive(tmp_zip)
            await st.edit_text(auto_premium(f"⏳ <b>Restoring... (do not close bot)</b>"), parse_mode="HTML")
            with open(tmp_zip, "rb") as f:
                zip_bytes = f.read()
            try: os.remove(tmp_zip)
            except: pass
            counts, bot_names = await restore_full_backup_zip(zip_bytes, uid)
            summary = auto_premium(
                f"✅ <b>FULL RESTORE COMPLETE</b>\n\n"
                f"📦 DBs restored: {counts.get('dbs',0)}\n"
                f"🤖 Bot sessions: {counts.get('bot_sessions',0)}\n"
                f"👥 User sessions: {counts.get('user_sessions',0)}\n"
                f"⚙️ Bots meta entries: {counts.get('bots_meta',0)}\n"
                f"📋 Bots seen: {len(bot_names)}\n\n"
                f"🔄 DB connections reopened.\n"
                f"ℹ️ If you restored config with new bots, restart the process to load them.")
            try: await st.edit_text(summary, parse_mode="HTML")
            except:
                await msg.reply_text(summary, parse_mode="HTML")
            try: await log_admin_action(uid, "Full Restore",
                f"dbs={counts.get('dbs',0)} bots={len(bot_names)}")
            except: pass
        except Exception as e:
            log.error(f"full restore: {e}"); traceback.print_exc()
            try:
                await st.edit_text(auto_premium(f"❌ <b>Restore failed</b>\n\n<code>{html_safe_error(e)}</code>"),
                                    parse_mode="HTML")
            except: pass
        return

    if act == 'osint_upload_docs':
        if not msg.document:
            return
        file_id = msg.document.file_id
        fname = msg.document.file_name or "docs"
        set_setting('osint_docs_file_id', file_id)
        temp_data.pop(uid, None)
        await msg.reply_text(
            auto_premium(f"✅ <b>Docs uploaded!</b>\n📄 <code>{escape(fname)}</code>\n\n"
                         f"Every user buying an OSINT API will receive this file."),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [ibtn("OPEN SETTINGS","adm_osint_settings",emoji="🔍",style="primary")],
                [ibtn("MAIN MENU","home",emoji="🏠",style="primary")]]))
        try: await log_admin_action(uid, "OSINT Docs Uploaded", fname)
        except: pass
        return

    if act == 'restore_wait':
        if not msg.document.file_name.lower().endswith('.json'): return
        fi = await msg.document.get_file()
        tmp = f"restore_{int(time.time())}.json"
        await fi.download_to_drive(tmp)
        try:
            with open(tmp, "r", encoding="utf-8") as f: data = json.load(f)
            counts = restore_from_backup(data)
            await msg.reply_text(auto_premium(f"✅ Restore Complete!\n" +
                "\n".join(f"• {k}: {v}" for k, v in counts.items())), parse_mode="HTML")
        except Exception as e:
            await msg.reply_text(f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
        finally:
            try: os.remove(tmp)
            except: pass
        temp_data.pop(uid, None); return
    if act in ('addzip', 's2_add_zip'):
        if not msg.document.file_name.lower().endswith(".zip"): return
        fi = await msg.document.get_file()
        path = f"temp_{int(time.time())}.zip"
        await fi.download_to_drive(path)
        sc = temp_data[uid].get('stock_server', 'SERVER2')
        cat = temp_data[uid].get('stock_cat', 'NORMAL ACCOUNT')
        temp_data.pop(uid, None)
        asyncio.create_task(telethon_add_zip(msg.chat_id, path, context, sc, cat, uid))

async def telethon_add_zip(chat_id, zip_path, context, srv_code, cat_name, admin_uid):
    try:
        await context.bot.send_message(chat_id,
            f"{emo('⏳')} Processing ZIP...\n"
            f"🎯 Category: {cat_name}\n🖥️ Server: {srv_code}",
            parse_mode="HTML")
        ctx = current_ctx()
        ex = f"{ctx.data_dir}/ext_{int(time.time())}"; os.makedirs(ex, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as z: z.extractall(ex)
        files = [f for f in os.listdir(ex) if f.endswith(".session")]
        if not files:
            await context.bot.send_message(chat_id, f"{emo('❌')} No .session files found.", parse_mode="HTML")
            shutil.rmtree(ex, ignore_errors=True); return

        staged = []
        failed = 0
        skipped = 0
        for f in files:
            try:
                base = f[:-8]; sp = os.path.join(ex, base)
                client = TelegramClient(sp, API_ID, API_HASH)
                await client.connect()
                if not await client.is_user_authorized():
                    failed += 1; await client.disconnect(); continue
                me = await client.get_me()
                ph = getattr(me, 'phone', None)
                if not ph:
                    failed += 1; await client.disconnect(); continue
                if cur.execute("SELECT phone FROM stock WHERE phone=?", (ph,)).fetchone():
                    skipped += 1; await client.disconnect(); continue
                cn, ci = get_country_info(ph)
                year = now_ist().year - 1
                perm = f"{ctx.data_dir}/sessions/{ph}"
                for ext in ['.session','.session-wal','.session-shm','.session-journal']:
                    src = sp + ext
                    if os.path.exists(src): shutil.move(src, perm + ext)
                staged.append({
                    'phone': ph,
                    'c_name': cn,
                    'c_icon': ci,
                    'year': year,
                    'session_file': perm + ".session",
                })
                await client.disconnect()
            except Exception as e:
                log.warning(f"zip session {f}: {e}")
                failed += 1
        shutil.rmtree(ex, ignore_errors=True)
        try: os.remove(zip_path)
        except: pass

        if not staged:
            await context.bot.send_message(chat_id,
                f"{emo('❌')} <b>No valid sessions.</b>\n"
                f"Failed: {failed}\nSkipped (dupe): {skipped}",
                parse_mode="HTML"); return

        country_groups = {}
        for a in staged:
            country_groups.setdefault(a['c_name'], []).append(a)

        zip_staging[admin_uid] = {
            'accounts': staged,
            'country_groups': country_groups,
            'prices': {},
            'server': srv_code,
            'category': cat_name,
        }
        await show_zip_price_ui(admin_uid, context)
        try:
            await context.bot.send_message(chat_id,
                f"{emo('✅')} ZIP parsed!\n\n"
                f"{emo('📦')} Valid: {len(staged)}\n"
                f"{emo('❌')} Failed: {failed}\n"
                f"{emo('♻️')} Skipped (dupe): {skipped}\n"
                f"{emo('🌎')} Countries: {len(country_groups)}\n\n"
                f"{emo('👉')} Now set price for each country above.",
                parse_mode="HTML")
        except: pass
    except Exception as e:
        log.error(f"telethon_add_zip: {e}"); traceback.print_exc()
        try:
            await context.bot.send_message(chat_id, f"{emo('❌')} {html_safe_error(e)}", parse_mode="HTML")
        except: pass


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from backup import restore_from_backup, restore_full_backup_zip
from buttons import ibtn, main_reply_kb
from config import API_HASH, API_ID, DEFAULT_STOCK_PRICE, log, now_ist
from context import cur, current_ctx, db
from countries import get_country_info
from database import is_master_owner, set_setting
from emojis import auto_premium, emo
from logs import log_admin_action, log_new_stock
from rich_ui import _tg_post, make_heading, make_paragraph, make_table, send_rich_async
from state import temp_data, zip_staging
from utils import html_safe_error
