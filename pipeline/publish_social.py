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
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
GRAPH = "https://graph.facebook.com/v21.0"
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_STORE = ROOT / "store.json"
OUTBOX = PROJECT / "outbox"
RETRY = 2


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def already_posted_deal_ids(store_path: Path, current_date: str) -> dict[str, str]:
    """收集不應再次發佈的優惠 id。

    來源一：store.json 內 postedFacebook 為 true 的優惠。
    來源二：之前日期 outbox/<date>/manifest.json 已收錄的 Facebook 貼文 id。
    回傳 {dealId: 原因}，方便列印略過原因。
    """
    seen: dict[str, str] = {}

    if store_path.exists():
        try:
            store = load_json(store_path)
        except json.JSONDecodeError:
            store = {}
        for deal in store.get("deals", []):
            if deal.get("postedFacebook") and deal.get("id"):
                seen[deal["id"]] = "store.json 已標記 postedFacebook"

    if OUTBOX.exists():
        for manifest in sorted(OUTBOX.glob("*/manifest.json")):
            if manifest.parent.name >= current_date:
                continue  # 只計之前日期，當日 manifest 屬本次發佈
            try:
                payload = load_json(manifest)
            except json.JSONDecodeError:
                continue
            for post in payload.get("posts", []):
                if post.get("platform") != "facebook":
                    continue
                deal_id = post.get("dealId")
                if deal_id and deal_id != "digest" and deal_id not in seen:
                    seen[deal_id] = f"已於 {manifest.parent.name} outbox 發佈"

    return seen


def mark_posted_facebook(store_path: Path, deal_ids: list[str]) -> None:
    """把成功發佈的優惠在 store.json 標記 postedFacebook = true。"""
    if not deal_ids or not store_path.exists():
        return
    try:
        store = load_json(store_path)
    except json.JSONDecodeError as exc:
        print(f"  ! 無法更新 {store_path.name}：{exc}")
        return

    marked = 0
    for deal in store.get("deals", []):
        if deal.get("id") in deal_ids and not deal.get("postedFacebook"):
            deal["postedFacebook"] = True
            marked += 1
    if marked:
        store_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已在 {store_path.name} 標記 {marked} 筆 postedFacebook = true")


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


PORTAL_COMMENT = "🔗 傳送門：https://flyandfeasthk.com（優惠碼＋申請入口全部喺入面）"


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


def main() -> int:
    ap = argparse.ArgumentParser(description="發佈社群貼文")
    ap.add_argument("--manifest", required=True, help="outbox/<date>/manifest.json 路徑")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="設定檔路徑")
    ap.add_argument("--store", default=str(DEFAULT_STORE), help="主資料庫路徑（用於 postedFacebook 去重）")
    ap.add_argument("--platform", choices=["facebook", "instagram"], help="只發佈指定平台")
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

    # 去重：同一優惠不重複發佈；速報（digest）每日照發
    posted_skipped: dict[str, str] = {}
    if not args.no_dedup:
        posted_skipped = already_posted_deal_ids(Path(args.store), manifest.get("date", ""))
        keep = []
        for post in posts:
            deal_id = post.get("dealId")
            if deal_id and deal_id != "digest" and deal_id in posted_skipped:
                continue
            keep.append(post)
        if len(keep) != len(posts):
            print(f"去重：略過 {len(posts) - len(keep)} 則已發佈過的優惠\n")
        posts = keep

    print(f"{'[DRY-RUN] ' if dry else '[LIVE] '}共 {len(posts)} 則待處理\n")

    ok = skipped = failed = 0
    fb_posted: list[str] = []
    for i, post in enumerate(posts, 1):
        label = f"{i}/{len(posts)} {post['platform']} · {post['dealId']}"
        try:
            if post["platform"] == "facebook":
                msg = post_facebook(cfg, post, dry)
            elif post["platform"] == "instagram":
                msg = post_instagram(cfg, post, dry)
            else:
                msg = f"不支援的平台：{post['platform']}"
            if msg.startswith("略過"):
                skipped += 1
            else:
                ok += 1
                if post["platform"] == "facebook" and msg.startswith("已發佈"):
                    fb_posted.append(post["dealId"])
            print(f"  {label}\n    {msg}")
        except RuntimeError as exc:
            failed += 1
            print(f"  {label}\n    失敗：{exc}")
        if not dry and i < len(posts):
            time.sleep(args.interval)

    if fb_posted and not dry:
        mark_posted_facebook(Path(args.store), fb_posted)

    print(f"\n完成：成功 {ok}、略過 {skipped}、失敗 {failed}")
    if dry:
        print("提示：這是 dry-run。確認內容無誤後加 --live 才會真正發佈。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
