#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自動回覆 Facebook 專頁與 Threads 上「想攞優惠連結」的留言，把 flyandfeasthk.com 傳送門發給對方。

設計原則
--------
1. 只回覆有查詢意圖的留言（關鍵詞命中），其餘留言只記錄、不回覆。
2. 預設 dry-run：先列印「準備回覆哪幾則」，確認無誤後加 --live 才會真正回覆。
3. 三層去重，避免重覆或洗版：
   - 留言 id 紀錄（同一則留言永不回覆兩次，跨執行、跨日期有效）
   - 每個用戶每日最多回覆一次（--per-user-daily，0 = 不限）
   - 每輪回覆上限（--limit）
4. 不回覆的情況：自家留言、含外部連結的疑似廣告、黑名單詞彙、過舊留言。
   這些只寫入日誌，不會有任何對外動作。

用法
----
    python pipeline/engage.py                                  # dry-run（安全，預設）
    python pipeline/engage.py --live                            # 真正回覆
    python pipeline/engage.py --platform facebook --live
    python pipeline/engage.py --days 3 --limit 10 --live
    python pipeline/engage.py --stats                           # 只看已回覆統計，不掃描

前置設定：pipeline/config.json 需有 facebook.pageId / facebook.pageAccessToken
（需 pages_manage_engagement 權限）與 threads.userId / threads.accessToken。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
GRAPH = "https://graph.facebook.com/v21.0"
THREADS_GRAPH = "https://graph.threads.net/v1.0"
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_STATE = ROOT / "engage_state.json"
DEFAULT_LOG = ROOT / "engage_log.jsonl"
HK_TZ = timezone(timedelta(hours=8))
RETRY = 2
DEFAULT_SITE = "https://www.flyandfeasthk.com"

# 觸發回覆的關鍵詞（不分大小寫、子字串比對）
# 注意：避免使用單字觸發詞（例如「平」會誤中「平日」），以免回覆非查詢留言。
KEYWORDS = [
    # 直接查詢優惠／連結
    "優惠", "优惠", "優恵", "著數", "特價", "促销", "促銷", "減價", "降价", "折扣", "折後",
    "傳送門", "传门", "传送门", "連結", "链接", "網址", "网址", "官網", "官网",
    "link", "website", "url", "官網", "主頁", "主页",
    # 追問／想攞更多
    "仲有", "還有", "还有", "有其他", "有咩", "有乜", "有邊", "有哪", "其他",
    "詳情", "详情", "邊度", "哪裡", "哪里", "點攞", "點拎", "點買", "想知", "想要",
    "有興趣", "有冇", "有没有", "點做", "怎麼買", "怎么买", "點book", "點訂",
    "推薦", "推荐", "邊間好", "邊隻好", "how much", "幾錢", "價錢", "价格", "what else",
    # 明確索取
    "留言", "pm", "dm", "inbox", "send", "私訊", "私信", "報名", "参加", "參加", "預約", "预约",
    # 優惠碼／預訂
    "優惠碼", "优惠码", "promo code", "coupon", "code", "代碼", "優惠券", "优惠券",
    "voucher", "booking", "預訂", "预订",
    # 查詢具體安排（常見追問）
    "點用", "怎麼用", "点用", "點申請", "申請", "使用期", "有效", "幾時", "什么时候", "幾時完",
    "到幾時", "幾點", "邊間", "哪間", "地址", "在哪", "邊度有", "點去", "地鐵", "訂位",
    # 主題詞
    "hotel", "buffet", "自助餐", "機票", "机票", "flight", "ticket",
    "攻略", "清單", "清单", "全集", "總覽", "总览", "list",
    # 正面回應（暖客，值得派連結）
    "好抵", "抵食", "抵玩", "抵買", "正呀",
]

# 命中即不回覆（可疑／廣告／不雅；只記錄）
BLACKLIST = [
    "加我", "加微信", "加wechat", "私訊我", "私信我", "代購", "代购", "外圍", "外围",
    "投資", "投资", "股票", "賭", "赌", "借貸", "借贷", "貸款", "贷款", "刷單", "刷单",
    "約炮", "约炮", "色情", "18+", "成人片", "博彩", "馬會", "马会", "殺豬盤", "杀猪盘",
    "賺錢", "赚钱", "兼職", "兼职", "招聘", "招人", "有意者", "聯繫我", "联系我",
]

