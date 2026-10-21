# -*- coding: utf-8 -*-
"""
本地 HTTP 服务（仅依赖标准库）
=============================
为桌面端界面提供 JSON API + 静态文件 + 导出下载。
只监听 127.0.0.1，不对外暴露。
"""
from __future__ import annotations

import base64
import contextlib
import json
import mimetypes
import os
import re
import subprocess
import tempfile
import threading
import traceback
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

import export as exporter
from core import Item, compute_quote
from core.config import EXPORT_DIR, UPLOAD_DIR, WEB_DIR
from core.floors import FLOOR_CODES, FLOOR_EN, normalize_floor
from core.rooms import EXTRA_ROOMS
from server import store

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".woff2": "font/woff2",
}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status
        self.message = message


# ------------------------------------------------------------------ 组装前端配置
def _rooms_with_extra(cfg) -> List[Dict[str, str]]:
    """pricing.json 的标准房间 + core.rooms.EXTRA_ROOMS（主卫 / 次卫 / 保姆房…）。

    只在**前端可选列表**里补齐，`data/pricing.json` 保持原样（md5 基准不变）。
    """
    rooms: List[Dict[str, str]] = [dict(r) for r in cfg.rooms()]
    have = {r.get("name", "") for r in rooms}
    for r in EXTRA_ROOMS:
        if r["name"] not in have:
            rooms.append(dict(r))
            have.add(r["name"])
    return rooms


def bootstrap_payload(conn) -> Dict[str, Any]:
    cfg = store.build_config(conn)
    raw = cfg.raw
    cats = []
    for cat in cfg.cat_list():
        if not cat.get("enabled",True): continue
        key = cat["key"]
        cats.append({
            **cat,
            "name_en": cfg.cat_name_en(key),
            "group_name": cfg.group_name(key),
            "group_name_en": cfg.group_name_en(key),
            "materials": [{"key": k, "label": v, "label_en": cfg.material_label_en(key, k),
                           "price": cfg.unit_price(key, k),
                           "default_price": cfg.default_unit_price(key, k),
                           "supply": cfg.supply_price(key, k),
                           "overridden": cfg.is_price_overridden(key, k),
                           "unit": cfg.price_entry(key, k).get("unit", "")}
                          for k, v in cfg.body_options(key) if cfg.price_entry(key,k).get("enabled",True)],
            "doors": [{"key": k, "label": v, "label_en": cfg.material_label_en(key, k),
                       "price": cfg.unit_price(key, k),
                       "default_price": cfg.default_unit_price(key, k),
                       "supply": cfg.supply_price(key, k),
                       "overridden": cfg.is_price_overridden(key, k),
                       "unit": cfg.price_entry(key, k).get("unit", "")}
                      for k, v in cfg.door_options(key) if cfg.price_entry(key,k).get("enabled",True)],
            "extras": [{"key": e.get("key"), "name": e.get("name"),
                        "name_en": e.get("name_en", ""), "price": e.get("price", 0),
                        "unit": e.get("unit", "pcs"), "basis": e.get("basis", "qty"),
                        "note": e.get("note", ""), "custom": bool(e.get("custom"))}
                       for e in cfg.extras_for(key)],
        })
    return {
        "meta": cfg.meta,
        "currency": cfg.currency,
        "version": cfg.version,
        "mm_per_ft": cfg.mm_per_ft,
        "nonstd_factor": cfg.nonstd_factor,
        "price_modes": raw.get("meta", {}).get("price_modes", {}),
        "price_modes_en": raw.get("meta", {}).get("price_modes_en", {}),
        "categories": cats,
        "rooms": _rooms_with_extra(cfg),
        "floors": store.list_floors(conn),
        "floor_codes": FLOOR_CODES,
        "floor_en": FLOOR_EN,
        "led": cfg.led_meta(),
        "extras_all": cfg.extras_items(),
        "company": cfg.company(),
        "remark": cfg.remark(),
        "settings": store.get_settings(conn),
        "stats": store.stats(conn),
        "units": [{"key": "mm", "name": "mm"}, {"key": "cm", "name": "cm"},
                  {"key": "inch", "name": "inch"}, {"key": "ft", "name": "ft"}],
        "defaults": {"discount": 1.0, "deposit_rate": 0.5, "tax_rate": 0.0,
                     "valid_days": 30, "mode": cfg.price_mode},
    }


def _compute(conn, items: List[Dict], header: Dict) -> Dict[str, Any]:
    cfg = store.build_config(conn)
    objs = [Item.from_dict(d) for d in (items or [])]
    lines, summary = compute_quote(
        cfg, objs, mode=header.get("mode"),
        discount=header.get("discount", 1.0),
        deposit_rate=header.get("deposit_rate", 0.5),
        tax_rate=header.get("tax_rate", 0.0))
    return {"lines": [l.to_dict() for l in lines], "summary": summary, "locked": False}


