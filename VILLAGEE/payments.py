#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — payments.py
Keypad, UPI auto-deposit, UTR/proof handling, referral bonus, balance transfer.
"""

import re, time, asyncio
from html import escape
from telegram import InlineKeyboardMarkup

# ============================================================
# KEYPAD / UPI AUTO
# ============================================================
def keypad_kb(prefix="kp_"):
    return InlineKeyboardMarkup([
        [ibtn("1", f"{prefix}1", emoji="1️⃣", style="primary"),
         ibtn("2", f"{prefix}2", emoji="2️⃣", style="primary"),
         ibtn("3", f"{prefix}3", emoji="3️⃣", style="primary")],
        [ibtn("4", f"{prefix}4", emoji="4️⃣", style="primary"),
         ibtn("5", f"{prefix}5", emoji="5️⃣", style="primary"),
         ibtn("6", f"{prefix}6", emoji="6️⃣", style="primary")],
        [ibtn("7", f"{prefix}7", emoji="7️⃣", style="primary"),
         ibtn("8", f"{prefix}8", emoji="8️⃣", style="primary"),
         ibtn("9", f"{prefix}9", emoji="9️⃣", style="primary")],
        [ibtn("⌫", f"{prefix}del", emoji="❌", style="danger"),
         ibtn("0", f"{prefix}0", emoji="0️⃣", style="primary"),
         ibtn("✅", f"{prefix}done", emoji="✅", style="success")],
        [ibtn("CANCEL", "cancel", emoji="🚫", style="danger")]])

async def complete_upi_order(oid, uid, amount, qr_msg_id=None, source="fampay_imap", utr=None, txn=None):
    if utr and is_utr_used_by_other_order(utr, oid): return False
    if txn and is_txn_used_by_other_order(txn, oid): return False
    async with get_user_lock(uid):
        row = cur.execute("SELECT status FROM upi_orders WHERE order_id=?", (oid,)).fetchone()
        if not row or row["status"] != "pending": return False
        r = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        old = r["balance"] if r else 0
        cur.execute("""UPDATE upi_orders SET status='success', verified_via=?, utr=?, txn_id=?
            WHERE order_id=?""", (source, utr, txn, oid))
        update_balance(uid, amount)
        cur.execute("""UPDATE users SET total_deposited=total_deposited+?,
            today_deposited=today_deposited+? WHERE user_id=?""", (amount, amount, uid))
        db.commit()
        record_balance_history(uid, amount, "deposit", source,
                               f"UPI {utr or txn or 'auto'}", old, old + amount)
    new = old + amount
    if not qr_msg_id:
        qr = cur.execute("SELECT qr_msg_id FROM upi_orders WHERE order_id=?", (oid,)).fetchone()
        qr_msg_id = qr["qr_msg_id"] if qr else None
    succ = (f"<b>{emo('✅')} PAYMENT VERIFIED</b>\n\n"
            f"{emo('🆔')} Order: <code>{oid}</code>\n"
            f"{emo('💰')} Added: <b>₹{amount}</b>\n"
            f"{emo('💼')} Old: ₹{old}\n{emo('💬')} New: ₹{new}\n\n"
            f"<i>Source: FamPay Auto • {_now_str()}</i>")
    try:
        if qr_msg_id: await _tg_post("deleteMessage", {"chat_id": uid, "message_id": qr_msg_id})
    except: pass
    try: await log_deposit(uid, amount, "UPI (FamPay Auto)", "approved", dep_id=oid, utr=utr or txn)
    except: pass
    try: await process_referral_bonus(uid, amount)
    except: pass
    try:
        await _tg_post("sendMessage", {"chat_id": uid, "text": succ, "parse_mode": "HTML",
            "reply_markup": main_reply_kb(uid).to_dict()})
    except: pass
    return True

async def show_upi_qr(chat_id, uid, amount):
    oid = generate_unique_order_id(uid)
    upi_id = get_fampay_upi_id()
    qr_bytes = None
    try:
        if QR_AVAILABLE:
            qr_bytes = await asyncio.to_thread(generate_qr_png_bytes, upi_id, str(amount), oid, UPI_MERCHANT_NAME)
    except Exception as e: log.warning(f"QR: {e}")
    cur.execute("""INSERT OR REPLACE INTO upi_orders (order_id, user_id, amount, status, qr_msg_id, created_ts)
        VALUES (?,?,?,?,?,?)""", (oid, uid, amount, "pending", 0, time.time())); db.commit()
    usdt_amt = round(amount / get_rate(), 2)
    msg = (f"<b>{emo('💳')} Secure UPI (15-Min)</b>\n\n"
           f"{emo('💰')} Amount: <b>₹{amount}</b> (≈ ${usdt_amt})\n"
           f"{emo('🆔')} Order: <code>{oid}</code>\n"
           f"{emo('🏦')} UPI: <code>{upi_id}</code>\n\n"
           f"{emo('1️⃣')} Scan QR\n{emo('2️⃣')} Pay exact ₹{amount}\n"
           f"{emo('3️⃣')} Auto-credit\n\n"
           f"<b>{emo('⚠️')} Pay exact amount.</b>\n<b>{emo('🚫')} UTR/TXN only ONCE.</b>")
    kb = InlineKeyboardMarkup([
        [ibtn("CHECK NOW", f"check_upi_{oid}", emoji="✅", style="success")],
        [ibtn("ENTER UTR", f"utr_enter|{oid}", emoji="🔢", style="primary")],
        [ibtn("CANCEL", "cancel", emoji="🚫", style="danger")]])
    sent = False; qr_msg_id = None
    if qr_bytes:
        try:
            r = await _tg_send_photo_buffer(uid, qr_bytes, msg, reply_markup=kb.to_dict())
            d = r.json()
            if d.get("ok"):
                qr_msg_id = d.get("result", {}).get("message_id"); sent = True
        except: pass
    if not sent:
        upi_url = create_upi_url(upi_id, str(amount), oid, UPI_MERCHANT_NAME)
        try:
            r = await _tg_post("sendMessage", {"chat_id": uid,
                "text": f"{msg}\n\n{emo('🔗')} UPI Link:\n<code>{escape(upi_url)}</code>",
                "parse_mode": "HTML", "reply_markup": kb.to_dict()}, timeout=30)
            d = r.json()
            if d.get("ok"):
                qr_msg_id = d.get("result", {}).get("message_id"); sent = True
        except: pass
    if qr_msg_id:
        cur.execute("UPDATE upi_orders SET qr_msg_id=? WHERE order_id=?", (qr_msg_id or 0, oid)); db.commit()
        asyncio.create_task(upi_order_watchdog(oid, uid, qr_msg_id))

async def upi_order_watchdog(oid, uid, qr_msg_id):
    await asyncio.sleep(UPI_VERIFY_WINDOW_SECONDS)
    row = cur.execute("SELECT status FROM upi_orders WHERE order_id=?", (oid,)).fetchone()
    if row and row["status"] == "pending":
        cur.execute("UPDATE upi_orders SET status='expired' WHERE order_id=?", (oid,)); db.commit()
        try:
            if qr_msg_id: await _tg_post("deleteMessage", {"chat_id": uid, "message_id": qr_msg_id})
        except: pass
        try:
            await _tg_post("sendMessage", {"chat_id": uid,
                "text": f"{emo('⏰')} <b>Session Expired!</b>\nIf you paid, tap Enter UTR.",
                "parse_mode": "HTML",
                "reply_markup": InlineKeyboardMarkup([
                    [ibtn("ENTER UTR", f"utr_enter|{oid}", emoji="🔢", style="success")],
                    [ibtn("HOME","home",emoji="🏠",style="primary")]]).to_dict()})
        except: pass

async def handle_upi_check(update, context):
    q = update.callback_query; data = q.data; uid = update.effective_user.id
    oid = data.replace("check_upi_", "")
    row = cur.execute("SELECT amount, status FROM upi_orders WHERE order_id=?", (oid,)).fetchone()
    if not row:
        try: await q.answer("Not found", show_alert=True)
        except: pass
        return
    if row["status"] == "success":
        try: await q.answer("Credited!", show_alert=True)
        except: pass
        return
    if row["status"] in ("expired","failed","mismatch","duplicate"):
        try: await q.answer("No longer valid.", show_alert=True)
        except: pass
        return
    exp = float(row["amount"]); cutoff = time.time() - 900
    match = cur.execute("""SELECT msg_id, amount, utr, txn_id FROM fampay_emails
        WHERE ABS(amount - ?) < 0.01 AND received_ts > ? AND (matched_order_id IS NULL OR matched_order_id='')
        ORDER BY received_ts DESC LIMIT 1""", (exp, cutoff)).fetchone()
    if match:
        paid = float(match["amount"]); utr = match["utr"]; txn = match["txn_id"]
        existing = None
        if utr: existing = is_utr_used_by_other_order(utr, oid)
        if not existing and txn: existing = is_txn_used_by_other_order(txn, oid)
        if existing:
            cur.execute("UPDATE upi_orders SET status='duplicate' WHERE order_id=?", (oid,)); db.commit()
            await _send_double_payment_alert(uid, oid, utr, txn, existing)
            try: await q.answer("🚫 Duplicate!", show_alert=True)
            except: pass
            return
        if abs(paid - exp) > 0.01:
            cur.execute("""UPDATE upi_orders SET status='mismatch', paid_amount=?, utr=?, txn_id=?
                WHERE order_id=?""", (paid, utr, txn, oid)); db.commit()
            try:
                cur.execute("UPDATE fampay_emails SET matched_order_id=? WHERE msg_id=?", (oid, match["msg_id"])); db.commit()
            except: pass
            await _send_mismatch_alert(uid, oid, exp, paid, utr, txn, "manual_check")
            try: await q.answer("⚠️ Mismatch!", show_alert=True)
            except: pass
            return
        try:
            cur.execute("UPDATE fampay_emails SET matched_order_id=? WHERE msg_id=?", (oid, match["msg_id"])); db.commit()
        except: pass
        await complete_upi_order(oid, uid, int(exp), None, "fampay_manual_check", utr=utr, txn=txn)
        try: await q.answer("✅ Verified!", show_alert=True)
        except: pass
        return
    try: await q.answer("⏳ No matching email yet. Wait 30-60s.", show_alert=True)
    except: pass

async def handle_utr_enter(update, context):
    q = update.callback_query; data = q.data; uid = update.effective_user.id
    oid = data.split("|", 1)[1]
    row = cur.execute("SELECT amount, status FROM upi_orders WHERE order_id=?", (oid,)).fetchone()
    if not row:
        try: await q.answer("Not found", show_alert=True)
        except: pass
        return
    if row["status"] == "success":
        try: await q.answer("Credited!", show_alert=True)
        except: pass
        return
    waiting_utr[uid] = {'order_id': oid, 'amount': float(row["amount"])}
    try: await q.answer()
    except: pass
    await q.message.reply_text(
        f"<b>{emo('🔢')} ENTER UTR / TXN</b>\n\n{emo('💰')} Amount: ₹{int(row['amount'])}\n"
        f"{emo('🆔')} Order: <code>{oid}</code>\n\n{emo('📝')} Send UTR:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL", "cancel", emoji="🚫", style="danger")]]))

async def handle_utr_text_input(update, context):
    msg = update.message; uid = update.effective_user.id
    text = (msg.text or "").strip()
    if text == "/cancel" or text.lower() == "cancel" or text == BTN_CANCEL:
        waiting_utr.pop(uid, None)
        await msg.reply_text(f"{emo('❌')} Cancelled.", parse_mode="HTML",
                             reply_markup=main_reply_kb(uid)); return
    info = waiting_utr.get(uid)
    if not info: return
    oid = info['order_id']; exp = info['amount']
    clean = re.sub(r'[^\w]', '', text).strip().upper()
    if len(clean) < 4:
        await msg.reply_text(f"{emo('⚠️')} UTR too short.", parse_mode="HTML"); return
    await msg.reply_text(f"{emo('🔍')} Searching <code>{escape(clean)}</code>...", parse_mode="HTML")
    row = cur.execute("""SELECT msg_id, amount, utr, txn_id, order_id FROM fampay_emails
        WHERE UPPER(utr)=? OR UPPER(txn_id)=? OR UPPER(order_id)=? LIMIT 1""",
        (clean, clean, clean)).fetchone()
    if not row:
        row = cur.execute("""SELECT msg_id, amount, utr, txn_id, order_id FROM fampay_emails
            WHERE raw_summary LIKE ? ORDER BY received_ts DESC LIMIT 1""", (f"%{clean}%",)).fetchone()
    if not row:
        await msg.reply_text(
            f"{emo('❌')} <b>Not found.</b>\n\n• Verify UTR/TXN\n• Wait 30-60s\n"
            f"• Bot checks every {IMAP_POLL_INTERVAL}s",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [ibtn("RETRY", f"utr_enter|{oid}", emoji="🔄", style="primary")],
                [ibtn("HOME","home",emoji="🏠",style="primary")]]))
        return
    try: ea = float(row["amount"]) if row["amount"] else None
    except: ea = None
    utr_v = row["utr"]; txn_v = row["txn_id"]
    existing = None
    if utr_v: existing = is_utr_used_by_other_order(utr_v, oid)
    if not existing and txn_v: existing = is_txn_used_by_other_order(txn_v, oid)
    if existing:
        waiting_utr.pop(uid, None)
        cur.execute("UPDATE upi_orders SET status='duplicate' WHERE order_id=?", (oid,)); db.commit()
        await _send_double_payment_alert(uid, oid, utr_v, txn_v, existing); return
    if ea is None or abs(ea - exp) > 0.01:
        try:
            cur.execute("UPDATE fampay_emails SET matched_order_id=? WHERE msg_id=?", (oid, row["msg_id"]))
            cur.execute("""UPDATE upi_orders SET status='mismatch', paid_amount=?, utr=?, txn_id=?,
                verified_via='utr_manual_mismatch' WHERE order_id=?""",
                (ea or 0, utr_v, txn_v, oid)); db.commit()
        except: pass
        waiting_utr.pop(uid, None)
        await _send_mismatch_alert(uid, oid, exp, ea or 0, utr_v or clean, txn_v, "utr_manual"); return
    try:
        cur.execute("UPDATE fampay_emails SET matched_order_id=? WHERE msg_id=?", (oid, row["msg_id"])); db.commit()
    except: pass
    ok = await complete_upi_order(oid, uid, int(exp), None, "fampay_utr_manual", utr=utr_v, txn=txn_v)
    waiting_utr.pop(uid, None)
    if ok:
        await msg.reply_text(f"{emo('✅')} Verified via UTR! ₹{int(exp)} credited.",
                             parse_mode="HTML", reply_markup=main_reply_kb(uid))
    else:
        await msg.reply_text(f"{emo('⚠️')} Already processed.", parse_mode="HTML",
                             reply_markup=main_reply_kb(uid))

async def handle_deposit_amount(update, context):
    msg = update.message; uid = update.effective_user.id; text = msg.text or ""
    method = deposit_input[uid]['method']; rate = get_rate(); min_d = get_min_deposit()
    try:
        if method in ("Cwallet","Binance","Tron","Polygon"):
            inr = int(re.sub(r'[^\d]', '', text))
            if inr < min_d:
                await msg.reply_text(f"{emo('⚠️')} Min ₹{min_d}.", parse_mode="HTML"); return
            if inr <= 0:
                await msg.reply_text(f"{emo('⚠️')} > 0", parse_mode="HTML"); return
            usdt = round(inr / rate, 2)
            if usdt <= 0:
                await msg.reply_text(f"{emo('⚠️')} Too small.", parse_mode="HTML"); return
            waiting_proof[uid] = {'amount': inr, 'method': method, 'usdt_amount': usdt}
            deposit_input.pop(uid, None)
            qr = {"Cwallet":CWALLET_QR,"Binance":BINANCE_QR,"Tron":TRON_QR,"Polygon":POLYGON_QR}[method]
            addr = {"Cwallet":CWALLET_ID,"Binance":BINANCE_ID,"Tron":TRON_ID,"Polygon":POLYGON_ID}[method]
            cap = (f"<b>{emo('💳')} {method} Deposit</b>\n\n"
                   f"{emo('💰')} You want: <b>₹{inr}</b>\n"
                   f"{emo('💱')} Send exactly: <b>${usdt} USDT</b>\n"
                   f"{emo('📊')} Rate: 1 USDT ≈ ₹{rate}\n\n"
                   f"{emo('🚀')} Address: <code>{addr}</code>\n\n"
                   f"<b>{emo('⚠️')} Send EXACT ${usdt} USDT</b>\n\n"
                   f"{emo('👉')} After sending, send TX Hash / Screenshot.")
            kb = InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]])
            try: await msg.reply_photo(qr, caption=cap, parse_mode="HTML", reply_markup=kb)
            except: await msg.reply_text(cap + f"\n\nQR: {qr}", parse_mode="HTML", reply_markup=kb)
        else:
            amt = int(re.sub(r'[^\d]', '', text))
            if amt < min_d:
                await msg.reply_text(f"{emo('⚠️')} Min ₹{min_d}.", parse_mode="HTML"); return
            waiting_proof[uid] = {'amount': amt, 'method': method}
            deposit_input.pop(uid, None)
            await msg.reply_text(f"<b>{emo('💳')} {method}</b>\n\n{emo('💰')} ₹{amt}\n\n{emo('👉')} Send Screenshot:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))
    except ValueError:
        await msg.reply_text(f"{emo('❌')} Invalid amount.", parse_mode="HTML")

async def handle_deposit_proof(update, context):
    msg = update.message; uid = update.effective_user.id
    info = waiting_proof.pop(uid); final = info['amount']
    cur.execute("INSERT INTO deposits (user_id, amount, method_name, status) VALUES (?,?,?,?)",
                (uid, final, info['method'], "pending")); db.commit()
    dep_id = cur.lastrowid
    await msg.reply_text(f"{emo('✅')} Submitted! Wait for approval.", parse_mode="HTML",
                          reply_markup=main_reply_kb(uid))
    kb = InlineKeyboardMarkup([
        [ibtn(f"ACCEPT ₹{final}", f"dep_acc|{dep_id}|{uid}|{info['method']}|exact|{final}",
              emoji="✅", style="success"),
         ibtn("REJECT", f"dep_rej|{dep_id}|{uid}", emoji="❌", style="danger")]])
    photo_id = None
    if msg.photo: photo_id = msg.photo[-1].file_id
    elif msg.document: photo_id = msg.document.file_id
    await log_deposit(uid, final, info['method'], "pending", dep_id=dep_id, photo_file_id=photo_id)
    for tgt in get_log_targets():
        try:
            await _tg_post("sendMessage", {"chat_id": tgt,
                "text": f"<b>{emo('🔔')} ACTION</b> — Ref <code>{dep_id}</code>",
                "parse_mode": "HTML", "reply_markup": kb.to_dict()})
        except: pass

async def process_referral_bonus(uid, amt):
    r = cur.execute("SELECT referred_by FROM users WHERE user_id=?", (uid,)).fetchone()
    ref = r[0] if r else None
    if ref:
        p = cur.execute("SELECT value FROM settings WHERE key='ref_percent'").fetchone()
        pct = float(p[0]) if p else 1.5
        if pct > 0:
            bonus = int(amt * (pct / 100))
            if bonus > 0:
                update_balance(ref, bonus)
                cur.execute("UPDATE users SET referral_earnings=referral_earnings+? WHERE user_id=?",
                            (bonus, ref)); db.commit()
                await log_referral_bonus(ref, uid, bonus, amt)


# ============================================================
# BALANCE TRANSFER
# ============================================================
async def handle_balance_transfer_uid(update, context):
    msg = update.message; uid = update.effective_user.id
    text = (msg.text or "").strip()
    if text == "/cancel" or text.lower() == "cancel" or text == BTN_CANCEL:
        temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('❌')} Cancelled.", parse_mode="HTML",
                             reply_markup=main_reply_kb(uid)); return
    try: to_uid = int(re.sub(r'[^\d]', '', text))
    except:
        await msg.reply_text(f"{emo('❌')} Invalid ID.", parse_mode="HTML"); return
    if to_uid == uid:
        await msg.reply_text(f"{emo('❌')} Cannot self-transfer.", parse_mode="HTML"); return
    recv = cur.execute("SELECT user_id, first_name, last_name FROM users WHERE user_id=?", (to_uid,)).fetchone()
    if not recv:
        await msg.reply_text(f"{emo('❌')} Not found.", parse_mode="HTML"); return
    r = get_user(uid); temp_data[uid] = {'step': 'balance_transfer_amt', 'to_uid': to_uid}
    rn = _full_name(recv["first_name"] or "", recv["last_name"] or "")
    await msg.reply_text(
        f"<b>{emo('💳')} SEND BALANCE — 2/2</b>\n\n{emo('💰')} Balance: <code>₹{safe_get(r,'balance',0)}</code>\n"
        f"{emo('👤')} Receiver: {rn} (<code>{to_uid}</code>)\n"
        f"{emo('📤')} Fee: <b>{get_transfer_fee()}%</b>\n\n{emo('👉')} Amount (₹):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[ibtn("CANCEL","cancel",emoji="🚫",style="danger")]]))

async def handle_balance_transfer_amt(update, context):
    msg = update.message; uid = update.effective_user.id
    text = (msg.text or "").strip()
    if text == "/cancel" or text.lower() == "cancel" or text == BTN_CANCEL:
        temp_data.pop(uid, None)
        await msg.reply_text(f"{emo('❌')} Cancelled.", parse_mode="HTML",
                             reply_markup=main_reply_kb(uid)); return
    state = temp_data.get(uid)
    if not state: return
    to_uid = state.get('to_uid')
    try: amt = int(re.sub(r'[^\d]', '', text))
    except:
        await msg.reply_text(f"{emo('❌')} Invalid.", parse_mode="HTML"); return
    if amt < 10:
        await msg.reply_text(f"{emo('⚠️')} Min ₹10.", parse_mode="HTML"); return
    fee_pct = get_transfer_fee(); fee = int(amt * fee_pct / 100); receive = amt - fee
    if receive < 1:
        await msg.reply_text(f"{emo('⚠️')} Too low.", parse_mode="HTML"); return
    r = get_user(uid)
    if safe_get(r, 'balance', 0) < amt:
        await msg.reply_text(f"<b>{emo('❌')} INSUFFICIENT</b>", parse_mode="HTML"); return
    async with get_user_lock(uid):
        cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=? AND balance>=?", (amt, uid, amt))
        if cur.rowcount == 0:
            await msg.reply_text(f"{emo('❌')} Failed.", parse_mode="HTML")
            temp_data.pop(uid, None); return
        old_from = safe_get(r, 'balance', 0)
        update_balance(to_uid, receive)
        cur.execute("INSERT INTO balance_transfers (from_uid, to_uid, amount, fee, received) VALUES (?,?,?,?,?)",
                    (uid, to_uid, amt, fee, receive))
        db.commit()
        record_balance_history(uid, -amt, "transfer_out", "p2p", f"To {to_uid}", old_from, old_from - amt)
        rec_r = cur.execute("SELECT balance FROM users WHERE user_id=?", (to_uid,)).fetchone()
        rec_new = rec_r["balance"] if rec_r else 0
        record_balance_history(to_uid, receive, "transfer_in", "p2p", f"From {uid}", rec_new - receive, rec_new)
    temp_data.pop(uid, None)
    await log_balance_transfer(uid, to_uid, amt, fee, receive)
    await msg.reply_text(
        f"<b>{emo('✅')} SUCCESS!</b>\n\n{emo('📤')} Sent: ₹{amt}\n{emo('💸')} Fee: ₹{fee}\n"
        f"{emo('📥')} Received: ₹{receive}",
        parse_mode="HTML", reply_markup=main_reply_kb(uid))
    try: await _tg_post("sendMessage", {"chat_id": to_uid, "parse_mode": "HTML",
        "text": f"<b>{emo('🎉')} RECEIVED!</b>\n📥 ₹{receive}\n👤 From: <code>{uid}</code>"})
    except: pass


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import BTN_CANCEL, ibtn, main_reply_kb
from config import (
    BINANCE_ID, BINANCE_QR, CWALLET_ID, CWALLET_QR, IMAP_POLL_INTERVAL, POLYGON_ID,
    POLYGON_QR, TRON_ID, TRON_QR, UPI_MERCHANT_NAME, UPI_VERIFY_WINDOW_SECONDS, log
)
from context import cur, db
from database import (
    get_fampay_upi_id, get_min_deposit, get_rate, get_transfer_fee, get_user,
    is_txn_used_by_other_order, is_utr_used_by_other_order, safe_get, update_balance
)
from emojis import emo
from fampay import _send_double_payment_alert, _send_mismatch_alert
from history import record_balance_history
from logs import (
    _full_name, _now_str, get_log_targets, log_balance_transfer, log_deposit,
    log_referral_bonus
)
from rich_ui import _tg_post, _tg_send_photo_buffer
from state import deposit_input, get_user_lock, temp_data, waiting_proof, waiting_utr
from utils import QR_AVAILABLE, create_upi_url, generate_qr_png_bytes, generate_unique_order_id
