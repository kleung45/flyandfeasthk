#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由優惠資料產生社交媒體文案（Facebook / Instagram / 小紅書）。

用法：
    python generate_content.py                    # 全部進行中的優惠
    python generate_content.py --limit 3          # 只出前 3 筆
    python generate_content.py --category flight  # 只出機票

輸出：outbox/YYYY-MM-DD/
    facebook.md      可直接複製貼上的專頁貼文
    instagram.md     IG 圖文（含 hashtag）
    xiaohongshu.md   小紅書筆記草稿
    manifest.json    發文用的結構化資料，供 publish_social.py 讀取
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
DATA_FILE = PROJECT / "data" / "deals.json"
OUTBOX = PROJECT / "outbox"
HK_TZ = timezone(timedelta(hours=8))

BASE_TAGS = ["#香港優惠", "#FlyAndFeastHK"]
CATEGORY_TAGS = {
    "flight": ["#香港機票", "#機票優惠", "#廉航", "#旅行"],
    "dining": ["#香港美食", "#自助餐", "#餐廳優惠", "#美食優惠"],
    "hotel": ["#香港酒店", "#酒店優惠"],
}


def money(deal: dict) -> str:
    return deal.get("priceLabel") or ""


def countdown(deal: dict) -> str:
    status = deal.get("status")
    days = deal.get("daysLeft")
    if status == "expired":
        return "已結束"
    if days == 0:
        return "今日結束"
    if days == 1:
        return "明日結束"
    if isinstance(days, int):
        return f"剩 {days} 日"
    return ""


CAT_STYLE = {
    "flight": {"emoji": "✈️", "label": "機票"},
    "hotel": {"emoji": "🏨", "label": "酒店"},
    "dining": {"emoji": "🍽️", "label": "餐飲"},
}


def _teaser(summary: str, limit: int = 90) -> str:
    """由長摘要抽一句短介紹，製造好奇感。"""
    if not summary:
        return ""
    cut = summary.split("。")[0]
    if len(cut) > limit:
        cut = cut[: limit - 1] + "…"
    return cut


def fb_post(deal: dict, site_url: str) -> str:
    """引流式 FB 貼文（短版）：唔寫得太詳盡，引留言→自動回覆送網站連結。"""
    style = CAT_STYLE.get(deal["category"], {"emoji": "🔥", "label": "優惠"})
    lines = [f"{style['emoji']} {deal['title']}"]

    if deal.get("route") or deal.get("venue"):
        lines.append(f"📍 {deal.get('route') or deal.get('venue')}")
    if deal.get("priceLabel"):
        lines.append(f"💰 {deal['priceLabel']}")

    teaser = _teaser(deal.get("summary", ""))
    if teaser:
        lines += ["", teaser]

    cd = countdown(deal)
    if cd:
        lines += ["", f"⏰ {cd}，手快有手慢冇！"]

    lines += [
        "",
        "💬 想知申請入口＋優惠碼，留言「優惠」，我哋會自動 send 連結俾你！",
        "",
        " ".join(dict.fromkeys(BASE_TAGS + CATEGORY_TAGS.get(deal["category"], [])[:2])),
    ]
    return "\n".join(lines)


def ig_caption(deal: dict, site_url: str) -> str:
    lines = [deal["title"]]
    if deal.get("subtitle"):
        lines.append(deal["subtitle"])
    lines.append("")
    lines.append(money(deal) + (f"｜{countdown(deal)}" if countdown(deal) else ""))
    if deal.get("period"):
        lines.append(deal["period"])
    lines.append("")
    if deal.get("summary"):
        lines.append(deal["summary"][:120])
        lines.append("")
    lines.append("詳情見主頁連結 Link in bio")
    lines.append("")
    tags = BASE_TAGS + CATEGORY_TAGS.get(deal["category"], []) + [f"#{t}".replace(" ", "") for t in deal.get("tags", [])]
    lines.append(" ".join(dict.fromkeys(tags)))
    return "\n".join(lines)


