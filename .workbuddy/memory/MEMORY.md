# hk-deals 專案慣例

## 部署
- 部署用 `pipeline/deploy.sh`（build_site.py + generate_content.py + push_api.py 走 GitHub API）。
- 注意：呢台機直接叫 `bash` 會誤觸 WSL（無 distro 報錯），必須用
  `C:\Users\Administrator\.workbuddy\binaries\PortableGit\versions\1.2.0\bin\bash.exe` 全路徑呼叫。
- `deploy.sh` 內置安全閘：`sample: true` 時拒絕推送（除非 `--force`）。
- 執行前設 `PYTHONIOENCODING=utf-8`。

## SEO／變現設定
- GA4：G-83BHD7MNDL（資源「Fly & Feast HK」，帳戶 YookDesign；帳戶內另有舊資源「Yook」屬其他站）。
  gtag.js 由 `build_site.py` 依 `meta.ga4MeasurementId` 直接注入，**GTM 容器（GTM-KQVGKZTS）
  內不要再加 GA4 tag，否則雙重計數**。
- GTM 容器：GTM-KQVGKZTS，`meta.gtmContainerId`，build 自動注入 head + noscript（目前容器內無 tag）。
- AdSense pub ID：ca-pub-1777376842974340（index.html + ads.txt）。
- 商戶外流連結（優惠 CTA）用 `rel="noopener sponsored"`；來源連結保持 `rel="noopener nofollow"`。
  `build_site.py render_card` 同 `assets/app.js` 兩處要同步改。

## 流程
- `pipeline/engage.py`：FB/Threads 留言自動回覆（dry-run 預設，--live 先發送；
  三層去重：留言 id、每用戶每日一次、每輪上限）。
  - `--max-posts` 預設 **30**（2026-09-17 由 20 上調）。帖文係按 API 回傳次序切頭 N 則，
    發文頻繁時 20 會滑掉只係 4 日前嘅帖文，令其上嘅新查詢留言被靜默漏掉。
  - 掃描池數字變動時，要先分辨係 **7 日日期窗口**（`--days`/`--comment-days`）
    抑或 **筆數窗口**（`--max-posts`）造成，兩者修法不同。
- `pipeline/build_site.py`：store.json + drafts → data/deals.json|.js + 靜態預渲染卡片
  + ItemList schema + sitemap.xml + GA4 注入。
- 社群文案（貼文唔放鏈 + 置頂留言放鏈策略）→ outbox/YYYY-MM-DD/。
