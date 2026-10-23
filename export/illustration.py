# -*- coding: utf-8 -*-
"""
柜体示意图生成器（Pillow 手绘 + 白色柜体样板图，无第三方绘图库依赖）
=====================================================================
按「柜型 + 实际长高深」画一张带尺寸标注的示意图，供 Excel 报价单 /
PDF / 打印页的 PICTURE 图片列使用。

对外主入口：
    render(kind, w_mm, h_mm, d_mm, out_path,
           mm_per_ft=304.8, dim_unit="mm",
           cab_name="", cab_name_en="") -> str

kind 支持（白色样板图）：balcony / tv / altar / shoe / dressing_table /
    book_desk / bookcase / wine / kitchen / island / low_cabinet / wardrobe
kind 支持（手绘兜底）：kitchen_base / kitchen_wall / panel / quartz / sink /
    vanity / storage / study / cabinet

样板图取自 assets/white_models 的 12 张白色柜体实拍/渲染图，保持原比例贴入
480x320 画布（不拉伸），尺寸仍按实际长高深标注。样板图缺失或柜型不在 12 类内时，
自动退回原来的手绘示意图，不影响导出。

旧 key 兼容：custom_cabinet（按柜体名称再分流）、base_cabinet→kitchen_base、
wall_cabinet→kitchen_wall、wall_panel→panel、fridge→cabinet。

尺寸标注一律带箭头，文字形如 "W 2400mm" / "H 2400mm" / "D 600mm"。
画布固定 480x320（Excel 里按 176x117 显示）。
"""
from __future__ import annotations

import math
import os
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

# ---------------- 白色柜体样板图 ----------------
ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "assets", "white_models")

# 12 类白色样板图：柜型 key → assets/white_models 下的文件名。顺序与样板图一致。
MODEL_ASSETS = {
    "balcony": "balcony.png",
    "tv": "tv.png",
    "altar": "altar.png",
    "shoe": "shoe.png",
    "dressing_table": "dressing_table.png",
    "book_desk": "book_desk.png",
    "bookcase": "bookcase.png",
    "wine": "wine.png",
    "kitchen": "kitchen.png",
    "island": "island.png",
    "low_cabinet": "low_cabinet.png",
    "wardrobe": "wardrobe.png",
}

# ---------------- 画布 ----------------
CW, CH = 480, 320

# ---------------- 配色（白色柜体 + 中性灰标注，与白色样板图同色系） ----------------
BODY_FRONT = (250, 250, 250)
BODY_SIDE = (238, 239, 241)
BODY_TOP = (255, 255, 255)
EDGE = (196, 200, 206)
SEAM = (214, 217, 222)
HANDLE = (176, 181, 188)
INSIDE = (240, 241, 243)     # 开放格内部
INSIDE_SHADOW = (224, 226, 230)
SLAB = (252, 252, 252)
SLAB_EDGE = (198, 202, 208)
STEEL = (176, 180, 184)
GLASS = (226, 233, 238)
DIM_LINE = (140, 140, 148)
DIM_TEXT = (88, 88, 96)
BG = (255, 255, 255, 0)

# 画法版本：改绘图逻辑时 +1，缓存文件名带版本，避免复用旧图（旧图不会自动失效）
# v6：12 类改用 assets/white_models 白色样板图（v5 及以前为木色手绘图）
PIC_VERSION = "v6"

_FONT_PATHS = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]
_font_cache: dict = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    if size in _font_cache:
        return _font_cache[size]
    f = None
    for p in _FONT_PATHS:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                break
            except Exception:
                continue
    if f is None:
        f = ImageFont.load_default()
    _font_cache[size] = f
    return f


# ---------------- 柜型 ----------------
KIND_LABEL = {
    "wardrobe": "WARDROBE",
    "shoe": "SHOE CABINET",
    "tv": "TV CABINET",
    "study": "STUDY CABINET",
    "book_desk": "STUDY DESK",
    "bookcase": "BOOKCASE",
    "dressing_table": "DRESSING TABLE",
    "altar": "ALTAR CABINET",
    "island": "KITCHEN ISLAND",
    "wine": "WINE CABINET",
    "low_cabinet": "LOW CABINET",
    "kitchen": "KITCHEN CABINET",
    "vanity": "VANITY CABINET",
    "balcony": "BALCONY CABINET",
    "storage": "STORAGE CABINET",
    "kitchen_base": "BASE CABINET",
    "kitchen_wall": "WALL CABINET",
    "panel": "WALL PANEL",
    "quartz": "QUARTZ TOP",
    "sink": "SINK",
    "cabinet": "CABINET",
}

# 品类 key 已经指明具体柜型的，必须先于名称关键字判定：
# 「吊柜 / 地柜 / 护墙板 / 台面 / 水槽」不能被「橱柜 / kitchen cabinet」这类宽泛词覆盖。
_CATEGORY_KIND = {
    "base_cabinet": "kitchen_base",
    "wall_cabinet": "kitchen_wall",
    "wall_panel": "panel",
    "kitchen_base": "kitchen_base",
    "kitchen_wall": "kitchen_wall",
    "panel": "panel",
    "quartz": "quartz",
    "sink": "sink",
}

