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
GRAPH = "https://graph.facebook.com/v21.0"
DEFAULT_CONFIG = ROOT / "config.json"
RETRY = 2


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


def post_facebook(cfg: dict, post: dict, dry: bool) -> str:
    page_id = cfg.get("facebook", {}).get("pageId")
    token = cfg.get("facebook", {}).get("pageAccessToken")
    if not page_id or not token:
        raise RuntimeError("config.json 未填 facebook.pageId 或 facebook.pageAccessToken")

    payload = {"message": post["message"], "access_token": token}
    if post.get("link"):
        payload["link"] = post["link"]

    if dry:
        return f"[dry-run] 將發佈到專頁 {page_id}（{len(post['message'])} 字）"

    result = api_post(f"{page_id}/feed", payload)
    return f"已發佈，post id = {result.get('id')}"


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
    ap.add_argument("--platform", choices=["facebook", "instagram"], help="只發佈指定平台")
    ap.add_argument("--limit", type=int, default=0, help="最多發佈幾則（0 = 全部）")
    ap.add_argument("--live", action="store_true", help="真正發佈（不加此參數為 dry-run）")
    ap.add_argument("--interval", type=float, default=3.0, help="每則之間的間隔秒數")
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

    print(f"{'[DRY-RUN] ' if dry else '[LIVE] '}共 {len(posts)} 則待處理\n")

    ok = skipped = failed = 0
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
            print(f"  {label}\n    {msg}")
        except RuntimeError as exc:
            failed += 1
            print(f"  {label}\n    失敗：{exc}")
        if not dry and i < len(posts):
            time.sleep(args.interval)

    print(f"\n完成：成功 {ok}、略過 {skipped}、失敗 {failed}")
    if dry:
        print("提示：這是 dry-run。確認內容無誤後加 --live 才會真正發佈。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
