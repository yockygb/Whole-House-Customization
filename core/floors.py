# -*- coding: utf-8 -*-
"""
楼层（Floor）
=============
从原系统 floors.py 原样迁移：B2 / B1 / GF / 1F / 2F / 3F / 4F / RF，也允许自定义
（Mezzanine、Podium、Level 5…）。楼层只用于分组与显示，**不参与任何计价**。
旧报价没有 floor 字段时按 GF 处理。
"""
from __future__ import annotations

from typing import List

DEFAULT_FLOOR = "GF"

# 排序：地下 → 地面 → 地上 → 屋顶；自定义楼层排在最后（保持录入顺序）
FLOOR_CODES: List[str] = ["B2", "B1", "GF", "1F", "2F", "3F", "4F", "RF"]

FLOOR_EN = {
    "B2": "Basement 2",
    "B1": "Basement 1",
    "GF": "Ground Floor",
    "1F": "First Floor",
    "2F": "Second Floor",
    "3F": "Third Floor",
    "4F": "Fourth Floor",
    "RF": "Roof Floor",
}

# 中文楼层名（导出/界面副标题用；英文为主，中文为辅）
FLOOR_CN = {
    "B2": "地下二层",
    "B1": "地下一层",
    "GF": "地面层",
    "1F": "一层",
    "2F": "二层",
    "3F": "三层",
    "4F": "四层",
    "RF": "屋顶层",
}

# 常见别名 → 标准码（大小写、空格都容错）
_ALIAS = {"G": "GF", "GROUND": "GF", "GROUNDFLOOR": "GF", "ROOF": "RF",
          "B1F": "B1", "B2F": "B2"}


def normalize_floor(value: str) -> str:
    """空 → GF；标准楼层码统一成大写（gf → GF）；自定义楼层原样保留。"""
    s = (value or "").strip()
    if not s:
        return DEFAULT_FLOOR
    up = s.upper().replace(" ", "")
    if up in FLOOR_EN:
        return up
    if up in _ALIAS:
        return _ALIAS[up]
    return s


def floor_rank(value: str) -> int:
    """排序权重：B2 < B1 < GF < 1F < … < RF < 自定义。"""
    f = normalize_floor(value)
    return FLOOR_CODES.index(f) if f in FLOOR_CODES else len(FLOOR_CODES)


def floor_name_en(value: str) -> str:
    f = normalize_floor(value)
    return FLOOR_EN.get(f, f)


def floor_name_cn(value: str) -> str:
    """中文楼层名；自定义楼层没有固定中文时返回空串。"""
    return FLOOR_CN.get(normalize_floor(value), "")


def floor_label(value: str) -> str:
    """「GF / Ground Floor」；自定义楼层没有固定英文时只给原值。"""
    f = normalize_floor(value)
    en = FLOOR_EN.get(f)
    return "%s / %s" % (f, en) if en else f


def floor_pair(value: str):
    """(标准码, 英文名)；给 Excel 分组标题用。"""
    f = normalize_floor(value)
    return f, floor_name_en(f)


def is_standard(value: str) -> bool:
    return normalize_floor(value) in FLOOR_EN
