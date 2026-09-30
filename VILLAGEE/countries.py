#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VILLAGEE SMS SHOP v28.1 — countries.py
Country calling-code table and country name <-> code helpers.
"""

import re

# ============================================================
# COUNTRY CODES
# ============================================================
COUNTRY_CODES = {
    '1':('United States','🇺🇸'),'7':('Russia','🇷🇺'),'20':('Egypt','🇪🇬'),
    '27':('South Africa','🇿🇦'),'31':('Netherlands','🇳🇱'),'32':('Belgium','🇧🇪'),
    '33':('France','🇫🇷'),'34':('Spain','🇪🇸'),'39':('Italy','🇮🇹'),
    '44':('UK','🇬🇧'),'46':('Sweden','🇸🇪'),'48':('Poland','🇵🇱'),
    '49':('Germany','🇩🇪'),'55':('Brazil','🇧🇷'),'60':('Malaysia','🇲🇾'),
    '61':('Australia','🇦🇺'),'62':('Indonesia','🇮🇩'),'63':('Philippines','🇵🇭'),
    '66':('Thailand','🇹🇭'),'84':('Vietnam','🇻🇳'),'86':('China','🇨🇳'),
    '90':('Turkey','🇹🇷'),'91':('India','🇮🇳'),'92':('Pakistan','🇵🇰'),
    '95':('Myanmar','🇲🇲'),'98':('Iran','🇮🇷'),'234':('Nigeria','🇳🇬'),
    '254':('Kenya','🇰🇪'),'380':('Ukraine','🇺🇦'),'880':('Bangladesh','🇧🇩'),
    '966':('Saudi Arabia','🇸🇦'),'971':('UAE','🇦🇪'),'964':('Iraq','🇮🇶'),
    '965':('Kuwait','🇰🇼'),'974':('Qatar','🇶🇦'),
}

def get_country_info(phone):
    phone = str(phone).replace(' ', '').replace('+', '')
    if not phone: return "Unknown", "🌍"
    for ln in (3, 2, 1):
        p = phone[:ln]
        if p in COUNTRY_CODES: return COUNTRY_CODES[p]
    return "Unknown", "🌍"


def country_name_to_code(name):
    if not name: return "xx"
    n = str(name).strip().lower()
    for k, v in LZT_COUNTRY_CATALOG.items():
        if k.lower() == n:
            return v[0].lower()
    m = {
        "india":"ind","in":"ind","myanmar":"mm","mm":"mm",
        "united states":"us","usa":"us","us":"us",
        "united kingdom":"uk","uk":"uk","gb":"uk",
        "bangladesh":"bd","bd":"bd","pakistan":"pk","pk":"pk",
        "russia":"ru","ru":"ru","nigeria":"ng","ng":"ng",
        "indonesia":"id","id":"id","philippines":"ph","ph":"ph",
        "vietnam":"vn","thailand":"th","malaysia":"my","china":"cn",
        "japan":"jp","brazil":"br","egypt":"eg","iraq":"iq","iran":"ir",
        "saudi arabia":"sa","uae":"ae","united arab emirates":"ae",
        "turkey":"tr","ukraine":"ua","kenya":"ke","south africa":"za",
        "netherlands":"nl","spain":"es","italy":"it","sweden":"se",
        "poland":"pl","germany":"de","france":"fr","australia":"au",
        "canada":"ca","mexico":"mx","argentina":"ar","colombia":"co",
        "chile":"cl","peru":"pe","morocco":"ma","nepal":"np",
        "sri lanka":"lk","singapore":"sg","south korea":"kr",
        "kazakhstan":"kz","uzbekistan":"uz","portugal":"pt","romania":"ro",
        "austria":"at","belgium":"be","hong kong":"hk",
    }
    if n in m: return m[n]
    return re.sub(r'[^a-z0-9]', '', n)[:3] or "xx"

def country_code_to_name(code):
    if not code: return None
    c = str(code).strip().lower()
    for k, v in LZT_COUNTRY_CATALOG.items():
        if v[0].lower() == c:
            return k
    m = {
        "ind":"India","in":"India","mm":"Myanmar","us":"United States","usa":"United States",
        "uk":"United Kingdom","gb":"United Kingdom","bd":"Bangladesh","pk":"Pakistan",
        "ru":"Russia","ng":"Nigeria","id":"Indonesia","ph":"Philippines","vn":"Vietnam",
        "th":"Thailand","my":"Malaysia","cn":"China","jp":"Japan","br":"Brazil",
        "eg":"Egypt","iq":"Iraq","ir":"Iran","sa":"Saudi Arabia","ae":"United Arab Emirates",
        "tr":"Turkey","ua":"Ukraine","ke":"Kenya","za":"South Africa","nl":"Netherlands",
        "es":"Spain","it":"Italy","se":"Sweden","pl":"Poland","de":"Germany","fr":"France",
        "au":"Australia","ca":"Canada","mx":"Mexico","ar":"Argentina","co":"Colombia",
        "cl":"Chile","pe":"Peru","ma":"Morocco","np":"Nepal","lk":"Sri Lanka",
        "sg":"Singapore","kr":"South Korea","kz":"Kazakhstan","uz":"Uzbekistan",
        "pt":"Portugal","ro":"Romania","at":"Austria","be":"Belgium","hk":"Hong Kong",
    }
    return m.get(c)


# ============================================================
# CROSS-MODULE IMPORTS (kept at bottom so circular references between
# modules resolve safely — every definition above already exists).
# ============================================================
from lzt_api import LZT_COUNTRY_CATALOG
