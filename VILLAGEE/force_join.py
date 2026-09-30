#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — force_join.py
Force-join channel checks and enforcement.
"""

import time, aiohttp
from html import escape
from telegram import InlineKeyboardMarkup

# ============================================================
# FORCE JOIN
# ============================================================
_force_join_cache = {}

def get_all_channels():
    return cur.execute("SELECT channel_id, channel_link FROM channels").fetchall()

def _channel_display_name(row):
    try:
        title = row["title"] if hasattr(row, "keys") and "title" in row.keys() else None
    except: title = None
    link = None
    try: link = row["channel_link"]
    except:
        try: link = row[1]
        except: link = None
    return title or link or "Channel"

def _channel_chat_id(row):
    try: return row["channel_id"]
    except:
        try: return row[0]
        except: return None

async def _tg_get_chat_member(chat_id, user_id):
    try:
        url = f"https://api.telegram.org/bot{current_ctx().token}/getChatMember"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params={"chat_id": str(chat_id), "user_id": int(user_id)},
                              timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
                if d.get("ok"):
                    return {"ok": True, "status": (d.get("result") or {}).get("status", "")}
                return {"ok": False, "description": d.get("description", "error")}
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}: {e}"}

async def check_user_in_channels(uid, use_cache=True):
    chans = get_all_channels()
    if not chans: return True, None
    if is_admin(uid): return True, None

    now = time.monotonic()
    if use_cache:
        ck = _force_join_cache.get(uid)
        if ck and now - ck[0] < FORCE_JOIN_CACHE_TTL:
            return ck[1], ck[2]

    missing = None
    for row in chans:
        ch_id = _channel_chat_id(row)
        if ch_id in (None, ""): continue
        info = await _tg_get_chat_member(ch_id, uid)
        if not info.get("ok"):
            log.warning(f"force-join check failed for chat {ch_id}: {info.get('description')}")
            continue
        status = (info.get("status") or "").lower()
        if status in ("creator", "administrator", "member", "restricted"):
            continue
        missing = row
        break

    ok = missing is None
    _force_join_cache[uid] = (now, ok, missing)
    return ok, missing

def force_join_kb():
    rows = []
    for r in get_all_channels():
        link = None
        try: link = r["channel_link"]
        except:
            try: link = r[1]
            except: link = None
        if not link: continue
        if not link.startswith("http"):
            link = "https://t.me/" + link.replace("@", "")
        rows.append([ibtn("JOIN CHANNEL", url=link, emoji="📢", style="primary")])
    rows.append([ibtn("VERIFY", "verify_join", emoji="✅", style="success")])
    return InlineKeyboardMarkup(rows)

async def send_force_join_prompt(chat_id, missing_row=None):
    if not get_all_channels(): return
    miss_line = ""
    if missing_row is not None:
        name = _channel_display_name(missing_row)
        miss_line = f"\n{emo('🚫')} You are not in: <b>{escape(str(name))}</b>"
    txt = (f"<b>{emo('⚠️')} JOIN REQUIRED</b>\n"
           f"{miss_line}\n"
           f"{emo('📢')} You must join all our channels to use the bot.\n"
           f"{emo('👉')} Join them, then tap <b>VERIFY</b>.")
    try:
        await _tg_post("sendMessage", {
            "chat_id": chat_id, "text": auto_premium(txt),
            "parse_mode": "HTML", "reply_markup": force_join_kb().to_dict()})
    except: pass

async def force_join_message(chat_id):
    await send_force_join_prompt(chat_id)

async def enforce_force_join(update, context=None, quiet=False):
    u = update.effective_user if update else None
    if not u: return True
    uid = u.id
    if is_admin(uid): return True
    if not get_all_channels(): return True
    ok, miss = await check_user_in_channels(uid, use_cache=False)
    if ok: return True
    if not quiet:
        await send_force_join_prompt(uid, miss)
        try:
            if update.callback_query:
                await update.callback_query.answer("Please join all channels first.", show_alert=True)
        except: pass
    return False


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn
from config import FORCE_JOIN_CACHE_TTL, log
from context import cur, current_ctx
from database import is_admin
from emojis import auto_premium, emo
from rich_ui import _tg_post
