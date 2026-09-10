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

git add -A
if git diff --cached --quiet; then
  echo "沒有變更，無需部署。"
  exit 0
fi

git commit -m "chore: 更新優惠資料 $(date +%Y-%m-%d)"
git push
echo "已推送，GitHub Actions 會自動發佈到 flyandfeasthk.com"
