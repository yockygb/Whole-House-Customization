# -*- coding: utf-8 -*-
"""
Excel 导出（客户版 / 内部版）
=============================
* 所有金额都是**真实 Excel 公式**，不是写死的数字：
  改尺寸 / 数量 / 折扣 / 价格表单价 → 报价单、成本毛利、汇总自动重算。
* 客户版：只有报价单 + 价格表（不含供货价 / 成本 / 毛利），明细表隐藏但保留公式。
* 内部版：报价单 + 明细 + 价格表 + 成本毛利 + 材料用量 + 汇总 + 说明。
* 中英双语、RM 货币、公司抬头 / Logo / 页脚 / 付款条款。
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.styles.colors import Color
from openpyxl.utils import get_column_letter
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.worksheet.properties import PageSetupProperties

from core.floors import (floor_pair, floor_name_en, floor_name_cn,
                         floor_rank, normalize_floor)
from core.rooms import room_en as room_en_of

# 示意图渲染器（Pillow 手绘）。缺失 Pillow 时降级为「无图」，不影响其余内容。
try:
    from export.illustration import render as render_illustration
    from export.illustration import resolve_kind, kind_label
except Exception:  # pragma: no cover
    try:
        from illustration import render as render_illustration
        from illustration import resolve_kind, kind_label
    except Exception:
        render_illustration = None

        def resolve_kind(cat_key, cab_name="", cab_name_en=""):
            return cat_key or "cabinet"

        def kind_label(kind):
            return "CABINET"

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIC_DIR = os.path.join(ROOT_DIR, "exports", "_pics")

try:
    from export.illustration import PIC_VERSION
except Exception:  # pragma: no cover
    try:
        from illustration import PIC_VERSION
    except Exception:
        PIC_VERSION = "v1"

SHEET_Q = "报价单_Quotation"
SHEET_D = "明细_Calculation"
SHEET_P = "价格表_PriceList"
SHEET_C = "成本毛利_CostProfit"
SHEET_U = "材料用量_MaterialUsage"
SHEET_S = "汇总_Summary"
SHEET_N = "说明_Notes"

D_R0 = 5            # 明细数据起始行
Q_R0 = 9            # 报价单数据起始行

NAVY = "1D1D1F"
GREY = "6E6E73"
NOTE_GREY = "595959"          # 与样例 A22 预报价声明同色
LINE = "BFBFBF"               # 与样例边框色一致（原 D2D2D7 偏蓝）
BLUE = "0071E3"
FLOOR_NAVY = "1F3864"         # 样例楼层标题色

# 样例：I 列单价格式 '"RM"#,##0.00'；币种可配置，导出前用 _set_currency() 覆盖
MONEY = '"RM"#,##0.00'
NUM2 = '0.00'
NUM3 = '0.000'


def _set_currency(cur: str) -> None:
    """把金额格式的币种前缀换成配置里的币种（默认 RM）。"""
    global MONEY
    c = (cur or "RM").replace('"', "")
    MONEY = '"%s"#,##0.00' % c

THIN = Side(style="thin", color=LINE)
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center", wrap_text=True)

FILL_HEAD = PatternFill("solid", fgColor="F5F5F7")
FILL_SUM = PatternFill("solid", fgColor="EAF2FD")
FILL_INPUT = PatternFill("solid", fgColor="FFF7E0")
FILL_WARN = PatternFill("solid", fgColor="FDECEC")


def _style_header(ws, row: int, ncols: int, height: int = 34) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(bold=True, size=9, color=NAVY)
        cell.fill = FILL_HEAD
        cell.border = BORDER
        cell.alignment = CENTER
    ws.row_dimensions[row].height = height


def _fit(ws, landscape: bool = True) -> None:
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)


def _cat_label(ln, en: bool = False) -> str:
    base = (ln.cat_name_en if en else ln.cat_name) or ""
    name = (ln.cab_name_en if en else ln.cab_name) or ""
    return "%s · %s" % (base, name) if name else base


# ------------------------------------------------------------------ 英主中辅（富文本）
# 规则：英文第一行，字号更大、加粗、颜色更深（近黑）；中文第二行，字号约为英文的
# 65%，颜色浅灰。Excel 单格里只有富文本能做到「同一格两种字号」。
EN_SIZE = 9.0
CN_RATIO = 0.66


def _rt_lines(lines, en_size: float = EN_SIZE, en_bold: bool = False,
              en_color: str = "") -> Any:
    """lines: [(text, is_cn), ...] → 富文本；中文按 66% 字号、浅灰、不加粗。

    en_color 为空时不显式设色（用 Excel 默认纯黑）——与旧样例一致，
    同时满足「英文颜色比中文深」的对比度要求（黑 vs #6E6E73）。
    """
    parts = []
    first = True
    en_font = dict(rFont="Calibri", sz=en_size, b=en_bold)
    if en_color:
        en_font["color"] = Color(rgb="FF" + en_color)
    for text, is_cn in lines:
        text = (text or "").strip()
        if not text:
            continue
        if not first:
            parts.append(TextBlock(InlineFont(rFont="Calibri", sz=en_size), "\n"))
        first = False
        if is_cn:
            parts.append(TextBlock(
                InlineFont(rFont="Microsoft YaHei", sz=round(en_size * CN_RATIO, 1),
                           color=Color(rgb="FF" + GREY)), text))
        else:
            parts.append(TextBlock(InlineFont(**en_font), text))
    if not parts:
        return ""
    if len(parts) == 1 and isinstance(parts[0], TextBlock):
        return parts[0].text          # 只有一行时退回普通字符串，方便公式/筛选
    return CellRichText(parts)


def _bi(en: str, cn: str = "", en_size: float = EN_SIZE, en_bold: bool = False,
        en_color: str = "") -> Any:
    """「英文一行 + 中文一行」的快捷写法。"""
    return _rt_lines([(en, False), (cn, True)], en_size=en_size, en_bold=en_bold,
                     en_color=en_color)


# ------------------------------------------------------------------ 价格表
def _strip_cost_note(text: str) -> str:
    """客户版备注去价：删掉含「供货价 / 成本 / 毛利 / supply / cost」的括号段与分句。"""
    if not text:
        return text or ""
    out = []
    for ln in str(text).split("\n"):
        ln = re.sub(r"[（(][^）)]*(?:供货价|成本|进价|毛利|supply|cost)[^）)]*[）)]",
                    "", ln, flags=re.I)
        parts = re.split(r"(?<=[;；。.])", ln)
        kept = [p for p in parts
                if not re.search(r"供货价|成本|进价|毛利|supply|cost", p, re.I)]
        ln = "".join(kept).strip()
        ln = re.sub(r"[;；]\s*$", "", ln).strip()
        if ln:
            out.append(ln)
    return "\n".join(out)


def _write_price_sheet(ws, cfg, mode: Optional[str], include_cost: bool):
    """写价格表。返回 (材料行号映射, 增项行号映射)。

    ★ 关键约束：报价单价恒在第 8 列（H）。客户版不写供货价 / 市场价（D–G 留空后隐藏），
      但**列结构必须与内部版一致**，否则明细里 `价格表!$H$n` 的引用会指向空列，
      Excel 重算后客户版金额会归零。
    """
    ws["A1"] = "价格表 / PRICE LIST"
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    ws.merge_cells("A1:K1")
    if include_cost:
        ws["A2"] = ("改价只改【报价单价 Quoted Price】列，报价单、成本毛利与增项金额会自动跟着变。"
                    "定制柜拆成「柜体 + 柜门」两行，明细单价 = 两行之和。"
                    "  Edit the Quoted Price column only; the quotation, cost and add-on amounts recalculate.")
    else:
        # 客户版：不得出现「成本 / 毛利 / 供货价」等内部口径字样
        ws["A2"] = ("改价只改【报价单价 Quoted Price】列，报价单与增项金额会自动跟着变。"
                    "定制柜拆成「柜体 + 柜门」两行，明细单价 = 两行之和。"
                    "  Edit the Quoted Price column only; the quotation and add-on amounts recalculate.")
    ws["A2"].font = Font(size=9, color=GREY)
    ws.merge_cells("A2:K2")
    ws["A2"].alignment = LEFT
    ws.row_dimensions[2].height = 28

    heads = ["体系\nSystem", "品类\nCategory", "材质 / 规格\nMaterial / Spec",
             "供货价\nSupply Price", "市场下限\nMarket Low", "市场中位\nMarket Mid",
             "市场上限\nMarket High", "报价单价(可改)\nQuoted Price", "单位\nUnit", "备注\nNote"]
    for i, h in enumerate(heads, 1):
        # 客户版 D–G 列的供货价 / 市场价表头留空（该 4 列随后被隐藏）
        if not include_cost and i in (4, 5, 6, 7):
            continue
        ws.cell(row=3, column=i, value=h)
    if include_cost:
        _style_header(ws, 3, len(heads))
    else:
        _style_header(ws, 3, len(heads))
        for cc in (4, 5, 6, 7):
            ws.cell(row=3, column=cc).value = None

    price_col = 8          # ★ 恒为 H
    unit_col = 9
    note_col = 10
    row = 4
    rows: Dict[Any, int] = {}
    for cat in cfg.cat_list():
        for mat_key, entry in (cfg.prices.get(cat["key"], {}) or {}).items():
            market = entry.get("market", [0, 0])
            ws.cell(row=row, column=1, value="%s\n%s" % (cfg.group_name(cat["key"]),
                                                         cfg.group_name_en(cat["key"])))
            ws.cell(row=row, column=2, value="%s\n%s" % (cat["name"], cfg.cat_name_en(cat["key"])))
            ws.cell(row=row, column=3, value="%s\n%s" % (entry.get("label", mat_key),
                                                         entry.get("label_en", "")))
            if include_cost:
                ws.cell(row=row, column=4, value=float(entry.get("supply", 0) or 0)).number_format = MONEY
                ws.cell(row=row, column=5, value=float(market[0])).number_format = MONEY
                ws.cell(row=row, column=6,
                        value=(float(market[0]) + float(market[-1])) / 2.0).number_format = MONEY
                ws.cell(row=row, column=7, value=float(market[-1])).number_format = MONEY
            c = ws.cell(row=row, column=price_col,
                        value=float(cfg.unit_price(cat["key"], mat_key, mode)))
            c.number_format = MONEY
            c.fill = FILL_INPUT
            c.font = Font(bold=True)
            ws.cell(row=row, column=unit_col, value=entry.get("unit", ""))
            note_txt = "%s\n%s" % (entry.get("note", ""), entry.get("note_en", ""))
            if not include_cost:
                note_txt = _strip_cost_note(note_txt)
            ws.cell(row=row, column=note_col, value=note_txt)
            for cc in range(1, note_col + 1):
                cell = ws.cell(row=row, column=cc)
                cell.border = BORDER
                cell.alignment = LEFT if cc in (1, 2, 3, note_col) else CENTER
                if cc != price_col:
                    cell.font = Font(size=9)
            ws.row_dimensions[row].height = 32
            rows[(cat["key"], mat_key)] = row
            row += 1

    # ---------------- 增项价格区块（明细的增项金额公式引用这里的 H 列） ----------------
    row += 1
    ws.cell(row=row, column=1, value="增项 / ADD-ONS")
    ws.cell(row=row, column=1).font = Font(bold=True, size=11, color=NAVY)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=note_col)
    row += 1
    addon_rows: Dict[str, int] = {}
    seen = set()
    for cat in cfg.cat_list():
        for ex in cfg.extras_for(cat["key"]):
            key = ex.get("key", "")
            if not key or key in seen:
                continue
            seen.add(key)
            basis_txt = {"length": "按长度 ft", "area": "按面积 ft²", "qty": "按个 / 套"}.get(
                ex.get("basis", "qty"), "")
            ws.cell(row=row, column=1, value="增项\nAdd-on")
            ws.cell(row=row, column=2, value=ex.get("name", key))
            ws.cell(row=row, column=3, value="%s\n%s" % (ex.get("name_en", ""), basis_txt))
            c = ws.cell(row=row, column=price_col, value=float(ex.get("price", 0) or 0))
            c.number_format = MONEY
            c.fill = FILL_INPUT
            c.font = Font(bold=True)
            ws.cell(row=row, column=unit_col, value=ex.get("unit", ""))
            addon_note = ex.get("note", "")
            if not include_cost:
                addon_note = _strip_cost_note(addon_note)
            ws.cell(row=row, column=note_col, value=addon_note)
            for cc in range(1, note_col + 1):
                cell = ws.cell(row=row, column=cc)
                cell.border = BORDER
                cell.alignment = LEFT if cc in (1, 2, 3, note_col) else CENTER
                if cc != price_col:
                    cell.font = Font(size=9)
            ws.row_dimensions[row].height = 30
            addon_rows[key] = row
            row += 1

    widths = {"A": 22, "B": 16, "C": 26, "D": 12, "E": 11, "F": 11, "G": 11,
              "H": 14, "I": 8, "J": 46}
    for k, v in widths.items():
        ws.column_dimensions[k].width = v
    ws.freeze_panes = "A4"
    _fit(ws)
    return rows, addon_rows


# ------------------------------------------------------------------ 明细（内部版，公式源）
def _write_detail_sheet(ws, cfg, lines, price_rows: Dict[Any, int],
                        addon_rows: Optional[Dict[str, int]] = None) -> None:
    ncols = 28
    last_col = get_column_letter(ncols)
    ws["A1"] = "计算明细（内部用 · 改这里全表重算） / CALCULATION DETAIL (INTERNAL)"
    ws["A1"].font = Font(bold=True, size=15, color=NAVY)
    ws.merge_cells("A1:%s1" % last_col)
    ws["A1"].alignment = LEFT
    ws.row_dimensions[1].height = 30

    ws["A2"] = ("金额 = ROUND(计价量 × 系数 × 单价 × 数量, 2) + 增项；"
                "计价量：定制柜/护墙板 = 长(ft) × 计价高(ft)，地柜/吊柜 = 长(ft)；"
                "计价高 = MAX(实际高, 3.3ft)（可关）；超深系数 = 深 ÷ 标准深；"
                "橱柜非标（高度≠标准 或 深>标准+10mm）×1.2。"
                "  Amount = measure x factor x unit price x qty + add-ons.")
    ws["A2"].font = Font(size=8, color=GREY)
    ws.merge_cells("A2:%s2" % last_col)
    ws["A2"].alignment = LEFT
    ws.row_dimensions[2].height = 30

    heads = ["序号\nNo.", "楼层\nFloor", "区域\nRoom", "区域备注\nRoom Note",
             "体系\nSystem", "品类\nCategory", "柜体名称\nCabinet Name",
             "材质 / 规格\nMaterial", "长(mm)\nL", "高(mm)\nH", "深(mm)\nD",
             "长(ft)\nL(ft)", "高(ft)\nH(ft)", "深(ft)\nD(ft)", "计价高(ft)\nBill H",
             "计价量\nMeasure", "单位\nUnit", "系数\nFactor", "单价\nUnit Price",
             "数量\nQty", "增项金额\nAdd-ons", "金额\nAmount", "增项明细\nAdd-on Detail",
             "备注 / 计价过程\nNote / Calc", "柜体金额\nCarcass", "柜门金额\nDoor",
             "灯带金额\nLED", "Quartz length (mm)\n石英石长度（留空随柜体）"]
    for i, h in enumerate(heads, 1):
        ws.cell(row=4, column=i, value=h)
    _style_header(ws, 4, ncols, 40)

    mft = cfg.mm_per_ft
    for i, ln in enumerate(lines):
        r = D_R0 + i
        cat = cfg.category(ln.cat_key)
        prow = price_rows.get((ln.cat_key, ln.material), 4)
        drow = price_rows.get((ln.cat_key, ln.door_key), 0) if (ln.split and ln.door_key) else 0
        mtype = cat.get("measure", "area")

        ws.cell(row=r, column=1, value=ln.idx)
        ws.cell(row=r, column=2, value="%s\n%s" % (ln.floor, ln.floor_en or ""))
        ws.cell(row=r, column=3, value="%s\n%s" % (ln.room, ln.room_en or ""))
        ws.cell(row=r, column=4, value=ln.room_note or "")
        ws.cell(row=r, column=5, value="%s\n%s" % (ln.group, ln.group_en or ""))
        ws.cell(row=r, column=6, value="%s\n%s" % (_cat_label(ln), _cat_label(ln, True)))
        ws.cell(row=r, column=7, value="%s\n%s" % (ln.cab_name or "—", ln.cab_name_en or ""))
        ws.cell(row=r, column=8, value="%s\n%s" % (ln.material_label, ln.material_label_en))
        ws.cell(row=r, column=9, value=float(ln.length_mm)).number_format = '#,##0'
        ws.cell(row=r, column=10, value=float(ln.height_mm)).number_format = '#,##0'
        ws.cell(row=r, column=11, value=float(ln.depth_mm)).number_format = '#,##0'
        ws.cell(row=r, column=12, value="=I%d/%s" % (r, mft)).number_format = NUM2
        ws.cell(row=r, column=13, value="=J%d/%s" % (r, mft)).number_format = NUM2
        ws.cell(row=r, column=14, value="=K%d/%s" % (r, mft)).number_format = NUM2

        if mtype == "area":
            min_h = float(cat.get("min_height_ft", 3.3))
            ws.cell(row=r, column=15,
                    value="=MAX(M%d,%s)" % (r, min_h) if ln.min_height_enabled and min_h>0 else "=M%d" % r)
        else:
            ws.cell(row=r, column=15, value="=M%d" % r)
        ws.cell(row=r, column=15).number_format = NUM2

        if mtype == "area":
            ws.cell(row=r, column=16, value="=L%d*O%d" % (r, r))
        elif mtype == "length":
            ws.cell(row=r, column=16, value="=L%d" % r)
        else:
            ws.cell(row=r, column=16, value="=T%d" % r)
        ws.cell(row=r, column=16).number_format = NUM3

        ws.cell(row=r, column=17, value=ln.unit)

        std_d_mm = float(cat.get("std_depth_mm", 0) or 0)
        if mtype == "area" and std_d_mm > 0 and not cat.get("ignore_depth"):
            std_expr = "%s/%s" % (std_d_mm, mft)
            ws.cell(row=r, column=18, value="=IF(N%d>%s,N%d/(%s),1)" % (r, std_expr, r, std_expr))
        elif mtype == "length":
            if ln.nonstd_override is not None:
                ws.cell(row=r, column=18, value=cfg.nonstd_factor if ln.nonstd_override else 1)
            elif bool(cat.get("check_height")) and cat.get("std_height_ft"):
                ws.cell(row=r, column=18,
                        value="=IF(OR(ABS(M%d-%s)>%s,K%d>%s),%s,1)"
                              % (r, cat["std_height_ft"], cfg.height_tol, r,
                                 std_d_mm + 10, cfg.nonstd_factor))
            elif std_d_mm:
                ws.cell(row=r, column=18,
                        value="=IF(K%d>%s,%s,1)" % (r, std_d_mm + 10, cfg.nonstd_factor))
            else:
                ws.cell(row=r, column=18, value=1)
        else:
            ws.cell(row=r, column=18, value=1)
        ws.cell(row=r, column=18).number_format = NUM2

        # 单价：手动定价写死并标黄；否则引用价格表（柜体 + 柜门）
        if ln.price_override:
            c = ws.cell(row=r, column=19, value=round(float(ln.unit_price), 2))
            c.fill = FILL_WARN
        elif drow:
            c = ws.cell(row=r, column=19,
                        value="=%s!$H$%d+%s!$H$%d" % (SHEET_P, prow, SHEET_P, drow))
        else:
            c = ws.cell(row=r, column=19, value="=%s!$H$%d" % (SHEET_P, prow))
        c.number_format = MONEY
        ws.cell(row=r, column=20, value=int(ln.qty))

        quartz = next((e for e in ln.extras_list if e.get('key') == 'quartz' and e.get('basis') == 'length'), None)
        ws.cell(row=r, column=28, value=quartz.get('l_mm') if quartz else None).number_format = '#,##0.####'
        if quartz:
            ws.cell(row=r, column=28).fill = FILL_INPUT

        # 增项金额（公式：单价引用价格表增项区块，改单价即联动；长/高变化也联动）
        if ln.extras_list:
            terms = []
            for e in ln.extras_list:
                key = e.get("key", "")
                arow = (addon_rows or {}).get(key)
                p = ("%s!$H$%d" % (SHEET_P, arow)) if arow else ("%.10g" % float(e.get("price", 0) or 0))
                q = int(e.get("qty", 1) or 1)
                if e.get("basis") == "length":
                    if key == 'quartz':
                        terms.append('ROUND(%s*IF(SUM(AB%d)>0,SUM(AB%d)/%.10g,L%d)*%d,2)' % (p, r, r, mft, r, q))
                    else:
                        terms.append("ROUND(%s*L%d*%d,2)" % (p, r, q))
                elif e.get("basis") == "area":
                    w_mm = float(e.get("w_mm", 0) or 0)
                    h_mm = float(e.get("h_mm", 0) or 0)
                    if w_mm > 0 and h_mm > 0:
                        terms.append("ROUND(%s*(%.4f/%.4f)*(%.4f/%.4f)*%d,2)"
                                     % (p, w_mm, mft, h_mm, mft, q))
                    else:
                        terms.append("ROUND(%s*L%d*M%d*%d,2)" % (p, r, r, q))
                else:
                    terms.append("ROUND(%s*%d,2)" % (p, q))
            ws.cell(row=r, column=21, value="=" + "+".join(terms))
        else:
            ws.cell(row=r, column=21, value=0)
        ws.cell(row=r, column=21).number_format = MONEY

        if mtype == "pcs":
            ws.cell(row=r, column=22, value="=ROUND(S%d*T%d,2)+U%d" % (r, r, r))
        else:
            ws.cell(row=r, column=22, value="=ROUND(P%d*R%d*S%d*T%d,2)+U%d" % (r, r, r, r, r))
        ws.cell(row=r, column=22).number_format = MONEY
        ws.cell(row=r, column=22).font = Font(bold=True, size=9)

        ws.cell(row=r, column=23, value=ln.extras_text or "")
        ws.cell(row=r, column=24, value=ln.basis or "")

        if ln.split and not ln.price_override and mtype != "pcs":
            ws.cell(row=r, column=25,
                    value="=ROUND(P%d*R%d*%s!$H$%d*T%d,2)"
                          % (r, r, SHEET_P, prow, r)).number_format = MONEY
            ws.cell(row=r, column=26,
                    value=("=ROUND(P%d*R%d*%s!$H$%d*T%d,2)" % (r, r, SHEET_P, drow, r))
                    if drow else 0).number_format = MONEY
        else:
            ws.cell(row=r, column=25, value=round(ln.body_amount, 2)).number_format = MONEY
            ws.cell(row=r, column=26, value=round(ln.door_amount, 2)).number_format = MONEY
        ws.cell(row=r, column=27, value=round(ln.led_amount, 2)).number_format = MONEY

        for c2 in range(1, ncols + 1):
            cell = ws.cell(row=r, column=c2)
            cell.border = BORDER
            if c2 in (2, 3, 4, 5, 6, 7, 8, 23, 24):
                cell.alignment = LEFT
            elif c2 in (1, 17, 20):
                cell.alignment = CENTER
            else:
                cell.alignment = RIGHT
            if c2 != 22:
                cell.font = Font(size=9)
        ws.row_dimensions[r].height = 40

    last = D_R0 + len(lines) - 1
    if not lines:
        last = D_R0
        ws.cell(row=D_R0, column=1, value="（尚未添加项目 / No items yet）")

    # 汇总
    r = last + 2
    ws.cell(row=r, column=1, value="报价汇总 / SUMMARY")
    ws.cell(row=r, column=1).font = Font(bold=True, size=12, color=NAVY)
    ws.merge_cells("A%d:V%d" % (r, r))
    ws.cell(row=r, column=1).fill = FILL_HEAD

    rr = r + 1
    for gkey in ("cabinet", "kitchen"):
        g = cfg.groups.get(gkey)
        if not g:
            continue
        ws.cell(row=rr, column=1, value="%s / %s" % (g.get("name", gkey), g.get("name_en", "")))
        ws.merge_cells("A%d:R%d" % (rr, rr))
        ws.cell(row=rr, column=1).alignment = LEFT
        c = ws.cell(row=rr, column=22,
                    value='=SUMIF($E$%d:$E$%d,"*"&"%s"&"*",$V$%d:$V$%d)'
                          % (D_R0, last, g.get("name", gkey), D_R0, last))
        c.number_format = MONEY
        c.font = Font(bold=True)
        rr += 1

    floors: List[str] = []
    for ln in lines:
        f = normalize_floor(getattr(ln, "floor", ""))
        if f not in floors:
            floors.append(f)
    floors.sort(key=floor_rank)
    for f in floors:
        _code, en = floor_pair(f)
        ws.cell(row=rr, column=1,
                value="楼层小计 · %s / %s subtotal" % (f, en) if en and en != f
                else "楼层小计 · %s" % f)
        ws.merge_cells("A%d:R%d" % (rr, rr))
        ws.cell(row=rr, column=1).alignment = LEFT
        ws.cell(row=rr, column=1).font = Font(size=9, color=GREY)
        c = ws.cell(row=rr, column=22,
                    value='=ROUND(SUMIF($B$%d:$B$%d,"%s*",$V$%d:$V$%d),2)'
                          % (D_R0, last, f, D_R0, last))
        c.number_format = MONEY
        c.font = Font(size=9)
        rr += 1

    ws.cell(row=rr, column=1, value="合计（市场指导价） / TOTAL")
    ws.merge_cells("A%d:R%d" % (rr, rr))
    ws.cell(row=rr, column=1).font = Font(bold=True, size=11)
    total_cell = "V%d" % rr
    c = ws.cell(row=rr, column=22, value="=ROUND(SUM($V$%d:$V$%d),2)" % (D_R0, last))
    c.number_format = MONEY
    c.font = Font(bold=True, size=12)
    for cc in range(1, 23):
        ws.cell(row=rr, column=cc).fill = FILL_SUM
        ws.cell(row=rr, column=cc).border = BORDER
    rr += 1

    ws.cell(row=rr, column=1, value="折扣系数（1 = 不打折，可改） / Discount factor")
    ws.merge_cells("A%d:R%d" % (rr, rr))
    ws.cell(row=rr, column=1).alignment = LEFT
    c = ws.cell(row=rr, column=22, value=1.0)   # 由 export_workbook 回填真实折扣
    c.number_format = '0.00'
    c.fill = FILL_INPUT
    c.font = Font(bold=True)
    c.border = BORDER
    disc_cell = "V%d" % rr
    rr += 1

    ws.cell(row=rr, column=1, value="折后合计 / TOTAL AFTER DISCOUNT")
    ws.merge_cells("A%d:R%d" % (rr, rr))
    ws.cell(row=rr, column=1).font = Font(bold=True, size=11)
    c = ws.cell(row=rr, column=22, value="=ROUND(%s*%s,2)" % (total_cell, disc_cell))
    c.number_format = MONEY
    c.font = Font(bold=True, size=12, color="C00000")
    for cc in range(1, 23):
        ws.cell(row=rr, column=cc).fill = FILL_SUM
        ws.cell(row=rr, column=cc).border = BORDER
    final_cell = "V%d" % rr
    rr += 1

    ws.cell(row=rr, column=1, value="定金比例（可改） / Deposit rate")
    ws.merge_cells("A%d:R%d" % (rr, rr))
    ws.cell(row=rr, column=1).alignment = LEFT
    c = ws.cell(row=rr, column=22, value=0.5)
    c.number_format = '0%'
    c.fill = FILL_INPUT
    c.font = Font(bold=True)
    c.border = BORDER
    dep_cell = "V%d" % rr
    rr += 1

    ws.cell(row=rr, column=1, value="定金金额 / DEPOSIT")
    ws.merge_cells("A%d:R%d" % (rr, rr))
    c = ws.cell(row=rr, column=22, value="=ROUND(%s*%s,2)" % (final_cell, dep_cell))
    c.number_format = MONEY
    c.font = Font(bold=True)
    c.border = BORDER
    rr += 1
    ws.cell(row=rr, column=1, value="余款 / BALANCE")
    ws.merge_cells("A%d:R%d" % (rr, rr))
    c = ws.cell(row=rr, column=22, value="=%s-%s" % (final_cell, "V%d" % (rr - 1)))
    c.number_format = MONEY
    c.border = BORDER

    widths = {"A": 5, "B": 10, "C": 12, "D": 16, "E": 14, "F": 18, "G": 14, "H": 26,
              "I": 9, "J": 9, "K": 9, "L": 8, "M": 8, "N": 8, "O": 9, "P": 10, "Q": 6,
              "R": 7, "S": 11, "T": 6, "U": 12, "V": 13, "W": 30, "X": 46, "Y": 12,
              "Z": 12, "AA": 11, "AB": 20}
    for k, v in widths.items():
        ws.column_dimensions[k].width = v
    ws.freeze_panes = "A5"
    _fit(ws)
    return {
        "total": int(total_cell[1:]),
        "disc": int(disc_cell[1:]),
        "net": int(final_cell[1:]),
        "dep_rate": int(dep_cell[1:]),
        "deposit": rr - 1,
        "balance": rr,
    }


# ------------------------------------------------------------------ 报价单（客户版）
# 版式严格对齐原系统 Vouguer 报价清单：
#   A1:B4 logo 图片 | C1:I1 公司信息 | J1:K1 日期与单号
#   A5 ATTN + Project | A6 greeting | A7 标题条 | 第 8 行表头（11 列，含 Picture 图片）
#   楼层分组行 → 数据行（D 列贴示意图）→ 产品合计 → 预报价声明 → Remark → 备注
# C 列图片由 illustration.py 按「品类 + 实际长高深」生成，图内含宽/高/深标注。

PIC_W, PIC_H = 176, 117          # Excel 中默认显示尺寸（px），与 C 列宽度匹配
PIC_ROW_H = 92                   # 默认行高（磅），保证图片完整显示

_EN_MONTHS = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]


def _en_date(s: str) -> str:
    """2026-10-21 → 21 October 2026；解析失败原样返回。"""
    txt = str(s or "").strip()
    if not txt:
        return ""
    for sep in ("-", "/", "."):
        if sep in txt:
            parts = txt.split(sep)
            if len(parts) == 3 and all(p.strip().isdigit() for p in parts):
                y, m, d = (int(p) for p in parts)
                if 1 <= m <= 12:
                    return "%d %s %d" % (d, _EN_MONTHS[m - 1], y)
    return txt


def _text_w(s: str) -> int:
    """粗略字宽：中日韩字符算 2，其余算 1。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in (s or ""))


