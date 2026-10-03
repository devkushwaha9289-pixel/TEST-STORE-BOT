#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — buttons.py
Inline/Reply button builders and keyboard factories.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# ============================================================
# BUTTON BUILDERS
# ============================================================
def ibtn(text, callback_data=None, url=None, emoji=None, style=None, raw_flag=None, custom_id=None):
    kw = {"text": text}
    if callback_data is not None: kw["callback_data"] = callback_data
    if url is not None: kw["url"] = url
    if custom_id:
        kw["icon_custom_emoji_id"] = str(custom_id)
    elif raw_flag and raw_flag in FLAG_IDS:
        kw["icon_custom_emoji_id"] = FLAG_IDS[raw_flag]
        if not text.startswith(raw_flag): kw["text"] = f"{raw_flag} {text}"
    elif raw_flag:
        kw["text"] = f"{raw_flag} {text}"
    elif emoji and emoji in EMOJI_MAP:
        kw["icon_custom_emoji_id"] = EMOJI_MAP[emoji]
        if not text.startswith(emoji): kw["text"] = f"{emoji} {text}"
    elif emoji:
        kw["text"] = f"{emoji} {text}"
    if style: kw["style"] = style
    return InlineKeyboardButton(**kw)

def rbtn(text, emoji=None, style=None, custom_id=None):
    kw = {"text": text}
    try:
        if custom_id and isinstance(custom_id, str) and custom_id.isdigit() and len(custom_id) >= 5:
            kw["icon_custom_emoji_id"] = custom_id
        elif emoji and emoji in EMOJI_MAP:
            kw["icon_custom_emoji_id"] = EMOJI_MAP[emoji]
    except Exception: pass
    if style: kw["style"] = style
    try: return KeyboardButton(**kw)
    except Exception: return KeyboardButton(text=text)


# ============================================================
# REPLY KEYBOARDS
# ============================================================
BTN_BUY1 = "BUY SERVER (1)"
BTN_BUY2 = "BUY SERVER (2)"
BTN_BUY3 = "BUY SERVER (3)"
BTN_BUYWA = "BUY WHATSAPP (4)"
BTN_RECHARGE = "RECHARGE"
BTN_PROFILE = "MY PROFILE"
BTN_REFER = "REFER FRIENDS"
BTN_REDEEM = "REDEEM"
BTN_SUPPORT = "SUPPORT"
BTN_BALANCE = "BALANCE"
BTN_CANCEL = "CANCEL"
BTN_MAINMENU = "MAIN MENU"
BTN_ADMIN = "ADMIN PANEL"

def main_reply_kb(uid=None):
    # Legacy name kept for compatibility; payment/admin UI is inline-only.
    return main_inline_kb(uid)


def _legacy_main_reply_kb(uid=None):
    try:
        rows = [
            [rbtn(BTN_BUY1, style="primary", custom_id=SERVER_EMOJI_IDS["s1"]),
             rbtn(BTN_BUY2, style="primary", custom_id=SERVER_EMOJI_IDS["s2"])],
            [rbtn(BTN_BUY3, style="primary", custom_id=SERVER_EMOJI_IDS["s3"]),
             rbtn(BTN_BUYWA, style="danger", custom_id=SERVER_EMOJI_IDS["wa"])],
            [rbtn(BTN_RECHARGE, "➕", "success"),
             rbtn(BTN_PROFILE, style="primary", custom_id=SERVER_EMOJI_IDS["profile"])],
            [rbtn(BTN_REFER, "👥", "primary"), rbtn(BTN_REDEEM, "🎁", "success")],
            [rbtn(BTN_SUPPORT, "🆘", "danger"),
             rbtn(BTN_BALANCE, style="primary", custom_id=BALANCE_PREMIUM_EMOJI_ID)],
        ]
        if uid is not None:
            try:
                if is_admin(uid): rows.append([rbtn(BTN_ADMIN, emoji="🔐", style="danger")])
            except: pass
        return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True,
                                    input_field_placeholder="Choose an option...")
    except Exception as e:
        log.error(f"main_reply_kb: {e}")
        rows = [
            [KeyboardButton(BTN_BUY1), KeyboardButton(BTN_BUY2)],
            [KeyboardButton(BTN_BUY3), KeyboardButton(BTN_BUYWA)],
            [KeyboardButton(BTN_RECHARGE), KeyboardButton(BTN_PROFILE)],
            [KeyboardButton(BTN_REFER), KeyboardButton(BTN_REDEEM)],
            [KeyboardButton(BTN_SUPPORT), KeyboardButton(BTN_BALANCE)],
        ]
        if uid is not None:
            try:
                if is_admin(uid): rows.append([KeyboardButton(BTN_ADMIN)])
            except: pass
        return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)

def redeem_reply_kb():
    # Legacy name kept for compatibility; no Telegram reply keyboard is used.
    return InlineKeyboardMarkup([[ibtn("CANCEL", "cancel", emoji="❌", style="danger")],
                                 [ibtn("BALANCE", "balance", emoji="💰", style="primary"),
                                  ibtn("RECHARGE", "recharge", emoji="➕", style="success")]])


def _legacy_redeem_reply_kb():
    try:
        return ReplyKeyboardMarkup([[rbtn(BTN_CANCEL, "❌", "danger")],
                                     [rbtn(BTN_BALANCE, style="primary", custom_id=BALANCE_PREMIUM_EMOJI_ID),
                                      rbtn(BTN_RECHARGE, "➕", "success")]], resize_keyboard=True)
    except:
        return ReplyKeyboardMarkup([[KeyboardButton(BTN_CANCEL)],
                                     [KeyboardButton(BTN_BALANCE), KeyboardButton(BTN_RECHARGE)]],
                                    resize_keyboard=True)

