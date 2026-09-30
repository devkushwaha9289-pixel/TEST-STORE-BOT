#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.2 — fampay.py
SINGLE FILE: FamPay auto-verification (new format, UTR/TXN only)

Verified format (30-Sep-2026 sample):
    Hey Dev Kushwaha,
    You have successfully received
    ₹1.0
    from DEV KUSHWAHA
    Transaction ID : FMPIB6697629157
    Date : 11:09 AM IST, 30 September 2026
    Updated Balance : ₹6.0
    UTR : 735850853755

Official sender ONLY: no-reply@famapp.in
"""

import re
import time
import sqlite3
import asyncio
import imaplib
import email
from datetime import datetime, timedelta
from html import escape
from typing import Any, Dict
from email.header import decode_header
from email.utils import parsedate_to_datetime
from telegram import InlineKeyboardMarkup


# ============================================================
# EMAIL PARSER
# ============================================================
class FamPayEmailParser:
    """Parser for the NEW FamPay email format."""

    @staticmethod
    def _clean(v):
        if not v:
            return v
        return re.sub(r'\s+', ' ', str(v)).strip().rstrip(' .,;:')

    @staticmethod
    def _find(text, patterns):
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                return m.group(1) if m.lastindex else m.group(0)
        return None

    @staticmethod
    def _decode_hdr(v):
        if not v:
            return ""
        out = ""
        for part, cs in decode_header(v):
            if isinstance(part, bytes):
                try:
                    part = part.decode(cs or "utf-8", errors="ignore")
                except Exception:
                    part = part.decode("utf-8", errors="ignore")
            out += part
        return out

    @staticmethod
    def _body(msg):
        plain, html = "", ""
        if msg.is_multipart():
            for p in msg.walk():
                ct = p.get_content_type()
                if "attachment" in str(p.get("Content-Disposition")):
                    continue
                pl = p.get_payload(decode=True)
                if not pl:
                    continue
                try:
                    dec = pl.decode("utf-8", errors="ignore")
                except Exception:
                    dec = ""
                if ct == "text/plain":
                    plain += dec
                elif ct == "text/html":
                    html += dec
        else:
            pl = msg.get_payload(decode=True)
            if pl:
                try:
                    dec = pl.decode("utf-8", errors="ignore")
                except Exception:
                    dec = ""
                if msg.get_content_type() == "text/plain":
                    plain = dec
                elif msg.get_content_type() == "text/html":
                    html = dec
        return plain, html

    @staticmethod
    def _strip_html(h):
        h = re.sub(r"<style[^>]*>.*?</style>", " ", h, flags=re.I | re.S)
        h = re.sub(r"<script[^>]*>.*?</script>", " ", h, flags=re.I | re.S)
        h = re.sub(r"<br\s*/?>", " ", h, flags=re.I)
        h = re.sub(r"</(div|p|tr|td|h[1-6])>", " ", h, flags=re.I)
        h = re.sub(r"&nbsp;", " ", h, flags=re.I)
        h = re.sub(r"&[a-z]+;", " ", h)
        h = re.sub(r"<[^>]+>", " ", h)
        return re.sub(r"\s+", " ", h).strip()

    # --------------------------------------------------------
    def from_raw(self, raw):
        try:
            msg = email.message_from_bytes(raw)
        except Exception:
            return None
        return self.parse(msg)

    def parse(self, msg) -> Dict[str, Any]:
        subject = self._decode_hdr(msg.get("Subject") or "")
        email_from = self._decode_hdr(msg.get("From") or "")
        date_hdr = msg.get("Date") or ""

        plain, html_body = self._body(msg)
        html_clean = self._strip_html(html_body) if html_body else ""
        combined = re.sub(r"\s+", " ", f"{subject} {plain} {html_clean}").strip()
        raw_email = re.sub(r'\s+', ' ', plain if plain else html_clean).strip()

        d: Dict[str, Any] = {
            "amount": None,
            "transaction_id": None,
            "utr": None,
            "order_id": None,        # not present in new format
            "purpose": None,         # not present in new format
            "raw_email": raw_email,
            "received_from": None,
            "received_to": None,
            "receiver_name": None,
            "sender_name": None,
            "payment_status": None,
            "date": None,
            "time": None,
            "subject": subject,
            "balance": None,
            "email_from": email_from,
            "email_date": None,
            "summary": None,
        }

        # email date (IST)
        try:
            d["email_date"] = parsedate_to_datetime(date_hdr).astimezone(IST).strftime(
                "%d %b %Y, %I:%M %p"
            )
        except Exception:
            d["email_date"] = date_hdr

        # amount — prioritize "received ₹X" first to avoid matching balance
        amt = self._find(combined, [
            r'received\s+(?:an\s+amount\s+of\s+)?(?:₹|INR|Rs\.?)?\s*([\d,]+(?:\.\d+)?)',
            r'(?:₹|INR|Rs\.?)\s*([\d,]+(?:\.\d+)?)\s+from\b',
            r'(?:₹|INR|Rs\.?)\s*([\d,]+(?:\.\d+)?)',
        ])
        if amt:
            d["amount"] = amt.replace(",", "").strip().rstrip(".")

        # transaction id
        txn = self._find(combined, [
            r'(?:Transaction|Txn|Payment)\s*(?:ID|Id|No\.?|Number)\s*[:=-]?\s*([A-Za-z0-9]{6,})',
            r'(FMPIB\w+)',
        ])
        if txn:
            d["transaction_id"] = self._clean(txn)

        # UTR (numeric preferred)
        utr = self._find(combined, [
            r'UTR\s*(?:No\.?|Number|ID|Ref(?:erence)?)?\s*[:=-]?\s*(\d{6,})',
            r'UTR\s*(?:No\.?|Number|ID|Ref(?:erence)?)?\s*[:=-]?\s*([A-Za-z0-9]{6,})',
        ])
        if utr:
            d["utr"] = self._clean(utr)

        # sender — "from DEV KUSHWAHA"
        sender = self._find(combined, [
            r'\bfrom\s+([A-Z][A-Za-z0-9\s\.\-&]{2,40}?)'
            r'(?=[\s\.]+(?:Transaction|Txn|UTR|Amount|Date|Updated|Balance|If|Best|₹|INR|Rs)\b|[.,]|$)',
            r'(?:Received\s*from|Sender|Paid\s*by)\s*[:=-]?\s*([A-Z][A-Za-z\s\.\-]{2,40}?)'
            r'(?=[\s\.]+(?:Transaction|Txn|UTR|Amount|Date|Updated|Balance|If|₹|INR|Rs)\b|[.,]|$)',
        ])
        if sender:
            d["received_from"] = d["sender_name"] = self._clean(sender)

        # receiver — greeting "Hey Dev Kushwaha,"
        receiver = self._find(combined, [
            r'(?:Hey|Hi|Hello)\s+([A-Z][A-Za-z\s\.\-]{1,40}?)\s*[,!]',
            r'(?:Received\s*by|Beneficiary|Receiver)\s*[:=-]?\s*([A-Z][A-Za-z\s\.\-]{2,40}?)'
            r'(?=[\s\.]+(?:Transaction|Txn|UTR|Amount|Date|Updated|Balance|₹|INR|Rs)\b|[.,]|$)',
        ])
        if receiver:
            d["received_to"] = d["receiver_name"] = self._clean(receiver)

        # status
        status = self._find(combined, [
            r'(?:Payment\s*Status|Status)\s*[:=-]?\s*([A-Za-z]+)',
        ])
        if status:
            d["payment_status"] = status.upper().strip()
        else:
            lower = combined.lower()
            if any(w in lower for w in
                   ("successfully received", "success", "received",
                    "credited", "completed")):
                d["payment_status"] = "SUCCESS"
            elif "failed" in lower:
                d["payment_status"] = "FAILED"
            elif "pending" in lower:
                d["payment_status"] = "PENDING"

        # balance
        bal = self._find(combined, [
            r'(?:Updated|Available|Current|Wallet)?\s*Balance\s*[:=-]?\s*'
            r'(?:is\s*)?(?:₹|INR|Rs\.?)?\s*([\d,]+(?:\.\d+)?)',
        ])
        if bal:
            d["balance"] = bal.replace(",", "").strip().rstrip(".")

        # date / time
        mon = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*'
        tpat = r'\d{1,2}:\d{2}\s*(?:AM|PM)'
        dpat = rf'\d{{1,2}}\s+{mon}\s*,?\s*\d{{4}}'
        date_s = time_s = None
        m = re.search(rf'({tpat})\s*(?:IST|UTC)?[,\s]*({dpat})', combined, re.I)
        if m:
            time_s, date_s = m.group(1), m.group(2)
        else:
            m = re.search(rf'({dpat})[,\s]*({tpat})', combined, re.I)
            if m:
                date_s, time_s = m.group(1), m.group(2)
            else:
                tm = re.search(tpat, combined, re.I)
                dm = re.search(dpat, combined, re.I)
                time_s = tm.group(0) if tm else None
                date_s = dm.group(0) if dm else None
        if date_s:
            ds = re.sub(r"\s*,\s*", " ", date_s).strip()
            ds = re.sub(r"\s+", " ", ds)
            for fmt in ("%d %b %Y", "%d %B %Y"):
                try:
                    ds = datetime.strptime(ds, fmt).strftime("%d %b %Y")
                    break
                except Exception:
                    continue
            d["date"] = ds
        if time_s:
            d["time"] = re.sub(r"\s+", " ", time_s.strip().upper())
        if not d["date"] or not d["time"]:
            try:
                dt = parsedate_to_datetime(date_hdr)
                d["date"] = d["date"] or dt.strftime("%d %b %Y")
                d["time"] = d["time"] or dt.strftime("%I:%M %p")
            except Exception:
                pass

        # summary
        sm = f"{d['receiver_name']}, you received" if d.get("receiver_name") else "You received"
        sm += f" ₹{d['amount']}" if d.get("amount") else " a payment"
        if d.get("sender_name"):
            sm += f" from {d['sender_name']}"
        if d.get("date") and d.get("time"):
            sm += f" on {d['date']} at {d['time']}"
        sm += "."
        if d.get("transaction_id"):
            sm += f" Txn {d['transaction_id']}."
        if d.get("utr"):
            sm += f" UTR {d['utr']}."
        if d.get("balance"):
            sm += f" Balance ₹{d['balance']}."
        d["summary"] = sm

        for k in list(d.keys()):
            if isinstance(d[k], str):
                d[k] = self._clean(d[k])
        return d

    def summarize(self, details) -> str:
        details = details or {}
        out = "📧 <b>New Payment Email</b>\n\n"
        out += f"<b>Subject:</b> {escape(str(details.get('subject') or ''))}\n"
        if details.get("date") and details.get("time"):
            out += (f"<b>Date:</b> {escape(str(details['date']))} "
                    f"{escape(str(details['time']))}\n")
        fields = [
            ("Amount", "amount", "₹"),
            ("Transaction ID", "transaction_id", ""),
            ("UTR", "utr", ""),
            ("Sender", "sender_name", ""),
            ("Receiver", "receiver_name", ""),
            ("Status", "payment_status", ""),
            ("Balance", "balance", "₹"),
        ]
        has = False
        for label, key, prefix in fields:
            val = details.get(key)
            if val:
                if not has:
                    out += "\n<b>🔍 Details:</b>\n"
                    has = True
                out += f"  {label}: {prefix}{escape(str(val))}\n"
        if not has:
            out += "\nNo detailed information extracted."
        out += f"\n<b>📄 Summary:</b>\n{escape(str(details.get('summary') or ''))}"
        return out


# ============================================================
# IMAP FETCH — only official sender (no-reply@famapp.in)
# ============================================================
def _imap_fetch_fampay_emails_blocking(ea, ap):
    """
    Search ONLY emails from the official FamPay sender (no-reply@famapp.in).
    Uses SINCE (last 3 days) so manually-read emails are still picked up.
    Dedup happens later via `gmail_processed` table.
    """
    conn = None
    out = []
    try:
        conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        conn.login(ea, ap)
        conn.select("INBOX")

        since = (datetime.utcnow() - timedelta(days=3)).strftime("%d-%b-%Y")

        # ✅ EXACT sender match — official FamPay only
        result, data = conn.search(
            None, f'(SINCE "{since}" FROM "{FAMPAY_SENDER}")'
        )
        if result != "OK":
            log.warning(f"IMAP search failed: {result}")
            return out

        ids = data[0].split()
        ids = ids[-100:] if len(ids) > 100 else ids  # safety cap

        for mid in ids:
            try:
                r2, md = conn.fetch(mid, "(RFC822)")
                if r2 != "OK" or not md or not md[0]:
                    continue
                out.append((mid.decode(), md[0][1]))
            except Exception:
                continue
    except Exception as e:
        log.warning(f"IMAP fetch error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            try:
                conn.logout()
            except Exception:
                pass
    return out


# ============================================================
# MATCHING — amount (email has no order_id)
# ============================================================
def _find_matching_pending_order(amount, oid_email, utr):
    """
    New FamPay emails do NOT carry merchant `order_id`.
    Match order by:
      1) exact order_id (legacy)
      2) amount within last 15 minutes
      3) amount (most recent)
    Real verification still relies on UTR / TXN uniqueness.
    """
    if oid_email:
        for cand in (oid_email, oid_email.strip(),
                     oid_email.strip().upper(), oid_email.strip().lower()):
            row = cur.execute(
                """SELECT order_id, user_id, amount FROM upi_orders
                   WHERE status='pending' AND UPPER(order_id)=UPPER(?)""",
                (cand,)
            ).fetchone()
            if row:
                return row
    if amount is not None:
        rows = cur.execute(
            """SELECT order_id, user_id, amount FROM upi_orders
               WHERE status='pending' AND ABS(amount - ?) < 0.01
                 AND created_ts > ?
               ORDER BY created_ts DESC LIMIT 5""",
            (float(amount), time.time() - 900)
        ).fetchall()
        if rows:
            return rows[0]
        rows = cur.execute(
            """SELECT order_id, user_id, amount FROM upi_orders
               WHERE status='pending' AND ABS(amount - ?) < 0.01
               ORDER BY created_ts DESC LIMIT 1""",
            (float(amount),)
        ).fetchall()
        if rows:
            return rows[0]
    return None


# ============================================================
# ALERTS
# ============================================================
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
    kb = InlineKeyboardMarkup([
        [ibtn("CONTACT OWNER", url=get_support_url(), emoji="📞", style="success")],
        [ibtn("HOME", "home", emoji="🏠", style="primary")]])
    try:
        await _tg_post("sendMessage", {"chat_id": uid, "text": msg,
            "parse_mode": "HTML", "reply_markup": kb.to_dict()})
    except Exception:
        pass


async def _send_double_payment_alert(uid, oid, utr, txn, existing):
    msg = (f"<b>{emo('🚫')} DUPLICATE PAYMENT BLOCKED</b>\n\n"
           f"{emo('🆔')} <b>Your Order:</b> <code>{oid}</code>\n"
           f"{emo('🔢')} <b>UTR:</b> <code>{utr or '—'}</code>\n"
           f"{emo('🆔')} <b>TXN:</b> <code>{txn or '—'}</code>\n"
           f"⚠️ Already used in <code>{existing}</code>.\n\n"
           f"{emo('📞')} {get_contact_1()}")
    kb = InlineKeyboardMarkup([
        [ibtn("CONTACT", url=get_support_url(), emoji="📞", style="success")],
        [ibtn("HOME", "home", emoji="🏠", style="primary")]])
    try:
        await _tg_post("sendMessage", {"chat_id": uid, "text": msg,
            "parse_mode": "HTML", "reply_markup": kb.to_dict()})
    except Exception:
        pass


# ============================================================
# EMAIL PROCESSING — strict sender guard
# ============================================================
async def _process_fampay_email(mid, raw, parsed):
    if cur.execute("SELECT 1 FROM gmail_processed WHERE msg_id=?", (mid,)).fetchone():
        return
    cur.execute(
        "INSERT OR IGNORE INTO gmail_processed (msg_id, processed_ts) VALUES (?, ?)",
        (mid, time.time())
    )
    db.commit()
    if not parsed:
        return

    # ✅ STRICT sender guard — only official FamPay
    email_from = (parsed.get("email_from") or "").lower()
    if FAMPAY_SENDER.lower() not in email_from:
        log.info(f"⏭ Skipping non-official sender: {email_from}")
        return

    try:
        amount_f = float(parsed.get("amount")) if parsed.get("amount") else None
    except Exception:
        amount_f = None
    utr = parsed.get("utr")
    txn = parsed.get("transaction_id")

    # store parsed email (for RECENT tab + audit)
    try:
        cur.execute(
            """INSERT OR IGNORE INTO fampay_emails
               (msg_id, amount, utr, txn_id, order_id, sender_name, receiver_name,
                purpose, raw_summary, received_ts)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (mid, amount_f, utr, txn, parsed.get("order_id"),
             parsed.get("sender_name") or parsed.get("received_from"),
             parsed.get("receiver_name") or parsed.get("received_to"),
             parsed.get("purpose"), parsed.get("summary"), time.time())
        )
        db.commit()
    except sqlite3.IntegrityError:
        return
    except Exception:
        pass

    if amount_f is None:
        return

    # dedup / fraud check
    existing = None
    if utr:
        existing = is_utr_used_by_other_order(utr)
    if not existing and txn:
        existing = is_txn_used_by_other_order(txn)

    match = _find_matching_pending_order(amount_f, parsed.get("order_id"), utr)
    if not match:
        return
    oid = match["order_id"]
    uid = match["user_id"]
    exp = float(match["amount"])

    if existing and existing != oid:
        cur.execute(
            """UPDATE upi_orders
               SET status='duplicate', utr=?, txn_id=?, paid_amount=?,
                   verified_via='fampay_duplicate_blocked'
               WHERE order_id=?""",
            (utr, txn, amount_f, oid)
        )
        db.commit()
        await _send_double_payment_alert(uid, oid, utr, txn, existing)
        return

    if abs(exp - amount_f) > 0.01:
        cur.execute(
            """UPDATE upi_orders
               SET status='mismatch', paid_amount=?, utr=?, txn_id=?,
                   verified_via='fampay_imap_mismatch'
               WHERE order_id=?""",
            (amount_f, utr, txn, oid)
        )
        db.commit()
        try:
            cur.execute("UPDATE fampay_emails SET matched_order_id=? WHERE msg_id=?",
                        (oid, mid))
            db.commit()
        except Exception:
            pass
        await _send_mismatch_alert(uid, oid, exp, amount_f, utr, txn, "fampay_auto")
        return

    try:
        cur.execute(
            """UPDATE upi_orders
               SET utr=?, txn_id=?, verified_via='fampay_imap', paid_amount=?
               WHERE order_id=?""",
            (utr, txn, amount_f, oid)
        )
        cur.execute("UPDATE fampay_emails SET matched_order_id=? WHERE msg_id=?",
                    (oid, mid))
        db.commit()
    except Exception:
        pass

    await complete_upi_order(oid, uid, int(exp), None, "fampay_imap", utr=utr, txn=txn)


