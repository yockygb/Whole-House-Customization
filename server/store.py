# -*- coding: utf-8 -*-
"""
数据层：SQLite 存储 + 价格配置装配
=================================
职责
----
* 建库建表、首次运行从公开空白出厂配置播种材料目录（默认价只读镜像）；
* 材料价格「覆盖」独立存放，未改过的材料行为与原系统完全一致；
* 报价单 / 明细 / 客户 / 项目 / 版本 / 自定义增项 / 自定义楼层 / 设置；
* 报价锁价快照：已签发报价永远用快照，不被后续改价影响。
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core import PricingConfig, compute_quote
from core.config import DB_PATH, PRICING_PATH
from core.engine import Item
from core.floors import FLOOR_CODES, FLOOR_EN

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, phone TEXT DEFAULT '', email TEXT DEFAULT '',
  address TEXT DEFAULT '', note TEXT DEFAULT '', created_at TEXT
);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER, name TEXT NOT NULL, address TEXT DEFAULT '',
  note TEXT DEFAULT '', created_at TEXT
);
CREATE TABLE IF NOT EXISTS quotes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quote_no TEXT, customer_id INTEGER, project_id INTEGER,
  customer TEXT DEFAULT '', project TEXT DEFAULT '', address TEXT DEFAULT '',
  quote_date TEXT, valid_days INTEGER DEFAULT 30,
  mode TEXT DEFAULT 'low', discount REAL DEFAULT 1.0,
  deposit_rate REAL DEFAULT 0.5, tax_rate REAL DEFAULT 0.0,
  status TEXT DEFAULT 'draft', locked INTEGER DEFAULT 0, version INTEGER DEFAULT 1,
  parent_id INTEGER, note TEXT DEFAULT '', terms TEXT DEFAULT '',
  snapshot_json TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS quote_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quote_id INTEGER NOT NULL, seq INTEGER DEFAULT 0,
  floor TEXT DEFAULT 'GF', room TEXT DEFAULT '', room_note TEXT DEFAULT '',
  cat TEXT NOT NULL, cab_name TEXT DEFAULT '', cab_name_en TEXT DEFAULT '',
  material TEXT DEFAULT '', door TEXT DEFAULT '',
  length_mm REAL DEFAULT 0, height_mm REAL DEFAULT 0, depth_mm REAL DEFAULT 0,
  qty INTEGER DEFAULT 1, unit TEXT DEFAULT 'mm',
  nonstd INTEGER, apply_min_height INTEGER DEFAULT 1,
  unit_price REAL, note TEXT DEFAULT '',
  extras TEXT DEFAULT '{}', extras_size TEXT DEFAULT '{}',
  led_type TEXT DEFAULT 'none', led_qty REAL DEFAULT 0, led_unit TEXT DEFAULT 'm',
  led_price REAL, led_power INTEGER DEFAULT 0, led_sensor INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS materials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE, cat_key TEXT, mat_key TEXT,
  name TEXT, name_en TEXT, part TEXT DEFAULT 'body', unit TEXT DEFAULT 'ft2',
  default_quote REAL DEFAULT 0, default_cost REAL DEFAULT 0,
  quote_price REAL, cost_price REAL,
  supplier TEXT DEFAULT '', stock_qty REAL DEFAULT 0, safety_stock REAL DEFAULT 0,
  note TEXT DEFAULT '', enabled INTEGER DEFAULT 1, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS price_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  material_id INTEGER, quote_price REAL, cost_price REAL,
  note TEXT DEFAULT '', created_at TEXT
);
CREATE TABLE IF NOT EXISTS suppliers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, contact TEXT DEFAULT '', phone TEXT DEFAULT '', note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS custom_extras (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE, name TEXT, name_en TEXT DEFAULT '', price REAL DEFAULT 0,
  unit TEXT DEFAULT 'pcs', basis TEXT DEFAULT 'qty', cats TEXT DEFAULT '',
  note TEXT DEFAULT '', enabled INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS custom_floors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE, name_en TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS config_overlay (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    json TEXT NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quote_id INTEGER, item_id INTEGER, path TEXT, kind TEXT DEFAULT 'image',
  created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_quote ON quote_items(quote_id);
CREATE INDEX IF NOT EXISTS idx_quotes_updated ON quotes(updated_at);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------- 价格配置
_pricing_cache: Dict[str, Any] = {"mtime": 0.0, "raw": None}


def pricing_raw() -> Dict[str, Any]:
    mtime = os.path.getmtime(PRICING_PATH)
    if _pricing_cache["raw"] is None or _pricing_cache["mtime"] != mtime:
        with open(PRICING_PATH, "r", encoding="utf-8") as f:
            _pricing_cache["raw"] = json.load(f)
        _pricing_cache["mtime"] = mtime
    return _pricing_cache["raw"]


def material_overrides(conn: sqlite3.Connection) -> Dict[Tuple[str, str], Dict[str, float]]:
    out: Dict[Tuple[str, str], Dict[str, float]] = {}
    for r in conn.execute("SELECT cat_key, mat_key, quote_price, cost_price FROM materials"):
        q, c = r["quote_price"], r["cost_price"]
        if q is None and c is None:
            continue
        d: Dict[str, float] = {}
        if q is not None:
            d["quote"] = float(q)
        if c is not None:
            d["cost"] = float(c)
        out[(r["cat_key"], r["mat_key"])] = d
    return out


def custom_extras(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM custom_extras WHERE enabled=1 ORDER BY id").fetchall()
    out = []
    for r in rows:
        cats = [c.strip() for c in (r["cats"] or "").split(",") if c.strip()]
        item = {"key": r["key"], "name": r["name"], "name_en": r["name_en"] or r["name"],
                "price": float(r["price"] or 0), "unit": r["unit"] or "pcs",
                "basis": r["basis"] or "qty", "custom": True}
        if cats:
            item["cats"] = cats
        out.append(item)
    return out


def build_config(conn: sqlite3.Connection) -> PricingConfig:
    import copy
    raw = copy.deepcopy(pricing_raw())
    for row in conn.execute("SELECT * FROM materials"):
        e = raw.get("prices", {}).get(row["cat_key"], {}).get(row["mat_key"])
        if e is not None:
            e.update(label=row["name"], label_en=row["name_en"] or "", enabled=bool(row["enabled"]))
    if raw.get("meta",{}).get("business_version") == 5:
        from server.catalogue import apply
        return PricingConfig(apply(conn,raw))
    return PricingConfig(raw, overrides=material_overrides(conn), extra_extras=custom_extras(conn))


# ---------------------------------------------------------------- 初始化 / 播种
def _code_for(cat_key: str, mat_key: str) -> str:
    return ("%s-%s" % (cat_key, mat_key)).upper().replace("_", "-")


def seed_materials(conn: sqlite3.Connection) -> None:
    """把 pricing.json 的默认价同步进材料表（只更新默认值，不动人工覆盖价）。"""
    raw = pricing_raw()
    cfg = PricingConfig(raw)
    for cat in cfg.cat_list():
        for mat_key, entry in (raw.get("prices", {}).get(cat["key"], {}) or {}).items():
            dq = cfg.default_unit_price(cat["key"], mat_key)
            dc = float(entry.get("supply", 0) or 0)
            code = _code_for(cat["key"], mat_key)
            row = conn.execute("SELECT id, default_quote, default_cost FROM materials WHERE code=?",
                               (code,)).fetchone()
            if row:
                conn.execute("UPDATE materials SET default_quote=?, default_cost=? WHERE id=?",
                             (dq, dc, row["id"]))
            else:
                conn.execute(
                    "INSERT INTO materials(code, cat_key, mat_key, name, name_en, part, unit,"
                    " default_quote, default_cost, supplier, stock_qty, safety_stock, note,"
                    " enabled, updated_at) VALUES (?,?,?,?,?,?,?,?,?,'',0,0,'',1,?)",
                    (code, cat["key"], mat_key, entry.get("label", mat_key),
                     entry.get("label_en", ""), entry.get("part", "body"),
                     entry.get("unit", "ft2"), dq, dc, now()))
    conn.commit()


def init_db() -> None:
    fresh = not os.path.exists(DB_PATH)
    with closing(connect()) as conn:
        conn.executescript(SCHEMA)
        for table, cols in {"quote_items": ["note_en", "room_note_en"], "quotes": ["note_en", "terms_en"]}.items():
            have = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
            for col in cols:
                if col not in have: conn.execute("ALTER TABLE %s ADD COLUMN %s TEXT DEFAULT ''" % (table,col))
        seed_materials(conn)
        from server.catalogue import migrate, migrate_kitchen, retire_legacy_bundles, separate_kitchen_library, migrate_kitchen_feet
        migrate(conn)
        migrate_kitchen(conn)
        retire_legacy_bundles(conn)
        separate_kitchen_library(conn,pricing_raw())
        migrate_kitchen_feet(conn)
        if fresh:
            raw = pricing_raw()
            for k, v in (("company_name", raw.get("company", {}).get("name", "")),
                         ("currency", raw.get("meta", {}).get("currency", "RM")),
                         ("quote_seq", "1")):
                conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", (k, v))
        conn.commit()


# ---------------------------------------------------------------- 设置
def get_settings(conn: sqlite3.Connection) -> Dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO settings(key, value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit()


# ---------------------------------------------------------------- 材料
def list_materials(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM materials ORDER BY cat_key, part, id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["enabled"] = bool(d["enabled"])
        d["quote_price_effective"] = d["quote_price"] if d["quote_price"] is not None \
            else d["default_quote"]
        d["cost_price_effective"] = d["cost_price"] if d["cost_price"] is not None \
            else d["default_cost"]
        d["overridden"] = d["quote_price"] is not None or d["cost_price"] is not None
        d["stock_alert"] = bool(d["safety_stock"] and d["stock_qty"] < d["safety_stock"])
        out.append(d)
    return out


def update_material(conn: sqlite3.Connection, mid: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
    if not row:
        raise KeyError("材料不存在")
    fields = {k: payload[k] for k in
              ("name", "name_en", "supplier", "note", "unit", "code")
              if k in payload}
    for k in ("stock_qty", "safety_stock"):
        if k in payload:
            fields[k] = float(payload[k] or 0)
    if "enabled" in payload:
        fields["enabled"] = 1 if payload["enabled"] else 0
    for k in ("quote_price", "cost_price"):
        if k in payload:
            v = payload[k]
            fields[k] = None if v in (None, "", "default") else float(v)
    fields["updated_at"] = now()
    sets = ", ".join("%s=?" % k for k in fields)
    conn.execute("UPDATE materials SET %s WHERE id=?" % sets, list(fields.values()) + [mid])
    if "quote_price" in payload or "cost_price" in payload:
        new = conn.execute("SELECT quote_price, cost_price FROM materials WHERE id=?",
                           (mid,)).fetchone()
        conn.execute("INSERT INTO price_versions(material_id, quote_price, cost_price, note,"
                     " created_at) VALUES (?,?,?,?,?)",
                     (mid, new["quote_price"], new["cost_price"],
                      payload.get("note_change", "手动改价"), now()))
    conn.commit()
    return dict(conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone())


def reset_material(conn: sqlite3.Connection, mid: int) -> None:
    conn.execute("UPDATE materials SET quote_price=NULL, cost_price=NULL, updated_at=? WHERE id=?",
                 (now(), mid))
    conn.commit()


def material_versions(conn: sqlite3.Connection, mid: int) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM price_versions WHERE material_id=? ORDER BY id DESC LIMIT 50", (mid,))]


# ---------------------------------------------------------------- 客户 / 项目
def list_customers(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM customers ORDER BY id DESC")]


def create_customer(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    cur = conn.execute(
        "INSERT INTO customers(name, phone, email, address, note, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (payload.get("name", "").strip(), payload.get("phone", ""),
         payload.get("email", ""), payload.get("address", ""),
         payload.get("note", ""), now()))
    conn.commit()
    return dict(conn.execute("SELECT * FROM customers WHERE id=?", (cur.lastrowid,)).fetchone())


def list_projects(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY id DESC")]


def create_project(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    cur = conn.execute(
        "INSERT INTO projects(customer_id, name, address, note, created_at) VALUES (?,?,?,?,?)",
        (payload.get("customer_id"), payload.get("name", "").strip(),
         payload.get("address", ""), payload.get("note", ""), now()))
    conn.commit()
    return dict(conn.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone())


# ---------------------------------------------------------------- 自定义增项 / 楼层
def list_custom_extras(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM custom_extras ORDER BY id")]


def upsert_custom_extra(conn: sqlite3.Connection, payload: Dict[str, Any]) -> None:
    key = payload.get("key") or ("custom_%s" % datetime.now().strftime("%H%M%S%f")[:12])
    conn.execute(
        "INSERT INTO custom_extras(key, name, name_en, price, unit, basis, cats, note, enabled)"
        " VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET"
        " name=excluded.name, name_en=excluded.name_en, price=excluded.price,"
        " unit=excluded.unit, basis=excluded.basis, cats=excluded.cats,"
        " note=excluded.note, enabled=excluded.enabled",
        (key, payload.get("name", key), payload.get("name_en", ""),
         float(payload.get("price") or 0), payload.get("unit", "pcs"),
         payload.get("basis", "qty"), payload.get("cats", ""),
         payload.get("note", ""), 1 if payload.get("enabled", True) else 0))
    conn.commit()


def delete_custom_extra(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM custom_extras WHERE key=?", (key,))
    conn.commit()


def list_floors(conn: sqlite3.Connection) -> List[Dict[str, str]]:
    out = [{"code": c, "name_en": FLOOR_EN.get(c, ""), "standard": True} for c in FLOOR_CODES]
    for r in conn.execute("SELECT * FROM custom_floors ORDER BY id"):
        out.append({"code": r["code"], "name_en": r["name_en"] or "", "standard": False})
    return out


def add_floor(conn: sqlite3.Connection, code: str, name_en: str = "") -> None:
    code = (code or "").strip()
    if not code:
        return
    conn.execute("INSERT OR IGNORE INTO custom_floors(code, name_en) VALUES (?,?)", (code, name_en))
    conn.commit()


def delete_floor(conn: sqlite3.Connection, code: str) -> None:
    conn.execute("DELETE FROM custom_floors WHERE code=?", (code,))
    conn.commit()


# ---------------------------------------------------------------- 报价单
ITEM_FIELDS = ("floor", "room", "room_note", "cat", "cab_name", "cab_name_en",
               "material", "door", "length_mm", "height_mm", "depth_mm", "qty", "unit",
               "nonstd", "apply_min_height", "unit_price", "note", "extras", "extras_size",
               "led_type", "led_qty", "led_unit", "led_price", "led_power", "led_sensor")


def _item_row_to_dict(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    d["extras"] = json.loads(d.get("extras") or "{}")
    d["extras_size"] = json.loads(d.get("extras_size") or "{}")
    d["nonstd"] = None if d["nonstd"] is None else bool(d["nonstd"])
    d["apply_min_height"] = bool(d["apply_min_height"])
    d["led_power"] = bool(d["led_power"])
    d["led_sensor"] = bool(d["led_sensor"])
    d["unit_price"] = d["unit_price"]
    return d


def _item_dict_to_row(quote_id: int, seq: int, d: Dict[str, Any]) -> tuple:
    from core.business import number
    quantity=number(d.get('qty',1),'cabinet quantity')
    if quantity<1 or quantity!=int(quantity):
        raise ValueError('Positive whole cabinet quantity required / 柜子数量须为正整数')
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    nonstd = d.get("nonstd")
    return (
        quote_id, seq,
        d.get("floor") or "GF", d.get("room") or "", d.get("room_note") or "",
        d.get("cat") or "", d.get("cab_name") or "", d.get("cab_name_en") or "",
        d.get("material") or "", d.get("door") or "",
        num(d.get("length_mm")), num(d.get("height_mm")), num(d.get("depth_mm")),
        int(num(d.get("qty")) or 1), d.get("unit") or "mm",
        None if nonstd is None else (1 if nonstd else 0),
        1 if d.get("apply_min_height", True) else 0,
        (None if d.get("unit_price") in (None, "") else num(d.get("unit_price"))),
        d.get("note") or "",
        json.dumps(d.get("extras") or {}, ensure_ascii=False),
        json.dumps(d.get("extras_size") or {}, ensure_ascii=False),
        d.get("led_type") or "none", num(d.get("led_qty")), d.get("led_unit") or "m",
        (None if d.get("led_price") in (None, "") else num(d.get("led_price"))),
        1 if d.get("led_power") else 0, 1 if d.get("led_sensor") else 0,
    )


def save_items(conn: sqlite3.Connection, quote_id: int, items: List[Dict[str, Any]], *, commit: bool = True) -> None:
    quote=get_quote(conn,quote_id)
    if quote:
        raw=config_for(conn,quote).raw
        used={i.get('cat') for i in items}
        if raw.get('meta',{}).get('business_version')==5 or any(c.get('source_key') and c['key'] in used for c in raw['categories']) or any((i.get('extras') or {}).get('glass_door') for i in items):
            conn.execute('UPDATE quotes SET pricing_snapshot_json=? WHERE id=?',(json.dumps(raw,ensure_ascii=False),quote_id))
    conn.execute("DELETE FROM quote_items WHERE quote_id=?", (quote_id,))
    sql = ("INSERT INTO quote_items(quote_id, seq, floor, room, room_note, cat, cab_name,"
           " cab_name_en, material, door, length_mm, height_mm, depth_mm, qty, unit, nonstd,"
           " apply_min_height, unit_price, note, extras, extras_size, led_type, led_qty,"
           " led_unit, led_price, led_power, led_sensor)"
           " VALUES (" + ",".join(["?"] * 27) + ")")
    for i, d in enumerate(items):
        cur = conn.execute(sql, _item_dict_to_row(quote_id, i, d))
        conn.execute("UPDATE quote_items SET note_en=?,room_note_en=? WHERE id=?", (d.get("note_en",""),d.get("room_note_en",""),cur.lastrowid))
    if commit:
        conn.commit()


def get_quote(conn: sqlite3.Connection, qid: int) -> Optional[Dict[str, Any]]:
    r = conn.execute("SELECT * FROM quotes WHERE id=?", (qid,)).fetchone()
    if not r:
        return None
    q = dict(r)
    q["locked"] = bool(q["locked"])
    q["snapshot"] = json.loads(q["snapshot_json"]) if q["snapshot_json"] else None
    q.pop("snapshot_json", None)
    q["pricing_snapshot"] = json.loads(q.pop("pricing_snapshot_json", None) or "null")
    q["items"] = [_item_row_to_dict(x) for x in conn.execute(
        "SELECT * FROM quote_items WHERE quote_id=? ORDER BY seq, id", (qid,))]
    return q


def list_quotes(conn: sqlite3.Connection, keyword: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    sql = ("SELECT q.*, (SELECT COUNT(*) FROM quote_items i WHERE i.quote_id=q.id) AS item_count,"
           " (SELECT SUM(i2.qty) FROM quote_items i2 WHERE i2.quote_id=q.id) AS qty_sum"
           " FROM quotes q")
    args: List[Any] = []
    if keyword:
        sql += " WHERE q.quote_no LIKE ? OR q.customer LIKE ? OR q.project LIKE ?"
        args = ["%%%s%%" % keyword] * 3
    sql += " ORDER BY q.updated_at DESC, q.id DESC LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in conn.execute(sql, args)]
    cfg = None
    for r in rows:
        r["locked"] = bool(r["locked"])
        snap = json.loads(r["snapshot_json"]) if r["snapshot_json"] else None
        r.pop("snapshot_json", None)
        if snap:
            r["total"] = snap.get("summary", {}).get("total", 0.0)
            continue
        if "pricing_snapshot_json" in r and r["pricing_snapshot_json"]:
            quote=get_quote(conn,r["id"])
            r["total"]=compute_for(conn,quote)["summary"]["total"]
            continue
        # 草稿没有快照：按当前价格即时算一个合计，历史列表才有金额可看
        if cfg is None:
            cfg = build_config(conn)
        items = [_item_row_to_dict(x) for x in conn.execute(
            "SELECT * FROM quote_items WHERE quote_id=? ORDER BY seq, id", (r["id"],))]
        _, summary = compute_quote(cfg, [Item.from_dict(d) for d in items],
                                   mode=r.get("mode"), discount=r.get("discount") if r.get("discount") not in (None, "") else 1.0,
                                   deposit_rate=r.get("deposit_rate") or 0.0,
                                   tax_rate=r.get("tax_rate") or 0.0)
        r["total"] = summary["total"]
    return rows


def next_quote_no(conn: sqlite3.Connection) -> str:
    today = datetime.now().strftime("%y%m%d")
    prefix = "Q%s-" % today
    row = conn.execute("SELECT quote_no FROM quotes WHERE quote_no LIKE ? ORDER BY id DESC LIMIT 1",
                       (prefix + "%",)).fetchone()
    seq = 1
    if row and row["quote_no"]:
        try:
            seq = int(row["quote_no"].split("-")[-1]) + 1
        except ValueError:
            seq = 1
    return "%s%03d" % (prefix, seq)


def create_quote(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    with conn:
        no = payload.get("quote_no") or next_quote_no(conn)
        cur = conn.execute(
            "INSERT INTO quotes(quote_no, customer_id, project_id, customer, project, address,"
            " quote_date, valid_days, mode, discount, deposit_rate, tax_rate, status, locked,"
            " version, parent_id, note, terms, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'draft',0,?,?,?,?,?,?)",
            (no, payload.get("customer_id"), payload.get("project_id"),
             payload.get("customer", ""), payload.get("project", ""), payload.get("address", ""),
             payload.get("quote_date") or datetime.now().strftime("%Y-%m-%d"),
             int(payload.get("valid_days") or 30), payload.get("mode") or build_config(conn).price_mode,
             float(payload.get("discount") if payload.get("discount") not in (None, "") else 1.0),
             float(payload.get("deposit_rate") if payload.get("deposit_rate") not in (None, "") else 0.5),
             float(payload.get("tax_rate") if payload.get("tax_rate") not in (None, "") else 0.0),
             int(payload.get("version") or 1), payload.get("parent_id"), payload.get("note", ""), payload.get("terms", ""),
             now(), now()))
        pricing = payload.get("pricing_snapshot") or build_config(conn).raw
        conn.execute("UPDATE quotes SET pricing_snapshot_json=? WHERE id=?", (json.dumps(pricing,ensure_ascii=False),cur.lastrowid))
        items = payload.get("items") or []
        if items:
            save_items(conn, cur.lastrowid, items, commit=False)
        update_quote_header(conn, cur.lastrowid, {k:payload.get(k,"") for k in ("note_en","terms_en")}, commit=False)
        quote = get_quote(conn, cur.lastrowid)
        compute_for(conn, quote)
        return quote


def update_quote_header(conn: sqlite3.Connection, qid: int, payload: Dict[str, Any], *, commit: bool = True) -> None:
    allowed = ("quote_no", "customer_id", "project_id", "customer", "project", "address",
               "quote_date", "valid_days", "mode", "discount", "deposit_rate", "tax_rate",
               "status", "note", "terms", "note_en", "terms_en")
    fields = {k: payload[k] for k in allowed if k in payload}
    if "discount" in fields:
        fields["discount"] = float(fields["discount"] if fields["discount"] not in (None, "") else 1.0)
    if "deposit_rate" in fields:
        fields["deposit_rate"] = float(fields["deposit_rate"] or 0.0)
    if "tax_rate" in fields:
        fields["tax_rate"] = float(fields["tax_rate"] or 0.0)
    if "valid_days" in fields:
        fields["valid_days"] = int(fields["valid_days"] or 30)
    if not fields:
        return
    fields["updated_at"] = now()
    sets = ", ".join("%s=?" % k for k in fields)
    conn.execute("UPDATE quotes SET %s WHERE id=?" % sets, list(fields.values()) + [qid])
    if commit:
        conn.commit()


def config_for(conn,quote):
    snapshot=quote.get('snapshot') or {}
    if quote.get('locked') and snapshot.get('pricing'):
        overrides={(e['cat'],e['mat']):{k:v for k,v in e.items() if k in ('quote','cost')} for e in snapshot.get('overrides',[])}
        return PricingConfig(snapshot['pricing'],overrides=overrides)
    raw = quote.get("pricing_snapshot")
    if raw:
        from . import catalogue
        current=build_config(conn).raw
        if raw.get('meta',{}).get('business_version')==5:
            import copy
            raw=copy.deepcopy(raw)
            known={c['key'] for c in raw['categories']}
            raw['categories'].extend(copy.deepcopy(c) for c in current['categories'] if c['key'] not in known)
            for cat,entries in current['prices'].items():
                table=raw['prices'].setdefault(cat,{})
                for key,e in entries.items():
                    if key not in table:table[key]=copy.deepcopy(e)
            known={e['key'] for e in raw['extras']['items']}
            raw['extras']['items'].extend(copy.deepcopy(e) for e in current['extras']['items'] if e['key'] not in known)
        raw=catalogue.extend_historical_kitchen(raw,current)
        return PricingConfig(catalogue.include_glass_option(raw,current,quote.get('items',[])))
    return build_config(conn)

def compute_for(conn: sqlite3.Connection, quote: Dict[str, Any]) -> Dict[str, Any]:
    """返回 {lines, summary}；已锁价报价直接返回快照，不重算。"""
    if quote.get("locked") and quote.get("snapshot"):
        snap = quote["snapshot"]
        return {"lines": snap.get("lines", []), "summary": snap.get("summary", {}),
                "locked": True, "snapshot_at": snap.get("at")}
    cfg = config_for(conn,quote)
    items = [Item.from_dict(d) for d in quote.get("items", [])]
    lines, summary = compute_quote(
        cfg, items, mode=quote.get("mode"),
        discount=quote.get("discount", 1.0),
        deposit_rate=quote.get("deposit_rate", 0.5),
        tax_rate=quote.get("tax_rate", 0.0))
    return {"lines": [l.to_dict() for l in lines], "summary": summary, "locked": False}


def lock_quote(conn: sqlite3.Connection, qid: int) -> Dict[str, Any]:
    quote = get_quote(conn, qid)
    if not quote:
        raise KeyError("报价不存在")
    data = compute_for(conn, dict(quote, locked=False, snapshot=None))
    snap = {"at": now(), "lines": data["lines"], "summary": data["summary"],
            "mode": quote.get("mode"), "discount": quote.get("discount"),
            "deposit_rate": quote.get("deposit_rate"), "tax_rate": quote.get("tax_rate"),
            "pricing": config_for(conn,quote).raw, "overrides": []}
    conn.execute("UPDATE quotes SET locked=1, status='issued', snapshot_json=?, updated_at=?"
                 " WHERE id=?", (json.dumps(snap, ensure_ascii=False), now(), qid))
    conn.commit()
    return get_quote(conn, qid)


def unlock_quote(conn: sqlite3.Connection, qid: int) -> None:
    conn.execute("UPDATE quotes SET locked=0, status='draft', snapshot_json=NULL, updated_at=?"
                 " WHERE id=?", (now(), qid))
    conn.commit()


def duplicate_quote(conn: sqlite3.Connection, qid: int) -> Dict[str, Any]:
    quote = get_quote(conn, qid)
    if not quote:
        raise KeyError("报价不存在")
    payload = dict(quote)
    import copy
    cfg=config_for(conn,quote)
    raw=copy.deepcopy(cfg.raw)
    for (cat,mat),values in cfg.overrides.items():
        e=raw.get('prices',{}).get(cat,{}).get(mat)
        if e:
            if 'quote' in values:e['market']=[values['quote']]*2
            if 'cost' in values:e['supply']=values['cost']
    payload['pricing_snapshot']=raw
    payload["quote_no"] = next_quote_no(conn)
    payload["parent_id"] = qid
    payload["version"] = int(quote.get("version") or 1) + 1
    payload["status"] = "draft"
    payload["customer"] = quote.get("customer", "")
    payload["project"] = quote.get("project", "")
    payload["items"] = quote.get("items", [])
    new = create_quote(conn, payload)
    return new


def delete_quote(conn: sqlite3.Connection, qid: int) -> None:
    conn.execute("DELETE FROM quote_items WHERE quote_id=?", (qid,))
    conn.execute("DELETE FROM quotes WHERE id=?", (qid,))
    conn.commit()


def save_attachment(conn: sqlite3.Connection, quote_id: int, path: str,
                    kind: str = "image") -> None:
    conn.execute("INSERT INTO attachments(quote_id, path, kind, created_at) VALUES (?,?,?,?)",
                 (quote_id, path, kind, now()))
    conn.commit()


def stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    q = conn.execute("SELECT COUNT(*) c FROM quotes").fetchone()["c"]
    c = conn.execute("SELECT COUNT(*) c FROM customers").fetchone()["c"]
    m = conn.execute("SELECT COUNT(*) c FROM materials").fetchone()["c"]
    alert = conn.execute("SELECT COUNT(*) c FROM materials WHERE safety_stock>0 AND"
                         " stock_qty<safety_stock").fetchone()["c"]
    return {"quotes": q, "customers": c, "materials": m, "stock_alert": alert}
