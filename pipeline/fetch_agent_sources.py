#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mode=agent 情報源抓取器：把「人手要看的頁」變成「已排序的待審候選」。

為甚麼有這支腳本：
    sources.json 裡 mode=agent 的來源沒有 RSS，之前只是一份清單，沒有人真的去讀。
    結果每日優惠線只能靠臨時搜尋，來源不穩定。這支腳本做三件事——
      1. 逐個抓頁面，去掉標籤成純文字行（自動試 utf-8 / big5 / gb18030）；
      2. 用價格樣式與優惠關鍵詞撈出疑似優惠行，按訊號強弱評分排序；
      3. 寫入 pipeline/raw/agent-YYYY-MM-DD.json 待審佇列。

它刻意「不會」寫入 store.json 或 drafts：
    價格、期限、條款必須由智能體或人手逐筆核實後才可收錄（見 about 頁的核實五步）。
    這支腳本只負責把候選送到眼前，不代替判斷。

用法：
    python fetch_agent_sources.py                  # 抓全部 enabled 的 agent 來源
    python fetch_agent_sources.py --source openrice_promo
    python fetch_agent_sources.py --max-per-source 20
    python fetch_agent_sources.py --check          # 只做全來源健康檢查（含 rss / api）
    python fetch_agent_sources.py --min-score 3

輸出：
    pipeline/raw/agent-YYYY-MM-DD.json    當日候選
    pipeline/raw/source-health.json       --check 的來源狀態

設計原則：只用標準庫，零依賴。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES_FILE = ROOT / "sources.json"
RAW_DIR = ROOT / "raw"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}
TIMEOUT = 25

# 價格樣式：HK$1,288 / $288 / 288元 / ¥8,800 / 1,288 HKD
PRICE_RE = re.compile(
    r"(?:HK\$|HKD|NT\$|US\$|¥|＄|\$)\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?"
    r"|\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s?(?:元|円|港元|港幣|HKD)",
    re.I,
)

# 優惠訊號：出現越多，越似一筆真優惠
STRONG_SIGNALS = [
    ("買一送一", 4), ("買1送1", 4), ("第二份半價", 3), ("半價", 3),
    ("全單", 2), ("折上折", 3), ("快閃", 3), ("閃促", 3), ("限量", 2),
    ("低至", 2), ("起", 1), ("免費", 3), ("送", 1),
    ("promotion", 2), ("deal", 1), ("sale", 2), ("offer", 1),
    ("discount", 2), ("bogo", 4),
]
WEAK_SIGNALS = [("優惠", 1), ("折", 1), ("減", 1), ("回贈", 2), ("折扣", 2), ("促銷", 2), ("特價", 2)]

# 日期樣式：2026-11-30 / 11月30日 / 30/11/2026 / 11.30
DATE_RE = re.compile(
    r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}"
    r"|\d{1,2}\s?月\s?\d{1,2}\s?日"
    r"|\d{1,2}/\d{1,2}/20\d{2}"
    r"|\d{4}年\d{1,2}月"
    r"|即日起|直至|至\s?\d{1,2}\s?月",
)

# 導航／頁尾／法務文字，一律丟棄
NOISE_RE = re.compile(
    r"版權|copyright|©|私隱|隱私|條款及細則|使用者條款|登入|註冊|訂閱|下載app"
    r"|cookie|接受所有|網站地圖|無障礙|招聘|聯絡我們|回首頁|返回頂部"
    r"|follow us|facebook|instagram|youtube|wechat|whatsapp us",
    re.I,
)

# 頁面內嵌 JSON／未清乾淨的標籤殘留，例：'</h5>\r\n","xdm:linkURL":"https://...'
RESIDUE_RE = re.compile(r'</|\{"|"\s*:\s*"|\\r\\n|\\n|xdm:|\\u[0-9a-f]{4}', re.I)

# 與本站兩大支柱無關的內容（頁面內嵌的網購／生活百貨廣告）
OFFTOPIC_RE = re.compile(r"生活用品|家電券|網購|外賣平台|超市優惠|寵物|母嬰", re.I)

