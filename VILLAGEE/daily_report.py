#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_report.py — automatic daily statement (every day 7:00 PM IST).

Every running bot sends its own statement (total selling + total deposit of the day)
to its owner and to the master owner. Runs inside each bot context.
"""
import asyncio
import html
from datetime import timedelta, timezone

import requests

from config import IST, log, now_ist

REPORT_HOUR = 19      # 7 PM IST
REPORT_MINUTE = 0


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def build_statement(ctx):
    """Return (text, totals) for 'today so far' (IST day) for one bot context."""
    now = now_ist()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    su, eu = _utc(start), _utc(now + timedelta(minutes=1))
    cur = ctx.cur

    def one(sql, args=()):
        try:
            r = cur.execute(sql, args).fetchone()
            return (r[0] or 0, r[1] or 0)
        except Exception as e:
            log.warning(f"statement query failed @{ctx.username}: {e}")
            return (0, 0)

    sell_n, sell_amt = one(
        "SELECT COUNT(*), COALESCE(SUM(price),0) FROM orders WHERE date >= ? AND date < ?", (su, eu))
    up_n, up_amt = one(
        """SELECT COUNT(*), COALESCE(SUM(COALESCE(paid_amount, amount)),0) FROM upi_orders
           WHERE status='success' AND date >= ? AND date < ?""", (su, eu))
    dp_n, dp_amt = one(
        """SELECT COUNT(*), COALESCE(SUM(amount),0) FROM deposits
           WHERE status='approved' AND date >= ? AND date < ?""", (su, eu))

    dep_n = int(up_n) + int(dp_n)
    dep_amt = float(up_amt) + float(dp_amt)
    text = (
        f"📊 <b>DAILY STATEMENT</b>\n"
        f"🤖 Bot: @{html.escape(str(ctx.username))}\n"
        f"📅 {now.strftime('%d-%m-%Y')} • {now.strftime('%I:%M %p')} IST\n"
        f"━━━━━━━━━━━━━━\n"
        f"🛒 <b>Total Selling:</b> ₹{float(sell_amt):.0f}  ({int(sell_n)} orders)\n"
        f"💰 <b>Total Deposit:</b> ₹{dep_amt:.0f}  ({dep_n} deposits)\n"
        f"━━━━━━━━━━━━━━"
    )
    return text, {"sell": float(sell_amt), "dep": dep_amt}


def _send(token, chat_id, text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=20)
        return bool(r.json().get("ok"))
    except Exception as e:
        log.warning(f"statement send {chat_id}: {e}")
        return False


def _get(ctx, key, default=""):
    try:
        r = ctx.cur.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else default
    except Exception:
        return default


def _set(ctx, key, value):
    try:
        ctx.cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        ctx.db.commit()
    except Exception as e:
        log.warning(f"statement setting save: {e}")


async def send_statement_now(ctx):
    from context import MASTER_OWNER_ID
    text, _ = build_statement(ctx)
    recipients = {int(ctx.owner_id), int(MASTER_OWNER_ID)}
    ok = 0
    for rid in recipients:
        if await asyncio.to_thread(_send, ctx.token, rid, text):
            ok += 1
    return ok


async def daily_statement_loop(ctx):
    """Check every 30s; fire once per day after 7:00 PM IST (also catches up if the bot was restarted)."""
    await asyncio.sleep(15)
    while True:
        try:
            now = now_ist()
            today = now.strftime("%Y-%m-%d")
            due = (now.hour, now.minute) >= (REPORT_HOUR, REPORT_MINUTE)
            if due and _get(ctx, "daily_statement_last") != today:
                _set(ctx, "daily_statement_last", today)   # mark first -> never double-send
                n = await send_statement_now(ctx)
                log.info(f"📊 Daily statement @{ctx.username} sent to {n} owner(s)")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning(f"daily statement loop @{getattr(ctx, 'username', '?')}: {e}")
        await asyncio.sleep(30)
