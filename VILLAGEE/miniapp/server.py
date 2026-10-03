#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP Mini App Backend (FastAPI)
Serves the Mini App + REST APIs + Health endpoints.
Validates Telegram WebApp initData.
Reads the same SQLite DB used by the bot.
"""
import os, sys, json, hmac, hashlib, sqlite3, time, secrets, string, asyncio, re
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
def _is_admin_db(con, uid, bot):
    try:
        from context import MASTER_OWNER_ID
    except Exception:
        MASTER_OWNER_ID = 0
    try:
        if int(uid) == int(MASTER_OWNER_ID) or int(uid) == int(bot.get("owner_id") or 0):
            return True
    except Exception:
        pass
    try:
        return bool(con.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)).fetchone())
    except Exception:
        return False


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
    # initData must be fresh (24h) so a leaked string cannot be replayed forever
    try:
        ad = int(dict(parse_qsl(x_init_data)).get("auth_date", "0"))
        if ad and time.time() - ad > 86400:
            raise HTTPException(401, "Session expired. Reopen the Mini App.")
    except HTTPException:
        raise
    except Exception:
        pass
    # ban + maintenance gate (same rules as the bot)
    con = open_db(x_bot_username)
    if con:
        try:
            r = con.execute("SELECT banned FROM users WHERE user_id=?", (user["id"],)).fetchone()
            if r and r["banned"] == 1:
                raise HTTPException(403, "You are banned from this store.")
            if gs(con, "bot_status", "on") != "on" and not _is_admin_db(con, user["id"], bot):
                raise HTTPException(503, "Store is under maintenance. Try again later.")
        finally:
            con.close()
    return {"user": user, "bot": bot, "un": x_bot_username}


def _require_on(un: str, key: str, label: str):
    con = open_db(un)
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        if gs(con, key, "on") != "on":
            raise HTTPException(400, f"{label} is currently disabled")
    finally:
        con.close()


async def bridge(a, fn_name: str, *args):
    """Run miniapp_bridge.<fn_name>(uid, *args) in the owning bot context."""
    import miniapp_bridge as mb
    fn = getattr(mb, fn_name)
    uid = a["user"]["id"]
    return await run_in_bot_context(a["un"], lambda: fn(uid, *args))


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
    try:
        cfg = await bridge(a, "mini_config")
        cfg["qr_provider"] = "https://api.qrserver.com/v1/create-qr-code/"
        return cfg
    except HTTPException as he:
        if he.status_code != 503:
            raise
    # bot not ready yet -> minimal read-only fallback
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        on = lambda k, d="on": gs(con, k, d) == "on"
        return {
            "store_name": (gs(con, "store_name", "") or gs(con, "bot_display_name", "") or a["un"]).strip(),
            "store_logo": (gs(con, "store_logo", "") or "https://i.ibb.co/pvYN5StT/file-00000000495071fa9b861c6819feb241.png").strip(),
            "support_url": gs(con, "support_url", "https://t.me/Z4X_Silent_Boy"),
            "contact_1": gs(con, "contact_1", ""), "contact_2": gs(con, "contact_2", ""),
            "min_deposit": int(float(gs(con, "min_deposit", "10"))),
            "usdt_rate": float(gs(con, "usdt_rate", "90")),
            "transfer_fee": int(float(gs(con, "transfer_fee", "10"))),
            "upi_manual": gs(con, "manual_upi_id", ""), "upi_auto": gs(con, "fampay_upi_id", ""),
            "bot_status": gs(con, "bot_status", "on"),
            "is_admin": _is_admin_db(con, a["user"]["id"], a["bot"]), "is_owner": False,
            "features": {"server1": on("buy1_status"), "server2": on("buy2_status"),
                         "server3": on("buy3_status"), "whatsapp": on("wa_status", "soon"),
                         "wallet": on("upi_status"), "fampay": on("fampay_status"),
                         "paytm": False, "manual": on("manual_upi_status"), "referral": True},
            "qr_provider": "https://api.qrserver.com/v1/create-qr-code/",
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
    _require_on(a["un"], "buy2_status", "Server 2")

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
    _require_on(a["un"], "buy3_status", "Server 3")
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
    reference: Optional[str] = None
    # Backward-compatible fields; server still applies the 12-digit rule.
    utr: Optional[str] = None
    txn: Optional[str] = None


@app.post("/api/verify-payment")
async def api_verify_payment(req: PaymentVerifyReq, a=Depends(auth)):
    """Verify the submitted UTR/TXN against the exact pending order amount.

    Flow:
      1) order_id -> DB -> owner + exact amount
      2) reference -> 12 numeric digits = UTR, otherwise TXN
      3) Gmail/App Password -> current bot DB settings
      4) Vercel verification API -> FamPay email
      5) exact amount check -> credit only on success
    """
    uid = a["user"]["id"]
    raw_ref = req.reference or req.utr or req.txn or ""
    reference = "".join(str(raw_ref).strip().upper().split())
    if not reference:
        raise HTTPException(400, "Enter UTR or Transaction ID")

    # One input is authoritative. If old clients send both fields, reject it
    # instead of silently choosing one.
    if req.utr and req.txn:
        raise HTTPException(400, "Enter only UTR or Transaction ID")

    # Strip common labels users may paste.
    reference = re.sub(
        r"^(?:UTR|TXN|TRANSACTIONID|TRANSACTION_ID|TRANSACTION)[:\-\s]*",
        "", reference,
    )
    reference = re.sub(r"[^A-Z0-9]", "", reference)
    if not reference:
        raise HTTPException(400, "Enter UTR or Transaction ID")

    is_utr = bool(re.fullmatch(r"\d{12}", reference))
    ref_type = "UTR" if is_utr else "TXN"
    if not is_utr and len(reference) < 6:
        raise HTTPException(400, "Invalid Transaction ID")

    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        # IMPORTANT: amount is taken from DB by order_id, never from the client.
        order = con.execute(
            "SELECT order_id, user_id, amount, status, provider, verified_via FROM upi_orders WHERE order_id=? AND user_id=?",
            (req.order_id, uid),
        ).fetchone()
        if not order:
            raise HTTPException(404, "Payment order not found")
        if order["status"] == "success":
            return {"verified": True, "status": "success", "message": "Already credited"}
        if str(order["provider"] or "fampay").lower() == "paytm":
            raise HTTPException(400, "Paytm orders verify automatically. Use 'Check payment'.")
        if order["verified_via"] == "manual_upi" or order["status"] == "manual_pending":
            raise HTTPException(400, "Manual UPI orders are approved by admin after you submit the UTR.")
        if order["status"] != "pending":
            raise HTTPException(400, f"Order is {order['status']}")
        if order["status"] in ("failed", "mismatch", "duplicate"):
            raise HTTPException(400, f"Order is {order['status']}")

        expected = float(order["amount"])

        try:
            from external_fampay import verify_fampay_reference_async
            result = await run_in_bot_context(
                a["un"],
                lambda: verify_fampay_reference_async(reference, expected, req.order_id),
            )
        except Exception as exc:
            raise HTTPException(502, f"FamPay verification service error: {exc}")

        if not result.get("success"):
            return {
                "verified": False,
                "status": result.get("status") or "api_error",
                "reference_type": ref_type,
                "message": result.get("message") or "Verification failed.",
            }

        if not result.get("verified"):
            data = result.get("data") or {}
            received = data.get("received_amount") or data.get("amount")
            is_mismatch = str(result.get("message") or "").lower() == "amount mismatch"
            return {
                "verified": False,
                "status": "mismatch" if is_mismatch else "not_found",
                "reference_type": ref_type,
                "expected": expected,
                "paid": received,
                "data": data,
                "message": result.get("message") or "Payment not verified.",
            }

        data = result.get("data") or {}
        try:
            paid = float(data.get("amount"))
        except Exception:
            paid = None
        if paid is None:
            return {
                "verified": False,
                "status": "api_error",
                "reference_type": ref_type,
                "message": "Verification API did not return a payment amount. Not credited.",
            }

        # Exact amount check AGAIN locally.
        if abs(paid - expected) > 0.01:
            utr_v = (data.get("utr") or (reference if is_utr else "")).strip().upper() or None
            txn_v = (data.get("transaction_id") or (reference if not is_utr else "")).strip().upper() or None
            con.execute(
                "UPDATE upi_orders SET status='mismatch', paid_amount=?, utr=?, txn_id=?, verified_via='fampay_api' WHERE order_id=?",
                (paid, utr_v, txn_v, req.order_id),
            )
            con.commit()
            return {
                "verified": False,
                "status": "mismatch",
                "reference_type": ref_type,
                "expected": expected,
                "paid": paid,
                "data": data,
                "message": f"Amount mismatch. Expected ₹{expected:g}, found ₹{paid:g}.",
            }

        utr_v = (data.get("utr") or (reference if is_utr else "")).strip().upper() or None
        txn_v = (data.get("transaction_id") or (reference if not is_utr else "")).strip().upper() or None

        # Duplicate reference protection.
        dup = None
        if utr_v:
            dup = con.execute(
                "SELECT order_id FROM upi_orders WHERE UPPER(COALESCE(utr,''))=UPPER(?) AND status='success' AND order_id!=? LIMIT 1",
                (utr_v, req.order_id),
            ).fetchone()
        if not dup and txn_v:
            dup = con.execute(
                "SELECT order_id FROM upi_orders WHERE UPPER(COALESCE(txn_id,''))=UPPER(?) AND status='success' AND order_id!=? LIMIT 1",
                (txn_v, req.order_id),
            ).fetchone()
        if dup:
            con.execute(
                "UPDATE upi_orders SET status='duplicate', utr=?, txn_id=? WHERE order_id=?",
                (utr_v, txn_v, req.order_id),
            )
            con.commit()
            return {
                "verified": False,
                "status": "duplicate",
                "reference_type": ref_type,
                "message": "This payment reference was already used.",
            }

        from payments import complete_upi_order
        ok = await run_in_bot_context(
            a["un"],
            lambda: complete_upi_order(
                req.order_id, uid, int(expected), None, "fampay_api", utr=utr_v, txn=txn_v
            ),
        )
        if not ok:
            return {
                "verified": False,
                "status": "already_processed",
                "reference_type": ref_type,
                "message": "Payment was already processed or is no longer pending.",
            }

        return {
            "verified": True,
            "status": "success",
            "reference_type": ref_type,
            "amount": int(expected),
            "order_id": req.order_id,
            "data": data,
            "message": f"₹{int(expected)} credited successfully.",
        }
    finally:
        con.close()

# ============================================================
# DEPOSITS  (all go through the bot logic -> same wallet/locks/checkers)
# ============================================================
class DepositReq(BaseModel):
    amount: int

@app.post("/api/deposit/paytm")
async def api_dep_paytm(req: DepositReq, a=Depends(auth)):
    return await bridge(a, "mini_deposit_paytm", req.amount)

@app.post("/api/deposit/auto")
async def api_dep_auto(req: DepositReq, a=Depends(auth)):
    return await bridge(a, "mini_deposit_fampay", req.amount)

@app.post("/api/deposit/manual")
async def api_dep_manual(req: DepositReq, a=Depends(auth)):
    return await bridge(a, "mini_deposit_manual", req.amount)

class ManualSubmitReq(BaseModel):
    order_id: str
    utr: str

@app.post("/api/deposit/manual/submit")
async def api_dep_manual_submit(req: ManualSubmitReq, a=Depends(auth)):
    return await bridge(a, "mini_manual_submit", req.order_id, req.utr)

class OrderReq(BaseModel):
    order_id: str

@app.post("/api/paytm/check")
async def api_paytm_check(req: OrderReq, a=Depends(auth)):
    return await bridge(a, "mini_check_paytm", req.order_id)

@app.get("/api/order/{oid}")
async def api_order(oid: str, a=Depends(auth)):
    uid = a["user"]["id"]
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        r = con.execute(
            "SELECT status, amount, provider FROM upi_orders WHERE order_id=? AND user_id=?",
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
            SELECT amount, method_name, status, date FROM deposits
            WHERE user_id=? ORDER BY id DESC LIMIT 50""", (uid,)).fetchall()
        upi = con.execute("""
            SELECT amount,
                   CASE WHEN LOWER(COALESCE(provider,''))='paytm' THEN 'PAYTM AUTO'
                        WHEN verified_via LIKE 'manual_upi%' THEN 'UPI MANUAL'
                        ELSE 'FAMPAY AUTO' END AS method_name,
                   status, date, order_id
            FROM upi_orders WHERE user_id=? ORDER BY created_ts DESC LIMIT 50""", (uid,)).fetchall()
        merged = [dict(r) for r in rows] + [dict(r) for r in upi]
        merged.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
        return merged[:60]
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
# REDEEM / TRANSFER / BALANCE HISTORY
# ============================================================
class RedeemReq(BaseModel):
    code: str