def xhs_note(deal: dict, site_url: str) -> str:
    lines = [f"{deal['title']}｜香港人必搶優惠", ""]
    if deal.get("summary"):
        lines += [deal["summary"], ""]
    lines.append(f"價格：{money(deal)}")
    if deal.get("period"):
        lines.append(f"期限：{deal['period']}")
    if countdown(deal):
        lines.append(f"倒數：{countdown(deal)}")
    if deal.get("highlights"):
        lines.append("")
        lines.append("小提醒：")
        lines += [f"- {h}" for h in deal["highlights"]]
    lines += ["", "訂之前記得比較官網同平台價，優惠名額有限。", "", "#香港機票 #香港美食 #優惠情報 #省錢攻略"]
    return "\n".join(lines)


def digest_post(deals: list[dict], site_url: str) -> str:
    lines = ["🔥【今日香港抵嘢速報】", ""]
    for d in deals[:6]:
        emoji = CAT_STYLE.get(d["category"], {"emoji": "🔥"})["emoji"]
        name = (d.get("venue") or "").split(" · ")[0] or d.get("route") or d["title"]
        lines.append(f"{emoji} {name}｜{money(d)}")

    lines += [
        "",
        "全部優惠仲有幾多日、點樣申請？",
        "留言「優惠」，我哋即刻 send 晒連結俾你 📩",
        "",
        " ".join(BASE_TAGS),
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="產生社交媒體文案")
    ap.add_argument("--limit", type=int, default=0, help="最多輸出幾筆單篇貼文（0 = 不限）")
    ap.add_argument("--category", choices=["flight", "dining", "hotel"], help="只處理指定類別")
    args = ap.parse_args()

    if not DATA_FILE.exists():
        raise SystemExit(f"找不到 {DATA_FILE}，請先執行 build_site.py")

    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    meta = payload.get("meta", {})
    site_url = meta.get("siteUrl", "")
    deals = [d for d in payload["deals"] if d.get("status") != "expired"]

    if args.category:
        deals = [d for d in deals if d["category"] == args.category]
    if args.limit:
        deals = deals[: args.limit]

    if not deals:
        raise SystemExit("沒有可發佈的優惠（可能全部已結束）。")

    today = datetime.now(HK_TZ).strftime("%Y-%m-%d")
    out_dir = OUTBOX / today
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"date": today, "generatedAt": datetime.now(HK_TZ).isoformat(timespec="seconds"), "posts": []}

    fb, ig, xhs = [], [], []
    for deal in deals:
        fb.append(f"## {deal['id']}\n\n{fb_post(deal, site_url)}\n")
        ig.append(f"## {deal['id']}\n\n{ig_caption(deal, site_url)}\n")
        xhs.append(f"## {deal['id']}\n\n{xhs_note(deal, site_url)}\n")
        manifest["posts"] += [
            {
                "dealId": deal["id"],
                "platform": "facebook",
                "category": deal["category"],
                "message": fb_post(deal, site_url),
                "link": site_url,  # 引流到自家網站（廣告收益），唔直接跳商戶
                "imageUrl": deal.get("image") or "",
            },
            {
                "dealId": deal["id"],
                "platform": "instagram",
                "category": deal["category"],
                "caption": ig_caption(deal, site_url),
                "link": site_url,
                "imageUrl": deal.get("image") or "",
            },
        ]

    digest = digest_post(deals, site_url)
    fb.insert(0, f"## digest\n\n{digest}\n")
    manifest["posts"].insert(
        0,
        {
            "dealId": "digest",
            "platform": "facebook",
            "category": "digest",
            "message": digest,
            "link": site_url,
            "imageUrl": "",
        },
    )

    (out_dir / "facebook.md").write_text("\n---\n\n".join(fb), encoding="utf-8")
    (out_dir / "instagram.md").write_text("\n---\n\n".join(ig), encoding="utf-8")
    (out_dir / "xiaohongshu.md").write_text("\n---\n\n".join(xhs), encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"完成：{out_dir}")
    print(f"  貼文 {len(deals)} 筆 + 1 則速報，社群文案 3 份，manifest.json 已產生")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