# 分類關鍵詞：候選行至少要沾到一個，否則不算這條線的優惠
CATEGORY_KEYWORDS = {
    "flight": ("航", "機票", "航班", "飛", "里數", "行李", "登機", "航線", "機場", "座位", "艙",
               "miles", "flight", "airline"),
    "dining": ("餐", "食", "菜", "飲", "茶", "宴", "廳", "餅", "自助", "酒", "酒店",
               "buffet", "dining", "restaurant"),
    "hotel": ("酒店", "房", "住宿", "入住", "套房", "度假", "hotel", "stay"),
}


def fetch_bytes(url: str) -> tuple[bytes, int]:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read(), resp.status


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "big5", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def to_lines(markup: str) -> list[str]:
    """HTML → 純文字行。先切掉 script/style/noscript/svg，再逐標籤斷行。"""
    text = re.sub(r"<(script|style|noscript|svg|template)\b.*?</\1>", " ", markup, flags=re.S | re.I)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr|/td|/span)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = re.sub(r"[\s\u00a0]+", " ", raw_line).strip()
        if not (6 <= len(line) <= 180):
            continue
        if NOISE_RE.search(line) or RESIDUE_RE.search(line) or OFFTOPIC_RE.search(line):
            continue
        lines.append(line)
    return lines


def matches_category(line: str, category: str) -> bool:
    """候選行要沾到該分類的關鍵詞，否則只是頁面上的雜項推廣（例如航空頁的網購廣告）。"""
    words = CATEGORY_KEYWORDS.get(category)
    if not words:
        return True
    low = line.lower()
    return any(w in low for w in words)


def score_line(line: str) -> int:
    score = 0
    if PRICE_RE.search(line):
        score += 2
    low = line.lower()
    for word, weight in STRONG_SIGNALS:
        if word.lower() in low:
            score += weight
    for word, weight in WEAK_SIGNALS:
        if word.lower() in low:
            score += weight
    if DATE_RE.search(line):
        score += 2
    # 太短多數是導航按鈕，太長多數是段落而非優惠標題
    if len(line) < 10:
        score -= 2
    if len(line) > 120:
        score -= 1
    return score


def extract_candidates(lines: list[str], source: dict, min_score: int, limit: int) -> list[dict]:
    category = source.get("category", "flight")
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []
    for line in lines:
        if not matches_category(line, category):
            continue
        key = re.sub(r"\W+", "", line)[:40]
        if not key or key in seen:
            continue
        seen.add(key)
        s = score_line(line)
        if s >= min_score:
            scored.append((s, line))
    scored.sort(key=lambda t: (-t[0], -len(t[1])))
    out = []
    for s, line in scored[:limit]:
        out.append(
            {
                "text": line,
                "score": s,
                "price": (PRICE_RE.search(line).group(0) if PRICE_RE.search(line) else None),
                "dateHint": (DATE_RE.search(line).group(0) if DATE_RE.search(line) else None),
                "sourceId": source["id"],
                "sourceName": source["name"],
                "category": source.get("category", "flight"),
                "weight": source.get("weight", 5),
                "sourceUrl": source["url"],
                # 提醒下游：這只是候選，未核實
                "needsVerification": True,
            }
        )
    return out


def run_fetch(sources: list[dict], min_score: int, per_source: int) -> dict:
    all_candidates: list[dict] = []
    report: list[dict] = []

    for src in sources:
        print(f"→ {src['name']}  {src['url']}")
        entry = {
            "id": src["id"],
            "name": src["name"],
            "category": src.get("category", "flight"),
            "url": src["url"],
            "ok": False,
            "http": None,
            "bytes": 0,
            "lines": 0,
            "candidates": 0,
            "error": None,
        }
        try:
            raw, status = fetch_bytes(src["url"])
        except urllib.error.HTTPError as exc:
            entry.update(http=exc.code, error=f"HTTP {exc.code}")
            print(f"  ! HTTP {exc.code}", file=sys.stderr)
            report.append(entry)
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            entry.update(error=str(exc))
            print(f"  ! 抓取失敗：{exc}", file=sys.stderr)
            report.append(entry)
            continue

        markup = decode(raw)
        lines = to_lines(markup)
        cands = extract_candidates(lines, src, min_score, per_source)

        entry.update(ok=True, http=status, bytes=len(raw), lines=len(lines), candidates=len(cands))
        # 0-1 個候選多數是 JS 渲染頁，腳本抽不到不代表冇優惠，下游仍要開頁看
        entry["yieldHint"] = "low" if len(cands) <= 1 else "normal"
        report.append(entry)
        all_candidates.extend(cands)
        print(f"  ✓ {status}  {len(raw) // 1024}KB  {len(lines)} 行  →  {len(cands)} 個候選")

    return {
        "fetchedAt": datetime.now().astimezone().isoformat(),
        "mode": "agent",
        "count": len(all_candidates),
        "sources": report,
        "candidates": all_candidates,
        "_note": "candidates 只係待審候選，未經核實。收錄前必須確認價格出處、期限、條款（見 about 頁核實五步）。",
    }


