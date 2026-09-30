#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — views.py
Main user views: maintenance, home, profile, purchase history, balance, refer, support, recharge, WhatsApp menu.
"""

from html import escape
from telegram import InlineKeyboardMarkup

# ============================================================
# MAINTENANCE
# ============================================================
async def show_maintenance(chat_id, kind="bot"):
    msgs = {
        "bot": f"<b>{emo('🚨')} BOT MAINTENANCE</b>\n\n{emo('🔧')} We are upgrading.\n{emo('⏰')} Try later.\n\n{emo('📞')} {get_contact_1()}",
        "buy1": f"<b>{emo('🚨')} SERVER 1 — MAINTENANCE</b>\n\n{emo('🔧')} Temporarily offline.",
        "buy2": f"<b>{emo('🚨')} SERVER 2 — MAINTENANCE</b>\n\n{emo('🔧')} Temporarily offline.",
        "buy3": f"<b>{emo('🚨')} SERVER 3 — MAINTENANCE</b>\n\n{emo('🔧')} Temporarily offline.",
    }
    msg = msgs.get(kind, msgs["bot"])
    try:
        await _tg_post("sendPhoto", {"chat_id": chat_id,
            "photo": get_setting('maintenance_image', MAINTENANCE_IMAGE),
            "caption": msg, "parse_mode": "HTML"})
    except:
        try: await _tg_post("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
        except: pass

# ============================================================
# MAIN VIEWS
# ============================================================
async def view_home(update):
    u = update.effective_user
    ensure_user(u.id, u.first_name or "", u.username or "", u.last_name or "")
    r = get_user(u.id)
    name = _full_name(safe_get(r,"first_name","") or "", safe_get(r,"last_name","") or "")
    blocks = [make_heading(STORE_HEADER, 2),
        make_table([["ℹ️ INFO","📋 DETAILS"],["👤 Name", name],["🆔 ID", str(safe_get(r, "user_id", u.id))],
            ["📅 Joined", str(safe_get(r, "joined_date", "N/A"))],
            ["💰 Balance", f"₹{safe_get(r, 'balance', 0):.1f}"],
            ["💳 Total Recharge", f"₹{safe_get(r, 'total_deposited', 0):.1f}"],
            ["📆 Today Recharge", f"₹{safe_get(r, 'today_deposited', 0):.1f}"],
            ["📦 Total Buy", str(safe_get(r, "total_purchases", 0))],
            ["📞 Contact", f"{get_contact_1()} | {get_contact_2()}"]])]
    fb = f"<b>{emo('🅱️')} {STORE_HEADER}</b>\n👤 {escape(name)}\n💰 ₹{safe_get(r,'balance',0):.1f}"
    try:
        await send_rich_async(u.id, blocks, reply_markup=main_inline_kb(u.id).to_dict(),
                              fallback_text=fb, edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_home: {e}")

async def view_profile(update):
    u = update.effective_user
    ensure_user(u.id, u.first_name or "", u.username or "", u.last_name or "")
    r = get_user(u.id)
    name = _full_name(safe_get(r,"first_name","") or "", safe_get(r,"last_name","") or "")
    blocks = [make_heading(STORE_HEADER, 2),
        make_table([["ℹ️ INFO","📋 DETAILS"],["👤 Name", name],["🆔 ID", str(safe_get(r, "user_id", u.id))],
            ["📅 Joined", str(safe_get(r, "joined_date", "N/A"))],
            ["💰 Balance", f"₹{safe_get(r,'balance',0):.1f}"],
            ["💳 Total Recharge", f"₹{safe_get(r,'total_deposited',0):.1f}"],
            ["📦 Purchased", str(safe_get(r, "total_purchases", 0))],
            ["💸 Total Spent", f"₹{safe_get(r, 'total_spent', 0):.1f}"],
            ["👥 Referrals", str(safe_get(r, "referral_count", 0))],
            ["🎁 Ref Earnings", f"₹{safe_get(r, 'referral_earnings', 0):.1f}"]])]
    kb = InlineKeyboardMarkup([
        [ibtn("📜 PURCHASE HISTORY","sec_hist_menu",emoji="👑",style="primary")],
        [ibtn("BALANCE HISTORY","bal_hist_1",custom_id=BALANCE_PREMIUM_EMOJI_ID,style="success")],
        [ibtn("BALANCE","balance",custom_id=BALANCE_PREMIUM_EMOJI_ID,style="primary"),
         ibtn("RECHARGE","recharge",emoji="➕",style="success")],
        [ibtn("MAIN MENU","home",emoji="🔙",style="danger")]])
    fb = f"<b>{emo('☯')} MY PROFILE</b>\n👤 {escape(name)}"
    await send_rich_async(u.id, blocks, reply_markup=kb.to_dict(), fallback_text=fb, edit_query=_edit_query_of(update))

async def view_purchase_history(update, page=1):
    u = update.effective_user; uid = u.id
    limit = 5; offset = (page-1) * limit
    total = cur.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (uid,)).fetchone()[0]
    if total == 0:
        kb = InlineKeyboardMarkup([[ibtn("BACK","sec_hist_menu",emoji="🔙",style="primary")],
                                    [ibtn("HOME","home",emoji="🏠",style="primary")]])
        await send_rich_async(uid, [make_heading("👑 PURCHASE HISTORY", 2),
            make_paragraph("📭 No history.")], reply_markup=kb.to_dict(),
            fallback_text="📭 No history", edit_query=_edit_query_of(update)); return
    rows = cur.execute("""SELECT phone, date, country, price, section FROM orders WHERE user_id=?
                          ORDER BY id DESC LIMIT ? OFFSET ?""", (uid, limit, offset)).fetchall()
    tp = max(1, (total + limit - 1) // limit)
    tb = [["📱 ITEM","🌎/📁","💰 PRICE","📅 DATE"]]
    for r in rows:
        ph = str(r["phone"] or "—")[:22]; cn = str(r["country"] or "—")[:14]
        try: pr = f"₹{float(r['price'] or 0):.0f}"
        except: pr = "—"
        dt = str(r["date"] or "—")
        if len(dt) > 16: dt = dt[:16]
        tb.append([ph, cn, pr, dt])
    blocks = [make_heading("👑 PURCHASE HISTORY", 2),
              make_table([["ℹ️ INFO","📋 VALUE"],["📄 Page", f"{page}/{tp}"],["📦 Total", str(total)]]),
              make_table(tb)]
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"purch_hist_{page-1}", emoji="🔙", style="primary"))
    if offset + limit < total: nav.append(ibtn("Next", f"purch_hist_{page+1}", emoji="👉", style="success"))
    kbr = []
    if nav: kbr.append(nav)
    kbr.append([ibtn("BACK","sec_hist_menu",emoji="🔙",style="primary"),
                ibtn("HOME","home",emoji="🏠",style="primary")])
    await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(kbr).to_dict(),
                          fallback_text=f"PURCHASE HISTORY {page}/{tp}", edit_query=_edit_query_of(update))

async def view_balance(update):
    u = update.effective_user
    ensure_user(u.id, u.first_name or "", u.username or "", u.last_name or "")
    r = get_user(u.id); bal = safe_get(r,'balance',0); fee = get_transfer_fee()
    blocks = [make_heading(STORE_HEADER, 2),
        make_table([["💠 WALLET","💰 VALUE"],["💰 Balance", f"₹{bal:.1f}"],
            ["💳 Total Recharge", f"₹{safe_get(r,'total_deposited',0):.1f}"],
            ["📆 Today Recharge", f"₹{safe_get(r,'today_deposited',0):.1f}"],
            ["👥 Referrals", str(safe_get(r, "referral_count", 0))],
            ["🎁 Ref Earnings", f"₹{safe_get(r, 'referral_earnings', 0):.1f}"],
            ["📤 Transfer Fee", f"{fee}%"]])]
    kb = InlineKeyboardMarkup([
        [ibtn("BALANCE HISTORY","bal_hist_1",custom_id=BALANCE_PREMIUM_EMOJI_ID,style="success")],
        [ibtn("SEND BALANCE","send_balance",emoji="💳",style="primary")],
        [ibtn("MAIN MENU","home",emoji="🔙",style="danger")]])
    await send_rich_async(u.id, blocks, reply_markup=kb.to_dict(),
                          fallback_text=f"💰 BALANCE ₹{bal:.1f}", edit_query=_edit_query_of(update))

async def view_refer(update):
    u = update.effective_user
    ensure_user(u.id, u.first_name or "", u.username or "", u.last_name or "")
    r = get_user(u.id)
    link = f"https://t.me/{current_ctx().username}?start=REF{u.id}"
    blocks = [make_heading(STORE_HEADER, 2),
        make_table([["🎗️ REFERRAL","💰 VALUE"],["👥 Total", str(safe_get(r, "referral_count", 0))],
            ["🎁 Earned", f"₹{safe_get(r, 'referral_earnings', 0):.1f}"],
            ["💯 Rate", REFERRAL_RATE],["🔗 Link", link]])]
    kb = InlineKeyboardMarkup([
        [ibtn("sʜᴀʀᴇ ʟɪɴᴋ", url=f"https://t.me/share/url?url={link}&text=.%0A%0A🎁+ᴠɪʟʟᴀɢᴇᴇ+sᴍs+sᴛᴏʀᴇ%0A🔥+ᴊᴏɪɴ+ᴛʜᴇ+ʙᴏᴛ+ᴀɴᴅ+ɢᴇᴛ+sᴛᴀʀᴛᴇᴅ!%0A💰+ᴇᴀʀɴ+ʀᴇᴡᴀʀᴅs+ᴠɪᴀ+ʀᴇғᴇʀʀᴀʟs!%0A%0A🛒+ᴘᴜʀᴄʜᴀsᴇ+ᴛᴇʟᴇɢʀᴀᴍ+ᴀᴄᴄᴏᴜɴᴛs+ғʀᴏᴍ+sᴇʀᴠᴇʀ+1+ᴀɴᴅ+sᴇʀᴠᴇʀ+2%0A%0A🛠️+ᴘᴜʀᴄʜᴀsᴇ+sᴏᴜʀᴄᴇ%2C+ᴘᴀɴᴇʟ+ᴀɴᴅ+ᴏsɪɴᴛ+ᴀᴘɪs+ғʀᴏᴍ+sᴇʀᴠᴇʀ+3%0A%0A📱+ᴘᴜʀᴄʜᴀsᴇ+ᴡʜᴀᴛsᴀᴘᴘ+ɴᴜᴍʙᴇʀs+ғʀᴏᴍ+sᴇʀᴠᴇʀ+4%0A%0A👇+ᴊᴏɪɴ+ɴᴏᴡ%3A+{link}",
              emoji="📢", style="success")],
        [ibtn("MAIN MENU","home",emoji="🔙",style="danger")]])
    await send_rich_async(u.id, blocks, reply_markup=kb.to_dict(),
                          fallback_text=f"🎗️ REFER\n{link}", edit_query=_edit_query_of(update))

async def view_support(update):
    blocks = [make_heading(STORE_HEADER, 2),
        make_table([["💬 SUPPORT","📞 CONTACT"],["📞", get_contact_1()],["📢", get_contact_2()]])]
    kb = InlineKeyboardMarkup([[ibtn("CONTACT ADMIN", url=get_support_url(), emoji="📞", style="success")],
                                [ibtn("MAIN MENU","home",emoji="🔙",style="danger")]])
    await send_rich_async(update.effective_user.id, blocks, reply_markup=kb.to_dict(),
                          fallback_text="💬 SUPPORT", edit_query=_edit_query_of(update))

async def view_recharge(update):
    u = update.effective_user
    ensure_user(u.id, u.first_name or "", u.username or "", u.last_name or "")
    r = get_user(u.id); bal = safe_get(r, 'balance', 0)
    min_d = get_min_deposit(); rate = get_rate()
    blocks = [make_heading(STORE_HEADER, 2), make_heading("⚡ RECHARGE CENTER", 3),
        make_table([["ℹ️ INFO","📋 DETAIL"],["💰 Balance", f"₹{bal:.1f}"],
            ["📉 Min Deposit", f"₹{min_d}"],["💱 USDT", f"1 USDT ≈ ₹{rate}"],
            ["⚡ UPI Auto", "FamPay Auto-Verify"],["📄 UPI Manual", "Manual UTR + Screenshot"],
            ["💎 Binance", "INR → USDT"],["🔷 Crypto", "BEP20 / TRON"]])]
    kb = InlineKeyboardMarkup([
        [ibtn("UPI AUTOMATIC","dep_upi",emoji="⚡",style="success")],
        [ibtn("UPI MANUAL","dep_manual_upi",emoji="📄",style="success")],
        [ibtn("BINANCE","depm_Binance",emoji="💎",style="primary")],
        [ibtn("CRYPTO","depm_Tron",emoji="💎",style="primary")],
        [ibtn("MAIN MENU","home",emoji="🔙",style="danger")]])
    await send_rich_async(u.id, blocks, reply_markup=kb.to_dict(),
                          fallback_text=f"⚡ RECHARGE ₹{bal:.1f}", edit_query=_edit_query_of(update))


async def view_buywa(update):
    uid = update.effective_user.id
    try:
        if is_wa_online():
            blocks = [make_heading(STORE_HEADER, 2), make_heading("🟢 WHATSAPP (4)", 3),
                make_table([["ℹ️ INFO","📋 DETAIL"],["🟢","WHATSAPP"],["⚡","Active"]])]
            await send_rich_async(uid, blocks, reply_markup=whatsapp_kb().to_dict(),
                                  fallback_text="🟢 WHATSAPP", edit_query=_edit_query_of(update))
        else:
            blocks = [make_heading(STORE_HEADER, 2), make_heading("🟢 WHATSAPP (4)", 3),
                make_table([["ℹ️ INFO","📋 DETAIL"],["📊 Status", "🚧 COMING SOON"],
                            ["📞 Support", get_contact_1()]]),
                make_paragraph("🔔 Coming soon.")]
            kb = InlineKeyboardMarkup([[ibtn("NOTIFY ME","wa_notify",emoji="🔔",style="success")],
                                        [ibtn("MAIN MENU","home",emoji="🔙",style="danger")]])
            await send_rich_async(uid, blocks, reply_markup=kb.to_dict(),
                                  fallback_text="🔔 Coming soon", edit_query=_edit_query_of(update))
    except Exception as e:
        log.error(f"view_buywa: {e}")


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn, main_inline_kb, whatsapp_kb
from config import MAINTENANCE_IMAGE, REFERRAL_RATE, STORE_HEADER, log
from context import cur, current_ctx
from database import (
    ensure_user, get_contact_1, get_contact_2, get_min_deposit, get_rate, get_setting,
    get_support_url, get_transfer_fee, get_user, is_wa_online, safe_get
)
from emojis import BALANCE_PREMIUM_EMOJI_ID, emo
from logs import _full_name
from rich_ui import (
    _edit_query_of, _tg_post, make_heading, make_paragraph, make_table, send_rich_async
)