# ------------------------------------------------------------------ OCR（可选）
def _ocr_dims(image_bytes: bytes) -> Dict[str, Any]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(UPLOAD_DIR, "paste_%s.png" % ts)
    with open(path, "wb") as f:
        f.write(image_bytes)
    exe = None
    for cand in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if os.path.exists(cand):
            exe = cand
            break
    if not exe:
        return {"ok": False, "saved": path,
                "reason": "未检测到本机 OCR 引擎（Tesseract），图片已保存，请手动确认尺寸"}
    try:
        out = subprocess.run([exe, path, "stdout", "--psm", "6", "-l", "eng"],
                             capture_output=True, timeout=40)
        text = out.stdout.decode("utf-8", "ignore")
    except Exception as exc:
        return {"ok": False, "saved": path, "reason": "OCR 执行失败：%s" % exc}
    nums = [float(n) for n in re.findall(r"\d{2,5}(?:\.\d+)?", text)]
    return {"ok": True, "saved": path, "text": text.strip()[:2000],
            "numbers": nums[:40]}


# ------------------------------------------------------------------ 路由
ROUTES: List[Tuple[str, re.Pattern, str]] = []


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, re.compile("^%s$" % pattern), fn.__name__))
        return fn
    return deco


@route("GET", r"/api/bootstrap")
def api_bootstrap(conn, m, body, q):
    return bootstrap_payload(conn)


@route("POST", r"/api/compute")
def api_compute(conn, m, body, q):
    return _compute(conn, body.get("items") or [], body.get("header") or {})


@route("GET", r"/api/quotes")
def api_quotes(conn, m, body, q):
    return {"quotes": store.list_quotes(conn, q.get("q", [""])[0])}


@route("POST", r"/api/quotes")
def api_quote_create(conn, m, body, q):
    quote = store.create_quote(conn, body or {})
    return {"quote": quote, "computed": store.compute_for(conn, quote)}


@route("GET", r"/api/quotes/(\d+)")
def api_quote_get(conn, m, body, q):
    quote = store.get_quote(conn, int(m.group(1)))
    if not quote:
        raise ApiError("报价不存在", 404)
    return {"quote": quote, "computed": store.compute_for(conn, quote)}


@route("PUT", r"/api/quotes/(\d+)")
def api_quote_save(conn, m, body, q):
    qid = int(m.group(1))
    quote = store.get_quote(conn, qid)
    if not quote:
        raise ApiError("报价不存在", 404)
    header = body.get("header") or {}
    if quote.get("locked"):
        raise ApiError("Unlock quotation before editing / 请先解锁报价再修改",409)
    store.update_quote_header(conn, qid, header)
    if "items" in body:
        store.save_items(conn, qid, body.get("items") or [])
    quote = store.get_quote(conn, qid)
    return {"quote": quote, "computed": store.compute_for(conn, quote)}


@route("DELETE", r"/api/quotes/(\d+)")
def api_quote_delete(conn, m, body, q):
    store.delete_quote(conn, int(m.group(1)))
    return {"ok": True}


@route("POST", r"/api/quotes/(\d+)/lock")
def api_quote_lock(conn, m, body, q):
    quote = store.lock_quote(conn, int(m.group(1)))
    return {"quote": quote, "computed": store.compute_for(conn, quote)}


@route("POST", r"/api/quotes/(\d+)/unlock")
def api_quote_unlock(conn, m, body, q):
    qid = int(m.group(1))
    store.unlock_quote(conn, qid)
    quote = store.get_quote(conn, qid)
    return {"quote": quote, "computed": store.compute_for(conn, quote)}


@route("POST", r"/api/quotes/(\d+)/duplicate")
def api_quote_dup(conn, m, body, q):
    quote = store.duplicate_quote(conn, int(m.group(1)))
    return {"quote": quote, "computed": store.compute_for(conn, quote)}


@route("GET", r"/api/materials")
def api_materials(conn, m, body, q):
    return {"materials": store.list_materials(conn)}


@route("PUT", r"/api/materials/(\d+)")
def api_material_update(conn, m, body, q):
    return {"material": store.update_material(conn, int(m.group(1)), body or {})}


@route("POST", r"/api/materials/(\d+)/reset")
def api_material_reset(conn, m, body, q):
    store.reset_material(conn, int(m.group(1)))
    return {"ok": True}


@route("GET", r"/api/materials/(\d+)/versions")
def api_material_versions(conn, m, body, q):
    return {"versions": store.material_versions(conn, int(m.group(1)))}


@route("GET", r"/api/customers")
def api_customers(conn, m, body, q):
    return {"customers": store.list_customers(conn)}


