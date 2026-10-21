# -*- coding: utf-8 -*-
"""报价单打印 / PDF 用的 HTML 模板（客户版与内部版）。

版式与 Excel 报价单同口径：
    Logo + 公司信息 | DATE / REFERENCE NO. | ATTN / PROJECT | 标题（英主中辅）
    10 列表格：NO. / PRODUCT / PICTURE / DESCRIPTION / DIMENSION /
              PROJECTED AREA / UNIT / QTY / PRICE (RM) / REMARK
    楼层分组标题带该楼层小计；末尾产品合计 / 折扣 / 折后总额 / 定金比例 /
    定金金额 / 余款；再往下是条款与备注。

客户版不出现成本与毛利；内部版在表格右侧追加 系数 / 成本 / 毛利 三列。
英文为主（第一行、字号大、颜色深），中文为辅（第二行、约 65% 字号、浅灰）。
"""
from __future__ import annotations

import base64
import os
from datetime import datetime
from typing import Any, Dict, List

from core.floors import floor_name_cn, floor_name_en, floor_rank, normalize_floor
from core.rooms import room_en as room_en_of

try:
    from export.illustration import render as render_illustration
    from export.illustration import resolve_kind, PIC_VERSION
except Exception:  # pragma: no cover
    try:
        from illustration import render as render_illustration
        from illustration import resolve_kind, PIC_VERSION
    except Exception:
        render_illustration = None
        PIC_VERSION = "v1"

        def resolve_kind(cat_key, cab_name="", cab_name_en=""):
            return cat_key or "cabinet"


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIC_DIR = os.path.join(ROOT_DIR, "exports", "_pics")
PIC_W, PIC_H = 100, 66         # 客户版打印页显示尺寸（px），与 PICTURE 列宽匹配
PIC_W_I, PIC_H_I = 84, 56      # 内部版列更多，示意图相应缩小


def _dim_text(ln) -> str:
    """尺寸文本：高或深为 0 时自动省略，与 Excel 报价单 DIMENSION 列同规则。"""
    L, H, D = round(ln.length_mm), round(ln.height_mm), round(ln.depth_mm)
    if not H and not D:
        return "%d" % L
    if not H:
        return "%d*%d" % (L, D)
    return "%d*%d*%d" % (L, H, D)

_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]


def _money(x: float, cur: str = "RM") -> str:
    return "%s %s" % (cur, format(round(float(x or 0), 2), ",.2f"))


def _esc(s: Any) -> str:
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _en_date(s: str) -> str:
    txt = str(s or "").strip()
    for sep in ("-", "/", "."):
        if sep in txt:
            parts = txt.split(sep)
            if len(parts) == 3 and all(p.strip().isdigit() for p in parts):
                y, m, d = (int(p) for p in parts)
                if 1 <= m <= 12:
                    return "%d %s %d" % (d, _EN_MONTHS[m - 1], y)
    return txt


