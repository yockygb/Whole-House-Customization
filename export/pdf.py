# -*- coding: utf-8 -*-
"""PDF 导出：用本机 Edge / Chrome 的 headless 打印能力把报价单 HTML 转成 PDF。"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional

_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser() -> Optional[str]:
    for p in _CANDIDATES:
        if os.path.exists(p):
            return p
    for name in ("msedge", "chrome", "chromium"):
        p = shutil.which(name)
        if p:
            return p
    return None


def html_to_pdf(url: str, out_path: str, timeout: int = 90) -> bool:
    browser = find_browser()
    if not browser:
        return False
    # ★ 必须是绝对路径：Edge 对 `--print-to-pdf=相对路径` 会静默不写文件
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
    profile = tempfile.mkdtemp(prefix="wbq_pdf_")
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run",
           "--no-default-browser-check", "--disable-extensions",
           "--user-data-dir=%s" % profile,
           "--no-pdf-header-footer", "--print-to-pdf-no-header",
           "--print-to-pdf=%s" % out_path, url]
    deadline=time.monotonic()+timeout
    try:
        subprocess.run(cmd, timeout=timeout, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
        # Edge's launcher can exit before its child has finished writing the PDF.
        while time.monotonic()<deadline:
            if os.path.exists(out_path) and os.path.getsize(out_path)>800:
                with open(out_path,'rb') as f:
                    f.seek(-64,os.SEEK_END)
                    if b'%%EOF' in f.read():return True
            time.sleep(.1)
    except Exception:
        return False
    finally:
        for _ in range(50):
            shutil.rmtree(profile, ignore_errors=True)
            if not os.path.exists(profile):break
            time.sleep(.1)
    return False