@app.post("/api/redeem")
async def api_redeem(req: RedeemReq, a=Depends(auth)):
    return await bridge(a, "mini_redeem", req.code)

class LookupReq(BaseModel):
    to_uid: int

@app.post("/api/transfer/lookup")
async def api_transfer_lookup(req: LookupReq, a=Depends(auth)):
    return await bridge(a, "mini_transfer_lookup", req.to_uid)

class TransferReq(BaseModel):
    to_uid: int
    amount: int

@app.post("/api/transfer")
async def api_transfer(req: TransferReq, a=Depends(auth)):
    return await bridge(a, "mini_transfer", req.to_uid, req.amount)

@app.get("/api/balance-history")
async def api_balance_history(a=Depends(auth)):
    return await bridge(a, "mini_balance_history")


# ============================================================
# ADMIN  (every call re-checks admin rights inside the bot context)
# ============================================================
class KeyReq(BaseModel):
    key: str

class KeyValReq(BaseModel):
    key: str
    value: str

class TargetReq(BaseModel):
    target: str

class BalanceReq(BaseModel):
    user_id: int
    amount: int
    mode: str

class BanReq(BaseModel):
    user_id: int
    banned: bool

class DecideReq(BaseModel):
    order_id: str
    action: str
    reason: Optional[str] = ""

