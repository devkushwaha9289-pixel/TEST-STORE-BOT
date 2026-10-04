#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — manual_upi.py
Manual UPI deposit flow (owner approve / reject / change amount).
"""

import re, time, asyncio
from html import escape
from telegram import InlineKeyboardMarkup

# ============================================================
# MANUAL UPI FLOW — ⭐ v28.1
# ============================================================
async def show_manual_upi_qr(chat_id, uid, amount):
    """Generate QR for manual UPI (same style as FamPay auto). Then wait for UTR + screenshot."""
    oid = generate_unique_order_id(uid)
    upi_id = get_manual_upi_id()
    qr_bytes = None
    try:
        qr_bytes = await asyncio.to_thread(
            generate_qr_png_bytes, upi_id, str(amount), oid, UPI_MERCHANT_NAME)
    except Exception as e:
        log.error(f"Manual QR generate failed: {e}")

    # Save to DB with status manual_pending
    cur.execute("""UPDATE upi_orders SET status='expired'
        WHERE user_id=? AND LOWER(COALESCE(provider,'fampay'))='manual' AND amount=?
          AND status IN ('pending','manual_pending')""", (uid, amount))
    cur.execute("""INSERT OR REPLACE INTO upi_orders
        (order_id, user_id, amount, status, qr_msg_id, created_ts, verified_via, provider)
        VALUES (?,?,?,?,?,?,?,?)""",
        (oid, uid, amount, "manual_pending", 0, time.time(), "manual_upi", "manual"))
    db.commit()
    try:
        cur.execute("""INSERT OR REPLACE INTO manual_upi_orders
            (order_id, user_id, amount, status, created_ts)
            VALUES (?,?,?,?,?)""", (oid, uid, amount, "pending", time.time()))
        db.commit()
    except: pass

    manual_upi_pending[uid] = {
        'order_id': oid, 'amount': amount,
        'utr': None, 'proof_file_id': None
    }

    usdt_amt = round(amount / get_rate(), 2)
    msg = (f"<b>{emo('📄')} MANUAL UPI PAYMENT</b>\n\n"
           f"{emo('💰')} Amount: <b>₹{amount}</b> (≈ ${usdt_amt})\n"
           f"{emo('🆔')} Order: <code>{oid}</code>\n"
           f"{emo('🏦')} UPI: <code>{upi_id}</code>\n\n"
           f"{emo('1️⃣')} Scan QR & Pay exact ₹{amount}\n"
           f"{emo('2️⃣')} Send <b>UTR / TXN ID</b> (text)\n"
           f"{emo('3️⃣')} Send <b>Payment Screenshot</b> (photo)\n\n"
           f"<b>{emo('⚠️')} Pay EXACT amount.</b>")

    kb = InlineKeyboardMarkup([
        [ibtn("CANCEL", "cancel", emoji="🚫", style="danger")]])

    sent = False
    if qr_bytes:
        sent = bool(await send_qr_photo(uid, qr_bytes, msg, reply_markup=kb.to_dict()))
    if not sent:
        upi_url = create_upi_url(upi_id, str(amount), oid, UPI_MERCHANT_NAME)
        try:
            await _tg_post("sendMessage", {"chat_id": uid,
                "text": f"{msg}\n\n{emo('🔗')} UPI Link:\n<code>{escape(upi_url)}</code>",
                "parse_mode": "HTML", "reply_markup": kb.to_dict()}, timeout=30)
        except: pass

    # Follow-up instructions
    try:
        await _tg_post("sendMessage", {"chat_id": uid,
            "text": (f"<b>{emo('📝')} NEXT STEPS</b>\n\n"
                     f"1️⃣ Send <b>UTR / TXN ID</b> as text\n"
                     f"2️⃣ Then send <b>Payment Screenshot</b> as photo\n\n"
                     f"{emo('⏳')} You have 15 minutes."),
            "parse_mode": "HTML"})
    except: pass

async def handle_manual_upi_text(update, context):
    """User sends UTR (text) during manual UPI flow."""
    msg = update.message; uid = update.effective_user.id
    text = (msg.text or "").strip()
    if text == "/cancel" or text.lower() == "cancel" or text == BTN_CANCEL:
        manual_upi_pending.pop(uid, None)
        await msg.reply_text(f"{emo('❌')} Cancelled.", parse_mode="HTML",
                             reply_markup=main_reply_kb(uid)); return
    st = manual_upi_pending.get(uid)
    if not st: return
    clean = re.sub(r'[^\w]', '', text).strip().upper()
    if len(clean) < 4:
        await msg.reply_text(f"{emo('⚠️')} UTR too short. Send at least 4 characters.",
                             parse_mode="HTML"); return
    st['utr'] = clean
    try:
        cur.execute("UPDATE manual_upi_orders SET utr=? WHERE order_id=?", (clean, st['order_id']))
        db.commit()
    except: pass
    await msg.reply_text(
        f"{emo('✅')} <b>UTR Saved</b>\n🔢 <code>{escape(clean)}</code>\n\n"
        f"{emo('📸')} Now send the <b>payment screenshot</b>.",
        parse_mode="HTML")
    if st.get('proof_file_id'):
        await _submit_manual_upi_to_owner(uid)

async def handle_manual_upi_proof(update, context):
    """User sends screenshot (photo/document) during manual UPI flow."""
    msg = update.message; uid = update.effective_user.id
    st = manual_upi_pending.get(uid)
    if not st: return
    file_id = None
    if msg.photo: file_id = msg.photo[-1].file_id
    elif msg.document: file_id = msg.document.file_id
    if not file_id:
        await msg.reply_text(f"{emo('❌')} Send a photo or document.",
                             parse_mode="HTML"); return
    st['proof_file_id'] = file_id
    try:
        cur.execute("UPDATE manual_upi_orders SET proof_file_id=? WHERE order_id=?",
                    (file_id, st['order_id']))
        db.commit()
    except: pass
    if st.get('utr'):
        await _submit_manual_upi_to_owner(uid)
    else:
        await msg.reply_text(
            f"{emo('✅')} <b>Screenshot Saved</b>\n\n"
            f"{emo('📝')} Now send the <b>UTR / TXN ID</b>.",
            parse_mode="HTML")

async def _submit_manual_upi_to_owner(uid):
    """Submit complete UTR+proof to OWNER's DM (not log channel)."""
    st = manual_upi_pending.pop(uid, None)
    if not st: return
    oid = st['order_id']; amount = st['amount']
    utr = st.get('utr') or "—"
    proof_file_id = st.get('proof_file_id')

    # Update DB status
    try:
        cur.execute("""UPDATE manual_upi_orders SET status='submitted' WHERE order_id=?""", (oid,))
        cur.execute("""UPDATE upi_orders SET utr=? WHERE order_id=?""", (utr, oid))
        db.commit()
    except: pass

    r = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (uid,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r['username'] else "—"

    rows = [
        ["ℹ️ INFO", "📋 DETAIL"],
        ["👤 Name", nm],
        ["🆔 User", str(uid)],
        ["🔗 Username", un],
        ["💰 Amount", f"₹{amount}"],
        ["🆔 Order", oid],
        ["🔢 UTR", utr],
        ["📅 Time", _now_str()],
    ]
    blocks = [
        make_heading("🔔 NEW MANUAL UPI PAYMENT", 2),
        make_table(rows),
    ]
    fb = (f"🔔 NEW MANUAL UPI\n👤 {nm} ({uid})\n💰 ₹{amount}\n🆔 {oid}\n🔢 {utr}")

    kb = InlineKeyboardMarkup([
        [ibtn("✅ APPROVE", f"manup_approve|{oid}", emoji="✅", style="success")],
        [ibtn("❌ REJECT", f"manup_reject|{oid}", emoji="❌", style="danger"),
         ibtn("💰 CHANGE AMOUNT", f"manup_amount|{oid}", emoji="💰", style="primary")],
    ])

    owner_id = current_owner_id()
    sent = False
    if proof_file_id:
        try:
            await _deliver_rich_photo_to_target(owner_id, proof_file_id, blocks, fb, kb.to_dict())
            sent = True
        except Exception as e:
            log.error(f"manual_upi owner photo delivery: {e}")
    if not sent:
        try:
            await send_rich_async(owner_id, blocks, reply_markup=kb.to_dict(),
                                  fallback_text=fb, show_placeholder=False)
        except Exception as e:
            log.error(f"manual_upi owner rich delivery: {e}")

    # Notify user
    try:
        await _tg_post("sendMessage", {"chat_id": uid,
            "text": (f"<b>{emo('✅')} Payment Submitted!</b>\n\n"
                     f"{emo('🆔')} Order: <code>{oid}</code>\n"
                     f"{emo('💰')} Amount: ₹{amount}\n"
                     f"{emo('🔢')} UTR: <code>{utr}</code>\n\n"
                     f"{emo('⏳')} Waiting for admin approval. Please wait..."),
            "parse_mode": "HTML", "reply_markup": main_reply_kb(uid).to_dict()})
    except: pass

async def complete_manual_upi_order(oid, uid, amount):
    """Credit the user after owner approval."""
    async with get_user_lock(uid):
        row = cur.execute("SELECT status FROM manual_upi_orders WHERE order_id=?", (oid,)).fetchone()
        if row and row["status"] == "approved":
            return False
        r = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        old = r["balance"] if r else 0
        # mark success in both tables
        try:
            cur.execute("UPDATE manual_upi_orders SET status='approved' WHERE order_id=?", (oid,))
        except: pass
        cur.execute("""UPDATE upi_orders SET status='success', verified_via='manual_upi_owner'
            WHERE order_id=?""", (oid,))
        update_balance(uid, amount)
        cur.execute("""UPDATE users SET total_deposited=total_deposited+?,
            today_deposited=today_deposited+? WHERE user_id=?""", (amount, amount, uid))
        db.commit()
        record_balance_history(uid, amount, "deposit", "manual_upi",
                               f"UPI {oid}", old, old + amount)
    new = old + amount
    succ = (f"<b>{emo('✅')} PAYMENT APPROVED</b>\n\n"
            f"{emo('🆔')} Order: <code>{oid}</code>\n"
            f"{emo('💰')} Added: <b>₹{amount}</b>\n"
            f"{emo('💼')} Old: ₹{old}\n{emo('💬')} New: ₹{new}\n\n"
            f"<i>Source: Manual UPI • {_now_str()}</i>")
    try:
        await _tg_post("sendMessage", {"chat_id": uid, "text": succ, "parse_mode": "HTML",
            "reply_markup": main_reply_kb(uid).to_dict()})
    except: pass
    try: await log_deposit(uid, amount, "UPI (Manual)", "approved", dep_id=oid)
    except: pass
    try: await process_referral_bonus(uid, amount)
    except: pass
    return True

async def reject_manual_upi_order(oid, owner_uid, reason=""):
    row = cur.execute("SELECT user_id, amount FROM manual_upi_orders WHERE order_id=?", (oid,)).fetchone()
    if not row:
        row = cur.execute("SELECT user_id, amount FROM upi_orders WHERE order_id=?", (oid,)).fetchone()
    if not row: return
    tu = row["user_id"]; amt = int(row["amount"])
    try:
        cur.execute("UPDATE manual_upi_orders SET status='rejected', reject_reason=? WHERE order_id=?",
                    (reason or "", oid))
    except: pass
    try:
        cur.execute("UPDATE upi_orders SET status='manual_rejected' WHERE order_id=?", (oid,))
    except: pass
    db.commit()
    reason_line = f"\n\n{emo('📝')} <b>Reason:</b> <i>{escape(reason)}</i>" if reason else ""
    try:
        await _tg_post("sendMessage", {"chat_id": tu,
            "text": (f"<b>{emo('❌')} PAYMENT REJECTED</b>\n\n"
                     f"{emo('🆔')} Order: <code>{oid}</code>\n"
                     f"{emo('💰')} Amount: ₹{amt}{reason_line}\n\n"
                     f"<b>{emo('👉')} Contact:</b> {get_contact_1()}"),
            "parse_mode": "HTML", "reply_markup": main_reply_kb(tu).to_dict()})
    except: pass
    try: await log_admin_action(owner_uid, "Manual UPI Reject", f"order={oid} amount={amt} reason={reason[:80]}")
    except: pass

async def reshow_manual_upi_request(oid):
    """Re-send the manual UPI request to owner with same buttons (used after amount change)."""
    row = cur.execute("""SELECT order_id, user_id, amount, utr FROM manual_upi_orders
        WHERE order_id=?""", (oid,)).fetchone()
    if not row: return
    tu = row["user_id"]; amount = int(row["amount"]); utr = row["utr"] or "—"
    r = cur.execute("SELECT first_name, last_name, username FROM users WHERE user_id=?", (tu,)).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r['username'] else "—"
    proof_file_id = None
    try:
        pr = cur.execute("SELECT proof_file_id FROM manual_upi_orders WHERE order_id=?", (oid,)).fetchone()
        if pr: proof_file_id = pr["proof_file_id"]
    except: pass
    owner_id = current_owner_id()
    rows = [
        ["ℹ️ INFO", "📋 DETAIL"],
        ["👤 Name", nm],
        ["🆔 User", str(tu)],
        ["🔗 Username", un],
        ["💰 Amount", f"₹{amount}"],
        ["🆔 Order", oid],
        ["🔢 UTR", utr],
        ["📅 Time", _now_str()],
    ]
    blocks = [
        make_heading("🔔 MANUAL UPI — UPDATED", 2),
        make_table(rows),
    ]
    fb = f"🔔 MANUAL UPI (updated)\n👤 {nm}\n💰 ₹{amount}\n🆔 {oid}"
    kb = InlineKeyboardMarkup([
        [ibtn("✅ APPROVE", f"manup_approve|{oid}", emoji="✅", style="success")],
        [ibtn("❌ REJECT", f"manup_reject|{oid}", emoji="❌", style="danger"),
         ibtn("💰 CHANGE AMOUNT", f"manup_amount|{oid}", emoji="💰", style="primary")],
    ])
    sent = False
    if proof_file_id:
        try:
            await _deliver_rich_photo_to_target(owner_id, proof_file_id, blocks, fb, kb.to_dict())
            sent = True
        except: pass
    if not sent:
        try:
            await send_rich_async(owner_id, blocks, reply_markup=kb.to_dict(),
                                  fallback_text=fb, show_placeholder=False)
        except: pass

async def submit_manual_upi_from_miniapp(uid, oid, utr):
    """Submit a Mini App manual-UPI UTR into the normal owner approval flow."""
    row = cur.execute(
        "SELECT user_id, amount, status, utr FROM manual_upi_orders WHERE order_id=?",
        (oid,),
    ).fetchone()
    if not row:
        raise RuntimeError("Manual payment order not found")
    if int(row["user_id"]) != int(uid):
        raise RuntimeError("Payment order does not belong to this user")
    if row["status"] == "approved":
        return {"ok": True, "status": "approved"}
    if row["status"] == "rejected":
        raise RuntimeError("Payment was rejected")

    clean = re.sub(r'[^A-Za-z0-9]', '', str(utr or '')).upper()
    if len(clean) < 4:
        raise RuntimeError("UTR too short")

    cur.execute("UPDATE manual_upi_orders SET utr=?, status='submitted' WHERE order_id=?",
                (clean, oid))
    cur.execute("UPDATE upi_orders SET utr=?, status='manual_pending' WHERE order_id=?",
                (clean, oid))
    db.commit()

    r = cur.execute(
        "SELECT first_name, last_name, username FROM users WHERE user_id=?",
        (uid,),
    ).fetchone()
    nm = _full_name(r["first_name"] if r else "—", r["last_name"] if r else "")
    un = f"@{r['username']}" if r and r["username"] else "—"
    amount = int(row["amount"])
    owner_id = current_owner_id()
    rows = [
        ["ℹ️ INFO", "📋 DETAIL"],
        ["👤 Name", nm], ["🆔 User", str(uid)], ["🔗 Username", un],
        ["💰 Amount", f"₹{amount}"], ["🆔 Order", oid], ["🔢 UTR", clean],
        ["📅 Time", _now_str()],
    ]
    blocks = [make_heading("🔔 NEW MANUAL UPI PAYMENT", 2), make_table(rows)]
    fb = f"🔔 NEW MANUAL UPI\n👤 {nm} ({uid})\n💰 ₹{amount}\n🆔 {oid}\n🔢 {clean}"
    kb = InlineKeyboardMarkup([
        [ibtn("✅ APPROVE", f"manup_approve|{oid}", emoji="✅", style="success")],
        [ibtn("❌ REJECT", f"manup_reject|{oid}", emoji="❌", style="danger"),
         ibtn("💰 CHANGE AMOUNT", f"manup_amount|{oid}", emoji="💰", style="primary")],
    ])
    await send_rich_async(owner_id, blocks, reply_markup=kb.to_dict(),
                          fallback_text=fb, show_placeholder=False)
    try:
        await _tg_post("sendMessage", {
            "chat_id": uid, "parse_mode": "HTML",
            "text": (f"<b>{emo('✅')} Payment Submitted!</b>\n\n"
                      f"🆔 Order: <code>{escape(oid)}</code>\n"
                      f"💰 Amount: ₹{amount}\n"
                      f"🔢 UTR: <code>{escape(clean)}</code>\n\n"
                      f"⏳ Waiting for admin approval."),
        })
    except Exception:
        pass
    return {"ok": True, "status": "manual_pending"}


async def handle_manual_upi_owner_text(update, context):
    """Owner sends reason text after tapping Reject."""
    msg = update.message; uid = update.effective_user.id
    text = (msg.text or "").strip()
    st = manual_upi_owner_state.get(uid)
    if not st: return
    if text == "/cancel" or text.lower() == "cancel" or text == BTN_CANCEL:
        manual_upi_owner_state.pop(uid, None)
        await msg.reply_text(f"{emo('❌')} Cancelled.", parse_mode="HTML"); return
    action = st.get('action')
    oid = st.get('order_id')
    if action == 'reject_reason':
        reason = "" if text.strip() in ("/skip", "") else text.strip()[:200]
        manual_upi_owner_state.pop(uid, None)
        await reject_manual_upi_order(oid, uid, reason)
        await msg.reply_text(f"{emo('✅')} <b>Rejected</b> — user notified.", parse_mode="HTML")
        return


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import BTN_CANCEL, ibtn, main_reply_kb
from config import UPI_MERCHANT_NAME, log
from context import cur, current_owner_id, db
from database import get_contact_1, get_manual_upi_id, get_rate, update_balance
from emojis import emo
from history import record_balance_history
from logs import _full_name, _now_str, log_admin_action, log_deposit
from payments import process_referral_bonus
from rich_ui import (
    _deliver_rich_photo_to_target, _tg_post, _tg_send_photo_buffer, send_qr_photo, make_heading,
    make_table, send_rich_async
)
from state import get_user_lock, manual_upi_owner_state, manual_upi_pending
from utils import QR_AVAILABLE, create_upi_url, generate_qr_png_bytes, generate_unique_order_id
