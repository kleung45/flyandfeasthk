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

    if warnings:
        print("\n提醒：")
        for w in warnings:
            print(f"  - {w}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
