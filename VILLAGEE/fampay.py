#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.4 — fampay.py
============================================================
FamPay Auto-Verification — ALL IMAP ISSUES FIXED
============================================================

Fixes:
✅ App Password space strip (16-char)
✅ IMAP timeout (15s) — no hang
✅ SINCE 3 days (survives manual read)
✅ Only official sender (no-reply@famapp.in)
✅ Plain + HTML body merge
✅ Multi-charset decode
✅ Amount + UTR + TXN + Balance extraction
✅ Every failure → Owner DM + Log channel
✅ IMAP login failure → Owner alert once per hour
✅ Detailed error logging
"""

import re
import time
import sqlite3
import asyncio
import imaplib
import email
import traceback
from datetime import datetime, timedelta
from html import escape
from typing import Any, Dict, Optional
from email.header import decode_header
from email.utils import parsedate_to_datetime
from telegram import InlineKeyboardMarkup


# ============================================================
# RATE LIMIT — imap failure alert (1 per hour)
# ============================================================
_last_imap_alert_ts = 0.0
_IMAP_ALERT_COOLDOWN = 3600  # 1 hour


# ============================================================
# PARSER
# ============================================================
class FamPayEmailParser:
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
        try:
            for part, cs in decode_header(v):
                if isinstance(part, bytes):
                    for enc in (cs, "utf-8", "latin-1", "cp1252"):
                        if not enc:
                            continue
                        try:
                            part = part.decode(enc, errors="ignore")
                            break
                        except Exception:
                            continue
                out += str(part)
        except Exception:
            out = str(v)
        return out

    @staticmethod
    def _get_body(msg):
        """Merge text/plain and text/html (decoded with fallback charsets)."""
        plain, html = "", ""
        parts = msg.walk() if msg.is_multipart() else [msg]
        for p in parts:
            try:
                if "attachment" in str(p.get("Content-Disposition") or ""):
                    continue
                ct = p.get_content_type()
                if ct not in ("text/plain", "text/html"):
                    continue
                pl = p.get_payload(decode=True)
                if not pl:
                    continue
                # Try multiple charsets
                text = ""
                for enc in (p.get_content_charset(), "utf-8", "latin-1", "cp1252"):
                    if not enc:
                        continue
                    try:
                        text = pl.decode(enc, errors="ignore")
                        break
                    except Exception:
                        continue
                if ct == "text/plain":
                    plain += text + " "
                else:
                    html += text + " "
            except Exception:
                continue
        return plain, html

    @staticmethod
    def _strip_html(h):
        h = re.sub(r"<style[^>]*>.*?</style>", " ", h, flags=re.I | re.S)
        h = re.sub(r"<script[^>]*>.*?</script>", " ", h, flags=re.I | re.S)
        h = re.sub(r"<br\s*/?>", " ", h, flags=re.I)
        h = re.sub(r"</(div|p|tr|td|h[1-6]|li)>", " ", h, flags=re.I)
        h = re.sub(r"&nbsp;", " ", h, flags=re.I)
        h = re.sub(r"&[a-z]+;", " ", h)
        h = re.sub(r"<[^>]+>", " ", h)
        return re.sub(r"\s+", " ", h).strip()

    def from_raw(self, raw) -> Optional[Dict[str, Any]]:
        try:
            msg = email.message_from_bytes(raw)
        except Exception:
            return None
        return self.parse(msg)

    def parse(self, msg) -> Dict[str, Any]:
        subject = self._decode_hdr(msg.get("Subject") or "")
        email_from = self._decode_hdr(msg.get("From") or "")
        date_hdr = msg.get("Date") or ""

        plain, html_body = self._get_body(msg)
        html_clean = self._strip_html(html_body) if html_body else ""
        combined = re.sub(r"\s+", " ", f"{subject} {plain} {html_clean}").strip()
        raw_email = re.sub(r'\s+', ' ', (plain or html_clean)).strip()

        d: Dict[str, Any] = {
            "amount": None, "transaction_id": None, "utr": None,
            "order_id": None, "purpose": None,
            "raw_email": raw_email[:2000],
            "received_from": None, "received_to": None,
            "receiver_name": None, "sender_name": None,
            "payment_status": None, "date": None, "time": None,
            "subject": subject, "balance": None,
            "email_from": email_from, "email_date": None,
            "summary": None, "parse_ok": False,
            "parse_error": None,
        }

        try:
            d["email_date"] = parsedate_to_datetime(date_hdr).astimezone(IST).strftime(
                "%d %b %Y, %I:%M %p"
            )
        except Exception:
            d["email_date"] = date_hdr

        # amount — "received ₹X" priority
        amt = self._find(combined, [
            r'received\s+(?:an\s+amount\s+of\s+)?(?:₹|INR|Rs\.?)?\s*([\d,]+(?:\.\d+)?)',
            r'(?:₹|INR|Rs\.?)\s*([\d,]+(?:\.\d+)?)\s+from\b',
            r'(?:₹|INR|Rs\.?)\s*([\d,]+(?:\.\d+)?)',
        ])
        if amt:
            d["amount"] = amt.replace(",", "").strip().rstrip(".")

        # txn
        txn = self._find(combined, [
            r'(?:Transaction|Txn|Payment)\s*(?:ID|Id|No\.?|Number)\s*[:=-]?\s*([A-Za-z0-9]{6,})',
            r'(FMPIB\w+)',
        ])
        if txn:
            d["transaction_id"] = self._clean(txn)

        # UTR
        utr = self._find(combined, [
            r'UTR\s*(?:No\.?|Number|ID|Ref(?:erence)?)?\s*[:=-]?\s*(\d{6,})',
            r'UTR\s*(?:No\.?|Number|ID|Ref(?:erence)?)?\s*[:=-]?\s*([A-Za-z0-9]{6,})',
        ])
        if utr:
            d["utr"] = self._clean(utr)

        # sender
        sender = self._find(combined, [
            r'\bfrom\s+([A-Z][A-Za-z0-9\s\.\-&]{2,40}?)'
            r'(?=[\s\.]+(?:Transaction|Txn|UTR|Amount|Date|Updated|Balance|If|Best|₹|INR|Rs)\b|[.,]|$)',
            r'(?:Received\s*from|Sender|Paid\s*by)\s*[:=-]?\s*([A-Z][A-Za-z\s\.\-]{2,40}?)'
            r'(?=[\s\.]+(?:Transaction|Txn|UTR|Amount|Date|Updated|Balance|If|₹|INR|Rs)\b|[.,]|$)',
        ])
        if sender:
            d["received_from"] = d["sender_name"] = self._clean(sender)

        # receiver
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
            if any(w in lower for w in ("successfully received", "success",
                                        "received", "credited", "completed")):
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

        # date/time
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

        d["parse_ok"] = bool(d.get("amount") and (d.get("utr") or d.get("transaction_id")))
        if not d["parse_ok"]:
            missing = []
            if not d.get("amount"): missing.append("amount")
            if not d.get("utr") and not d.get("transaction_id"):
                missing.append("utr/txn")
            d["parse_error"] = "missing: " + ",".join(missing)
        return d


# ============================================================
# IMAP FETCH — robust with timeout + retries
# ============================================================
def _strip_pwd(pwd: str) -> str:
    """Remove spaces (Gmail App Passwords are shown with spaces)."""
    return re.sub(r'\s+', '', str(pwd or ""))


def _imap_fetch_fampay_emails_blocking(ea, ap):
    """
    Robust IMAP fetch:
      - 15s socket timeout
      - Auto strip App Password spaces
      - INBOX fallback: [Gmail]/All Mail
      - SINCE last 3 days (UTC)
      - Official sender exact match
    Returns: (emails_list, error_string_or_None)
    """
    conn = None
    out = []
    err = None
    ea = (ea or "").strip()
    ap = _strip_pwd(ap)

    if not ea or not ap:
        return out, "credentials empty"

    try:
        conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, timeout=15)
        try:
            conn.login(ea, ap)
        except imaplib.IMAP4.error as le:
            err = f"LOGIN_FAILED: {le}"
            return out, err

        # Try INBOX first
        try:
            conn.select("INBOX")
        except Exception:
            try:
                conn.select('"[Gmail]/All Mail"')
            except Exception as e2:
                return out, f"select failed: {e2}"

        since = (datetime.utcnow() - timedelta(days=3)).strftime("%d-%b-%Y")

        # Exact official sender
        st, data = conn.search(None, f'(SINCE "{since}" FROM "{FAMPAY_SENDER}")')
        if st != "OK":
            # Fallback domain search
            st, data = conn.search(None, f'(SINCE "{since}" FROM "famapp")')
            if st != "OK":
                return out, f"search failed: {st}"

        ids = data[0].split() if data and data[0] else []
        ids = ids[-100:] if len(ids) > 100 else ids

        for mid in ids:
            try:
                r2, md = conn.fetch(mid, "(RFC822)")
                if r2 != "OK" or not md or not md[0]:
                    continue
                out.append((mid.decode(), md[0][1]))
            except Exception:
                continue

        return out, None

    except Exception as e:
        return out, f"{type(e).__name__}: {e}"
    finally:
        if conn:
            try: conn.close()
            except Exception: pass
            try: conn.logout()
            except Exception: pass


# ============================================================
# MATCHING
# ============================================================
def _find_matching_pending_order(amount, oid_email, utr):
    if oid_email:
        for cand in (oid_email, oid_email.strip(),
                     oid_email.strip().upper(), oid_email.strip().lower()):
            row = cur.execute(
                """SELECT order_id, user_id, amount, created_ts FROM upi_orders
                   WHERE status='pending' AND UPPER(order_id)=UPPER(?)""",
                (cand,)
            ).fetchone()
            if row:
                return row
    if amount is not None:
        rows = cur.execute(
            """SELECT order_id, user_id, amount, created_ts FROM upi_orders
               WHERE status='pending' AND ABS(amount - ?) < 0.01
                 AND created_ts > ?
               ORDER BY created_ts DESC LIMIT 5""",
            (float(amount), time.time() - 900)
        ).fetchall()
        if rows:
            return rows[0]
        rows = cur.execute(
            """SELECT order_id, user_id, amount, created_ts FROM upi_orders
               WHERE status='pending' AND ABS(amount - ?) < 0.01
               ORDER BY created_ts DESC LIMIT 1""",
            (float(amount),)
        ).fetchall()
        if rows:
            return rows[0]
    return None


# ============================================================
# ALERTS (owner + logs)
# ============================================================
async def _send_to_owner_and_logs(blocks, fallback_text, reply_markup=None):
    try:
        await _deliver_rich_to_target(current_owner_id(), blocks, fallback_text,
                                       reply_markup=reply_markup)
    except Exception as e:
        log.warning(f"owner alert failed: {e}")
    try:
        await _send_log_rich(blocks, fallback_text, reply_markup=reply_markup)
    except Exception as e:
        log.warning(f"log alert failed: {e}")


async def _alert_imap_error(err_msg):
    """IMAP login/connection failed — alert owner (rate limited to 1/hr)."""
    global _last_imap_alert_ts
    now = time.time()
    if now - _last_imap_alert_ts < _IMAP_ALERT_COOLDOWN:
        return
    _last_imap_alert_ts = now

    blocks = [make_heading("🚨 FAMPAY IMAP ERROR", 2),
              make_paragraph(
                  "Gmail IMAP login/fetch fail ho raha hai.\n"
                  "Auto-verification WORK नहीं कर रहा!"),
              make_table([["⚠️ ERROR", str(err_msg)[:200]],
                          ["📧 Sender", FAMPAY_SENDER],
                          ["🕐 Time", datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")]])]
    kb = InlineKeyboardMarkup([
        [ibtn("CHECK SETTINGS", "adm_gmail_menu", emoji="📧", style="primary")],
        [ibtn("TEST IMAP", "adm_gmail_test", emoji="🧪", style="success")],
        [ibtn("HOME", "home", emoji="🏠", style="primary")]])
    await _send_to_owner_and_logs(
        blocks,
        f"🚨 FamPay IMAP ERROR: {str(err_msg)[:150]}",
        kb.to_dict()
    )


async def _alert_order_not_found(parsed):
    rows = [["ℹ️ INFO", "📋 DETAIL"],
            ["💰 Amount", f"₹{parsed.get('amount') or '—'}"],
            ["🔢 UTR", str(parsed.get("utr") or "—")],
            ["🆔 TXN", str(parsed.get("transaction_id") or "—")],
            ["👤 Sender", str(parsed.get("sender_name") or "—")],
            ["👥 Receiver", str(parsed.get("receiver_name") or "—")],
            ["📅 Date", str(parsed.get("date") or "—")],
            ["⏰ Time", str(parsed.get("time") or "—")],
            ["📧 From", str(parsed.get("email_from") or "—")[:60]],
            ["⚠️ Reason", "No matching pending order"]]
    blocks = [make_heading("⚠️ FAMPAY PAYMENT — ORDER NOT FOUND", 2),
              make_paragraph(
                  "Payment email आया, लेकिन कोई pending order match नहीं हुआ.\n\n"
                  "Possible reasons:\n"
                  "• User ने order बनाए बिना pay किया\n"
                  "• Order expire हो गया (>15 min)\n"
                  "• Amount match नहीं\n"
                  "• Different UPI ID use हुआ"),
              make_table(rows)]
    fb = (f"⚠️ FAMPAY — ORDER NOT FOUND\n"
          f"💰 ₹{parsed.get('amount')} | UTR {parsed.get('utr')}\n"
          f"👤 {parsed.get('sender_name')}")
    kb = InlineKeyboardMarkup([
        [ibtn("MANUAL UPI", "adm_manual_upi_set", emoji="📄", style="primary")],
        [ibtn("HOME", "home", emoji="🏠", style="primary")]])
    await _send_to_owner_and_logs(blocks, fb, kb.to_dict())


async def _alert_parse_failed(mid, raw, err):
    try:
        snippet = raw.decode("utf-8", errors="ignore")[:800]
    except Exception:
        snippet = str(raw)[:800]
    snippet = escape(re.sub(r'\s+', ' ', snippet))
    blocks = [make_heading("❌ FAMPAY PARSE FAILED", 2),
              make_paragraph(f"mid: {mid}\nerror: {err}"),
              make_table([["⚠️ SNIPPET", snippet[:500]]])]
    fb = f"❌ FamPay parse failed: mid={mid}\nerr={err}"
    await _send_to_owner_and_logs(blocks, fb)


async def _send_mismatch_alert(uid, oid, exp, paid, utr=None, txn=None, src="auto"):
    diff = round((paid or 0) - (exp or 0), 2)
    ds = f"+₹{diff}" if diff > 0 else f"₹{diff}"
    msg = (f"<b>{emo('⚠️')} PAYMENT REJECTED — MISMATCH</b>\n\n"
           f"{emo('🆔')} <b>Order:</b> <code>{oid}</code>\n"
           f"{emo('💰')} <b>Expected:</b> ₹{int(exp)}\n"
           f"{emo('💵')} <b>Paid:</b> ₹{paid}\n"
           f"{emo('📉')} <b>Diff:</b> {ds}\n"
           f"{emo('🔢')} UTR: <code>{utr or '—'}</code>\n"
           f"{emo('🆔')} TXN: <code>{txn or '—'}</code>\n\n"
           f"<b>{emo('🚫')} NOT credited</b>\n"
           f"<b>{emo('👉')} Contact:</b> {get_contact_1()}")
    kb = InlineKeyboardMarkup([
        [ibtn("CONTACT OWNER", url=get_support_url(), emoji="📞", style="success")],
        [ibtn("HOME", "home", emoji="🏠", style="primary")]])
    try:
        await _tg_post("sendMessage", {"chat_id": uid, "text": msg,
            "parse_mode": "HTML", "reply_markup": kb.to_dict()})
    except Exception:
        pass
    blocks = [make_heading("⚠️ MISMATCH — NOT CREDITED", 2),
              make_table([["ℹ️ INFO", "📋 DETAIL"],
                          ["🆔 Order", oid], ["👤 User", str(uid)],
                          ["💰 Expected", f"₹{int(exp)}"],
                          ["💵 Paid", f"₹{paid}"],
                          ["📉 Diff", ds],
                          ["🔢 UTR", str(utr or "—")],
                          ["🆔 TXN", str(txn or "—")]])]
    await _send_to_owner_and_logs(blocks,
        f"⚠️ Mismatch: {oid} | Exp ₹{int(exp)} | Paid ₹{paid}")


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
    blocks = [make_heading("🚫 DUPLICATE PAYMENT", 2),
              make_table([["ℹ️ INFO", "📋 DETAIL"],
                          ["🆔 New Order", oid], ["👤 User", str(uid)],
                          ["🔢 UTR", str(utr or "—")],
                          ["🆔 TXN", str(txn or "—")],
                          ["♻️ Already In", existing]])]
    await _send_to_owner_and_logs(blocks,
        f"🚫 Duplicate: {oid} → already in {existing}")


# ============================================================
# PROCESS EMAIL
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
        await _alert_parse_failed(mid, raw, "parser returned None")
        return

    email_from = (parsed.get("email_from") or "").lower()
    if FAMPAY_SENDER.lower() not in email_from:
        log.info(f"⏭ Skipping non-official sender: {email_from}")
        return

    if not parsed.get("parse_ok"):
        await _alert_parse_failed(mid, raw,
            parsed.get("parse_error") or "missing amount/utr/txn")
        return

    try:
        amount_f = float(parsed.get("amount")) if parsed.get("amount") else None
    except Exception:
        amount_f = None
    utr = parsed.get("utr")
    txn = parsed.get("transaction_id")

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
    except Exception as e:
        log.warning(f"fampay_emails insert: {e}")

    if amount_f is None:
        await _alert_parse_failed(mid, raw, "amount missing")
        return

    existing = None
    if utr:
        existing = is_utr_used_by_other_order(utr)
    if not existing and txn:
        existing = is_txn_used_by_other_order(txn)

    match = _find_matching_pending_order(amount_f, parsed.get("order_id"), utr)

    if not match:
        await _alert_order_not_found(parsed)
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
    except Exception as e:
        log.warning(f"fampay update: {e}")

    await complete_upi_order(oid, uid, int(exp), None, "fampay_imap", utr=utr, txn=txn)
    log.info(f"✅ FamPay credited: {oid} ₹{int(exp)} UTR={utr} TXN={txn}")


# ============================================================
# POLL LOOP — with failure alerting
# ============================================================
async def fampay_imap_poll_loop():
    log.info(f"📧 FamPay poll @{current_bot_username()}")
    await asyncio.sleep(5)
    fail_count = 0
    while True:
        try:
            if not is_gmail_verify_enabled():
                await asyncio.sleep(IMAP_POLL_INTERVAL)
                continue

            ea = get_setting('gmail_email', '').strip()
            ap = get_setting('gmail_app_password', '').strip()

            if not ea or not ap:
                log.warning("FamPay: email/password not set")
                await asyncio.sleep(IMAP_POLL_INTERVAL)
                continue

            emails, err = await asyncio.to_thread(
                _imap_fetch_fampay_emails_blocking, ea, ap
            )

            if err:
                fail_count += 1
                log.warning(f"FamPay IMAP error (#{fail_count}): {err}")
                # Alert owner on every 6th failure (≈ every minute) OR
                # on critical errors immediately
                if "LOGIN_FAILED" in err or fail_count >= 6:
                    await _alert_imap_error(err)
                    fail_count = 0
                await asyncio.sleep(IMAP_POLL_INTERVAL)
                continue

            fail_count = 0

            if emails:
                parser = FamPayEmailParser()
                processed = 0
                for mid, raw in emails:
                    try:
                        parsed = parser.from_raw(raw)
                        await _process_fampay_email(mid, raw, parsed)
                        processed += 1
                    except Exception as e:
                        log.error(f"FamPay process mid={mid}: {e}")
                        traceback.print_exc()
                        try:
                            await _alert_parse_failed(mid, raw, f"exception: {e}")
                        except Exception:
                            pass
                if processed:
                    log.info(f"📬 FamPay: checked {processed} email(s)")

        except Exception as e:
            log.error(f"FamPay poll error: {e}")
            traceback.print_exc()

        await asyncio.sleep(IMAP_POLL_INTERVAL)


# ============================================================
# CROSS-MODULE IMPORTS
# ============================================================
from buttons import ibtn
from config import (
    FAMPAY_SENDER, IMAP_POLL_INTERVAL, IMAP_PORT, IMAP_SERVER, IST, log
)
from context import cur, current_bot_username, current_owner_id, db
from database import (
    get_contact_1, get_setting, get_support_url, is_gmail_verify_enabled,
    is_txn_used_by_other_order, is_utr_used_by_other_order
)
from emojis import emo
from payments import complete_upi_order
from rich_ui import (
    _deliver_rich_to_target, _send_log_rich, _tg_post,
    make_heading, make_paragraph, make_table
)
