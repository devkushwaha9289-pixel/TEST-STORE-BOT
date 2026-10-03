#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE — Mini App <-> Bot bridge.

Every coroutine here is executed by miniapp/server.py through
run_in_bot_context(), i.e. on the owning bot's event loop with the correct
BotContext (db / cur / settings).  This guarantees the Mini App uses exactly
the same wallet, locks, payment-checkers and settings as the Telegram bot.

Imports are done inside functions on purpose (circular-import safe).
"""

import re
import time
import asyncio
import sqlite3

PAYMENT_SETTING_KEYS = {
    "fampay_upi_id": "FamPay UPI",
    "paytm_upi_id": "Paytm UPI",
    "paytm_mid": "Paytm MID",
    "manual_upi_id": "Manual UPI",
}
TOGGLE_KEYS = {
    "bot_status": "Bot",
    "buy1_status": "Server 1",
    "buy2_status": "Server 2",
    "buy3_status": "Server 3",
    "wa_status": "WhatsApp",
    "upi_status": "UPI Deposits",
    "fampay_status": "FamPay Auto",
    "paytm_status": "Paytm Auto",
    "manual_upi_status": "UPI Manual",
}
TOGGLE_DEFAULTS = {"wa_status": "soon"}


# ============================================================
# helpers
# ============================================================
DEFAULT_STORE_LOGO = "https://i.ibb.co/pvYN5StT/file-00000000495071fa9b861c6819feb241.png"


def _qr_for(url):
    """Server-side QR (data URI) so the Mini App never depends on an external QR website."""
    try:
        from utils import qr_data_uri
        return qr_data_uri(url)
    except Exception:
        return ""


def _rowd(r):
    return dict(r) if r is not None else None


def _need_admin(uid):
    from database import is_admin
    if not is_admin(uid):
        raise RuntimeError("Admin access required")


def _need_owner(uid):
    from database import is_owner
    if not is_owner(uid):
        raise RuntimeError("Owner access required")


# ============================================================
# CONFIG (global-aware, so Mini App always shows what Admin set)
# ============================================================
async def mini_config(uid):
    from database import (
        get_fampay_upi_id, get_manual_upi_id, get_paytm_mid, get_paytm_upi_id,
        get_min_deposit, get_rate, get_setting, get_transfer_fee, get_support_url,
        get_contact_1, get_contact_2, is_admin, is_owner,
    )
    on = lambda k, d="on": get_setting(k, d) == "on"
    paytm_ready = bool(get_paytm_mid() and get_paytm_upi_id())
    return {
        "store_name": (get_setting("store_name", "") or get_setting("bot_display_name", "") or "Store").strip(),
        "store_logo": (get_setting("store_logo", "") or DEFAULT_STORE_LOGO).strip(),
        "support_url": get_support_url(),
        "contact_1": get_contact_1(),
        "contact_2": get_contact_2(),
        "min_deposit": get_min_deposit(),
        "usdt_rate": get_rate(),
        "transfer_fee": get_transfer_fee(),
        "upi_manual": get_manual_upi_id(),
        "upi_auto": get_fampay_upi_id(),
        "bot_status": get_setting("bot_status", "on"),
        "is_admin": bool(is_admin(uid)),
        "is_owner": bool(is_owner(uid)),
        "features": {
            "server1": on("buy1_status"),
            "server2": on("buy2_status"),
            "server3": on("buy3_status"),
            "whatsapp": on("wa_status", "soon"),
            "wallet": on("upi_status"),
            "fampay": on("upi_status") and on("fampay_status"),
            "paytm": on("upi_status") and on("paytm_status") and paytm_ready,
            "manual": on("upi_status") and on("manual_upi_status"),
            "referral": True,
        },
    }


# ============================================================
# DEPOSITS
# ============================================================
def _check_amount(amount):
    from database import get_min_deposit
    amount = int(amount)
    mn = get_min_deposit()
    if amount < mn:
        raise RuntimeError(f"Minimum deposit is Rs {mn}")
    if amount > 500000:
        raise RuntimeError("Amount too large")
    return amount


async def mini_deposit_paytm(uid, amount):
    from context import cur, db
    from config import PAYTM_MERCHANT_NAME
    from database import (
        get_active_upi_order, get_paytm_mid, get_paytm_upi_id, get_setting, is_banned,
    )
    from utils import generate_unique_order_id, create_upi_url
    from paytm import _paytm_order_watchdog

    if is_banned(uid):
        raise RuntimeError("You are banned")
    if get_setting("upi_status", "on") != "on" or get_setting("paytm_status", "on") != "on":
        raise RuntimeError("Paytm Automatic is disabled")
    mid, upi = get_paytm_mid(), get_paytm_upi_id()
    if not mid or not upi:
        raise RuntimeError("Paytm is not configured by admin")
    amount = _check_amount(amount)

    existing = get_active_upi_order(uid, "paytm", amount)
    fresh = not existing
    if existing:
        oid = existing["order_id"]
    else:
        oid = generate_unique_order_id(uid)
        try:
            cur.execute(
                """INSERT INTO upi_orders
                   (order_id, user_id, amount, status, qr_msg_id, created_ts, provider)
                   VALUES (?,?,?,?,?,?,?)""",
                (oid, uid, amount, "pending", 0, time.time(), "paytm"))
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            existing = get_active_upi_order(uid, "paytm", amount)
            if not existing:
                raise
            oid, fresh = existing["order_id"], False
    if fresh:
        # same auto-verify watchdog as the Telegram flow -> credits even if
        # the user closes the Mini App.
        asyncio.create_task(_paytm_order_watchdog(oid, uid, 0))
    return {
        "ok": True, "provider": "paytm", "order_id": oid, "upi_id": upi,
        "amount": amount, "poll": True,
        "upi_url": create_upi_url(upi, str(amount), oid, PAYTM_MERCHANT_NAME),
        "qr": _qr_for(create_upi_url(upi, str(amount), oid, PAYTM_MERCHANT_NAME)),
        "message": "Pay the exact amount. Paytm status is checked automatically.",
    }


async def mini_check_paytm(uid, oid):
    from context import cur
    from paytm import _try_paytm_order
    row = cur.execute(
        "SELECT status, user_id, provider FROM upi_orders WHERE order_id=?", (oid,)
    ).fetchone()
    if (not row or int(row["user_id"]) != int(uid)
            or str(row["provider"] or "").lower() != "paytm"):
        raise RuntimeError("Paytm order not found")
    if row["status"] == "pending":
        await _try_paytm_order(oid)
    r2 = cur.execute("SELECT status FROM upi_orders WHERE order_id=?", (oid,)).fetchone()
    return {"status": r2["status"] if r2 else "unknown"}


async def mini_deposit_fampay(uid, amount):
    from context import cur, db
    from config import UPI_MERCHANT_NAME
    from database import get_active_upi_order, get_fampay_upi_id, get_setting, is_banned
    from utils import generate_unique_order_id, create_upi_url

    if is_banned(uid):
        raise RuntimeError("You are banned")
    if get_setting("upi_status", "on") != "on" or get_setting("fampay_status", "on") != "on":
        raise RuntimeError("FamPay Automatic is disabled")
    upi = get_fampay_upi_id()
    if not upi:
        raise RuntimeError("Auto UPI not configured")
    amount = _check_amount(amount)

    existing = get_active_upi_order(uid, "fampay", amount)
    if existing and existing["status"] == "pending":
        oid = existing["order_id"]
    else:
        oid = generate_unique_order_id(uid)
        try:
            cur.execute(
                """INSERT INTO upi_orders
                   (order_id, user_id, amount, status, qr_msg_id, created_ts, provider)
                   VALUES (?,?,?,?,?,?,?)""",
                (oid, uid, amount, "pending", 0, time.time(), "fampay"))
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            ex = get_active_upi_order(uid, "fampay", amount)
            if not ex:
                raise
            oid = ex["order_id"]
    return {
        "ok": True, "provider": "fampay", "order_id": oid, "upi_id": upi,
        "amount": amount, "poll": True,
        "upi_url": create_upi_url(upi, str(amount), oid, UPI_MERCHANT_NAME),
        "qr": _qr_for(create_upi_url(upi, str(amount), oid, UPI_MERCHANT_NAME)),
        "message": "Pay exact amount, then submit UTR/TXN (or wait for auto-detect).",
    }


async def mini_deposit_manual(uid, amount):
    from context import cur, db
    from config import UPI_MERCHANT_NAME
    from database import get_manual_upi_id, get_setting, is_banned
    from utils import generate_unique_order_id, create_upi_url

    if is_banned(uid):
        raise RuntimeError("You are banned")
    if get_setting("upi_status", "on") != "on" or get_setting("manual_upi_status", "on") != "on":
        raise RuntimeError("UPI Manual is disabled")
    upi = get_manual_upi_id()
    if not upi:
        raise RuntimeError("Manual UPI not configured")
    amount = _check_amount(amount)

    # reuse a live manual order for the same amount (unique-index safe)
    ex = cur.execute(
        """SELECT order_id FROM upi_orders
           WHERE user_id=? AND amount=? AND status='manual_pending'
             AND verified_via='manual_upi' AND created_ts>=?
           ORDER BY created_ts DESC LIMIT 1""",
        (uid, amount, time.time() - 1800)).fetchone()
    if ex:
        oid = ex["order_id"]
    else:
        oid = generate_unique_order_id(uid)
        try:
            cur.execute(
                """INSERT OR REPLACE INTO upi_orders
                   (order_id, user_id, amount, status, qr_msg_id, created_ts, verified_via, provider)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (oid, uid, amount, "manual_pending", 0, time.time(), "manual_upi", "manual"))
            cur.execute(
                """INSERT OR REPLACE INTO manual_upi_orders
                   (order_id, user_id, amount, status, created_ts) VALUES (?,?,?,?,?)""",
                (oid, uid, amount, "pending", time.time()))
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            ex = cur.execute(
                """SELECT order_id FROM upi_orders WHERE user_id=? AND amount=?
                   AND status='manual_pending' ORDER BY created_ts DESC LIMIT 1""",
                (uid, amount)).fetchone()
            if not ex:
                raise
            oid = ex["order_id"]
    return {
        "ok": True, "provider": "manual", "order_id": oid, "upi_id": upi,
        "amount": amount, "poll": False,
        "upi_url": create_upi_url(upi, str(amount), oid, UPI_MERCHANT_NAME),
        "qr": _qr_for(create_upi_url(upi, str(amount), oid, UPI_MERCHANT_NAME)),
        "message": "Pay the exact amount, then submit your UTR for admin approval.",
    }


