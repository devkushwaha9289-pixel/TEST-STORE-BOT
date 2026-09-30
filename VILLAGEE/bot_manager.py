#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — bot_manager.py
Multi-bot manager (add/stop/start/remove bots).
"""

import re
from html import escape
from telegram import InlineKeyboardMarkup

# ============================================================
# BOT MANAGER
# ============================================================
async def view_bot_manager(update):
    uid = update.effective_user.id
    if not is_master_owner(uid): return
    cfg = load_bots_config(); bots = cfg.get("bots", {})
    table = [["#","🤖 BOT","👤 OWNER","⚡ STATUS"]]; rows_btns = []
    for i, (tk, info) in enumerate(bots.items(), 1):
        un = info.get("username", "unknown"); ow = info.get("owner_id", "—")
        is_m = info.get("is_master", False)
        ctx = BOTS_BY_USERNAME.get(un)
        st = "🟢 ON" if ctx and ctx.started else "🔴 OFF"
        if is_m: st = "👑 MASTER"
        table.append([str(i), f"@{un}"[:24], str(ow), st])
        rows_btns.append([ibtn(f"@{un} ({ow})", f"adm_bot_view|{tk[:15]}", emoji="🤖", style="primary")])
    if not table[1:]: table.append(["—","—","—","—"])
    kbr = [[ibtn("➕ ADD","adm_bot_add",emoji="➕",style="success")]]
    if rows_btns: kbr.extend(rows_btns[:10])
    kbr.append([ibtn("🔄 Refresh","adm_bots_menu",emoji="🔄",style="primary")])
    kbr.append([ibtn("BACK","admin_panel",emoji="🔙",style="primary")])
    await send_rich_async(uid, [make_heading("🤖 BOT MANAGER", 2),
        make_paragraph(f"👑 Master: {MASTER_OWNER_ID}"),
        make_paragraph(f"🤖 Bots: {len(bots)}"),
        make_table(table)],
        reply_markup=InlineKeyboardMarkup(kbr).to_dict(),
        fallback_text=f"BOTS {len(bots)}", edit_query=_edit_query_of(update))

async def handle_add_bot_token(update, context, token):
    uid = update.effective_user.id
    if not is_master_owner(uid): return
    token = token.strip()
    if ":" not in token or len(token) < 20:
        await update.message.reply_text(f"{emo('❌')} Invalid token.", parse_mode="HTML"); return
    cfg = load_bots_config()
    if token in cfg.get("bots", {}):
        await update.message.reply_text(f"{emo('⚠️')} Already added.", parse_mode="HTML"); return
    await update.message.reply_text(f"{emo('⏳')} Fetching...", parse_mode="HTML")
    uname = await fetch_bot_username(token)
    if not uname:
        await update.message.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
    if uname in BOTS_BY_USERNAME:
        await update.message.reply_text(f"{emo('⚠️')} Already running.", parse_mode="HTML"); return
    temp_data[uid] = {'admin_action': 'adm_bot_add_owner', 'new_bot_token': token, 'new_bot_username': uname}
    await update.message.reply_text(f"{emo('✅')} <b>@{escape(uname)}</b>\n\n{emo('📝')} Send OWNER ID:",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))

async def handle_add_bot_owner(update, context, owner_text):
    uid = update.effective_user.id
    if not is_master_owner(uid): return
    state = temp_data.get(uid, {})
    token = state.get('new_bot_token'); uname = state.get('new_bot_username')
    if not token or not uname: temp_data.pop(uid, None); return
    try: owner_id = int(re.sub(r'[^\d]', '', owner_text))
    except:
        await update.message.reply_text(f"{emo('❌')} Invalid ID.", parse_mode="HTML"); return
    cfg = load_bots_config()
    cfg.setdefault("bots", {})[token] = {"owner_id": owner_id, "username": uname, "is_master": False}
    save_bots_config(cfg); temp_data.pop(uid, None)
    await update.message.reply_text(f"{emo('⏳')} Starting @{escape(uname)}...", parse_mode="HTML")
    try:
        ctx = BotContext(token, uname, owner_id, is_master=False)
        BOTS_BY_TOKEN[token] = ctx; BOTS_BY_USERNAME[uname] = ctx; BOT_CONTEXTS.append(ctx)
        await ctx.start()
        await update.message.reply_text(f"{emo('✅')} <b>Started!</b>\n🤖 @{escape(uname)}\n👤 <code>{owner_id}</code>",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[ibtn("BOTS","adm_bots_menu",emoji="🔙",style="primary")]]))
    except Exception as e:
        log.error(f"start: {e}")
        await update.message.reply_text(f"{emo('❌')} Failed: {html_safe_error(e)}", parse_mode="HTML")

async def view_bot_detail(update, tp):
    uid = update.effective_user.id
    if not is_master_owner(uid): return
    cfg = load_bots_config()
    ft = next((tk for tk in cfg.get("bots", {}) if tk.startswith(tp)), None)
    if not ft:
        try: await update.callback_query.answer("Not found", show_alert=True)
        except: pass
        return
    info = cfg["bots"][ft]; un = info.get("username","unknown")
    ow = info.get("owner_id","—"); is_m = info.get("is_master", False)
    ctx = BOTS_BY_USERNAME.get(un)
    st = "🟢 RUNNING" if ctx and ctx.started else "🔴 STOPPED"
    if is_m: st = "👑 MASTER"
    kbr = [
        [ibtn("🛑 STOP","adm_bot_stop|"+ft[:15],emoji="🛑",style="danger")],
        [ibtn("▶️ START","adm_bot_start|"+ft[:15],emoji="▶️",style="success")],
        [ibtn("🗑️ REMOVE","adm_bot_remove_ask|"+ft[:15],emoji="🗑️",style="danger")],
        [ibtn("BACK","adm_bots_menu",emoji="🔙",style="primary")]]
    if is_m: kbr = [[ibtn("BACK","adm_bots_menu",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading(f"🤖 @{un}", 2),
        make_table([["ℹ️ INFO","📋 VALUE"],["🤖", f"@{un}"],["👤 Owner", str(ow)],
                    ["👑 Master", "YES" if is_m else "NO"],["⚡ Status", st]])],
        reply_markup=InlineKeyboardMarkup(kbr).to_dict(),
        fallback_text=f"@{un} | {st}", edit_query=_edit_query_of(update))

async def stop_bot_by_token_prefix(tp):
    cfg = load_bots_config()
    ft = next((tk for tk in cfg.get("bots",{}) if tk.startswith(tp)), None)
    if not ft: return False, "Not found"
    info = cfg["bots"][ft]; un = info.get("username")
    ctx = BOTS_BY_USERNAME.get(un)
    if not ctx: return False, "Not running"
    if ctx.is_master: return False, "Cannot stop master"
    try: await ctx.stop(); return True, f"Stopped @{un}"
    except Exception as e: return False, str(e)

async def start_bot_by_token_prefix(tp):
    cfg = load_bots_config()
    ft = next((tk for tk in cfg.get("bots",{}) if tk.startswith(tp)), None)
    if not ft: return False, "Not found"
    info = cfg["bots"][ft]; un = info.get("username")
    ctx = BOTS_BY_USERNAME.get(un)
    if not ctx:
        try:
            ctx = BotContext(ft, un, info.get("owner_id",0), info.get("is_master",False))
            BOTS_BY_TOKEN[ft] = ctx; BOTS_BY_USERNAME[un] = ctx; BOT_CONTEXTS.append(ctx)
        except Exception as e: return False, str(e)
    if ctx.started: return False, "Already running"
    try: await ctx.start(); return True, f"Started @{un}"
    except Exception as e: return False, str(e)

async def remove_bot_by_token_prefix(tp):
    cfg = load_bots_config()
    ft = next((tk for tk in cfg.get("bots",{}) if tk.startswith(tp)), None)
    if not ft: return False, "Not found"
    info = cfg["bots"][ft]; un = info.get("username")
    if info.get("is_master"): return False, "Cannot remove master"
    ctx = BOTS_BY_USERNAME.get(un)
    if ctx:
        try: await ctx.stop()
        except: pass
        BOTS_BY_USERNAME.pop(un, None); BOTS_BY_TOKEN.pop(ft, None)
        try: BOT_CONTEXTS.remove(ctx)
        except: pass
    cfg["bots"].pop(ft, None); save_bots_config(cfg)
    return True, f"Removed @{un}"


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn
from config import log
from context import (
    BOTS_BY_TOKEN, BOTS_BY_USERNAME, BOT_CONTEXTS, BotContext, MASTER_OWNER_ID,
    fetch_bot_username, load_bots_config, save_bots_config
)
from database import is_master_owner
from emojis import emo
from rich_ui import _edit_query_of, make_heading, make_paragraph, make_table, send_rich_async
from state import temp_data
from utils import html_safe_error