# 名称关键字 → 柜型（先英文后中文；具体柜型必须先于「橱柜 / kitchen cabinet」这类宽泛词，
# 否则「Kitchen cabinet sink」「橱柜护墙板」会被整张橱柜图覆盖）
_KIND_RULES = [
    ("dressing_table", ("dressing table", "makeup table", "vanity table", "梳妆台", "妆台")),
    ("book_desk", ("study desk", "writing desk", "book desk", "书台", "书桌")),
    ("bookcase", ("bookcase", "bookshelf", "书柜")),
    ("altar", ("altar cabinet", "altar table", "神台柜", "神台", "神龛", "佛龛", "供桌")),
    ("island", ("kitchen island", "island cabinet", "岛台")),
    ("low_cabinet", ("low cabinet", "矮柜")),
    ("wine", ("wine cabinet", "wine rack", "酒柜")),
    ("balcony", ("balcony cabinet", "阳台柜")),
    ("tv", ("tv cabinet", "tv unit", "tv console", "television cabinet", "media cabinet",
            "media console", "电视柜")),
    # 具体橱柜类型与平板类材料：先于宽泛的 kitchen / 橱柜
    ("kitchen_base", ("base cabinet", "kitchen base", "地柜", "底柜")),
    ("kitchen_wall", ("wall cabinet", "upper cabinet", "吊柜", "墙柜")),
    ("sink", ("kitchen sink", "sink", "水槽")),
    ("quartz", ("quartz", "stone top", "countertop", "石英石", "台面")),
    ("panel", ("wall panel", "panelling", "paneling", "护墙板", "墙板")),
    ("kitchen", ("kitchen cabinet", "kitchen cupboard", "橱柜")),
    ("wardrobe", ("wardrobe", "walk-in", "closet", "衣柜", "衣帽间")),
    ("shoe", ("shoe cabinet", "shoe rack", "shoe", "鞋柜")),
    ("balcony", ("balcony", "laundry", "阳台")),
    ("vanity", ("bathroom vanity", "bathroom cabinet", "washbasin", "vanity", "basin",
                "浴室柜", "洗手台", "洗手盆")),
    ("study", ("study cabinet", "study", "书房柜")),
    ("storage", ("storage", "sideboard", "餐边柜", "储物柜", "杂物柜")),
]

_DIRECT_KIND = {
    "wall_panel": "panel",
    "base_cabinet": "kitchen_base",
    "wall_cabinet": "kitchen_wall",
    "quartz": "quartz",
    "sink": "sink",
    "wardrobe": "wardrobe",
    "shoe": "shoe",
    "tv": "tv",
    "study": "study",
    "vanity": "vanity",
    "balcony": "balcony",
    "storage": "storage",
    "kitchen": "kitchen",
    "fridge": "cabinet",
    "cabinet": "cabinet",
}


def resolve_kind(cat_key: str, cab_name: str = "", cab_name_en: str = "") -> str:
    """把「品类 key + 柜体名称」解析成绘图柜型。

    判定顺序：具体品类 key（吊柜/地柜/护墙板/台面/水槽）→ 柜体名称关键字
    （具体柜型先于宽泛的「橱柜 / kitchen cabinet」）→ 其余品类 key 直映 →
    柜型 key 自身 → 普通柜体。中英文名称统一小写比较，忽略首尾空白。
    """
    key = (cat_key or "").strip()
    if key in _CATEGORY_KIND:
        return _CATEGORY_KIND[key]
    hay = " ".join([(cab_name_en or "").lower(), (cab_name or "").lower()]).strip()
    if hay:
        for kind, words in _KIND_RULES:
            for w in words:
                if w in hay:
                    return kind
    if key in _DIRECT_KIND:
        return _DIRECT_KIND[key]
    if key in _PAINTERS:          # panel / kitchen_base / kitchen_wall … 自映射
        return key
    # custom_cabinet 且名称没命中任何关键字 → 普通柜体
    return "cabinet"


def model_asset(kind: str) -> str:
    """返回该柜型对应的白色样板图路径；不在 12 类内或文件缺失时返回空串。"""
    name = MODEL_ASSETS.get((kind or "").strip())
    if not name:
        return ""
    path = os.path.join(ASSET_DIR, name)
    return path if os.path.isfile(path) else ""


def kind_label(kind: str) -> str:
    return KIND_LABEL.get(kind, "CABINET")


# ---------------- 文字 / 尺寸标注 ----------------
def _fmt_ft(v: float) -> str:
    if abs(v - round(v)) < 0.06:
        return "%dft" % int(round(v))
    return "%.1fft" % v


def _fmt_mm(v: float) -> str:
    return "%dmm" % int(round(v))


