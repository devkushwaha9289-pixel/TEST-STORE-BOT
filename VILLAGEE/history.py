#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — history.py
Balance history and per-section purchase history views.
"""

from telegram import InlineKeyboardMarkup

# ============================================================
# BALANCE HISTORY
# ============================================================
def record_balance_history(uid, amount, action, source, note="", old_bal=None, new_bal=None):
    try:
        cur.execute("""INSERT INTO balance_history
            (user_id, amount, action, source, note, old_balance, new_balance)
            VALUES (?,?,?,?,?,?,?)""", (uid, amount, action, source, note, old_bal, new_bal))
        db.commit()
    except Exception as e: log.warning(f"bal_hist: {e}")

async def view_balance_history(update, page=1):
    uid = update.effective_user.id
    limit = 10; offset = (page-1) * limit
    total = cur.execute("SELECT COUNT(*) FROM balance_history WHERE user_id=?", (uid,)).fetchone()[0]
    if total == 0:
        kb = InlineKeyboardMarkup([[ibtn("MAIN MENU","home",emoji="🔙",style="primary")]])
        await send_rich_async(uid, [make_heading("💰 BALANCE HISTORY", 2),
            make_paragraph("📭 No balance history yet.")],
            reply_markup=kb.to_dict(), fallback_text="📭 No history",
            edit_query=_edit_query_of(update)); return
    rows = cur.execute("""SELECT amount, action, source, note, old_balance, new_balance, date
        FROM balance_history WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?""",
        (uid, limit, offset)).fetchall()
    tp = max(1, (total + limit - 1) // limit)
    table = [["💰 AMT","🎯 ACTION","📌 SOURCE","💼 NEW BAL","📅 DATE"]]
    for r in rows:
        try: amt = f"₹{r['amount']}"
        except: amt = "—"
        a = str(r["action"] or "—")[:10]
        s = str(r["source"] or "—")[:16]
        try: nb = f"₹{r['new_balance']}"
        except: nb = "—"
        dt = str(r["date"] or "—")
        if len(dt) > 16: dt = dt[:16]
        table.append([amt, a, s, nb, dt])
    blocks = [make_heading("💰 BALANCE HISTORY", 2),
              make_table([["ℹ️ INFO","📋 VALUE"],["📄 Page", f"{page}/{tp}"],["📦 Total", str(total)]]),
              make_table(table)]
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"bal_hist_{page-1}", emoji="🔙", style="primary"))
    if offset + limit < total: nav.append(ibtn("Next", f"bal_hist_{page+1}", emoji="👉", style="success"))
    kbr = []
    if nav: kbr.append(nav)
    kbr.append([ibtn("MAIN MENU","home",emoji="🔙",style="primary")])
    await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(kbr).to_dict(),
                          fallback_text=f"💰 BALANCE HISTORY {page}/{tp}",
                          edit_query=_edit_query_of(update))

# ============================================================
# SECTION HISTORY
# ============================================================
SECTION_MAP = {
    "panels": {"label":"PANELS","emoji":"📦","section":"PANNELS"},
    "numbers": {"label":"NUMBERS","emoji":"📱","section":"SERVER2"},
    "src": {"label":"SOURCE CODE","emoji":"💻","section":"SOURCE CODE"},
    "osint": {"label":"OSINT APIS","emoji":"🔍","section":"OSINT APIS"},
}

async def view_section_history(update, section_key, page=1):
    uid = update.effective_user.id
    if section_key not in SECTION_MAP:
        try: await update.callback_query.answer("Invalid", show_alert=True)
        except: pass
        return
    meta = SECTION_MAP[section_key]; sec = meta["section"]
    limit = 8; offset = (page-1) * limit
    if sec == "SERVER2":
        total = cur.execute("""SELECT COUNT(*) FROM orders WHERE user_id=? AND
            section IN ('SERVER2','NUMBER','NUMBERS')""", (uid,)).fetchone()[0]
        rows = cur.execute("""SELECT phone, country, price, otp, twofa, date FROM orders
            WHERE user_id=? AND section IN ('SERVER2','NUMBER','NUMBERS')
            ORDER BY id DESC LIMIT ? OFFSET ?""", (uid, limit, offset)).fetchall()
    else:
        total = cur.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND country=?",
                            (uid, sec)).fetchone()[0]
        rows = cur.execute("""SELECT phone, country, price, otp, twofa, date FROM orders
            WHERE user_id=? AND country=? ORDER BY id DESC LIMIT ? OFFSET ?""",
            (uid, sec, limit, offset)).fetchall()
    if total == 0:
        kb = InlineKeyboardMarkup([[ibtn("BACK","sec_hist_menu",emoji="🔙",style="primary")],
                                    [ibtn("MAIN MENU","home",emoji="🏠",style="primary")]])
        await send_rich_async(uid, [make_heading(f"{meta['emoji']} {meta['label']} HISTORY", 2),
            make_paragraph("📭 No history.")], reply_markup=kb.to_dict(),
            fallback_text=f"📭 No {meta['label']} history",
            edit_query=_edit_query_of(update)); return
    tp = max(1, (total + limit - 1) // limit)
    table = [["📱 ITEM","💰 PRICE","🔢 OTP","📅 DATE"]]
    for r in rows:
        item = str(r["phone"] or "—")[:24]
        try: pr = f"₹{float(r['price'] or 0):.0f}"
        except: pr = "—"
        otp = str(r["otp"] or "—")[:10]
        dt = str(r["date"] or "—")
        if len(dt) > 16: dt = dt[:16]
        table.append([item, pr, otp, dt])
    blocks = [make_heading(f"{meta['emoji']} {meta['label']} HISTORY", 2),
              make_table([["ℹ️ INFO","📋 VALUE"],["📄 Page", f"{page}/{tp}"],["📦 Total", str(total)]]),
              make_table(table)]
    nav = []
    if page > 1: nav.append(ibtn("Prev", f"sec_hist|{section_key}|{page-1}", emoji="🔙", style="primary"))
    if offset + limit < total: nav.append(ibtn("Next", f"sec_hist|{section_key}|{page+1}", emoji="👉", style="success"))
    kbr = []
    if nav: kbr.append(nav)
    kbr.append([ibtn("BACK","sec_hist_menu",emoji="🔙",style="primary"),
                ibtn("MAIN MENU","home",emoji="🏠",style="primary")])
    await send_rich_async(uid, blocks, reply_markup=InlineKeyboardMarkup(kbr).to_dict(),
                          fallback_text=f"{meta['label']} HISTORY {page}/{tp}",
                          edit_query=_edit_query_of(update))

async def view_section_history_menu(update):
    uid = update.effective_user.id
    rows = []
    for k, m in SECTION_MAP.items():
        rows.append([ibtn(f"{m['emoji']} {m['label']} HISTORY", f"sec_hist|{k}|1",
                          emoji=m['emoji'], style="primary")])
    rows.append([ibtn("👑 ALL PURCHASES", "purch_hist_1", emoji="👑", style="success")])
    rows.append([ibtn("BACK", "profile", emoji="🔙", style="primary")])
    await send_rich_async(uid, [make_heading("📜 PURCHASE HISTORY", 2),
                                make_paragraph("Select a section:")],
                          reply_markup=InlineKeyboardMarkup(rows).to_dict(),
                          fallback_text="📜 Choose section", edit_query=_edit_query_of(update))


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn
from config import log
from context import cur, db
from rich_ui import _edit_query_of, make_heading, make_paragraph, make_table, send_rich_async
