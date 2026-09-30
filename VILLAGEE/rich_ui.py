#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — rich_ui.py
Rich (bot-API 9.x) message blocks, sender helpers and deep-link buttons.
"""

import json, asyncio, requests

# ============================================================
# RICH HELPERS
# ============================================================
def ce(eid, fb): return {"type":"custom_emoji","custom_emoji_id":str(eid),"alternative_text":fb}

def rt_split(text):
    text = str(text)
    if not text: return [""]
    parts = []; i = 0
    combined = dict(EMOJI_MAP); combined.update(FLAG_IDS)
    sorted_emojis = sorted(combined.items(), key=lambda x: -len(x[0]))
    while i < len(text):
        m = False
        for e, eid in sorted_emojis:
            if text.startswith(e, i):
                parts.append(ce(eid, e)); i += len(e); m = True; break
        if not m:
            np = len(text)
            for e, _ in sorted_emojis:
                p = text.find(e, i + 1)
                if p != -1 and p < np: np = p
            parts.append(text[i:np]); i = np
    merged = []
    for p in parts:
        if isinstance(p, str) and merged and isinstance(merged[-1], str): merged[-1] += p
        else: merged.append(p)
    return merged if merged else [""]

def tc(text, header=False, align="left"):
    c = {"text": rt_split(strip_html_for_rich(text)), "align": align, "valign": "middle"}
    if header: c["is_header"] = True
    return c

def make_table(rows, bordered=True, striped=True, compact=True, header_row=True):
    cells = []
    for idx, row in enumerate(rows):
        is_hdr = header_row and idx == 0
        cells.append([tc(c, header=is_hdr) for c in row])
    return {"type":"table","cells":cells,"is_bordered":bordered,"is_striped":striped}

def make_heading(text, size=2):
    return {"type":"heading","text": rt_split(strip_html_for_rich(text)),"size":size}

def make_paragraph(text):
    return {"type":"paragraph","text": rt_split(strip_html_for_rich(text))}

def build_rich_buttons_block(buttons, align="center"):
    if not buttons: return None
    rb = []
    for b in buttons:
        name = b.get('name', 'Button')
        if b.get('type') == 'rich' and b.get('emoji_id'):
            tp = [{"type":"custom_emoji","custom_emoji_id":str(b['emoji_id']),
                   "alternative_text": b.get('alternative_emoji') or '🔥'}, " " + name]
        else: tp = name
        rb.append({"text": tp, "style": b.get('style','primary'), "url": b.get('url','')})
    return {"type":"buttons","buttons":rb,"align":align} if rb else None

async def _send_rich_broadcast_msg(bot_token, chat_id, blocks, photo_file_id=None):
    payload = {"chat_id": chat_id, "rich_message": {"blocks": blocks}}
    if photo_file_id: payload["photo"] = photo_file_id
    try:
        r = await asyncio.to_thread(requests.post,
            f"https://api.telegram.org/bot{bot_token}/sendRichMessage",
            json=payload, timeout=30)
        d = r.json()
        if d.get("ok"): return d.get("result")
    except Exception as e: log.error(f"rich bcast: {e}")
    return None

async def _tg_post(endpoint, payload, files=None, timeout=20):
    return await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{current_ctx().token}/{endpoint}",
        json=payload, files=files, timeout=timeout)

async def _tg_send_photo_buffer(chat_id, png_bytes, caption, reply_markup=None, parse_mode="HTML", timeout=30):
    files = {'photo': ('qr.png', png_bytes, 'image/png')}
    data = {'chat_id': str(chat_id), 'caption': caption, 'parse_mode': parse_mode}
    if reply_markup is not None: data['reply_markup'] = json.dumps(reply_markup)
    return await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{current_ctx().token}/sendPhoto",
        data=data, files=files, timeout=timeout)


# ============================================================
# PER-ITEM PURCHASE BUTTON (deep-links)
# ============================================================
def _bot_uname():
    try:
        return current_ctx().username if current_ctx() else "bot"
    except:
        return "bot"

def build_deep_link_s1(category, country_name):
    cat_slug = slugify_category(category) or "all"
    cc = country_name_to_code(country_name)
    return f"https://t.me/{_bot_uname()}?start=buy_item_s1_{cat_slug}_{cc}"

def build_deep_link_s2(category, country_name):
    cat_slug = slugify_category(category) or "normal"
    cc = country_name_to_code(country_name)
    return f"https://t.me/{_bot_uname()}?start=buy_item_s2_{cat_slug}_{cc}"

def build_deep_link_s3(section, item_code):
    sec_slug = slugify_section(section) or "panels"
    return f"https://t.me/{_bot_uname()}?start=buy_item_s3_{sec_slug}_{item_code}"

def _purchase_button_block_from_link(deep_link):
    if not deep_link: return None
    return build_rich_buttons_block([{
        "name": "Purchase Now",
        "url": deep_link,
        "style": "success",
        "type": "rich",
        "emoji_id": PURCHASE_BUTTON_EMOJI_ID,
        "alternative_emoji": "🛒"
    }], align="center")

# ============================================================
# RICH SENDER
# ============================================================
def _blocks_to_fallback_text(blocks, fb):
    if fb: return fb
    try:
        parts = []
        for b in blocks or []:
            if isinstance(b, dict):
                t = b.get("text")
                if isinstance(t, list):
                    for p in t:
                        if isinstance(p, dict): parts.append(p.get("alternative_text",""))
                        else: parts.append(str(p))
                elif isinstance(t, str): parts.append(t)
        txt = " ".join(p for p in parts if p).strip()
        return txt[:3900] or "Please wait…"
    except: return "Please wait…"

async def send_rich_async(chat_id, blocks, reply_markup=None, fallback_text=None,
                          show_placeholder=True, edit_query=None):
    if edit_query is not None:
        msg_id = edit_query.message.message_id
        rp = {"chat_id": chat_id, "message_id": msg_id, "rich_message": {"blocks": blocks}}
        if reply_markup: rp["reply_markup"] = reply_markup
        try:
            r = await _tg_post("editMessageText", rp, timeout=20)
            if r.json().get("ok"): return
        except: pass
        try:
            r = await _tg_post("editRichMessage", rp, timeout=20)
            if r.json().get("ok"): return
        except: pass
        text = _blocks_to_fallback_text(blocks, fallback_text)
        pl = {"chat_id": chat_id, "message_id": msg_id, "text": text,
              "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_markup: pl["reply_markup"] = reply_markup
        try:
            r = await _tg_post("editMessageText", pl, timeout=20)
            if r.json().get("ok"): return
        except: pass
        try:
            fb = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True}
            if reply_markup: fb["reply_markup"] = reply_markup
            await _tg_post("sendMessage", fb, timeout=20)
        except: pass
        return
    placeholder_id = None
    if show_placeholder and edit_query is None:
        try:
            s = await _tg_post("sendMessage", {"chat_id": chat_id, "text": "🏠"}, timeout=10)
            placeholder_id = s.json().get("result", {}).get("message_id")
        except: pass
    payload = {"chat_id": chat_id, "rich_message": {"blocks": blocks}}
    if reply_markup: payload["reply_markup"] = reply_markup
    sent_ok = False
    try:
        r = await _tg_post("sendRichMessage", payload)
        if r.json().get("ok"): sent_ok = True
    except Exception as e: log.error(f"sendRichMessage: {e}")
    if not sent_ok and fallback_text:
        try:
            fb = {"chat_id": chat_id, "text": fallback_text, "parse_mode": "HTML",
                  "disable_web_page_preview": True}
            if reply_markup: fb["reply_markup"] = reply_markup
            await _tg_post("sendMessage", fb)
        except: pass
    if placeholder_id:
        try:
            await asyncio.sleep(0.3)
            await _tg_post("deleteMessage", {"chat_id": chat_id, "message_id": placeholder_id}, timeout=10)
        except: pass

def _edit_query_of(update):
    try: return getattr(update, "callback_query", None)
    except: return None

async def _deliver_rich_to_target(tcid, blocks, fb, reply_markup=None):
    source = get_log_source_chat(); msg_id = None
    if source and source != tcid:
        try:
            r = await _tg_post("sendRichMessage", {"chat_id": source, "rich_message": {"blocks": blocks}})
            d = r.json()
            if d.get("ok"): msg_id = d.get("result", {}).get("message_id")
        except: pass
    if msg_id:
        try:
            fr = await _tg_post("forwardMessage", {"chat_id": tcid, "from_chat_id": source,
                "message_id": msg_id}, timeout=25)
            fd = fr.json()
            if fd.get("ok"):
                fid = fd.get("result", {}).get("message_id")
                if reply_markup and fid:
                    try:
                        await _tg_post("editMessageReplyMarkup", {"chat_id": tcid,
                            "message_id": fid, "reply_markup": reply_markup})
                    except: pass
                return
        except: pass
    payload = {"chat_id": tcid, "rich_message": {"blocks": blocks}}
    if reply_markup: payload["reply_markup"] = reply_markup
    try:
        if (await _tg_post("sendRichMessage", payload)).json().get("ok"): return
    except: pass
    if fb:
        try:
            p = {"chat_id": tcid, "text": fb, "parse_mode": "HTML", "disable_web_page_preview": True}
            if reply_markup: p["reply_markup"] = reply_markup
            await _tg_post("sendMessage", p)
        except: pass

async def _send_log_rich(blocks, fb, reply_markup=None):
    targets = get_log_targets()
    if not targets: return
    await asyncio.gather(*[_deliver_rich_to_target(t, blocks, fb, reply_markup) for t in targets],
                          return_exceptions=True)

async def _send_user_log_rich(blocks, fb, reply_markup=None):
    target = get_user_log_channel()
    if not target: return
    await _deliver_rich_to_target(target, blocks, fb, reply_markup)

async def _deliver_rich_photo_to_target(tcid, photo_id, blocks, fb, reply_markup=None):
    source = get_log_source_chat(); msg_id = None
    if source and source != tcid:
        try:
            r = await _tg_post("sendRichMessage", {"chat_id": source,
                "rich_message": {"blocks": blocks}, "photo": photo_id}, timeout=30)
            d = r.json()
            if d.get("ok"): msg_id = d.get("result", {}).get("message_id")
        except: pass
    if msg_id:
        try:
            fr = await _tg_post("forwardMessage", {"chat_id": tcid, "from_chat_id": source,
                "message_id": msg_id}, timeout=30)
            fd = fr.json()
            if fd.get("ok"):
                fid = fd.get("result", {}).get("message_id")
                if reply_markup and fid:
                    try:
                        await _tg_post("editMessageReplyMarkup", {"chat_id": tcid,
                            "message_id": fid, "reply_markup": reply_markup})
                    except: pass
                return
        except: pass
    payload = {"chat_id": tcid, "rich_message": {"blocks": blocks}, "photo": photo_id}
    if reply_markup: payload["reply_markup"] = reply_markup
    try:
        if (await _tg_post("sendRichMessage", payload, timeout=30)).json().get("ok"): return
    except: pass
    if fb:
        try:
            p = {"chat_id": tcid, "photo": photo_id, "caption": fb, "parse_mode": "HTML"}
            if reply_markup: p["reply_markup"] = reply_markup
            await _tg_post("sendPhoto", p, timeout=30)
        except: pass

async def _send_log_photo_rich(photo_id, blocks, fb, reply_markup=None):
    targets = get_log_targets()
    if not targets: return
    await asyncio.gather(*[_deliver_rich_photo_to_target(t, photo_id, blocks, fb, reply_markup) for t in targets],
                          return_exceptions=True)


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from config import log
from context import current_ctx
from countries import country_name_to_code
from emojis import EMOJI_MAP, FLAG_IDS, PURCHASE_BUTTON_EMOJI_ID
from logs import get_log_source_chat, get_log_targets, get_user_log_channel
from utils import slugify_category, slugify_section, strip_html_for_rich
