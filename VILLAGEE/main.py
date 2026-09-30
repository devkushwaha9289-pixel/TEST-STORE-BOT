#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# VILLAGEE SMS SHOP — ULTIMATE v28.4  (SINGLE PORT)
# ============================================================
#  ✅ FastAPI on $PORT — serves Mini App + Health + Status
#  ✅ Bot on background thread
#  ✅ Render-safe (only uses $PORT)
#  ✅ FamPay NEW format (UTR/TXN only)
# ============================================================
"""
ENTRY POINT — run:  python main.py
"""

import os
import time
import asyncio
import logging
import threading

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("villagee.main")


# ============================================================
# CONFIG
# ============================================================
PORT       = int(os.getenv("PORT", "8000"))
HOST       = os.getenv("HOST", "0.0.0.0")
PUBLIC_URL = os.getenv("MINIAPP_URL", "").rstrip("/")

# Make sure miniapp_integration sees it
if PUBLIC_URL:
    os.environ["MINIAPP_URL"] = PUBLIC_URL


# ============================================================
# BOT THREAD (background — own asyncio loop)
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
# MAIN
# ============================================================
def main():
    from config import BOT_TOKEN, ORDER_PREFIX, STORE_HEADER
    from context import BOTS_CONFIG_FILE, MASTER_OWNER_ID
    from utils import QR_AVAILABLE

    print("=" * 64)
    print(f"  {STORE_HEADER} v28.4  (Single-Port: Mini App + Health + Bot)")
    print("=" * 64)
    print(f"  🌐 Public Port   : {PORT}")
    print(f"  🔗 Mini App URL  : {PUBLIC_URL or '⚠️  MINIAPP_URL NOT SET'}")
    print(f"  👑 Master Owner  : {MASTER_OWNER_ID}")
    print(f"  🤖 Bot Token     : {'SET' if BOT_TOKEN else 'NOT SET'}")
    print(f"  📦 Order Prefix  : {ORDER_PREFIX}")
    print(f"  🔲 QR            : {'OK' if QR_AVAILABLE else 'MISSING'}")
    print(f"  📁 Config        : {BOTS_CONFIG_FILE}")
    print(f"  🕒 TZ            : IST (UTC+5:30)")
    print("=" * 64)

    if not QR_AVAILABLE:
        print("⚠️  pip install qrcode[pil]")
    if not PUBLIC_URL:
        print("⚠️  MINIAPP_URL not set → WebApp menu button won't work")
        print("    Set it to your public URL, e.g.:")
        print("    export MINIAPP_URL=\"https://test-store-bot-1.onrender.com\"")
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
    # 2️⃣ FastAPI (Mini App + Health) — MAIN thread on PORT
    # ─────────────────────────────────────────────
    try:
        import uvicorn
        from miniapp.server import app as fastapi_app
    except Exception as e:
        log.error(f"❌ Cannot load Mini App: {e}")
        log.error("   pip install -r requirements.txt")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            return

    time.sleep(0.5)

    log.info(f"🌐 FastAPI starting on http://{HOST}:{PORT}/")
    log.info(f"   → Mini App  : http://{HOST}:{PORT}/?bot=<username>")
    log.info(f"   → Health    : http://{HOST}:{PORT}/health")
    log.info(f"   → Status    : http://{HOST}:{PORT}/status")

    try:
        uvicorn.run(
            fastapi_app,
            host=HOST,
            port=PORT,
            log_level="warning",
            access_log=False,
        )
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")


if __name__ == "__main__":
    main()
