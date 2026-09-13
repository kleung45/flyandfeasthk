#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 outbox 內已生成的文案發佈到 Facebook 專頁 / Instagram。

安全設計：預設為 dry-run，只會列印即將發佈的內容，不會真的發帖。
確認無誤後才加 --live。

用法：
    python publish_social.py --manifest ../outbox/2026-09-10/manifest.json
    python publish_social.py --manifest ... --platform facebook --limit 1
    python publish_social.py --manifest ... --live        # 真正發佈

前置設定：複製 config.example.json 為 config.json，填入 Page ID 與 Access Token。
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
GRAPH = "https://graph.facebook.com/v21.0"
THREADS_GRAPH = "https://graph.threads.net/v1.0"
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_STORE = ROOT / "store.json"
OUTBOX = PROJECT / "outbox"
MARKER_NAME = ".facebook_published.json"  # FB 當日發佈紀錄
THREADS_MARKER_NAME = ".threads_published.json"  # Threads 當日發佈紀錄
RETRY = 2
SOCIAL_PLATFORMS = ("facebook", "threads", "instagram")


def marker_name_for(platform: str) -> str:
    return MARKER_NAME if platform == "facebook" else THREADS_MARKER_NAME


def store_flag_for(platform: str) -> str:
    """store.json 內「已發佈」標記欄位名：FB 與 Threads 分開記賬。"""
    return "postedFacebook" if platform == "facebook" else "postedThreads"


