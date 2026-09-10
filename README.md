# Fly & Feast HK 飛嚐香港

香港出發的機票特價與餐廳優惠情報站。輕量靜態站 + 智能體情報流水線 + 社群自動分發。

```
情報源 → 抓取／核價 → 產出草稿 → 建站 → Facebook / Instagram
```

## 目錄結構

```
hk-deals/
├─ index.html                  網站首頁（單頁應用，資料驅動）
├─ robots.txt                  搜尋引擎指引
├─ sitemap.xml                 站點地圖
├─ CNAME                       GitHub Pages 自訂域名（flyandfeasthk.com）
├─ assets/
│  ├─ style.css                樣式（淺色簡潔風，響應式）
│  └─ app.js                   篩選、排序、搜尋、分享邏輯
├─ data/
│  ├─ deals.json               網站資料（由 build_site.py 產生）
│  └─ deals.js                 同上，包成 <script> 可直接載入的版本
├─ pipeline/
│  ├─ sources.json             情報源清單（rss / agent / api 三種模式）
│  ├─ store.json               主資料庫：已審核的優惠（唯一需要長期維護的檔案）
│  ├─ fetch_deals.py           抓取 RSS 情報源 → raw/
│  ├─ build_site.py            主資料庫 + drafts/ → data/
│  ├─ generate_content.py      產生 FB / IG / 小紅書文案 → outbox/
│  ├─ publish_social.py        透過 Graph API 發佈到 FB 專頁與 Instagram
│  ├─ config.example.json      憑證設定範本
│  ├─ raw/                     每日抓取原始結果（可視為暫存）
│  └─ drafts/                  智能體每日產出的新優惠草稿
└─ outbox/<日期>/              當日待發佈的社群文案
```

## 快速開始

需求：Python 3.10+，無第三方套件。

```bash
cd hk-deals/pipeline

python fetch_deals.py            # 抓 RSS 情報源
python build_site.py             # 產生網站資料
python generate_content.py       # 產生社群文案

cd .. && python -m http.server 8777     # 本地預覽 http://127.0.0.1:8777/
```

日常只需維護 `pipeline/store.json`（正式資料），或在 `pipeline/drafts/` 放當日草稿，
執行 `build_site.py` 就會自動合併、去重、標記狀態並排序。

### 新增一筆優惠（草稿格式）

在 `pipeline/drafts/2026-09-11.json` 放：

```json
{
  "deals": [
    {
      "id": "flight-xxx-20260911",
      "category": "flight",
      "title": "香港 → 沖繩 單程 HK$398 起",
      "subtitle": "來源名稱 / 活動名",
      "route": "香港 HKG → 沖繩 OKA",
      "venue": "餐飲類改用此欄填餐廳與地區",
      "priceLabel": "HK$398 起",
      "priceValue": 398,
      "originalLabel": "原價約 HK$820",
      "discountPct": 51,
      "endsAt": "2026-09-14T23:59:00+08:00",
      "period": "出發期限：2026-10-01 至 2026-12-20",
      "summary": "一到兩句說明這個價位為什麼值得留意。",
      "highlights": ["隱藏條款一", "隱藏條款二"],
      "url": "https://商戶官網",
      "sourceLabel": "來源名稱",
      "sourceUrl": "https://來源網址",
      "tags": ["廉航", "日本"],
      "sample": false
    }
  ]
}
```

必填欄位：`id`、`category`、`title`、`priceLabel`、`endsAt`。
`endsAt` 過期後卡片會自動標記「已結束」，可加 `--drop-expired` 直接剔除。

## 部署（flyandfeasthk.com）

靜態站沒有後端，任何靜態託管都可以：

| 平台 | 做法 |
|------|------|
| Cloudflare Pages | 連接 Git 倉庫，建置指令留空，輸出目錄填 `hk-deals`（推薦：香港訪問延遲低、免費 SSL） |
| GitHub Pages | 把 `hk-deals` 內容推到 `gh-pages` 分支；`CNAME` 檔已備好 `flyandfeasthk.com` |
| Netlify | 直接拖放 `hk-deals` 資料夾 |

**DNS 設定**（在域名商後台）：