async def mini_manual_submit(uid, oid, utr):
    from context import cur
    from manual_upi import submit_manual_upi_from_miniapp
    row = cur.execute("SELECT user_id FROM manual_upi_orders WHERE order_id=?", (oid,)).fetchone()
    if not row or int(row["user_id"]) != int(uid):
        raise RuntimeError("Manual payment order not found")
    res = await submit_manual_upi_from_miniapp(uid, oid, utr)
    res = res or {"ok": True}
    res.setdefault("message", "Submitted. Waiting for admin approval.")
    return res


# ============================================================
# REDEEM / TRANSFER
# ============================================================
async def mini_redeem(uid, code):
    from context import cur, db
    from database import update_balance, is_banned
    from history import record_balance_history
    from state import get_user_lock
    from logs import log_coupon_used

    if is_banned(uid):
        raise RuntimeError("You are banned")
    code = str(code or "").strip().upper()
    if not code:
        raise RuntimeError("Enter a coupon code")
    async with get_user_lock(uid):
        r = cur.execute(
            "SELECT amount, max_uses, used, active FROM coupons WHERE code=?", (code,)
        ).fetchone()
        if not r or not r[3] or r[2] >= r[1]:
            raise RuntimeError("Invalid or expired coupon")
        cur.execute("UPDATE coupons SET used=used+1 WHERE code=? AND used<max_uses", (code,))
        if cur.rowcount != 1:
            db.rollback()
            raise RuntimeError("Invalid or expired coupon")
        b = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        old = b["balance"] if b else 0
        update_balance(uid, r[0])
        db.commit()
        record_balance_history(uid, r[0], "coupon", "coupon", code, old, old + r[0])
    try:
        await log_coupon_used(uid, code, r[0])
    except Exception:
        pass
    return {"ok": True, "amount": int(r[0]), "message": f"Rs {int(r[0])} added to your wallet"}


