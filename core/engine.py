# -*- coding: utf-8 -*-
"""
全屋定制报价引擎 v2.0（原系统 quote_engine.py 的等价迁移）
=========================================================
本模块的**计价逻辑、公式、默认单价、系数、取价策略与原系统完全一致**，
逐行迁移自 C:\\Users\\ASUS\\wb-quote\\quote_engine.py，仅做三件事：

1. 改成包内相对导入（floors / cab_name）；
2. 增加只读的「材料价格覆盖」钩子（override），不传时行为与原系统 100% 相同；
3. 增加 compute_quote()，把折扣 / 定金 / 税费预留一并汇总（金额口径与原系统一致）。

计价规则（不得修改）
--------------------
体系一 板式柜体（定制柜 / 护墙板）：按 ft²
    计价量 = 长(ft) × 计价高(ft)
    计价高 = max(实际高, 3.3ft)      —— 高度不够 3.3ft 算 3.3ft（可开关）
    深度系数 = max(1, 实际深 / 标准深) —— 超深按比例加价，浅于标准不折价
    金额 = 计价量 × 深度系数 × 单价 × 数量

体系二 橱柜（地柜 / 吊柜）：按 ft
    金额 = 长度(ft) × 非标系数 × 单价 × 数量
    非标（高度≠标准高 或 深度>标准深+10mm）→ ×1.2
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple

from .cab_name import resolve_bilingual_cabinet_name
from .floors import floor_name_en, normalize_floor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(BASE_DIR, "data", "factory-pricing.json")

# 输入单位 -> mm
UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "inch": 25.4, "ft": 304.8, "m": 1000.0}
UNIT_LABELS = ["mm", "cm", "inch", "ft"]


def load_config(path: str = DEFAULT_CONFIG, overrides: Optional[Dict] = None,
                extra_extras: Optional[List[Dict]] = None) -> "PricingConfig":
    with open(path, "r", encoding="utf-8") as f:
        return PricingConfig(json.load(f), overrides=overrides, extra_extras=extra_extras)


class PricingConfig:
    """价格配置的只读视图 + 查询工具。"""

    def __init__(self, raw: Dict[str, Any], overrides: Optional[Dict] = None,
                 extra_extras: Optional[List[Dict]] = None):
        self.raw = raw
        self.meta = raw.get("meta", {})
        self.mm_per_ft = float(self.meta.get("mm_per_ft", 304.8))
        self.currency = self.meta.get("currency", "RM")
        self.version = self.meta.get("version", "1.0")
        self.groups = {g["key"]: g for g in raw.get("groups", [])}
        self.categories = {c["key"]: c for c in raw.get("categories", [])}
        self._cat_order = [c["key"] for c in raw.get("categories", [])]
        self.prices = raw.get("prices", {})
        self.price_mode = self.meta.get("price_mode", "high")
        self.nonstd_factor = float(self.meta.get("nonstd_factor", 1.2))
        self.height_tol = float(self.meta.get("height_tol_ft", 0.1))
        # —— 新增：材料价格覆盖（管理界面里手改过的报价价 / 成本价）——
        # 结构 {(cat_key, mat_key): {"quote": float|None, "cost": float|None}}
        self.overrides = overrides or {}
        # —— 新增：用户后续自定义的增项（不覆盖任何原始增项）——
        self.extra_extras = extra_extras or []

    # ---------------- 查询 ----------------
    def cat_list(self) -> List[Dict[str, Any]]:
        return [self.categories[k] for k in self._cat_order]

    def for_category(self, key):
        scoped = self.raw.get('kitchen_pricing')
        if scoped and self.category(key).get('source_key'):
            return PricingConfig(scoped, overrides=self.overrides)
        return self

    def category(self, key: str) -> Dict[str, Any]:
        if key not in self.categories:
            raise KeyError("未知品类: %s" % key)
        return self.categories[key]

    def floor_en(self, code):
        code=normalize_floor(code)
        for f in self.raw.get("floors",[]):
            if normalize_floor(f.get("code",""))==code:return f.get("name_en") or code
        return floor_name_en(code)

    def illustration(self) -> Dict[str, Any]:
        return self.raw.get("illustration", {}) or {}

    def cat_name(self, key: str) -> str:
        return self.category(key).get("name", key)

    def group_of(self, cat_key: str) -> str:
        return self.category(cat_key)["group"]

    def group_name(self, cat_key: str) -> str:
        return self.groups[self.group_of(cat_key)].get("name", self.group_of(cat_key))

    def materials(self, cat_key: str) -> List[Tuple[str, str]]:
        """[(材质key, 显示名)]；拆分计价的品类只返回柜体选项。"""
        return [(k, v.get("label", k)) for k, v in self._table(cat_key).items()
                if v.get("part") != "door"]

    # ---------------- 柜体 / 柜门拆分计价 ----------------
    def _table(self, cat_key: str) -> Dict[str, Any]:
        return self.prices.get(cat_key, {}) or {}

    def is_split(self, cat_key: str) -> bool:
        model = self.category(cat_key).get("pricing_model")
        if model: return model in ("projection_split", "kitchen_split")
        return any(v.get("part") == "door" for v in self._table(cat_key).values())

    def body_options(self, cat_key: str) -> List[Tuple[str, str]]:
        return self.materials(cat_key)

    def door_options(self, cat_key: str) -> List[Tuple[str, str]]:
        return [(k, v.get("label", k)) for k, v in self._table(cat_key).items()
                if v.get("part") == "door"]

    def default_body(self, cat_key: str) -> str:
        opts = self.body_options(cat_key)
        return opts[0][0] if opts else ""

    def default_door(self, cat_key: str) -> str:
        opts = self.door_options(cat_key)
        return opts[0][0] if opts else ""

    def body_price(self, cat_key: str, mat_key: str,
                   mode: Optional[str] = None) -> float:
        return self.unit_price(cat_key, mat_key or self.default_body(cat_key), mode)

    def door_price(self, cat_key: str, door_key: str,
                   mode: Optional[str] = None) -> float:
        if not door_key or door_key == "none":
            return 0.0
        return self.unit_price(cat_key, door_key, mode)

    def combined_price(self, cat_key: str, body_key: str, door_key: str,
                       mode: Optional[str] = None) -> float:
        if not self.is_split(cat_key):
            return self.unit_price(cat_key, body_key, mode)
        return _r(self.body_price(cat_key, body_key, mode)
                  + self.door_price(cat_key, door_key, mode), 2)

    def material_label(self, cat_key: str, mat_key: str) -> str:
        return self.price_entry(cat_key, mat_key).get("label", mat_key)

    def material_label_en(self, cat_key: str, mat_key: str) -> str:
        e = self.price_entry(cat_key, mat_key)
        return e.get("label_en") or e.get("label", mat_key)

    def cat_name_en(self, key: str) -> str:
        c = self.category(key)
        return c.get("name_en") or c.get("name", key)

    def group_name_en(self, cat_key: str) -> str:
        g = self.groups[self.group_of(cat_key)]
        return g.get("name_en") or g.get("name", self.group_of(cat_key))

    # ---------------- 区域（房间）----------------
    def rooms(self) -> List[Dict[str, str]]:
        return self.raw.get("rooms", []) or [{"name": "其他", "name_en": "Others"}]

    def room_names(self) -> List[str]:
        return [r.get("name", "") for r in self.rooms()]

    def room_en(self, name: str) -> str:
        raw = str(name or "").strip()
        rooms = self.rooms()
        for r in rooms:
            if r.get("name") == raw:
                return r.get("name_en", raw)
        for r in sorted(rooms, key=lambda x: len(str(x.get("name", ""))), reverse=True):
            base = str(r.get("name", "")).strip()
            if raw.startswith(base):
                number = raw[len(base):].strip().lstrip("#").strip()
                if base and number.isdigit():
                    return "%s %s" % (r.get("name_en") or base, number)
        return raw

    def mode_label_en(self, mode: Optional[str] = None) -> str:
        return self.meta.get("price_modes_en", {}).get(
            mode or self.price_mode, "Market Price - High")

    # ---------------- 公司抬头 / 页脚备注 ----------------
    def company(self) -> Dict[str, Any]:
        return self.raw.get("company", {}) or {}

    def remark(self) -> Dict[str, Any]:
        return self.raw.get("remark", {}) or {}

    def totals(self) -> Dict[str, Any]:
        """报价单合计区显示项（默认与旧样例一致：只显示产品合计）。

        show_discount_row / show_deposit_rows 可在「管理」里打开；
        打开后报价页会在产品合计下方追加折扣 / 折后总额 / 定金 / 余款。
        """
        t = self.raw.get("totals", {}) or {}
        return {
            "show_discount_row": bool(t.get("show_discount_row", False)),
            "show_deposit_rows": bool(t.get("show_deposit_rows", False)),
        }

    # ---------------- 灯带 ----------------
    def led_meta(self) -> Dict[str, Any]:
        return self.raw.get("led", {}) or {}

    def led_price_per_m(self) -> float:
        return float(self.led_meta().get("price_per_m", 0))

    def led_power_price(self) -> float:
        return float(self.led_meta().get("power_price", 0) or 0)

    def led_sensor_price(self) -> float:
        return float(self.led_meta().get("sensor_price", 0) or 0)

    def led_accessory(self) -> float:
        return self.led_power_price() + self.led_sensor_price()

    def led_units(self) -> List[Dict[str, str]]:
        return self.led_meta().get("units", []) or [{"key": "m", "name": "米"}]

    def led_unit_name(self, key: str) -> str:
        for u in self.led_units():
            if u.get("key") == key:
                return u.get("name", key)
        return key

    # ---------------- 增项 ----------------
    def extras_meta(self) -> Dict[str, Any]:
        return self.raw.get("extras", {}) or {}

    def extras_items(self) -> List[Dict[str, Any]]:
        """原始增项在前，用户自定义增项追加在后（原始数据永不改动）。"""
        base = self.extras_meta().get("items", []) or []
        return [e for e in list(base) + list(self.extra_extras or []) if e.get("enabled", True)]

    def extras_groups(self) -> List[str]:
        return self.extras_meta().get("groups", ["kitchen"]) or []

    def extras_for(self, cat_key: str, selected_keys=()) -> List[Dict[str, Any]]:
        try:
            grp = self.group_of(cat_key)
        except Exception:
            return []
        if grp not in self.extras_groups():
            return []
        selected_keys = set(selected_keys or ())
        out = []
        items = list(self.extras_meta().get("items", []) or []) + list(self.extra_extras or [])
        for it in items:
            if not it.get("enabled", True) and it.get("key") not in selected_keys:
                continue
            cats = it.get("cats")
            if cats and cat_key not in cats and it.get("key") not in selected_keys:
                continue
            out.append(it)
        return out

    def extra_item(self, key: str) -> Dict[str, Any]:
        for it in self.extras_items():
            if it.get("key") == key:
                return it
        return {}

    def extra_price(self, key: str) -> float:
        return float(self.extra_item(key).get("price", 0) or 0)

    def extra_name(self, key: str, en: bool = False) -> str:
        it = self.extra_item(key)
        return it.get("name_en" if en else "name", key) or key

    def m_per_ft(self) -> float:
        return float(self.led_meta().get("mm_per_ft", 304.8)) / 1000.0

    def led_to_m(self, qty: float, unit: str) -> float:
        return float(qty) if (unit or "m") != "ft" else float(qty) * self.m_per_ft()

    def led_from_m(self, qty_m: float, unit: str) -> float:
        return float(qty_m) if (unit or "m") != "ft" else float(qty_m) / self.m_per_ft()

    def default_material(self, cat_key: str) -> str:
        mats = self.materials(cat_key)
        return mats[0][0] if mats else ""

    def price_entry(self, cat_key: str, mat_key: str) -> Dict[str, Any]:
        table = self.prices.get(cat_key, {})
        if mat_key in table:
            return table[mat_key]
        if not table:
            raise KeyError("品类 %s 没有价格" % cat_key)
        return next(iter(table.values()))

    # ---------------- 取价（原规则 + 可选覆盖）----------------
    def default_unit_price(self, cat_key: str, mat_key: str,
                           mode: Optional[str] = None) -> float:
        """原系统取价：low 下限 / mid 中位 / high 上限。"""
        market = self.price_entry(cat_key, mat_key).get("market", [0, 0])
        lo, hi = float(market[0]), float(market[-1])
        mode = mode or self.price_mode
        if mode == "low":
            return lo
        if mode == "mid":
            return (lo + hi) / 2.0
        return hi

    def unit_price(self, cat_key: str, mat_key: str, mode: Optional[str] = None) -> float:
        """报价单价：材料管理里手改过就用覆盖价（并标记），否则按原取价策略。"""
        ov = (self.overrides.get((cat_key, mat_key)) or {}).get("quote")
        if ov is not None and float(ov) >= 0:
            return float(ov)
        return self.default_unit_price(cat_key, mat_key, mode)

    def is_price_overridden(self, cat_key: str, mat_key: str) -> bool:
        ov = (self.overrides.get((cat_key, mat_key)) or {}).get("quote")
        return ov is not None and float(ov) >= 0

    def default_supply_price(self, cat_key: str, mat_key: str) -> float:
        return float(self.price_entry(cat_key, mat_key).get("supply", 0) or 0)

    def supply_price(self, cat_key: str, mat_key: str) -> float:
        """成本价：材料管理里手改过就用覆盖价，否则用原供货价。"""
        ov = (self.overrides.get((cat_key, mat_key)) or {}).get("cost")
        if ov is not None and float(ov) >= 0:
            return float(ov)
        return self.default_supply_price(cat_key, mat_key)

    def std_depth_ft(self, cat_key: str) -> float:
        return float(self.category(cat_key).get("std_depth_mm", 600)) / self.mm_per_ft


# ---------------- 数据模型 ----------------
@dataclass
class Item:
    """一条待报价的柜体/材料。长度单位统一存 mm。"""
    room: str
    cat: str
    material: str                        # 拆分类目里 = 柜体 key；其他 = 材质 key
    length_mm: float
    height_mm: float = 0.0
    depth_mm: float = 0.0
    qty: int = 1
    note: str = ""
    door: str = ""                       # 柜门 key（"" / "none" = 不装门）
    nonstd: Optional[bool] = None        # None=按规则自动判定
    apply_min_height: bool = True        # 高度不足 3.3ft 按 3.3ft 计
    unit_price: Optional[float] = None   # 手动指定单价（None=按价格表自动取价）
    room_note: str = ""
    led_type: str = "none"               # "yes" / "none"
    led_qty: float = 0.0
    led_unit: str = "m"
    led_price: Optional[float] = None
    led_power: bool = False
    led_sensor: bool = False
    extras: Dict[str, int] = field(default_factory=dict)
    extras_size: Dict[str, Dict[str, float]] = field(default_factory=dict)
    cab_name: str = ""
    cab_name_en: str = ""
    floor: str = "GF"
    note_en: str = ""
    room_note_en: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Item":
        up = d.get("unit_price", d.get("price"))
        lp = d.get("led_price")
        return cls(
            room=d.get("room", ""),
            cat=d.get("cat") or d.get("category", ""),
            material=d.get("material", ""),
            door=d.get("door", "") or "",
            length_mm=float(d.get("length_mm", d.get("length", 0)) or 0),
            height_mm=float(d.get("height_mm", d.get("height", 0)) or 0),
            depth_mm=float(d.get("depth_mm", d.get("depth", 0)) or 0),
            qty=int(d.get("qty", 1) or 1),
            note=d.get("note", ""),
            nonstd=d.get("nonstd"),
            apply_min_height=bool(d.get("apply_min_height", True)),
            unit_price=(float(up) if up not in (None, "") else None),
            room_note=d.get("room_note", "") or "",
            note_en=d.get("note_en", "") or "",
            room_note_en=d.get("room_note_en", "") or "",
            led_type=d.get("led_type", "none") or "none",
            led_qty=float(d.get("led_qty", 0) or 0),
            led_unit=d.get("led_unit", "m") or "m",
            led_price=(float(lp) if lp not in (None, "") else None),
            led_power=bool(d.get("led_power", False)),
            led_sensor=bool(d.get("led_sensor", False)),
            extras={str(k): float(v or 0) for k, v in (d.get("extras") or {}).items()},
            extras_size={str(k): {str(kk): float(vv or 0) for kk, vv in (v or {}).items()}
                         for k, v in (d.get("extras_size") or {}).items()},
            cab_name=d.get("cab_name", "") or "",
            cab_name_en=d.get("cab_name_en", "") or "",
            floor=normalize_floor(d.get("floor", "")),
        )


@dataclass
class LineResult:
    idx: int
    room: str
    group: str
    cat_key: str
    cat_name: str
    material: str
    material_label: str
    length_mm: float
    height_mm: float
    depth_mm: float
    l_ft: float
    h_ft: float
    d_ft: float
    bill_h_ft: float
    measure: float
    unit: str
    factor: float
    unit_price: float
    qty: int
    amount: float
    supply_unit: float
    supply_amount: float
    basis: str
    note: str
    flags: List[str]
    item_note: str = ""
    min_height_applied: bool = False
    room_note: str = ""
    price_override: bool = False
    cat_name_en: str = ""
    material_label_en: str = ""
    group_en: str = ""
    unit_en: str = ""
    room_en: str = ""
    main_amount: float = 0.0
    led_type: str = "none"
    led_name: str = ""
    led_name_en: str = ""
    led_unit: str = ""
    led_qty: float = 0.0
    led_qty_m: float = 0.0
    led_price: float = 0.0
    led_accessory: float = 0.0
    led_amount: float = 0.0
    led_override: bool = False
    led_power: bool = False
    led_power_amount: float = 0.0
    led_sensor: bool = False
    led_sensor_amount: float = 0.0
    extras_amount: float = 0.0
    extras_text: str = ""
    extras_list: List[Dict[str, Any]] = field(default_factory=list)
    split: bool = False
    body_key: str = ""
    body_label: str = ""
    body_label_en: str = ""
    body_price: float = 0.0
    body_amount: float = 0.0
    door_key: str = ""
    door_label: str = ""
    door_label_en: str = ""
    door_price: float = 0.0
    door_amount: float = 0.0
    cab_name: str = ""
    cab_name_en: str = ""
    floor: str = "GF"
    floor_en: str = ""
    min_height_enabled: bool = True
    nonstd_override: Optional[bool] = None
    item_note_en: str = ""
    room_note_en: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------- 计算 ----------------
def _r(x: float, n: int = 4) -> float:
    return round(float(x) + 1e-9, n)


def compute_line(cfg: PricingConfig, item: Item, idx: int = 1,
                 mode: Optional[str] = None) -> LineResult:
    cat = cfg.category(item.cat)
    split = cfg.is_split(item.cat)
    body_key = item.material or (cfg.default_body(item.cat) if split else "")
    door_key = (item.door or "").strip()
    if door_key.lower() == "none":
        door_key = ""
    if split and not door_key:
        door_key = ""
    body_entry = cfg.price_entry(item.cat, body_key)
    door_entry = cfg.price_entry(item.cat, door_key) if (split and door_key) else {}
    entry = body_entry
    group_key = cat["group"]
    measure_type = cat.get("measure", "area")
    flags: List[str] = []

    mft = cfg.mm_per_ft
    l_ft = item.length_mm / mft
    h_ft = item.height_mm / mft
    d_ft = item.depth_mm / mft

    # 单价：拆分品类 = 柜体单价 + 柜门单价；其余 = 材质单价
    body_price = cfg.unit_price(item.cat, body_key, mode)
    door_price = (cfg.unit_price(item.cat, door_key, mode) if door_entry else 0.0)
    body_supply = cfg.supply_price(item.cat, body_key)
    door_supply = cfg.supply_price(item.cat, door_key) if door_entry else 0.0

    price_override = False
    if item.unit_price is not None and float(item.unit_price) >= 0:
        unit_price = float(item.unit_price)
        price_override = True
        flags.append("手动定价")
    else:
        unit_price = _r(body_price + door_price, 2) if split else body_price
    supply_unit = _r(body_supply + door_supply, 2) if split else body_supply

    if entry.get("source") in ("assumed", "reference"):
        flags.append("参考价")

    bill_h_ft = h_ft
    factor = 1.0
    basis = ""
    min_height_applied = False

    if measure_type == "area":
        # —— 体系一：长 × 计价高 × 深度系数 ——
        min_h = float(cat.get("min_height_ft", 3.3))
        if item.apply_min_height and h_ft < min_h:
            bill_h_ft = min_h
            min_height_applied = True
            flags.append("按%gft起算" % min_h)
        std_d = cfg.std_depth_ft(item.cat)
        if not cat.get("ignore_depth"):
            if d_ft > 0 and std_d > 0 and d_ft > std_d + 1e-6:
                factor = d_ft / std_d
                flags.append("超深×%.2f" % factor)
        measure = l_ft * bill_h_ft
        unit = "ft²"
        amount = measure * factor * unit_price * item.qty
        if split:
            price_txt = "(柜体%.0f+柜门%.0f)" % (body_price, door_price) if door_entry \
                else "(柜体%.0f+无门)" % body_price
        else:
            price_txt = "单价%.0f" % unit_price
        basis = "长%.2fft × 计价高%.2fft%s = %.2fft² × %s%s" % (
            l_ft, bill_h_ft, (" × 深系数%.2f" % factor) if factor > 1.0001 else "",
            measure, price_txt, (" × %d件" % item.qty) if item.qty > 1 else "")

    elif measure_type == "length":
        # —— 体系二：按长度英尺，非标×1.2 ——
        std_h = cat.get("std_height_ft")
        check_h = bool(cat.get("check_height", False))
        std_d_mm = float(cat.get("std_depth_mm", 0) or 0)
        nonstd = False
        reasons = []
        if item.nonstd is True:
            nonstd = True
            reasons.append("手动标记非标")
        elif item.nonstd is False:
            nonstd = False
        else:
            if check_h and std_h and h_ft > 0 and abs(h_ft - float(std_h)) > cfg.height_tol:
                nonstd = True
                reasons.append("高度%.2fft≠标准%.2fft" % (h_ft, float(std_h)))
            if std_d_mm and item.depth_mm > std_d_mm + float(cat.get("depth_tolerance_mm", 10)):
                nonstd = True
                reasons.append("深度%.0fmm>标准%.0fmm" % (item.depth_mm, std_d_mm))
        if nonstd:
            factor = cfg.nonstd_factor
            flags.append("非标×%.1f" % factor)
        measure = l_ft
        unit = "ft"
        amount = measure * factor * unit_price * item.qty
        basis = "长%.2fft × 单价%.0f%s%s" % (
            l_ft, unit_price,
            (" × %.1f(非标)" % factor) if factor > 1 else "",
            (" × %d件" % item.qty) if item.qty > 1 else "")

    else:  # pcs 按个
        measure = float(item.qty)
        unit = entry.get("unit", "个")
        factor = 1.0
        amount = unit_price * item.qty
        basis = "%d%s × 单价%.0f" % (item.qty, unit, unit_price)
        bill_h_ft = h_ft

    note = entry.get("note", "")
    if item.note:
        note = (note + "；" + item.note) if note else item.note

    if price_override:
        basis = basis + "（手动定价）"

    # ---- 柜体 / 柜门拆分金额 ----
    body_amount = 0.0
    door_amount = 0.0
    if split:
        if price_override:
            body_amount = _r(amount, 2)
        elif measure_type == "pcs":
            body_amount = _r(body_price * item.qty, 2)
            door_amount = _r(door_price * item.qty, 2)
        else:
            body_amount = _r(measure * factor * body_price * item.qty, 2)
            door_amount = _r(measure * factor * door_price * item.qty, 2)
        if not price_override:
            basis = basis + "；柜体%.2f + 柜门%.2f" % (body_amount, door_amount)

    # ---- 灯带（有/无）：数量×每米价 + 一套配件 ----
    led_on = bool(item.led_type and item.led_type != "none")
    led_unit = (item.led_unit or "m").lower()
    led_qty = float(item.led_qty or 0)
    led_base = cfg.led_price_per_m()
    led_price = float(item.led_price) if item.led_price is not None else led_base
    led_override = (item.led_price is not None and abs(led_price - led_base) > 0.005)
    led_qty_m = cfg.led_to_m(led_qty, led_unit)
    power_price = cfg.led_power_price()
    sensor_price = cfg.led_sensor_price()
    has_power = bool(led_on and item.led_power)
    has_sensor = bool(led_on and item.led_sensor)
    power_amt = _r(power_price, 2) if has_power else 0.0
    sensor_amt = _r(sensor_price, 2) if has_sensor else 0.0
    accessory = _r(power_amt + sensor_amt, 2)
    led_amount = 0.0
    if led_on and (led_qty_m > 0 or accessory > 0):
        led_amount = _r(led_qty_m * led_price + accessory, 2)
        amount = _r(amount + led_amount, 2)
        bits_led = ["灯带%.2f%s(%.2fm)×%.0f" % (led_qty, cfg.led_unit_name(led_unit),
                                                led_qty_m, led_price)]
        if has_power:
            bits_led.append("电源%.0f" % power_amt)
        if has_sensor:
            bits_led.append("感应器%.0f" % sensor_amt)
        basis = basis + " ＋ " + "+".join(bits_led) + "=%.2f" % led_amount
    main_amount = _r(amount - led_amount, 2)

    # ---- 增项（玻璃门 / 石英石 / 水槽 / 下拉架 / 高柜拉篮 / 碗碟拉篮）----
    extras_list: List[Dict[str, Any]] = []
    extras_amount = 0.0
    for ex in cfg.extras_for(item.cat, (item.extras or {}).keys()):
        key = ex.get("key", "")
        q = int((item.extras or {}).get(key, 0) or 0)
        if q <= 0:
            continue
        p = float(ex.get("price", 0) or 0)
        basis_kind = ex.get("basis", "qty") or "qty"
        size_mm = (0.0, 0.0)
        custom_length_mm = None
        if basis_kind == "length":
            sz = (item.extras_size or {}).get(key) or {}
            if key == "quartz" and "l_mm" in sz:
                custom_length_mm = float(sz['l_mm'])
                if not math.isfinite(custom_length_mm) or custom_length_mm <= 0:
                    raise ValueError('Quartz length must be positive mm, or leave blank for cabinet length / 石英石长度须大于零（毫米），或清空以跟随柜体长度')
            raw = (custom_length_mm / mft if custom_length_mm is not None else l_ft) * q
            ex_measure = _r(raw, 4)
            amt = _r(p * raw, 2)
            unit_txt = "ft"
        elif basis_kind == "area":
            sz = (item.extras_size or {}).get(key) or {}
            w_mm = float(sz.get("w_mm", 0) or 0)
            h_mm = float(sz.get("h_mm", 0) or 0)
            own_size = w_mm > 0 and h_mm > 0
            if own_size:
                w_ft, hh_ft = w_mm / mft, h_mm / mft
            else:
                w_ft, hh_ft = l_ft, h_ft
            raw = w_ft * hh_ft * q
            ex_measure = _r(raw, 4)
            amt = _r(p * raw, 2)
            unit_txt = "ft²"
            size_mm = (w_mm, h_mm) if own_size else (0.0, 0.0)
        else:
            ex_measure = float(q)
            amt = _r(p * q, 2)
            unit_txt = ""
        extras_amount = _r(extras_amount + amt, 2)
        extras_list.append({"key": key, "name": ex.get("name", key),
                            "name_en": ex.get("name_en", ""),
                            "qty": q, "price": _r(p, 2), "amount": amt,
                            "basis": basis_kind, "measure": ex_measure,
                            "unit": unit_txt,
                            "w_mm": size_mm[0], "h_mm": size_mm[1]})
        if custom_length_mm is not None:
            extras_list[-1]['l_mm'] = custom_length_mm
    extras_text = "、".join(
        ("%s %gmm × %d (%.2fft)" % (e['name'], e['l_mm'], e['qty'], e['measure'])) if e['basis'] == 'length' and e.get('l_mm')
        else ("%s %.2fft" % (e["name"], e["measure"])) if e["basis"] == "length"
        else ("%s %d×%dmm %.2fft²" % (e["name"], round(e["w_mm"]), round(e["h_mm"]),
                                      e["measure"])) if e["basis"] == "area" and e["w_mm"]
        else ("%s %.2fft²" % (e["name"], e["measure"])) if e["basis"] == "area"
        else ("%s×%d" % (e["name"], e["qty"]))
        for e in extras_list)
    if extras_amount:
        amount = _r(amount + extras_amount, 2)
        basis = basis + " ＋ 增项 %s=%.2f" % (extras_text, extras_amount)
    main_amount = _r(main_amount, 2)

    # ---- 材质显示名 ----
    body_label = entry.get("label", body_key)
    body_label_en = entry.get("label_en", body_label)
    door_label = door_entry.get("label", door_key) if door_entry else ""
    door_label_en = (door_entry.get("label_en", door_label) if door_entry else "")
    if split:
        if door_entry:
            mat_label = "%s + %s" % (body_label, door_label)
            mat_label_en = "%s + %s" % (body_label_en, door_label_en)
        else:
            mat_label = "%s（无门）" % body_label
            mat_label_en = "%s (no door)" % body_label_en
    else:
        mat_label, mat_label_en = body_label, body_label_en

    cabinet_name_en, cabinet_name_cn = resolve_bilingual_cabinet_name(
        item.cab_name, item.cab_name_en, cfg.raw.get("cabinet_name_glossary", {}))
    return LineResult(
        min_height_enabled=item.apply_min_height, nonstd_override=item.nonstd,
        item_note_en=item.note_en, room_note_en=item.room_note_en,
        idx=idx, room=item.room, group=cfg.group_name(item.cat),
        cat_key=item.cat, cat_name=cat.get("name", item.cat),
        cab_name=cabinet_name_cn,
        cab_name_en=cabinet_name_en,
        floor=normalize_floor(item.floor),
        floor_en=cfg.floor_en(item.floor),
        material=body_key, material_label=mat_label,
        length_mm=item.length_mm, height_mm=item.height_mm, depth_mm=item.depth_mm,
        l_ft=_r(l_ft), h_ft=_r(h_ft), d_ft=_r(d_ft), bill_h_ft=_r(bill_h_ft),
        measure=_r(measure, 3), unit=unit, factor=_r(factor, 3),
        unit_price=_r(unit_price, 2), qty=item.qty, amount=_r(amount, 2),
        supply_unit=_r(supply_unit, 2),
        supply_amount=_r(measure * factor * supply_unit * item.qty
                         if measure_type != "pcs" else supply_unit * item.qty, 2),
        basis=basis, note=note, item_note=(item.note or ""), flags=flags,
        min_height_applied=min_height_applied,
        room_note=item.room_note or "",
        price_override=price_override,
        cat_name_en=cfg.cat_name_en(item.cat),
        material_label_en=mat_label_en,
        group_en=cfg.group_name_en(item.cat),
        unit_en=entry.get("unit_en", "" if unit in ("ft", "ft²") else unit),
        room_en=cfg.room_en(item.room),
        main_amount=main_amount,
        led_type=("yes" if led_on else "none"),
        led_name=("有灯带" if led_on else "—"),
        led_name_en=("LED Strip" if led_on else "—"),
        led_unit=led_unit,
        led_qty=_r(led_qty, 3),
        led_qty_m=_r(led_qty_m, 3),
        led_price=_r(led_price, 2),
        led_accessory=accessory,
        led_amount=led_amount,
        led_override=led_override,
        led_power=has_power,
        led_power_amount=power_amt,
        led_sensor=has_sensor,
        led_sensor_amount=sensor_amt,
        extras_amount=extras_amount,
        extras_text=extras_text,
        extras_list=extras_list,
        split=split,
        body_key=body_key,
        body_label=body_label,
        body_label_en=body_label_en,
        body_price=_r(body_price, 2),
        body_amount=body_amount,
        door_key=door_key,
        door_label=door_label,
        door_label_en=door_label_en,
        door_price=_r(door_price, 2),
        door_amount=door_amount,
    )


def compute_all(cfg: PricingConfig, items: List[Item],
                mode: Optional[str] = None) -> Tuple[List[LineResult], Dict[str, Any]]:
    # Preserve the saved quotation order; moving a line must not change its pricing.
    lines = [compute_line(cfg, it, i + 1, mode) for i, it in enumerate(items)]
    group_totals: Dict[str, float] = {}
    for ln in lines:
        group_totals[ln.group] = group_totals.get(ln.group, 0.0) + ln.amount
    summary = {
        "count": len(lines),
        "group_totals": group_totals,
        "total": _r(sum(l.amount for l in lines), 2),
        "supply_total": _r(sum(l.supply_amount for l in lines), 2),
        "led_rows": sum(1 for l in lines if l.led_amount > 0),
        "led_total": _r(sum(l.led_amount for l in lines), 2),
        "extra_rows": sum(1 for l in lines if l.extras_amount > 0),
        "extra_total": _r(sum(l.extras_amount for l in lines), 2),
    }
    summary["gross_profit"] = _r(summary["total"] - summary["supply_total"], 2)
    summary["gross_margin"] = _r(
        summary["gross_profit"] / summary["total"] * 100, 2) if summary["total"] else 0.0
    return lines, summary


def compute_quote(cfg: PricingConfig, items: List[Item], mode: Optional[str] = None,
                  discount: float = 1.0, deposit_rate: float = 0.5,
                  tax_rate: float = 0.0) -> Tuple[List[LineResult], Dict[str, Any]]:
    """在原汇总口径上追加折扣 / 定金 / 税费预留。

    原系统口径：合计 = 各行金额之和（已含灯带与增项）；
                折后 = ROUND(合计 × 折扣, 2)；定金 = ROUND(折后 × 定金比例, 2)；
                成本 = 各行供货金额之和；毛利 = 合计 − 成本；毛利率 = 毛利 ÷ 合计。
    """
    lines, summary = compute_all(cfg, items, mode)
    disc = float(discount if discount not in (None, "") else 1.0)
    dep = float(deposit_rate if deposit_rate not in (None, "") else 0.0)
    tax = float(tax_rate if tax_rate not in (None, "") else 0.0)
    summary["discount"] = _r(disc, 4)
    summary["net_total"] = _r(summary["total"] * disc, 2)
    summary["discount_amount"] = _r(summary["total"] - summary["net_total"], 2)
    summary["deposit_rate"] = _r(dep, 4)
    summary["deposit"] = _r(summary["net_total"] * dep, 2)
    summary["balance"] = _r(summary["net_total"] - summary["deposit"], 2)
    summary["tax_rate"] = _r(tax, 4)
    summary["tax"] = _r(summary["net_total"] * tax, 2)
    summary["net_total_with_tax"] = _r(summary["net_total"] + summary["tax"], 2)
    summary["gross_profit_net"] = _r(summary["net_total"] - summary["supply_total"], 2)
    summary["gross_margin_net"] = _r(
        summary["gross_profit_net"] / summary["net_total"] * 100, 2) if summary["net_total"] else 0.0
    # 楼层 / 区域 / 品类 / 材质 汇总（金额口径与明细一致）
    summary["by_floor"] = _sum_by(lines, lambda l: l.floor)
    summary["by_room"] = _sum_by(lines, lambda l: l.room)
    summary["by_category"] = _sum_by(lines, lambda l: l.cat_name)
    summary["by_material"] = _sum_by(lines, lambda l: l.material_label)
    return lines, summary


def _sum_by(lines: List[LineResult], key_fn) -> List[Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for l in lines:
        k = key_fn(l) or ""
        row = out.setdefault(k, {"key": k, "count": 0, "amount": 0.0,
                                 "supply": 0.0, "measure": 0.0})
        row["count"] += 1
        row["amount"] += l.amount
        row["supply"] += l.supply_amount
        row["measure"] += l.measure
    rows = []
    for row in out.values():
        row["amount"] = _r(row["amount"], 2)
        row["supply"] = _r(row["supply"], 2)
        row["measure"] = _r(row["measure"], 3)
        row["profit"] = _r(row["amount"] - row["supply"], 2)
        rows.append(row)
    return rows


def mm_from(value: float, unit: str) -> float:
    return float(value or 0) * UNIT_TO_MM.get(unit, 1.0)


def fmt_money(x: float, currency: str = "RM") -> str:
    return "%s %s" % (currency, format(round(x, 2), ",.2f"))
