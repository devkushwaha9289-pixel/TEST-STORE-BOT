#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# VILLAGEE SMS SHOP — ULTIMATE v28.1
# ============================================================
#  ✅ ZIP upload — per-country pricing (S2)
#  ✅ New Stock logs → BOTH admin + public logs
#  ✅ Category emoji IDs (Fake/Scam/Old-Scam-Fake)
#  ✅ Price step after description (single add)
#  ✅ Manage Devices + Logout
#  ✅ S1/S2 Purchase warning (Graph Manager / Plus Messenger)
#  ✅ S1: Reset authorizations BEFORE showing number
#  ✅ OSINT APIs — auto-key generation (30d), docs upload
#  ✅ PANEL purchase → RICH table (secret brand, NO download)
#  ✅ MASTER FULL BACKUP/RESTORE (ZIP: all bots + DBs + sessions)
#  ✅ FORCE JOIN hard-enforced on EVERY interaction
#  ✅ Premium custom-emoji in backup/status messages
#  ✅ v28.1: MANUAL UPI DEPOSIT FLOW
#      - UPI ID: devkushwaha94@ibl
#      - QR auto-generated like FamPay
#      - User sends UTR + screenshot
#      - Request goes to OWNER DM (not log channel)
#      - Approve / Reject(+optional reason) / Change Amount
#      - Change Amount uses keypad, re-shows same request
# ============================================================
"""
ENTRY POINT — run:  python main.py
"""

import os, asyncio

from config import BOT_TOKEN, ORDER_PREFIX, STORE_HEADER
from context import BOTS_CONFIG_FILE, MASTER_OWNER_ID
from runner import run_multi_bot
from utils import QR_AVAILABLE

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print(f"  {STORE_HEADER} v28.1 (Manual UPI Deposit Flow)")
    print(f"  ✅ Manual UPI → QR (same style as FamPay auto)")
    print(f"  ✅ User sends UTR + screenshot")
    print(f"  ✅ Request → OWNER DM (not log channel)")
    print(f"  ✅ Approve / Reject (optional reason) / Change Amount")
    print(f"  ✅ Change Amount uses keypad, re-shows same request")
    print(f"  ✅ UPI MANUAL ID: devkushwaha94@ibl (default)")
    print(f"  ✅ FORCE JOIN hard-enforced everywhere")
    print(f"  ✅ Premium custom emoji in backups")
    print(f"  Master Owner: {MASTER_OWNER_ID}")
    print(f"  Master Bot Token: {'SET' if BOT_TOKEN else 'NOT SET'}")
    print(f"  Order Prefix: {ORDER_PREFIX}")
    print(f"  QR Local: {'OK' if QR_AVAILABLE else 'MISSING'}")
    print(f"  TZ: IST (UTC+5:30)")
    print(f"  Config: {BOTS_CONFIG_FILE}")
    print("=" * 60)
    if not QR_AVAILABLE: print("⚠️  pip install qrcode[pil]")
    if not os.path.exists("bots"): os.makedirs("bots", exist_ok=True)
    try: asyncio.run(run_multi_bot())
    except KeyboardInterrupt: print("\nShutting down...")

if __name__ == "__main__":
    main()
