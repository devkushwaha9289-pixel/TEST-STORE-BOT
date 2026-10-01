#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP Mini App Backend (FastAPI)
Serves the Mini App + REST APIs + Health endpoints.
Validates Telegram WebApp initData.
Reads the same SQLite DB used by the bot.
"""
import os, sys, json, hmac, hashlib, sqlite3, time, secrets, string, asyncio
from urllib.parse import parse_qsl, quote
from datetime import timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ---------- paths ----------
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOTS_CONFIG = os.path.join(BASE_DIR, "bots_config.json")
STATIC_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

IST          = timezone(timedelta(hours=5, minutes=30))
ORDER_PREFIX = "VILLAGEEsms"
UPI_NAME     = "VILLAGEE SMS"

_START_TS = time.time()

# ---------- helpers ----------
def load_bots():
    try:
        with open(BOTS_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f).get("bots", {})
    except Exception:
        return {}

def get_bot_by_username(un: str):
    for token, info in load_bots().items():
        if info.get("username") == un:
            return {"token": token, **info}
    return None

def ensure_shared_schema(con):
    """Add columns used to bridge Mini App purchases with the Telegram bot."""
    migrations = [
        ("order_id", "TEXT"),
        ("source", "TEXT DEFAULT 'bot'"),
        ("status", "TEXT DEFAULT 'Completed'"),
    ]
    for col, typ in migrations:
        try:
            con.execute(f"ALTER TABLE orders ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    try:
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id) WHERE order_id IS NOT NULL")
    except Exception:
        pass
    try:
        con.commit()
    except Exception:
        pass


def open_db(username: str):
    path = os.path.join(BASE_DIR, "bots", username, "otp_bot_final.db")
    if not os.path.exists(path):
        return None
    con = sqlite3.connect(path, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    ensure_shared_schema(con)
    return con

def validate_init(init_data: str, bot_token: str):
    """Verify Telegram WebApp initData using bot token."""
    try:
        d = dict(parse_qsl(init_data, keep_blank_values=True))
        received = d.pop("hash", None)
        if not received:
            return None
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calc   = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received):
            return None
        u = d.get("user")
        return json.loads(u) if u else None
    except Exception:
        return None

def gs(con, key, default=""):
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default

def gen_oid():
    return f"{ORDER_PREFIX}{secrets.token_hex(5)}{secrets.token_hex(2).upper()}"

def upi_url(upi, amt, oid, name):
    return (f"upi://pay?pa={quote(upi)}&pn={quote(name)}"
            f"&am={amt}&tr={oid}&tn={quote('Order ' + oid)}")

def _uptime_str(sec):
    s = int(sec)
    d, s = divmod(s, 86400); h, s = divmod(s, 3600); m, s = divmod(s, 60)
    out = []
    if d: out.append(f"{d}d")
    if h: out.append(f"{h}h")
    if m: out.append(f"{m}m")
    out.append(f"{s}s")
    return " ".join(out)

# ---------- app ----------
app = FastAPI(title="VILLAGEE SMS SHOP Mini App")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ============================================================
# ROOT + HEALTH
# ============================================================
@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/health")
async def health():
    # Public endpoint: do not expose bot usernames, owner IDs, user counts,
    # master IDs, tokens, or other private bot metadata.
    try:
        from context import BOT_CONTEXTS
        running = sum(1 for ctx in BOT_CONTEXTS if ctx.started)
        healthy = running > 0
        return {
            "status": "ok" if healthy else "degraded",
            "healthy": healthy,
            "uptime": _uptime_str(time.time() - _START_TS),
            "miniapp": True,
        }
    except Exception:
        return {"status": "error", "healthy": False}

@app.get("/status")
async def status():
    # Public endpoint kept intentionally minimal. Bot/admin metadata is private.
    try:
        from context import BOT_CONTEXTS
        running = sum(1 for ctx in BOT_CONTEXTS if ctx.started)
        return {
            "store": "VILLAGEE SMS SHOP",
            "version": "28.4",
            "uptime": _uptime_str(time.time() - _START_TS),
            "miniapp": True,
            "running": bool(running),
        }
    except Exception:
        return {"status": "error"}

@app.get("/ping")
async def ping():
    return "pong"


# ============================================================
# AUTH
# ============================================================
async def auth(
    x_bot_username: str = Header(..., alias="X-Bot-Username"),
    x_init_data:    str = Header(..., alias="X-Init-Data"),
):
    bot = get_bot_by_username(x_bot_username)
    if not bot:
        raise HTTPException(401, "Unknown bot")
    user = validate_init(x_init_data, bot["token"])
    if not user:
        raise HTTPException(401, "Invalid initData")
    return {"user": user, "bot": bot, "un": x_bot_username}


async def run_in_bot_context(username: str, coro_factory):
    """Execute a bot-module coroutine on the owning bot event loop.

    The bot runner uses one asyncio loop per bot. Mini App FastAPI runs on a
    different loop, so direct calls to bot handlers would lose the current
    BotContext. This bridge preserves the correct context for multi-bot use.
    """
    from context import BOTS_BY_USERNAME, _current_bot
    ctx = BOTS_BY_USERNAME.get(username)
    if not ctx or not ctx.started or not ctx.telethon_loop:
        raise HTTPException(503, "Bot is not ready")

    async def runner():
        tok = _current_bot.set(ctx)
        try:
            return await coro_factory()
        finally:
            _current_bot.reset(tok)

    fut = asyncio.run_coroutine_threadsafe(runner(), ctx.telethon_loop)
    try:
        return await asyncio.wrap_future(fut)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


# ============================================================
# CONFIG
# ============================================================
@app.get("/api/config")
async def api_config(a=Depends(auth)):
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        return {
            "store_name":  "VILLAGEE SMS SHOP",
            "support_url": gs(con, "support_url", "https://t.me/Z4X_Silent_Boy"),
            "min_deposit": int(float(gs(con, "min_deposit", "10"))),
            "usdt_rate":   float(gs(con, "usdt_rate", "90")),
            "upi_manual":  gs(con, "manual_upi_id", ""),
            "upi_auto":    gs(con, "fampay_upi_id", ""),
            "bot_status":  gs(con, "bot_status", "on"),
            "buy1":        gs(con, "buy1_status", "on"),
            "buy2":        gs(con, "buy2_status", "on"),
            "buy3":        gs(con, "buy3_status", "on"),
            "qr_provider": "https://api.qrserver.com/v1/create-qr-code/",
            "features": {
                "server1": gs(con, "buy1_status", "on") == "on",
                "server2": gs(con, "buy2_status", "on") == "on",
                "server3": gs(con, "buy3_status", "on") == "on",
                "wallet": gs(con, "upi_status", "on") == "on",
                "referral": True,
            },
        }
    finally:
        con.close()


# ============================================================
# ME
# ============================================================
@app.get("/api/me")
async def api_me(a=Depends(auth)):
    uid = a["user"]["id"]
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        r = con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        if not r:
            fn = a["user"].get("first_name", "")
            un = a["user"].get("username", "")
            con.execute(
                "INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?,?,?)",
                (uid, fn, un),
            )
            con.commit()
            r = con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        return dict(r)
    finally:
        con.close()


# ============================================================
# SERVERS
# ============================================================
@app.get("/api/servers")
async def api_servers(a=Depends(auth)):
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        s2 = con.execute(
            "SELECT COUNT(*) FROM stock WHERE available=1 AND server='SERVER2'"
        ).fetchone()[0]
        s3 = con.execute(
            "SELECT COUNT(*) FROM file_products WHERE active=1"
        ).fetchone()[0]
        return {
            "s1": {"enabled": gs(con, "buy1_status", "on") == "on"},
            "s2": {"enabled": gs(con, "buy2_status", "on") == "on", "count": s2},
            "s3": {"enabled": gs(con, "buy3_status", "on") == "on", "count": s3},
        }
    finally:
        con.close()


# ============================================================
# SERVER 2 (Telegram accounts)
# ============================================================
@app.get("/api/s2/categories")
async def api_s2_cats(a=Depends(auth)):
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        rows = con.execute("""
            SELECT name, emoji FROM custom_categories
            WHERE server='SERVER2' AND active=1
            ORDER BY sort_order, id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()

