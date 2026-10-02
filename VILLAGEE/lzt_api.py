#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — lzt_api.py
LZT Market API layer: rate-limit, sessions, requests, filters, pricing, OTP.
"""

import re, time, asyncio, socket, aiohttp
from datetime import datetime, timezone

# Runtime state that is RE-ASSIGNED via `global` — it must live in the same module
# as the functions that assign it (Python `from x import y` would copy the value).
_lzt_missing_logged = False
_lzt_session = None
_lzt_rate_lock = asyncio.Lock()
_lzt_last_request_at = 0.0
_lzt_blocked_until = 0.0

def reset_lzt_missing_logged():
    """Used by admin text handler (other module) to reset the flag."""
    global _lzt_missing_logged
    _lzt_missing_logged = False

# ============================================================
# LZT
# ============================================================
LZT_COUNTRY_CATALOG = {
    "Argentina": ("AR","🇦🇷","54"),"Australia": ("AU","🇦🇺","61"),"Austria": ("AT","🇦🇹","43"),
    "Bangladesh": ("BD","🇧🇩","880"),"Belgium": ("BE","🇧🇪","32"),"Brazil": ("BR","🇧🇷","55"),
    "Canada": ("CA","🇨🇦","1"),"Chile": ("CL","🇨🇱","56"),"China": ("CN","🇨🇳","86"),
    "Colombia": ("CO","🇨🇴","57"),"Egypt": ("EG","🇪🇬","20"),"France": ("FR","🇫🇷","33"),
    "Germany": ("DE","🇩🇪","49"),"Hong Kong": ("HK","🇭🇰","852"),"India": ("IN","🇮🇳","91"),
    "Indonesia": ("ID","🇮🇩","62"),"Iran": ("IR","🇮🇷","98"),"Iraq": ("IQ","🇮🇶","964"),
    "Italy": ("IT","🇮🇹","39"),"Japan": ("JP","🇯🇵","81"),"Kazakhstan": ("KZ","🇰🇿","7"),
    "Kenya": ("KE","🇰🇪","254"),"Malaysia": ("MY","🇲🇾","60"),"Mexico": ("MX","🇲🇽","52"),
    "Morocco": ("MA","🇲🇦","212"),"Nepal": ("NP","🇳🇵","977"),"Netherlands": ("NL","🇳🇱","31"),
    "Nigeria": ("NG","🇳🇬","234"),"Pakistan": ("PK","🇵🇰","92"),"Peru": ("PE","🇵🇪","51"),
    "Philippines": ("PH","🇵🇭","63"),"Poland": ("PL","🇵🇱","48"),"Portugal": ("PT","🇵🇹","351"),
    "Romania": ("RO","🇷🇴","40"),"Russia": ("RU","🇷🇺","7"),"Saudi Arabia": ("SA","🇸🇦","966"),
    "Singapore": ("SG","🇸🇬","65"),"South Africa": ("ZA","🇿🇦","27"),"South Korea": ("KR","🇰🇷","82"),
    "Spain": ("ES","🇪🇸","34"),"Sri Lanka": ("LK","🇱🇰","94"),"Thailand": ("TH","🇹🇭","66"),
    "Turkey": ("TR","🇹🇷","90"),"Ukraine": ("UA","🇺🇦","380"),
    "United Arab Emirates": ("AE","🇦🇪","971"),"United Kingdom": ("GB","🇬🇧","44"),
    "United States": ("US","🇺🇸","1"),"Uzbekistan": ("UZ","🇺🇿","998"),"Vietnam": ("VN","🇻🇳","84"),
}

def resolve_lzt_token():
    e = (LZT_TOKEN or "").strip()
    if e: return e
    try:
        row = cur.execute("SELECT value FROM settings WHERE key='lzt_token'").fetchone()
        if row and str(row[0]).strip(): return str(row[0]).strip()
    except: pass
    return ""

def get_user_daybreak(uid):
    try:
        v = get_setting(f"lzt_daybreak_{uid}", "")
        if v:
            n = int(v)
            if n in DAYBREAK_OPTIONS: return n
    except: pass
    try:
        v2 = get_setting("lzt_default_daybreak", str(DEFAULT_DAYBREAK))
        n2 = int(v2)
        if n2 in DAYBREAK_OPTIONS: return n2
    except: pass
    return DEFAULT_DAYBREAK

def set_user_daybreak(uid, value):
    try: n = int(value)
    except: n = DEFAULT_DAYBREAK
    if n not in DAYBREAK_OPTIONS: n = DEFAULT_DAYBREAK
    set_setting(f"lzt_daybreak_{uid}", str(n))

def lzt_item_last_edited_ts(item):
    """Return the listing's last-edited timestamp as Unix seconds.

    Primary LZT field: edit_date. Several fallback field names are supported
    for compatibility with older API responses.
    """
    if not isinstance(item, dict):
        return None

    value = None
    for field in ("edit_date",) + tuple(LAST_EDIT_FIELD_CANDIDATES):
        candidate = item.get(field)
        if candidate not in (None, "", 0, "0", False):
            value = candidate
            break

    if value is None:
        return None

    try:
        if isinstance(value, (int, float)):
            ts = float(value)
        else:
            raw = str(value).strip()
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = dt.timestamp()
            except Exception:
                ts = float(raw)

        if ts > 1e12:
            ts /= 1000.0

        return ts if ts > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def lzt_item_last_edited_age_seconds(item, now=None):
    ts = lzt_item_last_edited_ts(item)
    if ts is None:
        return None

    current = float(time.time() if now is None else now)
    age = current - ts

    if age < 0:
        return None

    return age


def lzt_item_age_seconds(item):
    # Backward-compatible name used by the existing UI.
    return lzt_item_last_edited_age_seconds(item)


def lzt_item_is_eligible(item):
    """Eligible only when listing last-edited age is > 86400 seconds."""
    age = lzt_item_last_edited_age_seconds(item)
    if age is None:
        return (False, None)

    return (age > LAST_EDIT_MIN_AGE_SECONDS), age


def lzt_currency_to_inr_rate(currency):
    c = str(currency or LZT_PRICE_CURRENCY).strip().lower()
    if c == "usd": return get_rate()
    defaults = {"rub":1.05,"eur":100.0,"gbp":118.0,"cny":13.0,"uah":2.3,
                "kzt":0.2,"byn":29.0,"try":2.9,"jpy":0.62,"brl":17.0}
    try:
        row = cur.execute("SELECT value FROM settings WHERE key=?", (f"{c}_inr_rate",)).fetchone()
        return float(row[0]) if row and row[0] else defaults.get(c, 1.05)
    except: return defaults.get(c, 1.05)

def lzt_price_currency(item):
    if isinstance(item, dict):
        for k in ("currency","price_currency","priceCurrency","currency_code","currencyCode"):
            v = item.get(k)
            if v: return str(v).strip().lower()
        pd = item.get("price_data") or item.get("priceData")
        if isinstance(pd, dict):
            for k in ("currency","currency_code","currencyCode"):
                v = pd.get(k)
                if v: return str(v).strip().lower()
    return LZT_PRICE_CURRENCY

def lzt_price_breakdown(item, markup_percent):
    rp = item.get("price_with_fee") or item.get("priceWithSellerFee") or item.get("price") or 0
    try: mp = float(rp)
    except: mp = 0.0
    c = lzt_price_currency(item)
    inr_base = mp * lzt_currency_to_inr_rate(c)
    try: markup_percent = int(float(markup_percent))
    except: markup_percent = 20
    markup = max(0, int(round(inr_base * (markup_percent / 100))))
    base = max(0, int(round(inr_base)))
    return {"market_price":mp,"currency":c.upper(),"base_inr":base,
            "markup_percent":markup_percent,"markup_inr":markup,"final_inr":max(1, base+markup)}

def lzt_final_inr_price(item, markup): return lzt_price_breakdown(item, markup)["final_inr"]

def get_lzt_markup(country_name):
    cs = [country_name]
    if country_name in LZT_COUNTRY_CATALOG:
        iso = LZT_COUNTRY_CATALOG[country_name][0]
        cs.extend([iso, iso.upper()])
    row = None
    for c in dict.fromkeys(cs):
        row = cur.execute("SELECT markup_percent FROM lzt_settings WHERE LOWER(country)=LOWER(?)", (c,)).fetchone()
        if row: break
    if not row:
        row = cur.execute("SELECT value FROM settings WHERE key='lzt_global_markup'").fetchone()
    try: return int(float(row[0])) if row else 20
    except: return 20

def clear_lzt_cache():
    cached_lzt_stock.clear(); cached_lzt_stock_at.clear()
    cached_lzt_stock_responses.clear(); cached_lzt_stock_response_at.clear()

def clean_lzt_params(params):
    if not params: return None
    clean = {}
    for k, v in params.items():
        if k is None or v is None: continue
        if isinstance(v, (list, tuple)):
            cl = [str(i) for i in v if i is not None]
            if cl: clean[str(k)] = cl
        else: clean[str(k)] = str(v)
    return clean or None

def parse_lzt_retry_after(headers):
    if not headers: return None
    try: raw = headers.get("Retry-After")
    except: raw = None
    if not raw: return None
    try: return max(0.0, float(raw))
    except: pass
    try:
        ra = datetime.strptime(str(raw), "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
        return max(0.0, (ra - datetime.now(timezone.utc)).total_seconds())
    except: return None

def parse_lzt_retry_after_body(text):
    if not text: return None
    m = re.search(r"(\d+)\s*minute", str(text), re.IGNORECASE)
    if m: return float(m.group(1)) * 60
    m = re.search(r"(\d+)\s*second", str(text), re.IGNORECASE)
    if m: return float(m.group(1))
    return None

async def wait_lzt_rate_limit():
    global _lzt_last_request_at
    async with _lzt_rate_lock:
        now = time.monotonic()
        bw = max(0.0, _lzt_blocked_until - now)
        sw = max(0.0, LZT_MIN_REQUEST_INTERVAL - (now - _lzt_last_request_at))
        w = max(bw, sw)
        if w > 0: await asyncio.sleep(w)
        _lzt_last_request_at = time.monotonic()

async def apply_lzt_rate_limit_cooldown(retry_after=None):
    global _lzt_blocked_until
    wf = max(float(retry_after or 0), LZT_RATE_LIMIT_COOLDOWN)
    _lzt_blocked_until = max(_lzt_blocked_until, time.monotonic() + wf)
    return wf

async def get_lzt_session():
    global _lzt_session
    cl = asyncio.get_running_loop()
    sl = getattr(_lzt_session, "_loop", None) if _lzt_session is not None else None
    if _lzt_session is None or _lzt_session.closed or sl is not cl:
        if _lzt_session is not None and not _lzt_session.closed:
            await close_lzt_session()
        ck = {"limit":5,"ttl_dns_cache":300,"keepalive_timeout":30,"enable_cleanup_closed":True}
        if LZT_FORCE_IPV4: ck["family"] = socket.AF_INET
        _lzt_session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(**ck), trust_env=True)
    return _lzt_session

async def close_lzt_session():
    global _lzt_session
    if _lzt_session is not None and not _lzt_session.closed:
        await _lzt_session.close()
    _lzt_session = None

async def lzt_request(method, endpoint, params=None, data=None, return_error=False,
                      timeout_total=None, max_retries=None, notify_errors=True):
    global _lzt_missing_logged
    tok_res = resolve_lzt_token()
    if not tok_res:
        if not _lzt_missing_logged:
            _lzt_missing_logged = True
            log.error("S1 token missing for %s %s", method, endpoint)
        return None
    tok = tok_res.replace("Bearer ", "").strip()
    method = str(method or "GET").upper()
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json",
               "Content-Type": "application/json", "User-Agent": "VillageeShopBot/1.0"}
    if not endpoint.startswith("/"): endpoint = "/" + endpoint
    url = f"{LZT_BASE_URL}{endpoint}"
    params = clean_lzt_params(params)
    is_stock = method == 'GET' and endpoint == '/telegram'
    if max(0.0, _lzt_blocked_until - time.monotonic()) > 0:
        if return_error: return {"error":"rate limited","http_status":429,
                                 "retry_after":max(0.0, _lzt_blocked_until-time.monotonic())}
        return None
    to = timeout_total if timeout_total is not None else (LZT_STOCK_TIMEOUT if is_stock else LZT_REQUEST_TIMEOUT)
    mr = max(1, int(max_retries if max_retries is not None else (LZT_STOCK_RETRIES if is_stock else LZT_MAX_RETRIES)))
    timeout = aiohttp.ClientTimeout(total=float(to), connect=min(2.0, float(to)),
                                     sock_connect=min(2.0, float(to)), sock_read=float(to))
    last_d = ""
    try:
        s = await get_lzt_session()
        for attempt in range(1, mr + 1):
            try:
                rk = {"headers": headers, "params": params, "timeout": timeout}
                if LZT_PROXY: rk["proxy"] = LZT_PROXY
                if method == 'POST':
                    rk["json"] = data; req = s.post(url, **rk)
                elif method == 'GET': req = s.get(url, **rk)
                else: return None
                await wait_lzt_rate_limit()
                async with req as r:
                    try: text = await r.text()
                    except Exception as ex:
                        last_d = f"{type(ex).__name__}: {ex!r}"
                        if attempt < mr: await asyncio.sleep(0.15*attempt); continue
                        break
                    if r.status >= 500 and attempt < mr:
                        await asyncio.sleep(0.25*attempt); continue
                    if r.status == 429:
                        ra = parse_lzt_retry_after(r.headers) or parse_lzt_retry_after_body(text)
                        wf = await apply_lzt_rate_limit_cooldown(ra)
                        if return_error:
                            try: err = await r.json(content_type=None)
                            except: err = {"error": text or "rate limited"}
                            if not isinstance(err, dict): err = {"error": str(err)}
                            err["http_status"] = r.status; err["retry_after"] = wf
                            return err
                        return None
                    if r.status >= 400:
                        if return_error:
                            try: err = await r.json(content_type=None)
                            except: err = {"error": text}
                            if not isinstance(err, dict): err = {"error": str(err)}
                            err["http_status"] = r.status
                            return err
                        return None
                    try: return await r.json(content_type=None)
                    except Exception as ex:
                        last_d = f"{type(ex).__name__}: {ex!r}"; return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_d = f"{type(e).__name__}: {e!r}"
                if isinstance(e, (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError,
                                  aiohttp.ClientOSError)):
                    await close_lzt_session(); s = await get_lzt_session()
                if attempt < mr: await asyncio.sleep(0.15*attempt); continue
        if return_error: return {"error": last_d, "exception": last_d.split(':', 1)[0]}
        return None
    except Exception as e:
        detail = f"{type(e).__name__}: {e!r}"
        if return_error: return {"error": detail, "exception": type(e).__name__}
        return None

def lzt_stock_request_key(params):
    clean = clean_lzt_params(params) or {}
    items = []
    for k, v in sorted(clean.items()):
        items.append((k, tuple(v) if isinstance(v, list) else v))
    return tuple(items)

def lzt_is_rate_limited_response(res):
    return isinstance(res, dict) and int(res.get("http_status") or 0) == 429

def lzt_retry_after_text(res):
    if not lzt_is_rate_limited_response(res): return "a few minutes"
    try: sec = max(0, int(float(res.get("retry_after") or 0)))
    except: sec = 0
    if sec <= 0: return "a few minutes"
    m = max(1, (sec + 59) // 60)
    return f"~{m} min"

def lzt_rate_limited_message(res=None):
    return f"{emo('⚠️')} <b>Stock refresh limited.</b>\n\nShowing cached. Try again in {lzt_retry_after_text(res)}."

async def fetch_lzt_stock_response(params, timeout_total=None, max_retries=None):
    key = lzt_stock_request_key(params)
    now = time.monotonic()
    cached = cached_lzt_stock_responses.get(key)
    cat = cached_lzt_stock_response_at.get(key, 0.0)
    if cached is not None and now - cat <= STOCK_CACHE_TTL: return cached
    existing = active_lzt_stock_requests.get(key)
    if existing and not existing.done(): return await existing
    async def _fetch():
        res = await lzt_request('GET', '/telegram', params=params,
                                timeout_total=timeout_total or LZT_STOCK_TIMEOUT,
                                max_retries=max_retries if max_retries is not None else LZT_STOCK_RETRIES,
                                notify_errors=False, return_error=True)
        if isinstance(res, dict) and 'items' in res:
            cached_lzt_stock_responses[key] = res
            cached_lzt_stock_response_at[key] = time.monotonic()
        elif lzt_is_rate_limited_response(res) and cached is not None: return cached
        return res
    task = asyncio.create_task(_fetch())
    active_lzt_stock_requests[key] = task
    try: return await task
    finally:
        if active_lzt_stock_requests.get(key) is task: active_lzt_stock_requests.pop(key, None)

def as_boolish(v):
    if isinstance(v, bool): return v
    if v is None: return False
    if isinstance(v, (int, float)): return v not in (0, -1)
    return str(v).strip().lower() in ("1","true","yes","y","on")

def lzt_item_has_spam(item):
    if not isinstance(item, dict): return False
    v = item.get("telegram_spam_block", item.get("spam", -1))
    return str(v) not in ("-1","0","False","false","None","")

def lzt_item_has_premium(item):
    return as_boolish(item.get("telegram_premium", item.get("premium"))) if isinstance(item, dict) else False

def lzt_item_has_mail(item):
    if not isinstance(item, dict): return False
    return as_boolish(item.get("login_mail", item.get("email", item.get("has_email", item.get("telegram_email")))))

def lzt_item_has_geoblock(item):
    if not isinstance(item, dict): return False
    return as_boolish(item.get("telegram_geo_block", item.get("geo_block", item.get("geoblock"))))

def lzt_item_matches_filters(item, flt):
    sp = flt.get("spam","any")
    if sp != "any":
        hs = lzt_item_has_spam(item)
        if sp == "no" and hs: return False
        if sp == "yes" and not hs: return False
    pp = flt.get("premium","any")
    if pp != "any":
        hp = lzt_item_has_premium(item)
        if pp == "yes" and not hp: return False
        if pp == "no" and hp: return False
    gp = flt.get("geoblock","any")
    if gp != "any":
        hg = lzt_item_has_geoblock(item)
        if gp == "no" and hg: return False
        if gp == "yes" and not hg: return False
    mp = flt.get("login_mail","any")
    if mp != "any":
        hm = lzt_item_has_mail(item)
        if mp == "yes" and not hm: return False
        if mp == "no" and hm: return False
    return True

def filter_lzt_items(items, flt): return [i for i in items if lzt_item_matches_filters(i, flt)]

def filter_lzt_eligible(items):
    out = []
    for it in items:
        ok, _ = lzt_item_is_eligible(it)
        if ok: out.append(it)
    return out

def get_user_filters(uid):
    db_db = str(get_user_daybreak(uid))
    default = {"spam":"any","geoblock":"no","offline":db_db,"login_mail":"any","premium":"any","sort":"az"}
    if uid not in user_lzt_filters: user_lzt_filters[uid] = default.copy()
    else:
        for k, v in default.items(): user_lzt_filters[uid].setdefault(k, v)
        user_lzt_filters[uid]["offline"] = db_db
    return user_lzt_filters[uid]

def get_filter_key(flt):
    return "_".join(str(flt.get(k,"any")) for k in ("spam","geoblock","offline","login_mail","premium"))

def _safe_daybreak(v):
    try: n = int(v)
    except: return DEFAULT_DAYBREAK
    return n if n in DAYBREAK_OPTIONS else DEFAULT_DAYBREAK

async def cache_lzt_stock_loop():
    global cached_lzt_stock
    sem = asyncio.Semaphore(max(1, LZT_CACHE_CONCURRENCY))
    async def fetch_and_cache(cn, fkey):
        async with sem:
            try:
                parts = fkey.split("_")
                sp, gb, off, lm, pr = parts[0],parts[1],parts[2],parts[3],parts[4]
                iso = LZT_COUNTRY_CATALOG.get(cn, ("US","🇺🇸","1"))[0]
                dbv = _safe_daybreak(off)
                params = {"country[]":iso,"spam":sp if sp != "any" else None,
                          "nsb":1,"pmin":0.01,"pmax":1000,"page":1,"per_page":40,
                          "password":"no","currency":LZT_PRICE_CURRENCY,"daybreak":dbv}
                if pr != "any": params["premium"] = pr
                res = await fetch_lzt_stock_response(params, timeout_total=LZT_STOCK_TIMEOUT,
                                                       max_retries=LZT_STOCK_RETRIES)
                if fkey not in cached_lzt_stock: cached_lzt_stock[fkey] = {}
                if res and 'items' in res:
                    flt = {"spam":sp,"geoblock":gb,"offline":str(dbv),
                           "login_mail":lm,"premium":pr}
                    filtered = filter_lzt_eligible(filter_lzt_items(res.get('items',[]), flt))
                    if not filtered: cached_lzt_stock[fkey][cn] = (0, 0.0)
                    else:
                        cheapest = min(filtered, key=lambda x: float(x.get('price') or 99999))
                        fp = lzt_final_inr_price(cheapest, get_lzt_markup(cn))
                        cached_lzt_stock[fkey][cn] = (len(filtered), fp)
                    cached_lzt_stock_at.setdefault(fkey, {})[cn] = time.monotonic()
            except: pass
    while True:
        try:
            keys = list(active_filter_keys)
            batch = max(1, LZT_CACHE_BATCH_SIZE // max(1, len(keys)))
            tgts = list(active_lzt_cache_targets)[:batch]
            if not tgts:
                await asyncio.sleep(max(5, LZT_CACHE_IDLE_SECONDS)); continue
            for c in tgts: active_lzt_cache_targets.discard(c)
            await asyncio.gather(*[fetch_and_cache(c, k) for k in keys for c in tgts])
        except Exception as e: log.error(f"cache loop: {e}")
        await asyncio.sleep(max(5, LZT_CACHE_IDLE_SECONDS))

def lzt_market_price(item):
    if not isinstance(item, dict): return None
    try:
        p = float(item.get("price_with_fee") or item.get("priceWithSellerFee") or item.get("price"))
        return p if p > 0 else None
    except: return None

def lzt_item_requires_password(item):
    if not isinstance(item, dict): return False
    for k in ("password","login_password","telegram_password","telegram_login_password",
              "has_password","hasPassword","twofa","two_fa","2fa"):
        v = item.get(k)
        if v in (None, "", 0, "0", False, "None", "none", "no", "NO"): continue
        return True
    return False

def lzt_item_country_name(item, fallback=None):
    if isinstance(item, dict):
        for k in ("country","telegram_country","country_name","countryName"):
            v = item.get(k)
            if v:
                v = str(v).strip()
                for name, (iso, _f, _c) in LZT_COUNTRY_CATALOG.items():
                    if v.lower() in (name.lower(), iso.lower()): return name
        phone = item.get("phone") or item.get("telegram_phone") or item.get("login")
        if phone: return get_country_info(str(phone))[0]
    return fallback or "Unknown"

def lzt_error_text(res):
    if not isinstance(res, dict): return str(res or "")
    return " | ".join(str(res[k]) for k in ("error","errors","error_description","message","detail") if res.get(k))

def lzt_purchase_has_error(res):
    if not res: return True
    if not isinstance(res, dict): return False
    return any(res.get(k) for k in ("error","errors","error_description"))

def lzt_purchase_item_id(res, fb):
    if isinstance(res, dict):
        item = res.get("item") or res.get("account") or res.get("telegram")
        if isinstance(item, dict): return str(item.get("item_id") or item.get("id") or fb)
        for k in ("item_id","id"):
            if res.get(k): return str(res.get(k))
    return str(fb)

def lzt_updated_market_price_from_error(res):
    m = re.search(r"costs now\s+([0-9]+(?:\.[0-9]+)?)", lzt_error_text(res), re.IGNORECASE)
    if m:
        try: return float(m.group(1))
        except: return None
    return None

def lzt_should_retry_purchase(res):
    t = lzt_error_text(res).lower()
    return "retry_request" in t or "retry request" in t

async def lzt_fast_buy_item(item_id, market_price):
    cp = market_price; last = None
    for attempt in range(1, max(1, LZT_FAST_BUY_RETRIES) + 1):
        body = {"price": cp} if cp is not None else None
        last = await lzt_request('POST', f"/{item_id}/fast-buy",
                                 params={"currency": LZT_PRICE_CURRENCY}, data=body, return_error=True)
        if last and not lzt_purchase_has_error(last): return last
        updated = lzt_updated_market_price_from_error(last)
        if updated and updated > 0:
            cp = updated; await asyncio.sleep(0.5); continue
        if not lzt_should_retry_purchase(last): return last
        await asyncio.sleep(min(3, 0.5 + (attempt * 0.1)))
    return last

def normalize_lzt_phone(raw, fb):
    p = str(raw or "").strip()
    if not p or p.startswith("LZT_"): return f"Hidden-{fb}"
    c = p.replace(" ", "")
    return f"+{c.lstrip('+')}" if c.lstrip("+").isdigit() else p

async def try_lzt_reset_authorizations(item_id, attempts=None, wait=None):
    att = max(1, attempts if attempts is not None else LZT_RESET_AUTH_RETRIES)
    w = max(0.0, wait if wait is not None else LZT_RESET_AUTH_WAIT)
    last_err = ""
    for i in range(1, att + 1):
        try:
            res = await lzt_request(
                'POST', f"/{item_id}/telegram-reset-authorizations",
                timeout_total=15, max_retries=2, return_error=True
            )
            if isinstance(res, dict):
                if res.get('errors') or res.get('error') or res.get('error_description'):
                    last_err = lzt_error_text(res) or str(res)
                    log.warning(f"reset_auth attempt {i}/{att} failed {item_id}: {last_err}")
                else:
                    log.info(f"✅ reset_auth OK for {item_id}")
                    return True, ""
            else:
                last_err = f"Unexpected response type: {type(res).__name__}"
                log.warning(f"reset_auth attempt {i}/{att} {item_id}: {last_err}")
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            log.error(f"reset_auth exception {i}/{att} {item_id}: {last_err}")
        if i < att: await asyncio.sleep(w * i)
    return False, last_err

async def get_verified_lzt_otp(item_id, attempts=3, delay=1.5):
    def collect(v, pk="", cands=None, d=0):
        if cands is None: cands = []
        if v is None or d > 8: return cands
        trusted = {"code","otp","login_code","telegram_login_code","telegramLoginCode"}
        texts = {"message","text","sms","telegram_message"}
        cont = {"data","item","telegram","response","result","codes"}
        kn = str(pk or "")
        if isinstance(v, dict):
            for k, n in v.items():
                ks = str(k)
                if ks in trusted or ks in texts: collect(n, ks, cands, d+1)
                elif ks in cont: collect(n, ks, cands, d+1)
            return cands
        if isinstance(v, (list, tuple)):
            if kn in cont or kn in trusted or kn in texts:
                for i in v: collect(i, kn, cands, d+1)
            return cands
        if kn not in trusted and kn not in texts and kn != "codes": return cands
        tv = str(v)
        if "login detected" in tv.lower(): return cands
        m = re.search(OTP_REGEX, tv)
        if m:
            prio = 100 if kn in trusted else 50
            cands.append((0, prio, m.group(0)))
        return cands
    def extract(res):
        c = collect(res)
        if not c: return None
        c.sort(key=lambda i: (i[0], i[1]), reverse=True)
        return c[0][2]
    seen = []; last = None
    for _ in range(max(1, attempts)):
        res = await lzt_request('GET', f"/{item_id}/telegram-login-code")
        last = res
        code = extract(res)
        if code:
            seen.append(code)
            if seen.count(code) >= 2 or attempts == 1: return code, True, res
        await asyncio.sleep(delay)
    return (seen[-1], False, last) if seen else (None, False, last)

def country_slug(name): return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def find_country_by_slug(slug):
    n = slug.strip().lower().replace("_", "-")
    for name in LZT_COUNTRY_CATALOG:
        if country_slug(name) == n: return name
    matches = find_country_matches(n.replace("-", " "))
    return matches[0] if matches else None

def get_country_button_code(name):
    if name == "India": return "IND"
    return LZT_COUNTRY_CATALOG.get(name, ("","",""))[0] or name[:3].upper()

def country_button_label(name, price_text=None, include_phone=True):
    iso, flag, call = LZT_COUNTRY_CATALOG.get(name, ("","🌍",""))
    short = get_country_button_code(name)
    parts = [flag, short]
    if include_phone and call: parts.append(f"+{call}")
    label = " ".join(parts)
    if price_text is not None: label = f"{label} | {price_text}"
    return label

def find_country_matches(query):
    q = query.strip().lower().replace("+", "")
    if not q: return []
    exact, partial = [], []
    for name, (iso, flag, call) in LZT_COUNTRY_CATALOG.items():
        tokens = {name.lower(), iso.lower(), call.lower()}
        if q in tokens or (q.isdigit() and call.startswith(q)): exact.append(name)
        elif q in name.lower() or iso.lower().startswith(q) or (q.isdigit() and q in call): partial.append(name)
    return sorted(dict.fromkeys(exact + partial))

def resolve_lzt_user_refresh(uid, key):
    now = time.monotonic(); ck = (uid, key)
    last = user_refresh_cooldown.get(ck, 0.0)
    rem = USER_REFRESH_COOLDOWN - (now - last)
    if rem > 0: return rem
    user_refresh_cooldown[ck] = now
    return 0.0


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from config import (
    DAYBREAK_OPTIONS, DEFAULT_DAYBREAK, LAST_EDIT_MIN_AGE_SECONDS,
    LAST_EDIT_FIELD_CANDIDATES, LZT_BASE_URL, LZT_CACHE_BATCH_SIZE, LZT_CACHE_CONCURRENCY,
    LZT_CACHE_IDLE_SECONDS, LZT_FAST_BUY_RETRIES, LZT_FORCE_IPV4, LZT_MAX_RETRIES,
    LZT_MIN_REQUEST_INTERVAL, LZT_PRICE_CURRENCY, LZT_PROXY, LZT_RATE_LIMIT_COOLDOWN,
    LZT_REQUEST_TIMEOUT, LZT_RESET_AUTH_RETRIES, LZT_RESET_AUTH_WAIT, LZT_STOCK_RETRIES,
    LZT_STOCK_TIMEOUT, LZT_TOKEN, OTP_REGEX, STOCK_CACHE_TTL, USER_REFRESH_COOLDOWN, log
)
from context import cur
from countries import get_country_info
from database import get_rate, get_setting, set_setting
from emojis import emo
from state import (
    active_filter_keys, active_lzt_cache_targets, active_lzt_stock_requests,
    cached_lzt_stock, cached_lzt_stock_at, cached_lzt_stock_response_at,
    cached_lzt_stock_responses, user_lzt_filters, user_refresh_cooldown
)