def run_check(config: dict) -> dict:
    """全來源健康檢查：rss 看是否真的是 XML，agent 看 HTTP 與可抽取行數。"""
    results = []
    for src in config["sources"]:
        if not src.get("enabled", True):
            results.append(
                {
                    "id": src["id"],
                    "name": src["name"],
                    "mode": src.get("mode"),
                    "url": src["url"],
                    "status": "disabled",
                    "http": None,
                    "detail": src.get("note", "")[:80],
                }
            )
            continue
        print(f"· {src['id']}")
        item = {
            "id": src["id"],
            "name": src["name"],
            "mode": src.get("mode"),
            "url": src["url"],
            "http": None,
            "bytes": 0,
            "status": "unknown",
            "detail": "",
        }
        try:
            raw, status = fetch_bytes(src["url"])
            item.update(http=status, bytes=len(raw))
            head = raw[:400].lstrip().lower()
            is_xml = head.startswith(b"<?xml") or b"<rss" in head or b"<feed" in head
            if src.get("mode") == "rss":
                if is_xml:
                    item.update(status="ok", detail="XML feed")
                else:
                    item.update(status="blocked", detail="回傳不是 RSS（可能 Cloudflare 攔截）")
            else:
                lines = to_lines(decode(raw))
                item.update(status="ok" if len(lines) > 20 else "thin", detail=f"{len(lines)} 行可讀文字")
        except urllib.error.HTTPError as exc:
            item.update(http=exc.code, status="dead", detail=f"HTTP {exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            item.update(status="dead", detail=str(exc)[:120])
        results.append(item)

    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    return {
        "checkedAt": datetime.now().astimezone().isoformat(),
        "summary": summary,
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取 mode=agent 情報源，產生待審候選")
    ap.add_argument("--source", help="只抓指定 source id")
    ap.add_argument("--max-per-source", type=int, default=15, help="每個來源最多保留幾個候選（預設 15）")
    ap.add_argument("--min-score", type=int, default=3, help="候選最低分（預設 3；調高＝更嚴格）")
    ap.add_argument("--check", action="store_true", help="只做全來源健康檢查")
    args = ap.parse_args()

    if not SOURCES_FILE.exists():
        print(f"找不到 {SOURCES_FILE}", file=sys.stderr)
        return 1

    config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if args.check:
        result = run_check(config)
        out = RAW_DIR / "source-health.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n來源狀態：")
        for r in result["results"]:
            print(f"  {r['status']:9s} {str(r.get('http') or '-'):>4s}  {r['id']:24s} {r['detail']}")
        print(f"\n完成：{out}  統計 {result['summary']}")
        return 0

    targets = [
        s
        for s in config["sources"]
        if s.get("mode") == "agent"
        and s.get("enabled", True)
        and (not args.source or s["id"] == args.source)
    ]
    if not targets:
        print("沒有符合條件的 agent 來源。", file=sys.stderr)
        return 0

    result = run_fetch(targets, args.min_score, args.max_per_source)
    today = datetime.now().strftime("%Y-%m-%d")
    out = RAW_DIR / f"agent-{today}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for s in result["sources"] if s["ok"])
    print(f"\n完成：{out}")
    print(f"來源 {ok}/{len(result['sources'])} 成功，共 {result['count']} 個待審候選（未核實）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