def _est_height(text: str, cols: int = 150, line_h: int = 13, pad: int = 5) -> int:
    lines = 0
    for seg in (text or "").split("\n"):
        lines += max(1, -(-_text_w(seg) // cols))
    return lines * line_h + pad


def _qline(ws, r: int, text: str, ncols: int = 11, *, bold=False, size=9,
           align=None, border=False, height=None, color="000000", cols=150) -> None:
    """整行合并写一段说明文字（Remark / 备注 用）。"""
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    c = ws.cell(row=r, column=1, value=text)
    c.font = Font(bold=bold, size=size, color=color)
    c.alignment = align or Alignment(horizontal="left", vertical="center", wrap_text=True)
    if border:
        for cc in range(1, ncols + 1):
            ws.cell(row=r, column=cc).border = BORDER
    ws.row_dimensions[r].height = height if height is not None else _est_height(text, cols)


def _qline_rich(ws, r: int, lines, ncols: int = 11, *, en_size: float = 9,
                cols: int = 150) -> None:
    """整行合并写「英主中辅」富文本（条款 / 备注 用），行高按行数自动估。"""
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    c = ws.cell(row=r, column=1, value=_rt_lines(lines, en_size=en_size))
    c.font = Font(size=en_size, color="000000")
    c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    txt = "\n".join(t for t, _ in lines if t)
    ws.row_dimensions[r].height = _est_height(txt, cols, 13, 5)


def _write_floor_header(ws, r: int, floor: str, ncols: int = 11,
                        sub_formula: Optional[str] = None, count: int = 0, cfg=None) -> None:
    """楼层分组标题行 —— **严格对齐样例 A9**。

    样例就是 `A9:J9` 整行合并、只写楼层名、10pt 加粗 #1F3864、浅蓝底 EAF3FE、
    行高 20。这里保持同一结构：英文第一行 `GF / GROUND FLOOR`，中文第二行
    `地面层 · 3 项`。

    ★ 楼层小计**不放在报价页**（样例也没有），改为：
      · 明细_Calculation 的「报价汇总」区逐楼层 `SUMIF` 行（真实公式）
      · 汇总_Summary 的「按楼层 / By Floor」
    sub_formula 参数保留给内部版调用方，传入也不写进报价页。
    """
    code, en = floor_pair(floor)
    if cfg is not None: en=cfg.floor_en(code)
    cn = floor_name_cn(floor)
    title_en = code if (not en or en == code) else "%s / %s" % (code, en.upper())
    sub_cn = ("%s · %d 项" % (cn, count)) if cn else ("%d 项" % count)

    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    c = ws.cell(row=r, column=1, value=_bi(title_en, sub_cn, en_size=10,
                                           en_bold=True, en_color=FLOOR_NAVY))
    c.font = Font(bold=True, size=10, color=FLOOR_NAVY)
    c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    fill = PatternFill("solid", fgColor="EAF3FE")
    for cc in range(1, ncols + 1):
        cell = ws.cell(row=r, column=cc)
        cell.fill = fill
        cell.border = BORDER
    ws.row_dimensions[r].height = 20


def _pic_path(ln, pic_dir: str, unit: str = "mm") -> str:
    """按「柜型 + 长高深」生成示意图：同柜型同尺寸只画一次，不同尺寸各自一张。

    文件名带 `PIC_VERSION`，画法升级后自动换一份新图，不会复用旧缓存。
    """
    kind = resolve_kind(ln.cat_key, ln.cab_name or "", ln.cab_name_en or "")
    name = "%s_%d_%d_%d_%s_%s.png" % (
        kind, round(ln.length_mm), round(ln.height_mm), round(ln.depth_mm), unit,
        PIC_VERSION)
    path = os.path.join(pic_dir, name)
    if os.path.exists(path):
        return path
    render_illustration(kind, ln.length_mm, ln.height_mm, ln.depth_mm, path,
                        dim_unit=unit, cab_name=ln.cab_name or "",
                        cab_name_en=ln.cab_name_en or "")
    return path


def _add_pic(ws, ln, r: int, pic_dir: str,
             w_px: int = PIC_W, h_px: int = PIC_H, unit: str = "mm",
             row_h_pt: float = 0.0) -> bool:
    """把该行示意图贴到 D 列（图片位）：精确尺寸 + 单元格内居中。

    row_h_pt 已知时按「(行高px - 图高) / 2」垂直居中，避免图片贴住上边框。
    失败时静默跳过，不影响其余内容。
    """
    if render_illustration is None or not pic_dir:
        return False
    try:
        path = _pic_path(ln, pic_dir, unit)
        if not os.path.exists(path):
            return False
        img = XLImage(path)
        img.width, img.height = w_px, h_px
        off_y = 3
        if row_h_pt:
            off_y = max(2, int((row_h_pt * 4.0 / 3.0 - h_px) / 2.0))
        img.anchor = OneCellAnchor(
            _from=AnchorMarker(col=3, row=r - 1,
                               colOff=pixels_to_EMU(4), rowOff=pixels_to_EMU(off_y)),
            ext=XDRPositiveSize2D(pixels_to_EMU(w_px), pixels_to_EMU(h_px)))
        ws.add_image(img)
        return True
    except Exception:
        # 锚点 API 不可用时退回普通锚定（左上角对齐），保证仍然出图
        try:
            img = XLImage(_pic_path(ln, pic_dir, unit))
            img.width, img.height = w_px, h_px
            ws.add_image(img, "D%d" % r)
            return True
        except Exception:
            return False


def _write_quote_sheet(ws, cfg, quote, lines, summary, discount, deposit_rate,
                       pic_dir: str = "", sum_rows: Optional[Dict[str, int]] = None) -> None:
    """报价单：眉头 + 英主中辅表头 + 楼层分组小计 + 产品合计 / 折扣 / 定金 + 条款。

    版式对齐原系统 Vouguer 报价清单，但语言顺序改为「英文主、中文辅」：
      A1:B4 logo | C1:I1 公司信息 | J1:K1 日期 / 单号
      A5 ATTN / PROJECT | A6 greeting | A7 标题条
      第 8 行表头（EN 大字深色 + CN 小字浅灰，同一格两行）
      明细行：A 序号 | B 柜体名 | C 示意图 | D 描述 | E 尺寸 | F 投影面积
              | G 单位 | H 数量 | I 单价 | J 备注（增项 / 灯带 / 标记）
      楼层标题行右侧带该楼层小计；末尾产品合计 → 折扣 → 折后总额 → 定金 → 条款
    所有金额都是 Excel 公式，改明细即联动。
    """
    co = cfg.company()
    rk = cfg.remark()
    ill = cfg.illustration()
    ncols = 11
    pic_w = int(ill.get("width_px", PIC_W) or PIC_W)
    pic_h = int(ill.get("height_px", PIC_H) or PIC_H)
    pic_unit = ill.get("dim_unit", "mm") or "mm"
    row_h = max(PIC_ROW_H, int(pic_h * 0.78) + 6)
    sum_rows = sum_rows or {}

    widths = {"A": 5.5, "B": 12, "C": 22, "D": 26, "E": 36, "F": 20, "G": 12,
              "H": 7, "I": 7, "J": 16, "K": 30}
    for k, v in widths.items():
        ws.column_dimensions[k].width = v

    # ---------- 眉头：logo ----------
    logo = co.get("logo", "")
    if logo and not os.path.isabs(logo):
        logo = os.path.join(__import__("core.config",fromlist=["DATA_DIR"]).DATA_DIR,"company-logo.png") if logo == "data/company-logo.png" else os.path.join(ROOT_DIR,logo)
    if logo and os.path.exists(logo):
        try:
            img = XLImage(logo)
            img.width = int(co.get("logo_width_px", 150) or 150)
            img.height = int(co.get("logo_height_px", 43) or 43)
            ws.add_image(img, "A1")
        except Exception:
            pass
    ws.merge_cells("A1:B4")
    for rr in (1, 2, 3, 4):
        ws.row_dimensions[rr].height = 12

    ws.merge_cells("C1:I1")
    c = ws["C1"]
    c.value = co.get("name", "")
    c.font = Font(bold=True, size=13)
    c.alignment = Alignment(horizontal="left", vertical="bottom")

    for rr, key in ((2, "address"), (3, "mobile"), (4, "email")):
        ws.merge_cells("C%d:I%d" % (rr, rr))
        c = ws.cell(row=rr, column=3, value=co.get(key, ""))
        c.font = Font(size=8.5)
        c.alignment = Alignment(horizontal="left", vertical="center")

    # 右上：日期 / 单号（英文标签）
    ws.merge_cells("J1:K1")
    ws.merge_cells("J2:K2")
    ws["J1"] = "DATE: %s" % _en_date(quote.get("quote_date", ""))
    ws["J1"].font = Font(bold=True, size=9)
    ws["J1"].alignment = Alignment(horizontal="right", vertical="bottom")
    ws["J2"] = "REFERENCE NO.: %s" % (quote.get("quote_no", "") or "")
    ws["J2"].font = Font(bold=True, size=9)
    ws["J2"].alignment = Alignment(horizontal="right", vertical="center")

    # ATTN / PROJECT
    attn = "ATTN: %s" % (quote.get("customer", "") or "")
    if quote.get("project"):
        attn += "    PROJECT: %s" % quote["project"]
    ws.merge_cells("A5:K5")
    ws["A5"] = attn
    ws["A5"].font = Font(bold=True, size=9)
    ws["A5"].alignment = Alignment(horizontal="left", vertical="bottom")
    ws.row_dimensions[5].height = 20

    ws.merge_cells("A6:K6")
    ws["A6"] = co.get("greeting", "")
    ws["A6"].font = Font(size=9)
    ws["A6"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[6].height = 18

    # 标题条：QUOTATION 大字 + 报价单 小字（同一格两行，英文在上）
    ws.merge_cells("A7:K7")
    t = ws["A7"]
    title_en = co.get("title", "QUOTATION") or "QUOTATION"
    t.value = _bi(title_en, co.get("title_cn","报价单"), en_size=12, en_bold=True)
    t.font = Font(bold=True, size=12)
    t.alignment = CENTER
    for cc in range(1, ncols + 1):
        cell = ws.cell(row=7, column=cc)
        cell.border = Border(left=THIN, right=THIN, bottom=THIN,
                             top=Side(style="medium", color="000000"))
    ws.row_dimensions[7].height = 24

    # ---------- 表头（EN 主 + CN 辅） ----------
    heads = [
        ("NO.", "序号"),
        ("AREA", "区域"),
        ("PRODUCT", "产品名称"),
        ("PICTURE", "示意图"),
        ("DESCRIPTION", "描述"),
        ("Dimension(L*H*D)mm", "长*高*深 (mm)"),
        ("PROJECTED AREA", "投影面积"),
        ("UNIT", "单位"),
        ("QTY", "数量"),
        ("Price", "单价"),
        ("REMARK", "备注"),
    ]
    hdr_row = Q_R0 - 1
    for i, (en, cn) in enumerate(heads, 1):
        cell = ws.cell(row=hdr_row, column=i, value=_bi(en, cn, en_size=9,
                                                      en_bold=True))
        cell.font = Font(bold=True, size=9)
        cell.alignment = CENTER
        cell.fill = PatternFill("solid", fgColor="EDEDED")
        cell.border = Border(left=THIN, right=THIN, bottom=THIN,
                             top=Side(style="medium", color="000000"))
    ws.row_dimensions[hdr_row].height = 44

    # ---------- 明细行（按楼层分组：组标题带小计） ----------
    # 先按录入顺序切出楼层组，才能在小计公式里写准「明细!V起:V止」与项数
    groups: List[List[Any]] = []
    for i, ln in enumerate(lines):
        f = normalize_floor(getattr(ln, "floor", ""))
        if not groups or groups[-1][0] != f:
            groups.append([f, i, i])
        else:
            groups[-1][2] = i

    r = Q_R0
    gi = 0
    for i, ln in enumerate(lines):
        dr = D_R0 + i
        cat = cfg.category(ln.cat_key)
        measure_type = cat.get("measure", "area")

        if gi < len(groups) and i == groups[gi][1]:
            f, a_i, b_i = groups[gi]
            sub = "=ROUND(SUM(%s!V%d:V%d),2)" % (SHEET_D, D_R0 + a_i, D_R0 + b_i)
            _write_floor_header(ws, r, f, ncols, sub_formula=sub,
                                count=b_i - a_i + 1, cfg=cfg)
            r += 1
            gi += 1

        ws.cell(row=r, column=1, value=ln.idx)

        # B：区域/房间（不含楼层）；C：产品 = 「品类 · 柜体名称」
        area_en = (ln.room_en or "").strip()
        area_cn = (ln.room or "").strip()
        if not area_en or area_en == area_cn:
            area_en = room_en_of(area_cn)
        ws.cell(row=r, column=2,
                value=_rt_lines([(area_en, False), (area_cn, True)], en_size=8.5))

        cat_en = (ln.cat_name_en or "").strip()
        cat_cn = (ln.cat_name or "").strip()
        cab_en = (ln.cab_name_en or "").strip()
        cab_cn = (ln.cab_name or "").strip()
        if not cab_en or cab_en.lower() == cab_cn.lower():
            cab_en = ""
        if cab_en and cab_cn and cab_en.lower() != cab_cn.lower():
            # 品类名已包含在柜体名里时不重复（「地柜 · 厨房地柜」→「厨房地柜」）
            en_dup = bool(cat_en) and cat_en.lower() in cab_en.lower()
            cn_dup = bool(cat_cn) and cat_cn in cab_cn
            prod_en = cab_en if en_dup else ("%s · %s" % (cat_en, cab_en) if cat_en else cab_en)
            prod_cn = cab_cn if cn_dup else ("%s · %s" % (cat_cn, cab_cn) if cat_cn else cab_cn)
        elif cab_en:                       # 只有英文名
            prod_en, prod_cn = ("%s · %s" % (cat_en, cab_en) if cat_en else cab_en), cat_cn
        else:                              # 只有中文名 → 英文行不给中文，避免冒充英文
            prod_en, prod_cn = cat_en, ("%s · %s" % (cat_cn, cab_cn) if cab_cn else cat_cn)
        ws.cell(row=r, column=3,
                value=_rt_lines([(prod_en, False), (prod_cn, True)], en_size=9))

        # D：示意图（行高确定后再贴，图片才能垂直居中）
        ws.cell(row=r, column=4, value="")

        # E：描述（楼层和区域单独列出；描述只保留材质与备注）
        mat_en = (ln.material_label_en or "").strip()
        mat_cn = (ln.material_label or "").strip()
        if mat_en == mat_cn:
            mat_en = ""

        en_block = [mat_en] if mat_en else []
        cn_block = []
        if mat_cn:
            cn_block.append(mat_cn)
        if ln.room_note_en:
            en_block.append(ln.room_note_en)
        if ln.room_note:
            cn_block.append(ln.room_note)
        dl = [(t, False) for t in en_block] + [(t, True) for t in cn_block if t]
        ws.cell(row=r, column=5, value=_rt_lines(dl, en_size=8.5))

        # F：尺寸（高或深为 0 自动省略）
        ws.cell(row=r, column=6,
                value='=IF(AND({d}!J{r}=0,{d}!K{r}=0),{d}!I{r},'
                      'IF({d}!J{r}=0,{d}!I{r}&"*"&{d}!K{r},'
                      '{d}!I{r}&"*"&{d}!J{r}&"*"&{d}!K{r}))'
                      .format(d=SHEET_D, r=dr))
        # G/H/I：投影面积 / 单位 / 数量
        if measure_type == "pcs":
            ws.cell(row=r, column=7, value="/")
        else:
            ws.cell(row=r, column=7,
                    value="=%s!P%d" % (SHEET_D, dr)).number_format = NUM2
        ws.cell(row=r, column=8, value="=%s!Q%d" % (SHEET_D, dr))
        ws.cell(row=r, column=9,
                value="=%s!T%d" % (SHEET_D, dr)).number_format = '0'
        # J：单价 = 该行金额 ÷ 数量（数量 1 时即整行金额）
        c = ws.cell(row=r, column=10,
                    value="=ROUND(%s!V%d/%s!T%d,2)" % (SHEET_D, dr, SHEET_D, dr))
        c.number_format = MONEY
        if ln.price_override:
            c.fill = FILL_INPUT

        # K：备注（英文块在上：LED strip / power supply / sensor；中文块在下：增项、行备注、标记）
        en_bits, cn_bits = [], []
        if ln.led_amount > 0:
            en_bits.append("LED strip %g%s" % (ln.led_qty, cfg.led_unit_name(ln.led_unit)))
            if ln.led_power:
                en_bits.append("power supply")
            if ln.led_sensor:
                en_bits.append("sensor")
        if ln.extras_text:
            cn_bits.append(ln.extras_text)
        if ln.item_note_en:
            en_bits.append(ln.item_note_en)
        if ln.item_note:
            cn_bits.append(ln.item_note)
        if ln.flags:
            cn_bits.append("[" + " / ".join(ln.flags) + "]")
        rl = []
        if en_bits:
            rl.append(("Incl. " + ", ".join(en_bits), False))
        if cn_bits:
            rl.append(("含 " + "，".join(cn_bits), True))
        ws.cell(row=r, column=11, value=_rt_lines(rl, en_size=8) if rl else "")

        for cc in range(1, ncols + 1):
            cell = ws.cell(row=r, column=cc)
            cell.border = BORDER
            cell.font = Font(size=9)          # 样例正文 9pt、默认黑
            if cc in (2, 3, 5, 11):
                cell.alignment = Alignment(horizontal="left", vertical="center",
                                           wrap_text=True)
            elif cc == 6:
                cell.alignment = CENTER
            elif cc in (7, 10):
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = CENTER
        ws.cell(row=r, column=11).font = Font(size=8.5)
        if ln.price_override:
            ws.cell(row=r, column=10).fill = FILL_INPUT
        # 行高按「描述块 + 备注块」的估算行数取大者（备注已拆成英/中两行）
        remark_txt = "\n".join([t for t, _ in rl]) if rl else ""
        if getattr(ln,'pricing_model','')=='kitchen_split':
            from export.descriptions import remark
            en,cn=remark(ln,cfg)
            remark_txt=en+'\n'+cn
        desc_txt = "\n".join([t for t, _ in dl]) if dl else ""
        rh = max(row_h, _est_height(remark_txt, 24, 13, 10),
                 _est_height(desc_txt, 34, 13, 10) if desc_txt else 0)
        ws.row_dimensions[r].height = rh
        _add_pic(ws, ln, r, pic_dir, pic_w, pic_h, pic_unit, row_h_pt=rh)
        r += 1

    last = r - 1
    dlast = D_R0 + max(0, len(lines) - 1)
    if not lines:
        ws.cell(row=Q_R0, column=1, value="No items yet / 尚未添加项目")
        last = dlast = Q_R0

    # ---------- 合计区：产品合计 → 折扣 → 折后总额 → 定金比例 → 定金金额 ----------
    def _sum_row(row: int, en: str, cn: str, value, *, money: bool = True,
                 bold: bool = False, big: bool = False, color: str = "",
                 fill=None, pct: bool = False) -> None:
        ws.merge_cells("A%d:I%d" % (row, row))
        c = ws.cell(row=row, column=1, value=_bi(en, cn, en_size=10 if big else 9,
                                                 en_bold=bold, en_color=color))
        c.font = Font(bold=bold or big, size=10 if big else (9 if not bold else 10))
        c.alignment = Alignment(horizontal="right", vertical="center")
        c2 = ws.cell(row=row, column=10, value=value)
        c2.number_format = '0%' if pct else MONEY
        c2.font = Font(bold=True, size=11 if big else 9.5, color=color or None)
        c2.alignment = Alignment(horizontal="right", vertical="center")
        ws.cell(row=row, column=11, value="")
        for cc in range(1, ncols + 1):
            cell = ws.cell(row=row, column=cc)
            if fill:
                cell.fill = fill
            cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
        ws.row_dimensions[row].height = 22

    rt = last + 1
    total_ref = "%s!V%d" % (SHEET_D, sum_rows.get("total", D_R0))
    net_ref = "%s!V%d" % (SHEET_D, sum_rows.get("net", D_R0))
    _sum_row(rt, "PRODUCT TOTAL (RM)", "产品合计", "=ROUND(%s,2)" % total_ref,
             bold=True, big=True, fill=PatternFill("solid", fgColor="EDEDED"))
    for cc in range(1, ncols + 1):
        ws.cell(row=rt, column=cc).border = Border(
            left=THIN, right=THIN, top=THIN,
            bottom=Side(style="medium", color="000000"))

    r = rt + 1
    to = cfg.totals()
    has_discount = discount is not None and float(discount) < 0.9999
    show_disc = has_discount and to.get("show_discount_row", False)
    if show_disc:
        _sum_row(r, "DISCOUNT", "折扣",
                 "=ROUND(%s-%s,2)" % (total_ref, net_ref), fill=FILL_SUM)
        r += 1
        _sum_row(r, "NET TOTAL (RM)", "折后总额", "=ROUND(%s,2)" % net_ref,
                 bold=True, big=True, color="C00000")
        for cc in range(1, ncols + 1):
            ws.cell(row=r, column=cc).border = Border(
                left=THIN, right=THIN, top=THIN,
                bottom=Side(style="medium", color="000000"))
        r += 1

    if to.get("show_deposit_rows", False):
        net_cell = net_ref if has_discount else total_ref
        dep_ref = "%s!V%d" % (SHEET_D, sum_rows.get("dep_rate", D_R0))
        _sum_row(r, "DEPOSIT RATE", "定金比例", "=%s" % dep_ref, pct=True)
        r += 1
        dep_amt = "%s!V%d" % (SHEET_D, sum_rows.get("deposit", D_R0))
        _sum_row(r, "DEPOSIT (RM)", "定金金额", "=ROUND(%s,2)" % dep_amt, bold=True)
        r += 1
        bal_ref = "%s!V%d" % (SHEET_D, sum_rows.get("balance", D_R0))
        _sum_row(r, "BALANCE (RM)", "余款", "=ROUND(%s,2)" % bal_ref)
        r += 1

    # ---------- 预报价声明（样例 A22：紧接合计行、8pt #595959、无边框、行高 16） ----------
    note = rk.get("preliminary_note", "")
    if note:
        lines = [(note, False)]
        if rk.get("preliminary_note_cn"):
            lines.append((rk["preliminary_note_cn"], True))
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
        c = ws.cell(row=r, column=1, value=_rt_lines(lines, en_size=8))
        c.font = Font(size=8, color=NOTE_GREY)
        c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws.row_dimensions[r].height = 16 if len(lines) == 1 else 30
        r += 1

    # ---------- 页脚条款（EN 一行 + CN 一行，与样例 R26 同结构、仅换序） ----------
    if rk.get("enabled", True):
        r += 1                                   # 样例在声明后空一行再写 Remark
        title = str(rk.get("title", "REMARK")).replace("：", "").strip()
        c = ws.cell(row=r, column=1,
                    value="%s / %s" % (title.upper(), rk.get("title_cn", "条款")))
        c.font = Font(bold=True, size=10)
        ws.row_dimensions[r].height = 18
        r += 1
        for it in rk.get("items", []):
            en = "%s %s" % (it.get("no", ""), it.get("label_en", it.get("label", "")))
            if it.get("en"):
                en += ": %s" % it["en"]
            lines = [(en, False)]
            if it.get("cn"):
                lines.append(("%s %s" % (it.get("no", ""), it["cn"]), True))
            _qline_rich(ws, r, lines, ncols, en_size=9)
            r += 1

        r += 1
        c = ws.cell(row=r, column=1, value="NOTES / %s" % rk.get("notes_cn", "备注"))
        c.font = Font(bold=True, size=10)
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[r].height = 18
        r += 1
        for it in rk.get("notes", []):
            lines = []
            if it.get("en"):
                lines.append(("%s %s" % (it.get("no", ""), it["en"]), False))
            if it.get("cn"):
                lines.append(("%s %s" % (it.get("no", ""), it["cn"]), True))
            _qline_rich(ws, r, lines, ncols, en_size=8.5)
            r += 1

    # ---------- 打印设置（A4 纵向，表头跨页重复） ----------
    ws.freeze_panes = "A%d" % Q_R0
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = "%d:%d" % (hdr_row, hdr_row)
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5
# ------------------------------------------------------------------ 成本毛利
def _write_cost_sheet(ws, cfg, lines, price_rows) -> None:
    ws["A1"] = "成本与毛利核算（内部，勿随报价单外发） / COST & PROFIT (INTERNAL)"
    ws["A1"].font = Font(bold=True, size=14, color="C00000")
    ws.merge_cells("A1:L1")
    ws["A2"] = ("供货价取自价格表 D 列；毛利率 = 毛利 ÷ 收入。增项与灯带不单独计成本。"
                "  Supply price from PriceList column D; margin = gross profit / revenue.")
    ws["A2"].font = Font(size=9, color=GREY)
    ws.merge_cells("A2:L2")
    ws["A2"].alignment = LEFT
    ws.row_dimensions[2].height = 26

    heads = ["序号\nNo.", "品类\nCategory", "材质 / 规格\nMaterial", "计价量\nMeasure",
             "系数\nFactor", "数量\nQty", "供货单价\nSupply Price", "成本金额\nCost",
             "收入金额\nRevenue", "毛利\nGross Profit", "毛利率\nMargin", "楼层\nFloor"]
    for i, h in enumerate(heads, 1):
        ws.cell(row=3, column=i, value=h)
    _style_header(ws, 3, len(heads))

    r0 = 4
    for i, ln in enumerate(lines):
        r = r0 + i
        drow = D_R0 + i
        prow = price_rows.get((ln.cat_key, ln.material), 4)
        drow_p = price_rows.get((ln.cat_key, ln.door_key), 0) if (ln.split and ln.door_key) else 0
        ws.cell(row=r, column=1, value=ln.idx)
        ws.cell(row=r, column=2, value="%s\n%s" % (_cat_label(ln), _cat_label(ln, True)))
        ws.cell(row=r, column=3, value="%s\n%s" % (ln.material_label, ln.material_label_en))
        ws.cell(row=r, column=4, value="=%s!P%d" % (SHEET_D, drow)).number_format = NUM2
        ws.cell(row=r, column=5, value="=%s!R%d" % (SHEET_D, drow)).number_format = NUM2
        ws.cell(row=r, column=6, value="=%s!T%d" % (SHEET_D, drow)).number_format = '0'
        if drow_p:
            ws.cell(row=r, column=7,
                    value="=%s!$D$%d+%s!$D$%d" % (SHEET_P, prow, SHEET_P, drow_p))
        else:
            ws.cell(row=r, column=7, value="=%s!$D$%d" % (SHEET_P, prow))
        ws.cell(row=r, column=7).number_format = MONEY
        if cfg.category(ln.cat_key).get("measure") == "pcs":
            ws.cell(row=r, column=8, value="=ROUND(G%d*F%d,2)" % (r, r))
        else:
            ws.cell(row=r, column=8, value="=ROUND(D%d*E%d*G%d*F%d,2)" % (r, r, r, r))
        ws.cell(row=r, column=8).number_format = MONEY
        ws.cell(row=r, column=9, value="=%s!V%d" % (SHEET_D, drow)).number_format = MONEY
        ws.cell(row=r, column=10, value="=I%d-H%d" % (r, r)).number_format = MONEY
        ws.cell(row=r, column=11, value="=IF(I%d=0,0,J%d/I%d)" % (r, r, r)).number_format = '0.0%'
        ws.cell(row=r, column=12, value="%s\n%s" % (ln.floor, ln.floor_en or ""))
        for c in range(1, 13):
            cell = ws.cell(row=r, column=c)
            cell.border = BORDER
            cell.alignment = LEFT if c in (2, 3, 12) else (CENTER if c in (1, 6) else RIGHT)
            cell.font = Font(size=9)
        ws.row_dimensions[r].height = 30

    last = r0 + len(lines) - 1 if lines else r0
    r = last + 1
    ws.cell(row=r, column=1, value="合计 / TOTAL")
    ws.merge_cells("A%d:G%d" % (r, r))
    ws.cell(row=r, column=1).alignment = RIGHT
    ws.cell(row=r, column=1).font = Font(bold=True)
    for col, f in ((8, "=SUM(H%d:H%d)"), (9, "=SUM(I%d:I%d)"), (10, "=SUM(J%d:J%d)")):
        c = ws.cell(row=r, column=col, value=f % (r0, last))
        c.number_format = MONEY
        c.font = Font(bold=True)
    c = ws.cell(row=r, column=11, value="=IF(I%d=0,0,J%d/I%d)" % (r, r, r))
    c.number_format = '0.0%'
    c.font = Font(bold=True)
    for cc in range(1, 13):
        ws.cell(row=r, column=cc).fill = FILL_SUM
        ws.cell(row=r, column=cc).border = BORDER

    widths = {"A": 5, "B": 20, "C": 30, "D": 10, "E": 8, "F": 7, "G": 13, "H": 13,
              "I": 13, "J": 13, "K": 9, "L": 10}
    for k, v in widths.items():
        ws.column_dimensions[k].width = v
    _fit(ws)


# ------------------------------------------------------------------ 材料用量
def _write_usage_sheet(ws, cfg, lines) -> None:
    from export.bilingual_sheets import usage_sheet
    return usage_sheet(ws,cfg,lines)


def _write_summary_sheet(ws, cfg, lines, summary, kind: str = "internal") -> None:
    from export.bilingual_sheets import summary_sheet
    return summary_sheet(ws,cfg,lines,summary,kind)


def _write_notes_sheet(ws, cfg, quote, summary, kind: str = "internal") -> None:
    from export.bilingual_sheets import notes_sheet
    return notes_sheet(ws,cfg,quote,summary,kind)


def export_workbook(path: str, cfg, quote: Dict[str, Any], lines: List[Any],
                    summary: Dict[str, Any], kind: str = "internal") -> str:
    """kind: internal（内部版）/ customer（客户版）。返回文件路径。

    Preserve the saved line order, including manual moves across floor groups.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    mode = quote.get("mode") or cfg.price_mode
    discount = float(quote.get("discount") if quote.get("discount") not in (None, "") else 1.0)
    deposit = float(quote.get("deposit_rate", 0.5) or 0.0)
    _set_currency(cfg.currency)

    wb = Workbook()
    ws_q = wb.active
    ws_q.title = SHEET_Q
    ws_d = wb.create_sheet(SHEET_D)
    ws_p = wb.create_sheet(SHEET_P)
    ws_c = wb.create_sheet(SHEET_C) if kind == "internal" else None
    ws_u = wb.create_sheet(SHEET_U) if kind == "internal" else None
    ws_s = wb.create_sheet(SHEET_S)
    ws_n = wb.create_sheet(SHEET_N)

    price_rows, addon_rows = _write_price_sheet(ws_p, cfg, mode, include_cost=(kind == "internal"))
    sum_rows = _write_detail_sheet(ws_d, cfg, lines, price_rows, addon_rows)
    # 明细汇总区的折扣 / 定金输入格写入真实值
    _set_detail_discount(ws_d, len(lines), discount, deposit)

    _write_quote_sheet(ws_q, cfg, quote, lines, summary, discount, deposit,
                       PIC_DIR, sum_rows)
    if kind == "internal":
        _write_cost_sheet(ws_c, cfg, lines, price_rows)
        _write_usage_sheet(ws_u, cfg, lines)
    _write_summary_sheet(ws_s, cfg, lines, summary, kind)
    _write_notes_sheet(ws_n, cfg, quote, summary, kind)

    if kind == "customer":
        ws_d.sheet_state = "hidden"
        # 客户版价格表：只保留报价单价相关列
        for col in ("D", "E", "F", "G"):
            ws_p.column_dimensions[col].hidden = True

    from export.business import finalize as finalize_business
    finalize_business(wb,cfg,quote,lines,summary,kind,price_rows,addon_rows,sum_rows)
    from export.standalone_layout import finalize_workbook
    finalize_workbook(wb, cfg, quote, kind, lines)
    wb.save(path)
    from export.formula_cache import recalculate
    recalculate(path)
    return path


def _set_detail_discount(ws_d, nlines: int, discount: float, deposit: float) -> None:
    """把明细表汇总区的折扣 / 定金输入格改成实际值（保持公式联动）。"""
    start = D_R0 + max(nlines, 1) + 2
    for r in range(start, start + 20):
        v = ws_d.cell(row=r, column=1).value
        if not isinstance(v, str):
            continue
        cell = ws_d.cell(row=r, column=22)
        if v.startswith("折扣系数"):
            cell.value = float(discount)
        elif v.startswith("定金比例"):
            cell.value = float(deposit)


def default_filename(quote: Dict[str, Any], kind: str) -> str:
    no = (quote.get("quote_no") or "quote").replace("/", "-")
    tag = "客户版" if kind == "customer" else "内部版"
    return "%s_%s_%s.xlsx" % (no, quote.get("customer", "") or "客户", tag)
