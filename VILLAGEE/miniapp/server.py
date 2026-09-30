#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP — Mini App Backend (FastAPI)
Serves the Mini App + REST APIs + Health endpoints.
Validates Telegram WebApp initData.
Reads the same SQLite DB used by the bot.
"""
import os, sys, json, hmac, hashlib, sqlite3, time, secrets, string
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

def open_db(username: str):
    path = os.path.join(BASE_DIR, "bots", username, "otp_bot_final.db")
    if not os.path.exists(path):
        return None
    con = sqlite3.connect(path, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
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
app = FastAPI(title="VILLAGEE Mini App")
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
    try:
        from context import BOT_CONTEXTS, MASTER_OWNER_ID
        bots = []
        running = 0
        total_users = 0
        for ctx in BOT_CONTEXTS:
            if ctx.started: running += 1
            try:
                from context import _current_bot
                tok = _current_bot.set(ctx)
                try:
                    u = ctx.cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                except Exception:
                    u = 0
                finally:
                    _current_bot.reset(tok)
            except Exception:
                u = 0
            total_users += u
            bots.append({
                "username": ctx.username,
                "started": bool(ctx.started),
                "owner_id": ctx.owner_id,
                "is_master": ctx.is_master,
                "users": u,
            })
        healthy = running > 0
        return {
            "status": "ok" if healthy else "degraded",
            "healthy": healthy,
            "uptime": _uptime_str(time.time() - _START_TS),
            "miniapp_url": os.getenv("MINIAPP_URL", "") or None,
            "bots": {
                "total": len(bots),
                "running": running,
                "total_users": total_users,
                "list": bots,
            },
            "master_owner": MASTER_OWNER_ID,
        }
    except Exception as e:
        return {"status": "error", "msg": str(e)}

@app.get("/status")
async def status():
    try:
        from context import BOT_CONTEXTS, MASTER_OWNER_ID
        from datetime import datetime
        bots = []
        running = 0
        for ctx in BOT_CONTEXTS:
            if ctx.started: running += 1
            bots.append({
                "username": ctx.username,
                "started": bool(ctx.started),
                "owner_id": ctx.owner_id,
                "is_master": ctx.is_master,
            })
        return {
            "store": "VILLAGEE SMS SHOP",
            "version": "28.4",
            "time_ist": datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p"),
            "uptime": _uptime_str(time.time() - _START_TS),
            "miniapp": True,
            "bots": {"total": len(bots), "running": running, "list": bots},
            "master_owner": MASTER_OWNER_ID,
        }
    except Exception as e:
        return {"status": "error", "msg": str(e)}

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
            "contact_1":   gs(con, "contact_1", "@Z4X_Silent_Boy"),
            "contact_2":   gs(con, "contact_2", "@VILLAGEE_SMS_UPDATEs"),
            "support_url": gs(con, "support_url", "https://t.me/Z4X_Silent_Boy"),
            "min_deposit": int(float(gs(con, "min_deposit", "10"))),
            "usdt_rate":   float(gs(con, "usdt_rate", "90")),
            "upi_manual":  gs(con, "manual_upi_id", ""),
            "upi_auto":    gs(con, "fampay_upi_id", ""),
            "bot_status":  gs(con, "bot_status", "on"),
            "buy1":        gs(con, "buy1_status", "on"),
            "buy2":        gs(con, "buy2_status", "on"),
            "buy3":        gs(con, "buy3_status", "on"),
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
            SELECT id, name, price, description
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
    con = open_db(a["un"])
    if not con:
        raise HTTPException(500, "DB missing")
    try:
        r = con.execute(
            "SELECT * FROM stock WHERE phone=? AND available=1", (req.phone,)
        ).fetchone()
        if not r:
            raise HTTPException(404, "Sold out")
        u = con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        price = int(r["price"])
        disc  = int(u["discount"] or 0) if u else 0
        final = price if not disc else int(price * (100 - disc) / 100)
        bal   = int(u["balance"] or 0) if u else 0
        if bal < final:
            raise HTTPException(400, f"Insufficient balance. Need ₹{final}")
        oid = gen_oid()
        con.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
            (final, uid, final),
        )
        con.execute("UPDATE stock SET available=0 WHERE phone=?", (req.phone,))
        con.execute("""
            INSERT INTO orders (user_id, country, year, price, phone, otp, section)
            VALUES (?,?,?,?,?,?,?)
        """, (uid, r["country_name"], r["account_year"] or 2024,
              final, req.phone, "APP_PENDING", "SERVER2"))
        con.execute("""
            INSERT INTO balance_history
            (user_id, amount, action, source, note, old_balance, new_balance)
            VALUES (?,?,?,?,?,?,?)
        """, (uid, -final, "purchase", "miniapp",
              f"Item {req.phone}", bal, bal - final))
        con.commit()
        return {"ok": True, "order_id": oid, "amount": final,
                "message": "Order created. Open the bot chat to receive OTP."}
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
        """, (oid, uid, req.amount, "manual_pending", time.time(), "manual_upi"))
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
            "instructions": "Open the bot chat → send UTR + screenshot",
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
            SELECT phone, country, price, date FROM orders
            WHERE user_id=? ORDER BY id DESC LIMIT 30
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
