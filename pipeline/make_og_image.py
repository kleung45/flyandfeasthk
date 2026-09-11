#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生社群分享封面圖 assets/og-cover.png（1200×630）。

Facebook／WhatsApp／Twitter 的分享卡片用 1.91:1 橫圖最理想，
原本用方形 logo 會被裁切或縮小，點擊率較低。

用法：
    python pipeline/make_og_image.py

需要 Pillow（已安裝於隔離虛擬環境：~/.workbuddy/binaries/python/envs/default）。
若要改文案，編輯下面的 TEXT 區塊後重新執行即可。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
OUT = ASSETS / "og-cover.png"

W, H = 1200, 630
BAR = 12

BG = (251, 248, 244)
INK = (23, 24, 26)
MUTED = (106, 110, 118)
FAINT = (154, 154, 148)
ACCENT = (229, 72, 77)
ACCENT_SOFT = (253, 236, 236)

EYEBROW = "Fly & Feast HK　飛嚐香港"
LINE1 = "香港最抵嘅"
LINE2 = "機票同餐廳優惠"
SUBLINE = "每日核價更新 · 附期限、條款同來源"
URL = "www.flyandfeasthk.com"
FOOTNOTE = "價格以商戶官方公佈為準"

FONT_DIR = Path("C:/Windows/Fonts")


def load_font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for name in names:
        path = FONT_DIR / name
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def main() -> int:
    bold = lambda s: load_font(["msjhbd.ttc", "msjh.ttc", "arialbd.ttf"], s)
    regular = lambda s: load_font(["msjh.ttc", "arial.ttf"], s)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # 品牌色頂條
    draw.rectangle([0, 0, W, BAR], fill=ACCENT)

    # 右側柔色圓底（襯托 logo）
    draw.ellipse([690, 80, 1190, 580], fill=ACCENT_SOFT)

    logo = Image.open(ASSETS / "logo.png").convert("RGBA")
    target_w = 400
    target_h = round(logo.height * target_w / logo.width)
    logo = logo.resize((target_w, target_h), Image.LANCZOS)
    img.paste(logo, (1190 - target_w, 80 + (500 - target_h) // 2), logo)

    # 左側文案
    draw.text((80, 70), EYEBROW, font=regular(27), fill=MUTED)
    draw.text((78, 168), LINE1, font=bold(70), fill=INK)
    draw.text((78, 262), LINE2, font=bold(70), fill=INK)
    draw.text((80, 384), SUBLINE, font=regular(30), fill=MUTED)

    # 網址徽章
    url_font = bold(30)
    pad_x, badge_h = 30, 66
    badge_w = round(draw.textlength(URL, font=url_font)) + pad_x * 2
    draw.rounded_rectangle([78, 452, 78 + badge_w, 452 + badge_h], radius=33, fill=ACCENT)
    draw.text((78 + pad_x, 452 + badge_h // 2), URL, font=url_font, fill=(255, 255, 255), anchor="lm")

    draw.text((80, 574), FOOTNOTE, font=regular(22), fill=FAINT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"已產生 {OUT}（{img.width}×{img.height}，{OUT.stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
