#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — fampay.py
FamPay email parser + Gmail IMAP polling for automatic UPI deposits.
"""

import re, time, sqlite3, asyncio, imaplib, email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from telegram import InlineKeyboardMarkup

# ============================================================
# FAMPAY
# ============================================================
class FamPayEmailParser:
    @staticmethod
    def _clean_value(v):
        if not v: return v
        return re.sub(r'\s+', ' ', str(v)).strip().rstrip(' .,;:')
    @staticmethod
    def _extract(text, patterns):
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m: return m.group(1) if m.lastindex else m.group(0)
        return None
    @staticmethod
    def _decode_header_value(v):
        if not v: return ""
        out = ""
        for part, cs in decode_header(v):
            if isinstance(part, bytes):
                try: part = part.decode(cs or "utf-8", errors="ignore")
                except: part = part.decode("utf-8", errors="ignore")
            out += part
        return out
    @staticmethod
    def _get_body_text(msg):
        plain, html = "", ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if "attachment" in str(part.get("Content-Disposition")): continue
                pl = part.get_payload(decode=True)
                if not pl: continue
                try: dec = pl.decode("utf-8", errors="ignore")
                except: dec = ""
                if ct == "text/plain": plain += dec
                elif ct == "text/html": html += dec
        else:
            pl = msg.get_payload(decode=True)
            if pl:
                try: dec = pl.decode("utf-8", errors="ignore")
                except: dec = ""
                ct = msg.get_content_type()
                if ct == "text/plain": plain = dec
                elif ct == "text/html": html = dec
        return plain, html
    @staticmethod
    def _clean_html(h):
        return re.sub(r"\s+", " ", re.sub(r"&[a-z]+;", " ", re.sub(r"<[^>]+>", " ", h))).strip()
    def extract_details_from_raw(self, raw):
        try: msg = email.message_from_bytes(raw)
        except: return None
        return self.extract_details(msg)
    def extract_details(self, msg):
        subject = self._decode_header_value(msg.get("Subject","") or "")
        email_from = msg.get("From","") or ""; edh = msg.get("Date","") or ""
        plain, html = self._get_body_text(msg)
        bc = self._clean_html(html) if html else ""
        combined = re.sub(r'\s+', ' ', f"{subject} {plain} {bc}").strip()
        raw_email = re.sub(r'\s+', ' ', plain if plain else bc).strip()
        details = {"amount":None,"transaction_id":None,"utr":None,"order_id":None,
                   "received_from":None,"received_to":None,"receiver_name":None,
                   "sender_name":None,"purpose":None,"payment_status":None,
                   "date":None,"time":None,"subject":subject,"balance":None,
                   "email_from":email_from,"email_date":None,"summary":None,"raw_email":raw_email}
        try:
            dt = parsedate_to_datetime(edh); details["email_date"] = dt.strftime("%d %b %Y, %I:%M %p")
        except: details["email_date"] = edh
        amt = self._extract(combined, [r'(?:₹|INR|Rs\.?)\s*([\d,]+\.?\d*)',
            r'([\d,]+\.?\d*)\s*(?:₹|INR|Rs\.?)',
            r'amount\s*[:=-]?\s*(?:₹|INR|Rs\.?)?\s*([\d,]+\.?\d*)'])
        if amt: details["amount"] = amt.replace(',', '').strip()
        txn = self._extract(combined, [r'Transaction\s*ID\s*[:=-]?\s*(\S+)', r'Transaction\s*Id\s*[:=-]?\s*(\S+)',
            r'Txn\s*ID\s*[:=-]?\s*(\S+)', r'Txn\s*Id\s*[:=-]?\s*(\S+)', r'Payment\s*ID\s*[:=-]?\s*(\S+)',
            r'Payment\s*Id\s*[:=-]?\s*(\S+)', r'(FMPIB\d+)'])
        if txn: details["transaction_id"] = self._clean_value(txn)
        utr = self._extract(combined, [r'UTR\s*[:=-]?\s*(\S+)', r'UTR\s*No\s*[:=-]?\s*(\S+)',
            r'UTR\s*Number\s*[:=-]?\s*(\S+)', r'UTR\s*ID\s*[:=-]?\s*(\S+)', r'UTR\s*Ref\s*[:=-]?\s*(\S+)'])
        if utr: details["utr"] = self._clean_value(utr)
        order = self._extract(combined, [r'(VILLAGEEsms[A-Za-z0-9]+)', r'Order\s*ID\s*[:=-]?\s*(\S+)',
            r'Order\s*Id\s*[:=-]?\s*(\S+)', r'Order-?Id\s*[:=-]?\s*(\S+)',
            r'Order\s*#?\s*[:=-]?\s*(\S+)', r'Order\s*Number\s*[:=-]?\s*(\S+)', r'(UPI\d{10,})'])
        if order: details["order_id"] = self._clean_value(order)
        sender = self._extract(combined, [
            r'from\s+([A-Z][A-Za-z\s]+?)(?=\s+(?:Transaction|UTR|Amount|₹|INR|Rs|$|Date|Updated|Purpose|If|for|at|on|,))',
            r'(?:Received\s*from|Sender|Paid\s*by)\s*[:=-]?\s*([A-Z][A-Za-z\s]+?)(?=\s+(?:Transaction|UTR|Amount|₹|INR|Rs|$|Date|Updated|Purpose|If))'])
        if sender:
            s = self._clean_value(sender); details["received_from"] = s; details["sender_name"] = s
        receiver = self._extract(combined, [r'(?:Hey|Hi|Hello)\s+([A-Z][A-Za-z\s]+?),',
            r'(?:Received\s*by|To|Beneficiary|Receiver)\s*[:=-]?\s*([A-Z][A-Za-z\s]+?)(?=\s+(?:Transaction|UTR|Amount|₹|INR|Rs|$|Date|Updated|Purpose|If))'])
        if receiver:
            r = self._clean_value(receiver); details["received_to"] = r; details["receiver_name"] = r
        purpose = self._extract(combined, [r'Purpose\s*[:=-]?\s*(.+?)(?=\s+If|$|\.\s+If)',
            r'Remarks\s*[:=-]?\s*(.+?)(?=\s+If|$|\.\s+If)',
            r'Message\s*[:=-]?\s*(.+?)(?=\s+If|$|\.\s+If)',
            r'Description\s*[:=-]?\s*(.+?)(?=\s+If|$|\.\s+If)'])
        if purpose:
            details["purpose"] = self._clean_value(purpose)
            om = re.search(r'(VILLAGEEsms[A-Za-z0-9]+)', purpose, re.IGNORECASE)
            if om and not details["order_id"]: details["order_id"] = self._clean_value(om.group(1))
        status = self._extract(combined, [r'(?:Status|Payment\s*Status)\s*[:=-]?\s*(\w+)'])
        if status: details["payment_status"] = status.upper().strip()
        else:
            l = combined.lower()
            if any(w in l for w in ['success','received','credited','completed']): details["payment_status"] = "SUCCESS"
            elif 'failed' in l: details["payment_status"] = "FAILED"
            elif 'pending' in l: details["payment_status"] = "PENDING"
        bal = self._extract(combined, [r'(?:Updated\s*)?Balance\s*[:=-]?\s*(?:₹|INR|Rs\.?)?\s*([\d,]+\.?\d*)',
            r'(?:Available|Current)\s*Balance\s*[:=-]?\s*(?:₹|INR|Rs\.?)?\s*([\d,]+\.?\d*)',
            r'Wallet\s*Balance\s*[:=-]?\s*(?:₹|INR|Rs\.?)?\s*([\d,]+\.?\d*)'])
        if bal: details["balance"] = bal.replace(',', '').strip()
        for pat in [
            r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))\s*(?:IST|UTC)?[,\s]*(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{4})',
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{4})[,\s]*(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))']:
            m = re.search(pat, combined, re.IGNORECASE)
            if m:
                try:
                    t, d = m.groups(); details["date"] = d.strip(); details["time"] = t.strip().upper()
                except: pass
                break
        if not details["date"] or not details["time"]:
            try:
                dt = parsedate_to_datetime(edh)
                if not details["date"]: details["date"] = dt.strftime("%d %b %Y")
                if not details["time"]: details["time"] = dt.strftime("%I:%M %p")
            except: pass
        parts = []
        if details.get("receiver_name"): parts.append(f"{details['receiver_name']}, you received")
        elif details.get("amount"): parts.append(f"You received ₹{details['amount']}")
        else: parts.append("You received a payment")
        if details.get("sender_name"): parts.append(f"from {details['sender_name']}")
        if details.get("date") and details.get("time"): parts.append(f"on {details['date']} at {details['time']}")
        if details.get("transaction_id"): parts.append(f"Txn {details['transaction_id']}")
        if details.get("utr"): parts.append(f"UTR {details['utr']}")
        if details.get("balance"): parts.append(f"Balance ₹{details['balance']}")
        if details.get("purpose"): parts.append(f"Purpose: {details['purpose']}")
        details["summary"] = ". ".join(parts) + "."
        for k in details:
            if isinstance(details[k], str): details[k] = self._clean_value(details[k])
        return details

def _imap_fetch_fampay_emails_blocking(ea, ap):
    conn = None; out = []
    try:
        conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        conn.login(ea, ap); conn.select("INBOX")
        result, data = conn.search(None, f'(FROM "{FAMPAY_SENDER}" UNSEEN)')
        if result != "OK": return out
        for mid in data[0].split():
            try:
                r2, md = conn.fetch(mid, "(RFC822)")
                if r2 != "OK" or not md or not md[0]: continue
                out.append((mid.decode(), md[0][1]))
                conn.store(mid, "+FLAGS", "\\Seen")
            except: continue
    except: pass
    finally:
        if conn:
            try: conn.close()
            except: pass
            try: conn.logout()
            except: pass
    return out

def _find_matching_pending_order(amount, oid_email, utr):
    if oid_email:
        for cand in [oid_email, oid_email.strip(), oid_email.strip().upper(), oid_email.strip().lower()]:
            row = cur.execute("""SELECT order_id, user_id, amount FROM upi_orders
                WHERE status='pending' AND UPPER(order_id)=UPPER(?)""", (cand,)).fetchone()
            if row: return row
    if amount is not None:
        rows = cur.execute("""SELECT order_id, user_id, amount FROM upi_orders
            WHERE status='pending' AND ABS(amount - ?) < 0.01 AND created_ts > ?
            ORDER BY created_ts DESC LIMIT 5""", (float(amount), time.time() - 900)).fetchall()
        if rows: return rows[0]
        rows = cur.execute("""SELECT order_id, user_id, amount FROM upi_orders
            WHERE status='pending' AND ABS(amount - ?) < 0.01
            ORDER BY created_ts DESC LIMIT 1""", (float(amount),)).fetchall()
        if rows: return rows[0]
    return None

async def _send_mismatch_alert(uid, oid, exp, paid, utr=None, txn=None, src="auto"):
    ul = f"{emo('🔢')} <b>UTR:</b> <code>{utr or '—'}</code>\n" if utr else ""
    tl = f"{emo('🆔')} <b>TXN:</b> <code>{txn or '—'}</code>\n" if txn else ""
    diff = round((paid or 0) - (exp or 0), 2)
    ds = f"+₹{diff}" if diff > 0 else f"₹{diff}"
    msg = (f"<b>{emo('⚠️')} PAYMENT REJECTED — MISMATCH</b>\n\n"
           f"{emo('🆔')} <b>Order:</b> <code>{oid}</code>\n"
           f"{emo('💰')} <b>Expected:</b> ₹{int(exp)}\n{emo('💵')} <b>Paid:</b> ₹{paid}\n"
           f"{emo('📉')} <b>Diff:</b> {ds}\n{ul}{tl}{emo('📍')} <b>Source:</b> {src}\n\n"
           f"<b>{emo('🚫')} NOT credited</b>\n\n"
           f"<b>{emo('👉')} Contact:</b> {get_contact_1()}")
    kb = InlineKeyboardMarkup([[ibtn("CONTACT OWNER", url=get_support_url(), emoji="📞", style="success")],
                                [ibtn("HOME","home",emoji="🏠",style="primary")]])
    try: await _tg_post("sendMessage", {"chat_id": uid, "text": msg, "parse_mode": "HTML",
        "reply_markup": kb.to_dict()})
    except: pass

async def _send_double_payment_alert(uid, oid, utr, txn, existing):
    msg = (f"<b>{emo('🚫')} DUPLICATE PAYMENT BLOCKED</b>\n\n"
           f"{emo('🆔')} <b>Your Order:</b> <code>{oid}</code>\n"
           f"{emo('🔢')} <b>UTR:</b> <code>{utr or '—'}</code>\n"
           f"{emo('🆔')} <b>TXN:</b> <code>{txn or '—'}</code>\n"
           f"⚠️ Already used in <code>{existing}</code>.\n\n"
           f"{emo('📞')} {get_contact_1()}")
    kb = InlineKeyboardMarkup([[ibtn("CONTACT", url=get_support_url(), emoji="📞", style="success")],
                                [ibtn("HOME","home",emoji="🏠",style="primary")]])
    try: await _tg_post("sendMessage", {"chat_id": uid, "text": msg, "parse_mode": "HTML",
        "reply_markup": kb.to_dict()})
    except: pass

async def _process_fampay_email(mid, raw, parsed):
    if cur.execute("SELECT 1 FROM gmail_processed WHERE msg_id=?", (mid,)).fetchone(): return
    cur.execute("INSERT OR IGNORE INTO gmail_processed (msg_id, processed_ts) VALUES (?, ?)",
                (mid, time.time())); db.commit()
    if not parsed: return
    try: amount_f = float(parsed.get("amount")) if parsed.get("amount") else None
    except: amount_f = None
    utr = parsed.get("utr"); txn = parsed.get("transaction_id")
    try:
        cur.execute("""INSERT OR IGNORE INTO fampay_emails
            (msg_id, amount, utr, txn_id, order_id, sender_name, receiver_name, purpose,
             raw_summary, received_ts) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (mid, amount_f, utr, txn, parsed.get("order_id"),
             parsed.get("sender_name") or parsed.get("received_from"),
             parsed.get("receiver_name") or parsed.get("received_to"),
             parsed.get("purpose"), parsed.get("summary"), time.time()))
        db.commit()
    except sqlite3.IntegrityError: return
    except: pass
    if amount_f is None: return
    existing = None
    if utr: existing = is_utr_used_by_other_order(utr)
    if not existing and txn: existing = is_txn_used_by_other_order(txn)
    match = _find_matching_pending_order(amount_f, parsed.get("order_id"), utr)
    if not match: return
    oid = match["order_id"]; uid = match["user_id"]; exp = float(match["amount"])
    if existing and existing != oid:
        cur.execute("""UPDATE upi_orders SET status='duplicate', utr=?, txn_id=?, paid_amount=?,
            verified_via='fampay_duplicate_blocked' WHERE order_id=?""", (utr, txn, amount_f, oid)); db.commit()
        await _send_double_payment_alert(uid, oid, utr, txn, existing); return
    if abs(exp - amount_f) > 0.01:
        cur.execute("""UPDATE upi_orders SET status='mismatch', paid_amount=?, utr=?, txn_id=?,
            verified_via='fampay_imap_mismatch' WHERE order_id=?""", (amount_f, utr, txn, oid)); db.commit()
        try:
            cur.execute("UPDATE fampay_emails SET matched_order_id=? WHERE msg_id=?", (oid, mid)); db.commit()
        except: pass
        await _send_mismatch_alert(uid, oid, exp, amount_f, utr, txn, "fampay_auto"); return
    try:
        cur.execute("""UPDATE upi_orders SET utr=?, txn_id=?, verified_via='fampay_imap',
            paid_amount=? WHERE order_id=?""", (utr, txn, amount_f, oid))
        cur.execute("UPDATE fampay_emails SET matched_order_id=? WHERE msg_id=?", (oid, mid)); db.commit()
    except: pass
    await complete_upi_order(oid, uid, int(exp), None, "fampay_imap", utr=utr, txn=txn)