async def mini_transfer_lookup(uid, to_uid):
    from context import cur
    from database import get_transfer_fee
    to_uid = int(to_uid)
    if to_uid == uid:
        raise RuntimeError("You cannot transfer to yourself")
    r = cur.execute(
        "SELECT user_id, first_name, last_name, username FROM users WHERE user_id=?", (to_uid,)
    ).fetchone()
    if not r:
        raise RuntimeError("User not found (they must have started the bot)")
    name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or "User"
    return {"user_id": to_uid, "name": name, "username": r["username"] or "",
            "fee_percent": get_transfer_fee()}


async def mini_transfer(uid, to_uid, amount):
    from context import cur, db
    from database import get_transfer_fee, get_user, is_banned, safe_get, update_balance
    from history import record_balance_history
    from state import get_user_lock
    from logs import log_balance_transfer
    from rich_ui import _tg_post
    from emojis import emo

    if is_banned(uid):
        raise RuntimeError("You are banned")
    to_uid, amt = int(to_uid), int(amount)
    if to_uid == uid:
        raise RuntimeError("You cannot transfer to yourself")
    if amt < 10:
        raise RuntimeError("Minimum transfer is Rs 10")
    if not cur.execute("SELECT 1 FROM users WHERE user_id=?", (to_uid,)).fetchone():
        raise RuntimeError("Receiver not found")
    fee = int(amt * get_transfer_fee() / 100)
    receive = amt - fee
    if receive < 1:
        raise RuntimeError("Amount too low")
    async with get_user_lock(uid):
        r = get_user(uid)
        old_from = int(safe_get(r, "balance", 0) or 0)
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
                    (amt, uid, amt))
        if cur.rowcount != 1:
            db.rollback()
            raise RuntimeError("Insufficient balance")
        update_balance(to_uid, receive)
        cur.execute(
            "INSERT INTO balance_transfers (from_uid, to_uid, amount, fee, received) VALUES (?,?,?,?,?)",
            (uid, to_uid, amt, fee, receive))
        db.commit()
        record_balance_history(uid, -amt, "transfer_out", "p2p", f"To {to_uid}", old_from, old_from - amt)
        rr = cur.execute("SELECT balance FROM users WHERE user_id=?", (to_uid,)).fetchone()
        rn = rr["balance"] if rr else 0
        record_balance_history(to_uid, receive, "transfer_in", "p2p", f"From {uid}", rn - receive, rn)
    try:
        await log_balance_transfer(uid, to_uid, amt, fee, receive)
    except Exception:
        pass
    try:
        await _tg_post("sendMessage", {
            "chat_id": to_uid, "parse_mode": "HTML",
            "text": f"<b>{emo('🎉')} RECEIVED!</b>\n📥 ₹{receive}\n👤 From: <code>{uid}</code>"})
    except Exception:
        pass
    return {"ok": True, "sent": amt, "fee": fee, "received": receive,
            "message": f"Sent Rs {amt} (fee Rs {fee}). Receiver got Rs {receive}."}


