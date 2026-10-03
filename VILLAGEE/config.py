#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — config.py
Global configuration: tokens/IDs/URLs/limits, IST time helper, logging setup.
"""

import os, logging
from datetime import datetime, timedelta, timezone

# ============================================================
# TIME
# ============================================================
IST = timezone(timedelta(hours=5, minutes=30))
def now_ist(): return datetime.now(IST)


# ============================================================
# CONFIG
# ============================================================
API_ID = int(os.getenv("API_ID", "32208414"))
API_HASH = os.getenv("API_HASH", "628f11c05a44c8dda4b006e66f4bf7df")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8688851169:AAEtvbAYart5t7h4QnCi2aS5C0TN6RN7Daw")

STORE_HEADER = "🅱️ VILLAGEE SMS SHOP"
DEFAULT_CONTACT_1 = "@Z4X_Silent_Boy"
DEFAULT_CONTACT_2 = "@VILLAGEE_SMS_UPDATEs"
DEFAULT_SUPPORT_URL = "https://t.me/Z4X_Silent_Boy"
DEFAULT_UPDATE_URL = "https://t.me/VILLAGEE_SMS_UPDATEs"
REFERRAL_RATE = "1.5%"
OTP_DB_NAME = "otp_bot_final.db"
ORDER_PREFIX = "VILLAGEEsms"
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL", "-1003876693918"))
TERMS_URL = "https://digitalworld1318-sys.github.io/services/"
MAINTENANCE_IMAGE = "https://i.ibb.co/rKGjp2GS/80bf7c4fc981.jpg"

PURCHASE_WARNING = (
    "⚠️ <b>Important:</b> Please use <b>Graph Manager / Plus Messenger</b>.\n"
    "🚫 We are not responsible for any freeze/ban"
)
PURCHASE_WARNING_ROWS = [
    ["⚠️ IMPORTANT", "Please use Graph Manager / Plus Messenger."],
    ["🚫 DISCLAIMER", "We are not responsible for any freeze/ban"],
]

PANEL_BRANDS = {
    'lzt.market': 'LZT MARKET', 'grizzlysms.com': 'GRIZZLY SMS',
    'smspva.com': 'SMSPVA', '5sim.net': '5SIM', 'sms-activate.org': 'SMS-ACTIVATE',
    'sms-man.com': 'SMS-MAN', 'tiger-sms.com': 'TIGER SMS', 'onlinesim.io': 'ONLINESIM',
    'vak-sms.com': 'VAK-SMS', 'smshub.org': 'SMSHUB', 'smspool.net': 'SMSPOOL',
    'smscodes.io': 'SMSCODES', 'proxystore.io': 'PROXYSTORE',
}

CWALLET_QR = "https://ibb.co/0RfRDMQG"
CWALLET_ID = "81323047"
BINANCE_QR = "https://i.ibb.co/k2mtG4kM/a173ae021b42.jpg"
BINANCE_ID = "1242151195"
TRON_QR = "https://ibb.co/QFd6Zzj9"
TRON_ID = "TSQhx39pg43KdDpSwFBksGYWWxh7F7VkZZ"
POLYGON_QR = "https://ibb.co/NgNjtQNC"
POLYGON_ID = "0xb454937A5827712cc03b2471386f886a03F7a1D0"

# ⭐ v28.1 — Manual UPI
DEFAULT_MANUAL_UPI_ID = os.getenv("MANUAL_UPI_ID", "devkushwaha94@ibl")
MANUAL_UPI_WINDOW_SECONDS = 900  # 15 minutes

DEFAULT_UPI_PAY_ID = os.getenv("UPI_PAY_ID", "devkushwaha94@fam")
UPI_MERCHANT_NAME = os.getenv("UPI_MERCHANT_NAME", "VILLAGEE SMS")
UPI_VERIFY_WINDOW_SECONDS = 900

# Paytm Automatic UPI
PAYTM_STATUS_URL = os.getenv("PAYTM_STATUS_URL", "https://securegw.paytm.in/merchant-status/getTxnStatus")
PAYTM_MID = os.getenv("PAYTM_MID", "").strip()
PAYTM_UPI_ID = os.getenv("PAYTM_UPI_ID", "").strip()
PAYTM_MERCHANT_NAME = os.getenv("PAYTM_MERCHANT_NAME", "Paytm Merchant").strip()
PAYTM_VERIFY_INTERVAL = float(os.getenv("PAYTM_VERIFY_INTERVAL", "10"))
PAYTM_REQUEST_TIMEOUT = float(os.getenv("PAYTM_REQUEST_TIMEOUT", "10"))
DEFAULT_MIN_DEPOSIT = 10
DEFAULT_STOCK_PRICE = 100

DEFAULT_GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "")
DEFAULT_GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
FAMPAY_SENDER = "no-reply@famapp.in"
IMAP_POLL_INTERVAL = 10

OTP_REGEX = r"\b\d{4,8}\b"
AUTO_CANCEL_SECONDS = 600

LZT_TOKEN = os.getenv("LZT_TOKEN", "").strip()
LZT_BASE_URL = os.getenv("LZT_BASE_URL", "https://prod-api.lzt.market").rstrip("/")
LZT_REQUEST_TIMEOUT = float(os.getenv("LZT_REQUEST_TIMEOUT", "8"))
LZT_STOCK_TIMEOUT = float(os.getenv("LZT_STOCK_TIMEOUT", "12"))
LZT_MAX_RETRIES = int(os.getenv("LZT_MAX_RETRIES", "2"))
LZT_STOCK_RETRIES = int(os.getenv("LZT_STOCK_RETRIES", "1"))
LZT_CACHE_CONCURRENCY = int(os.getenv("LZT_CACHE_CONCURRENCY", "1"))
LZT_FORCE_IPV4 = os.getenv("LZT_FORCE_IPV4", "1").strip().lower() not in ("0","false","no","off")
LZT_HTTP_FALLBACK = os.getenv("LZT_HTTP_FALLBACK", "1").strip().lower() not in ("0","false","no","off")
LZT_PROXY = os.getenv("LZT_PROXY", "").strip()
LZT_FAST_BUY_RETRIES = int(os.getenv("LZT_FAST_BUY_RETRIES", "5"))
LZT_PRICE_CURRENCY = os.getenv("LZT_PRICE_CURRENCY", "rub").strip().lower() or "rub"
LZT_REQUEST_INTERVAL = max(2.0, float(os.getenv("LZT_REQUEST_INTERVAL", "3")))
LZT_MIN_REQUEST_INTERVAL = LZT_REQUEST_INTERVAL
LZT_RATE_LIMIT_COOLDOWN = float(os.getenv("LZT_RATE_LIMIT_COOLDOWN", "300"))
LZT_CACHE_BATCH_SIZE = max(1, int(os.getenv("LZT_CACHE_BATCH_SIZE", "1")))
LZT_CACHE_IDLE_SECONDS = float(os.getenv("LZT_CACHE_IDLE_SECONDS", "15"))
USER_REFRESH_COOLDOWN = float(os.getenv("USER_REFRESH_COOLDOWN", "10"))
STOCK_CACHE_TTL = float(os.getenv("STOCK_CACHE_TTL", "300"))

LZT_RESET_AUTH_RETRIES = int(os.getenv("LZT_RESET_AUTH_RETRIES", "3"))
LZT_RESET_AUTH_WAIT = float(os.getenv("LZT_RESET_AUTH_WAIT", "2.0"))

OSINT_DEFAULT_BASE_URL = os.getenv(
    "OSINT_BASE_URL", "https://villagee-sms-apis-shop-store.vercel.app"
).rstrip("/")
OSINT_ADMIN_PATH = "admin-VILLAGEEbhai"
OSINT_DEFAULT_KEY_DAYS = int(os.getenv("OSINT_DEFAULT_KEY_DAYS", "30"))

FORCE_JOIN_CACHE_TTL = float(os.getenv("FORCE_JOIN_CACHE_TTL", "8"))

OSINT_NAME_TO_ENDPOINT = {
    "NUMBER INFO": "/mobile2info",
    "AADHAR INFO": "/id2info",
    "NAME 2 INFO": "/name2info",
    "PAN INFO": "/pan",
    "PAN TO GST": "/pantogst",
    "GST TO PAN": "/gsttopan",
    "AADHAR TO MASKED PAN": "/aadhar2pan",
    "VOTER EPIC TO INFO": "/Voter_info",
    "TELEGRAM TO NUMBER": "/tg2num",
    "PAN NUMBER TO INFO": "/pan",
    "CNIC TO INFO": "/pakistan",
    "AADHAR TO FAMILY": "/adhar2family",
    "RATION TO FAMILY": "/ration2family",
    "AADHAR TO RATION NUMBER": "/adhar2rationNo",
    "VEHICLE TO CHALLAN INFO": "/vehicle_challan",
    "VEHICLE INFO": "/vehicle",
    "VEHICLE TO OWNER MOBILE": "/vehicle",
    "IFSC CODE INFO": "/ifsc",
    "ALL LPG GAS INFO": "/lpg",
    "MOBILE TO RC": "/vehicle",
}

DAYBREAK_OPTIONS = ("any", 1, 7, 14, 30)
DEFAULT_DAYBREAK = 1
# Listing eligibility: last edited time must be older than 24 hours.
LAST_EDIT_MIN_AGE_SECONDS = int(os.getenv("LAST_EDIT_MIN_AGE_SECONDS", "86400"))

# Backward compatibility for existing imports elsewhere in the project.
ELIGIBILITY_MIN_AGE_SECONDS = LAST_EDIT_MIN_AGE_SECONDS

LAST_EDIT_FIELD_CANDIDATES = (
    "last_edit","lastEdit","last_edited","lastEdited","last_edited_at","lastEditedAt",
    "edit_at","editAt","edited_at","editedAt","updated_at","updatedAt","date_edit",
    "dateEdit","date_edited","dateEdited","last_edit_date","lastEditDate",
)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("villagee")
