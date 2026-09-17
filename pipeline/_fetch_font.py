#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下載 Playfair Display（SIL Open Font License 1.1）latin 子集 woff2 供站內自託管。

Playfair Display 在 Google Fonts 是**可變字體**：一個 woff2 檔已涵蓋 400–900 全字重，
所以只需一個檔案，CSS 用 `font-weight: 400 900` 宣告即可。

用法：python pipeline/_fetch_font.py
產出：assets/fonts/playfair-display-latin.woff2
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "fonts"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}
CSS_URL = "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400..900&display=swap"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(CSS_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as resp:
        css = resp.read().decode("utf-8")

    blocks = re.findall(r"/\*\s*latin\s*\*/\s*@font-face\s*\{(.*?)\}", css, re.S)
    if not blocks:
        raise SystemExit("找不到 latin 子集的 @font-face，Google Fonts 回應格式可能已變。")

    block = blocks[0]
    m_u = re.search(r"url\((https://[^)]+\.woff2)\)", block)
    if not m_u:
        raise SystemExit("latin 區塊沒有 woff2 網址。")

    req2 = urllib.request.Request(m_u.group(1), headers=UA)
    with urllib.request.urlopen(req2, timeout=60) as resp2:
        data = resp2.read()

    target = OUT / "playfair-display-latin.woff2"
    target.write_bytes(data)
    print(f"已下載 {target.name}（{len(data) // 1024} KB，涵蓋 400–900 可變字重）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
