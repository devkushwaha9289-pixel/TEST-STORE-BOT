#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — utils.py
Generic helpers: masking, slugs, order-ids, UPI URL / QR generation.
"""

import re, time, string, secrets
from html import escape
from urllib.parse import quote

import base64
from io import BytesIO

try:
    import qrcode
    QR_AVAILABLE = True
except Exception:
    qrcode = None
    QR_AVAILABLE = False

try:
    from qrcode.constants import ERROR_CORRECT_M
except Exception:
    ERROR_CORRECT_M = 0


def html_safe_error(e): return escape(str(e) if e else "Unknown error")

def strip_html_for_rich(text):
    if not text: return ""
    text = str(text)
    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
                  lambda m: (m.group(2) or m.group(1)), text,
                  flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    for k, v in (('&amp;','&'),('&lt;','<'),('&gt;','>'),
                 ('&quot;','"'),('&#39;',"'"),('&nbsp;',' ')):
        text = text.replace(k, v)
    return text

def mask_username_public(username):
    u = str(username or "").strip()
    if not u or u == "—": return "—"
    u = u.lstrip("@")
    if len(u) <= 4: return "@" + "*" * len(u)
    return "@" + f"{u[:2]}{'*' * (len(u) - 4)}{u[-2:]}"

def mask_user_id_public(uid):
    s = str(uid or "").strip()
    if not s: return "—"
    if len(s) <= 5: return "*" * len(s)
    return f"{s[:3]}{'*' * (len(s) - 5)}{s[-2:]}"

# ============================================================
# SLUGS & ITEM CODES
# ============================================================
def generate_item_code():
    return f"{ORDER_PREFIX}{secrets.randbelow(90000) + 10000}"

def slugify_category(name):
    if not name: return ""
    n = str(name).upper().strip()
    for suffix in (" ACCOUNT", " PANEL", " PANELS", " APIS", " API", " SRC", " CODE"):
        if n.endswith(suffix):
            n = n[:-len(suffix)]
    return re.sub(r'[^a-z0-9]', '', n.lower())

def slugify_section(name):
    if not name: return ""
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def find_category_by_slug(server, slug):
    if not slug: return None
    slug = slug.lower()
    for r in cur.execute("SELECT name FROM custom_categories WHERE server=? AND active=1",
                         (server,)).fetchall():
        if slugify_category(r["name"]) == slug:
            return r["name"]
    return None

def get_panel_brand_name(name, link):
    link_l = (link or "").strip().lower()
    for domain, brand in PANEL_BRANDS.items():
        if domain in link_l:
            return brand
    try:
        m = re.search(r'https?://([^/]+)', link_l)
        if m:
            host = m.group(1).replace("www.", "")
            base = host.split(".")[0]
            if base:
                return base.upper()
    except Exception:
        pass
    return str(name or "PANEL").upper()


# ============================================================
# ORDER ID / QR
# ============================================================
def generate_unique_order_id(uid):
    uid_str = str(uid)
    us = uid_str[:4] if len(uid_str) >= 4 else uid_str.zfill(4)
    alnum = string.ascii_letters + string.digits
    letters = string.ascii_letters
    for _ in range(30):
        mid = "".join(secrets.choice(alnum) for _ in range(8))
        end = "".join(secrets.choice(letters) for _ in range(4))
        oid = f"{ORDER_PREFIX}{us}{mid}{end}"
        try:
            if not cur.execute("SELECT 1 FROM upi_orders WHERE order_id=?", (oid,)).fetchone():
                return oid
        except: return oid
    return f"{ORDER_PREFIX}{us}{int(time.time()*1000)}{secrets.token_hex(2)}"

def create_upi_url(upi, amount, order_id, name):
    return ("upi://pay?"f"pa={quote(str(upi), safe='')}"f"&pn={quote(str(name), safe='')}"
            f"&am={quote(str(amount), safe='')}"f"&tr={quote(str(order_id), safe='')}"
            f"&tn={quote(f'Payment for ORDER{order_id}', safe='')}"f"&cu=INR")

def make_qr_png_bytes(data):
    """Render ANY text (UPI link) as a PNG QR. Works with Pillow or pure-PyPNG backend."""
    if not QR_AVAILABLE:
        raise RuntimeError("qrcode not installed (pip install qrcode[pil])")
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    try:
        img.save(buf, format="PNG")
    except TypeError:
        buf = BytesIO(); img.save(buf)
    out = buf.getvalue()
    if not out:
        raise RuntimeError("QR render produced empty image")
    return out

def generate_qr_png_bytes(upi, amount, order_id, name):
    return make_qr_png_bytes(create_upi_url(upi, amount, order_id, name))

def qr_data_uri(data):
    """data:image/png;base64,... for the Mini App (no external QR service needed)."""
    try:
        return "data:image/png;base64," + base64.b64encode(make_qr_png_bytes(data)).decode()
    except Exception:
        return ""


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from config import ORDER_PREFIX, PANEL_BRANDS
from context import cur
