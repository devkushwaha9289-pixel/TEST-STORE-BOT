#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — devices.py
Telethon device management (list/logout sessions) and OTP message sender.
"""

import re, time
from datetime import timezone
from telegram import InlineKeyboardMarkup
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest

# ============================================================
# DEVICE MANAGEMENT
# ============================================================
async def _get_active_devices(client):
    devices = []
    try:
        result = await client(GetAuthorizationsRequest())
        for auth in result.authorizations:
            devices.append({
                'hash': getattr(auth, 'hash', None),
                'device_model': getattr(auth, 'device_model', 'Unknown') or 'Unknown',
                'platform': getattr(auth, 'platform', 'Unknown') or 'Unknown',
                'app_name': getattr(auth, 'app_name', 'Unknown') or 'Unknown',
                'app_version': getattr(auth, 'app_version', 'Unknown') or 'Unknown',
                'date_created': getattr(auth, 'date_created', None),
                'date_active': getattr(auth, 'date_active', None),
                'ip': getattr(auth, 'ip', 'Unknown') or 'Unknown',
                'country': getattr(auth, 'country', '') or '',
                'region': getattr(auth, 'region', '') or '',
                'city': getattr(auth, 'city', '') or '',
                'current': bool(getattr(auth, 'current', False)),
            })
    except Exception as e:
        log.error(f"_get_active_devices: {e}")
    return devices

async def _logout_device(client, session_hash):
    try:
        h = session_hash
        if isinstance(h, str): h = int(h)
        await client(ResetAuthorizationRequest(h))
        return True
    except Exception as e:
        log.error(f"_logout_device: {e}")
        return False

def _fmt_dt_ist(dt):
    if not dt: return "—"
    try:
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).strftime('%d-%m-%Y %I:%M %p')
    except Exception:
        try: return str(dt)[:19]
        except: return "—"

async def show_manage_devices(update, phone):
    uid = update.effective_user.id
    q = update.callback_query
    if phone not in active_orders:
        try: await q.answer("⚠️ Session expired. Please buy again.", show_alert=True)
        except: pass
        return
    order = active_orders[phone]
    client = order.get('client')
    if not client:
        try: await q.answer("⚠️ Session missing.", show_alert=True)
        except: pass
        return
    try: await q.answer("📱 Fetching devices...")
    except: pass
    devices = await _get_active_devices(client)
    if not devices:
        kb = InlineKeyboardMarkup([
            [ibtn("🔄 Retry", f"manage_devices|{phone}", emoji="🔄", style="primary")],
            [ibtn("🔙 Back to OTP", f"back_to_otp|{phone}", emoji="🔙", style="success")],
        ])
        await send_rich_async(uid, [make_heading("📱 ACTIVE DEVICES", 2),
            make_paragraph("⚠️ No devices found or unable to fetch device list.")],
            reply_markup=kb.to_dict(),
            fallback_text="📱 No devices found.",
            edit_query=q)
        return
    total = len(devices)
    current_count = sum(1 for d in devices if d['current'])
    other_count = total - current_count
    header_rows = [
        ["ℹ️ INFO", "📋 VALUE"],
        ["📱 Total Devices", str(total)],
        ["⭐ Current", str(current_count)],
        ["👥 Other Devices", str(other_count)],
        ["⚠️ Tip", "Logout unknown devices!"],
    ]
    blocks = [
        make_heading("⚠️ SECURITY CHECK REQUIRED", 2),
        make_paragraph("Review all active devices below. Logout any device you don't recognize!"),
        make_heading(f"📱 Active Devices — +{phone}", 3),
        make_table(header_rows),
    ]
    kb_rows = []
    for idx, dev in enumerate(devices, 1):
        model = str(dev.get('device_model', 'Unknown'))[:40]
        platform = str(dev.get('platform', 'Unknown'))[:30]
        app_name = str(dev.get('app_name', 'Unknown'))[:30]
        app_ver = str(dev.get('app_version', 'Unknown'))[:20]
        ip = str(dev.get('ip', 'Unknown'))[:30]
        loc_parts = [dev.get('city', ''), dev.get('region', ''), dev.get('country', '')]
        location = ", ".join([p for p in loc_parts if p]) or "—"
        cur_tag = " ⭐ CURRENT" if dev.get('current') else ""
        dev_icon = "📱" if "phone" in model.lower() or "android" in platform.lower() or "ios" in platform.lower() else "💻"
        hash_short = str(dev.get('hash', 'N/A'))[:8]
        rows = [
            ["ℹ️ INFO", "📋 DETAIL"],
            ["🔢 Device", f"{dev_icon} #{idx}{cur_tag}"],
            ["📱 Model", model],
            ["🖥️ Platform", platform],
            ["📦 App", f"{app_name} v{app_ver}"],
            ["🌐 IP", ip],
            ["📍 Location", location[:40]],
            ["📅 Created", _fmt_dt_ist(dev.get('date_created'))],
            ["⏰ Last Active", _fmt_dt_ist(dev.get('date_active'))],
            ["🆔 Session", f"{hash_short}..."],
        ]
        blocks.append(make_table(rows))
        if not dev.get('current') and dev.get('hash'):
            kb_rows.append([
                ibtn(f"❌ Logout Device #{idx}", f"logout_device|{phone}|{dev['hash']}",
                     emoji="❌", style="danger")
            ])
    kb_rows.append([
        ibtn("🔄 Refresh", f"manage_devices|{phone}", emoji="🔄", style="primary"),
    ])
    kb_rows.append([
        ibtn("🔙 Back to OTP", f"back_to_otp|{phone}", emoji="🔙", style="success"),
    ])
    await send_rich_async(
        uid, blocks,
        reply_markup=InlineKeyboardMarkup(kb_rows).to_dict(),
        fallback_text=f"📱 Active Devices ({total}) — {other_count} other device(s)",
        edit_query=q,
    )

async def handle_logout_device(update, phone, session_hash):
    uid = update.effective_user.id
    q = update.callback_query
    if phone not in active_orders:
        try: await q.answer("⚠️ Session expired.", show_alert=True)
        except: pass
        return
    order = active_orders[phone]
    client = order.get('client')
    if not client:
        try: await q.answer("⚠️ Session missing.", show_alert=True)
        except: pass
        return
    try: await q.answer("🔒 Logging out device...")
    except: pass
    ok = await _logout_device(client, session_hash)
    if ok:
        try: await q.answer("✅ Device logged out!", show_alert=True)
        except: pass
        await show_manage_devices(update, phone)
    else:
        try: await q.answer("❌ Failed to logout device. Try again.", show_alert=True)
        except: pass

async def back_to_otp_view(update, phone):
    uid = update.effective_user.id
    q = update.callback_query
    if phone not in active_orders:
        try: await q.answer("⚠️ Session expired.", show_alert=True)
        except: pass
        return
    order = active_orders[phone]
    client = order.get('client')
    st = order.get('start', time.time())
    code = None
    try:
        msgs = await client.get_messages(777000, limit=5)
        for m in msgs:
            if m.date.timestamp() > st - 10 and m.message:
                mm = re.search(OTP_REGEX, m.message)
                if mm and "Login detected" not in m.message:
                    code = mm.group(); break
    except Exception as e:
        log.error(f"back_to_otp_view: {e}")
    if code:
        await send_otp_rich(
            uid, phone, order.get('country', ''), order.get('c_icon', '🌍'),
            code, order.get('twofa', 'None'),
            edit_query=q, masked=False, title="✅ LATEST OTP"
        )
    else:
        try: await q.answer("⏳ No OTP found yet. Tap Get OTP Again.", show_alert=True)
        except: pass

# ============================================================
# OTP
# ============================================================
async def send_otp_rich(uid, phone, country, c_icon, code, twofa, edit_query=None, masked=False, title="✅ LATEST OTP"):
    if masked:
        dp = mask_phone_public(phone); do = mask_otp_public(code); d2 = mask_2fa_public(twofa)
    else:
        dp = phone; do = code; d2 = twofa if twofa != "None" else "Disabled"
    rows = [["ℹ️ INFO","📋 DETAIL"],["📱 Phone", dp],["🏳️ Country", f"{c_icon} {country}"],
            ["🔢 OTP", do],["🔐 2FA", d2],["📅 Time", _now_str()]]
    fb = (f"<b>{title}</b>\n📱 <code>{dp}</code>\n🏳️ {c_icon} {country}\n"
          f"🔢 <code>{do}</code>\n🔐 {d2}")
    kb = None
    if not masked:
        kb = InlineKeyboardMarkup([
            [ibtn("Get OTP Again", callback_data=f"get_otp|{phone}", emoji="🔄", style="primary")],
            [ibtn("Manage Devices", callback_data=f"manage_devices|{phone}", emoji="📱", style="success")],
            [ibtn("Finish & Logout", callback_data=f"logout_bot|{phone}", emoji="🚪", style="danger")],
        ])
    await send_rich_async(uid, [make_heading(title, 2), make_table(rows)],
                          reply_markup=kb.to_dict() if kb else None,
                          fallback_text=fb, edit_query=edit_query, show_placeholder=False)


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn
from config import IST, OTP_REGEX, log
from logs import _now_str, mask_2fa_public, mask_otp_public, mask_phone_public
from rich_ui import make_heading, make_paragraph, make_table, send_rich_async
from state import active_orders