# ============================================================
# BALANCE HISTORY (user)
# ============================================================
async def mini_balance_history(uid):
    from context import cur
    try:
        rows = cur.execute(
            "SELECT * FROM balance_history WHERE user_id=? ORDER BY id DESC LIMIT 60", (uid,)
        ).fetchall()
    except Exception:
        return []
    return [dict(r) for r in rows]


# ============================================================
# ADMIN
# ============================================================
async def mini_admin_overview(uid):
    _need_admin(uid)
    from context import cur
    from database import get_setting, get_fampay_upi_id, get_manual_upi_id, get_paytm_mid, get_paytm_upi_id
    q1 = lambda sql, a=(): (cur.execute(sql, a).fetchone() or [0])[0] or 0
    toggles = []
    for k, label in TOGGLE_KEYS.items():
        toggles.append({"key": k, "label": label,
                        "on": get_setting(k, TOGGLE_DEFAULTS.get(k, "on")) == "on"})
    return {
        "stats": {
            "users": q1("SELECT COUNT(*) FROM users"),
            "banned": q1("SELECT COUNT(*) FROM users WHERE banned=1"),
            "balance_total": q1("SELECT SUM(balance) FROM users"),
            "deposited_total": q1("SELECT SUM(total_deposited) FROM users"),
            "orders": q1("SELECT COUNT(*) FROM orders"),
            "revenue": q1("SELECT SUM(price) FROM orders"),
            "stock_s2": q1("SELECT COUNT(*) FROM stock WHERE available=1 AND server='SERVER2'"),
            "products_s3": q1("SELECT COUNT(*) FROM file_products WHERE active=1"),
            "manual_pending": q1("SELECT COUNT(*) FROM manual_upi_orders WHERE status='submitted'"),
            "mismatch": q1("SELECT COUNT(*) FROM upi_orders WHERE status='mismatch'"),
            "duplicate": q1("SELECT COUNT(*) FROM upi_orders WHERE status='duplicate'"),
        },
        "toggles": toggles,
        "payment": {
            "fampay_upi_id": get_fampay_upi_id(),
            "paytm_upi_id": get_paytm_upi_id(),
            "paytm_mid": get_paytm_mid(),
            "manual_upi_id": get_manual_upi_id(),
        },
        "settings": {
            "min_deposit": get_setting("min_deposit", "10"),
            "usdt_rate": get_setting("usdt_rate", "90"),
            "transfer_fee": get_setting("transfer_fee", "10"),
            "support_url": get_setting("support_url", ""),
            "contact_1": get_setting("contact_1", ""),
            "contact_2": get_setting("contact_2", ""),
        },
    }


