#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — context.py
Multi-bot context (contextvars, DB/cursor proxies, bot registry, BotContext).
"""

import os, json, asyncio, sqlite3, contextvars, aiohttp
from telegram import Update

# ============================================================
# MULTI-BOT CONTEXT
# ============================================================
MASTER_OWNER_ID = int(os.getenv("MASTER_OWNER_ID", "6698156001"))
BOTS_CONFIG_FILE = "bots_config.json"
_current_bot = contextvars.ContextVar('current_bot', default=None)

class _DBProxy:
    def __getattr__(self, n):
        c = _current_bot.get()
        if c is None: raise RuntimeError("No bot ctx")
        return getattr(c.db, n)
    def __setattr__(self, n, v):
        c = _current_bot.get()
        if c is None: raise RuntimeError("No bot ctx")
        setattr(c.db, n, v)

class _CurProxy:
    def __getattr__(self, n):
        c = _current_bot.get()
        if c is None: raise RuntimeError("No bot ctx")
        return getattr(c.cur, n)

db = _DBProxy()
cur = _CurProxy()

def current_ctx():
    c = _current_bot.get()
    if c is None: raise RuntimeError("No bot ctx")
    return c
def current_owner_id():
    c = _current_bot.get()
    return c.owner_id if c else MASTER_OWNER_ID
def current_bot_username():
    c = _current_bot.get()
    return c.username if c else "unknown"
def get_telethon():
    c = _current_bot.get()
    return c.telethon_client if c else None

BOTS_BY_TOKEN = {}
BOTS_BY_USERNAME = {}
BOT_CONTEXTS = []

def load_bots_config():
    if not os.path.exists(BOTS_CONFIG_FILE): return {"bots": {}}
    try:
        with open(BOTS_CONFIG_FILE, "r", encoding="utf-8") as f: cfg = json.load(f)
        if "bots" not in cfg: cfg["bots"] = {}
        return cfg
    except Exception as e:
        log.error(f"load_bots_config: {e}"); return {"bots": {}}

def save_bots_config(cfg):
    try:
        with open(BOTS_CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2)
    except Exception as e: log.error(f"save_bots_config: {e}")

async def fetch_bot_username(token):
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json()
                if d.get("ok"): return d["result"]["username"]
    except Exception as e: log.error(f"fetch_bot_username: {e}")
    return None


# ============================================================
# BOT CONTEXT
# ============================================================
class BotContext:
    def __init__(self, token, username, owner_id, is_master=False):
        self.token = token; self.username = username
        self.owner_id = int(owner_id); self.is_master = bool(is_master)
        self.data_dir = os.path.join("bots", username)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "sessions"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "downloads"), exist_ok=True)
        self.db_path = os.path.join(self.data_dir, OTP_DB_NAME)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL;")
        self.cur = self.db.cursor()
        self.app = None; self.telethon_client = None
        self.telethon_loop = None; self.fampay_task = None; self.started = False
        self.display_name = username
        self.report_task = None
        tok = _current_bot.set(self)
        try: _init_schema()
        finally: _current_bot.reset(tok)

    async def start(self):
        if self.started: return
        app = build_app_for_ctx(self); self.app = app
        await app.initialize()

        # Bot display name is fetched from the bot token (getMe) and stored for the Mini App.
        try:
            me = await app.bot.get_me()
            self.display_name = (me.first_name or me.username or self.username or "").strip()
            self.cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                             ("bot_display_name", self.display_name))
            self.cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                             ("bot_username_live", me.username or self.username or ""))
            self.db.commit()
        except Exception as e:
            log.warning(f"getMe @{self.username}: {e}")

        # =====================================================
        # AUTO MINI APP MENU BUTTON
        # Same effect as:
        # setChatMenuButton -> web_app -> https://test-store-bot-1.onrender.com
        # Applied automatically to every configured bot on startup.
        # =====================================================
        try:
            from miniapp_integration import set_bot_commands, set_menu_button
            await set_bot_commands(app)
            await set_menu_button(app, self.username)
            log.info(f"🛍️ Mini App menu + /commands set @{self.username}")
        except Exception as e:
            log.warning(f"⚠️ Mini App menu button @{self.username}: {e}")

        # Payment verification is handled by the external Vercel FamPay API.
        # No direct IMAP polling is started in the bot.
        self.fampay_task = None
        log.info(f"💳 FamPay verification via Vercel API @{self.username}")

        # Daily 7 PM IST statement (total selling + total deposit) to the owners.
        try:
            from daily_report import daily_statement_loop
            self.report_task = asyncio.create_task(daily_statement_loop(self))
        except Exception as e:
            log.warning(f"daily statement start @{self.username}: {e}")

        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        self.started = True

    async def stop(self):
        if not self.started: return
        if getattr(self, "report_task", None):
            try:
                self.report_task.cancel()
                await asyncio.gather(self.report_task, return_exceptions=True)
            except Exception:
                pass
            self.report_task = None
        if self.fampay_task:
            try:
                self.fampay_task.cancel()
                await asyncio.gather(self.fampay_task, return_exceptions=True)
            except Exception:
                pass
            self.fampay_task = None
        try: await self.app.updater.stop()
        except: pass
        try: await self.app.stop()
        except: pass
        try: await self.app.shutdown()
        except: pass
        if self.telethon_client:
            try: await self.telethon_client.disconnect()
            except: pass
        self.started = False

    def reopen_db(self):
        try:
            try: self.db.close()
            except: pass
        except: pass
        self.db = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL;")
        self.cur = self.db.cursor()


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from config import OTP_DB_NAME, log
from database import _init_schema
from runner import build_app_for_ctx
