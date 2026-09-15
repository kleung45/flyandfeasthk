# 社群留言自動回覆 — 執行紀錄

任務：為 Fly & Feast HK 的 Facebook 專頁與 Threads 回覆查詢留言，派發網站傳送門。
腳本：`pipeline/engage.py`（預設 dry-run，`--live` 才發送）

## 執行歷史

### 2026-09-15 15:39（首次執行）
- dry-run：掃描 41 則（FB 20 則帖文 + Threads 20 則帖文），準備回覆 **0 則**。
- 略過原因：自家留言 ×32、已回覆過 ×9。無新留言待回覆。
- 依規則（準備回覆 = 0）**未執行 --live**，未對外發送任何內容。
- 憑證正常：兩個平台皆成功讀取帖文與留言，無 API 錯誤。
- 附帶：修正 `engage.py` 內 `build_candidates()` 的死碼（回傳 `scanned, scanned`，
  `candidates` 從未填充），改名為 `collect_comments()` 並只回傳 scanned。已重跑 dry-run 驗證輸出一致。
- 註：同日 14:32–14:36 曾有一次 live 執行（非本自動化），成功回覆 9 則 Threads 留言。
  本輪掃到的「已回覆過 ×9」即為該批。

## 待觀察
- 首輪執行前 engage_state/log 已有資料，本自動化無更早歷史。
- 目前累計回覆 9 則，全部為 Threads，尙無 Facebook 留言被回覆。
