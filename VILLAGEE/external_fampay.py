#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External FamPay verification client.

The Telegram bot / Mini App NEVER connects to Gmail/IMAP directly.
All payment lookup is delegated to the deployed Vercel verification API.
"""
import asyncio
import re
import requests

FAMPAY_VERIFY_API = "https://vilagee-sms-shop-bot-famapy-auto-ve.vercel.app/verify"


def _credentials():
    # Import lazily so this module can be imported safely during bot startup.
    from database import get_setting
    enabled = (get_setting("gmail_verify_enabled", "on") or "on").strip().lower() == "on"
    gmail = (get_setting("gmail_email", "") or "").strip()
    app_password = (get_setting("gmail_app_password", "") or "").strip().replace(" ", "")
    return enabled, gmail, app_password


def classify_reference(reference: str):
    """12 numeric digits = UTR. Everything else = TXN."""
    value = re.sub(r"\s+", "", str(reference or "").strip().upper())
    if not value:
        return None, ""
    value = re.sub(r"^(?:UTR|TXN|TRANSACTIONID|TRANSACTION_ID|TRANSACTION)[:\-\s]*", "", value)
    if re.fullmatch(r"\d{12}", value):
        return "utr", value
    return "txn", value


def _amount_text(amount):
    try:
        f = float(amount)
        if f.is_integer():
            return str(int(f))
        return f"{f:.2f}".rstrip("0").rstrip(".")
    except Exception:
        return str(amount)


def verify_fampay_reference(reference: str, amount: float, order_id: str = ""):
    """Call Vercel using credentials stored in the current bot DB.

    The amount is supplied by the caller from the pending order DB row.
    order_id is intentionally not sent to the Vercel API because the deployed
    API verifies the payment reference; local code ties that result to the
    exact pending order.
    """
    enabled, gmail, app_password = _credentials()
    if not enabled:
        return {"success": False, "verified": False, "status": "disabled",
                "message": "FamPay verification is disabled in Admin Panel."}
    if not gmail or not app_password:
        return {"success": False, "verified": False, "status": "credentials_missing",
                "message": "Set Gmail and Gmail App Password in Admin Panel first."}

    kind, value = classify_reference(reference)
    if not value:
        return {"success": False, "verified": False, "status": "invalid_reference",
                "message": "Enter UTR or Transaction ID."}
    if kind == "utr" and not re.fullmatch(r"\d{12}", value):
        return {"success": False, "verified": False, "status": "invalid_reference",
                "message": "UTR must be exactly 12 numeric digits."}

    params = {
        "gmail": gmail,
        "app_password": app_password,
        kind: value,
        "amount": _amount_text(amount),
    }

    try:
        response = requests.get(FAMPAY_VERIFY_API, params=params, timeout=45)
    except requests.RequestException as exc:
        return {"success": False, "verified": False, "status": "api_error",
                "message": f"Verification service unavailable: {exc}"}

    try:
        data = response.json()
    except Exception:
        return {"success": False, "verified": False, "status": "api_error",
                "message": f"Verification API returned HTTP {response.status_code}."}

    if not isinstance(data, dict):
        return {"success": False, "verified": False, "status": "api_error",
                "message": "Invalid verification API response."}

    data["http_status"] = response.status_code
    data["query_type"] = kind
    data["query_value"] = value
    return data


async def verify_fampay_reference_async(reference: str, amount: float, order_id: str = ""):
    return await asyncio.to_thread(verify_fampay_reference, reference, amount, order_id)