def _dim_label(prefix: str, v: float, unit: str = "mm") -> str:
    """'W' + 2400 + mm → 'W 2400mm'。"""
    return "%s %s" % (prefix, _fmt_mm(v) if unit == "mm" else _fmt_ft(v))


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _rot_text(img: Image.Image, cx: float, cy: float, text: str, font,
              fill, angle: int = 90) -> None:
    """把文字渲染到透明层、旋转后贴到 (cx, cy) 中心。"""
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    w, h = _text_size(d, text, font)
    tmp = Image.new("RGBA", (max(1, w + 8), max(1, h + 8)), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    d.text((4, 4 - d.textbbox((0, 0), text, font=font)[1]), text, font=font, fill=fill)
    tmp = tmp.rotate(angle, expand=True, resample=Image.BICUBIC)
    img.paste(tmp, (int(cx - tmp.width / 2), int(cy - tmp.height / 2)), tmp)


def _arrow(draw, x: float, y: float, ux: float, uy: float, size: float = 4.6) -> None:
    """箭头：尖端在 (x,y)，指向单位向量 (ux,uy)。"""
    px, py = -uy, ux
    draw.polygon([(x, y),
                  (x - ux * size + px * size * 0.55, y - uy * size + py * size * 0.55),
                  (x - ux * size - px * size * 0.55, y - uy * size - py * size * 0.55)],
                 fill=DIM_LINE)


def _dim_h(img, draw, x1: float, x2: float, y: float, y_from: float,
           text: str, font) -> Tuple[float, float, float, float]:
    """水平尺寸线（标注宽度）：两端向外箭头 + 引出线 + 下方文字。

    返回文字矩形 (x1,y1,x2,y2)，供进深标注避让。
    """
    draw.line([(x1, y), (x2, y)], fill=DIM_LINE, width=1)
    # 引出线：从柜体底边延伸到尺寸线
    for x in (x1, x2):
        draw.line([(x, y_from), (x, y + 4)], fill=(210, 210, 216), width=1)
    _arrow(draw, x1, y, -1, 0)
    _arrow(draw, x2, y, 1, 0)
    w, h = _text_size(draw, text, font)
    tx, ty = (x1 + x2) / 2 - w / 2, y + 8
    draw.text((tx, ty), text, font=font, fill=DIM_TEXT)
    return (tx, ty, tx + w, ty + h)


def _dim_v(img, draw, y1: float, y2: float, x: float, x_from: float,
           text: str, font) -> None:
    """垂直尺寸线（标注高度）：文字旋转 90°。"""
    draw.line([(x, y1), (x, y2)], fill=DIM_LINE, width=1)
    for y in (y1, y2):
        draw.line([(x_from, y), (x - 4, y)], fill=(210, 210, 216), width=1)
    _arrow(draw, x, y1, 0, -1)
    _arrow(draw, x, y2, 0, 1)
    _rot_text(img, x - 15, (y1 + y2) / 2, text, font, DIM_TEXT, 90)


def _dim_depth(img, draw, x1: float, y1: float, x2: float, y2: float,
               text: str, font, off: float = 18.0, avoid=None) -> None:
    """进深尺寸线：沿「前角 → 后角」的斜边向外偏 off 像素。

    与顶面斜边的写法不同，进深线画在**侧下方**并整体外移，两端箭头 + 引出线 +
    水平文字（不旋转），保证 176px 显示时「深」这一维依然读得出来。

    avoid: 已有其它标注的文字矩形 (x1,y1,x2,y2)，重叠时把文字上移避让。
    """
    vx, vy = x2 - x1, y2 - y1
    ln = math.hypot(vx, vy) or 1.0
    ux, uy = vx / ln, vy / ln
    nx, ny = -uy, ux                      # 法向量
    if nx < 0:                            # 取指向柜体外侧（右下）的那一侧
        nx, ny = -nx, -ny
    ax, ay = x1 + nx * off, y1 + ny * off
    bx, by = x2 + nx * off, y2 + ny * off
    # 引出线（浅灰，从柜体真实角点拉到尺寸线）
    draw.line([(x1, y1), (ax, ay)], fill=(206, 206, 212), width=1)
    draw.line([(x2, y2), (bx, by)], fill=(206, 206, 212), width=1)
    # 尺寸线 + 两端箭头
    draw.line([(ax, ay), (bx, by)], fill=DIM_LINE, width=1)
    _arrow(draw, ax, ay, -ux, -uy)
    _arrow(draw, bx, by, ux, uy)
    # 文字：尺寸线外侧再偏 15px，水平摆放并收敛在画布内
    tw, th = _text_size(draw, text, font)
    mx, my = (ax + bx) / 2, (ay + by) / 2
    lx = mx + nx * 15 - tw / 2
    ly = my + ny * 15 - th / 2
    lx = min(max(lx, 4.0), CW - tw - 4.0)
    ly = min(max(ly, 4.0), CH - th - 6.0)
    if avoid:                             # 与宽度标注重叠 → 上移
        ax1, ay1, ax2, ay2 = avoid
        for _ in range(6):
            hit = not (lx + tw < ax1 or lx > ax2 or ly + th < ay1 or ly > ay2)
            if not hit:
                break
            ly = max(ly - (th + 8), 4.0)
    draw.text((lx, ly), text, font=font, fill=DIM_TEXT)
    return (lx, ly, lx + tw, ly + th)


# ---------------- 基础形体 ----------------
def _box(draw, ox: float, oy: float, W: float, H: float, dx: float, dy: float,
         *, legs: bool = True, doors: int = 0, handles: bool = True,
         handle_frac: float = 0.56) -> None:
    """带厚度感的柜体（正面 + 右侧面 + 顶面），oy 为正面底边。"""
    draw.polygon([(ox, oy - H), (ox + dx, oy - H - dy),
                  (ox + W + dx, oy - H - dy), (ox + W, oy - H)],
                 fill=BODY_TOP, outline=EDGE)
    draw.polygon([(ox + W, oy), (ox + W + dx, oy - dy),
                  (ox + W + dx, oy - H - dy), (ox + W, oy - H)],
                 fill=BODY_SIDE, outline=EDGE)
    draw.rectangle([ox, oy - H, ox + W, oy], fill=BODY_FRONT, outline=EDGE)

    if doors > 0:
        step = W / doors
        for i in range(1, doors):
            x = ox + i * step
            draw.line([(x, oy - H + 1), (x, oy - 1)], fill=SEAM, width=1)
        if handles:
            hl = min(16, max(8, H * 0.10))
            for i in range(1, doors):
                x = ox + i * step
                cy = oy - H * handle_frac
                draw.rounded_rectangle([x - 7, cy - hl / 2, x - 4, cy + hl / 2],
                                       radius=1, fill=HANDLE)
                draw.rounded_rectangle([x + 4, cy - hl / 2, x + 7, cy + hl / 2],
                                       radius=1, fill=HANDLE)

    if legs:
        lw, lh = 5, 7
        draw.rectangle([ox + 4, oy, ox + 4 + lw, oy + lh], fill=BODY_SIDE, outline=EDGE)
        draw.rectangle([ox + W - 9, oy, ox + W - 4, oy + lh], fill=BODY_SIDE, outline=EDGE)


def _slab(draw, ox: float, oy: float, W: float, H: float, dx: float, dy: float) -> None:
    """薄板（台面）。"""
    draw.polygon([(ox, oy - H), (ox + dx, oy - H - dy),
                  (ox + W + dx, oy - H - dy), (ox + W, oy - H)],
                 fill=SLAB, outline=SLAB_EDGE)
    draw.polygon([(ox + W, oy), (ox + W + dx, oy - dy),
                  (ox + W + dx, oy - H - dy), (ox + W, oy - H)],
                 fill=SLAB, outline=SLAB_EDGE)
    draw.rectangle([ox, oy - H, ox + W, oy], fill=SLAB, outline=SLAB_EDGE)


def _niche(draw, x1: float, y1: float, x2: float, y2: float, shelf: int = 0) -> None:
    """开放格：内凹暗色 + 内阴影 + 可选层板。"""
    draw.rectangle([x1, y1, x2, y2], fill=INSIDE, outline=EDGE)
    draw.line([(x1 + 1, y1 + 1), (x2 - 1, y1 + 1)], fill=INSIDE_SHADOW, width=2)
    for i in range(1, shelf + 1):
        yy = y1 + (y2 - y1) * i / (shelf + 1)
        draw.line([(x1, yy), (x2, yy)], fill=EDGE, width=1)
        draw.line([(x1, yy + 1), (x2, yy + 1)], fill=(240, 236, 226), width=1)


def _drawer(draw, x1: float, y1: float, x2: float, y2: float) -> None:
    """抽屉面 + 长条拉手。"""
    draw.rectangle([x1, y1, x2, y2], fill=BODY_FRONT, outline=EDGE)
    cy = (y1 + y2) / 2
    draw.line([(x1 + 6, cy), (x2 - 6, cy)], fill=HANDLE, width=3)


def _long_handle(draw, x: float, cy: float, H: float, side: int = 1) -> None:
    """竖向长拉手（衣柜常用）。"""
    hl = max(10.0, min(H * 0.26, 34.0))
    hx = x + side * 5
    draw.rounded_rectangle([hx - 1.5, cy - hl / 2, hx + 1.5, cy + hl / 2],
                           radius=1, fill=HANDLE)


def _seams(draw, ox: float, oy: float, W: float, H: float, n: int,
           top: float = 1.0, bottom: float = 1.0) -> None:
    if n <= 1:
        return
    step = W / n
    for i in range(1, n):
        x = ox + i * step
        draw.line([(x, oy - H * top), (x, oy - H * bottom)], fill=SEAM, width=1)


# ---------------- 各柜型 ----------------
def _doors_by_ft(w_ft: float, per_ft: float = 2.0, lo: int = 2, hi: int = 5) -> int:
    """门扇数按「实际宽度（英尺）/ 每扇约 per_ft 英尺」估算，与画布缩放无关。"""
    return max(lo, min(hi, int(round(max(w_ft, 0.1) / per_ft))))


def _draw_wardrobe(draw, ox, oy, W, H, dx, dy, w_ft=4.0) -> None:
    """衣柜：通高柜体 + 竖向长拉手 + 顶部收口线。"""
    n = _doors_by_ft(w_ft, 2.2, 2, 5)
    _box(draw, ox, oy, W, H, dx, dy, legs=True, doors=n, handles=False)
    # 顶部收口
    draw.line([(ox, oy - H + 4), (ox + W, oy - H + 4)], fill=SEAM, width=1)
    # 每扇门竖向长拉手
    step = W / n
    for i in range(n):
        x_l = ox + i * step
        side = 1 if i < n - 1 else -1
        if i == 0:
            side = 1
        anchor = x_l + step - 6 if side > 0 else x_l + 6
        _long_handle(draw, anchor, oy - H * 0.52, H, side=side)
    # 踢脚
    draw.line([(ox, oy - 8), (ox + W, oy - 8)], fill=EDGE, width=1)


def _draw_shoe(draw, ox, oy, W, H, dx, dy, w_ft=3.0) -> None:
    """鞋柜：上部斜切百叶（透气槽）+ 下部对开门 + 台面。"""
    n = _doors_by_ft(w_ft, 2.0, 2, 4)
    _box(draw, ox, oy, W, H, dx, dy, legs=True, doors=0)
    # 台面线
    top_band = max(5.0, H * 0.06)
    draw.line([(ox, oy - H + top_band), (ox + W, oy - H + top_band)], fill=EDGE, width=1)
    # 上部百叶透气槽
    y0 = oy - H + top_band + 6
    y1 = oy - H * 0.56
    slots = max(3, int((y1 - y0) / 9))
    for i in range(slots):
        yy = y0 + i * 9
        if yy > y1 - 4:
            break
        draw.line([(ox + 8, yy), (ox + W - 8, yy)], fill=INSIDE_SHADOW, width=2)
    # 下部柜门
    draw.line([(ox, oy - H * 0.56), (ox + W, oy - H * 0.56)], fill=EDGE, width=1)
    _seams(draw, ox, oy, W, H, n, top=0.56, bottom=0.03)
    step = W / n
    for i in range(1, n):
        x = ox + i * step
        cy = oy - H * 0.30
        draw.rounded_rectangle([x - 7, cy - 5, x - 4, cy + 5], radius=1, fill=HANDLE)
        draw.rounded_rectangle([x + 4, cy - 5, x + 7, cy + 5], radius=1, fill=HANDLE)


def _draw_tv(draw, ox, oy, W, H, dx, dy, w_ft=6.0) -> None:
    """电视柜：低柜 + 中部开放格 + 两侧柜门/抽屉。"""
    _box(draw, ox, oy, W, H, dx, dy, legs=True, doors=0)
    pad = max(8.0, W * 0.06)
    nw = W - pad * 2
    nx1 = ox + W * 0.5 - nw * 0.28
    nx2 = ox + W * 0.5 + nw * 0.28
    _niche(draw, nx1, oy - H + 5, nx2, oy - 6, shelf=1)
    # 左右柜门
    if nx1 - ox > 16:
        _seams(draw, ox, oy, (nx1 - ox), H, 1)
        cy = oy - H * 0.5
        draw.rounded_rectangle([nx1 - 12, cy - 5, nx1 - 9, cy + 5], radius=1, fill=HANDLE)
        draw.rounded_rectangle([nx2 + 9, cy - 5, nx2 + 12, cy + 5], radius=1, fill=HANDLE)
    # 中间缝
    draw.line([(nx1 - 2, oy - H + 1), (nx1 - 2, oy - 1)], fill=SEAM, width=1)
    draw.line([(nx2 + 2, oy - H + 1), (nx2 + 2, oy - 1)], fill=SEAM, width=1)
    # 台面
    draw.line([(ox, oy - H + 2), (ox + W, oy - H + 2)], fill=EDGE, width=1)


def _draw_study(draw, ox, oy, W, H, dx, dy, w_ft=6.0) -> None:
    """书柜：左侧开放层板 + 右侧封闭柜门。"""
    _box(draw, ox, oy, W, H, dx, dy, legs=True, doors=0)
    open_w = W * 0.58
    _niche(draw, ox + 4, oy - H + 4, ox + open_w, oy - 4, shelf=3)
    # 右侧门
    x_split = ox + open_w + 3
    draw.line([(x_split, oy - H + 1), (x_split, oy - 1)], fill=SEAM, width=1)
    cy = oy - H * 0.5
    draw.rounded_rectangle([x_split + 3, cy - 6, x_split + 6, cy + 6], radius=1, fill=HANDLE)
    # 右半再分上下门
    if H > 60:
        draw.line([(x_split, oy - H * 0.5), (ox + W, oy - H * 0.5)], fill=SEAM, width=1)


def _draw_book_desk(draw, ox, oy, W, H, dx, dy, w_ft=5.0) -> None:
    """Study desk: open knee space, desktop and one drawer pedestal."""
    top = max(7.0, H * 0.09)
    _slab(draw, ox, oy - H * 0.28, W, top, dx, dy)
    leg_top = oy - H * 0.28 + top
    draw.rectangle([ox + 5, leg_top, ox + W * 0.18, oy - 3], fill=BODY_FRONT, outline=EDGE)
    draw.line([(ox + W * 0.18, leg_top), (ox + W * 0.18, oy - 3)], fill=EDGE, width=1)
    _drawer(draw, ox + W * 0.70, leg_top - 2, ox + W - 4, oy - 3)


def _draw_dressing_table(draw, ox, oy, W, H, dx, dy, w_ft=3.0) -> None:
    """Dressing table: drawers and a tall mirror, unlike a basin vanity."""
    top = max(6.0, H * 0.08)
    _box(draw, ox, oy, W, H * 0.52, dx, dy, legs=True, doors=0)
    _drawer(draw, ox + 4, oy - H * 0.52 + 3, ox + W - 4, oy - H * 0.52 + H * 0.18)
    mirror_w, mirror_h = W * 0.38, H * 0.38
    cx = ox + W * 0.5
    y2 = oy - H * 0.52 - top
    draw.rounded_rectangle([cx - mirror_w / 2, y2 - mirror_h, cx + mirror_w / 2, y2],
                           radius=5, fill=(241, 244, 247), outline=STEEL, width=2)
    draw.line([(cx, y2 - mirror_h + 5), (cx, y2 - 3)], fill=EDGE, width=1)


def _draw_vanity(draw, ox, oy, W, H, dx, dy, w_ft=3.0) -> None:
    """浴室柜：柜体 + 台面 + 台上盆 + 龙头。"""
    _box(draw, ox, oy, W, H, dx, dy, legs=True, doors=2, handle_frac=0.5)
    # 台面
    top_h = max(5.0, H * 0.07)
    _slab(draw, ox - 2, oy - H, W + 4, top_h, dx + 2, dy * 0.92)
    # 台盆（坐在台面上方，椭圆口 + 内壁）
    cx = ox + W * 0.5 + dx * 0.42
    cy = oy - H - top_h * 0.6 - dy * 0.18
    rx, ry = W * 0.26, max(5.0, H * 0.12)
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(240, 240, 243), outline=STEEL)
    draw.ellipse([cx - rx + 4, cy - ry + 2.5, cx + rx - 4, cy + ry - 2.5],
                 outline=(206, 208, 212))
    draw.ellipse([cx - 2.5, cy - 1.5, cx + 2.5, cy + 1.5], fill=(220, 222, 226))
    # 龙头：立柱 + 横臂 + 出水口（L 形，比圆弧更清楚；高度夹紧防出画）
    hs = max(9.0, min(H * 0.22, 26.0))
    hs = max(4.0, min(hs, cy - ry - 10.0))
    top = cy - ry - hs
    draw.line([(cx, cy - ry), (cx, top)], fill=STEEL, width=3)
    draw.line([(cx, top), (cx + 9, top)], fill=STEEL, width=3)
    draw.line([(cx + 9, top), (cx + 9, top + 7)], fill=STEEL, width=3)
    draw.ellipse([cx - 3, top - 3, cx + 3, top + 3], fill=STEEL)


