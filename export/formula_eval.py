# -*- coding: utf-8 -*-
"""
迷你 Excel 公式求值器（测试用）
===============================
不依赖 Excel，把导出的 xlsx 里的公式按 Excel 语义重算一遍，用于验证
「引擎算出来的金额」与「Excel 公式算出来的金额」是否一致。

支持：+ - * / & 比较运算、括号、单元格引用（含 表名!A1）、
ROUND / MAX / MIN / ABS / IF / OR / AND / SUM / SUMIF，
SUMIF 支持 "*文本*"、"1F*" 这类通配条件。
"""
from __future__ import annotations

import fnmatch
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Tuple

from openpyxl.utils import column_index_from_string

TOKEN_RE = re.compile(
    r'\s*(?:(?P<str>"[^"]*")|(?P<num>\d+\.?\d*)|'
    r'(?P<ref>(?:[^\s!()+\-*/<>=,&]+!)?\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)|'
    r'(?P<func>[A-Z][A-Z0-9.]*)\s*\()'
)


def _col_letter(idx: int) -> str:
    s = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


class Evaluator:
    def __init__(self, wb):
        self.wb = wb
        self.cache = {}

    # ---------- 单元格 ----------
    def cell(self, sheet: str, coord: str):
        coord = coord.replace("$", "").upper()
        key = (sheet, coord)
        if key in self.cache:
            return self.cache[key]
        v = self.wb[sheet][coord].value
        if isinstance(v, str) and v.startswith("="):
            v = self.eval_formula(v[1:], sheet)
        self.cache[key] = v
        return v

    # ---------- 求值 ----------
    def eval_formula(self, formula: str, sheet: str):
        saved = (getattr(self, "tokens", None), getattr(self, "pos", 0),
                 getattr(self, "sheet", sheet))
        self.tokens = self._tokenize(formula)
        self.pos = 0
        self.sheet = sheet
        try:
            return self._cmp()
        finally:
            self.tokens, self.pos, self.sheet = saved

    def _tokenize(self, s: str) -> List[Tuple[str, Any]]:
        toks, i = [], 0
        while i < len(s):
            m = TOKEN_RE.match(s, i)
            if not m:
                ch = s[i]
                if ch in "+-*/<>=(),:&":
                    toks.append(("op", ch))
                    i += 1
                    continue
                if ch.isspace():
                    i += 1
                    continue
                raise ValueError("无法解析: %r (在 %r 中)" % (s[i:i + 12], s))
            i = m.end()
            if m.group("str"):
                toks.append(("str", m.group("str")[1:-1]))
            elif m.group("num"):
                toks.append(("num", float(m.group("num"))))
            elif m.group("ref"):
                toks.append(("ref", m.group("ref")))
            elif m.group("func"):
                toks.append(("func", m.group("func")))
        return toks

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _next(self):
        t = self._peek()
        self.pos += 1
        return t

    def _expect(self, val):
        t = self._next()
        if t[1] != val:
            raise ValueError("期望 %r，得到 %r" % (val, t))

    def _cmp(self):
        left = self._concat()
        t = self._peek()
        if t[0] == "op" and t[1] in (">", "<", ">=", "<=", "=", "<>"):
            op = self._next()[1]
            right = self._concat()
            return {">": left > right, "<": left < right, ">=": left >= right,
                    "<=": left <= right, "=": left == right, "<>": left != right}[op]
        return left

    def _concat(self):
        val = self._expr()
        while True:
            t = self._peek()
            if t[0] == "op" and t[1] == "&":
                self._next()
                val = "%s%s" % (val, self._expr())
            else:
                return val

    def _expr(self):
        val = self._term()
        while True:
            t = self._peek()
            if t[0] == "op" and t[1] in "+-":
                op = self._next()[1]
                r = self._term()
                val = val + r if op == "+" else val - r
            else:
                return val

    def _term(self):
        val = self._factor()
        while True:
            t = self._peek()
            if t[0] == "op" and t[1] in "*/":
                op = self._next()[1]
                r = self._factor()
                val = val * r if op == "*" else (val / r if r else 0)
            else:
                return val

    def _factor(self):
        t = self._peek()
        if t[0] == "op" and t[1] == "-":
            self._next()
            return -self._factor()
        if t[0] == "op" and t[1] == "+":
            self._next()
            return self._factor()
        return self._primary()

    def _primary(self):
        kind, val = self._next()
        if kind == "num":
            return val
        if kind == "str":
            return val
        if kind == "ref":
            return self._ref(val)
        if kind == "func":
            args = []
            if self._peek()[1] != ")":
                args.append(self._cmp())
                while self._peek() == ("op", ","):
                    self._next()
                    args.append(self._cmp())
            self._expect(")")
            return self._call(val, args)
        if (kind, val) == ("op", "("):
            v = self._cmp()
            self._expect(")")
            return v
        raise ValueError("意外的 token: %r %r" % (kind, val))

    def _ref(self, ref: str):
        if "!" in ref:
            sheet, coord = ref.split("!")
            sheet = sheet.strip("'")
        else:
            sheet, coord = self.sheet, ref
        if ":" in coord:
            a, b = coord.split(":")
            return ("range", sheet, a, b)
        return self.cell(sheet, coord)

    def _range_values(self, rng):
        _, sheet, a, b = rng
        ma = re.match(r"([A-Z]+)(\d+)", a.replace("$", ""))
        mb = re.match(r"([A-Z]+)(\d+)", b.replace("$", ""))
        c1, r1 = column_index_from_string(ma.group(1)), int(ma.group(2))
        c2, r2 = column_index_from_string(mb.group(1)), int(mb.group(2))
        out = []
        for r in range(min(r1, r2), max(r1, r2) + 1):
            for c in range(min(c1, c2), max(c1, c2) + 1):
                out.append(self.cell(sheet, "%s%d" % (_col_letter(c), r)))
        return out

    def _call(self, name, args):
        n = name.upper()
        if n == "ROUND":
            v, d = float(args[0]), int(args[1])
            q = Decimal(1).scaleb(-d)
            return float(Decimal(repr(v)).quantize(q, rounding=ROUND_HALF_UP))
        if n == "MAX":
            return max(args)
        if n == "MIN":
            return min(args)
        if n == "ABS":
            return abs(args[0])
        if n == "OR":
            return any(bool(a) for a in args)
        if n == "AND":
            return all(bool(a) for a in args)
        if n == "IF":
            return args[1] if args[0] else args[2]
        if n == "SUM":
            total = 0
            for a in args:
                if isinstance(a, tuple) and a[0] == "range":
                    total += sum(v for v in self._range_values(a) if isinstance(v, (int, float)))
                elif isinstance(a, (int, float)):
                    total += a
            return total
        if n == "SUMIF":
            rng, crit, sumrng = args
            vals = self._range_values(rng)
            sums = self._range_values(sumrng)
            total = 0
            for v, s in zip(vals, sums):
                if self._match(v, crit):
                    total += s if isinstance(s, (int, float)) else 0
            return total
        raise ValueError("未实现的函数: %s" % name)

    @staticmethod
    def _match(value, crit) -> bool:
        if isinstance(crit, (int, float)):
            return isinstance(value, (int, float)) and abs(value - crit) < 1e-9
        c = str(crit)
        v = "" if value is None else str(value)
        if "*" in c or "?" in c:
            return fnmatch.fnmatchcase(v, c)
        return v == c
