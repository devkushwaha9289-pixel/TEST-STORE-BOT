VILLAGEE SMS SHOP v28.1 — split source
======================================
Run:   pip install -r requirements.txt
       python main.py

main.py         entry point
config.py       all constants / tokens / limits / logging
emojis.py       premium emoji ids + EMOJI_MAP + emo()
countries.py    country codes helpers
context.py      multi-bot context, DB proxies, BotContext
database.py     schema + settings/user/admin helpers
utils.py        masks, slugs, order-id, UPI URL, QR
buttons.py      button + keyboard builders
rich_ui.py      rich message blocks/sender + deep-links
logs.py         log channel targets + all log_* functions
devices.py      device management + OTP sender
osint.py        OSINT admin API, settings view, OSINT purchase
backup.py       full ZIP backup/restore + JSON backup/restore
history.py      balance/section history
force_join.py   force-join checks
state.py        shared runtime state
lzt_api.py      Server 1 API layer
server1.py      SERVER 1 views + buy
server2.py      SERVER 2 views, purchase, admin S2
server3.py      SERVER 3 file/panel views, purchase, admin S3
fampay.py       FamPay email parser + IMAP poll
payments.py     UPI auto deposit, UTR/proof, referral, transfer
manual_upi.py   manual UPI flow
views.py        home/profile/balance/refer/support/recharge
admin_panel.py  admin panel views
admin_actions.py / admin_text.py   admin callbacks / admin text input
zip_upload.py   ZIP staging + document handler
bot_manager.py  multi-bot manager
broadcast.py    broadcasts
commands.py     /start /cancel /admin /stock + deep links
callbacks.py    main callback router
text_handlers.py text/photo/video/error handlers
runner.py       per-bot app + multi-bot runner

Note: cross-module imports sit at the BOTTOM of each file on purpose
(circular references between handlers/views resolve safely that way).

v28.5 — Mini App parity + Paytm fix
-----------------------------------
admin_text.py       FIX: SET PAYTM UPI / SET PAYTM MID now save (handler was missing)
miniapp_bridge.py   NEW: runs bot logic for Mini App (Paytm/FamPay/Manual deposit,
                    redeem, transfer, balance history, full admin API)
miniapp/server.py   new endpoints + ban/maintenance gate + server on/off checks
miniapp/static/*    Paytm Auto, Manual UTR submit, Redeem, Send Balance, Support,
                    Balance History, WhatsApp card and complete Admin Panel