def _draw_balcony(draw, ox, oy, W, H, dx, dy, w_ft=4.0) -> None:
    """阳台柜：上柜门 + 下部开放格（放洗衣机/杂物）。"""
    _box(draw, ox, oy, W, H, dx, dy, legs=True, doors=0)
    split = 0.52
    y_mid = oy - H * split
    n = _doors_by_ft(w_ft, 2.0, 2, 3)
    _seams(draw, ox, oy, W, H, n, top=1.0, bottom=split)
    draw.line([(ox, y_mid), (ox + W, y_mid)], fill=EDGE, width=1)
    _niche(draw, ox + 5, y_mid + 4, ox + W - 5, oy - 6, shelf=1)
    # 上柜门拉手
    step = W / n
    for i in range(1, n):
        x = ox + i * step
        cy = oy - H * 0.78
        draw.rounded_rectangle([x - 7, cy - 5, x - 4, cy + 5], radius=1, fill=HANDLE)
        draw.rounded_rectangle([x + 4, cy - 5, x + 7, cy + 5], radius=1, fill=HANDLE)


def _draw_storage(draw, ox, oy, W, H, dx, dy, w_ft=5.0) -> None:
    """储物柜 / 餐边柜：上排抽屉 + 下排柜门。"""
    _box(draw, ox, oy, W, H, dx, dy, legs=True, doors=0)
    dh = H * 0.22
    y_d = oy - H + dh
    _drawer(draw, ox + 2, oy - H + 3, ox + W - 2, y_d - 2)
    draw.line([(ox, y_d), (ox + W, y_d)], fill=EDGE, width=1)
    n = _doors_by_ft(w_ft, 2.2, 2, 4)
    _seams(draw, ox, oy, W, H, n, top=1 - dh / H, bottom=0.03)
    step = W / n
    for i in range(1, n):
        x = ox + i * step
        cy = oy - H * 0.26
        draw.rounded_rectangle([x - 7, cy - 5, x - 4, cy + 5], radius=1, fill=HANDLE)
        draw.rounded_rectangle([x + 4, cy - 5, x + 7, cy + 5], radius=1, fill=HANDLE)


