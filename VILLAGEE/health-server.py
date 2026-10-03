#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — health_server.py
Flask health/status server. Runs on Render (PORT env) or VPS (8000).
Endpoint "/" shows bot health, uptime, bots, users, services, etc.
"""

import os
import time
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, request

# ============================================================
# CONFIG
# ============================================================
DEFAULT_PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HEALTH_HOST", "0.0.0.0")
IST = timezone(timedelta(hours=5, minutes=30))

_START_TS = time.time()

app = Flask(__name__)


# ============================================================
# HELPERS
# ============================================================
def _bots_snapshot():
    try:
        from context import BOT_CONTEXTS, MASTER_OWNER_ID, _current_bot
    except Exception:
        return {"bots": [], "total_bots": 0, "total_users": 0, "running": 0,
                "master_owner": None}

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
                "db_path": ctx.db_path,
                "data_dir": ctx.data_dir,
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


def _setting(key, default=""):
    try:
        from database import get_setting
        return get_setting(key, default)
    except Exception:
        return default


def _flag(key):
    return _setting(key, "off") == "on"


def _uptime_str(seconds):
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


# ============================================================
# ROUTES
# ============================================================
@app.route("/", methods=["GET"])
def index():
    from config import STORE_HEADER, ORDER_PREFIX
    from utils import QR_AVAILABLE

    snap = _bots_snapshot()
    up_s = _uptime_str(time.time() - _START_TS)
    now_ist = datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")

    flags = {
        "bot":        _flag("bot_status"),
        "server1":    _flag("server1_status"),
        "server2":    _flag("buy2_status"),
        "server3":    _flag("buy3_status"),
        "upi":        _flag("upi_status"),
        "fampay":     _flag("gmail_verify_enabled"),
    }
    fampay_email = _setting("gmail_email", "") or "—"
    manual_upi = _setting("manual_upi_id", "") or "—"
    auto_upi = _setting("fampay_upi_id", "") or "—"
    lzt_token = "SET" if _setting("lzt_token", "").strip() else "NOT SET"

    healthy = snap["running"] > 0
    status_color = "#16a34a" if healthy else "#dc2626"
    status_text = "ONLINE" if healthy else "OFFLINE"

    bot_rows = ""
    for b in snap["bots"]:
        dot = "🟢" if b["started"] else "🔴"
        crown = "👑" if b["is_master"] else "🤖"
        bot_rows += (
            f"<tr>"
            f"<td>{dot} {crown} @{b['username']}</td>"
            f"<td><code>{b['owner_id']}</code></td>"
            f"<td>{'YES' if b['is_master'] else 'no'}</td>"
            f"<td>{b['users']}</td>"
            f"<td>{'RUNNING' if b['started'] else 'STOPPED'}</td>"
            f"</tr>"
        )
    if not bot_rows:
        bot_rows = "<tr><td colspan='5'>No bots registered</td></tr>"

    def pill(val, on="on", label_on="ON", label_off="OFF"):
        color = "#16a34a" if val == on else "#6b7280"
        text = label_on if val == on else label_off
        return f"<span style='background:{color};color:#fff;padding:2px 8px;border-radius:12px;font-size:12px'>{text}</span>"

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{STORE_HEADER} — Health</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b1220; color: #e6edf3;
  }}
  .wrap {{ max-width: 960px; margin: 0 auto; }}
  .hero {{
    background: linear-gradient(135deg, #111827, #1f2937);
    border: 1px solid #1f2937; border-radius: 16px; padding: 24px; margin-bottom: 20px;
  }}
  h1 {{ margin: 0 0 6px 0; font-size: 22px; letter-spacing: .5px; }}
  .sub {{ color: #9ca3af; font-size: 13px; }}
  .status {{
    display: inline-block; margin-top: 12px; padding: 6px 14px; border-radius: 999px;
    background: {status_color}; color: #fff; font-weight: 700; font-size: 13px; letter-spacing: .5px;
  }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px; margin-bottom: 20px; }}
  .card {{ background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 14px; }}
  .k {{ color: #9ca3af; font-size: 12px; text-transform: uppercase; letter-spacing: .6px; }}
  .v {{ font-size: 18px; font-weight: 600; margin-top: 4px; word-break: break-all; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #1f2937; }}
  th {{ color: #9ca3af; font-size: 12px; text-transform: uppercase; }}
  code {{ background:#0f172a; padding:2px 6px; border-radius:6px; font-size:12px; }}
  .section-title {{ margin: 24px 0 10px 0; font-size: 15px; color: #cbd5e1; letter-spacing: .4px; }}
  footer {{ margin-top: 28px; color: #6b7280; font-size: 12px; text-align: center; }}
  a {{ color: #60a5fa; }}
</style></head>
<body><div class="wrap">

  <div class="hero">
    <h1>{STORE_HEADER}</h1>
    <div class="sub">Order Prefix: <code>{ORDER_PREFIX}</code> &nbsp;|&nbsp; Master Owner: <code>{snap['master_owner']}</code></div>
    <div class="status">{status_text} — {snap['running']}/{snap['total_bots']} bots</div>
  </div>

  <div class="grid">
    <div class="card"><div class="k">Server Time (IST)</div><div class="v">{now_ist}</div></div>
    <div class="card"><div class="k">Uptime</div><div class="v">{up_s}</div></div>
    <div class="card"><div class="k">Total Bots</div><div class="v">{snap['total_bots']}</div></div>
    <div class="card"><div class="k">Total Users</div><div class="v">{snap['total_users']}</div></div>
    <div class="card"><div class="k">QR Generator</div><div class="v">{'✅ AVAILABLE' if QR_AVAILABLE else '❌ MISSING'}</div></div>
    <div class="card"><div class="k">Server 1 Token</div><div class="v">{lzt_token}</div></div>
  </div>

  <div class="section-title">⚙️ Service Status</div>
  <div class="grid">
    <div class="card"><div class="k">Bot</div><div class="v">{pill(flags['bot'])}</div></div>
    <div class="card"><div class="k">Server 1</div><div class="v">{pill(flags['server1'])}</div></div>
    <div class="card"><div class="k">Server 2</div><div class="v">{pill(flags['server2'])}</div></div>
    <div class="card"><div class="k">Server 3</div><div class="v">{pill(flags['server3'])}</div></div>
    <div class="card"><div class="k">UPI</div><div class="v">{pill(flags['upi'])}</div></div>
    <div class="card"><div class="k">FamPay Auto</div><div class="v">{pill(flags['fampay'])}</div></div>
  </div>

  <div class="section-title">💳 Payment Config</div>
  <div class="grid">
    <div class="card"><div class="k">Auto UPI</div><div class="v"><code>{auto_upi}</code></div></div>
    <div class="card"><div class="k">Manual UPI</div><div class="v"><code>{manual_upi}</code></div></div>
    <div class="card"><div class="k">FamPay Email</div><div class="v"><code>{fampay_email}</code></div></div>
  </div>

  <div class="section-title">🤖 Bots</div>
  <table>
    <thead><tr><th>Bot</th><th>Owner</th><th>Master</th><th>Users</th><th>Status</th></tr></thead>
    <tbody>{bot_rows}</tbody>
  </table>

  <footer>
    VILLAGEE SMS SHOP v28.1 &nbsp;|&nbsp; <a href="/health">/health</a> &nbsp;|&nbsp; <a href="/status">/status</a>
  </footer>

</div></body></html>"""
    return html, 200