@route("POST", r"/api/customers")
def api_customer_create(conn, m, body, q):
    return {"customer": store.create_customer(conn, body or {})}


@route("GET", r"/api/projects")
def api_projects(conn, m, body, q):
    return {"projects": store.list_projects(conn)}


@route("POST", r"/api/projects")
def api_project_create(conn, m, body, q):
    return {"project": store.create_project(conn, body or {})}


@route("GET", r"/api/extras")
def api_extras(conn, m, body, q):
    return {"extras": store.list_custom_extras(conn)}


@route("POST", r"/api/extras")
def api_extra_save(conn, m, body, q):
    store.upsert_custom_extra(conn, body or {})
    return {"ok": True}


@route("DELETE", r"/api/extras/(.+)")
def api_extra_delete(conn, m, body, q):
    store.delete_custom_extra(conn, urllib.parse.unquote(m.group(1)))
    return {"ok": True}


@route("GET", r"/api/floors")
def api_floors(conn, m, body, q):
    return {"floors": store.list_floors(conn)}


@route("POST", r"/api/floors")
def api_floor_add(conn, m, body, q):
    store.add_floor(conn, (body or {}).get("code", ""), (body or {}).get("name_en", ""))
    return {"floors": store.list_floors(conn)}


@route("DELETE", r"/api/floors/(.+)")
def api_floor_delete(conn, m, body, q):
    store.delete_floor(conn, urllib.parse.unquote(m.group(1)))
    return {"floors": store.list_floors(conn)}


@route("GET", r"/api/settings")
def api_settings(conn, m, body, q):
    return {"settings": store.get_settings(conn)}


@route("PUT", r"/api/settings")
def api_settings_put(conn, m, body, q):
    for k, v in (body or {}).items():
        store.set_setting(conn, k, v)
    return {"settings": store.get_settings(conn)}


@route("POST", r"/api/ocr/dims")
def api_ocr(conn, m, body, q):
    data = (body or {}).get("image", "")
    if "," in data:
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data)
    except Exception:
        raise ApiError("图片数据无效")
    return _ocr_dims(raw)


