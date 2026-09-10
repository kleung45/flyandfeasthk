#!/usr/bin/env python3
"""把本機 main 分支的內容推送到 GitHub（走 API，不依賴 git push）。

背景：執行 `git push` 在這台機器上會無回應逾時（沒有任何輸出就掛住），
每日自動化若照樣呼叫會卡死。改用 GitHub Git Data API 直接建立 commit
並更新遠端分支，行為等同一次 push。

憑證由 `git credential fill` 取得，只在記憶體中使用，不寫入磁碟、不輸出到日誌。

用法：
    python pipeline/push_api.py
    python pipeline/push_api.py --message "自訂提交訊息"
    python pipeline/push_api.py --dry-run
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
REPO = os.environ.get("GH_REPO", "kleung45/flyandfeasthk")
BRANCH = os.environ.get("GH_BRANCH", "main")
TIMEOUT = 60
RETRIES = 3
HK_TZ = timezone(timedelta(hours=8))
VALID_MODES = {"100644", "100755", "120000"}


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失敗：{proc.stderr.strip()}")
    return proc.stdout


def git_bytes(*args: str) -> bytes:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} 失敗：{proc.stderr.decode(errors='replace').strip()}"
        )
    return proc.stdout


def get_token() -> str:
    env = dict(os.environ)
    env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=45,
    )
    if proc.returncode != 0:
        raise SystemExit(f"無法取得 GitHub 憑證：{proc.stderr.strip()}")
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("憑證輸出中沒有 password 欄位")


def api(token: str, path: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    last = ""
    for attempt in range(1, RETRIES + 1):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}{path}", data=body, method=method
        )
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "fly-and-feast-pipeline")
        if body:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:300]
            if exc.code in (500, 502, 503) and attempt < RETRIES:
                last = f"{exc.code} {detail}"
                time.sleep(2 * attempt)
                continue
            raise SystemExit(f"{method} {path} 失敗 {exc.code}：{detail}")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = str(exc)
            if attempt < RETRIES:
                time.sleep(2 * attempt)
                continue
            raise SystemExit(f"{method} {path} 連線失敗：{last}")
    raise SystemExit(f"{method} {path} 重試 {RETRIES} 次仍失敗：{last}")


def staged_files() -> list[tuple[str, str]]:
    """回傳 [(相對路徑, git 模式)]。

    先執行 `git add -A`，讓 git 依 .gitattributes 對換行做正規化；
    之後一律從 index 取內容，避免把 Windows 的 CRLF 原始位元組直接寫進遠端。
    """
    git("add", "-A")
    out = git("ls-files", "-s")
    seen: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip() or "\t" not in line:
            continue
        meta, _, path = line.partition("\t")
        parts = meta.split()
        mode = parts[0] if parts and parts[0] in VALID_MODES else "100644"
        if path:
            seen[path] = mode
    return sorted(seen.items())


def main() -> None:
    parser = argparse.ArgumentParser(description="透過 GitHub API 推送本機內容")
    parser.add_argument("--message", default=None, help="提交訊息，預設自動產生")
    parser.add_argument("--dry-run", action="store_true", help="只顯示會推送什麼，不真的提交")
    parser.add_argument(
        "--force",
        action="store_true",
        help="遠端有本機沒有的提交時，仍強行覆蓋（預設會中止）",
    )
    args = parser.parse_args()

    # 防覆蓋檢查：有人在 GitHub 網頁改過檔案時，本機的舊版本會把它蓋掉
    git("fetch", "origin", BRANCH)
    remote_head = git("rev-parse", "FETCH_HEAD").strip()
    local_head = git("rev-parse", "HEAD").strip()
    if remote_head != local_head:
        behind = (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", remote_head, local_head], cwd=ROOT
            ).returncode
            != 0
        )
        if behind and not args.force:
            files = git("diff", "--name-only", f"{local_head}..{remote_head}").split()
            print(f"遠端有本機沒有的提交（{remote_head[:9]}），為避免覆蓋已中止。")
            print("受影響的檔案：" + "、".join(files) if files else "（無法列出）")
            print("先執行 `git fetch origin main && git reset --hard FETCH_HEAD` 對齊，")
            print("或確認要覆蓋時加 --force。")
            raise SystemExit(1)

    files = staged_files()
    if not files:
        raise SystemExit("沒有可推送的檔案。")
    print(f"準備推送 {len(files)} 個檔案到 {REPO}@{BRANCH}")

    token = get_token()
    head = api(token, f"/git/ref/heads/{BRANCH}")["object"]["sha"]
    base_tree = api(token, f"/git/commits/{head}")["tree"]["sha"]
    print(f"遠端目前 HEAD：{head[:9]}")

    entries = []
    for path, mode in files:
        # 從 index 取內容（已套用 .gitattributes 的換行正規化），而非磁碟原始位元組
        content = git_bytes("cat-file", "blob", f":{path}")
        blob = api(
            token,
            "/git/blobs",
            "POST",
            {"content": base64.b64encode(content).decode(), "encoding": "base64"},
        )["sha"]
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": blob})
    print(f"已上傳 {len(entries)} 個 blob")

    tree = api(token, "/git/trees", "POST", {"base_tree": base_tree, "tree": entries})["sha"]
    if tree == base_tree:
        print("遠端內容與本機一致，無需提交。")
        return
    print(f"新 tree：{tree[:9]}")

    if args.dry_run:
        print("--dry-run：略過提交。")
        return

    now = datetime.now(HK_TZ)
    message = args.message or f"chore: 更新優惠資料 {now:%Y-%m-%d}"
    commit = api(
        token,
        "/git/commits",
        "POST",
        {"message": message, "tree": tree, "parents": [head]},
    )["sha"]
    api(token, f"/git/refs/heads/{BRANCH}", "PATCH", {"sha": commit, "force": False})
    print(f"已推送：{commit[:9]}")
    print(f"連結：https://github.com/{REPO}/commit/{commit}")

    # 讓本機與遠端對齊，避免下一次提交出現分岔
    try:
        git("fetch", "origin", BRANCH)
        fetched = git("rev-parse", "FETCH_HEAD").strip()
        if fetched == commit:
            git("reset", "--hard", "FETCH_HEAD")
            print("本機已同步至最新提交。")
        else:
            print(f"注意：抓取到的提交（{fetched[:9]}）與推送結果不符，略過本機同步。")
    except SystemExit as exc:
        print(f"注意：本機同步失敗，但不影響線上部署（{exc}）")


if __name__ == "__main__":
    main()
