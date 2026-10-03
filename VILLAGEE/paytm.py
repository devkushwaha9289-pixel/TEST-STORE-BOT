#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Paytm Automatic UPI deposit flow.

Uses Paytm's merchant-status endpoint:
POST /merchant-status/getTxnStatus
JSON: {"MID": "...", "ORDERID": "..."}
"""

import asyncio
import time
from decimal import Decimal, InvalidOperation
from html import escape

import requests
from telegram import InlineKeyboardMarkup


async def check_paytm_status(mid: str, order_id: str) -> dict:
    """Fetch transaction status from Paytm without blocking the bot loop."""
    if not mid:
        raise RuntimeError("PAYTM_MID is not configured")

    def _request():
        r = requests.post(
            PAYTM_STATUS_URL,
            json={"MID": mid, "ORDERID": order_id},
            timeout=PAYTM_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {}

    return await asyncio.to_thread(_request)


def _amount_matches(expected, received) -> bool:
    try:
        return Decimal(str(received)) == Decimal(str(expected))
    except (InvalidOperation, TypeError, ValueError):
        return False


async def _try_paytm_order(order_id: str, notify_uid: bool = False) -> bool:
    row = cur.execute(
        "SELECT amount, status, user_id, qr_msg_id, provider FROM upi_orders WHERE order_id=?",
        (order_id,),
    ).fetchone()
    if not row or str(row["provider"] or "fampay").lower() != "paytm":
        return False
    if row["status"] != "pending":
        return row["status"] == "success"

    mid = get_paytm_mid()
    if not mid:
        return False

    try:
        data = await check_paytm_status(mid, order_id)
    except Exception as e:
        log.warning("Paytm status error for %s: %s", order_id, e)
        return False

    status = str(data.get("STATUS") or "UNKNOWN").upper()
    if status != "TXN_SUCCESS":
        return False

    expected = row["amount"]
    paid = data.get("TXNAMOUNT")
    if not _amount_matches(expected, paid):
        cur.execute(
            """UPDATE upi_orders
               SET status='mismatch', paid_amount=?, verified_via='paytm_api'
               WHERE order_id=? AND status='pending'""",
            (paid, order_id),
        )
        db.commit()
        try:
            await _send_mismatch_alert(
                row["user_id"], order_id, expected, paid,
                None, data.get("TXNID"), "paytm_api"
            )
        except Exception:
            pass
        return False

    txn = str(data.get("TXNID") or "").strip().upper() or None
    if txn:
        existing = is_txn_used_by_other_order(txn, order_id)
        if existing:
            cur.execute(
                """UPDATE upi_orders
                   SET status='duplicate', txn_id=?, verified_via='paytm_api'
                   WHERE order_id=? AND status='pending'""",
                (txn, order_id),
            )
            db.commit()
            try:
                await _send_double_payment_alert(
                    row["user_id"], order_id, None, txn, existing
                )
            except Exception:
                pass
            return False

    ok = await complete_upi_order(
        order_id, row["user_id"], int(row["amount"]),
        row["qr_msg_id"], "paytm_api", txn=txn
    )
    return bool(ok)


async def _paytm_order_watchdog(order_id: str, uid: int, qr_msg_id: int):
    deadline = time.monotonic() + UPI_VERIFY_WINDOW_SECONDS
    while time.monotonic() < deadline:
        if await _try_paytm_order(order_id):
            return
        await asyncio.sleep(max(3.0, PAYTM_VERIFY_INTERVAL))

    row = cur.execute(
        "SELECT status FROM upi_orders WHERE order_id=?",
        (order_id,),
    ).fetchone()
    if row and row["status"] == "pending":
        cur.execute(
            "UPDATE upi_orders SET status='expired' WHERE order_id=?",
            (order_id,),
        )
        db.commit()
        try:
            if qr_msg_id:
                await _tg_post(
                    "deleteMessage",
                    {"chat_id": uid, "message_id": qr_msg_id},
                )
        except Exception:
            pass
        try:
            await _tg_post(
                "sendMessage",
                {
                    "chat_id": uid,
                    "text": (
                        f"{emo('⏰')} <b>Paytm payment session expired.</b>\n\n"
                        "If you already paid, please contact support with the "
                        f"order ID: <code>{escape(order_id)}</code>"
                    ),
                    "parse_mode": "HTML",
                    "reply_markup": InlineKeyboardMarkup(
                        [[ibtn("HOME", "home", emoji="🏠", style="primary")]]
                    ).to_dict(),
                },
            )
        except Exception:
            pass


async def show_paytm_qr(chat_id, uid, amount):
    """Create a Paytm UPI QR and start automatic status polling."""
    mid = get_paytm_mid()
    upi_id = get_paytm_upi_id()
    if not mid or not upi_id:
        await _tg_post(
            "sendMessage",
            {
                "chat_id": uid,
                "text": (
                    f"{emo('❌')} <b>Paytm Automatic is not configured.</b>\n\n"
                    "Set PAYTM_MID and PAYTM_UPI_ID in the environment."
                ),
                "parse_mode": "HTML",
            },
        )
        return

    oid = generate_unique_order_id(uid)
    qr_bytes = None
    try:
        if QR_AVAILABLE:
            qr_bytes = await asyncio.to_thread(
                generate_qr_png_bytes,
                upi_id,
                str(amount),
                oid,
                PAYTM_MERCHANT_NAME,
            )
    except Exception as e:
        log.warning("Paytm QR: %s", e)

    cur.execute(
        """INSERT OR REPLACE INTO upi_orders
           (order_id, user_id, amount, status, qr_msg_id, created_ts, provider)
           VALUES (?,?,?,?,?,?,?)""",
        (oid, uid, amount, "pending", 0, time.time(), "paytm"),
    )
    db.commit()

    usdt_amt = round(amount / get_rate(), 2)
    msg = (
        f"<b>{emo('💳')} PAYTM AUTOMATIC (15-Min)</b>\n\n"
        f"{emo('💰')} Amount: <b>₹{amount}</b> (≈ ${usdt_amt})\n"
        f"{emo('🆔')} Order: <code>{escape(oid)}</code>\n"
        f"{emo('🏦')} UPI: <code>{escape(upi_id)}</code>\n\n"
        f"{emo('1️⃣')} Scan QR / open UPI link\n"
        f"{emo('2️⃣')} Pay exact ₹{amount}\n"
        f"{emo('3️⃣')} Paytm status is checked automatically\n\n"
        f"<b>{emo('⚠️')} Pay exact amount.</b>"
    )
    kb = InlineKeyboardMarkup([
        [ibtn("CHECK NOW", f"check_paytm_{oid}", emoji="✅", style="success")],
        [ibtn("CANCEL", "cancel", emoji="🚫", style="danger")],
    ])

    qr_msg_id = None
    sent = False
    if qr_bytes:
        try:
            r = await _tg_send_photo_buffer(
                uid, qr_bytes, msg, reply_markup=kb.to_dict()
            )
            d = r.json()
            if d.get("ok"):
                qr_msg_id = d.get("result", {}).get("message_id")
                sent = True
        except Exception as e:
            log.warning("Paytm QR send: %s", e)

    if not sent:
        upi_url = create_upi_url(
            upi_id, str(amount), oid, PAYTM_MERCHANT_NAME
        )
        try:
            r = await _tg_post(
                "sendMessage",
                {
                    "chat_id": uid,
                    "text": (
                        f"{msg}\n\n{emo('🔗')} UPI Link:\n"
                        f"<code>{escape(upi_url)}</code>"
                    ),
                    "parse_mode": "HTML",
                    "reply_markup": kb.to_dict(),
                },
                timeout=30,
            )
            d = r.json()
            if d.get("ok"):
                qr_msg_id = d.get("result", {}).get("message_id")
                sent = True
        except Exception as e:
            log.warning("Paytm message send: %s", e)

    if qr_msg_id:
        cur.execute(
            "UPDATE upi_orders SET qr_msg_id=? WHERE order_id=?",
            (qr_msg_id, oid),
        )
        db.commit()
        asyncio.create_task(_paytm_order_watchdog(oid, uid, qr_msg_id))


async def handle_paytm_check(update, context):
    q = update.callback_query
    uid = update.effective_user.id
    oid = q.data.replace("check_paytm_", "", 1)

    row = cur.execute(
        "SELECT amount, status, user_id, provider FROM upi_orders WHERE order_id=?",
        (oid,),
    ).fetchone()
    if (
        not row
        or str(row["user_id"]) != str(uid)
        or str(row["provider"] or "").lower() != "paytm"
    ):
        try:
            await q.answer("Paytm order not found.", show_alert=True)
        except Exception:
            pass
        return

    if row["status"] == "success":
        try:
            await q.answer("Already credited.", show_alert=True)
        except Exception:
            pass
        return

    if row["status"] in ("failed", "mismatch", "duplicate", "expired"):
        try:
            await q.answer(
                f"Order status: {row['status']}",
                show_alert=True,
            )
        except Exception:
            pass
        return

    try:
        await q.answer("Checking Paytm...")
    except Exception:
        pass

    ok = await _try_paytm_order(oid, notify_uid=True)
    if ok:
        return

    row2 = cur.execute(
        "SELECT status FROM upi_orders WHERE order_id=?",
        (oid,),
    ).fetchone()
    status = row2["status"] if row2 else "UNKNOWN"
    if status == "mismatch":
        text = "Amount mismatch. Payment was not credited."
    else:
        text = "Paytm has not marked this order as successful yet."

    try:
        await q.message.reply_text(
            f"{emo('⏳')} <b>Paytm verification</b>\n\n{escape(text)}",
            parse_mode="HTML",
        )
    except Exception:
        pass


from buttons import ibtn
from config import (
    PAYTM_MERCHANT_NAME, PAYTM_REQUEST_TIMEOUT, PAYTM_STATUS_URL,
    PAYTM_VERIFY_INTERVAL, UPI_VERIFY_WINDOW_SECONDS, log,
)
from context import cur, db
from database import (
    get_paytm_mid, get_paytm_upi_id, get_rate,
    is_txn_used_by_other_order,
)
from emojis import emo
from payments import complete_upi_order
from fampay import _send_double_payment_alert, _send_mismatch_alert
from rich_ui import _tg_post, _tg_send_photo_buffer
from utils import (
    QR_AVAILABLE, create_upi_url, generate_qr_png_bytes,
    generate_unique_order_id,
)