def _export_quote(conn, qid: int, kind: str, fmt: str) -> Tuple[str, str]:
    quote = store.get_quote(conn, qid)
    if not quote:
        raise ApiError("报价不存在", 404)
    data = store.compute_for(conn, quote)
    cfg = store.export_config(conn, quote)
    if data.get("locked"):
        from core.engine import LineResult
        lines = [LineResult(**l) for l in data["lines"]]
        summary = data["summary"]
    else:
        from core.engine import LineResult
        lines = [LineResult(**l) for l in data["lines"]]
        summary = data["summary"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "xlsx":
        name = exporter.default_filename(quote, kind)
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        path = os.path.join(EXPORT_DIR, "%s_%s" % (stamp, name))
        exporter.export_workbook(path, cfg, quote, lines, summary, kind=kind)
        return path, name
    # PDF：先渲染打印页 → headless 打印
    html = exporter.render_print_html(quote, lines, summary, cfg, kind=kind)
    html_path = os.path.join(EXPORT_DIR, "print_%s_%s.html" % (qid, stamp))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    name = "%s_%s_%s.pdf" % ((quote.get("quote_no") or "quote").replace("/", "-"),
                             quote.get("customer") or "客户",
                             "客户版" if kind == "customer" else "内部版")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    path = os.path.join(EXPORT_DIR, "%s_%s" % (stamp, name))
    url = "http://127.0.0.1:%d/print/%d?kind=%s" % (PORT, qid, kind)
    if exporter.html_to_pdf(url, path):
        return path, name
    raise ApiError("本机未找到可用的 Edge/Chrome，无法直接生成 PDF；"
                   "可改用「打印」按钮，在浏览器打印对话框里选「另存为 PDF」", 501)


@route("GET", r"/api/quotes/(\d+)/export")
def api_export(conn, m, body, q):
    qid = int(m.group(1))
    kind = (q.get("kind", ["customer"])[0] or "customer").lower()
    fmt = (q.get("fmt", ["xlsx"])[0] or "xlsx").lower()
    path, name = _export_quote(conn, qid, kind, fmt)
    return {"ok": True, "file": os.path.basename(path), "name": name,
            "url": "/api/download?f=%s" % urllib.parse.quote(os.path.basename(path))}


@route("GET", r"/api/download")
def api_download(conn, m, body, q):
    name = q.get("f", [""])[0]
    safe = os.path.basename(name)
    path = os.path.join(EXPORT_DIR, safe)
    if not os.path.exists(path):
        raise ApiError("文件不存在", 404)
    return {"__file__": path, "__name__": safe}


@route("GET", r"/api/health")
def api_health(conn, m, body, q):
    return {"ok": True, "time": datetime.now().isoformat(timespec="seconds")}


class Handler(BaseHTTPRequestHandler):
    server_version = "Whole-House-Customization/3.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):   # 安静模式
        pass

    # ---------------- 工具 ----------------
    def _send(self, status: int, body: bytes, ctype: str,
              extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _file(self, path: str, download_name: Optional[str] = None) -> None:
        if not os.path.exists(path):
            self._json({"error": "not found"}, 404)
            return
        ctype = MIME.get(os.path.splitext(path)[1].lower()) or \
            mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        extra = {}
        if download_name:
            extra["Content-Disposition"] = "attachment; filename*=UTF-8''%s" % \
                urllib.parse.quote(download_name)
        self._send(200, data, ctype, extra)

    # ---------------- 请求分发 ----------------
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                self._handle_api(method, path, query)
            elif path.startswith("/print/"):
                self._handle_print(path, query)
            elif path in ("/", "/index.html"):
                self._file(os.path.join(WEB_DIR, "studio.html"))
            else:
                self._handle_static(path)
        except ApiError as exc:
            self._json({"error": exc.message}, exc.status)
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc()
            self._json({"error": "Operation failed / 操作失败", "detail": traceback.format_exc(limit=3)}, 500)

    def _handle_api(self, method: str, path: str, query):
        for m_method, pattern, fn_name in ROUTES:
            if m_method != method:
                continue
            m = pattern.match(path)
            if not m:
                continue
            body = self._read_body()
            fn = globals()[fn_name]
            with contextlib.closing(store.connect()) as conn:
                result = fn(conn, m, body, query)
            if isinstance(result, dict) and "__file__" in result:
                self._file(result["__file__"], result["__name__"])
            else:
                self._json(result)
            return
        self._json({"error": "未知接口 %s" % path}, 404)

    def _handle_print(self, path: str, query):
        m = re.match(r"^/print/(\d+)$", path)
        if not m:
            self._json({"error": "not found"}, 404)
            return
        with contextlib.closing(store.connect()) as conn:
            quote = store.get_quote(conn, int(m.group(1)))
            if not quote:
                self._json({"error": "报价不存在"}, 404)
                return
            data = store.compute_for(conn, quote)
            cfg = store.export_config(conn, quote)
        from core.engine import LineResult
        lines = [LineResult(**l) for l in data["lines"]]
        kind = (query.get("kind", ["customer"])[0] or "customer").lower()
        html = exporter.render_print_html(quote, lines, data["summary"], cfg, kind=kind,
                                         auto_print=(query.get("auto", ["0"])[0] == "1"))
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _handle_static(self, path: str):
        rel = urllib.parse.unquote(path.lstrip("/"))
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if os.path.commonpath([full, os.path.normpath(WEB_DIR)]) != os.path.normpath(WEB_DIR):
            self._json({"error": "forbidden"}, 403)
            return
        self._file(full)

    def _read_body(self) -> Dict[str, Any]:
        if self.headers.get("Origin") and self.headers.get("Origin") != "http://"+self.headers.get("Host", ""):
            raise ApiError("Local requests only / 仅接受本机请求",403)
        length = int(self.headers.get("Content-Length") or 0)
        if length > 32*1024*1024: raise ApiError("File too large (32 MB) / 文件超过32MB",413)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            raise ApiError("请求体不是合法 JSON")


import sys
from server.independent import install
install(sys.modules[__name__])

PORT = 8878


def serve(port: int = PORT, open_browser: bool = True) -> None:
    global PORT
    PORT = port
    store.init_db()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    from core.config import DATA_DIR
    with open(os.path.join(DATA_DIR,"server.json"),"w") as f: json.dump({"port":port,"pid":os.getpid()},f)
    globals()["SERVER"] = httpd
    url = "http://127.0.0.1:%d/" % port
    print("=" * 62)
    print(" Whole-House Customization Quotation Studio v3 / 全屋定制报价独立版  ·  %s" % url)
    print(" 关闭此窗口即退出。数据保存在 data/app.db")
    print("=" * 62)
    if open_browser:
        threading.Timer(0.6, lambda: _open_app_window(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def _open_app_window(url: str) -> None:
    """优先用 Edge/Chrome 的 --app 模式开一个无地址栏窗口，像桌面应用。"""
    browser = exporter.find_browser()
    if browser:
        try:
            subprocess.Popen([browser, "--app=%s" % url, "--window-size=1440,960",
                              "--user-data-dir=%s" % os.path.join(
                                  tempfile.gettempdir(), "whole_house_customization_independent_v3_profile")])
            return
        except Exception:
            pass
    import webbrowser
    webbrowser.open(url)
