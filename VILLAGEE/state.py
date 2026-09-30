#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — state.py
Shared in-memory runtime state (dicts/sets/locks).
"""

import asyncio

# ============================================================
# STATE
# ============================================================
active_orders = {}
deposit_input = {}
admin_dep_state = {}
user_spam = {}
custom_dep_amt = {}
temp_data = {}
user_locks = {}
waiting_proof = {}
waiting_utr = {}
cached_lzt_stock = {}
cached_lzt_stock_at = {}
active_filter_keys = {"no_no_1_any_any"}
active_lzt_cache_targets = set()
active_lzt_stock_requests = {}
cached_lzt_stock_responses = {}
cached_lzt_stock_response_at = {}
user_lzt_filters = {}
user_refresh_cooldown = {}
user_lzt_purchases = {}
lzt_search_state = {}

DEFAULT_FILTER_FKEY = "no_no_1_any_any"

zip_staging = {}

# ⭐ v28.1 — Manual UPI state
manual_upi_pending = {}         # {uid: {'order_id', 'amount', 'utr', 'proof_file_id'}}
manual_upi_owner_state = {}     # {owner_uid: {'order_id', 'action': 'reject_reason'|'change_amount', 'val'}}

def get_user_lock(uid):
    if uid not in user_locks: user_locks[uid] = asyncio.Lock()
    return user_locks[uid]

def user_has_active_operation(uid):
    return any(uid in d for d in [deposit_input, temp_data, waiting_proof,
                                   admin_dep_state, custom_dep_amt, waiting_utr,
                                   manual_upi_pending])

def clear_user_operations(uid):
    for d in [deposit_input, temp_data, waiting_proof, admin_dep_state, custom_dep_amt, waiting_utr]:
        d.pop(uid, None)
