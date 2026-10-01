#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — runner.py
Per-bot Application builder and multi-bot runner.
+ Mini App integration (WebApp menu button + /app command)
"""

import asyncio
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telethon import TelegramClient

# ============================================================
# PER-BOT APP
# ============================================================
def _wrap_cb(fn, ctx):
    async def wrapper(update, context):
        _current_bot.set(ctx)
        return await fn(update, context)
    return wrapper

async def _post_init_for(app, ctx):
    tok = _current_bot.set(ctx)
    try:
        ctx.telethon_loop = asyncio.get_running_loop()
        try:
            client = TelegramClient(f"{ctx.data_dir}/bot_session_main", API_ID, API_HASH)
            await client.start(bot_token=ctx.token)
            ctx.telethon_client = client
            log.info(f"✅ Telethon @{ctx.username}")
        except Exception as e:
            log.error(f"Telethon @{ctx.username}: {e}")

        asyncio.create_task(cache_lzt_stock_loop())

        # ⭐ Mini App — set bot menu button (opens WebApp)
        try:
            await set_bot_commands(app)
            await set_menu_button(app, ctx.username)
            log.info(f"✅ Mini App menu + /commands set @{ctx.username}")
        except Exception as e:
            log.warning(f"Mini App menu @{ctx.username}: {e}")

        log.info(f"✅ Loops @{ctx.username}")
    finally:
        _current_bot.reset(tok)

def build_app_for_ctx(ctx):
    app = (Application.builder().token(ctx.token)
           .concurrent_updates(True)
           .post_init(lambda a: _post_init_for(a, ctx))
           .build())
    ctx.app = app
    W = lambda fn: _wrap_cb(fn, ctx)

    # ---- Commands ----
    app.add_handler(CommandHandler("start", W(cmd_start)))
    app.add_handler(CommandHandler("cancel", W(cmd_cancel)))
    app.add_handler(CommandHandler("admin", W(cmd_admin)))
    app.add_handler(CommandHandler("stock", W(cmd_stock)))
    app.add_handler(CommandHandler("app",  W(cmd_app)))    # ⭐ Mini App
    app.add_handler(CommandHandler("shop", W(cmd_app)))    # ⭐ alias

    # ---- Callbacks / Messages ----
    app.add_handler(CallbackQueryHandler(W(on_callback)))
    app.add_handler(MessageHandler(filters.Document.ALL, W(handle_document)))
    app.add_handler(MessageHandler(filters.PHOTO, W(on_photo)))
    app.add_handler(MessageHandler(filters.VIDEO, W(on_video)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, W(on_text)))
    app.add_error_handler(on_error)
    return app

# ============================================================
# MULTI-BOT RUNNER
# ============================================================
async def run_multi_bot():
    cfg = load_bots_config()
    bots_cfg = cfg.setdefault("bots", {})
    if BOT_TOKEN not in bots_cfg:
        mu = await fetch_bot_username(BOT_TOKEN)
        if not mu:
            log.error("❌ Cannot fetch master bot username"); mu = "master_bot"
        bots_cfg[BOT_TOKEN] = {"owner_id": MASTER_OWNER_ID, "username": mu, "is_master": True}
    else:
        bots_cfg[BOT_TOKEN]["owner_id"] = MASTER_OWNER_ID
        bots_cfg[BOT_TOKEN]["is_master"] = True
    save_bots_config(cfg)

    for token, info in list(bots_cfg.items()):
        try:
            un = info.get("username")
            if not un:
                un = await fetch_bot_username(token)
                if not un:
                    log.error(f"⚠️ Invalid token {token[:20]}..."); continue
                info["username"] = un; save_bots_config(cfg)
            ctx = BotContext(token, un, info.get("owner_id", MASTER_OWNER_ID),
                             info.get("is_master", False))
            BOTS_BY_TOKEN[token] = ctx; BOTS_BY_USERNAME[un] = ctx; BOT_CONTEXTS.append(ctx)
            log.info(f"✅ Registered @{un}")
        except Exception as e:
            log.error(f"❌ Init fail {info.get('username', token[:20])}: {e}")

    started = []
    for ctx in BOT_CONTEXTS:
        try:
            await ctx.start(); started.append(ctx)
            log.info(f"🟢 @{ctx.username} started")
        except Exception as e:
            log.error(f"❌ Start fail @{ctx.username}: {e}")

    log.info(f"🚀 {len(started)} bot(s) running")
    await asyncio.Event().wait()

    for ctx in started:
        try: await ctx.stop()
        except: pass


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from callbacks import on_callback
from commands import cmd_admin, cmd_cancel, cmd_start, cmd_stock
from config import API_HASH, API_ID, BOT_TOKEN, log
from context import (
    BOTS_BY_TOKEN, BOTS_BY_USERNAME, BOT_CONTEXTS, BotContext, MASTER_OWNER_ID,
    _current_bot, fetch_bot_username, load_bots_config, save_bots_config
)
from lzt_api import cache_lzt_stock_loop
from miniapp_integration import cmd_app, set_bot_commands, set_menu_button   # ⭐ Mini App
from text_handlers import on_error, on_photo, on_text, on_video
from zip_upload import handle_document