def _draw_kitchen_base(draw, ox, oy, W, H, dx, dy, w_ft=10.0) -> None:
    """地柜：柜体 + 外挑台面 + 踢脚。"""
    _box(draw, ox, oy, W, H, dx, dy, legs=False,
         doors=_doors_by_ft(w_ft, 2.4, 2, 5))
    top_h = max(6.0, H * 0.09)
    _slab(draw, ox - 3, oy - H, W + 6, top_h, dx + 3, dy * 0.9)
    # 踢脚
    draw.rectangle([ox, oy - 7, ox + W, oy], fill=BODY_SIDE, outline=EDGE)


def _draw_kitchen_wall(draw, ox, oy, W, H, dx, dy, w_ft=8.0) -> None:
    """吊柜：柜体 + 顶部封板 + 底部灯带阴影。"""
    _box(draw, ox, oy, W, H, dx, dy, legs=False,
         doors=_doors_by_ft(w_ft, 2.2, 2, 5))
    draw.line([(ox, oy - H + 3), (ox + W, oy - H + 3)], fill=SEAM, width=1)
    # 底部灯带
    draw.line([(ox + 2, oy - 2), (ox + W - 2, oy - 2)], fill=(246, 222, 158), width=3)
    draw.line([(ox, oy), (ox + W, oy)], fill=EDGE, width=1)