@app.get("/api/s2/category/{cat}")
async def api_s2_countries(cat: str, a=Depends(auth)):
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        rows = con.execute("""
            SELECT country_name as country, country_icon as icon,
                   MIN(price) as min_price, COUNT(*) as count
            FROM stock
            WHERE available=1 AND server='SERVER2' AND category=?
            GROUP BY country_name ORDER BY country_name
        """, (cat,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()

@app.get("/api/s2/{cat}/{country}")
async def api_s2_items(cat: str, country: str, a=Depends(auth)):
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        rows = con.execute("""
            SELECT phone, country_icon as icon, price
            FROM stock
            WHERE available=1 AND server='SERVER2'
              AND category=? AND country_name=?
            ORDER BY price ASC LIMIT 100
        """, (cat, country)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()

@app.get("/api/item/{phone}")
async def api_item(phone: str, a=Depends(auth)):
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        r = con.execute(
            "SELECT * FROM stock WHERE phone=? AND available=1", (phone,)
        ).fetchone()
        if not r:
            raise HTTPException(404, "Not found")
        return dict(r)
    finally:
        con.close()


# ============================================================
# SERVER 3 (files / panels / OSINT)
# ============================================================
@app.get("/api/s3/sections")
async def api_s3_sections(a=Depends(auth)):
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        rows = con.execute(
            "SELECT DISTINCT section FROM file_products WHERE active=1"
        ).fetchall()
        return [r["section"] for r in rows]
    finally:
        con.close()

@app.get("/api/s3/{section}")
async def api_s3_items(section: str, a=Depends(auth)):
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        rows = con.execute("""
            SELECT id, name, price, description, file_link, api_endpoint, item_code
            FROM file_products
            WHERE section=? AND active=1
            ORDER BY sort_order, id
        """, (section,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


# ============================================================
# PURCHASE (S2 from Mini App)
# ============================================================
class PurchaseReq(BaseModel):
    phone: str

@app.post("/api/purchase")
async def api_purchase(req: PurchaseReq, a=Depends(auth)):
    uid = a["user"]["id"]
    phone = (req.phone or "").strip()
    if not phone:
        raise HTTPException(400, "Phone is required")

    # IMPORTANT: the real Telegram purchase worker performs the debit, stock
    # reservation, Telethon validation and auto-OTP setup. Do not duplicate
    # those operations in the Mini App DB connection.
    try:
        from server2 import process_purchase_from_miniapp
        return await run_in_bot_context(
            a["un"],
            lambda: process_purchase_from_miniapp(uid, phone),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


class FilePurchaseReq(BaseModel):
    product_id: int

@app.post("/api/purchase/file")
async def api_purchase_file(req: FilePurchaseReq, a=Depends(auth)):
    try:
        from server3 import process_file_purchase_from_miniapp
        return await run_in_bot_context(
            a["un"],
            lambda: process_file_purchase_from_miniapp(a["user"]["id"], int(req.product_id)),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


class PaymentVerifyReq(BaseModel):
    order_id: str
    utr: Optional[str] = None
    txn: Optional[str] = None


async def _complete_miniapp_upi_order(order_id, uid, amount, utr=None, txn=None):
    """Use the bot's canonical UPI completion path for Mini App verification."""
    from payments import complete_upi_order
    return await complete_upi_order(
        order_id, uid, amount, None, "miniapp_utr", utr=utr, txn=txn
    )

@app.post("/api/verify-payment")
async def api_verify_payment(req: PaymentVerifyReq, a=Depends(auth)):
    uid = a["user"]["id"]
    utr = (req.utr or "").strip().upper()
    txn = (req.txn or "").strip().upper()
    if not utr and not txn:
        raise HTTPException(400, "Enter UTR or Transaction ID")
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        order = con.execute(
            "SELECT order_id, user_id, amount, status FROM upi_orders WHERE order_id=? AND user_id=?",
            (req.order_id, uid),
        ).fetchone()
        if not order:
            raise HTTPException(404, "Payment order not found")
        if order["status"] == "success":
            return {"verified": True, "status": "success", "message": "Already credited"}
        if order["status"] in ("expired", "failed", "mismatch", "duplicate"):
            raise HTTPException(400, f"Order is {order['status']}")

        # Manual UPI orders are approved by the Telegram admin workflow.
        # The Mini App can submit the UTR here, after which the same owner
        # approval buttons used by the Telegram bot are sent to the owner.
        manual = con.execute(
            "SELECT order_id, amount, status FROM manual_upi_orders WHERE order_id=? AND user_id=?",
            (req.order_id, uid),
        ).fetchone()
        if manual:
            if manual["status"] == "approved":
                return {"verified": True, "status": "success", "message": "Already credited"}
            if manual["status"] in ("rejected", "expired"):
                raise HTTPException(400, f"Order is {manual['status']}")
            con.execute("UPDATE manual_upi_orders SET utr=?, status='submitted' WHERE order_id=?",
                        (utr or txn, req.order_id))
            con.execute("UPDATE upi_orders SET utr=?, status='manual_pending' WHERE order_id=?",
                        (utr or txn, req.order_id))
            con.commit()
            try:
                from manual_upi import submit_manual_upi_from_miniapp
                await run_in_bot_context(
                    a["un"],
                    lambda: submit_manual_upi_from_miniapp(uid, req.order_id, utr or txn),
                )
            except Exception as e:
                raise HTTPException(400, str(e))
            return {
                "verified": False, "status": "manual_pending",
                "message": "UTR submitted. Waiting for admin approval.",
            }

        # Find the bank/FamPay record by UTR, TXN or order id.
        conditions = []
        params = []
        if utr:
            conditions.append("UPPER(COALESCE(utr,''))=?")
            params.append(utr)
        if txn:
            conditions.append("UPPER(COALESCE(txn_id,''))=?")
            params.append(txn)
        where = " OR ".join(conditions)
        match = con.execute(
            f"SELECT msg_id, amount, utr, txn_id, order_id FROM fampay_emails WHERE {where} ORDER BY received_ts DESC LIMIT 1",
            params,
        ).fetchone()
        if not match:
            return {"verified": False, "status": "not_found", "message": "UTR/TXN not found yet. Wait and try again."}

        # Reject reuse of an already successful UTR/TXN.
        dup = None
        if match["utr"]:
            dup = con.execute("SELECT order_id FROM upi_orders WHERE UPPER(COALESCE(utr,''))=UPPER(?) AND status='success' AND order_id!=? LIMIT 1", (match["utr"], req.order_id)).fetchone()
        if not dup and match["txn_id"]:
            dup = con.execute("SELECT order_id FROM upi_orders WHERE UPPER(COALESCE(txn_id,''))=UPPER(?) AND status='success' AND order_id!=? LIMIT 1", (match["txn_id"], req.order_id)).fetchone()
        if dup:
            con.execute("UPDATE upi_orders SET status='duplicate', utr=?, txn_id=? WHERE order_id=?", (match["utr"], match["txn_id"], req.order_id))
            con.commit()
            return {"verified": False, "status": "duplicate", "message": "This payment reference was already used."}

        try:
            paid = float(match["amount"])
        except Exception:
            paid = 0.0
        expected = float(order["amount"])
        if abs(paid - expected) > 0.01:
            con.execute("UPDATE upi_orders SET status='mismatch', paid_amount=?, utr=?, txn_id=?, verified_via='miniapp_utr' WHERE order_id=?",
                        (paid, match["utr"], match["txn_id"], req.order_id))
            con.commit()
            return {"verified": False, "status": "mismatch", "expected": expected, "paid": paid,
                    "message": f"Amount mismatch. Expected ₹{int(expected)}, found ₹{paid:g}."}

        # Mark the exact bank/FamPay email as consumed, then let the same
        # bot-side completion function perform the credit.  This keeps Mini
        # App and Telegram Bot verification identical (balance, history,
        # referral bonus, duplicate protection, notifications, etc.).
        con.execute("UPDATE fampay_emails SET matched_order_id=? WHERE msg_id=?",
                    (req.order_id, match["msg_id"]))
        con.commit()

        try:
            result = await run_in_bot_context(
                a["un"],
                lambda: _complete_miniapp_upi_order(
                    req.order_id, uid, int(expected), match["utr"], match["txn_id"]
                ),
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, str(e))

        if not result:
            return {"verified": False, "status": "already_processed",
                    "message": "Payment was already processed or is no longer pending."}

        return {"verified": True, "status": "success", "amount": int(expected),
                "message": f"₹{int(expected)} credited successfully."}
    finally:
        con.close()


# ============================================================
# DEPOSITS
# ============================================================
class DepositReq(BaseModel):
    amount: int

@app.post("/api/deposit/manual")
async def api_dep_manual(req: DepositReq, a=Depends(auth)):
    uid = a["user"]["id"]
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        min_d = int(float(gs(con, "min_deposit", "10")))
        if req.amount < min_d:
            raise HTTPException(400, f"Min ₹{min_d}")
        upi = gs(con, "manual_upi_id", "")
        if not upi:
            raise HTTPException(400, "Manual UPI not configured")
        oid = gen_oid()
        con.execute("""
            INSERT INTO upi_orders
            (order_id, user_id, amount, status, created_ts, verified_via)
            VALUES (?,?,?,?,?,?)
        """, (oid, uid, req.amount, "pending", time.time(), "manual_upi"))
        con.execute("""
            INSERT OR REPLACE INTO manual_upi_orders
            (order_id, user_id, amount, status, created_ts)
            VALUES (?,?,?,?,?)
        """, (oid, uid, req.amount, "pending", time.time()))
        con.commit()
        return {
            "ok": True,
            "order_id": oid,
            "upi_id": upi,
            "amount": req.amount,
            "upi_url": upi_url(upi, req.amount, oid, UPI_NAME),
            "instructions": "Pay the exact amount, then enter UTR or Transaction ID below.",
        }
    finally:
        con.close()

@app.post("/api/deposit/auto")
async def api_dep_auto(req: DepositReq, a=Depends(auth)):
    uid = a["user"]["id"]
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        min_d = int(float(gs(con, "min_deposit", "10")))
        if req.amount < min_d:
            raise HTTPException(400, f"Min ₹{min_d}")
        upi = gs(con, "fampay_upi_id", "")
        if not upi:
            raise HTTPException(400, "Auto UPI not configured")
        oid = gen_oid()
        con.execute("""
            INSERT INTO upi_orders
            (order_id, user_id, amount, status, created_ts, verified_via)
            VALUES (?,?,?,?,?,?)
        """, (oid, uid, req.amount, "pending", time.time(), "fampay_auto"))
        con.commit()
        return {
            "ok": True,
            "order_id": oid,
            "upi_id": upi,
            "amount": req.amount,
            "upi_url": upi_url(upi, req.amount, oid, UPI_NAME),
            "poll": True,
        }
    finally:
        con.close()

@app.get("/api/order/{oid}")
async def api_order(oid: str, a=Depends(auth)):
    uid = a["user"]["id"]
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        r = con.execute(
            "SELECT status, amount FROM upi_orders WHERE order_id=? AND user_id=?",
            (oid, uid),
        ).fetchone()
        return dict(r) if r else {"status": "unknown"}
    finally:
        con.close()


# ============================================================
# HISTORY / REFER
# ============================================================
@app.get("/api/history")
async def api_history(a=Depends(auth)):
    uid = a["user"]["id"]
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        rows = con.execute("""
            SELECT phone, country, price, date, section, status, order_id
            FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 50
        """, (uid,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()

@app.get("/api/deposit-history")
async def api_deposit_history(a=Depends(auth)):
    uid = a["user"]["id"]
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        rows = con.execute("""
            SELECT amount, method_name, status, date
            FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 50
        """, (uid,)).fetchall()
        auto_rows = con.execute("""
            SELECT amount, 'UPI AUTO' AS method_name, status, date
            FROM upi_orders WHERE user_id=? ORDER BY date DESC LIMIT 50
        """, (uid,)).fetchall()
        manual_rows = con.execute("""
            SELECT amount, 'UPI MANUAL' AS method_name, status, date
            FROM manual_upi_orders WHERE user_id=? ORDER BY date DESC LIMIT 50
        """, (uid,)).fetchall()
        merged = [dict(r) for r in rows] + [dict(r) for r in auto_rows] + [dict(r) for r in manual_rows]
        merged.sort(key=lambda x: str(x.get('date') or ''), reverse=True)
        return merged[:50]
    finally:
        con.close()

@app.get("/api/referrals")
async def api_referrals(a=Depends(auth)):
    uid = a["user"]["id"]
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        rows = con.execute("""
            SELECT user_id, first_name, last_name, username, joined_date
            FROM users WHERE referred_by=? ORDER BY joined_date DESC LIMIT 50
        """, (uid,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()

@app.get("/api/referral-history")
async def api_referral_history(a=Depends(auth)):
    uid = a["user"]["id"]
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        # Older databases may not have the ledger yet; create it lazily.
        con.execute("""CREATE TABLE IF NOT EXISTS referral_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER NOT NULL,
            referred_user_id INTEGER NOT NULL, bonus_amount INTEGER DEFAULT 0,
            deposit_amount INTEGER DEFAULT 0, percent REAL DEFAULT 0,
            event_type TEXT DEFAULT 'bonus', date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        con.commit()
        rows = con.execute("""
            SELECT rh.bonus_amount, rh.deposit_amount, rh.percent, rh.event_type, rh.date,
                   rh.referred_user_id, u.first_name, u.last_name, u.username
            FROM referral_history rh
            LEFT JOIN users u ON u.user_id=rh.referred_user_id
            WHERE rh.referrer_id=? ORDER BY rh.id DESC LIMIT 50
        """, (uid,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()

@app.get("/api/refer")
async def api_refer(a=Depends(auth)):
    uid = a["user"]["id"]
    return {"link": f"https://t.me/{a['un']}?start=REF{uid}"}


# ============================================================
# RUN (standalone)
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("MINIAPP_PORT", "8080")))
    uvicorn.run(app, host="0.0.0.0", port=port)
