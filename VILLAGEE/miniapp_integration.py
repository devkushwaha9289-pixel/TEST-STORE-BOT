#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE — Mini App integration for the bot.
Adds a /app command and sets the bot menu button to open the Mini App.
"""
from telegram import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
    MenuButtonWebApp
)
from telegram.ext import CommandHandler

MINIAPP_URL = "https://test-store-bot-1.onrender.com"
MINIAPP_BUTTON_TEXT = "🛍️ Shop"

def _webapp_url(bot_username: str) -> str:
    return f"{MINIAPP_URL}/?bot={bot_username}"

async def cmd_app(update, context):
    if not MINIAPP_URL:
        await update.message.reply_text("⚠️ Mini App URL not configured (MINIAPP_URL).")
        return
    url = _webapp_url(context.bot.username)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🛒 Open Mini App", web_app=WebAppInfo(url=url))
    ]])
    await update.message.reply_text(
        "🛍️ <b>VILLAGEE SMS SHOP</b>\nTap below to open the Mini App:",
        parse_mode="HTML", reply_markup=kb)

async def set_menu_button(app, bot_username: str):
    """Set the Telegram private-chat menu button and command list automatically."""
    from config import log

    if not MINIAPP_URL:
        log.warning("Mini App URL is empty; menu button was not set")
        return False

    bot_username = (bot_username or "").lstrip("@").strip()
    url = _webapp_url(bot_username)

    # 1) Mini App menu button (same API as setChatMenuButton).
    try:
        result = await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=MINIAPP_BUTTON_TEXT,
                web_app=WebAppInfo(url=url),
            )
        )
        if result is not True:
            log.warning(f"setChatMenuButton returned {result!r} @{bot_username}")
            return False
        log.info(f"✅ setChatMenuButton @{bot_username} -> {url}")
    except Exception as e:
        log.exception(f"❌ setChatMenuButton failed @{bot_username}: {e}")
        return False

    # 2) Keep the '/' command picker populated as well.
    try:
        await app.bot.set_my_commands([
            ("start", "Start bot"),
            ("shop", "Open Mini App shop"),
            ("app", "Open Mini App"),
            ("stock", "Check stock"),
            ("cancel", "Cancel current action"),
            ("admin", "Admin panel"),
        ])
        log.info(f"✅ Bot commands set @{bot_username}")
    except Exception as e:
        log.exception(f"⚠️ setMyCommands failed @{bot_username}: {e}")

    return True

def register(app, W):
    """Register /app handler into an existing Application (via wrapper)."""
    app.add_handler(CommandHandler("app", W(cmd_app)))
    app.add_handler(CommandHandler("shop", W(cmd_app)))
