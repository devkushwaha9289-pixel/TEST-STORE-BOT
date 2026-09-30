#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# VILLAGEE SMS SHOP — ULTIMATE v28.3  (ALL-IN-ONE)
# ============================================================
#  ✅ Bot (background thread)
#  ✅ Flask Health Server (main thread — Render-safe, PORT env)
#  ✅ Mini App (FastAPI, background thread — MINIAPP_PORT env)
#  ✅ FamPay NEW format (UTR/TXN only)
#  ✅ Conflict recovery (deleteWebhook + drop_pending_updates)
#  ✅ Ek command: `python main.py` → sab kuch chalu
# ============================================================
"""
ENTRY POINT — run:  python main.py
"""

import os
import sys
import time
import asyncio
import logging
import threading

# ============================================================
# EARLY LOGGING SETUP
# ============================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("villagee.main")


# ============================================================
# CONFIG (read early so all threads see same values)
# ============================================================
HEALTH_PORT   = int(os.getenv("PORT", "8000"))
HEALTH_HOST   = os.getenv("HEALTH_HOST", "0.0.0.0")
MINIAPP_PORT  = int(os.getenv("MINIAPP_PORT", "8080"))
MINIAPP_HOST  = os.getenv("MINIAPP_HOST", "0.0.0.0")
MINIAPP_URL   = os.getenv("MINIAPP_URL", "https://test-store-bot-1.onrender.com").rstrip("/")

# Make sure miniapp_integration sees it
if MINIAPP_URL:
    os.environ["MINIAPP_URL"] = MINIAPP_URL