def _draw_panel(draw, ox, oy, W, H, dx, dy, w_ft=10.0) -> None:
    """护墙板：薄平板 + 竖向分缝 + 踢脚线。"""
    _box(draw, ox, oy, W, H, dx, dy, legs=False, doors=0)
    ng = max(2, min(6, int(round(max(w_ft, 1.0) / 2.6))))
    step = W / ng
    for i in range(1, ng):
        x = ox + i * step
        draw.line([(x, oy - H + 2), (x, oy - 4)], fill=SEAM, width=1)
    draw.line([(ox, oy - 5), (ox + W, oy - 5)], fill=EDGE, width=2)


def _draw_cabinet(draw, ox, oy, W, H, dx, dy, w_ft=4.0) -> None:
    """兜底：普通柜体，门数随实际宽度变化。"""
    _box(draw, ox, oy, W, H, dx, dy, legs=True,
         doors=_doors_by_ft(w_ft, 2.0, 2, 4))


def _draw_quartz(draw, ox, oy, W, H, dx, dy, w_ft=10.0) -> None:
    _slab(draw, ox, oy, W, H, dx, dy)


def _draw_sink(draw, ox, oy, W, H, dx, dy, w_ft=3.0) -> None:
    """洗手盆 / 水槽：薄台面 + 台上盆 + 龙头。"""
    _slab(draw, ox, oy, W, H, dx, dy)
    # 盆体（台上盆，坐在台面上方）
    bw = W * 0.56
    bh = max(10.0, min(W * 0.18, 46.0))
    x1 = ox + (W - bw) / 2 + dx * 0.30
    x2 = x1 + bw
    y2 = oy - H + 2
    y1 = y2 - bh
    draw.rounded_rectangle([x1, y1, x2, y2], radius=6,
                           fill=(238, 238, 241), outline=STEEL)
    draw.rounded_rectangle([x1 + 5, y1 + 4, x2 - 5, y2 - 4], radius=5,
                           outline=(206, 208, 212))
    # 下水口
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    r = max(3.0, bh * 0.16)
    draw.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8],
                 fill=(222, 222, 226), outline=STEEL)
    # 龙头（L 形，高度夹紧防出画）
    hs = max(10.0, min(bh * 0.9, 40.0))
    hs = max(4.0, min(hs, y1 - 8.0))
    top = y1 - hs
    draw.line([(cx, y1), (cx, top)], fill=STEEL, width=3)
    draw.line([(cx, top), (cx + 10, top)], fill=STEEL, width=3)
    draw.line([(cx + 10, top), (cx + 10, top + 8)], fill=STEEL, width=3)
    draw.ellipse([cx - 3, top - 3, cx + 3, top + 3], fill=STEEL)


