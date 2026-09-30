#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — text_handlers.py
Text / photo / video / error handlers.
"""

import traceback
from html import escape
from telegram import InlineKeyboardMarkup

# ============================================================
# TEXT HANDLER
# ============================================================
async def on_text(update, context):
    try:
        msg = update.message
        if not msg or not msg.text: return
        text = msg.text.strip()
        uid = update.effective_user.id
        ensure_user(uid, update.effective_user.first_name or "",
                    update.effective_user.username or "",
                    update.effective_user.last_name or "")
        if is_banned(uid): return

        # ⭐ Manual UPI — user sending UTR
        if uid in manual_upi_pending:
            await handle_manual_upi_text(update, context); return

        # ⭐ Manual UPI — OWNER reject reason
        if uid in manual_upi_owner_state:
            await handle_manual_upi_owner_text(update, context); return

        if not is_bot_online() and not is_admin(uid):
            await show_maintenance(uid, "bot"); return

        # Force-join hard gate for TEXT
        if not is_admin(uid) and get_all_channels():
            cmd_bypass = text in ("/cancel", BTN_CANCEL) or text.startswith("/start")
            if not cmd_bypass:
                ok, miss = await check_user_in_channels(uid, use_cache=False)
                if not ok:
                    await send_force_join_prompt(uid, miss); return

        if uid in waiting_utr: await handle_utr_text_input(update, context); return
        if uid in lzt_search_state:
            lzt_search_state.pop(uid, None)
            matches = find_country_matches(text)
            if not matches:
                await msg.reply_text(f"{emo('❌')} No match. Try +91 or US.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [ibtn("BACK","buy1",emoji="🔙",style="primary"),
                         ibtn("SEARCH","lzt_search_country",emoji="🔍",style="primary")]]))
                return
            if len(matches) == 1:
                nm = matches[0]; iso = LZT_COUNTRY_CATALOG[nm][0]
                kb = InlineKeyboardMarkup([
                    [ibtn(f"Open {country_button_label(nm)}", f"lzt_chk|{iso}|1", emoji="🎯", style="success")],
                    [ibtn("BACK","buy1",emoji="🔙",style="primary")]])
                await msg.reply_text(f"✅ <b>{LZT_COUNTRY_CATALOG[nm][1]} {escape(nm)}</b>",
                                      parse_mode="HTML", reply_markup=kb)
                return
            btns, row = [], []
            for nm in matches[:10]:
                iso, flag, _ = LZT_COUNTRY_CATALOG[nm]
                row.append(ibtn(country_button_label(nm), f"lzt_chk|{iso}|1", raw_flag=flag, style="success"))
                if len(row) == 2: btns.append(row); row = []
            if row: btns.append(row)
            btns.append([ibtn("BACK","buy1",emoji="🔙",style="primary")])
            await msg.reply_text(f"🔎 {len(matches)} matches:", parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(btns))
            return
        if uid in temp_data and temp_data[uid].get('step') == 'balance_transfer_uid':
            await handle_balance_transfer_uid(update, context); return
        if uid in temp_data and temp_data[uid].get('step') == 'balance_transfer_amt':
            await handle_balance_transfer_amt(update, context); return
        if uid in temp_data and 'admin_action' in temp_data[uid]:
            await handle_admin_text(update, context); return
        if uid in waiting_proof and (msg.photo or msg.document or (text and "http" in text)):
            await handle_deposit_proof(update, context); return
        if uid in deposit_input and deposit_input[uid].get('step') == 'wait_amt':
            await handle_deposit_amount(update, context); return

        if text == BTN_ADMIN:
            if is_admin(uid): await view_admin_panel(update)
            else: await msg.reply_text(f"{emo('❌')} Not authorized.", parse_mode="HTML",
                                        reply_markup=main_reply_kb(uid))
            return
        if text == BTN_BUY1: await view_buy1_lzt(update, 1); return
        if text == BTN_BUY2: await view_buy2(update); return
        if text == BTN_BUY3: await view_buy3(update); return
        if text == BTN_BUYWA: await view_buywa(update); return
        if text == BTN_RECHARGE: await view_recharge(update); return
        if text == BTN_PROFILE: await view_profile(update); return
        if text == BTN_REFER: await view_refer(update); return
        if text == BTN_SUPPORT: await view_support(update); return
        if text == BTN_BALANCE: await view_balance(update); return
        if text == BTN_REDEEM:
            temp_data[uid] = {'admin_action': 'redeem'}
            await msg.reply_text(f"<b>{emo('🔥')} Redeem</b>\n\n{emo('🎁')} Enter code:",
                                  parse_mode="HTML", reply_markup=redeem_reply_kb())
            return
        if text == BTN_CANCEL: await cmd_cancel(update, context); return
        if text == BTN_MAINMENU:
            try: await msg.reply_text("🏠", reply_markup=main_reply_kb(uid))
            except: pass
            await view_home(update); return
        await msg.reply_text(f"{emo('❓')} Use /start", parse_mode="HTML",
                              reply_markup=main_reply_kb(uid))
    except Exception as e:
        log.error(f"on_text: {e}"); traceback.print_exc()

async def on_photo(update, context):
    try:
        uid = update.effective_user.id; msg = update.message
        if is_banned(uid): return

        # ⭐ Manual UPI — user sending screenshot
        if uid in manual_upi_pending:
            await handle_manual_upi_proof(update, context); return

        if not is_admin(uid) and get_all_channels():
            ok, miss = await check_user_in_channels(uid, use_cache=False)
            if not ok and uid not in waiting_proof and uid not in temp_data:
                await send_force_join_prompt(uid, miss); return
        if uid in temp_data:
            act = temp_data[uid].get('admin_action', '')
            if act in ('bc_wait_msg', 'bc_wait_image'):
                try: temp_data[uid]['bcast_text'] = msg.caption_html or msg.caption or ""
                except: temp_data[uid]['bcast_text'] = msg.caption or ""
                temp_data[uid]['bcast_text'] = auto_premium(temp_data[uid]['bcast_text'])
                temp_data[uid]['bcast_media_type'] = 'photo'
                temp_data[uid]['bcast_media_id'] = msg.photo[-1].file_id
                temp_data[uid]['admin_action'] = 'bc_btn_menu'
                await msg.reply_text(f"{emo('✅')} Photo attached.", parse_mode="HTML",
                                      reply_markup=bcast_btn_action_kb())
                return
        if uid in waiting_proof: await handle_deposit_proof(update, context)
    except Exception as e: log.error(f"on_photo: {e}")

async def on_video(update, context):
    try:
        uid = update.effective_user.id; msg = update.message
        if is_banned(uid): return
        if not is_admin(uid) and get_all_channels():
            ok, miss = await check_user_in_channels(uid, use_cache=False)
            if not ok and uid not in temp_data:
                await send_force_join_prompt(uid, miss); return
        if uid in temp_data:
            act = temp_data[uid].get('admin_action', '')
            if act in ('bc_wait_msg', 'bc_wait_video'):
                try: temp_data[uid]['bcast_text'] = msg.caption_html or msg.caption or ""
                except: temp_data[uid]['bcast_text'] = msg.caption or ""
                temp_data[uid]['bcast_text'] = auto_premium(temp_data[uid]['bcast_text'])
                temp_data[uid]['bcast_media_type'] = 'video'
                temp_data[uid]['bcast_media_id'] = msg.video.file_id
                temp_data[uid]['admin_action'] = 'bc_btn_menu'
                await msg.reply_text(f"{emo('✅')} Video attached.", parse_mode="HTML",
                                      reply_markup=bcast_btn_action_kb())
                return
    except Exception as e: log.error(f"on_video: {e}")

async def on_error(update, context):
    log.exception("Unhandled:", exc_info=context.error)


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from admin_panel import view_admin_panel
from admin_text import handle_admin_text
from broadcast import bcast_btn_action_kb
from buttons import (
    BTN_ADMIN, BTN_BALANCE, BTN_BUY1, BTN_BUY2, BTN_BUY3, BTN_BUYWA, BTN_CANCEL,
    BTN_MAINMENU, BTN_PROFILE, BTN_RECHARGE, BTN_REDEEM, BTN_REFER, BTN_SUPPORT, ibtn,
    main_reply_kb, redeem_reply_kb
)
from commands import cmd_cancel
from config import log
from database import ensure_user, is_admin, is_banned, is_bot_online
from emojis import auto_premium, emo
from force_join import check_user_in_channels, get_all_channels, send_force_join_prompt
from lzt_api import LZT_COUNTRY_CATALOG, country_button_label, find_country_matches
from manual_upi import handle_manual_upi_owner_text, handle_manual_upi_proof, handle_manual_upi_text
from payments import (
    handle_balance_transfer_amt, handle_balance_transfer_uid, handle_deposit_amount,
    handle_deposit_proof, handle_utr_text_input
)
from server1 import view_buy1_lzt
from server2 import view_buy2
from server3 import view_buy3
from state import (
    deposit_input, lzt_search_state, manual_upi_owner_state, manual_upi_pending, temp_data,
    waiting_proof, waiting_utr
)
from views import (
    show_maintenance, view_balance, view_buywa, view_home, view_profile, view_recharge,
    view_refer, view_support
)