# 回覆模板輪換（避免每則一模一樣，Meta 對機械式重複回覆不友善）
# {url} 由 main() 依平台帶 UTM 標籤代入，方便 GA4 分辨社群引流成效。
TEMPLATES = [
    "唔使客氣 🙌 你要嘅優惠＋預訂入口全部喺呢度：\n{url}\n\n"
    "網站每日更新香港出發嘅機票特價同酒店自助餐／餐廳優惠，每筆都有優惠碼、適用期限同官方來源。"
    "名額有限，睇啱就快手啲。價格以商戶官方公佈為準。",

    "收到 📩 傳送門喺呢度：\n{url}\n\n"
    "入面有齊今日最抵嘅香港出發機票同餐飲優惠。想搵邊類（機票／自助餐／火鍋／下午茶）可以再話我知，"
    "我幫你篩。價格以商戶官方公佈為準。",

    "多謝支持 👉 {url}\n\n"
    "所有優惠（機票／酒店自助餐／餐廳）都整理好喺入面，連優惠碼同預訂入口，跟住做就得。"
    "記得留意每筆嘅截止日期同條款，價格以商戶官方公佈為準。",

    "即刻俾你 🙂\n{url}\n\n"
    "每日更新嘅香港出發機票特價＋自助餐／餐廳折扣都在此，另附優惠碼、適用期限同原始來源。"
    "價格以商戶官方公佈為準。",

    "呢個優惠嘅申請入口＋優惠碼，喺網站對應嗰筆入面就有 👇\n{url}\n\n"
    "入到去搵返同一間餐廳／同一條航線，就會見到預訂連結同適用期限。"
    "名額有限，價格以商戶官方公佈為準。",

    "冇問題 👌 全部優惠（連優惠碼同截止日期）集中喺呢度：\n{url}\n\n"
    "網站每筆都附原始來源，方便你自己核對。想我幫你揀最抵嘅幾筆都可以話我知。"
    "價格以商戶官方公佈為準。",
]

EXTERNAL_LINK_RE = re.compile(r"https?://|www\.[a-z0-9\-]+\.", re.I)
DIGITS_ONLY_RE = re.compile(r"^[\s\d\W_]+$", re.UNICODE)


# --------------------------------------------------------------------------
# 基礎工具
# --------------------------------------------------------------------------

