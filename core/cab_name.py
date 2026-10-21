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
from typing import Dict, List, Optional

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
    "榻榻米": "Tatami",
    "冰箱": "Fridge",
    # —— 常见但原词典没有的 ——
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

# 长词优先：3 字词排在 2 字词前面，保证「储物柜」不被拆开
_KEYS: List[str] = sorted(DICT, key=len, reverse=True)

_CJK = re.compile(r"[\u4e00-\u9fff]")
_SEP = re.compile(r"[\s\-_/、,，.。·]+")
_TRAILING_CODE = re.compile(r"\s*([0-9]+|[A-Za-z])\s*$")


def _segment(core: str) -> Optional[List[str]]:
    """最长词优先切分；有任何一个字切不出来就返回 None（不猜）。"""
    out: List[str] = []
    i = 0
    n = len(core)
    while i < n:
        for k in _KEYS:
            if core.startswith(k, i):
                out.append(k)
                i += len(k)
                break
        else:
            return None
    return out


def translate_cabinet_name(name: str) -> str:
    """中文柜体名 → 英文；无法可靠翻译时返回 ""（不是瞎猜）。"""
    raw = (name or "").strip()
    if not raw:
        return ""
    # 已经是英文（没有汉字）：原样返回，避免「Shoe Cabinet / Shoe Cabinet」
    if not _CJK.search(raw):
        return raw

    suffix = ""
    m = _TRAILING_CODE.search(raw)
    core = raw
    if m:
        suffix = m.group(1)
        core = raw[:m.start()].strip()
    core = _SEP.sub("", core)          # 「主卧 衣柜」「主卧-衣柜」都能认
    if not core:
        return ""
    parts = _segment(core)
    if parts is None:
        return ""
    words: List[str] = []
    for p in parts:
        for w in DICT[p].split():
            # 「厨房橱柜」→ Kitchen + Kitchen Cabinet，去掉重复的 Kitchen
            if words and words[-1].lower() == w.lower():
                continue
            words.append(w)
    en = " ".join(words)
    return ("%s %s" % (en, suffix)).strip() if suffix else en


def resolve_cabinet_name_en(cab_name: str, override: str = "") -> str:
    """最终英文名：手动覆盖优先，否则自动翻译。"""
    ov = (override or "").strip()
    if ov:
        return ov
    return translate_cabinet_name(cab_name)


def bilingual_cab_name(cab_name: str, override: str = "") -> str:
    """「中文 / English」；没有英文时只给中文。"""
    zh = (cab_name or "").strip()
    en = resolve_cabinet_name_en(zh, override)
    if not zh:
        return en
    if not en or en.lower() == zh.lower():
        return zh
    return "%s / %s" % (zh, en)


def is_translatable(name: str) -> bool:
    """词典能否完整覆盖；界面用它决定提示「自动」还是「请手动填英文」。"""
    raw = (name or "").strip()
    if not raw:
        return False
    if not _CJK.search(raw):
        return True
    m = _TRAILING_CODE.search(raw)
    core = raw[:m.start()].strip() if m else raw
    core = _SEP.sub("", core)
    return bool(core) and _segment(core) is not None