_PAINTERS = {
    "wardrobe": _draw_wardrobe,
    "shoe": _draw_shoe,
    "tv": _draw_tv,
    "study": _draw_study,
    "bookcase": _draw_study,
    "book_desk": _draw_book_desk,
    "dressing_table": _draw_dressing_table,
    "altar": _draw_cabinet,
    "island": _draw_kitchen_base,
    "kitchen": _draw_kitchen_base,
    "wine": _draw_storage,
    "low_cabinet": _draw_storage,
    "vanity": _draw_vanity,
    "balcony": _draw_balcony,
    "storage": _draw_storage,
    "kitchen_base": _draw_kitchen_base,
    "kitchen_wall": _draw_kitchen_wall,
    "panel": _draw_panel,
    "cabinet": _draw_cabinet,
    "quartz": _draw_quartz,
    "sink": _draw_sink,
}


# ---------------- 白色样板图拼版 ----------------
MODEL_AREA = (56, 40, CW - 56 - 74, CH - 40 - 56)      # 与手绘一致的绘图区


def _fit_box(iw: int, ih: int, avail_w: float, avail_h: float) -> Tuple[int, int]:
    """等比缩放到可用区域内的像素尺寸（长宽比保持，不拉伸）。"""
    iw, ih = max(1, int(iw)), max(1, int(ih))
    scale = min(float(avail_w) / iw, float(avail_h) / ih)
    return max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))


def _model_box(iw: int, ih: int) -> Tuple[int, int, int, int]:
    """样板图在画布上的居中矩形 (x, y, w, h)。"""
    ml, mt, avail_w, avail_h = MODEL_AREA
    w, h = _fit_box(iw, ih, avail_w, avail_h)
    return (int(round(ml + (avail_w - w) / 2.0)),
            int(round(mt + (avail_h - h) / 2.0)), w, h)


def _paste_model(img: Image.Image, source: Image.Image, rect) -> None:
    """把样板图等比贴到既定矩形（不拉伸）。"""
    x, y, w, h = rect
    resized = source.resize((w, h), Image.LANCZOS)
    img.paste(resized, (x, y), resized)


def _annotate_model(img, draw, rect, raw_w: float, raw_h: float, raw_d: float,
                    dim_unit: str, font) -> None:
    """在样板图外围标注实际宽/高/深；文字与单位口径与手绘图一致。

    所有标注都画在图片矩形**外侧**（引出线从矩形外一格起笔），并且在调用方
    之**后再贴一次图片**：图片矩形内因此始终与源图逐像素一致，任何标注
    （含字体上下伸部）都不可能覆盖照片边缘。
    """
    x, y, w, h = rect
    _dim_h(img, draw, x, x + w, min(y + h + 20, CH - 26), y + h + 1,
           _dim_label("W", raw_w, dim_unit), font)
    _dim_v(img, draw, y, y + h, max(14.0, x - 22), x - 1,
           _dim_label("H", raw_h, dim_unit), font)
    if raw_d > 0:
        text = _dim_label("D", raw_d, dim_unit)
    else:
        text = "D —"
    tw, th = _text_size(draw, text, font)
    tx = min(max(x + w - tw, 4.0), CW - tw - 4.0)
    ty = min(max(y - th - 8, 4.0), CH - th - 4.0)
    draw.text((tx, ty), text, font=font, fill=DIM_TEXT)


