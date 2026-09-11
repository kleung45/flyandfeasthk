#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把主資料庫 + 每日草稿合併，輸出網站用的資料檔。

流程：pipeline/store.json（人工／智能體審核過的正式資料）
      + pipeline/drafts/*.json（每日由智能體產出的新草稿）
      → data/deals.json + data/deals.js

用法：
    python build_site.py
    python build_site.py --keep-expired     # 保留已結束的優惠（預設保留，標記為已結束）
    python build_site.py --drop-expired     # 直接剔除已結束的優惠
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
STORE = ROOT / "store.json"
DRAFTS = ROOT / "drafts"
DATA = PROJECT / "data"

HK_TZ = timezone(timedelta(hours=8))
END_SOON_DAYS = 3
REQUIRED = ("id", "category", "title", "priceLabel", "endsAt")

INDEX = PROJECT / "index.html"
SITEMAP = PROJECT / "sitemap.xml"

CARDS_START = "<!-- SEO:CARDS:START -->"
CARDS_END = "<!-- SEO:CARDS:END -->"
ITEMLIST_START = "<!-- SEO:ITEMLIST:START -->"
ITEMLIST_END = "<!-- SEO:ITEMLIST:END -->"

GRID_RE = re.compile(r'<div class="grid" id="grid"[^>]*></div>')

CAT_LABEL = {"flight": "機票", "dining": "餐飲", "hotel": "酒店"}
CAT_EMOJI = {"flight": "✈️", "dining": "🍜", "hotel": "🏨"}
CAT_STICKER = {"flight": "st-flight", "dining": "st-dining", "hotel": "st-hotel"}


# --------------------------------------------------------------------------
# 靜態預渲染：把優惠卡片寫進 index.html 的 #grid，
# 令 HTML 原始碼本身就含優惠文字（不依賴 JavaScript 才看得到內容）。
# 前端 assets/app.js 載入後會用相同模板重新渲染一次，視覺結果完全一致。
# 若 app.js 的 card() 有改動，這裡要同步更新。
# --------------------------------------------------------------------------

def esc(value) -> str:
    s = "" if value is None else str(value)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def countdown(deal: dict) -> str:
    if deal.get("status") == "expired":
        return "已結束"
    d = deal.get("daysLeft")
    if d == 0:
        return "今日結束"
    if d == 1:
        return "明日結束"
    if isinstance(d, int):
        return f"剩 {d} 日"
    return ""


def category_badge(cat: str) -> str:
    cls = {"flight": "badge-flight", "dining": "badge-dining"}.get(cat, "badge-hotel")
    return f'<span class="badge {cls}">{esc(CAT_LABEL.get(cat, "優惠"))}</span>'


def status_badge(deal: dict) -> str:
    if deal.get("status") == "expired":
        return '<span class="badge badge-expired">已結束</span>'
    if deal.get("status") == "ending":
        return f'<span class="badge badge-urgent">{esc(countdown(deal))}</span>'
    return ""


def card_sticker(cat: str) -> str:
    emoji = CAT_EMOJI.get(cat, "🎁")
    cls = CAT_STICKER.get(cat, "st-hotel")
    return f'<span class="card-sticker {cls}" aria-hidden="true">{emoji}</span>'


def render_card(deal: dict) -> str:
    cls = "card" + (" is-expired" if deal.get("status") == "expired" else "")
    route = deal.get("route") or deal.get("venue") or ""

    badges = category_badge(deal.get("category", "")) + status_badge(deal)
    if deal.get("sample"):
        badges += '<span class="badge badge-sample">示範</span>'

    save = f'<span class="save">省 {esc(deal["discountPct"])}%</span>' if deal.get("discountPct") else ""

    highlights = ""
    if deal.get("highlights"):
        items = "".join(f"<li>{esc(h)}</li>" for h in deal["highlights"])
        highlights = f"<ul>{items}</ul>"

    source = ""
    if deal.get("sourceLabel"):
        label = esc(deal["sourceLabel"])
        if deal.get("sourceUrl"):
            label = f'<a href="{esc(deal["sourceUrl"])}" target="_blank" rel="noopener nofollow">{label}</a>'
        source = f'<p class="source">來源：{label}</p>'

    share = ""
    if deal.get("status") != "expired":
        share = f'<button class="icon-btn" type="button" data-share="{esc(deal["id"])}">分享</button>'

    if deal.get("status") == "expired":
        cta = '<span class="period">優惠已結束</span>'
    else:
        cta = (
            f'<a class="link-btn" href="{esc(deal.get("url") or "#")}"'
            ' target="_blank" rel="noopener nofollow">查看優惠 →</a>'
        )

    return (
        f'<article class="{cls}" data-id="{esc(deal["id"])}">'
        f'<div class="card-top">{badges}{card_sticker(deal.get("category", ""))}</div>'
        f'<h3>{esc(deal.get("title"))}</h3>'
        + (f'<p class="sub">{esc(deal["subtitle"])}</p>' if deal.get("subtitle") else "")
        + (f'<p class="route">{esc(route)}</p>' if route else "")
        + '<div class="price-row">'
        f'<span class="price">{esc(deal.get("priceLabel") or "")}</span>'
        + (f'<span class="price-was">{esc(deal["originalLabel"])}</span>' if deal.get("originalLabel") else "")
        + save
        + "</div>"
        + (f'<p class="summary">{esc(deal["summary"])}</p>' if deal.get("summary") else "")
        + highlights
        + '<div class="card-foot">'
        f'<span class="period">{esc(deal.get("period") or countdown(deal))}</span>'
        f'<span class="actions">{share}{cta}</span>'
        "</div>"
        + source
        + "</article>"
    )


def replace_region(html: str, start: str, end: str, body: str) -> str:
    i, j = html.find(start), html.find(end)
    if i == -1 or j == -1 or j < i:
        return html
    return html[: i + len(start)] + "\n" + body + "\n      " + html[j:]


def bootstrap_index(html: str) -> str:
    """首次執行時插入標記與 FAQ 區塊，之後每次建置只替換標記之間的內容。"""
    if CARDS_START not in html:
        m = GRID_RE.search(html)
        if m:
            indent = "\n      "
            html = (
                html[: m.start()]
                + '<div class="grid" id="grid">'
                + indent + CARDS_START
                + indent + CARDS_END
                + "\n    </div>"
                + html[m.end():]
            )

    if ITEMLIST_START not in html:
        anchor = "</head>"
        block = (
            "<!-- SEO:ITEMLIST:START -->\n"
            "<!-- SEO:ITEMLIST:END -->\n"
        )
        html = html.replace(anchor, block + anchor, 1)

    return html


def inject_index(deals: list[dict], meta: dict) -> None:
    if not INDEX.exists():
        print(f"提醒：找不到 {INDEX.name}，略過靜態預渲染")
        return

    html = bootstrap_index(INDEX.read_text(encoding="utf-8"))

    live = [d for d in deals if d.get("status") != "expired"]
    cards = "\n".join(render_card(d) for d in live)
    html = replace_region(html, CARDS_START, CARDS_END, cards)

    itemlist = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "香港出發機票特價與餐廳優惠（進行中）",
        "description": meta.get("disclaimer", ""),
        "numberOfItems": len(live),
        "itemListOrder": "https://schema.org/ItemListOrderDescending",
        "itemListElement": [],
    }
    for i, d in enumerate(live, 1):
        entry: dict = {"@type": "ListItem", "position": i, "name": d.get("title")}
        url = d.get("url")
        price = d.get("priceValue")
        if url and isinstance(price, (int, float)):
            offer = {
                "@type": "Offer",
                "name": d.get("title"),
                "url": url,
                "price": price,
                "priceCurrency": "HKD",
                "category": CAT_LABEL.get(d.get("category"), "優惠"),
            }
            if d.get("endsAt"):
                offer["availabilityEnds"] = d["endsAt"]
            if d.get("sourceLabel"):
                offer["seller"] = {"@type": "Organization", "name": d["sourceLabel"]}
            entry["item"] = offer
        elif url:
            entry["url"] = url
        itemlist["itemListElement"].append(entry)

    ld = (
        '<script type="application/ld+json">\n'
        + json.dumps(itemlist, ensure_ascii=False, indent=2)
        + "\n</script>"
    )
    html = replace_region(html, ITEMLIST_START, ITEMLIST_END, ld)
    INDEX.write_text(html, encoding="utf-8")
    print(f"  靜態預渲染 {len(live)} 筆優惠卡片 + ItemList 結構化資料已寫入 index.html")


def write_sitemap(meta: dict) -> None:
    site = (meta.get("siteUrl") or "").rstrip("/")
    if not site:
        return
    today = datetime.now(HK_TZ).date().isoformat()
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        f"    <loc>{site}/</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        "    <changefreq>daily</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>\n"
        "</urlset>\n"
    )
    SITEMAP.write_text(xml, encoding="utf-8")
    print(f"  sitemap.xml 已更新（lastmod {today}）")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=HK_TZ)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect() -> tuple[dict, list[dict], list[str]]:
    if not STORE.exists():
        raise SystemExit(f"找不到主資料庫：{STORE}")

    base = load_json(STORE)
    deals: list[dict] = list(base.get("deals", []))
    seen = {d.get("id") for d in deals}
    warnings: list[str] = []
    added = 0

    for path in sorted(DRAFTS.glob("*.json")):
        try:
            payload = load_json(path)
        except json.JSONDecodeError as exc:
            warnings.append(f"{path.name}：JSON 格式錯誤（{exc}）")
            continue

        incoming = payload.get("deals") if isinstance(payload, dict) else payload
        if not isinstance(incoming, list):
            warnings.append(f"{path.name}：找不到 deals 陣列")
            continue

        for deal in incoming:
            missing = [k for k in REQUIRED if not deal.get(k)]
            if missing:
                warnings.append(f"{path.name} 的 {deal.get('id', '(無 id)')} 缺少欄位：{', '.join(missing)}")
                continue
            if deal["id"] in seen:
                continue
            if not deal.get("sample"):
                deal["sample"] = False
            deals.append(deal)
            seen.add(deal["id"])
            added += 1

    print(f"主資料庫 {len(base.get('deals', []))} 筆，草稿新增 {added} 筆")
    return base, deals, warnings


def decorate(deals: list[dict]) -> list[dict]:
    now = datetime.now(HK_TZ)
    out = []

    for deal in deals:
        deal = dict(deal)
        end = parse_dt(deal.get("endsAt"))
        if end is None:
            deal["status"] = "unknown"
            deal["daysLeft"] = None
        else:
            # 以「日」為單位計算剩餘天數，避免時分秒造成邊界誤判
            days_left = (end.date() - now.date()).days
            deal["daysLeft"] = max(0, days_left)
            if end < now:
                deal["status"] = "expired"
                deal["daysLeft"] = 0
            elif days_left <= END_SOON_DAYS:
                deal["status"] = "ending"
            else:
                deal["status"] = "active"
        out.append(deal)

    order = {"ending": 0, "active": 1, "unknown": 2, "expired": 3}
    out.sort(key=lambda d: (order.get(d["status"], 9), d.get("endsAt") or "9999"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="建置網站資料檔")
    ap.add_argument("--drop-expired", action="store_true", help="剔除已結束的優惠")
    args = ap.parse_args()

    base, deals, warnings = collect()
    deals = decorate(deals)

    if args.drop_expired:
        before = len(deals)
        deals = [d for d in deals if d["status"] != "expired"]
        print(f"剔除已結束優惠 {before - len(deals)} 筆")

    stats = {
        "total": len(deals),
        "active": sum(1 for d in deals if d["status"] in ("active", "ending")),
        "ending": sum(1 for d in deals if d["status"] == "ending"),
        "expired": sum(1 for d in deals if d["status"] == "expired"),
        "flight": sum(1 for d in deals if d["category"] == "flight"),
        "dining": sum(1 for d in deals if d["category"] == "dining"),
        "hotel": sum(1 for d in deals if d["category"] == "hotel"),
    }

    meta = dict(base.get("meta", {}))
    meta["updated"] = datetime.now(HK_TZ).isoformat(timespec="seconds")
    meta["stats"] = stats
    meta["sample"] = any(d.get("sample") for d in deals)

    payload = {"meta": meta, "deals": deals}

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "deals.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATA / "deals.js").write_text(
        "// 由 build_site.py 自動產生，請勿手動編輯。\n"
        "window.DEAL_DATA = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )

    print(
        f"完成：{DATA / 'deals.json'} / {DATA / 'deals.js'}\n"
        f"  進行中 {stats['active']} 筆（當中 {stats['ending']} 筆 3 日內結束）、"
        f"已結束 {stats['expired']} 筆\n"
        f"  機票 {stats['flight']} / 餐飲 {stats['dining']} / 酒店 {stats['hotel']}"
    )

    # SEO 產物：靜態預渲染 + sitemap（每次建置自動更新）
    inject_index(deals, meta)
    write_sitemap(meta)

    if warnings:
        print("\n提醒：")
        for w in warnings:
            print(f"  - {w}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
