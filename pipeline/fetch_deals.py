#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取情報源 RSS，輸出原始標題清單供智能體篩選。

用法：
    python fetch_deals.py                # 抓取所有 enabled 的 rss 來源
    python fetch_deals.py --source hkexpress_promo
    python fetch_deals.py --days 3       # 只保留最近 3 天的條目

輸出：pipeline/raw/YYYY-MM-DD.json
設計原則：只用標準庫，零依賴，任何環境都能跑得動。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES_FILE = ROOT / "sources.json"
RAW_DIR = ROOT / "raw"

UA = (
    "Mozilla/5.0 (compatible; FlyAndFeastHK/1.0; +https://flyandfeasthk.com/about) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
TIMEOUT = 20

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def strip_html(text: str | None, limit: int = 300) -> str:
    """去掉標籤與多餘空白，截斷成摘要。"""
    if not text:
        return ""
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    patterns = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in patterns:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return None


def parse_feed(payload: bytes, source: dict) -> list[dict]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        print(f"  ! XML 解析失敗：{exc}", file=sys.stderr)
        return []

    items: list[dict] = []

    # RSS 2.0
    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        raw_date = node.findtext("pubDate") or node.findtext("{http://purl.org/dc/elements/1.1/}date")
        desc = node.findtext("description") or node.findtext(
            "{http://purl.org/rss/1.0/modules/content/}encoded"
        )
        if title:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "published": parse_date(raw_date),
                    "summary": strip_html(desc),
                    "sourceId": source["id"],
                    "sourceName": source["name"],
                    "category": source.get("category", "flight"),
                    "weight": source.get("weight", 5),
                }
            )

    # Atom
    for node in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = (node.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        link_el = node.find("{http://www.w3.org/2005/Atom}link")
        link = link_el.get("href") if link_el is not None else ""
        raw_date = node.findtext("{http://www.w3.org/2005/Atom}updated") or node.findtext(
            "{http://www.w3.org/2005/Atom}published"
        )
        desc = node.findtext("{http://www.w3.org/2005/Atom}summary") or node.findtext(
            "{http://www.w3.org/2005/Atom}content"
        )
        if title:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "published": parse_date(raw_date),
                    "summary": strip_html(desc),
                    "sourceId": source["id"],
                    "sourceName": source["name"],
                    "category": source.get("category", "flight"),
                    "weight": source.get("weight", 5),
                }
            )

    return items


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取特價情報源 RSS")
    ap.add_argument("--source", help="只抓指定 source id")
    ap.add_argument("--days", type=int, default=14, help="只保留最近 N 天的條目（預設 14）")
    args = ap.parse_args()

    if not SOURCES_FILE.exists():
        print(f"找不到 {SOURCES_FILE}", file=sys.stderr)
        return 1

    config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    targets = [
        s
        for s in config["sources"]
        if s.get("mode") == "rss" and s.get("enabled", True) and (not args.source or s["id"] == args.source)
    ]

    if not targets:
        print("沒有符合條件的 rss 來源。", file=sys.stderr)
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    all_items: list[dict] = []
    report: list[dict] = []

    for src in targets:
        print(f"→ {src['name']}  {src['url']}")
        try:
            payload = fetch(src["url"])
            items = parse_feed(payload, src)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            print(f"  ! 抓取失敗：{exc}", file=sys.stderr)
            report.append({"id": src["id"], "ok": False, "error": str(exc), "count": 0})
            continue

        kept = []
        for item in items:
            pub = item.get("published")
            if pub:
                try:
                    if datetime.fromisoformat(pub) < cutoff:
                        continue
                except ValueError:
                    pass
            kept.append(item)

        print(f"  ✓ {len(items)} 條，保留 {len(kept)} 條")
        report.append({"id": src["id"], "ok": True, "count": len(kept), "error": None})
        all_items.extend(kept)

    all_items.sort(key=lambda i: i.get("published") or "", reverse=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    out = RAW_DIR / f"{today}.json"
    out.write_text(
        json.dumps(
            {
                "fetchedAt": datetime.now().astimezone().isoformat(),
                "sourceReport": report,
                "count": len(all_items),
                "items": all_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n完成：{out}（共 {len(all_items)} 條）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