# ---------------- 主入口 ----------------
def render(kind: str, w_mm: float, h_mm: float, d_mm: float,
           out_path: str, mm_per_ft: float = 304.8,
           dim_unit: str = "mm",
           cab_name: str = "", cab_name_en: str = "",
           dim_font: int = 20) -> str:
    """生成一张 480x320 的柜体示意图，返回文件路径。

    kind: 柜型 key（见 KIND_LABEL）；旧品类 key 也兼容。
    dim_unit: "mm"（默认，与报价单 Dimension 列同口径）/ "ft"。
    cab_name / cab_name_en: 仅用于 kind=custom_cabinet 时的二次分流与日志。
    dim_font: 尺寸标注字号。Excel 按 176px 显示用 20；打印/PDF 显示尺寸更小，
              传更大的字号（30）保证 W/H/D 仍然清晰。
    """
    if kind not in _PAINTERS:
        kind = resolve_kind(kind, cab_name, cab_name_en)

    raw_w = float(w_mm or 0)
    raw_h = float(h_mm or 0)
    raw_d = float(d_mm or 0)
    w = max(raw_w / mm_per_ft, 0.15)
    h = raw_h / mm_per_ft
    d = max(raw_d / mm_per_ft, 0.0)

    flat = kind in ("quartz", "sink")
    if kind == "quartz":
        h = max(h, 0.16)
    if kind == "sink":
        h = max(h, 0.18)
    if h <= 0.01:
        h = 2.0
    if kind in ("panel", "quartz") and d <= 0.02:
        d = 0.06

    # 深度未填（0）时：不能画成一张平面立面图（那样的图没有「深」这一维）。
    # 给一个名义进深只用于**出图**，标注仍写 `D —`，不虚构数值。
    d_unknown = (raw_d <= 0) and not flat
    if d_unknown:
        d = 2.0                      # ≈600mm，定制柜标准深

    # 深度偏移（透视压缩）：0.58 / 0.40 比原来的 0.52 / 0.34 更能看出「有进深」
    dx_ft = d * 0.58
    dy_ft = d * 0.40

    # 绘图区（上/右留白给进深标注，下留白给宽度文字）
    ml, mr, mt, mb = 56, 74, 40, 56
    avail_w = CW - ml - mr
    avail_h = CH - mt - mb

    bbox_w = w + dx_ft
    bbox_h = h + dy_ft
    s = min(avail_w / bbox_w, avail_h / bbox_h)

    W, H = w * s, h * s
    dx, dy = dx_ft * s, dy_ft * s

    # 极浅的柜体（护墙板 18mm、台面 20mm、水槽…）按比例只剩 1~2px，
    # 图上等于没有进深，D 标注也无处可落。给一个最小可视进深。
    if raw_d > 0:
        dx = max(dx, 13.0)
        dy = max(dy, 9.0)

    ox = ml + max(0.0, (avail_w - (W + dx)) / 2)
    oy = mt + max(0.0, (avail_h - (H + dy)) / 2) + H + dy     # 正面底边 y

    img = Image.new("RGBA", (CW, CH), BG)
    draw = ImageDraw.Draw(img)
    f_dim = _font(dim_font)

    # 12 类柜型用白色样板图；其余柜型（护墙板 / 台面 / 水槽 / 浴室柜 / 未知）仍用手绘。
    asset = model_asset(kind)
    if asset:
        try:
            with Image.open(asset) as handle:
                source = handle.convert("RGBA")
            rect = _model_box(source.width, source.height)
            # 先画尺寸标注、最后贴照片：照片矩形内永远与源图逐像素一致，
            # 标注（含字体上下伸部）只会落在矩形外侧。
            _annotate_model(img, draw, rect, raw_w, raw_h, raw_d, dim_unit, f_dim)
            _paste_model(img, source, rect)
            out_dir = os.path.dirname(os.path.abspath(out_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            img.convert("RGB").save(out_path, "PNG")
            return out_path
        except Exception:
            # 样板图损坏或不可读时退回手绘，导出不中断
            img = Image.new("RGBA", (CW, CH), BG)
            draw = ImageDraw.Draw(img)

    _PAINTERS[kind](draw, ox, oy, W, H, dx, dy, w)

    # ---- 尺寸标注 ----
    # 宽度（正面下方）；记下文字矩形，供进深标注避让
    w_box = _dim_h(img, draw, ox, ox + W, oy + 22, oy,
                   _dim_label("W", raw_w, dim_unit), f_dim)
    # 高度（正面左侧）—— 平板类不标高度
    if not flat:
        _dim_v(img, draw, oy - H, oy, ox - 24, ox, _dim_label("H", raw_h, dim_unit), f_dim)
    # 进深（正面底右角 → 背面底右角，尺寸线外移到侧下方）—— 只要填了深度就一定标
    if d > 0 or d_unknown:
        d_text = _dim_label("D", raw_d, dim_unit) if raw_d > 0 else "D —"
        _dim_depth(img, draw, ox + W, oy, ox + W + dx, oy - dy, d_text, f_dim,
                   avoid=w_box)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    img.convert("RGB").save(out_path, "PNG")
    return out_path


if __name__ == "__main__":
    demo = [
        ("wardrobe", 2400, 2400, 600),
        ("shoe", 1200, 1100, 350),
        ("tv", 2000, 450, 400),
        ("study", 1800, 2100, 350),
        ("vanity", 900, 850, 500),
        ("balcony", 1200, 2200, 600),
        ("storage", 1500, 900, 400),
        ("kitchen_base", 3000, 850, 600),
        ("kitchen_wall", 2400, 700, 350),
        ("panel", 3000, 2400, 18),
        ("quartz", 3000, 0, 600),
        ("sink", 800, 0, 0),
    ]
    for k, a, b, c in demo:
        p = render(k, a, b, c, "output/_demo_%s.png" % k)
        print("ok", k, p)
