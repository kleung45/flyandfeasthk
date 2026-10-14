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
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
REPO = os.environ.get("GH_REPO", "kleung45/flyandfeasthk")
BRANCH = os.environ.get("GH_BRANCH", "main")
TIMEOUT = 60
RETRIES = 3
HK_TZ = timezone(timedelta(hours=8))
VALID_MODES = {"100644", "100755", "120000"}


def git(*args: str, timeout: int = 90) -> str:
    # 這台機器上 git fetch／push 偶爾會無限期掛住（零輸出、不回應），
    # 所以所有 git 呼叫一律加上逾時，掛住時降級而不是拖死整個部署流程。
    try:
        proc = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(f"git {' '.join(args)} 逾時（{timeout}s）")
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
    """依序取得 GitHub 令牌：環境變數 → config.json（本機、不上傳）→ 系統憑證助手。

    這台機器上從 Python 子進程呼叫 git-credential-manager 會無回應（實測 45 秒逾時），
    所以正式做法是把令牌存在 pipeline/config.json 的 github.token，只在最後才退回憑證助手。
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token

    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            token = (cfg.get("github") or {}).get("token", "").strip()
            if token:
                return token
        except (json.JSONDecodeError, OSError):
            pass

    env = dict(os.environ)
    env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(
            "無法取得 GitHub 憑證：憑證助手逾時。請在 pipeline/config.json 加入\n"
            '  "github": { "token": "<你的 GitHub PAT>" }\n'
            "（config.json 已列入 .gitignore，不會上傳）"
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


def staged_files() -> list[tuple[str, str, str]]:
    """回傳 [(相對路徑, git 模式, index 內的 blob sha)]。

    先執行 `git add -A`，讓 git 依 .gitattributes 對換行做正規化；
    之後一律從 index 取內容，避免把 Windows 的 CRLF 原始位元組直接寫進遠端。
    這裡一併回傳 blob sha，好在推送前比對遠端——內容一樣的檔案唔需要重新上傳。
    """
    git("add", "-A")
    out = git("ls-files", "-s")
    seen: dict[str, tuple[str, str]] = {}
    for line in out.splitlines():
        if not line.strip() or "\t" not in line:
            continue
        meta, _, path = line.partition("\t")
        parts = meta.split()
        mode = parts[0] if parts and parts[0] in VALID_MODES else "100644"
        sha = parts[1] if len(parts) > 1 else ""
        if path:
            seen[path] = (mode, sha)
    return sorted((p, m, s) for p, (m, s) in seen.items())


def remote_blobs(token: str, tree_sha: str) -> dict[str, str]:
    """遞迴列出遠端某個 tree 內所有 blob：{路徑: blobs sha}。

    用途一：偵測「本機已刪除但遠端仍在」的檔案。Git Data API 建立 tree 時若只用
    base_tree + 本機檔案，行為是純增量的——刪除永遠不會傳到遠端
    （2026-09-24 踩過：.workbuddy 內部筆記從索引移除後，仍留在公開 repo 內）。
    用途二：同本機 index 的 blob sha 比對，內容無變的檔案唔使重新上傳——
    2026-10-14 踩過：489 個檔案一次過建 tree 會被 GitHub 以 422
    「input was too large to process」擋下。
    """
    paths: dict[str, str] = {}
    # 先用 recursive=1 一次取回整棵 tree（repo 有幾百個目錄，逐層走會慢十倍以上）
    try:
        full = api(token, f"/git/trees/{tree_sha}?recursive=1")
    except SystemExit:
        full = {}
    if full.get("tree"):
        for item in full["tree"]:
            if item.get("type") == "blob":
                paths[f"{item['path']}"] = item.get("sha", "")
        return paths

    pending: list[tuple[str, str]] = [("", tree_sha)]
    while pending:
        prefix, sha = pending.pop()
        data = api(token, f"/git/trees/{sha}")
        for item in data.get("tree", []):
            path = f"{prefix}{item['path']}"
            if item.get("type") == "blob":
                paths[path] = item.get("sha", "")
            elif item.get("type") == "tree" and item.get("sha"):
                pending.append((path + "/", item["sha"]))
    return paths


def build_tree(token: str, base_tree: str, entries: list[dict], chunk: int = 80) -> str:
    """分批建立 tree，避免一次過提交太多 entry 被 GitHub 拒收。

    Git Data API 支援以 base_tree 逐層疊加，所以可以安全地切細提交。
    """
    tree = base_tree
    for i in range(0, len(entries), chunk):
        tree = api(
            token, "/git/trees", "POST", {"base_tree": tree, "tree": entries[i : i + chunk]}
        )["sha"]
    return tree


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
    # 若 git fetch 逾時／失敗，改用 API 拿到的遠端 HEAD 判斷（下面非強制更新 ref，
    # 遠端若已前進，GitHub 會拒絕，不會造成覆蓋），所以可以安全降級繼續。
    try:
        git("fetch", "origin", BRANCH)
        remote_head = git("rev-parse", "FETCH_HEAD").strip()
        local_head = git("rev-parse", "HEAD").strip()
    except SystemExit as exc:
        print(f"注意：無法用本機 git 比對遠端（{exc}），改由推送時的非強制更新保護。")
        remote_head = local_head = ""
    if remote_head and remote_head != local_head:
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
    print(f"本機追蹤檔案 {len(files)} 個，目標 {REPO}@{BRANCH}")

    token = get_token()
    head = api(token, f"/git/ref/heads/{BRANCH}")["object"]["sha"]
    base_tree = api(token, f"/git/commits/{head}")["tree"]["sha"]
    print(f"遠端目前 HEAD：{head[:9]}")

    # 取遠端檔案清單（路徑 → blob sha）：
    #   1. 遠端有、本機沒有的檔案要以 sha=null 移除，否則刪除不會生效
    #      （Git Data API 的 base_tree 是純增量語意）
    #   2. 內容（blob sha）與遠端一致的檔案唔需要重新上傳，只留在 base_tree 內即可
    try:
        remote_map = remote_blobs(token, base_tree)
    except SystemExit as exc:
        print(f"注意：未能讀取遠端檔案清單，本次略過刪除處理並全量上傳（{exc}）")
        remote_map = {}

    if remote_map:
        local_paths = {path for path, _, _ in files}
        deletions = sorted(set(remote_map) - local_paths)
        to_upload = [f for f in files if remote_map.get(f[0]) != f[2]]
    else:
        deletions = []
        to_upload = list(files)

    if deletions:
        print(f"將移除遠端 {len(deletions)} 個檔案：")
        for path in deletions[:20]:
            print(f"  - {path}")
        if len(deletions) > 20:
            print(f"  …（其餘 {len(deletions) - 20} 個）")

    print(f"內容有變、需要上傳：{len(to_upload)} 個（其餘 {len(files) - len(to_upload)} 個沿用遠端）")

    entries = []
    for path, mode, _ in to_upload:
        # 從 index 取內容（已套用 .gitattributes 的換行正規化），而非磁碟原始位元組
        content = git_bytes("cat-file", "blob", f":{path}")
        blob = api(
            token,
            "/git/blobs",
            "POST",
            {"content": base64.b64encode(content).decode(), "encoding": "base64"},
        )["sha"]
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": blob})
    for path in deletions:
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
    print(
        f"已上傳 {len(entries) - len(deletions)} 個 blob"
        + (f"，並移除 {len(deletions)} 個檔案" if deletions else "")
    )

    if not entries:
        print("遠端內容與本機一致，無需提交。")
        return
    tree = build_tree(token, base_tree, entries)
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
