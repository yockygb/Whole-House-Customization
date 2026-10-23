# -*- coding: utf-8 -*-
"""
柜体名称中英对照
================
从原系统 cab_name_en.py 原样迁移。用户只写中文（「主卧鞋柜」），导出时自动给出英文。

规则
----
1. 词典 + 最长词优先：从左到右每次匹配最长的词，逐段拼英文。
2. 可组合：房间词 + 柜体词自由组合（主卧 / 鞋柜 → Master Bedroom Shoe Cabinet）。
3. 不瞎猜：出现词典里没有的字就返回空串，由界面提示用户手填英文。
4. 原样保留：本模块只产出英文，中文原值由调用方原封不动保存。
"""
from __future__ import annotations

import re
from typing import Dict

# —— 房间 / 位置词 ——
ROOM_WORDS: Dict[str, str] = {
    "主卧": "Master Bedroom",
    "次卧": "Second Bedroom",
    "儿童房": "Kids Room",
    "长辈房": "Elder Room",
    "卧室": "Bedroom",
    "客厅": "Living Room",
    "餐厅": "Dining Room",
    "厨房": "Kitchen",
    "玄关": "Entrance",
    "书房": "Study",
    "阳台": "Balcony",
    "衣帽间": "Walk-in Closet",
    "卫生间": "Bathroom",
    "浴室": "Bathroom",
    "洗衣房": "Laundry Room",
}

# —— 柜体 / 家具词 ——
CABINET_WORDS: Dict[str, str] = {
    "衣柜": "Wardrobe",
    "鞋柜": "Shoe Cabinet",
    "电视柜": "TV Cabinet",
    "书柜": "Bookcase",
    "储物柜": "Storage Cabinet",
    "餐边柜": "Sideboard",
    "酒柜": "Wine Cabinet",
    "高柜": "Tall Cabinet",
    "吊柜": "Wall Cabinet",
    "地柜": "Base Cabinet",
    "浴室柜": "Bathroom Vanity",
    "洗衣柜": "Laundry Cabinet",
    "展示柜": "Display Cabinet",
    "橱柜": "Kitchen Cabinet",
    "床头柜": "Bedside Table",
    "梳妆台": "Dressing Table",
    "书桌": "Desk",
    "书台": "Study Desk",
    "妆台": "Dressing Table",
    "妆柜": "Vanity Cabinet",
    "矮柜": "Low Cabinet",
    "岛台": "Kitchen Island",
    "阳台柜": "Balcony Cabinet",
    "榻榻米": "Tatami",
    "冰箱": "Fridge",
    # —— 常见但原词典没有的 ——
    "神台柜": "Altar Cabinet",
    "神台": "Altar Cabinet",
    "神龛": "Altar Cabinet",
    "佛龛": "Altar Cabinet",
    "供桌": "Altar Table",
    "玄关台": "Console Table",
    "屏风": "Divider Screen",
    "卡座": "Banquette",
    "楼梯柜": "Staircase Cabinet",
    "电视墙": "TV Wall",
    "护墙板": "Wall Panel",
    "木门": "Timber Door",
    "吧台": "Bar Counter",
    "地台": "Platform",
    "地柜组合": "Base Cabinet Set",
    "柜": "Cabinet",
}

DICT: Dict[str, str] = {**ROOM_WORDS, **CABINET_WORDS}

_CJK = re.compile(r"[\u4e00-\u9fff]")
_SEP = re.compile(r"[\s\-_/、,，.。·]+")
_TRAILING_CODE = re.compile(r"(?:\s+([A-Za-z])|([0-9]+))\s*$")


def _dictionary(glossary=None):
    out = dict(DICT)
    if isinstance(glossary, dict):
        out.update({str(k).strip(): str(v).strip() for k, v in glossary.items()
                    if str(k).strip() and str(v).strip()})
    return out


def _translate(raw, mapping):
    normalized = {_SEP.sub("", key).lower(): value for key, value in mapping.items()}
    keys = sorted(normalized, key=len, reverse=True)
    core = _SEP.sub("", raw).lower()
    if not core:
        return ""
    parts = []
    i = 0
    while i < len(core):
        match = next((key for key in keys if core.startswith(key, i)), None)
        if not match:
            return ""
        parts.extend(normalized[match].split())
        i += len(match)
    words = []
    for word in parts:
        if not words or words[-1].lower() != word.lower():
            words.append(word)
    return " ".join(words)


def translate_cabinet_name(name: str, glossary=None) -> str:
    """Translate a cabinet name in either direction; unknown text is not guessed."""
    raw = (name or "").strip()
    if not raw:
        return ""
    suffix = ""
    m = _TRAILING_CODE.search(raw)
    core = raw
    if m:
        suffix = m.group(1) or m.group(2)
        core = raw[:m.start()].strip()
    mapping = _dictionary(glossary)
    if _CJK.search(core):
        translated = _translate(core, mapping)
    else:
        reverse = {}
        for zh, en in mapping.items():
            reverse[en.lower()] = zh
        translated = _translate(core, reverse)
    return ("%s %s" % (translated, suffix)).strip() if translated and suffix else translated


def resolve_cabinet_name_en(cab_name: str, override: str = "", glossary=None) -> str:
    """Final English name, retaining saved legacy English overrides."""
    ov = (override or "").strip()
    if ov:
        return ov
    if not _CJK.search((cab_name or "").strip()):
        return (cab_name or "").strip()
    return translate_cabinet_name(cab_name, glossary)


def resolve_bilingual_cabinet_name(name: str, override: str = "", glossary=None):
    raw = (name or "").strip()
    if _CJK.search(raw):
        return resolve_cabinet_name_en(raw, override, glossary), raw
    en = (override or raw).strip()
    zh = translate_cabinet_name(raw, glossary)
    return en or raw, zh or raw


def bilingual_cab_name(cab_name: str, override: str = "") -> str:
    """「中文 / English」；没有英文时只给中文。"""
    zh = (cab_name or "").strip()
    en = resolve_cabinet_name_en(zh, override)
    if not zh:
        return en
    if not en or en.lower() == zh.lower():
        return zh
    return "%s / %s" % (zh, en)


def is_translatable(name: str, glossary=None) -> bool:
    """词典能否完整覆盖；界面用它决定提示「自动」还是「请手动填英文」。"""
    raw = (name or "").strip()
    if not raw:
        return False
    if not _CJK.search(raw):
        return True
    return bool(translate_cabinet_name(raw, glossary))