def main_inline_kb(uid):
    rows = [
        [ibtn("BUY SERVER (1)","buy1",custom_id=SERVER_EMOJI_IDS["s1"],style="primary"),
         ibtn("BUY SERVER (2)","buy2",custom_id=SERVER_EMOJI_IDS["s2"],style="primary")],
        [ibtn("BUY SERVER (3)","buy3",custom_id=SERVER_EMOJI_IDS["s3"],style="primary"),
         ibtn("BUY WHATSAPP (4)","buywa",custom_id=SERVER_EMOJI_IDS["wa"],style="danger")],
        [ibtn("RECHARGE","recharge",emoji="💳",style="success"),
         ibtn("MY PROFILE","profile",custom_id=SERVER_EMOJI_IDS["profile"],style="primary")],
        [ibtn("REFER FRIENDS","refer",emoji="👥",style="primary"),
         ibtn("REDEEM","redeem",emoji="🎁",style="success")],
        [ibtn("SUPPORT","support",emoji="🆘",style="danger"),
         ibtn("BALANCE","balance",custom_id=BALANCE_PREMIUM_EMOJI_ID,style="primary")],
    ]
    if is_admin(uid): rows.append([ibtn("ADMIN PANEL","admin_panel",emoji="🔐",style="danger")])
    return InlineKeyboardMarkup(rows)

def _build_cat_button(name, cb, fb_emoji="🎯"):
    cid = _cat_custom_emoji_id(name)
    prefix = _cat_display_prefix(name)
    disp = f"{prefix}{name}" if prefix else name
    if cid:
        return ibtn(disp, cb, custom_id=cid, style="primary")
    return ibtn(name, cb, emoji=fb_emoji, style="primary")

def get_servers(server="SERVER2"):
    return cur.execute("""SELECT id, name, emoji FROM custom_categories WHERE server=? AND active=1 ORDER BY sort_order, id""", (server,)).fetchall()

def get_file_products(section):
    return cur.execute("""SELECT * FROM file_products WHERE section=? AND active=1 ORDER BY sort_order, id""", (section,)).fetchall()

def category_select_kb(prefix="setcat"):
    rows = []; all_cats = []
    for c in cur.execute("SELECT name, emoji FROM custom_categories WHERE server='SERVER2' AND active=1 ORDER BY sort_order, id").fetchall():
        all_cats.append((f"{c['emoji']} {c['name']}", f"SERVER2|{c['name']}"))
    for i in range(0, len(all_cats), 2):
        row = []
        for j in range(2):
            if i+j < len(all_cats):
                lbl, cb = all_cats[i+j]
                row.append(ibtn(lbl, f"{prefix}|{cb}", style="primary"))
        rows.append(row)
    rows.append([ibtn("CANCEL", "cancel", emoji="❌", style="danger")])
    return InlineKeyboardMarkup(rows)

def server2_kb():
    try:
        cats = get_servers("SERVER2")
        rows = []
        for i in range(0, len(cats), 2):
            row = []
            for j in range(2):
                if i+j < len(cats):
                    srv = cats[i+j]
                    row.append(_build_cat_button(srv["name"], f"srv2:{srv['name']}", fb_emoji=srv["emoji"]))
            rows.append(row)
        rows.append([ibtn("MAIN MENU","home",emoji="🔙",style="danger")])
        return InlineKeyboardMarkup(rows)
    except Exception as e:
        log.error(f"server2_kb: {e}")
        rows = []
        try:
            for c in cur.execute("SELECT name FROM custom_categories WHERE server='SERVER2' AND active=1 ORDER BY sort_order, id").fetchall():
                rows.append([InlineKeyboardButton(text=str(c["name"])[:40], callback_data=f"srv2:{c['name']}")])
        except: pass
        rows.append([ibtn("MAIN MENU","home",emoji="🔙",style="danger")])
        return InlineKeyboardMarkup(rows)

def server3_kb():
    return InlineKeyboardMarkup([
        [ibtn("PANELS","srv3:PANNELS",emoji="📦",style="primary")],
        [ibtn("SOURCE CODE","srv3:SOURCE CODE",emoji="💻",style="primary")],
        [ibtn("OSINT APIS","srv3:OSINT APIS",custom_id=SERVER_EMOJI_IDS["osint"],style="primary")],
        [ibtn("MAIN MENU","home",emoji="🔙",style="danger")]])

def whatsapp_kb():
    cats = get_servers("WHATSAPP")
    rows = []
    for i in range(0, len(cats), 2):
        row = []
        for j in range(2):
            if i+j < len(cats):
                srv = cats[i+j]
                row.append(_build_cat_button(srv["name"], f"srvwa:{srv['name']}", fb_emoji=srv["emoji"]))
        rows.append(row)
    rows.append([ibtn("MAIN MENU","home",emoji="🔙",style="danger")])
    return InlineKeyboardMarkup(rows)


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from config import log
from context import cur
from database import is_admin
from emojis import (
    BALANCE_PREMIUM_EMOJI_ID, EMOJI_MAP, FLAG_IDS, SERVER_EMOJI_IDS, _cat_custom_emoji_id,
    _cat_display_prefix
)