@app.route("/health", methods=["GET"])
def health():
    snap = _bots_snapshot()
    healthy = snap["running"] > 0
    return jsonify({
        "status": "ok" if healthy else "degraded",
        "healthy": healthy,
        "uptime_seconds": round(time.time() - _START_TS, 1),
        "uptime": _uptime_str(time.time() - _START_TS),
        "time_ist": datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p"),
        "bots": {
            "total": snap["total_bots"],
            "running": snap["running"],
            "total_users": snap["total_users"],
        },
        "services": {
            "bot": _flag("bot_status"),
            "server1": _flag("server1_status"),
            "server2": _flag("buy2_status"),
            "server3": _flag("buy3_status"),
            "upi": _flag("upi_status"),
            "fampay": _flag("gmail_verify_enabled"),
        },
    }), (200 if healthy else 503)


@app.route("/status", methods=["GET"])
def status():
    snap = _bots_snapshot()
    return jsonify({
        "store": "VILLAGEE SMS SHOP",
        "version": "28.1",
        "time_ist": datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p"),
        "uptime": _uptime_str(time.time() - _START_TS),
        "uptime_seconds": round(time.time() - _START_TS, 1),
        "bots": snap,
        "payments": {
            "auto_upi": _setting("fampay_upi_id", ""),
            "manual_upi": _setting("manual_upi_id", ""),
            "fampay_email": _setting("gmail_email", ""),
            "fampay_enabled": _flag("gmail_verify_enabled"),
        },
        "flags": {
            "bot": _flag("bot_status"),
            "server1": _flag("server1_status"),
            "server2": _flag("buy2_status"),
            "server3": _flag("buy3_status"),
            "upi": _flag("upi_status"),
        },
    }), 200


@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200


# ============================================================
# PUBLIC ENTRY
# ============================================================
def run_health_server(host=HOST, port=DEFAULT_PORT, debug=False):
    app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)


def start_health_server_thread(host=HOST, port=DEFAULT_PORT):
    t = threading.Thread(
        target=run_health_server,
        kwargs={"host": host, "port": port, "debug": False},
        daemon=True,
        name="health-server",
    )
    t.start()
    return t


if __name__ == "__main__":
    print(f"🌐 Health server → http://{HOST}:{DEFAULT_PORT}/")
    run_health_server()