# ============================================================
# IMAP POLL LOOP
# ============================================================
async def fampay_imap_poll_loop():
    log.info(f"📧 FamPay poll @{current_bot_username()}")
    await asyncio.sleep(5)
    while True:
        try:
            if not is_gmail_verify_enabled():
                await asyncio.sleep(IMAP_POLL_INTERVAL)
                continue
            ea = get_setting('gmail_email', '').strip()
            ap = get_setting('gmail_app_password', '').strip()
            if not ea or not ap:
                await asyncio.sleep(IMAP_POLL_INTERVAL)
                continue
            emails = await asyncio.to_thread(_imap_fetch_fampay_emails_blocking, ea, ap)
            if emails:
                parser = FamPayEmailParser()
                processed = 0
                for mid, raw in emails:
                    try:
                        parsed = parser.from_raw(raw)
                        await _process_fampay_email(mid, raw, parsed)
                        processed += 1
                    except Exception as e:
                        log.warning(f"FamPay parse error mid={mid}: {e}")
                if processed:
                    log.info(f"📬 FamPay: checked {processed} email(s)")
        except Exception as e:
            log.warning(f"FamPay poll error: {e}")
        await asyncio.sleep(IMAP_POLL_INTERVAL)


# ============================================================
# CROSS-MODULE IMPORTS (project glue — required)
# ============================================================
from buttons import ibtn
from config import (
    FAMPAY_SENDER, IMAP_POLL_INTERVAL, IMAP_PORT, IMAP_SERVER, IST, log
)
from context import cur, current_bot_username, db
from database import (
    get_contact_1, get_setting, get_support_url, is_gmail_verify_enabled,
    is_txn_used_by_other_order, is_utr_used_by_other_order
)
from emojis import emo
from payments import complete_upi_order
from rich_ui import _tg_post