def load_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def api(method: str, url: str, data: dict | None = None) -> dict:
    """呼叫 Graph API（FB 或 Threads），附簡單重試。"""
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    last: Exception | None = None
    for attempt in range(RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            last = RuntimeError(f"HTTP {exc.code}：{detail[:400]}")
            if exc.code in (429, 500, 502, 503) and attempt < RETRY:
                time.sleep(2 ** attempt * 3)
                continue
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < RETRY:
                time.sleep(2 ** attempt * 3)
                continue
            break
    raise RuntimeError(f"呼叫 API 失敗：{last}")


def get_json(base: str, path: str, params: dict) -> dict:
    url = f"{base}/{path}?{urllib.parse.urlencode(params)}"
    return api("GET", url)


def post_json(base: str, path: str, data: dict) -> dict:
    return api("POST", f"{base}/{path}", data)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S+0000"):
        try:
            return datetime.strptime(value.replace("Z", "+0000"), fmt)
        except ValueError:
            continue
    return None


def now_hk() -> datetime:
    return datetime.now(HK_TZ)


def today_str() -> str:
    return now_hk().strftime("%Y-%m-%d")


def matched_keyword(text: str) -> str | None:
    low = (text or "").lower()
    for kw in KEYWORDS:
        if kw.lower() in low:
            return kw
    return None


def is_blocked(text: str) -> str | None:
    low = (text or "").lower()
    for bad in BLACKLIST:
        if bad.lower() in low:
            return bad
    return None


def log_line(path: Path, record: dict) -> None:
    record = {"at": now_hk().isoformat(timespec="seconds"), **record}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# 抓取留言
# --------------------------------------------------------------------------

def fb_collect_posts(cfg: dict, days: int, max_posts: int) -> list[dict]:
    fb = cfg.get("facebook", {})
    page_id, token = fb.get("pageId"), fb.get("pageAccessToken")
    if not page_id or not token:
        raise RuntimeError("config.json 未填 facebook.pageId 或 facebook.pageAccessToken")
    payload = get_json(GRAPH, f"{page_id}/posts", {
        "fields": "id,created_time,message,permalink_url",
        "limit": max_posts,
        "access_token": token,
    })
    cutoff = now_hk() - timedelta(days=days)
    posts = []
    for post in payload.get("data", []):
        ts = parse_time(post.get("created_time"))
        if ts and ts < cutoff:
            continue
        posts.append(post)
    return posts


def fb_collect_comments(post_id: str, token: str, comment_cutoff: datetime) -> list[dict]:
    """回傳貼文下所有（含一層回覆）留言。"""
    rich = ("id,message,from,created_time,parent,permalink_url,"
            "comments.limit(25){id,message,from,created_time,parent,permalink_url}")
    simple = "id,message,from,created_time,parent"
    out: list[dict] = []
    for fields in (rich, simple):
        try:
            payload = get_json(GRAPH, f"{post_id}/comments",
                               {"fields": fields, "limit": 50, "access_token": token})
        except RuntimeError:
            continue
        out = []
        for comment in payload.get("data", []):
            out.append(comment)
            for reply in (comment.get("comments") or {}).get("data", []) or []:
                out.append(reply)
        if out or fields == simple:
            break
    result = []
    for comment in out:
        ts = parse_time(comment.get("created_time"))
        if ts and ts < comment_cutoff:
            continue
        result.append(comment)
    return result


def threads_collect_media(cfg: dict, days: int, max_posts: int) -> list[dict]:
    th = cfg.get("threads", {})
    user_id, token = th.get("userId"), th.get("accessToken")
    if not user_id or not token:
        raise RuntimeError("config.json 未填 threads.userId 或 threads.accessToken")
    payload = get_json(THREADS_GRAPH, f"{user_id}/threads", {
        "fields": "id,text,timestamp,permalink",
        "limit": max_posts,
        "access_token": token,
    })
    cutoff = now_hk() - timedelta(days=days)
    media = []
    for item in payload.get("data", []):
        ts = parse_time(item.get("timestamp"))
        if ts and ts < cutoff:
            continue
        media.append(item)
    return media


def threads_own_username(cfg: dict) -> str:
    token = cfg.get("threads", {}).get("accessToken")
    if not token:
        return ""
    try:
        me = get_json(THREADS_GRAPH, "me", {"fields": "id,username", "access_token": token})
        return (me.get("username") or "").lower()
    except RuntimeError:
        return ""


def threads_collect_replies(media_id: str, token: str, comment_cutoff: datetime) -> list[dict]:
    """取得某則帖文下的所有回覆（先試 conversation，再退回 replies）。"""
    collected: list[dict] = []
    for path, fields in (
        (f"{media_id}/conversation", "id,text,timestamp,username,replied_to,permalink"),
        (f"{media_id}/replies", "id,text,timestamp,username,replied_to,permalink"),
        (f"{media_id}/replies", "id,text,timestamp,username"),
    ):
        try:
            payload = get_json(THREADS_GRAPH, path,
                               {"fields": fields, "limit": 50, "access_token": token})
        except RuntimeError:
            continue
        collected = payload.get("data", []) or []
        if collected:
            break
    result = []
    for item in collected:
        ts = parse_time(item.get("timestamp"))
        if ts and ts < comment_cutoff:
            continue
        result.append(item)
    return result


# --------------------------------------------------------------------------
# 發送回覆
# --------------------------------------------------------------------------

def fb_reply(comment_id: str, text: str, token: str) -> str:
    res = post_json(GRAPH, f"{comment_id}/comments", {"message": text, "access_token": token})
    reply_id = res.get("id")
    if not reply_id:
        raise RuntimeError(f"回覆無回應 id：{res}")
    return reply_id


def threads_reply(user_id: str, reply_to_id: str, text: str, token: str) -> str:
    if len(text) > 500:
        text = text[:499].rstrip() + "…"
    container = post_json(THREADS_GRAPH, f"{user_id}/threads", {
        "media_type": "TEXT",
        "text": text,
        "reply_to_id": reply_to_id,
        "access_token": token,
    })
    creation_id = container.get("id")
    if not creation_id:
        raise RuntimeError(f"Threads 建立回覆容器失敗：{container}")
    time.sleep(3)
    res = post_json(THREADS_GRAPH, f"{user_id}/threads_publish",
                    {"creation_id": creation_id, "access_token": token})
    reply_id = res.get("id")
    if not reply_id:
        raise RuntimeError(f"Threads 發佈回覆失敗：{res}")
    return reply_id


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def collect_comments(cfg: dict, args, cutoff: datetime) -> list[dict]:
    """抓取兩個平台上近期帖文的所有留言／回覆（未過濾，篩選在 main() 進行）。"""
    scanned: list[dict] = []

    if args.platform in ("facebook", "both"):
        fb = cfg.get("facebook", {})
        page_id, token = fb.get("pageId"), fb.get("pageAccessToken")
        posts = fb_collect_posts(cfg, args.days, args.max_posts)
        print(f"Facebook：找到 {len(posts)} 則近期帖文（{args.days} 日內）")
        for post in posts:
            try:
                comments = fb_collect_comments(post["id"], token, cutoff)
            except RuntimeError as exc:
                print(f"  ! 讀取 {post['id']} 留言失敗：{exc}")
                continue
            for comment in comments:
                author = comment.get("from") or {}
                scanned.append({
                    "platform": "facebook",
                    "commentId": comment.get("id"),
                    "postId": post["id"],
                    "user": str(author.get("id") or ""),
                    "userName": author.get("name") or "",
                    "text": comment.get("message") or "",
                    "createdAt": comment.get("created_time") or "",
                    "permalink": comment.get("permalink_url") or post.get("permalink_url") or "",
                    "isOwn": str(author.get("id") or "") == str(page_id),
                })

    if args.platform in ("threads", "both"):
        th = cfg.get("threads", {})
        user_id, token = th.get("userId"), th.get("accessToken")
        own = threads_own_username(cfg)
        try:
            media = threads_collect_media(cfg, args.days, args.max_posts)
        except RuntimeError as exc:
            print(f"Threads：讀取帖文失敗（略過）：{exc}")
            media = []
        print(f"Threads：找到 {len(media)} 則近期帖文（{args.days} 日內）")
        for item in media:
            try:
                replies = threads_collect_replies(item["id"], token, cutoff)
            except RuntimeError as exc:
                print(f"  ! 讀取 {item['id']} 回覆失敗：{exc}")
                continue
            for rep in replies:
                username = (rep.get("username") or "")
                scanned.append({
                    "platform": "threads",
                    "commentId": rep.get("id"),
                    "postId": item["id"],
                    "user": username.lower(),
                    "userName": username,
                    "text": rep.get("text") or "",
                    "createdAt": rep.get("timestamp") or "",
                    "permalink": rep.get("permalink") or item.get("permalink") or "",
                    "isOwn": bool(own) and username.lower() == own,
                })

    return scanned


def site_url_for(site_url: str, platform: str, keyword: str = "") -> str:
    """為回覆連結加上 UTM 標籤，方便 GA4 分辨社群引流成效。"""
    url = site_url or ""
    if not url:
        return url
    sep = "&" if "?" in url else "?"
    src = "threads" if platform == "threads" else "facebook"
    utm = f"{url}{sep}utm_source={src}&utm_medium=social&utm_campaign=comment_reply"
    if keyword:
        utm += f"&utm_content={urllib.parse.quote(keyword)}"
    return utm


def main() -> int:
    ap = argparse.ArgumentParser(description="自動回覆社群優惠查詢留言（預設 dry-run）")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--log", default=str(DEFAULT_LOG))
    ap.add_argument("--platform", choices=["facebook", "threads", "both"], default="both")
    ap.add_argument("--days", type=int, default=7, help="只看最近幾日的帖文")
    ap.add_argument("--comment-days", type=int, default=7, help="只回覆最近幾日的留言")
    ap.add_argument("--max-posts", type=int, default=20, help="每個平台最多掃幾則帖文")
    ap.add_argument("--limit", type=int, default=20, help="本輪最多回覆幾則")
    ap.add_argument("--per-user-daily", type=int, default=1, help="每個用戶每日最多回覆幾次（0=不限）")
    ap.add_argument("--interval", type=float, default=4.0, help="每則回覆之間相隔秒數")
    ap.add_argument("--live", action="store_true", help="真正回覆（不加 = dry-run）")
    ap.add_argument("--stats", action="store_true", help="只顯示歷史統計，不掃描")
    args = ap.parse_args()

    state_path = Path(args.state)
    log_path = Path(args.log)
    state = load_json(state_path, {}) or {}
    state.setdefault("replied", {})
    state.setdefault("userDaily", {})

    if args.stats:
        replied = state.get("replied", {})
        by_platform: dict[str, int] = {}
        for item in replied.values():
            by_platform[item.get("platform", "?")] = by_platform.get(item.get("platform", "?"), 0) + 1
        print(f"累計已回覆 {len(replied)} 則：{by_platform or '（尚無）'}")
        recent = sorted(replied.items(), key=lambda kv: kv[1].get("at", ""), reverse=True)[:10]
        for cid, item in recent:
            print(f"  {item.get('at','')} {item.get('platform','')} @{item.get('userName','')} "
                  f"[{item.get('keyword','')}] → {item.get('replyId','')}")
        return 0

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(f"找不到設定檔 {config_path}")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    site_url = (cfg.get("site", {}) or {}).get("url") or DEFAULT_SITE

    dry = not args.live
    comment_cutoff = now_hk() - timedelta(days=args.comment_days)
    today = today_str()

    scanned = collect_comments(cfg, args, comment_cutoff)
    print(f"共掃描到 {len(scanned)} 則留言／回覆\n")

    replied_state: dict = state["replied"]
    user_daily: dict = state["userDaily"]

    pending: list[dict] = []
    reasons: dict[str, int] = {}

    def note(reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1

    for item in scanned:
        if not item.get("commentId"):
            note("無留言 id") ; continue
        if item.get("isOwn"):
            note("自家留言") ; continue
        if item["commentId"] in replied_state:
            note("已回覆過") ; continue
        if not (item.get("text") or "").strip():
            note("空白留言") ; continue
        bad = is_blocked(item["text"])
        if bad:
            note(f"黑名單詞：{bad}") ; continue
        if EXTERNAL_LINK_RE.search(item["text"]):
            note("疑似廣告（含外部連結）") ; continue
        kw = matched_keyword(item["text"])
        if not kw:
            note("非查詢留言") ; continue
        if args.per_user_daily and item.get("user"):
            key = f"{item['platform']}:{item['user']}"
            if user_daily.get(key) == today:
                note("該用戶今日已回覆") ; continue
        item["keyword"] = kw
        pending.append(item)

    pending = pending[: args.limit]

    print(f"{'[DRY-RUN] ' if dry else '[LIVE] '}準備回覆 {len(pending)} 則；"
          f"略過 {sum(reasons.values())} 則")
    if reasons:
        print("  略過原因：" + "、".join(f"{k}×{v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])))
    print()

    ok = failed = 0
    if dry:
        for item in pending:
            text = random.choice(TEMPLATES).format(
                url=site_url_for(site_url, item["platform"], item.get("keyword", "")))
            print(f"  · {item['platform']} @{item['userName']} 「{item['text'][:40]}」"
                  f"（命中：{item['keyword']}）")
            print(f"    → {text.splitlines()[0]}")
    else:
        for i, item in enumerate(pending, 1):
            template = TEMPLATES[(i - 1) % len(TEMPLATES)]
            text = template.format(
                url=site_url_for(site_url, item["platform"], item.get("keyword", "")))
            label = f"{i}/{len(pending)} {item['platform']} @{item['userName']}"
            try:
                if item["platform"] == "facebook":
                    reply_id = fb_reply(item["commentId"], text,
                                        cfg["facebook"]["pageAccessToken"])
                else:
                    reply_id = threads_reply(cfg["threads"]["userId"], item["commentId"], text,
                                             cfg["threads"]["accessToken"])
                ok += 1
                replied_state[item["commentId"]] = {
                    "platform": item["platform"],
                    "postId": item["postId"],
                    "user": item["user"],
                    "userName": item["userName"],
                    "keyword": item["keyword"],
                    "replyId": reply_id,
                    "at": now_hk().isoformat(timespec="seconds"),
                }
                if args.per_user_daily and item.get("user"):
                    user_daily[f"{item['platform']}:{item['user']}"] = today
                log_line(log_path, {"action": "replied", "platform": item["platform"],
                                    "commentId": item["commentId"], "replyId": reply_id,
                                    "userName": item["userName"], "keyword": item["keyword"]})
                print(f"  {label}\n    已回覆 → {reply_id}")
            except (RuntimeError, KeyError) as exc:
                failed += 1
                log_line(log_path, {"action": "failed", "platform": item["platform"],
                                    "commentId": item["commentId"], "error": str(exc)[:300]})
                print(f"  {label}\n    失敗：{exc}")
            if i < len(pending):
                time.sleep(args.interval)

    # 記錄略過的留言（只記錄有查詢意圖但被擋掉的，方便覆核）
    if not dry:
        for item in scanned:
            if item["commentId"] not in replied_state and matched_keyword(item.get("text", "")):
                if not item.get("isOwn"):
                    log_line(log_path, {"action": "skipped", "platform": item["platform"],
                                        "commentId": item["commentId"],
                                        "userName": item["userName"],
                                        "text": (item.get("text") or "")[:80]})

    # 精簡 state，避免無限增長
    if len(replied_state) > 3000:
        keep = sorted(replied_state.items(), key=lambda kv: kv[1].get("at", ""), reverse=True)[:3000]
        state["replied"] = dict(keep)
    state["lastRun"] = now_hk().isoformat(timespec="seconds")
    state["lastRunStats"] = {"scanned": len(scanned), "pending": len(pending),
                             "replied": ok, "failed": failed}
    save_json(state_path, state)

    print(f"\n完成：成功 {ok}、失敗 {failed}（累計已回覆 {len(state['replied'])} 則）")
    if dry:
        print("提示：這是 dry-run，未對外發送任何回覆。確認內容無誤後加 --live 才會真正回覆。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