- Cloudflare Pages：加一筆 `CNAME`，名稱 `@`，指向 `<專案名>.pages.dev`。
- GitHub Pages：加四筆 `A` 指向 `185.199.108.153 / .109.153 / .110.153 / .111.153`，
  再加一筆 `CNAME`，名稱 `www`，指向 `<你的帳號>.github.io`。

本站已內建 SEO 檔案：`robots.txt`、`sitemap.xml`，以及指向 `flyandfeasthk.com` 的 canonical 與 OG 標籤。
申請 Google Search Console 時直接提交 `https://flyandfeasthk.com/sitemap.xml`。

之後若換域名，記得同步更新這四處：`index.html` 的 canonical 與 `og:url`、`robots.txt`、
`sitemap.xml`、`pipeline/store.json` 的 `meta.siteUrl`，以及 `CNAME`。

## 接上 Facebook / Instagram 自動發帖

1. 建立 Facebook 專頁，並開一個 Instagram 商業帳號、連結到該專頁。
2. 到 [developers.facebook.com](https://developers.facebook.com/) 建立 App（類型選 Business）。
3. 用 Graph API Explorer 取得具備以下權限的權杖：
   `pages_show_list`、`pages_manage_posts`、`pages_read_engagement`、
   `instagram_basic`、`instagram_content_publish`。
   （非管理員身分發帖需要送 App Review。）
4. 用 `GET /me/accounts` 拿到 Page ID 與 Page Access Token。
5. 用 `GET /{page-id}?fields=instagram_business_account` 拿到 IG User ID。
6. 把短期權杖換成**長期權杖**（Page Token 可用 `GET /oauth/access_token?grant_type=fb_exchange_token&...` 延長至約 60 天），
   並設定到期前提醒自己更新。
7. 複製 `pipeline/config.example.json` 為 `pipeline/config.json`，填入上述值。**此檔已被 `.gitignore` 排除，切勿提交。**

發佈：

```bash
cd pipeline
python publish_social.py --manifest ../outbox/2026-09-10/manifest.json              # 先 dry-run 檢查
python publish_social.py --manifest ../outbox/2026-09-10/manifest.json --live       # 確認後才真正發佈
```

限制說明：

- **Instagram 必須有公開圖片網址**（`imageUrl`），沒有填就會自動略過。
  建議為每筆優惠配一張 1080×1350 的圖，放在 `data/images/` 並用站點網址引用。
- **小紅書沒有開放接口**，`outbox/<日期>/xiaohongshu.md` 是給你複製貼上用的。
- 同一優惠不要在同日重複發佈，`config.json` 的 `posting` 段有建議頻率。

## 變現

這類站的核心收入是**聯盟佣金**，不是廣告：

- **Agoda / Booking 聯盟**：酒店訂單佣金，香港市場主力。
- **Klook / Trip.com 聯盟**：餐飲券、活動票券，正好對應你的餐飲內容線。
- **Travelpayouts**：機票與酒店聚合，適合補齊機票數據。
- 申請通過後在 `config.json` 的 `affiliate` 段填入 ID，再到 `store.json` 的 `url` 欄位
  加上追蹤參數（例如 `?cid=YOURID`），或寫個小腳本在 `build_site.py` 輸出時統一附加。

引流價值：優惠站的自然流量可以導向你現有的室內設計與風水諮詢業務——
在「關於本站」放一條軟性連結，比硬銷有效得多。

## 合規與免責

- 只抓取**公開**的促銷頁、RSS 與聯盟資料，不繞過反爬機制、不破解任何登入牆。
- 每筆優惠都必須保留原始來源連結，讓讀者可自行核實。
- 所有輸出都帶免責聲明，價格與名額一律註明「以商戶官方公佈為準」。
- 聯盟連結需明確揭露（頁面已在「關於本站」聲明）。
- 示範資料期間請保留黃色提示條；接入真實情報後在 `store.json` 把 `meta.sample` 設為 `false`。

## 下一步建議

1. 申請 Agoda 與 Klook 聯盟帳號，這是收入的前提。
2. 建立 Facebook 專頁與 Instagram 商業帳號，接上發帖權杖。
3. 為每筆優惠準備配圖（目前 `image` 欄位留空，IG 發帖需要）。
4. 持續觀察哪些優惠帶來最多點擊，把 `store.json` 的內容重心往那邊移。