def _b64_file(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def _logo_uri(cfg) -> str:
    logo = (cfg.company() or {}).get("logo", "")
    if not logo:
        return ""
    if not os.path.isabs(logo):
        logo = os.path.join(__import__("core.config",fromlist=["DATA_DIR"]).DATA_DIR,"company-logo.png") if logo == "data/company-logo.png" else os.path.join(ROOT_DIR,logo)
    return _b64_file(logo)


def _pic_data_uri(ln) -> str:
    """生成（或复用）该行示意图，返回 data:image/png;base64,...；失败返回空串。

    打印页图片显示尺寸比 Excel 小，故用 dim_font=26 单独渲染一份，
    保证图内 W / H / D 标注仍然清晰。
    """
    if render_illustration is None:
        return ""
    try:
        kind = resolve_kind(ln.cat_key, ln.cab_name or "", ln.cab_name_en or "")
        name = "%s_%d_%d_%d_mm_pf_%s.png" % (
            kind, round(ln.length_mm), round(ln.height_mm), round(ln.depth_mm),
            PIC_VERSION)
        path = os.path.join(PIC_DIR, name)
        if not os.path.exists(path):
            os.makedirs(PIC_DIR, exist_ok=True)
            render_illustration(kind, ln.length_mm, ln.height_mm, ln.depth_mm,
                                path, dim_unit="mm", cab_name=ln.cab_name or "",
                                cab_name_en=ln.cab_name_en or "", dim_font=30)
        return _b64_file(path)
    except Exception:
        return ""


def _remark_text(ln,cfg):
    from export.descriptions import remark
    return remark(ln,cfg)


def _bi(en: str, cn: str = "", tag: str = "div") -> str:
    """英文主行 + 中文副行。"""
    out = ""
    if en:
        out += "<%s class='en'>%s</%s>" % (tag, _esc(en), tag)
    if cn:
        out += "<%s class='cn'>%s</%s>" % (tag, _esc(cn), tag)
    return out


def _group_rows(lines: List[Any]):
    """按录入顺序切楼层组 → [(floor, start, end)]。"""
    groups = []
    for i, ln in enumerate(lines):
        f = normalize_floor(getattr(ln, "floor", ""))
        if not groups or groups[-1][0] != f:
            groups.append([f, i, i])
        else:
            groups[-1][2] = i
    return groups


def render(quote: Dict[str, Any], lines: List[Any], summary: Dict[str, Any],
           cfg, kind: str = "customer", auto_print: bool = False) -> str:
    cur = cfg.currency
    company = cfg.company()
    remark = cfg.remark()
    internal = kind == "internal"
    ncol = 10

    groups = _group_rows(lines)
    group_of = {}
    for f, a, b in groups:
        for i in range(a, b + 1):
            group_of[i] = (f, a, b)

    rows = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        f, a, b = group_of[i]
        if i == a:
            code = f
            en = cfg.floor_en(f)
            cn = floor_name_cn(f)
            sub = sum(l.amount for l in lines[a:b + 1])
            rows.append(
                "<tr class='grp'><td colspan='%d' class='grpcell'>"
                "<span class='grpen'>%s · %s</span>"
                "<span class='grpcn'>%s · %d 项</span>"
                "<span class='grpsum'>SUBTOTAL / 小计 <b>%s</b></span>"
                "</td></tr>"
                % (ncol, _esc(code), _esc(en.upper()),
                   _esc(cn or ""), b - a + 1, _money(sub, "")))

        cab_en = (ln.cab_name_en or "").strip() or (ln.cat_name_en or "").strip()
        cab_cn = (ln.cab_name or "").strip() or (ln.cat_name or "").strip()

        # 描述：英文整块在上（楼层·区域 / 材质），中文整块在下
        floor_en = (ln.floor_en or "").strip() or floor_name_en(ln.floor)
        room_en = (ln.room_en or "").strip()
        if not room_en or room_en == (ln.room or "").strip():
            room_en = room_en_of(ln.room)
        mat_en = (ln.material_label_en or "").strip()
        mat_cn = (ln.material_label or "").strip()
        if mat_en == mat_cn:
            mat_en = ""
        en_lines = [x for x in (" · ".join([e for e in (floor_en, room_en) if e]), mat_en) if x]
        cn_lines = [" · ".join([c for c in (ln.floor, ln.room) if c])]
        if mat_cn:
            cn_lines.append(mat_cn)
        if ln.room_note_en:
            en_lines.append(ln.room_note_en)
        if ln.room_note:
            cn_lines.append(ln.room_note)
        desc = "".join("<div class='en'>%s</div>" % _esc(x) for x in en_lines)
        desc += "".join("<div class='cn'>%s</div>" % _esc(x) for x in cn_lines if x)

        uri = _pic_data_uri(ln)
        pw, ph = (PIC_W_I, PIC_H_I) if internal else (PIC_W, PIC_H)
        pic = ("<img src='%s' width='%d' height='%d'>" % (uri, pw, ph)) if uri else ""

        extra = ""
        r_en, r_cn = _remark_text(ln, cfg)
        rmk = ("<div class='en'>%s</div>" % _esc(r_en) if r_en else "") + ("<div class='cn'>%s</div>" % _esc(r_cn) if r_cn else "")
        measure_type = cfg.category(ln.cat_key).get("measure", "area")
        rows.append(
            "<tr>"
            "<td class='c'>%d</td>"
            "<td class='prod'>%s</td>"
            "%s"
            "<td>%s</td>"
            "<td class='c dim'>%s</td>"
            "<td class='n'>%s</td>"
            "<td class='c'>%s</td>"
            "<td class='c'>%g</td>"
            "<td class='n'>%s</td>"
            "%s"
            "<td class='rmk'>%s</td>"
            "</tr>"
            % (i + 1, _bi(cab_en.upper(), cab_cn, "div"),
               "<td class='pic'>%s</td>" % pic,
               desc,
               _dim_text(ln),
               ("/" if measure_type == "pcs" else "%.2f" % ln.measure),
               _esc(ln.unit), ln.qty,
               _money(ln.amount, ""), extra, rmk))
        i += 1

    # ---- 表头 ----
    heads = [("NO.", "序号", "4.5%"), ("PRODUCT", "产品名称", "12%"),
                 ("PICTURE", "示意图", "15.5%"), ("DESCRIPTION", "描述", "19.5%"),
                 ("DIMENSION (MM)", "尺寸 W*H*D", "8.5%"),
                 ("PROJECTED AREA", "投影面积", "6.5%"), ("UNIT", "单位", "4.5%"),
                 ("QTY", "数量", "4.5%"), ("PRICE (RM)", "单价", "8.5%"),
                 ("REMARK", "备注", "16%")]
    cols = "".join('<col style="width:%s">' % w for _, _, w in heads)
    thead = "".join("<th>%s</th>" % _bi(en, cn) for en, cn, _ in heads)

    # ---- 合计区 ----
    total = float(summary.get("total", 0) or 0)
    net = float(summary.get("net_total", 0) or 0)
    disc = float(summary.get("discount", 1) or 1)
    dep_rate = float(summary.get("deposit_rate", 0) or 0)
    dep = float(summary.get("deposit", 0) or 0)
    bal = float(summary.get("balance", 0) or 0)
    sum_rows = [("PRODUCT TOTAL (RM)", "产品合计", _money(total, ""), "", "")]
    if disc < 0.9999:
        sum_rows.append(("DISCOUNT", "折扣", _money(total - net, ""), "",
                         "× %.2f" % disc))
        sum_rows.append(("NET TOTAL (RM)", "折后总额", _money(net, ""), "big", ""))
    sum_rows.append(("DEPOSIT RATE", "定金比例", "%.0f%%" % (dep_rate * 100), "", ""))
    sum_rows.append(("DEPOSIT (RM)", "定金金额", _money(dep, ""), "", ""))
    sum_rows.append(("BALANCE (RM)", "余款", _money(bal, ""), "", ""))
    if internal:
        sum_rows.append(("COST", "成本", _money(summary.get("supply_total", 0), ""), "", ""))
        sum_rows.append(("GROSS PROFIT", "毛利",
                         "%s（%.1f%%）" % (_money(summary.get("gross_profit", 0), ""),
                                          float(summary.get("gross_margin", 0) or 0)),
                         "", ""))
    sum_html = "".join(
        "<tr%s><td class='lbl'>%s<span class='cn'>%s</span></td>"
        "<td class='val%s'>%s</td><td class='rate'>%s</td></tr>"
        % (" class='hi'" if cls == "big" else "", _esc(en), _esc(cn),
           " big" if cls == "big" else "", _esc(val), _esc(extra))
        for en, cn, val, cls, extra in sum_rows)

    remark_items = "".join(
        "<li><span class='en'>%s、%s</span>%s%s</li>"
        % (_esc(it.get("no", "")), _esc(it.get("label", "")),
           ("：%s" % _esc(it["en"])) if it.get("en") else "",
           ("<span class='cn'>%s</span>" % _esc(it["cn"])) if it.get("cn") else "")
        for it in remark.get("items", []))
    remark_notes = "".join(
        "<li><span class='en'>%s %s</span><span class='cn'>%s</span></li>"
        % (_esc(it.get("no", "")), _esc(it.get("en", "")), _esc(it.get("cn", "")))
        for it in remark.get("notes", []))

    title_en = (company.get("title", "QUOTATION") or "QUOTATION").upper()
    stamp = "INTERNAL / 内部版" if internal else "CUSTOMER / 客户版"
    note_html = ""
    for en,cn in ((quote.get("note_en",""),quote.get("note","")),(quote.get("terms_en",""),quote.get("terms",""))):
        if en or cn: note_html += "<div class='note'>"+_bi(en,cn,"div")+"</div>"
    logo = _logo_uri(cfg)

    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>%(title)s %(no)s</title>
<style>
  @page { size: A4 portrait; margin: 11mm 9mm 12mm; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "SF Pro Text", "Helvetica Neue", "Segoe UI",
         "Microsoft YaHei UI", "PingFang SC", Arial, sans-serif;
         color: #1d1d1f; margin: 0; padding: 14px 16px 24px; font-size: 9px;
         line-height: 1.4; background: #fff;
         -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  @media print { body { padding: 0; } }
  .en { font-weight: 600; color: #1d1d1f; }
  .cn { display: block; font-size: 65%%; font-weight: 400; color: #86868b;
        line-height: 1.25; }
  /* ---------- 眉头 ---------- */
  .top { display: flex; justify-content: space-between; align-items: flex-start; }
  .brand { display: flex; gap: 10px; align-items: flex-start; }
  .brand img { height: 38px; width: auto; }
  .co { font-size: 15px; font-weight: 700; letter-spacing: .3px; }
  .meta { font-size: 8px; color: #6e6e73; margin-top: 2px; }
  .right { text-align: right; font-size: 8.5px; color: #1d1d1f; line-height: 1.6; }
  .right b { font-weight: 700; }
  .stamp { display: inline-block; font-size: 8px; color: #0071e3;
           border: 1px solid #0071e3; border-radius: 9px; padding: 1px 7px;
           margin-bottom: 4px; }
  .attn { margin-top: 8px; padding-top: 6px; border-top: 2px solid #1d1d1f;
          font-size: 9.5px; font-weight: 700; }
  .greet { font-size: 8px; color: #6e6e73; margin-top: 3px; }
  .title { text-align: center; margin: 9px 0 7px; padding: 5px 0;
           border-top: 1px solid #1d1d1f; border-bottom: 1px solid #1d1d1f; }
  .title .t { font-size: 14px; font-weight: 700; letter-spacing: 1.2px; }
  .title .s { font-size: 8px; color: #86868b; letter-spacing: 2px; }
  /* ---------- 表格 ---------- */
  table { width: 100%%; border-collapse: collapse; table-layout: fixed; }
  thead { display: table-header-group; }
  th { background: #ededed; font-size: 8px; font-weight: 700; padding: 4px 3px;
       border: 1px solid #c9c9ce; border-top: 2px solid #1d1d1f; text-align: center;
       vertical-align: middle; }
  th .cn { font-weight: 400; }
  td { border: 1px solid #dcdce1; padding: 2px 3px; vertical-align: middle; }
  tr { page-break-inside: avoid; break-inside: avoid; }
  .c { text-align: center; }
  .n { text-align: right; font-variant-numeric: tabular-nums; }
  .prod .en { font-size: 8.5px; letter-spacing: .2px; }
  .prod .cn { font-size: 7px; }
  .dim { font-variant-numeric: tabular-nums; letter-spacing: .2px; }
  .rmk { font-size: 7px; color: #6e6e73; line-height: 1.35; }
  .rmk .en { font-size: 7px; font-weight: 600; color: #1d1d1f; }
  .rmk .cn { font-size: 6.2px; color: #86868b; }
  td.pic { padding: 2px; text-align: center; }
  td.pic img { display: block; margin: 0 auto; max-width: 100%%; height: auto; }
  /* ---------- 楼层分组 ---------- */
  tr.grp td.grpcell { background: #eaf3fe; border: 1px solid #bfd7f2;
                      padding: 4px 6px; font-size: 8.5px; }
  .grpen { font-weight: 700; color: #0b3d66; letter-spacing: .4px; }
  .grpcn { color: #6e6e73; font-size: 7px; margin-left: 6px; }
  .grpsum { float: right; color: #0b3d66; font-size: 8px; }
  .grpsum b { font-variant-numeric: tabular-nums; }
  /* ---------- 合计 ---------- */
  .sumwrap { margin-top: 14px; page-break-inside: avoid; break-inside: avoid; }
  .sumh { padding-bottom: 3px; border-bottom: 1px solid #dcdce1; }
  .sumh .h-en { font-size: 9px; font-weight: 700; letter-spacing: 1px; color: #1d1d1f; }
  .sumh .h-cn { font-size: 7px; color: #86868b; margin-left: 6px; letter-spacing: .5px; }
  .sum { display: flex; justify-content: flex-end; margin-top: 6px;
         page-break-inside: avoid; break-inside: avoid; }
  .sum table { width: 52%%; table-layout: auto; }
  .sum td { border: none; padding: 3px 6px; }
  .sum tr { border-bottom: 1px solid #e5e5ea; }
  .sum .lbl { text-align: right; font-size: 8.5px; font-weight: 600; }
  .sum .lbl .cn { display: inline; font-size: 7px; margin-left: 4px; }
  .sum .val { text-align: right; font-variant-numeric: tabular-nums;
              font-weight: 700; width: 34%%; }
  .sum .rate { text-align: right; color: #86868b; font-size: 7.5px; width: 12%%; }
  .sum tr.hi td { border-top: 2px solid #1d1d1f; border-bottom: 2px solid #1d1d1f;
                  padding-top: 5px; padding-bottom: 5px; }
  .sum .big { font-size: 12px; color: #c00000; }
  /* ---------- 条款 ---------- */
  .cols { display: flex; gap: 12px; margin-top: 10px; page-break-inside: avoid; }
  .cols > div { flex: 1; }
  .box { border: 1px solid #dcdce1; border-radius: 5px; padding: 6px 9px; }
  .box h3 { margin: 0 0 4px; font-size: 9px; letter-spacing: .3px; }
  ul { margin: 0; padding-left: 13px; }
  li { margin-bottom: 3px; font-size: 7.5px; line-height: 1.4; }
  li .en { font-size: 7.5px; }
  li .cn { font-size: 6.5px; }
  .note { margin-top: 8px; font-size: 7.5px; color: #6e6e73; }
  .sign { display: flex; gap: 40px; margin-top: 26px;
          page-break-inside: avoid; break-inside: avoid; }
  .sign > div { flex: 1; }
  .sign .line { border-top: 1px solid #1d1d1f; height: 1px; margin-bottom: 4px; }
  .sign span { font-size: 7px; color: #6e6e73; letter-spacing: .2px; }
  .foot { margin-top: 10px; border-top: 1px solid #dcdce1; padding-top: 5px;
          font-size: 7px; color: #86868b; display: flex;
          justify-content: space-between; }
  @media print { .noprint { display: none; } }
  .noprint { position: fixed; right: 16px; bottom: 16px; z-index: 9; }
  .noprint button { font: inherit; padding: 7px 13px; border-radius: 8px;
    border: 0; background: #0071e3; color: #fff; cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,.18); }
</style></head>
<body>
<div class="noprint"><button onclick="window.print()">Print / Save as PDF</button></div>

<div class="top">
  <div class="brand">
    %(logo)s
    <div>
      <div class="co">%(co)s</div>
      <div class="meta">%(addr)s</div>
      <div class="meta">%(contact)s</div>
    </div>
  </div>
  <div class="right">
    <div class="stamp">%(stamp)s</div>
    <div><b>DATE:</b> %(date)s</div>
    <div><b>REFERENCE NO.:</b> %(no)s</div>
  </div>
</div>

<div class="attn">ATTN: %(customer)s　　PROJECT: %(project)s</div>
<div class="greet">%(greet)s</div>

<div class="title">
  <div class="t">%(title)s</div>
  <div class="s">报价单</div>
</div>

<table>
<colgroup>%(cols)s</colgroup>
<thead><tr>%(thead)s</tr></thead>
<tbody>%(rows)s</tbody>
</table>

<div class="sumwrap">
  <div class="sumh"><span class="h-en">SUMMARY</span><span class="h-cn">报价汇总</span></div>
  <div class="sum"><table>%(sum)s</table></div>
</div>

<div class="cols">
  <div class="box"><h3>REMARK / 条款</h3><ul>%(remark_items)s</ul></div>
  <div class="box"><h3>NOTES / 备注</h3><ul>%(remark_notes)s</ul></div>
</div>
%(note_html)s
<div class="sign">
  <div><div class="line"></div><span>客户确认 CONFIRMED BY / 日期 DATE</span></div>
  <div><div class="line"></div><span>公司代表 FOR &amp; ON BEHALF OF</span></div>
</div>
<div class="foot"><span>%(prelim)s</span><span>%(gen)s</span></div>
%(auto)s
</body></html>""" % {
        "title": _esc(title_en), "no": _esc(quote.get("quote_no", "")),
        "logo": ("<img src='%s'>" % logo) if logo else "",
        "co": _esc(company.get("name", "")),
        "addr": _esc(company.get("address", "")),
        "contact": _esc("%s　%s" % (company.get("mobile", ""), company.get("email", ""))),
        "stamp": stamp,
        "date": _esc(_en_date(quote.get("quote_date", ""))),
        "greet": _esc(company.get("greeting", "")),
        "customer": _esc(quote.get("customer", "") or "-"),
        "project": _esc(quote.get("project", "") or "-"),
        "cols": cols, "thead": thead, "rows": "".join(rows),
        "sum": sum_html,
        "remark_items": remark_items, "remark_notes": remark_notes,
        "note_html": note_html,
        "prelim": _esc(remark.get("preliminary_note", "")),
        "gen": "Generated %s · 全屋定制报价系统 v2" % datetime.now().strftime("%Y-%m-%d %H:%M"),
        "auto": "<script>window.addEventListener('load',function(){setTimeout(function(){"
                "window.print()},350)})</script>" if auto_print else "",
    }