async def mini_admin_toggle(uid, key):
    _need_admin(uid)
    from database import get_setting, set_setting
    from logs import log_admin_action
    if key not in TOGGLE_KEYS:
        raise RuntimeError("Unknown toggle")
    cur_v = get_setting(key, TOGGLE_DEFAULTS.get(key, "on"))
    nv = "off" if cur_v == "on" else "on"
    set_setting(key, nv)
    try:
        await log_admin_action(uid, f"MiniApp toggle {TOGGLE_KEYS[key]}", nv.upper())
    except Exception:
        pass
    return {"key": key, "on": nv == "on"}


async def mini_admin_set_payment(uid, key, value):
    _need_admin(uid)
    from database import set_setting, set_global_payment_setting
    from logs import log_admin_action
    if key not in PAYMENT_SETTING_KEYS:
        raise RuntimeError("Unknown payment setting")
    v = re.sub(r"\s+", "", str(value or ""))
    if key == "paytm_mid":
        if not re.fullmatch(r"[A-Za-z0-9_\-]{6,40}", v):
            raise RuntimeError("Invalid Paytm MID")
    else:
        if not re.fullmatch(r"[A-Za-z0-9._\-]{2,}@[A-Za-z0-9._\-]{2,}", v):
            raise RuntimeError("Invalid UPI ID (example: name@paytm)")
    set_setting(key, v)
    if key != "manual_upi_id":  # manual UPI is per-bot, others are global
        set_global_payment_setting(key, v)
    try:
        await log_admin_action(uid, f"MiniApp set {PAYMENT_SETTING_KEYS[key]}", v)
    except Exception:
        pass
    return {"ok": True, "key": key, "value": v}


async def mini_admin_set_setting(uid, key, value):
    _need_admin(uid)
    from database import set_setting
    from logs import log_admin_action
    allowed = {"min_deposit", "usdt_rate", "transfer_fee", "support_url", "contact_1", "contact_2"}
    if key not in allowed:
        raise RuntimeError("Unknown setting")
    v = str(value or "").strip()
    if key in ("min_deposit", "transfer_fee"):
        try:
            n = int(float(v))
        except Exception:
            raise RuntimeError("Number required")
        if n < 0 or (key == "transfer_fee" and n > 90) or (key == "min_deposit" and n < 1):
            raise RuntimeError("Value out of range")
        v = str(n)
    if key == "usdt_rate":
        try:
            if float(v) <= 0:
                raise ValueError
        except Exception:
            raise RuntimeError("Positive number required")
    set_setting(key, v)
    try:
        await log_admin_action(uid, f"MiniApp set {key}", v)
    except Exception:
        pass
    return {"ok": True, "key": key, "value": v}


