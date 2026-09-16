# hk-deals 專案慣例

## 部署
- 部署用 `pipeline/deploy.sh`（build_site.py + generate_content.py + push_api.py 走 GitHub API）。
- 注意：呢台機直接叫 `bash` 會誤觸 WSL（無 distro 報錯），必須用
  `C:\Users\Administrator\.workbuddy\binaries\PortableGit\versions\1.2.0\bin\bash.exe` 全路徑呼叫。
- `deploy.sh` 內置安全閘：`sample: true` 時拒絕推送（除非 `--force`）。
- 執行前設 `PYTHONIOENCODING=utf-8`。

## SEO／變現設定
- GA4 ID 放 `pipeline/store.json` → `meta.ga4MeasurementId`（G-XXXX…），build 時由
  `build_site.py` 自動注入 index.html（`SEO:GA4` marker 區）；留空則只出佔位註解。
- AdSense pub ID：ca-pub-1777376842974340（index.html + ads.txt）。
- 商戶外流連結（優惠 CTA）用 `rel="noopener sponsored"`；來源連結保持 `rel="noopener nofollow"`。
  `build_site.py render_card` 同 `assets/app.js` 兩處要同步改。

## 流程
- `pipeline/engage.py`：FB/Threads 留言自動回覆（dry-run 預設，--live 先發送；
  三層去重：留言 id、每用戶每日一次、每輪上限）。
- `pipeline/build_site.py`：store.json + drafts → data/deals.json|.js + 靜態預渲染卡片
  + ItemList schema + sitemap.xml + GA4 注入。
- 社群文案（貼文唔放鏈 + 置頂留言放鏈策略）→ outbox/YYYY-MM-DD/。
