#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — broadcast.py
Broadcast keyboards, single-bot broadcast and global broadcast.
"""

import asyncio, aiohttp
from telegram import InlineKeyboardMarkup

# ============================================================
# GLOBAL BROADCAST
# ============================================================
async def view_global_broadcast(update):
    uid = update.effective_user.id
    if not is_master_owner(uid): return
    total_bots = len(BOTS_BY_USERNAME); total_users = 0
    for ctx in BOT_CONTEXTS:
        try:
            tok = _current_bot.set(ctx)
            try: total_users += ctx.cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            finally: _current_bot.reset(tok)
        except: pass
    rows = [
        [ibtn("📢 GLOBAL BROADCAST","gb_start",emoji="📢",style="danger")],
        [ibtn("📌 GLOBAL BCAST + PIN","gb_start_pin",emoji="📌",style="danger")],
        [ibtn("🔙 BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("🌍 GLOBAL BROADCAST", 2),
        make_paragraph("Full-featured broadcast (media/buttons/pin/rich) to every user of every bot."),
        make_table([["ℹ️ INFO","📋 VALUE"],["🤖 Bots", str(total_bots)],
                    ["👥 Total Users", str(total_users)]])],
        reply_markup=InlineKeyboardMarkup(rows).to_dict(),
        fallback_text=f"🌍 GB — {total_bots} bots | {total_users} users",
        edit_query=_edit_query_of(update))

async def do_global_broadcast_full(admin_uid, context, state):
    text = state.get('bcast_text', '')
    media_type = state.get('bcast_media_type'); media_id = state.get('bcast_media_id')
    buttons = state.get('bcast_buttons', []); should_pin = state.get('bcast_pin', False)
    button_position = state.get('bcast_button_position', 'below_center')
    has_rich = any(b.get('type') == 'rich' for b in buttons)
    kb = None if has_rich else build_bcast_kb(buttons)
    rich_blocks = None
    if has_rich:
        if button_position.endswith("_left"): align = "left"
        elif button_position.endswith("_right"): align = "right"
        else: align = "center"
        rbb = build_rich_buttons_block(buttons, align=align)
        text_block = make_paragraph(text)
        if button_position.startswith("above_"):
            rich_blocks = [rbb, text_block] if rbb else [text_block]
        else:
            rich_blocks = [text_block, rbb] if rbb else [text_block]
    all_users = []
    for ctx in BOT_CONTEXTS:
        if not ctx.started: continue
        try:
            tok = _current_bot.set(ctx)
            try:
                for r in ctx.cur.execute("SELECT user_id FROM users").fetchall():
                    all_users.append((ctx.token, ctx.username, int(r[0])))
            finally: _current_bot.reset(tok)
        except: pass
    total = len(all_users); sent = 0; failed = 0
    status_msg = await context.bot.send_message(admin_uid,
        f"{emo('🌍')} GLOBAL BROADCAST → {total} users...", parse_mode="HTML")
    for i, (bot_token, bot_uname, u_id) in enumerate(all_users, 1):
        try:
            if has_rich:
                photo_id = media_id if (media_type == 'photo' and media_id) else None
                result = await _send_rich_broadcast_msg(bot_token, u_id, rich_blocks, photo_id)
                if result:
                    sent += 1
                    mid = result.get("message_id")
                    if should_pin and mid:
                        try:
                            async with aiohttp.ClientSession() as s:
                                await s.post(f"https://api.telegram.org/bot{bot_token}/pinChatMessage",
                                    json={"chat_id": u_id, "message_id": mid,
                                          "disable_notification": True},
                                    timeout=aiohttp.ClientTimeout(total=10))
                        except: pass
                else:
                    try:
                        base = f"https://api.telegram.org/bot{bot_token}"
                        async with aiohttp.ClientSession() as s:
                            if media_type == 'photo' and media_id:
                                await s.post(f"{base}/sendPhoto",
                                    json={"chat_id": u_id, "photo": media_id,
                                          "caption": text, "parse_mode": "HTML",
                                          "reply_markup": kb.to_dict() if kb else None},
                                    timeout=aiohttp.ClientTimeout(total=15))
                            elif media_type == 'video' and media_id:
                                await s.post(f"{base}/sendVideo",
                                    json={"chat_id": u_id, "video": media_id,
                                          "caption": text, "parse_mode": "HTML",
                                          "reply_markup": kb.to_dict() if kb else None},
                                    timeout=aiohttp.ClientTimeout(total=15))
                            else:
                                await s.post(f"{base}/sendMessage",
                                    json={"chat_id": u_id, "text": text,
                                          "parse_mode": "HTML",
                                          "reply_markup": kb.to_dict() if kb else None,
                                          "disable_web_page_preview": True},
                                    timeout=aiohttp.ClientTimeout(total=15))
                        sent += 1
                    except: failed += 1
            else:
                base = f"https://api.telegram.org/bot{bot_token}"
                payload = {"chat_id": u_id, "parse_mode": "HTML", "disable_web_page_preview": True}
                if kb: payload["reply_markup"] = kb.to_dict()
                endpoint = "sendMessage"
                if media_type == 'photo' and media_id:
                    endpoint = "sendPhoto"; payload["photo"] = media_id; payload["caption"] = text
                    payload.pop("disable_web_page_preview", None)
                elif media_type == 'video' and media_id:
                    endpoint = "sendVideo"; payload["video"] = media_id; payload["caption"] = text
                    payload.pop("disable_web_page_preview", None)
                else:
                    payload["text"] = text
                mid = None
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.post(f"{base}/{endpoint}", json=payload,
                                            timeout=aiohttp.ClientTimeout(total=15)) as r:
                            d = await r.json()
                            if d.get("ok"):
                                mid = d.get("result", {}).get("message_id")
                                sent += 1
                            else: failed += 1
                except: failed += 1
                if should_pin and mid:
                    try:
                        async with aiohttp.ClientSession() as s:
                            await s.post(f"{base}/pinChatMessage",
                                json={"chat_id": u_id, "message_id": mid, "disable_notification": True},
                                timeout=aiohttp.ClientTimeout(total=10))
                    except: pass
        except: failed += 1
        if i % 30 == 0:
            try:
                await status_msg.edit_text(
                    f"{emo('🌍')} GLOBAL BCAST\n✅ {sent} | ❌ {failed}\n📊 {i}/{total}",
                    parse_mode="HTML")
            except: pass
        await asyncio.sleep(0.05)
    try:
        await status_msg.edit_text(
            f"{emo('✅')} <b>Global Broadcast Complete!</b>\n\n"
            f"{emo('📊')} Total: {total}\n✅ Sent: {sent}\n❌ Failed: {failed}\n"
            f"📌 Pin: {'Yes' if should_pin else 'No'}\n🎨 Rich: {'Yes' if has_rich else 'No'}",
            parse_mode="HTML")
    except: pass
    await log_admin_action(admin_uid, "Global Broadcast", f"Sent={sent} Failed={failed}")


# ============================================================
# BROADCAST HELPERS
# ============================================================
def build_bcast_kb(buttons):
    if not buttons: return None
    inline_btns = [b for b in buttons if b.get('type', 'inline') == 'inline']
    if not inline_btns: return None
    rows = []
    for i in range(0, min(len(inline_btns), 6), 2):
        row = []
        for j in range(2):
            if i+j < len(inline_btns):
                b = inline_btns[i+j]
                row.append(ibtn(b['name'], url=b['url'], style=b['style']))
        rows.append(row)
    return InlineKeyboardMarkup(rows) if rows else None

def bcast_media_menu_kb():
    return InlineKeyboardMarkup([
        [ibtn("ADD VIDEO","bc_add_video",emoji="🎬",style="primary"),
         ibtn("ADD IMAGE","bc_add_image",emoji="🎥",style="primary")],
        [ibtn("NO MEDIA","bc_no_media",emoji="❌",style="danger"),
         ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])

def bcast_btn_action_kb():
    return InlineKeyboardMarkup([
        [ibtn("ADD BUTTON","bc_add_btn",emoji="➕",style="success")],
        [ibtn("📍 Button Position","bc_btn_pos_menu",emoji="📍",style="primary")],
        [ibtn("DONE","bc_done",emoji="✅",style="danger")],
        [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])

def bcast_btn_type_kb():
    return InlineKeyboardMarkup([
        [ibtn("🔵 INLINE BUTTON","bc_btn_inline",emoji="🔗",style="primary")],
        [ibtn("🎨 RICH BUTTON","bc_btn_rich",emoji="✨",style="success")],
        [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])

def bcast_color_kb():
    return InlineKeyboardMarkup([
        [ibtn("PRIMARY","bc_color_primary",emoji="💠",style="primary")],
        [ibtn("SUCCESS","bc_color_success",emoji="✅",style="success")],
        [ibtn("DANGER","bc_color_danger",emoji="❌",style="danger")],
        [ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])

def bcast_position_kb(current="below_center"):
    def mk(pos, label, emoji, style="primary"):
        mark = "✅ " if current == pos else ""
        return ibtn(f"{mark}{label}", f"bc_pos|{pos}", emoji=emoji, style=style)
    return InlineKeyboardMarkup([
        [mk("above_left", "Top Left", "↖️"),
         mk("above_center", "Top Center", "⬆️"),
         mk("above_right", "Top Right", "↗️")],
        [mk("below_left", "Bottom Left", "↙️"),
         mk("below_center", "Bottom Center", "⬇️"),
         mk("below_right", "Bottom Right", "↘️")],
        [ibtn("BACK","bc_btn_menu",emoji="🔙",style="primary")]])

async def do_broadcast(context, admin_uid, state):
    text = state.get('bcast_text', '')
    media_type = state.get('bcast_media_type'); media_id = state.get('bcast_media_id')
    buttons = state.get('bcast_buttons', []); should_pin = state.get('bcast_pin', False)
    button_position = state.get('bcast_button_position', 'below_center')
    has_rich = any(b.get('type') == 'rich' for b in buttons)
    kb = None if has_rich else build_bcast_kb(buttons)
    rich_blocks = None
    if has_rich:
        if button_position.endswith("_left"): align = "left"
        elif button_position.endswith("_right"): align = "right"
        else: align = "center"
        rbb = build_rich_buttons_block(buttons, align=align)
        text_block = make_paragraph(text)
        if button_position.startswith("above_"):
            rich_blocks = [rbb, text_block] if rbb else [text_block]
        else:
            rich_blocks = [text_block, rbb] if rbb else [text_block]
    users = cur.execute("SELECT user_id FROM users").fetchall()
    total = len(users); sent = failed = 0
    bot_token = context.bot.token
    status_msg = await context.bot.send_message(admin_uid, f"{emo('📢')} Broadcasting to {total}...",
                                                 parse_mode="HTML")
    for i, (u_id,) in enumerate(users, 1):
        try:
            if has_rich:
                pid = media_id if (media_type == 'photo' and media_id) else None
                result = await _send_rich_broadcast_msg(bot_token, int(u_id), rich_blocks, pid)
                if result:
                    sent += 1
                    mid = result.get("message_id")
                    if should_pin and mid:
                        try: await context.bot.pin_chat_message(chat_id=int(u_id),
                            message_id=mid, disable_notification=True)
                        except: pass
                else:
                    try:
                        if media_type == 'photo' and media_id:
                            await context.bot.send_photo(chat_id=int(u_id), photo=media_id,
                                caption=text, parse_mode="HTML", reply_markup=kb)
                        elif media_type == 'video' and media_id:
                            await context.bot.send_video(chat_id=int(u_id), video=media_id,
                                caption=text, parse_mode="HTML", reply_markup=kb)
                        else:
                            await context.bot.send_message(chat_id=int(u_id), text=text,
                                parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
                        sent += 1
                    except: failed += 1
            else:
                msg = None
                if media_type == 'photo' and media_id:
                    msg = await context.bot.send_photo(chat_id=int(u_id), photo=media_id,
                        caption=text, parse_mode="HTML", reply_markup=kb)
                elif media_type == 'video' and media_id:
                    msg = await context.bot.send_video(chat_id=int(u_id), video=media_id,
                        caption=text, parse_mode="HTML", reply_markup=kb)
                else:
                    msg = await context.bot.send_message(chat_id=int(u_id), text=text,
                        parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
                if should_pin and msg:
                    try: await context.bot.pin_chat_message(chat_id=int(u_id),
                        message_id=msg.message_id, disable_notification=True)
                    except: pass
                sent += 1
        except: failed += 1
        if i % 20 == 0:
            try:
                await status_msg.edit_text(f"{emo('📢')} {i}/{total}\n{emo('✅')} {sent} | {emo('❌')} {failed}",
                    parse_mode="HTML")
            except: pass
        await asyncio.sleep(0.05)
    try:
        await status_msg.edit_text(auto_premium(
            f"✅ <b>Broadcast Complete!</b>\n\n"
            f"Total: {total}\n✅ {sent}\n❌ {failed}\n"
            f"📌 Pin: {'Yes' if should_pin else 'No'}\n"
            f"🎨 Rich: {'Yes' if has_rich else 'No'}"), parse_mode="HTML")
    except: pass
    await log_admin_action(admin_uid, "Broadcast", f"Sent={sent} Failed={failed}")


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn
from context import BOTS_BY_USERNAME, BOT_CONTEXTS, _current_bot, cur
from database import is_master_owner
from emojis import auto_premium, emo
from logs import log_admin_action
from rich_ui import (
    _edit_query_of, _send_rich_broadcast_msg, build_rich_buttons_block, make_heading,
    make_paragraph, make_table, send_rich_async
)
