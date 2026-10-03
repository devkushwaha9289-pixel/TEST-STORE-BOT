#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE — Mini App integration for the bot.
Adds /app and /shop commands and sets the bot menu button to open the Mini App.
"""

from telegram import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
    MenuButtonWebApp
)
from telegram.ext import CommandHandler

import os
MINIAPP_URL = os.getenv("MINIAPP_URL", "https://test-store-bot-1.onrender.com").rstrip("/")
MINIAPP_BUTTON_TEXT = "🛍️ Shop"


def _webapp_url(bot_username: str) -> str:
    return f"{MINIAPP_URL}/?bot={bot_username}"


async def cmd_app(update, context):
    if not MINIAPP_URL:
        await update.message.reply_text(
            "⚠️ Mini App URL not configured (MINIAPP_URL)."
        )
        return

    username = (getattr(context.bot, "username", "") or "").lstrip("@").strip()
    url = _webapp_url(username)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🛒 Open Mini App",
            web_app=WebAppInfo(url=url)
        )
    ]])

    await update.message.reply_text(
        "🛍️ <b>VILLAGEE SMS SHOP</b>\n"
        "Tap below to open the Mini App:",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def set_bot_commands(app):
    """Set the Telegram command list for the current bot."""
    from config import log

    try:
        await app.bot.set_my_commands([
            ("start", "Start bot"),
            ("shop", "Open Mini App"),
            ("app", "Open Mini App"),
            ("stock", "Check stock"),
            ("cancel", "Cancel current action"),
            ("admin", "Admin panel"),
        ])
        log.info("✅ Bot commands set")
        return True
    except Exception as e:
        log.exception(f"⚠️ setMyCommands failed: {e}")
        return False


async def set_menu_button(app, bot_username: str):
    """Set the Telegram private-chat menu button to open the Mini App."""
    from config import log

    if not MINIAPP_URL:
        log.warning("Mini App URL is empty; menu button was not set")
        return False

    bot_username = (bot_username or "").lstrip("@").strip()
    url = _webapp_url(bot_username)

    try:
        result = await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=MINIAPP_BUTTON_TEXT,
                web_app=WebAppInfo(url=url),
            )
        )
        if result is not True:
            log.warning(
                f"setChatMenuButton returned {result!r} @{bot_username}"
            )
            return False

        log.info(f"✅ setChatMenuButton @{bot_username} -> {url}")
        return True

    except Exception as e:
        log.exception(
            f"❌ setChatMenuButton failed @{bot_username}: {e}"
        )
        return False


def register(app, W):
    """Register Mini App handlers into an existing Application."""
    app.add_handler(CommandHandler("app", W(cmd_app)))
    app.add_handler(CommandHandler("shop", W(cmd_app)))
