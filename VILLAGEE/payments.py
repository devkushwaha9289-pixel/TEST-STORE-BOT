#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — payments.py
Keypad, UPI auto-deposit, UTR/proof handling, referral bonus, balance transfer.
"""

import re, time, asyncio, sqlite3
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

async def complete_upi_order(oid, uid, amount, qr_msg_id=None, source="fampay_api", utr=None, txn=None):
    # Paytm duplicate protection is based ONLY on BANKTXNID stored as UTR.
    # TXNID is stored for reference but must never block a Paytm payment.
    if utr and is_utr_used_by_other_order(utr, oid): return False
    if txn and not str(source).lower().startswith("paytm") and is_txn_used_by_other_order(txn, oid):
        return False
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
    source_label = {
        "fampay_api": "FamPay Auto",
        "fampay_imap": "FamPay Auto",
        "paytm_api": "Paytm Auto",
    }.get(source, source)
    succ = (f"<b>{emo('✅')} PAYMENT VERIFIED</b>\n\n"
            f"{emo('🆔')} Order: <code>{oid}</code>\n"
            f"{emo('💰')} Added: <b>₹{amount}</b>\n"
            f"{emo('💼')} Old: ₹{old}\n{emo('💬')} New: ₹{new}\n\n"
            f"<i>Source: {source_label} • {_now_str()}</i>")
    try:
        if qr_msg_id: await _tg_post("deleteMessage", {"chat_id": uid, "message_id": qr_msg_id})
    except: pass
    try: await log_deposit(uid, amount, f"UPI ({source_label})", "approved", dep_id=oid, utr=utr or txn)
    except: pass
    try: await process_referral_bonus(uid, amount)
    except: pass
    try:
        await _tg_post("sendMessage", {"chat_id": uid, "text": succ, "parse_mode": "HTML",
            "reply_markup": main_reply_kb(uid).to_dict()})
    except: pass
    return True

async def show_upi_qr(chat_id, uid, amount):
    upi_id = get_fampay_upi_id()
    if not upi_id:
        await _tg_post("sendMessage", {"chat_id": uid, "parse_mode": "HTML",
            "text": f"{emo('❌')} <b>FamPay Automatic is not configured.</b>\nAsk admin to set the FamPay UPI ID."})
        return
    # Reserve the order FIRST (never fails on stale/duplicate pending rows), then build the QR for that exact id.
    oid, existing = reserve_upi_order(uid, "fampay", amount)
    qr_bytes = None
    try:
        qr_bytes = await asyncio.to_thread(generate_qr_png_bytes, upi_id, str(amount), oid, UPI_MERCHANT_NAME)
    except Exception as e: log.error(f"FamPay QR generate failed: {e}")
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
        qr_msg_id = await send_qr_photo(uid, qr_bytes, msg, reply_markup=kb.to_dict())
        sent = bool(qr_msg_id)
    if not sent:
        upi_url = create_upi_url(upi_id, str(amount), oid, UPI_MERCHANT_NAME)
        try:
            r = await _tg_post("sendMessage", {"chat_id": uid,
                "text": f"{msg}\n\n{emo('🔗')} UPI Link:\n<code>{escape(upi_url)}</code>",
                "parse_mode": "HTML", "reply_markup": kb.to_dict()}, timeout=30)
            d = r.json()
            if d.get("ok"):
                qr_msg_id = d.get("result", {}).get("message_id"); sent = True
            else:
                log.warning(f"FamPay msg rejected: {d.get('description')}")
        except Exception as e: log.warning(f"FamPay msg send: {e}")
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
    """CHECK NOW never reads local FamPay/IMAP data.
    It simply opens the UTR/TXN verification flow.
    """
    q = update.callback_query; uid = update.effective_user.id
    oid = q.data.replace("check_upi_", "", 1)
    row = cur.execute("SELECT amount, status, user_id FROM upi_orders WHERE order_id=?", (oid,)).fetchone()
    if not row or str(row["user_id"]) != str(uid):
        try: await q.answer("Order not found", show_alert=True)
        except Exception: pass
        return
    if row["status"] == "success":
        try: await q.answer("Already credited", show_alert=True)
        except Exception: pass
        return
    if row["status"] in ("failed", "mismatch", "duplicate"):
        try: await q.answer("This order cannot be verified again.", show_alert=True)
        except Exception: pass
        return
    try: await q.answer()
    except Exception: pass
    await handle_utr_enter(update, context)


async def handle_utr_enter(update, context):
    q = update.callback_query; data = q.data; uid = update.effective_user.id
    oid = data.split("|", 1)[1]
    row = cur.execute(
        "SELECT amount, status, user_id FROM upi_orders WHERE order_id=?", (oid,)
    ).fetchone()
    if not row or str(row["user_id"]) != str(uid):
        try: await q.answer("Order not found", show_alert=True)
        except Exception: pass
        return
    if row["status"] == "success":
        try: await q.answer("Credited!", show_alert=True)
        except Exception: pass
        return
    waiting_utr[uid] = {"order_id": oid}
    try: await q.answer()
    except Exception: pass
    await q.message.reply_text(
        f"<b>{emo('🔢')} ENTER UTR / TXN</b>\n\n"
        f"{emo('💰')} Amount: ₹{int(float(row['amount']))}\n"
        f"{emo('🆔')} Order: <code>{escape(oid)}</code>\n\n"
        f"Send <b>12-digit numeric UTR</b> OR <b>Transaction ID (TXN)</b>.\n"
        f"Example UTR: <code>878258799122</code>\n"
        f"Example TXN: <code>FMPIB6703774432</code>",
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
    if not info:
        return
    oid = info["order_id"]

    # IMPORTANT: amount/user/status always come from this order in DB.
    row = cur.execute(
        "SELECT amount, status, user_id FROM upi_orders WHERE order_id=?", (oid,)
    ).fetchone()
    if not row or str(row["user_id"]) != str(uid):
        waiting_utr.pop(uid, None)
        await msg.reply_text(f"{emo('❌')} Payment order not found.", parse_mode="HTML",
                             reply_markup=main_reply_kb(uid)); return
    if row["status"] == "success":
        waiting_utr.pop(uid, None)
        await msg.reply_text(f"{emo('✅')} This order is already credited.", parse_mode="HTML",
                             reply_markup=main_reply_kb(uid)); return
    if row["status"] in ("failed", "mismatch", "duplicate"):
        waiting_utr.pop(uid, None)
        await msg.reply_text(f"{emo('⚠️')} Order status: <b>{escape(str(row['status']))}</b>",
                             parse_mode="HTML", reply_markup=main_reply_kb(uid)); return

    expected = float(row["amount"])
    raw = text.strip()
    # Classification requested by the shop:
    # exactly 12 numeric digits => UTR; anything else => TXN.
    clean = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not clean:
        await msg.reply_text(f"{emo('⚠️')} Enter UTR or Transaction ID.", parse_mode="HTML"); return
    if re.fullmatch(r"\d{12}", clean):
        reference_type = "UTR"
    else:
        reference_type = "TXN"
        if len(clean) < 6:
            await msg.reply_text(f"{emo('⚠️')} Invalid Transaction ID.", parse_mode="HTML"); return

    await msg.reply_text(
        f"{emo('🔍')} Verifying <b>{reference_type}</b> <code>{escape(clean)}</code>\n"
        f"Order: <code>{escape(oid)}</code> • Amount: ₹{int(expected)}...",
        parse_mode="HTML")

    # Only Vercel API is called. Gmail/App Password are read from this bot DB
    # inside external_fampay.py; they are never hard-coded here.
    result = await verify_fampay_reference_async(clean, expected, oid)

    if not result.get("success"):
        await msg.reply_text(
            f"{emo('❌')} <b>Verification failed</b>\n\n"
            f"{escape(str(result.get('message') or 'Verification service error.'))}",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [ibtn("RETRY", f"utr_enter|{oid}", emoji="🔄", style="primary")],
                [ibtn("HOME", "home", emoji="🏠", style="primary")]]))
        return

    if not result.get("verified"):
        data = result.get("data") or {}
        received = data.get("received_amount") or data.get("amount")
        message = str(result.get("message") or "Payment not verified")
        if message.lower() == "amount mismatch" or result.get("status") == "mismatch":
            message = f"Amount mismatch. Expected ₹{expected:g}, received ₹{received or '?'}"
        await msg.reply_text(
            f"{emo('⚠️')} <b>Payment not verified</b>\n\n{escape(message)}",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [ibtn("RETRY", f"utr_enter|{oid}", emoji="🔄", style="primary")],
                [ibtn("HOME", "home", emoji="🏠", style="primary")]]))
        return

    data = result.get("data") or {}
    try:
        paid = float(data.get("amount"))
    except Exception:
        paid = None
    if paid is None:
        await msg.reply_text(f"{emo('❌')} API did not return a payment amount. Not credited.",
                             parse_mode="HTML"); return

    # Exact amount check AGAIN locally. Never credit on API/client mismatch.
    if abs(paid - expected) > 0.01:
        utr_v = (data.get("utr") or (clean if reference_type == "UTR" else "")).strip().upper() or None
        txn_v = (data.get("transaction_id") or (clean if reference_type == "TXN" else "")).strip().upper() or None
        cur.execute(
            "UPDATE upi_orders SET status='mismatch', paid_amount=?, utr=?, txn_id=?, verified_via='fampay_api' WHERE order_id=?",
            (paid, utr_v, txn_v, oid))
        db.commit()
        await _send_mismatch_alert(uid, oid, expected, paid, utr_v, txn_v, "fampay_api")
        waiting_utr.pop(uid, None)
        return

    utr_v = (data.get("utr") or (clean if reference_type == "UTR" else "")).strip().upper() or None
    txn_v = (data.get("transaction_id") or (clean if reference_type == "TXN" else "")).strip().upper() or None

    existing = None
    if utr_v:
        existing = is_utr_used_by_other_order(utr_v, oid)
    if not existing and txn_v:
        existing = is_txn_used_by_other_order(txn_v, oid)
    if existing:
        waiting_utr.pop(uid, None)
        cur.execute(
            "UPDATE upi_orders SET status='duplicate', utr=?, txn_id=? WHERE order_id=?",
            (utr_v, txn_v, oid)); db.commit()
        await _send_double_payment_alert(uid, oid, utr_v, txn_v, existing)
        return

    ok = await complete_upi_order(oid, uid, int(expected), None, "fampay_api", utr=utr_v, txn=txn_v)
    waiting_utr.pop(uid, None)
    if ok:
        await msg.reply_text(
            f"{emo('✅')} <b>PAYMENT VERIFIED</b>\n\n"
            f"Order: <code>{escape(oid)}</code>\n"
            f"₹{int(expected)} credited successfully.\n"
            f"Reference: <code>{escape(utr_v or txn_v or clean)}</code>\n"
            f"Source: Vercel FamPay API",
            parse_mode="HTML", reply_markup=main_reply_kb(uid))
    else:
        await msg.reply_text(f"{emo('⚠️')} Already processed or no longer pending.",
                             parse_mode="HTML", reply_markup=main_reply_kb(uid))


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
                # Keep a dedicated referral ledger so the Mini App can show
                # referral history separately from purchase/wallet history.
                before_row = cur.execute("SELECT balance FROM users WHERE user_id=?", (ref,)).fetchone()
                old_balance = int(before_row[0] or 0) if before_row else 0
                update_balance(ref, bonus)
                after_row = cur.execute("SELECT balance FROM users WHERE user_id=?", (ref,)).fetchone()
                new_balance = int(after_row[0] or 0) if after_row else old_balance + bonus
                cur.execute("UPDATE users SET referral_earnings=referral_earnings+? WHERE user_id=?",
                            (bonus, ref))
                cur.execute("""INSERT INTO referral_history
                    (referrer_id, referred_user_id, bonus_amount, deposit_amount, percent, event_type)
                    VALUES (?,?,?,?,?,?)""",
                    (ref, uid, bonus, int(amt), pct, 'bonus'))
                try:
                    cur.execute("""INSERT INTO balance_history
                        (user_id, amount, action, source, note, old_balance, new_balance)
                        VALUES (?,?,?,?,?,?,?)""",
                        (ref, bonus, 'REFERRAL BONUS', 'referral',
                         f'Referral bonus from user {uid} on ₹{int(amt)} deposit',
                         old_balance, new_balance))
                except Exception:
                    pass
                db.commit()
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
    get_active_upi_order, get_fampay_upi_id, get_min_deposit, get_rate, get_transfer_fee, get_user,
    is_txn_used_by_other_order, is_utr_used_by_other_order, safe_get, update_balance
)
from emojis import emo
from fampay import _send_double_payment_alert, _send_mismatch_alert
from external_fampay import verify_fampay_reference_async
from history import record_balance_history
from logs import (
    _full_name, _now_str, get_log_targets, log_balance_transfer, log_deposit,
    log_referral_bonus
)
from rich_ui import _tg_post, _tg_send_photo_buffer, send_qr_photo
from state import deposit_input, get_user_lock, temp_data, waiting_proof, waiting_utr
from utils import QR_AVAILABLE, create_upi_url, generate_qr_png_bytes, generate_unique_order_id
from database import reserve_upi_order
