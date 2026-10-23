# -*- coding: utf-8 -*-
"""区域（房间）中英文对照。

`data/pricing.json` 只列了 13 个标准房间（主卧 / 次卧 / 客厅 …），实际报价里
还会出现「主卫 / 次卫 / 公卫 / 保姆房 / 储物间」这类常见区域。原系统对未知
区域直接回退成中文，于是导出时「英文行」里混进了中文（`First Floor · 主卫`）。

本模块只做**文案映射**，不参与任何计价：
  · `ROOM_EN`       标准房间 + 常见扩展房间的英文名
  · `EXTRA_ROOMS`   前端「区域」下拉需要补齐的扩展房间（name / name_en）
  · `room_en(name)` 查英文名；查不到返回空串，调用方据此**不写英文行**，
                    避免用中文冒充英文。
"""
from __future__ import annotations

import re
from typing import Dict, List

# 标准 13 个（与 data/pricing.json 保持一致，作为兜底） + 常见扩展
ROOM_EN: Dict[str, str] = {
    # —— 与 pricing.json 一致 ——
    "主卧": "Master Bedroom",
    "次卧": "Second Bedroom",
    "儿童房": "Children's Room",
    "长辈房": "Elder's Room",
    "衣帽间": "Walk-in Closet",
    "书房": "Study",
    "客厅": "Living Room",
    "餐厅": "Dining Room",
    "厨房": "Kitchen",
    "玄关": "Foyer",
    "阳台": "Balcony",
    "卫生间": "Bathroom",
    "其他": "Others",
    # —— 常见扩展 ——
    "主卫": "Master Bathroom",
    "次卫": "Second Bathroom",
    "客卫": "Guest Bathroom",
    "公卫": "Common Bathroom",
    "主浴室": "Master Bathroom",
    "浴室": "Bathroom",
    "洗手间": "Washroom",
    "保姆房": "Maid's Room",
    "工人房": "Maid's Room",
    "储物间": "Storage Room",
    "储藏室": "Storage Room",
    "杂物间": "Utility Room",
    "洗衣房": "Laundry Room",
    "家政间": "Utility Room",
    "走廊": "Corridor",
    "过道": "Corridor",
    "楼梯": "Staircase",
    "楼梯间": "Staircase",
    "玄关区": "Foyer",
    "门厅": "Entrance Hall",
    "露台": "Terrace",
    "花园": "Garden",
    "庭院": "Courtyard",
    "车库": "Carport",
    "车位": "Car Park",
    "影音室": "Home Theatre",
    "家庭厅": "Family Hall",
    "健身房": "Gym",
    "茶室": "Tea Room",
    "书房区": "Study Area",
    "办公区": "Home Office",
    "电竞房": "Gaming Room",
    "宠物房": "Pet Room",
    "佛堂": "Prayer Room",
    "书房/办公": "Study / Office",
    "餐厅+厨房": "Dining / Kitchen",
}

# 前端「区域」下拉需要补的项（pricing.json 里没有的）
EXTRA_ROOMS: List[Dict[str, str]] = [
    {"name": "主卫", "name_en": "Master Bathroom"},
    {"name": "次卫", "name_en": "Second Bathroom"},
    {"name": "客卫", "name_en": "Guest Bathroom"},
    {"name": "保姆房", "name_en": "Maid's Room"},
    {"name": "储物间", "name_en": "Storage Room"},
    {"name": "洗衣房", "name_en": "Laundry Room"},
    {"name": "走廊", "name_en": "Corridor"},
    {"name": "楼梯间", "name_en": "Staircase"},
    {"name": "露台", "name_en": "Terrace"},
    {"name": "影音室", "name_en": "Home Theatre"},
]

# 生成「主卧衣柜」这类复合名时，允许削掉的尾部量词
_TAILS = ("区域", "空间", "区", "间", "室", "房")


def room_en(name: str, known: Dict[str, str] | None = None) -> str:
    """返回区域英文名；没有对应英文时返回空串。

    known: 传入 `{name: name_en}`（来自 pricing.json）时优先使用，便于用户自定义。
    """
    raw = str(name or "").strip()
    if not raw:
        return ""
    if known:
        for k, v in known.items():
            if k == raw:
                return (v or "").strip()
        for k, v in sorted(known.items(), key=lambda pair: len(pair[0]), reverse=True):
            if raw.startswith(k):
                suffix = raw[len(k):]
                match = re.fullmatch(r"\s*(?:#|№)?\s*(\d+)", suffix)
                if match and v:
                    return f"{v.strip()} {match.group(1)}"
    hit = ROOM_EN.get(raw)
    if hit:
        return hit
    # 去掉空格 / 全角空格后再试
    compact = raw.replace(" ", "").replace("\u3000", "")
    hit = ROOM_EN.get(compact)
    if hit:
        return hit
    # 削尾部量词再试（「主卫间」→「主卫」）
    for tail in _TAILS:
        if compact.endswith(tail) and len(compact) > len(tail):
            hit = ROOM_EN.get(compact[: -len(tail)])
            if hit:
                return hit
    return ""