class CouponReq(BaseModel):
    code: str
    amount: int = 0
    max_uses: int = 1

class ProductReq(BaseModel):
    id: int
    action: str
    value: Optional[str] = None

class StockPriceReq(BaseModel):
    category: str
    country: str
    price: int

class BroadcastReq(BaseModel):
    text: str

@app.get("/api/admin/overview")
async def api_admin_overview(a=Depends(auth)):
    return await bridge(a, "mini_admin_overview")

@app.post("/api/admin/toggle")
async def api_admin_toggle(req: KeyReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_toggle", req.key)

@app.post("/api/admin/payment")
async def api_admin_payment(req: KeyValReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_set_payment", req.key, req.value)

@app.post("/api/admin/setting")
async def api_admin_setting(req: KeyValReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_set_setting", req.key, req.value)

@app.post("/api/admin/user")
async def api_admin_user(req: TargetReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_user", req.target)

@app.post("/api/admin/balance")
async def api_admin_balance(req: BalanceReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_balance", req.user_id, req.amount, req.mode)

@app.post("/api/admin/ban")
async def api_admin_ban(req: BanReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_ban", req.user_id, req.banned)

@app.get("/api/admin/manual")
async def api_admin_manual(a=Depends(auth)):
    return await bridge(a, "mini_admin_manual_list")

@app.post("/api/admin/manual/decide")
async def api_admin_manual_decide(req: DecideReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_manual_decide", req.order_id, req.action, req.reason or "")

@app.get("/api/admin/coupons")
async def api_admin_coupons(a=Depends(auth)):
    return await bridge(a, "mini_admin_coupons")

@app.post("/api/admin/coupons/add")
async def api_admin_coupon_add(req: CouponReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_coupon_add", req.code, req.amount, req.max_uses)

@app.post("/api/admin/coupons/delete")
async def api_admin_coupon_delete(req: CouponReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_coupon_delete", req.code)

@app.get("/api/admin/products")
async def api_admin_products(a=Depends(auth)):
    return await bridge(a, "mini_admin_products")

@app.post("/api/admin/products/update")
async def api_admin_product_update(req: ProductReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_product_update", req.id, req.action, req.value)

@app.get("/api/admin/stock")
async def api_admin_stock(a=Depends(auth)):
    return await bridge(a, "mini_admin_stock")

@app.post("/api/admin/stock/price")
async def api_admin_stock_price(req: StockPriceReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_stock_price", req.category, req.country, req.price)

@app.post("/api/admin/broadcast")
async def api_admin_broadcast(req: BroadcastReq, a=Depends(auth)):
    return await bridge(a, "mini_admin_broadcast", req.text)


# ============================================================
# RUN (standalone)
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("MINIAPP_PORT", "8080")))
    uvicorn.run(app, host="0.0.0.0", port=port)