# ============================================================
# 1) FLASK HEALTH SERVER (MAIN THREAD — Render sees PORT)
# ============================================================
def _build_flask_app():
    try:
        from flask import Flask, jsonify
    except Exception as e:
        log.error(f"❌ Flask not installed: {e}")
        log.error("   Fix: pip install flask")
        return None

    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    app = Flask(__name__)
    START_TS = time.time()

    def _snapshot():
        try:
            from context import BOT_CONTEXTS, MASTER_OWNER_ID, _current_bot
        except Exception as e:
            return {"error": str(e), "bots": [], "total_bots": 0,
                    "running": 0, "total_users": 0, "master_owner": None}
        bots = []
        total_users = 0
        running = 0
        for ctx in BOT_CONTEXTS:
            tok = _current_bot.set(ctx)
            try:
                try:
                    users = ctx.cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                except Exception:
                    users = 0
                total_users += users
                if ctx.started:
                    running += 1
                bots.append({
                    "username": ctx.username,
                    "owner_id": ctx.owner_id,
                    "is_master": ctx.is_master,
                    "started": bool(ctx.started),
                    "users": users,
                })
            finally:
                _current_bot.reset(tok)
        return {
            "bots": bots,
            "total_bots": len(BOT_CONTEXTS),
            "running": running,
            "total_users": total_users,
            "master_owner": MASTER_OWNER_ID,
        }

    def _setting(k, d=""):
        try:
            from database import get_setting
            return get_setting(k, d)
        except Exception:
            return d

    def _flag(k):
        return _setting(k, "off") == "on"

    def _uptime(s):
        s = int(s); d, s = divmod(s, 86400); h, s = divmod(s, 3600); m, s = divmod(s, 60)
        out = []
        if d: out.append(f"{d}d")
        if h: out.append(f"{h}h")
        if m: out.append(f"{m}m")
        out.append(f"{s}s")
        return " ".join(out)

    @app.route("/", methods=["GET"])
    def index():
        try:
            from config import STORE_HEADER, ORDER_PREFIX
        except Exception:
            STORE_HEADER = "VILLAGEE SMS SHOP"
            ORDER_PREFIX = "VILLAGEEsms"
        snap = _snapshot()
        healthy = snap.get("running", 0) > 0
        color = "#16a34a" if healthy else "#dc2626"
        status_text = "ONLINE" if healthy else "OFFLINE"

        def pill(v, on="on", lo="ON", lf="OFF"):
            c = "#16a34a" if v == on else "#6b7280"
            return f"<span style='background:{c};color:#fff;padding:2px 8px;border-radius:12px;font-size:12px'>{lo if v==on else lf}</span>"

        bots_html = ""
        for b in snap.get("bots", []):
            dot = "🟢" if b["started"] else "🔴"
            crown = "👑" if b["is_master"] else "🤖"
            bots_html += (
                f"<tr><td>{dot} {crown} @{b['username']}</td>"
                f"<td><code>{b['owner_id']}</code></td>"
                f"<td>{b['users']}</td>"
                f"<td>{'RUNNING' if b['started'] else 'STOPPED'}</td></tr>"
            )
        if not bots_html:
            bots_html = "<tr><td colspan='4'>No bots registered</td></tr>"

        miniapp_box = ""
        if MINIAPP_URL:
            miniapp_box = (
                f"<div class='card'><div class='k'>Mini App</div>"
                f"<div class='v'><a href='{MINIAPP_URL}' target='_blank'>{MINIAPP_URL}</a></div></div>"
            )
        else:
            miniapp_box = (
                "<div class='card'><div class='k'>Mini App</div>"
                "<div class='v' style='color:#f59e0b'>⚠️ NOT SET</div></div>"
            )

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{STORE_HEADER} — Health</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;padding:24px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0b1220;color:#e6edf3}}
.wrap{{max-width:960px;margin:0 auto}}
.hero{{background:linear-gradient(135deg,#111827,#1f2937);border:1px solid #1f2937;border-radius:16px;padding:24px;margin-bottom:20px}}
h1{{margin:0 0 6px;font-size:22px}}
.sub{{color:#9ca3af;font-size:13px}}
.status{{display:inline-block;margin-top:12px;padding:6px 14px;border-radius:999px;background:{color};color:#fff;font-weight:700;font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:20px}}
.card{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:14px}}
.k{{color:#9ca3af;font-size:12px;text-transform:uppercase}}
.v{{font-size:18px;font-weight:600;margin-top:4px;word-break:break-all}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid #1f2937}}
th{{color:#9ca3af;font-size:12px;text-transform:uppercase}}
code{{background:#0f172a;padding:2px 6px;border-radius:6px;font-size:12px}}
.section-title{{margin:24px 0 10px;font-size:15px;color:#cbd5e1}}
footer{{margin-top:28px;color:#6b7280;font-size:12px;text-align:center}}
a{{color:#60a5fa}}
</style></head><body><div class="wrap">
<div class="hero">
  <h1>{STORE_HEADER}</h1>
  <div class="sub">Order Prefix: <code>{ORDER_PREFIX}</code> | Master: <code>{snap.get('master_owner')}</code></div>
  <div class="status">{status_text} — {snap.get('running',0)}/{snap.get('total_bots',0)} bots</div>
</div>
<div class="grid">
  <div class="card"><div class="k">Time (IST)</div><div class="v">{datetime.now(IST).strftime('%d-%m-%Y %I:%M:%S %p')}</div></div>
  <div class="card"><div class="k">Uptime</div><div class="v">{_uptime(time.time()-START_TS)}</div></div>
  <div class="card"><div class="k">Bots</div><div class="v">{snap.get('total_bots',0)}</div></div>
  <div class="card"><div class="k">Users</div><div class="v">{snap.get('total_users',0)}</div></div>
</div>
<div class="section-title">🌐 Mini App</div>
<div class="grid">{miniapp_box}</div>
<div class="section-title">⚙️ Services</div>
<div class="grid">
  <div class="card"><div class="k">Bot</div><div class="v">{pill(_flag('bot_status'))}</div></div>
  <div class="card"><div class="k">S1 LZT</div><div class="v">{pill(_flag('server1_status'))}</div></div>
  <div class="card"><div class="k">S2</div><div class="v">{pill(_flag('buy2_status'))}</div></div>
  <div class="card"><div class="k">S3</div><div class="v">{pill(_flag('buy3_status'))}</div></div>
  <div class="card"><div class="k">UPI</div><div class="v">{pill(_flag('upi_status'))}</div></div>
  <div class="card"><div class="k">FamPay</div><div class="v">{pill(_flag('gmail_verify_enabled'))}</div></div>
</div>
<div class="section-title">💳 Payments</div>
<div class="grid">
  <div class="card"><div class="k">Auto UPI</div><div class="v"><code>{_setting('fampay_upi_id','—') or '—'}</code></div></div>
  <div class="card"><div class="k">Manual UPI</div><div class="v"><code>{_setting('manual_upi_id','—') or '—'}</code></div></div>
  <div class="card"><div class="k">FamPay Email</div><div class="v"><code>{_setting('gmail_email','—') or '—'}</code></div></div>
</div>
<div class="section-title">🤖 Bots</div>
<table><thead><tr><th>Bot</th><th>Owner</th><th>Users</th><th>Status</th></tr></thead>
<tbody>{bots_html}</tbody></table>
<footer>VILLAGEE SMS SHOP v28.3 | <a href="/health">/health</a> | <a href="/status">/status</a> | <a href="/ping">/ping</a></footer>
</div></body></html>"""
        return html, 200

    @app.route("/health", methods=["GET"])
    def health():
        snap = _snapshot()
        healthy = snap.get("running", 0) > 0
        return jsonify({
            "status": "ok" if healthy else "degraded",
            "healthy": healthy,
            "uptime": _uptime(time.time() - START_TS),
            "time_ist": datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p"),
            "miniapp_url": MINIAPP_URL or None,
            "bots": {
                "total": snap.get("total_bots", 0),
                "running": snap.get("running", 0),
                "total_users": snap.get("total_users", 0),
            },
        }), (200 if healthy else 503)

    @app.route("/status", methods=["GET"])
    def status():
        snap = _snapshot()
        return jsonify({
            "store": "VILLAGEE SMS SHOP",
            "version": "28.3",
            "time_ist": datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p"),
            "uptime": _uptime(time.time() - START_TS),
            "miniapp_url": MINIAPP_URL or None,
            "bots": snap,
            "flags": {
                "bot": _flag("bot_status"),
                "server1": _flag("server1_status"),
                "server2": _flag("buy2_status"),
                "server3": _flag("buy3_status"),
                "upi": _flag("upi_status"),
                "fampay": _flag("gmail_verify_enabled"),
            },
        }), 200

    @app.route("/ping", methods=["GET"])
    def ping():
        return "pong", 200

    return app


# ============================================================
# 2) BOT THREAD (background — own asyncio event loop)
# ============================================================
def _bot_thread_target():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        from runner import run_multi_bot
        loop.run_until_complete(run_multi_bot())
    except Exception as e:
        log.exception(f"❌ Bot thread crashed: {e}")
    finally:
        try:
            loop.close()
        except Exception:
            pass


# ============================================================
# 3) MINI APP THREAD (background — uvicorn/FastAPI on own port)
# ============================================================
def _miniapp_thread_target():
    try:
        import uvicorn
        from miniapp.server import app as fastapi_app
    except Exception as e:
        log.warning(f"⚠️  Mini App not started: {e}")
        log.warning("   Fix: pip install -r miniapp/requirements.txt")
        return

    try:
        cfg = uvicorn.Config(
            fastapi_app,
            host=MINIAPP_HOST,
            port=MINIAPP_PORT,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(cfg)
        log.info(f"🌐 Mini App server listening on http://{MINIAPP_HOST}:{MINIAPP_PORT}")
        server.run()
    except Exception as e:
        log.exception(f"❌ Mini App crashed: {e}")


# ============================================================
# MAIN
# ============================================================
def main():
    from config import BOT_TOKEN, ORDER_PREFIX, STORE_HEADER
    from context import BOTS_CONFIG_FILE, MASTER_OWNER_ID
    from utils import QR_AVAILABLE

    print("=" * 62)
    print(f"  {STORE_HEADER} v28.3  (Bot + Flask Health + Mini App)")
    print("=" * 62)
    print(f"  ✅ FamPay NEW format (UTR/TXN only)")
    print(f"  ✅ Flask Health : http://{HEALTH_HOST}:{HEALTH_PORT}/")
    print(f"  🌐 Mini App     : http://{MINIAPP_HOST}:{MINIAPP_PORT}/")
    print(f"  🔗 Mini App URL : {MINIAPP_URL or '⚠️  NOT SET (set MINIAPP_URL for WebApp)'}")
    print(f"  👑 Master Owner : {MASTER_OWNER_ID}")
    print(f"  🤖 Bot Token    : {'SET' if BOT_TOKEN else 'NOT SET'}")
    print(f"  📦 Order Prefix : {ORDER_PREFIX}")
    print(f"  🔲 QR           : {'OK' if QR_AVAILABLE else 'MISSING'}")
    print(f"  📁 Config       : {BOTS_CONFIG_FILE}")
    print(f"  🕒 TZ           : IST (UTC+5:30)")
    print("=" * 62)

    if not QR_AVAILABLE:
        print("⚠️  pip install qrcode[pil]")
    if not MINIAPP_URL:
        print("⚠️  MINIAPP_URL not set → /app command will show 'not configured'")
    if not os.path.exists("bots"):
        os.makedirs("bots", exist_ok=True)

    # ─────────────────────────────────────────────
    # 1️⃣ BOT — background thread
    # ─────────────────────────────────────────────
    bot_thread = threading.Thread(
        target=_bot_thread_target,
        name="bot-runner",
        daemon=True,
    )
    bot_thread.start()
    log.info("🤖 Bot thread started (background)")

    # ─────────────────────────────────────────────
    # 2️⃣ MINI APP — background thread
    # ─────────────────────────────────────────────
    miniapp_thread = threading.Thread(
        target=_miniapp_thread_target,
        name="miniapp-server",
        daemon=True,
    )
    miniapp_thread.start()
    log.info("🌐 Mini App thread started (background)")

    # small grace so both bind their ports before Flask blocks
    time.sleep(0.8)

    # ─────────────────────────────────────────────
    # 3️⃣ FLASK HEALTH — MAIN thread (Render-safe)
    # ─────────────────────────────────────────────
    app = _build_flask_app()
    if app is None:
        log.error("❌ Flask unavailable — bot + miniapp still running (no health endpoint)")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            return

    log.info(f"🌐 Flask health starting on http://{HEALTH_HOST}:{HEALTH_PORT}/")
    try:
        app.run(
            host=HEALTH_HOST,
            port=HEALTH_PORT,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")


if __name__ == "__main__":
    main()