async def mini_admin_user(uid, target):
    _need_admin(uid)
    from context import cur
    t = re.sub(r"[^\d]", "", str(target or ""))
    r = None
    if t:
        r = cur.execute("SELECT * FROM users WHERE user_id=?", (int(t),)).fetchone()
    if not r:
        un = str(target or "").strip().lstrip("@")
        if un:
            r = cur.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (un,)).fetchone()
    if not r:
        raise RuntimeError("User not found")
    return dict(r)


async def mini_admin_balance(uid, target_uid, amount, mode):
    _need_admin(uid)
    from context import cur, db
    from database import update_balance
    from history import record_balance_history
    from state import get_user_lock
    from logs import log_admin_action
    from rich_ui import _tg_post
    target_uid, amount = int(target_uid), int(amount)
    if amount <= 0:
        raise RuntimeError("Amount must be positive")
    if mode not in ("add", "deduct"):
        raise RuntimeError("Bad mode")
    async with get_user_lock(target_uid):
        r = cur.execute("SELECT balance FROM users WHERE user_id=?", (target_uid,)).fetchone()
        if not r:
            raise RuntimeError("User not found")
        old = int(r["balance"] or 0)
        delta = amount if mode == "add" else -amount
        if old + delta < 0:
            raise RuntimeError("User balance would go negative")
        update_balance(target_uid, delta)
        db.commit()
        record_balance_history(target_uid, delta, "admin_add" if delta > 0 else "admin_deduct",
                               "miniapp_admin", f"By {uid}", old, old + delta)
    try:
        await log_admin_action(uid, f"MiniApp balance {mode}", f"{target_uid} Rs{amount}")
    except Exception:
        pass
    if delta > 0:
        try:
            await _tg_post("sendMessage", {
                "chat_id": target_uid, "parse_mode": "HTML",
                "text": f"💰 <b>₹{amount}</b> was added to your wallet by admin."})
        except Exception:
            pass
    return {"ok": True, "old": old, "new": old + delta}


async def mini_admin_ban(uid, target_uid, banned):
    _need_admin(uid)
    from context import cur, db
    from logs import log_admin_action
    from database import is_admin
    target_uid = int(target_uid)
    if is_admin(target_uid):
        raise RuntimeError("Cannot ban an admin")
    cur.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, target_uid))
    db.commit()
    try:
        await log_admin_action(uid, "MiniApp ban" if banned else "MiniApp unban", str(target_uid))
    except Exception:
        pass
    return {"ok": True, "banned": bool(banned)}


async def mini_admin_manual_list(uid):
    _need_admin(uid)
    from context import cur
    rows = cur.execute(
        """SELECT m.order_id, m.user_id, m.amount, m.utr, m.status, m.created_ts,
                  u.first_name, u.username
           FROM manual_upi_orders m LEFT JOIN users u ON u.user_id=m.user_id
           WHERE m.status='submitted' ORDER BY m.created_ts DESC LIMIT 50"""
    ).fetchall()
    return [dict(r) for r in rows]


async def mini_admin_manual_decide(uid, oid, action, reason=""):
    _need_admin(uid)
    from context import cur
    from manual_upi import complete_manual_upi_order, reject_manual_upi_order
    row = cur.execute(
        "SELECT user_id, amount, status FROM manual_upi_orders WHERE order_id=?", (oid,)
    ).fetchone()
    if not row:
        raise RuntimeError("Order not found")
    if row["status"] not in ("submitted", "pending"):
        raise RuntimeError(f"Order already {row['status']}")
    if action == "approve":
        ok = await complete_manual_upi_order(oid, int(row["user_id"]), int(row["amount"]))
        if ok is False:
            raise RuntimeError("Already approved")
        return {"ok": True, "status": "approved"}
    if action == "reject":
        await reject_manual_upi_order(oid, uid, reason or "Rejected by admin")
        return {"ok": True, "status": "rejected"}
    raise RuntimeError("Bad action")


async def mini_admin_coupons(uid):
    _need_admin(uid)
    from context import cur
    rows = cur.execute("SELECT code, amount, max_uses, used, active FROM coupons").fetchall()
    return [dict(r) for r in rows]


