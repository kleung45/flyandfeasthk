#!/usr/bin/env bash
# 一鍵建置並部署到 GitHub Pages。
# 未設定 Git 遠端時只做本機建置，不會報錯，方便每日自動化安全呼叫。
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTHONIOENCODING=utf-8
PYTHON="${PYTHON:-python}"

echo "== 重建網站資料 =="
"$PYTHON" pipeline/build_site.py

echo
echo "== 產生社群文案 =="
"$PYTHON" pipeline/generate_content.py

echo
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "尚未設定 Git 遠端（git remote add origin ...），只完成本機建置，跳過部署。"
  exit 0
fi

# 安全閘：示範資料仍在上線內容中時，拒絕推送，避免公開假價格
if [ "${1:-}" != "--force" ] && grep -q '"sample": true' data/deals.json 2>/dev/null; then
  echo "偵測到網站資料仍包含示範優惠（sample = true），已中止部署。"
  echo "請先在 pipeline/store.json 換上真實優惠並把 meta.sample 設為 false；"
  echo "若確定要照樣部署，執行：bash pipeline/deploy.sh --force"
  exit 1
fi

echo
echo "== 推送並部署 =="
# 這台機器上 `git push` 會無回應逾時（實測掛住 90 秒以上且零輸出），
# 因此改走 GitHub API 推送，效果等同一次 push。
"$PYTHON" pipeline/push_api.py
echo "已推送，GitHub Actions 會自動發佈網站"
