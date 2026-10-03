#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — osint.py
OSINT admin API helpers, OSINT admin settings view and OSINT API purchase.
"""

import re, time, asyncio, aiohttp
from html import escape
from urllib.parse import quote
from telegram import InlineKeyboardMarkup

# ============================================================
# OSINT ADMIN API HELPERS
# ============================================================
_osint_token_cache = {}
_osint_token_lock = asyncio.Lock()

def get_osint_base_url():
    v = (get_setting('osint_base_url', OSINT_DEFAULT_BASE_URL) or '').strip()
    return (v or OSINT_DEFAULT_BASE_URL).rstrip('/')

def get_osint_owner_id():
    return (get_setting('osint_owner_id', '') or '').strip()

def get_osint_secret_key():
    return (get_setting('osint_secret_key', '') or '').strip()

def get_osint_docs_file_id():
    return (get_setting('osint_docs_file_id', '') or '').strip()

def osint_is_configured():
    return bool(get_osint_owner_id() and get_osint_secret_key())

def _osint_cache_key():
    return f"{current_bot_username()}::{get_osint_owner_id()}::{get_osint_base_url()}"

def osint_clear_cached_token():
    _osint_token_cache.pop(_osint_cache_key(), None)

def osint_prefix_from_endpoint(endpoint):
    e = str(endpoint or "").strip().lstrip('/')
    if not e:
        return "API"
    low = e.lower()
    special = {
        'voter_info': 'VOTER', 'voterinfo': 'VOTER', 'voter': 'VOTER',
        'mobile2info': 'NUM2INFO', 'mobile2infov2': 'NUM2INFOV2',
        'num': 'NUM',
        'tg2num': 'TG2NUM',
        'mobile2hpgas': 'HPGAS',
        'vehicle_challan': 'CHALLAN',
        'adhar2rationno': 'RATION', 'adhar2rationnov2': 'RATIONV2',
    }
    if low in special:
        return special[low]
    base = re.sub(r'[^A-Za-z0-9]', '', e)
    if not base:
        base = "API"
    return base.upper()[:14]

async def osint_admin_login(force=False):
    if not osint_is_configured():
        return None, "Owner credentials not set"
    cache_key = _osint_cache_key()
    now = time.time()
    cache = _osint_token_cache.get(cache_key)
    if not force and cache and cache.get('token') and cache.get('expires_at', 0) > now + 60:
        return cache['token'], None
    async with _osint_token_lock:
        now = time.time()
        cache = _osint_token_cache.get(cache_key)
        if not force and cache and cache.get('token') and cache.get('expires_at', 0) > now + 60:
            return cache['token'], None
        base = get_osint_base_url()
        oid = get_osint_owner_id()
        sk = get_osint_secret_key()
        url = f"{base}/{OSINT_ADMIN_PATH}/login?owner_id={quote(oid)}&secret_key={quote(sk)}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    try:
                        d = await r.json(content_type=None)
                    except Exception:
                        d = None
                    if isinstance(d, dict) and d.get('success') and d.get('token'):
                        hrs = float(d.get('expires_in_hours', 12) or 12)
                        _osint_token_cache[cache_key] = {
                            'token': d['token'],
                            'expires_at': now + (hrs * 3600) - 30,
                        }
                        return d['token'], None
                    err = (d or {}).get('message') or f"HTTP {r.status}"
                    return None, str(err)
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

async def osint_generate_key(endpoint, days=None):
    if not osint_is_configured():
        return None, "OSINT owner credentials not configured"
    api = str(endpoint or '').strip()
    if not api:
        return None, "No endpoint configured for this API"
    if not api.startswith('/'):
        api = '/' + api
    days = int(days if days is not None else OSINT_DEFAULT_KEY_DAYS)
    prefix = osint_prefix_from_endpoint(api)
    base = get_osint_base_url()
    oid = get_osint_owner_id()
    sk = get_osint_secret_key()
    url = (f"{base}/{OSINT_ADMIN_PATH}/generate-key?"
           f"owner_id={quote(oid)}&secret_key={quote(sk)}&"
           f"prefix={quote(prefix)}&access=single&api={quote(api)}&days={days}")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=25)) as r:
                try:
                    d = await r.json(content_type=None)
                except Exception:
                    d = None
                if isinstance(d, dict) and d.get('success') and isinstance(d.get('key'), dict):
                    k = d['key']
                    return {
                        'key': str(k.get('key') or ''),
                        'prefix': prefix,
                        'endpoint': api,
                        'expiry': k.get('expiry'),
                        'days': k.get('days', days),
                        'access': k.get('access', 'single'),
                    }, None
                err = (d or {}).get('message') or f"HTTP {r.status}"
                return None, str(err)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


# ============================================================
# OSINT ADMIN PANEL VIEW
# ============================================================
async def view_admin_osint_settings(update):
    uid = update.effective_user.id
    if not is_admin(uid): return
    oid = get_osint_owner_id() or "❌ NOT SET"
    sk_set = "✅ SET" if get_osint_secret_key() else "❌ NOT SET"
    base = get_osint_base_url()
    docs = get_osint_docs_file_id()
    docs_disp = "✅ SET" if docs else "❌ NOT SET"
    cache = _osint_token_cache.get(_osint_cache_key())
    now = time.time()
    if cache and cache.get('token') and cache.get('expires_at', 0) > now:
        ttl = int(cache['expires_at'] - now)
        tok_disp = f"🟢 Valid ({ttl//60}m {ttl%60}s)"
    else:
        tok_disp = "⚪ None"
    api_count = cur.execute(
        "SELECT COUNT(*) FROM file_products WHERE section='OSINT APIS' AND active=1"
    ).fetchone()[0]
    missing_ep = cur.execute("""SELECT COUNT(*) FROM file_products
        WHERE section='OSINT APIS' AND active=1
        AND (api_endpoint IS NULL OR api_endpoint='')""").fetchone()[0]
    rows = [
        [ibtn("SET OWNER ID","adm_osint_set_oid",emoji="👤",style="primary"),
         ibtn("SET SECRET","adm_osint_set_skey",emoji="🔑",style="primary")],
        [ibtn("SET BASE URL","adm_osint_set_url",emoji="🌐",style="primary")],
        [ibtn("📤 UPLOAD DOCS","adm_osint_upload_docs",emoji="📤",style="success")],
        [ibtn("👁 VIEW DOCS","adm_osint_view_docs",emoji="📖",style="primary"),
         ibtn("🗑 DELETE DOCS","adm_osint_del_docs",emoji="🗑️",style="danger")],
        [ibtn("🧪 TEST LOGIN","adm_osint_test",emoji="🧪",style="success"),
         ibtn("🔄 CLEAR TOKEN","adm_osint_clear_token",emoji="🔄",style="primary")],
        [ibtn("📋 MANAGE APIs","adm_s3_view|OSINT APIS|1",emoji="📋",style="primary")],
        [ibtn("BACK","admin_panel",emoji="🔙",style="primary")]]
    await send_rich_async(uid, [make_heading("🔍 OSINT API SETTINGS", 2),
        make_paragraph("Users get a 30-day single-endpoint key + docs file after purchase."),
        make_table([["⚙️ KEY","📋 VALUE"],
                    ["👤 Owner ID", oid[:25]],
                    ["🔑 Secret", sk_set],
                    ["🌐 Base URL", base[:55]],
                    ["📖 Docs File", docs_disp],
                    ["🔐 Token", tok_disp],
                    ["📦 Active APIs", str(api_count)],
                    ["⚠️ Missing EP", str(missing_ep)]])],
        reply_markup=InlineKeyboardMarkup(rows).to_dict(),
        fallback_text="🔍 OSINT API SETTINGS", edit_query=_edit_query_of(update))


async def _process_osint_api_purchase(update, p):
    uid = update.effective_user.id
    r = get_user(uid)
    price = p['price']
    d = safe_get(r, "discount", 0)
    final = price if d == 0 else int(price * (100 - d) / 100)

    if not osint_is_configured():
        kb = InlineKeyboardMarkup([
            [ibtn("CONTACT SUPPORT", url=get_support_url(), emoji="📞", style="primary")],
            [ibtn("HOME","home",emoji="🏠",style="primary")]])
        try:
            await update.callback_query.message.reply_text(
                f"{emo('❌')} <b>API service is not configured.</b>\n\n"
                f"Please contact support to enable OSINT API purchase.",
                parse_mode="HTML", reply_markup=kb)
        except: pass
        return

    endpoint = ''
    try: endpoint = (p['api_endpoint'] or '').strip()
    except: endpoint = ''
    if not endpoint:
        try: endpoint = (p['file_link'] or '').strip()
        except: endpoint = ''
    if not endpoint:
        kb = InlineKeyboardMarkup([
            [ibtn("CONTACT SUPPORT", url=get_support_url(), emoji="📞", style="primary")],
            [ibtn("HOME","home",emoji="🏠",style="primary")]])
        try:
            await update.callback_query.message.reply_text(
                f"{emo('❌')} <b>API endpoint not configured.</b>\n\n"
                f"Please contact support.",
                parse_mode="HTML", reply_markup=kb)
        except: pass
        return

    if safe_get(r, "balance", 0) < final:
        kb = InlineKeyboardMarkup([
            [ibtn("RECHARGE","recharge",emoji="💳",style="success")],
            [ibtn("HOME","home",emoji="🏠",style="primary")]])
        try:
            await update.callback_query.message.reply_text(
                f"<b>{emo('❌')} INSUFFICIENT BALANCE</b>\n\n"
                f"Need: <b>₹{final}</b>\nHave: ₹{safe_get(r,'balance',0)}",
                parse_mode="HTML", reply_markup=kb)
        except: pass
        return

    async with get_user_lock(uid):
        old_bal = safe_get(r, "balance", 0)
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
                    (final, uid, final))
        if cur.rowcount == 0:
            return
        db.commit()
        record_balance_history(uid, -final, "purchase", "server3:OSINT APIS",
                               f"API {p['name']}", old_bal, old_bal - final)

    try:
        await update.callback_query.message.reply_text(
            f"{emo('⏳')} <b>Generating your API key…</b>\n\n"
            f"📦 {escape(p['name'])}\n🔗 {escape(endpoint)}\n🕒 Valid for {OSINT_DEFAULT_KEY_DAYS} days",
            parse_mode="HTML")
    except: pass

    key_info, err = await osint_generate_key(endpoint, days=OSINT_DEFAULT_KEY_DAYS)

    if not key_info:
        async with get_user_lock(uid):
            r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
            old2 = r2["balance"] if r2 else 0
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (final, uid)); db.commit()
            record_balance_history(uid, final, "refund", "server3:OSINT APIS",
                                   "Key generation failed", old2, old2 + final)
        kb = InlineKeyboardMarkup([
            [ibtn("CONTACT SUPPORT", url=get_support_url(), emoji="📞", style="primary")],
            [ibtn("HOME","home",emoji="🏠",style="primary")]])
        try:
            await update.callback_query.message.reply_text(
                f"{emo('❌')} <b>API Key generation failed.</b>\n\n"
                f"💰 ₹{final} has been refunded to your balance.\n\n"
                f"Error: <code>{escape(str(err)[:120])}</code>",
                parse_mode="HTML", reply_markup=kb)
        except: pass
        try:
            await _send_log_rich([make_heading("⚠️ OSINT KEY FAILED", 2),
                make_table([["ℹ️ INFO","📋 DETAIL"],["👤 User", str(uid)],
                            ["🎯 API", p['name']],["🔗 Endpoint", endpoint],
                            ["💰 Refunded", f"₹{final}"],["❌ Error", str(err)[:120]],
                            ["📅 Time", _now_str()]])], "OSINT key fail")
        except: pass
        return

    oid = generate_unique_order_id(uid)
    async with get_user_lock(uid):
        cur.execute("""INSERT INTO orders (user_id, country, year, price, phone, otp, section)
                    VALUES (?,?,?,?,?,?,?)""",
                    (uid, 'OSINT APIS', now_ist().year, final, p['name'],
                     (key_info.get('key') or '')[:40], 'OSINT APIS'))
        cur.execute("""UPDATE users SET total_purchases=total_purchases+1,
                    total_spent=total_spent+? WHERE user_id=?""", (final, uid))
        db.commit()
        r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()

    await log_purchase_both(uid, oid, p['name'], final, "N/A", "N/A", "N/A",
                            r2["balance"] if r2 else 0, status="Completed", is_file=True,
                            deep_link=build_deep_link_s3(p['section'], p['item_code']))

    base_url = get_osint_base_url()
    api_key = key_info.get('key') or ''
    endpoint_final = key_info.get('endpoint') or endpoint
    expiry_str = str(key_info.get('expiry') or '—')
    days_val = key_info.get('days') or OSINT_DEFAULT_KEY_DAYS
    usage_url = f"{base_url}{endpoint_final}?key={api_key}&<params>"

    rows_main = [
        ["ℹ️ INFO", "📋 DETAIL"],
        ["📦 API", str(p['name'])],
        ["🆔 Order", str(oid)],
        ["💰 Paid", f"₹{final}"],
        ["🎯 Endpoint", str(endpoint_final)],
        ["📅 Validity", f"{int(days_val)} days"],
        ["⏰ Expiry", str(expiry_str)],
    ]
    rows_creds = [
        ["🌐 BASE URL", str(base_url)],
        ["🔑 API KEY", str(api_key)],
    ]
    rows_example = [
        ["📝 EXAMPLE CALL", str(usage_url)],
    ]
    rows_footer = [
        ["📖 Docs", "Attached file below"],
        ["⚠️ IMPORTANT", "Save this key! Do not share it."],
    ]

    kb_rows = []
    if get_osint_docs_file_id():
        kb_rows.append([ibtn("📖 RE-SEND DOCS", "osint_show_docs", emoji="📖", style="primary")])
    kb_rows.append([ibtn("HOME", "home", emoji="🏠", style="primary")])
    kb = InlineKeyboardMarkup(kb_rows)

    blocks = [
        make_heading(STORE_HEADER, 2),
        make_heading("✅ API PURCHASE SUCCESSFUL!", 3),
        make_table(rows_main),
        make_table(rows_creds),
        make_table(rows_example),
        make_table(rows_footer),
    ]

    fallback = (
        f"✅ API PURCHASE SUCCESSFUL!\n"
        f"📦 {p['name']}\n🆔 {oid}\n💰 ₹{final}\n"
        f"🌐 {base_url}\n🔑 {api_key}\n"
        f"🎯 {endpoint_final}\n📅 {int(days_val)} days\n⏰ {expiry_str}\n"
        f"📝 {usage_url}\n"
        f"⚠️ Save this key! Do not share it."
    )

    try:
        await send_rich_async(uid, blocks, reply_markup=kb.to_dict(),
                              fallback_text=fallback, show_placeholder=False)
    except Exception as e:
        log.warning(f"OSINT rich delivery msg: {e}")
        try:
            await _tg_post("sendMessage", {"chat_id": uid, "text": fallback,
                "parse_mode": "HTML", "reply_markup": kb.to_dict(),
                "disable_web_page_preview": True})
        except: pass

    docs_fid = get_osint_docs_file_id()
    if docs_fid:
        try:
            await _tg_post("sendDocument", {"chat_id": uid, "document": docs_fid,
                "caption": f"{emo('📖')} <b>OSINT API Documentation</b>\n"
                           f"<i>Save this file for future reference.</i>",
                "parse_mode": "HTML"}, timeout=30)
        except Exception as e:
            log.warning(f"OSINT docs delivery: {e}")
    else:
        try:
            await _tg_post("sendMessage", {"chat_id": uid,
                "text": f"{emo('ℹ️')} Documentation will be shared by support shortly.",
                "parse_mode": "HTML"})
        except: pass

    try: asyncio.create_task(process_referral_bonus(uid, final))
    except: pass


async def process_osint_purchase_from_miniapp(uid, prod_id):
    """OSINT API purchase worker for the Mini App (returns a dict, raises RuntimeError on failure)."""
    p = cur.execute("SELECT * FROM file_products WHERE id=? AND active=1", (prod_id,)).fetchone()
    if not p:
        raise RuntimeError("Product not found")
    if not osint_is_configured():
        raise RuntimeError("API service is not configured. Contact support.")
    endpoint = ''
    try: endpoint = (p['api_endpoint'] or '').strip()
    except Exception: endpoint = ''
    if not endpoint:
        try: endpoint = (p['file_link'] or '').strip()
        except Exception: endpoint = ''
    if not endpoint:
        raise RuntimeError("API endpoint not configured. Contact support.")

    r = get_user(uid)
    price = int(p['price'])
    d = int(safe_get(r, "discount", 0) or 0)
    final = price if d == 0 else int(price * (100 - d) / 100)
    async with get_user_lock(uid):
        old_bal = int(safe_get(r, "balance", 0) or 0)
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (final, uid, final))
        if cur.rowcount != 1:
            raise RuntimeError(f"Insufficient balance. Need \u20b9{final}")
        db.commit()
        record_balance_history(uid, -final, "purchase", "server3:OSINT APIS",
                               f"API {p['name']}", old_bal, old_bal - final)

    key_info, err = await osint_generate_key(endpoint, days=OSINT_DEFAULT_KEY_DAYS)
    if not key_info:
        async with get_user_lock(uid):
            r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
            old2 = r2["balance"] if r2 else 0
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (final, uid)); db.commit()
            record_balance_history(uid, final, "refund", "server3:OSINT APIS",
                                   "Key generation failed", old2, old2 + final)
        raise RuntimeError(f"API key generation failed. \u20b9{final} refunded. ({str(err)[:80]})")

    oid = generate_unique_order_id(uid)
    async with get_user_lock(uid):
        cur.execute("""INSERT INTO orders (user_id, country, year, price, phone, otp, section)
                    VALUES (?,?,?,?,?,?,?)""",
                    (uid, 'OSINT APIS', now_ist().year, final, p['name'],
                     (key_info.get('key') or '')[:40], 'OSINT APIS'))
        cur.execute("UPDATE users SET total_purchases=COALESCE(total_purchases,0)+1, "
                    "total_spent=COALESCE(total_spent,0)+? WHERE user_id=?", (final, uid))
        db.commit()
        r2 = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
    try:
        await log_purchase_both(uid, oid, p['name'], final, "N/A", "N/A", "N/A",
                                r2["balance"] if r2 else 0, status="Completed", is_file=True,
                                deep_link=build_deep_link_s3(p['section'], p['item_code']))
    except Exception as e:
        log.warning(f"OSINT miniapp log: {e}")
    try: asyncio.create_task(process_referral_bonus(uid, final))
    except Exception: pass

    api_key = key_info.get('key') or ''
    endpoint_final = key_info.get('endpoint') or endpoint
    base_url = get_osint_base_url()
    return {'ok': True, 'order_id': oid, 'amount': final, 'name': p['name'],
            'link': f"{base_url}{endpoint_final}?key={api_key}",
            'api_endpoint': endpoint_final, 'api_key': api_key,
            'item_code': p['item_code'] or '',
            'message': 'Purchase successful. API key generated.'}


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn
from config import (
    OSINT_ADMIN_PATH, OSINT_DEFAULT_BASE_URL, OSINT_DEFAULT_KEY_DAYS, STORE_HEADER, log,
    now_ist
)
from context import cur, current_bot_username, db
from database import get_setting, get_support_url, get_user, is_admin, safe_get
from emojis import emo
from history import record_balance_history
from logs import _now_str, log_purchase_both
from payments import process_referral_bonus
from rich_ui import (
    _edit_query_of, _send_log_rich, _tg_post, build_deep_link_s3, make_heading,
    make_paragraph, make_table, send_rich_async
)
from state import get_user_lock
from utils import generate_unique_order_id