async def mini_admin_coupon_add(uid, code, amount, max_uses):
    _need_admin(uid)
    from context import cur, db
    code = re.sub(r"[^A-Za-z0-9_\-]", "", str(code or "")).upper()
    amount, max_uses = int(amount), int(max_uses)
    if not code or amount <= 0 or max_uses <= 0:
        raise RuntimeError("Code, amount and max uses are required")
    cur.execute("INSERT OR REPLACE INTO coupons (code,amount,max_uses,used,active) VALUES (?,?,?,0,1)",
                (code, amount, max_uses))
    db.commit()
    return {"ok": True, "code": code}


async def mini_admin_coupon_delete(uid, code):
    _need_admin(uid)
    from context import cur, db
    cur.execute("DELETE FROM coupons WHERE code=?", (str(code).upper(),))
    db.commit()
    return {"ok": True}


async def mini_admin_products(uid):
    _need_admin(uid)
    from context import cur
    rows = cur.execute(
        """SELECT id, section, name, price, active, item_code
           FROM file_products ORDER BY section, sort_order, id LIMIT 300"""
    ).fetchall()
    return [dict(r) for r in rows]


async def mini_admin_product_update(uid, pid, action, value=None):
    _need_admin(uid)
    from context import cur, db
    pid = int(pid)
    if not cur.execute("SELECT 1 FROM file_products WHERE id=?", (pid,)).fetchone():
        raise RuntimeError("Product not found")
    if action == "toggle":
        cur.execute("UPDATE file_products SET active=1-COALESCE(active,0) WHERE id=?", (pid,))
    elif action == "price":
        v = int(value)
        if v < 0:
            raise RuntimeError("Invalid price")
        cur.execute("UPDATE file_products SET price=? WHERE id=?", (v, pid))
    elif action == "delete":
        cur.execute("DELETE FROM file_products WHERE id=?", (pid,))
    else:
        raise RuntimeError("Bad action")
    db.commit()
    return {"ok": True}


async def mini_admin_stock(uid):
    _need_admin(uid)
    from context import cur
    rows = cur.execute(
        """SELECT category, country_name, country_icon, COUNT(*) AS n, MIN(price) AS min_price
           FROM stock WHERE available=1 AND server='SERVER2'
           GROUP BY category, country_name ORDER BY category, country_name"""
    ).fetchall()
    return [dict(r) for r in rows]


async def mini_admin_stock_price(uid, category, country, price):
    _need_admin(uid)
    from context import cur, db
    price = int(price)
    if price < 0:
        raise RuntimeError("Invalid price")
    cur.execute(
        "UPDATE stock SET price=? WHERE available=1 AND server='SERVER2' AND category=? AND country_name=?",
        (price, category, country))
    db.commit()
    return {"ok": True, "updated": cur.rowcount}


async def mini_admin_broadcast(uid, text):
    _need_admin(uid)
    from context import cur
    from rich_ui import _tg_post
    from logs import log_admin_action
    text = str(text or "").strip()
    if not text:
        raise RuntimeError("Message is empty")
    if len(text) > 3500:
        raise RuntimeError("Message too long")
    ids = [r[0] for r in cur.execute("SELECT user_id FROM users WHERE COALESCE(banned,0)=0").fetchall()]

    async def _run():
        ok = fail = 0
        for u in ids:
            try:
                r = await _tg_post("sendMessage", {"chat_id": u, "text": text, "parse_mode": "HTML"})
                try:
                    good = r.json().get("ok")
                except Exception:
                    good = True
                ok += 1 if good else 0
                fail += 0 if good else 1
            except Exception:
                fail += 1
            await asyncio.sleep(0.06)
        try:
            await _tg_post("sendMessage", {
                "chat_id": uid, "parse_mode": "HTML",
                "text": f"📣 Broadcast finished.\n✅ Sent: {ok}\n❌ Failed: {fail}"})
        except Exception:
            pass

    asyncio.create_task(_run())
    try:
        await log_admin_action(uid, "MiniApp broadcast", f"{len(ids)} users")
    except Exception:
        pass
    return {"ok": True, "queued": len(ids)}