def already_posted_deal_ids(store_path: Path, current_date: str, platform: str = "facebook") -> dict[str, str]:
    """收集不應再次發佈的優惠 id（按平台分開判斷）。

    來源一：store.json 內對應平台標記（postedFacebook / postedThreads）為 true。
    來源二：之前日期 outbox/<date>/manifest.json 已收錄的同一平台貼文 id。
    來源三：當日已寫入的發佈紀錄 marker（防範同一天重複執行造成重複貼文）。
    回傳 {dealId: 原因}，方便列印略過原因。
    """
    flag_key = store_flag_for(platform)
    marker_file = marker_name_for(platform)
    seen: dict[str, str] = {}

    if store_path.exists():
        try:
            store = load_json(store_path)
        except json.JSONDecodeError:
            store = {}
        for deal in store.get("deals", []):
            if deal.get(flag_key) and deal.get("id"):
                seen[deal["id"]] = f"store.json 已標記 {flag_key}"

    if current_date:
        marker = OUTBOX / current_date / marker_file
        if marker.exists():
            try:
                marked = load_json(marker)
            except json.JSONDecodeError:
                marked = {}
            for deal_id in marked.get("dealIds", []):
                if deal_id:  # 包含 digest：速報同一平台每日只發一次
                    seen.setdefault(deal_id, f"當日已發佈（{marker_file}）")

    if OUTBOX.exists():
        for manifest in sorted(OUTBOX.glob("*/manifest.json")):
            if manifest.parent.name >= current_date:
                continue  # 只計之前日期，當日 manifest 屬本次發佈
            try:
                payload = load_json(manifest)
            except json.JSONDecodeError:
                continue
            for post in payload.get("posts", []):
                if post.get("platform") != platform:
                    continue
                deal_id = post.get("dealId")
                if deal_id and deal_id != "digest" and deal_id not in seen:
                    seen[deal_id] = f"已於 {manifest.parent.name} outbox 發佈"

    return seen


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_publish_marker(manifest_path: Path, deal_ids: list[str], platform: str = "facebook") -> None:
    """記錄當日已成功發佈的優惠（按平台分檔），避免同日再次執行時重複貼文。"""
    marker = manifest_path.parent / marker_name_for(platform)
    existing: list[str] = []
    if marker.exists():
        try:
            existing = load_json(marker).get("dealIds", [])
        except json.JSONDecodeError:
            existing = []
    merged = list(dict.fromkeys(existing + deal_ids))
    marker.write_text(
        json.dumps(
            {"publishedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
             "dealIds": merged},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"已寫入發佈紀錄 {marker.name}（共 {len(merged)} 筆）")


def mark_posted_facebook(store_path: Path, deal_ids: list[str], platform: str = "facebook") -> None:
    """把成功發佈的優惠在 store.json 標記對應平台的已發佈旗標。"""
    if not deal_ids or not store_path.exists():
        return
    flag_key = store_flag_for(platform)
    try:
        store = load_json(store_path)
    except json.JSONDecodeError as exc:
        print(f"  ! 無法更新 {store_path.name}：{exc}")
        return

    marked = 0
    for deal in store.get("deals", []):
        if deal.get("id") in deal_ids and not deal.get(flag_key):
            deal[flag_key] = True
            marked += 1
    if marked:
        store_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已在 {store_path.name} 標記 {marked} 筆 {flag_key} = true")


def api_post(path: str, data: dict[str, str]) -> dict:
    """呼叫 Graph API，附帶簡單重試。"""
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{GRAPH}/{path}", data=body, method="POST")
    last: Exception | None = None
    for attempt in range(RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            last = RuntimeError(f"HTTP {exc.code}：{detail}")
            if exc.code in (429, 500, 502, 503) and attempt < RETRY:
                time.sleep(2**attempt * 3)
                continue
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < RETRY:
                time.sleep(2**attempt * 3)
                continue
            break
    raise RuntimeError(f"呼叫 Graph API 失敗：{last}")


def api_post_threads(path: str, data: dict[str, str]) -> dict:
    """呼叫 Threads API（graph.threads.net），重試邏輯同 api_post。"""
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{THREADS_GRAPH}/{path}", data=body, method="POST")
    last: Exception | None = None
    for attempt in range(RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            last = RuntimeError(f"HTTP {exc.code}：{detail}")
            if exc.code in (429, 500, 502, 503) and attempt < RETRY:
                time.sleep(2**attempt * 3)
                continue
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < RETRY:
                time.sleep(2**attempt * 3)
                continue
            break
    raise RuntimeError(f"呼叫 Threads API 失敗：{last}")


PORTAL_COMMENT = "🔗 傳送門：https://www.flyandfeasthk.com（優惠碼＋申請入口全部喺入面）"


def _pin_portal_comment(cfg: dict, post_id: str) -> str:
    """發佈後用專頁身份留言放傳送門並置頂（留言引流閉環）。"""
    token = cfg.get("facebook", {}).get("pageAccessToken")
    try:
        comment = api_post(f"{post_id}/comments", {"message": PORTAL_COMMENT, "access_token": token})
        comment_id = comment.get("id")
        if not comment_id:
            return "留言失敗（無回應 id）"
        api_post(comment_id, {"is_pinned": "true", "access_token": token})
        return "已留言並置頂傳送門"
    except RuntimeError as exc:
        return f"留言/置頂失敗（不影響貼文本身）：{exc}"


def post_facebook(cfg: dict, post: dict, dry: bool) -> str:
    page_id = cfg.get("facebook", {}).get("pageId")
    token = cfg.get("facebook", {}).get("pageAccessToken")
    if not page_id or not token:
        raise RuntimeError("config.json 未填 facebook.pageId 或 facebook.pageAccessToken")

    # 短文案引流策略：貼文本身不放連結（留言解鎖），傳送門放在置頂留言裡
    payload = {"message": post["message"], "access_token": token}

    if dry:
        return f"[dry-run] 將發佈到專頁 {page_id}（{len(post['message'])} 字）＋置頂留言傳送門"

    result = api_post(f"{page_id}/feed", payload)
    post_id = result.get("id", "")
    pin_msg = _pin_portal_comment(cfg, post_id)
    return f"已發佈，post id = {post_id}；{pin_msg}"


def post_instagram(cfg: dict, post: dict, dry: bool) -> str:
    ig = cfg.get("instagram", {})
    ig_id = ig.get("igUserId")
    token = ig.get("accessToken")
    if not ig_id or not token:
        raise RuntimeError("config.json 未填 instagram.igUserId 或 instagram.accessToken")

    image_url = (post.get("imageUrl") or "").strip()
    if not image_url.startswith("http"):
        return "略過：Instagram 必須有公開可存取的圖片網址（imageUrl 為空）"

    if dry:
        return f"[dry-run] 將發佈到 IG 帳號 {ig_id}（圖片：{image_url}）"

    container = api_post(
        f"{ig_id}/media",
        {"image_url": image_url, "caption": post["caption"], "access_token": token},
    )
    creation_id = container.get("id")
    if not creation_id:
        raise RuntimeError(f"建立容器失敗：{container}")

    time.sleep(5)
    result = api_post(f"{ig_id}/media_publish", {"creation_id": creation_id, "access_token": token})
    return f"已發佈，media id = {result.get('id')}"


def post_threads(cfg: dict, post: dict, dry: bool) -> str:
    """發佈文字帖到 Threads（兩步：建立容器 → 發佈）。

    Threads 無置頂留言 API，文案生成時已把傳送門直接寫進內文。
    """
    th = cfg.get("threads", {})
    user_id = th.get("userId")
    token = th.get("accessToken")
    if not user_id or not token:
        raise RuntimeError("config.json 未填 threads.userId 或 threads.accessToken（需先完成 Threads 授權）")

    text = post["message"]
    if len(text) > 500:
        text = text[:499].rstrip() + "…"

    if dry:
        return f"[dry-run] 將發佈到 Threads 帳號 {user_id}（{len(text)} 字）"

    container = api_post_threads(
        f"{user_id}/threads",
        {"media_type": "TEXT", "text": text, "access_token": token},
    )
    creation_id = container.get("id")
    if not creation_id:
        raise RuntimeError(f"Threads 建立容器失敗：{container}")

    time.sleep(3)
    result = api_post_threads(
        f"{user_id}/threads_publish",
        {"creation_id": creation_id, "access_token": token},
    )
    return f"已發佈，threads post id = {result.get('id')}"


def main() -> int:
    ap = argparse.ArgumentParser(description="發佈社群貼文")
    ap.add_argument("--manifest", required=True, help="outbox/<date>/manifest.json 路徑")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="設定檔路徑")
    ap.add_argument("--store", default=str(DEFAULT_STORE), help="主資料庫路徑（用於 postedFacebook 去重）")
    ap.add_argument("--platform", choices=["facebook", "threads", "instagram"], help="只發佈指定平台")
    ap.add_argument("--limit", type=int, default=0, help="最多發佈幾則（0 = 全部）")
    ap.add_argument("--live", action="store_true", help="真正發佈（不加此參數為 dry-run）")
    ap.add_argument("--interval", type=float, default=3.0, help="每則之間的間隔秒數")
    ap.add_argument("--no-dedup", action="store_true", help="關閉去重（預設會略過已發佈過的優惠）")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(f"找不到 manifest：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(f"找不到設定檔 {config_path}，請先複製 config.example.json 為 config.json")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))

    dry = not args.live
    posts = manifest.get("posts", [])
    if args.platform:
        posts = [p for p in posts if p["platform"] == args.platform]
    if args.limit:
        posts = posts[: args.limit]

    # 去重：同一優惠在同一平台不重複發佈（FB／Threads 分開記賬）；Instagram 不去重
    dedup_platforms = [p for p in ("facebook", "threads") if not args.platform or p == args.platform]
    seen_by_platform = {
        p: already_posted_deal_ids(Path(args.store), manifest.get("date", ""), p)
        for p in dedup_platforms
    } if not args.no_dedup else {}
    if seen_by_platform:
        before = len(posts)
        posts = [
            p for p in posts
            if p["platform"] == "instagram"
            or p.get("dealId") not in seen_by_platform.get(p["platform"], {})
        ]
        if len(posts) != before:
            print(f"去重：略過 {before - len(posts)} 則已發佈過的優惠\n")

    print(f"{'[DRY-RUN] ' if dry else '[LIVE] '}共 {len(posts)} 則待處理\n")

    ok = skipped = failed = 0
    posted_by_platform: dict[str, list[str]] = {}
    for i, post in enumerate(posts, 1):
        label = f"{i}/{len(posts)} {post['platform']} · {post['dealId']}"
        try:
            if post["platform"] == "facebook":
                msg = post_facebook(cfg, post, dry)
            elif post["platform"] == "threads":
                msg = post_threads(cfg, post, dry)
            elif post["platform"] == "instagram":
                msg = post_instagram(cfg, post, dry)
            else:
                msg = f"不支援的平台：{post['platform']}"
            if msg.startswith("略過"):
                skipped += 1
            else:
                ok += 1
                if post["platform"] in ("facebook", "threads") and msg.startswith("已發佈"):
                    posted_by_platform.setdefault(post["platform"], []).append(post["dealId"])
            print(f"  {label}\n    {msg}")
        except RuntimeError as exc:
            failed += 1
            print(f"  {label}\n    失敗：{exc}")
        if not dry and i < len(posts):
            time.sleep(args.interval)

    if not dry:
        for platform, ids in posted_by_platform.items():
            mark_posted_facebook(Path(args.store), ids, platform)
            write_publish_marker(manifest_path, ids, platform)

    print(f"\n完成：成功 {ok}、略過 {skipped}、失敗 {failed}")
    if dry:
        print("提示：這是 dry-run。確認內容無誤後加 --live 才會真正發佈。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