async def fampay_imap_poll_loop():
    log.info(f"📧 FamPay poll @{current_bot_username()}")
    await asyncio.sleep(5)
    while True:
        try:
            if not is_gmail_verify_enabled():
                await asyncio.sleep(IMAP_POLL_INTERVAL); continue
            ea = get_setting('gmail_email','').strip()
            ap = get_setting('gmail_app_password','').strip()
            if not ea or not ap:
                await asyncio.sleep(IMAP_POLL_INTERVAL); continue
            emails = await asyncio.to_thread(_imap_fetch_fampay_emails_blocking, ea, ap)
            if emails:
                log.info(f"📬 FamPay: {len(emails)} new")
                parser = FamPayEmailParser()
                for mid, raw in emails:
                    try: await _process_fampay_email(mid, raw, parser.extract_details_from_raw(raw))
                    except: pass
        except: pass
        await asyncio.sleep(IMAP_POLL_INTERVAL)


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from buttons import ibtn
from config import FAMPAY_SENDER, IMAP_POLL_INTERVAL, IMAP_PORT, IMAP_SERVER, log
from context import cur, current_bot_username, db
from database import (
    get_contact_1, get_setting, get_support_url, is_gmail_verify_enabled,
    is_txn_used_by_other_order, is_utr_used_by_other_order
)
from emojis import emo
from payments import complete_upi_order
from rich_ui import _tg_post
