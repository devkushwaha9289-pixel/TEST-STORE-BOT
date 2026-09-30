#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE — Mini App integration for the bot.
Adds a /app command and sets the bot menu button to open the Mini App.
"""
import os
from telegram import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
    MenuButtonWebApp
)
from telegram.ext import CommandHandler

MINIAPP_URL = os.getenv("MINIAPP_URL", "https://test-store-bot-1.onrender.com").rstrip("/")

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
    """Set bot's menu button to open the Mini App."""
    if not MINIAPP_URL:
        return
    url = _webapp_url(bot_username)
    try:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="🛒 Store", web_app=WebAppInfo(url=url))
        )
    except Exception as e:
        from config import log
        log.warning(f"set_menu_button @{bot_username}: {e}")

def register(app, W):
    """Register /app handler into an existing Application (via wrapper)."""
    app.add_handler(CommandHandler("app", W(cmd_app)))
    app.add_handler(CommandHandler("shop", W(cmd_app)))
