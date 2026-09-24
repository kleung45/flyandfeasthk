#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生多頁內容：優惠詳情頁、分類頁、攻略頁、合規頁，並輸出完整 sitemap.xml。

動機
----
AdSense 對「單頁聚合站 + 無隱私政策 + 大量外連」的審核向來嚴格。把每筆優惠拆成
獨立 URL、每頁附上由資料推導的編輯分析，再加上合規頁與完整站內導覽，網站才符合
「有增值的原創內容」門檻，同時保留每日自動產生的流水線。

輸入
----
data/deals.json（由 build_site.py 產生，含 meta 與裝飾後的 deals）

輸出
----
deals/<id>/index.html          每筆優惠獨立頁
deals/index.html               優惠總覽
deals/<flight|dining|hotel>/   分類頁
guides/index.html              攻略總覽
guides/<slug>/index.html       攻略文章
about|contact|privacy|terms/index.html   合規頁
sitemap.xml                    收錄以上全部 URL

用法
----
    python build_pages.py
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
DATA = PROJECT / "data"
STORE = ROOT / "store.json"
JAPAN_FILE = ROOT / "japan.json"
SITEMAP = PROJECT / "sitemap.xml"

# 日本美食專欄：城市顯示次序（未列出的城市按首次出現排在後面）
JAPAN_CITY_ORDER = ["東京", "大阪", "京都", "神戶", "名古屋", "橫濱", "福岡", "札幌", "沖繩"]

HK_TZ = timezone(timedelta(hours=8))
SITE_FALLBACK = "https://www.flyandfeasthk.com"

# 對外聯絡資料：如要更改，只改這裡。
CONTACT = {
    "brand": "Fly & Feast HK 飛嚐香港",
    "whatsapp": "+852 5545 1490",
    "whatsapp_url": "https://wa.me/85255451490",
    "email": "keith@ooowls.com",
    "facebook": "https://www.facebook.com/profile.php?id=1281889241677837",
    "facebook_label": "Flyandfeasthk",
}

CAT_LABEL = {"flight": "機票特價", "dining": "餐廳優惠", "hotel": "酒店優惠"}
CAT_ICON = {"flight": "✈️", "dining": "🍜", "hotel": "🏨"}
CAT_DESC = {
    "flight": "香港出發的機票特價、廉航閃促與一口價機票，全部為來回連稅或明確淨價，並註明適用旅遊日期與行李安排。",
    "dining": "香港餐廳、酒店自助餐與放題優惠，只收錄有明確折扣、明確期限與可查證官方報價的項目。",
    "hotel": "香港酒店住宿與酒店餐飲優惠，附適用日期、房型或餐飲時段與條款提醒。",
}
CAT_SLUG = {"flight": "flight", "dining": "dining", "hotel": "hotel"}

# 平台辨識：由 url 或 sourceLabel 判斷落單渠道
PLATFORMS = [
    ("klook.com", "Klook"),
    ("kkday.com", "KKday"),
    ("space.hk01.com", "01空間"),
    ("hk01.com", "香港01"),
    ("s.openrice.com", "OpenRice"),
    ("openrice.com", "OpenRice"),
    ("eshop.harbour-plaza.com", "海逸酒店官方網上商店"),
    ("sheratontungchungshop.com", "酒店官方網上商店"),
    ("shangri-la.com", "酒店官網"),
    ("parkhotelgroup.com", "酒店官網"),
    ("harbour-plaza.com", "酒店官網"),
    ("fave.co", "Fave"),
    ("groupbuya.com", "GroupBuya"),
    ("wingontravel.com", "永安旅遊 App"),
]

# 條款訊號：關鍵詞組 → 提醒文字
# 註：服務費寫法（已包 vs 另收）另外單獨處理，因為同一筆優惠可能兩種寫法並存。
TERM_SIGNALS = [
    (("現金",), "現場須以現金付款，記得預備足夠現鈔。"),
    (("名額", "限量", "售完", "額滿", "售罄", "先到先得"),
     "屬名額制、售完即止，揀到合適日期建議即刻落單。"),
    (("小童", "長者", "兒童", "歲"),
     "小童、長者或指定年齡層另有折扣安排，未必與成人同價。"),
    (("訂金",), "須先付訂金才完成預留，取消安排要另外確認。"),
    (("提前", "預早"), "須提前預訂，臨時訂位未必有位。"),
    (("不適用", "除外", "公眾假期"), "有指定日子不適用，訂之前對清楚日曆。"),
    (("App", "手機應用", "應用程式"), "須以指定 App 或指定帳戶下單，未裝的話要先準備。"),
    (("Visa", "Mastercard", "指定信用卡", "信用卡"),
     "付款方式有限制，須以指定發卡機構或卡種付款。"),
    (("不可與其他優惠", "不能與其他優惠", "不適用於其他折扣"),
     "不可與其他優惠同時使用，唔好預算疊加折扣。"),
    (("只限堂食", "不設外賣"), "只限堂食，外賣或外送未必適用。"),
    (("必須", "須出示"), "有身分或憑證要求，現場須出示相關證明。"),
]


# --------------------------------------------------------------------------
# 基礎工具
# --------------------------------------------------------------------------

def esc(value) -> str:
    s = "" if value is None else str(value)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def hk_num(value: float) -> str:
    """HK$1,126 這種格式；有小數就保留。"""
    if value is None:
        return ""
    if abs(value - round(value)) < 0.05:
        return f"HK${int(round(value)):,}"
    return f"HK${value:,.1f}"


def money_in(text: str) -> list[float]:
    out = []
    for m in re.finditer(r"HK\$\s*([\d][\d,]*(?:\.\d+)?)", text or ""):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def per_head(deal: dict) -> float | None:
    """抓出每人／每單位成本。

    優先使用 priceValue —— 這是編輯在收錄時已核定的頭條人均價，
    比自動抽取可靠。只有在 priceValue 從缺時，才回退到由標價文字抽取：
    依次比對「人均 HK$X」、「HK$X／位」、「HK$X／N 位」（自行除以人數）。
    抽取前會剔走小童／長者價的片段，避免誤取最低價。
    """
    pv = deal.get("priceValue")
    if isinstance(pv, (int, float)) and pv > 0:
        return float(pv)

    blob = " ".join(
        str(deal.get(k) or "")
        for k in ("priceLabel", "originalLabel", "subtitle", "summary")
    )
    frags = re.split(r"[、，,。；;！!？?]", blob)
    kept = [f for f in frags if not re.search(r"小童|長者|兒童|歲|幼童", f)]
    blob = " ".join(kept) if kept else blob
    cands: list[float] = []

    for v in re.findall(r"人均\s*(?:約\s*|低至\s*)?HK\$\s*([\d][\d,]*(?:\.\d+)?)", blob):
        cands.append(float(v.replace(",", "")))
    for v in re.findall(r"HK\$\s*([\d][\d,]*(?:\.\d+)?)\s*[／/]\s*位", blob):
        cands.append(float(v.replace(",", "")))
    for total, count in re.findall(
        r"HK\$\s*([\d][\d,]*(?:\.\d+)?)\s*[／/]\s*(\d+)\s*位", blob
    ):
        n = int(count)
        if n > 0:
            cands.append(float(total.replace(",", "")) / n)

    return min(cands) if cands else None


def fold_label(pct) -> str | None:
    """省 50% → 5 折。"""
    if not pct:
        return None
    zhe = (100 - float(pct)) / 10
    if zhe <= 1.05:
        return "1 折"
    if abs(zhe - round(zhe)) < 0.05:
        return f"{int(round(zhe))} 折"
    return f"{zhe:.1f} 折"


def detect_platform(deal: dict) -> str:
    for key, name in PLATFORMS:
        if key.lower() in str(deal.get("url") or "").lower():
            return name
    src = str(deal.get("sourceLabel") or "")
    for key, name in PLATFORMS:
        if key.split(".")[0] in src.lower():
            return name
    if "官網" in src or "官方" in src:
        return "商戶官方渠道"
    return "商戶官方或指定平台"


def tag_overlap(a: dict, b: dict) -> int:
    """兩個優惠共用幾個標籤。用來判斷『同類』是否真的可比。"""
    ta = {str(t).strip() for t in (a.get("tags") or []) if str(t).strip()}
    tb = {str(t).strip() for t in (b.get("tags") or []) if str(t).strip()}
    return len(ta & tb)


def ends_text(deal: dict) -> str:
    raw = deal.get("endsAt") or ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if not m:
        return "未標示"
    return f"{m.group(1)} 年 {int(m.group(2))} 月 {int(m.group(3))} 日"


def status_chip(deal: dict) -> str:
    st = deal.get("status")
    if st == "expired":
        return "已結束"
    d = deal.get("daysLeft")
    if st == "ending":
        if d == 0:
            return "今日結束"
        if d == 1:
            return "明日結束"
        return f"剩 {d} 日"
    if isinstance(d, int):
        return f"剩 {d} 日"
    return "進行中"


# --------------------------------------------------------------------------
# 編輯觀點：由既有資料推導，內容隨數據變化
# --------------------------------------------------------------------------

def editorial_blocks(deal: dict, peers: list[dict]) -> list[tuple[str, list[str], list[str]]]:
    """回傳 [(小標題, 段落清單, 列點清單), ...]。"""
    blocks: list[tuple[str, list[str], list[str]]] = []

    blob = " ".join(str(deal.get(k) or "") for k in
                    ("priceLabel", "originalLabel", "period", "summary"))
    blob += " " + " ".join(str(h) for h in (deal.get("highlights") or []))
    pv = per_head(deal)
    pct = deal.get("discountPct")
    cat = deal.get("category")
    unit = "每位" if cat == "dining" else ("每張" if cat == "flight" else "每間")

    # 1) 價錢點計
    paras, bullets = [], []
    price_text = str(deal.get("priceLabel") or "").strip()
    if price_text:
        bullets.append(f"標示價：{price_text}")
    orig = str(deal.get("originalLabel") or "").strip()
    if orig:
        bullets.append(f"原價對照：{orig}")
    if pv is not None:
        bullets.append(f"折算人均／單位成本約 {hk_num(pv)}（{unit}）")
    fold = fold_label(pct)
    if fold:
        bullets.append(f"折扣幅度約 {fold}（官方標示省 {pct}%）")
    if not bullets:
        bullets.append("此筆未標示明確價格，建議直接到商戶頁面確認。")
    paras.append(
        "以下數字全部按商戶頁面標示的價格直接抄錄，沒有加工或估算。"
        if bullets else ""
    )
    blocks.append(("價錢點計", [p for p in paras if p], bullets))

    # 2) 點訂最抵
    plat = detect_platform(deal)
    paras2 = []
    paras2.append(
        f"這筆優惠經**{plat}**下單。" if plat != "商戶官方或指定平台"
        else "這筆優惠的落單渠道未在來源中明確標示，建議先到商戶官方頁面核實。"
    )
    if "官網" in plat or "官方" in plat:
        paras2.append("走商戶官方渠道通常最少一層中間人，遇到爭議時追討也直接些。")
    else:
        paras2.append("第三方平台的價格與名額以結帳頁為準，落到付款頁請再對一次總額。")
    period = str(deal.get("period") or "").strip()
    if period:
        paras2.append(f"期限：{period}")
    if deal.get("status") == "expired":
        paras2.append("注意：此優惠已結束，本頁僅作紀錄，請到商戶頁面查找現行方案。")
    blocks.append(("點訂最抵", paras2, []))

    # 3) 要留意的條款
    hits = []
    svc_incl = any(k in blob for k in ("已包", "已連", "已含", "已包括"))
    svc_excl = any(k in blob for k in ("另收", "未連", "未含", "另計", "須另付", "另外收費"))
    if svc_incl and svc_excl:
        hits.append(
            "價錢寫法混合：優惠方案本身已包服務費，但原價比較或後備方案要另收加一——"
            "落單時要認清自己揀的是哪一個方案。"
        )
    elif svc_incl:
        hits.append("標示價已包含服務費，實付金額與標價一致，計預算時唔需要再另加。")
    elif svc_excl:
        hits.append("標示價未包含全部服務費或附加費，落單前要看清結帳頁的實付總額。")
    for keys, note in TERM_SIGNALS:
        if any(k in blob for k in keys):
            hits.append(note)
    seen = set()
    hits = [h for h in hits if not (h in seen or seen.add(h))]
    if not hits:
        hits = ["來源資料未列出特別限制條款；但仍以商戶官方公佈的條款為準。"]
    blocks.append(("要留意的條款", [], hits))

    # 4) 適合邊種場合
    paras4 = []
    if cat == "dining":
        if pv is None:
            paras4.append("價位未明確，難以判斷是否划算，建議先比對商戶原價。")
        elif pv < 150:
            paras4.append(f"人均約 {hk_num(pv)}，屬日常價位，適合平日收工想食好少少、又唔想計太盡的飯局。")
        elif pv < 300:
            paras4.append(f"人均約 {hk_num(pv)}，屬週末小確幸價位，兩個人或三四人聚餐都容易承擔。")
        elif pv < 550:
            paras4.append(f"人均約 {hk_num(pv)}，適合家庭聚會、生日飯等要有體面又唔想爆預算的場合。")
        else:
            paras4.append(f"人均約 {hk_num(pv)}，屬節慶或請客級別，重點在菜式質素與環境，唔係單純鬥平。")
    elif cat == "flight":
        route = deal.get("route") or ""
        paras4.append(
            f"航線：{route}。" if route else "航線資料未標示，請到航空公司或代理頁面確認。"
        )
        paras4.append("機票類優惠最緊要對清楚是否『來回連稅』、包不包寄艙行李，以及可否改期；"
                      "標價便宜但行李費另加，實際未必最抵。")
    else:
        paras4.append("酒店類優惠要同時看房型、入住日期限制與是否含餐飲，"
                      "標價低但限制多，實際可用性會差很遠。")
    tags = [str(t) for t in (deal.get("tags") or [])]
    if tags:
        paras4.append("標籤：" + "、".join(tags) + "。")
    blocks.append(("適合邊種場合", paras4, []))

    # 5) 同類點揀：優先比較標籤重疊的項目（同屬自助餐、同區之類），
    #    標籤全無重疊時才退回整個類別，避免拿火鍋放題去比茶餐廳碟頭飯。
    paras5 = []
    same = [p for p in peers
            if p.get("category") == cat
            and p.get("id") != deal.get("id")
            and p.get("status") != "expired"]
    with_pv = [p for p in same if per_head(p) is not None]
    themed = [p for p in with_pv if tag_overlap(deal, p) > 0]
    basis = themed or with_pv
    basis_name = "標籤相近的" if themed else "同類"

    if pv is not None and basis:
        by_price = sorted(basis, key=lambda p: per_head(p))
        cheaper = [p for p in by_price if per_head(p) < pv - 0.5]
        if not cheaper:
            paras5.append(
                f"在現時收錄 {len(basis) + 1} 筆{basis_name}優惠中，"
                f"這筆的{unit}成本屬最低一批。"
            )
        else:
            paras5.append(
                f"在現時收錄的{basis_name}優惠中，有 {len(cheaper)} 筆的{unit}成本比這筆更低，"
                "如果只以價錢行先，值得一併比較。"
            )
        # 標籤相近的項目夠多時，就只列這些，不混入其他類型
        near_pool = themed if len(themed) >= 2 else basis
        near = sorted(near_pool, key=lambda p: (-tag_overlap(deal, p), abs(per_head(p) - pv)))[:3]
        lines = []
        for p in near:
            title = re.sub(r"\s+", " ", str(p.get("title") or ""))[:44]
            lines.append(f"{title}（{hk_num(per_head(p))}／{unit}）")
        paras5.append("價位最接近的選擇：" + "；".join(lines) + "。")
    else:
        paras5.append("同類可比較的價格資料不足，暫未能提供橫向對比。")
    paras5.append("以上比較只按本頁收錄的資料計算，不代表市面上全部選擇。")
    blocks.append(("同類點揀", paras5, []))

    return blocks


def editorial_html(deal: dict, peers: list[dict]) -> str:
    blocks = editorial_blocks(deal, peers)
    parts = [
        '<section class="editorial" aria-labelledby="ed-title">',
        '<h2 id="ed-title">🧾 編輯觀點 <span class="ed-cat">由優惠資料逐項推導，非商戶文案轉載</span></h2>',
    ]
    for title, paras, bullets in blocks:
        parts.append(f"<h3>{esc(title)}</h3>")
        for p in paras:
            # 支援 **粗體**
            body = esc(p).replace("**", "\x00")
            body = re.sub(r"\x00(.+?)\x00", r"<strong>\1</strong>", body)
            parts.append(f"<p>{body}</p>")
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>")
    parts.append(
        f'<p class="ed-foot">本頁由 Fly &amp; Feast HK 編輯部依商戶公開資料整理與核對，'
        f'最後核對日期見頁首。價格、名額與條款隨時變動，一切以商戶官方公佈為準。</p>'
    )
    parts.append("</section>")
    return "".join(parts)


# --------------------------------------------------------------------------
# 共用版式
# --------------------------------------------------------------------------

def nav_html(active: str) -> str:
    items = [
        ("/", "首頁", "home"),
        ("/deals/", "全部優惠", "deals"),
        ("/deals/flight/", "機票特價", "flight"),
        ("/deals/dining/", "餐廳優惠", "dining"),
        ("/deals/hotel/", "酒店優惠", "hotel"),
        ("/japan/", "日本美食", "japan"),
        ("/guides/", "優惠攻略", "guides"),
        ("/about/", "關於本站", "about"),
    ]
    chunks = []
    for href, label, key in items:
        cur = ' aria-current="page"' if key == active else ""
        chunks.append(f'<a href="{href}"{cur}>{esc(label)}</a>')
    return '<nav class="nav" aria-label="主導覽">' + "".join(chunks) + "</nav>"


def header_html(active: str) -> str:
    return (
        '<header class="site-header">'
        '<div class="wrap header-inner">'
        '<a class="brand" href="/">'
        '<img class="brand-mark" src="/assets/logo-mark.png" alt="Fly &amp; Feast HK 標誌" width="52" height="52">'
        '<span class="brand-text"><strong>Fly &amp; Feast HK</strong><small>飛嚐香港</small></span>'
        "</a>"
        + nav_html(active)
        + "</div></header>"
    )


def footer_html() -> str:
    return (
        '<footer class="site-footer">'
        '<div class="wrap footer-inner">'
        "<div>"
        '<img class="footer-logo" src="/assets/logo-mark.png" alt="" width="44" height="44">'
        "<strong>Fly &amp; Feast HK</strong>"
        "<p>香港出發的機票特價與餐廳優惠情報</p>"
        "</div>"
        '<div class="footer-links">'
        '<a href="/deals/">全部優惠</a>'
        '<a href="/deals/flight/">機票特價</a>'
        '<a href="/deals/dining/">餐廳優惠</a>'
        '<a href="/deals/hotel/">酒店優惠</a>'
        '<a href="/japan/">日本美食</a>'
        '<a href="/guides/">優惠攻略</a>'
        "</div>"
        '<div class="footer-links">'
        '<a href="/about/">關於本站</a>'
        '<a href="/contact/">聯絡我們</a>'
        '<a href="/privacy/">隱私政策</a>'
        '<a href="/terms/">免責聲明</a>'
        "</div>"
        "</div>"
        '<div class="wrap footer-bottom">'
        f'<p>© {datetime.now(HK_TZ).year} Fly &amp; Feast HK · '
        "本頁優惠資訊僅供參考，一切以商戶官方公佈為準。"
        f'部分連結為聯盟連結，詳見<a href="/terms/">免責聲明</a>。</p>'
        "</div></footer>"
    )


def breadcrumb_html(trail: list[tuple[str, str]]) -> str:
    """trail: [(label, href|None)]，第一項固定為首頁。"""
    parts = ['<nav class="crumb wrap" aria-label="麵包屑">']
    parts.append('<a href="/">首頁</a>')
    for label, href in trail:
        parts.append('<span aria-hidden="true">›</span>')
        if href:
            parts.append(f'<a href="{href}">{esc(label)}</a>')
        else:
            parts.append(f'<span aria-current="page">{esc(label)}</span>')
    parts.append("</nav>")
    return "".join(parts)


def breadcrumb_ld(trail: list[tuple[str, str]], site: str) -> dict:
    items = [{"@type": "ListItem", "position": 1, "name": "首頁", "item": site + "/"}]
    for i, (label, href) in enumerate(trail, 2):
        entry = {"@type": "ListItem", "position": i, "name": label}
        if href:
            entry["item"] = site + href
        items.append(entry)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def layout(
    *,
    title: str,
    desc: str,
    path: str,
    body: str,
    meta: dict,
    active: str = "",
    ld: list[dict] | None = None,
) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    canonical = site + path
    ga4 = (meta.get("ga4MeasurementId") or "").strip()
    gtm = (meta.get("gtmContainerId") or "").strip()

    head_extra = ""
    if ga4 and re.match(r"^G-[A-Z0-9]{6,15}$", ga4, re.IGNORECASE):
        head_extra += (
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={esc(ga4)}"></script>\n'
            "<script>window.dataLayer=window.dataLayer||[];"
            "function gtag(){dataLayer.push(arguments);}"
            f"gtag('js',new Date());gtag('config','{esc(ga4)}');</script>\n"
        )
    if gtm and re.match(r"^GTM-[A-Z0-9]{5,12}$", gtm, re.IGNORECASE):
        head_extra += (
            "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':"
            "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],"
            "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src="
            "'https://www.googletagmanager.com/gtm.js?id='+i+dl;"
            f"f.parentNode.insertBefore(j,f);}})(window,document,'script','dataLayer','{gtm}');</script>\n"
        )

    ld_html = ""
    for item in (ld or []):
        ld_html += (
            '<script type="application/ld+json">\n'
            + json.dumps(item, ensure_ascii=False, indent=2)
            + "\n</script>\n"
        )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-Hant-HK">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n"
        f'<meta name="description" content="{esc(desc)}">\n'
        f'<link rel="canonical" href="{esc(canonical)}">\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:site_name" content="Fly &amp; Feast HK">\n'
        f'<meta property="og:title" content="{esc(title)}">\n'
        f'<meta property="og:description" content="{esc(desc)}">\n'
        f'<meta property="og:url" content="{esc(canonical)}">\n'
        '<meta property="og:image" content="' + site + '/assets/og-cover.png">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        '<link rel="icon" type="image/png" href="/assets/logo-mark.png">\n'
        '<link rel="stylesheet" href="/assets/style.css">\n'
        '<link rel="stylesheet" href="/assets/pages.css">\n'
        + head_extra
        + ld_html
        + "</head>\n<body>\n"
        + header_html(active)
        + body
        + footer_html()
        + "\n</body>\n</html>\n"
    )


def card_html(deal: dict, link_local: bool = True) -> str:
    """沿用首頁卡片的樣式，但標題連到站內詳情頁。"""
    url = f"/deals/{esc(deal['id'])}/"
    cat = deal.get("category", "")
    badge = f'<span class="badge badge-{esc(cat) if cat in CAT_SLUG else "hotel"}">{esc(CAT_LABEL.get(cat, "優惠"))}</span>'
    chip = status_chip(deal)
    if deal.get("status") == "expired":
        chip_html = '<span class="badge badge-expired">已結束</span>'
    elif deal.get("status") == "ending":
        chip_html = f'<span class="badge badge-urgent">{esc(chip)}</span>'
    else:
        chip_html = ""
    sticker_cls = {"flight": "st-flight", "dining": "st-dining", "hotel": "st-hotel"}.get(cat, "st-hotel")
    route = deal.get("route") or deal.get("venue") or ""
    save = f'<span class="save">省 {esc(deal["discountPct"])}%</span>' if deal.get("discountPct") else ""
    hl = ""
    if deal.get("highlights"):
        hl = "<ul>" + "".join(f"<li>{esc(h)}</li>" for h in deal["highlights"][:4]) + "</ul>"
    src = ""
    if deal.get("sourceLabel"):
        label = esc(deal["sourceLabel"])
        if deal.get("sourceUrl"):
            label = f'<a href="{esc(deal["sourceUrl"])}" target="_blank" rel="noopener nofollow">{label}</a>'
        src = f'<p class="source">來源：{label}</p>'
    cta = (
        '<span class="period">優惠已結束</span>'
        if deal.get("status") == "expired"
        else f'<a class="link-btn" href="{url}">睇詳情與條款 →</a>'
    )
    return (
        f'<article class="card{" is-expired" if deal.get("status") == "expired" else ""}" data-id="{esc(deal["id"])}">'
        f'<div class="card-top">{badge}{chip_html}<span class="card-sticker {sticker_cls}" aria-hidden="true">{CAT_ICON.get(cat, "🎁")}</span></div>'
        f'<h3><a href="{url}">{esc(deal.get("title"))}</a></h3>'
        + (f'<p class="sub">{esc(deal["subtitle"])}</p>' if deal.get("subtitle") else "")
        + (f'<p class="route">{esc(route)}</p>' if route else "")
        + '<div class="price-row">'
        f'<span class="price">{esc(deal.get("priceLabel") or "")}</span>'
        + (f'<span class="price-was">{esc(deal["originalLabel"])}</span>' if deal.get("originalLabel") else "")
        + save
        + "</div>"
        + (f'<p class="summary">{esc(deal["summary"])}</p>' if deal.get("summary") else "")
        + hl
        + f'<div class="card-foot"><span class="period">{esc(deal.get("period") or chip)}</span>'
        f'<span class="actions">{cta}</span></div>'
        + src
        + "</article>"
    )


def grid_html(deals: list[dict]) -> str:
    if not deals:
        return '<p class="empty">現時未有符合條件的優惠。</p>'
    return '<div class="grid">' + "".join(card_html(d) for d in deals) + "</div>"


# --------------------------------------------------------------------------
# 各頁產生
# --------------------------------------------------------------------------

def build_deal_page(deal: dict, peers: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    cat = deal.get("category", "")
    cat_label = CAT_LABEL.get(cat, "優惠")
    cat_slug = CAT_SLUG.get(cat, "hotel")
    url = f"/deals/{deal['id']}/"
    updated = str(meta.get("updated") or "")[:10]
    pv = per_head(deal)
    plat = detect_platform(deal)

    # 相關優惠：同類 + 標籤相近 + 價位接近，排除自己
    same = [p for p in peers
            if p.get("id") != deal.get("id")
            and p.get("category") == cat
            and p.get("status") != "expired"]
    base_price = pv if pv is not None else 1e9
    same.sort(key=lambda p: (
        -tag_overlap(deal, p),
        abs((per_head(p) if per_head(p) is not None else 1e9) - base_price),
    ))
    related = same[:3]
    if len(related) < 3:
        extra = [p for p in peers
                 if p.get("id") != deal.get("id")
                 and p not in related
                 and p.get("status") != "expired"]
        related += extra[: 3 - len(related)]

    facts = []
    venue = deal.get("venue") or deal.get("route")
    if venue:
        facts.append(("地點／航線", venue))
    if pv is not None:
        facts.append(("折算成本", f"{hk_num(pv)}（{'每位' if cat == 'dining' else '每單位'}）"))
    facts.append(("下單渠道", plat))
    facts.append(("優惠期限", ends_text(deal)))
    facts.append(("現況", status_chip(deal)))
    facts.append(("最後核對", updated))
    facts_html = "".join(
        f'<div class="deal-fact"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in facts
    )

    hl_html = ""
    if deal.get("highlights"):
        hl_html = (
            '<h2 class="section-h2">📋 優惠內容</h2><ul>'
            + "".join(f"<li>{esc(h)}</li>" for h in deal["highlights"])
            + "</ul>"
        )

    terms_html = ""
    if deal.get("period") or deal.get("priceLabel"):
        rows = []
        if deal.get("period"):
            rows.append(("適用期限", deal["period"]))
        if deal.get("priceLabel"):
            rows.append(("價格與收費", deal["priceLabel"]))
        if deal.get("originalLabel"):
            rows.append(("原價對照", deal["originalLabel"]))
        if venue:
            rows.append(("地點", venue))
        terms_html = (
            '<section class="terms-box"><h2>⚠️ 條款與收費一覽</h2><dl>'
            + "".join(
                f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in rows
            )
            + "</dl></section>"
        )

    cta = ""
    if deal.get("status") != "expired" and deal.get("url"):
        cta = (
            '<div class="deal-actions">'
            f'<a class="link-btn" href="{esc(deal["url"])}" target="_blank" rel="noopener sponsored">'
            "前往商戶頁面查看 →</a>"
            f'<a class="btn-ghost" href="/deals/{esc(cat_slug)}/">睇更多{esc(cat_label)}</a>'
            "</div>"
        )
    else:
        cta = (
            '<div class="deal-actions">'
            f'<a class="btn-ghost" href="/deals/{esc(cat_slug)}/">睇現行{esc(cat_label)}</a>'
            "</div>"
        )

    src = ""
    if deal.get("sourceLabel") or deal.get("sourceUrl"):
        src = (
            '<div class="source-block"><p><strong>原始來源：</strong>'
            + (
                f'<a href="{esc(deal["sourceUrl"])}" target="_blank" rel="noopener nofollow">'
                f'{esc(deal.get("sourceLabel") or deal["sourceUrl"])}</a>'
                if deal.get("sourceUrl")
                else esc(deal.get("sourceLabel"))
            )
            + "</p><p>本頁價格、名額與條款全部抄錄自商戶或媒體公開資料，"
            "未經任何加工。優惠隨時變動或售罄，一切以商戶官方公佈為準。</p></div>"
        )

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("全部優惠", "/deals/"), (cat_label, f"/deals/{cat_slug}/"), (deal.get("title", ""), None)])
        + '<article>'
        '<div class="deal-hero">'
        f'<div class="card-top"><span class="badge badge-{esc(cat_slug)}">{esc(cat_label)}</span>'
        + (
            f'<span class="badge badge-urgent">{esc(status_chip(deal))}</span>'
            if deal.get("status") == "ending"
            else ""
        )
        + "</div>"
        f"<h1>{esc(deal.get('title'))}</h1>"
        + (f'<p class="lede-line">{esc(deal["subtitle"])}</p>' if deal.get("subtitle") else "")
        + '<div class="price-panel">'
        f'<span class="p-now">{esc(deal.get("priceLabel") or "價格以商戶頁面為準")}</span>'
        + (f'<span class="p-was">{esc(deal["originalLabel"])}</span>' if deal.get("originalLabel") else "")
        + (f'<span class="p-save">省 {esc(deal["discountPct"])}%</span>' if deal.get("discountPct") else "")
        + '<span class="p-note">價格與名額以商戶官方頁面即時顯示為準。</span>'
        "</div>"
        f'<dl class="deal-facts">{facts_html}</dl>'
        "</div>"
        + (f'<h2 class="section-h2">📖 優惠簡介</h2><p>{esc(deal.get("summary"))}</p>' if deal.get("summary") else "")
        + "<div>" + editorial_html(deal, peers) + "</div>"
        + hl_html
        + terms_html
        + cta
        + src
        + "</article>"
        + (
            '<section class="related"><h2 class="section-h2">🔎 相關優惠</h2>'
            '<p class="section-note">與本筆同類、價位最接近的項目。</p>'
            + grid_html(related)
            + "</section>"
        )
        + "</main>"
    )

    ld = [
        breadcrumb_ld([("全部優惠", "/deals/"), (cat_label, f"/deals/{cat_slug}/"), (deal.get("title", ""), None)], site),
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": deal.get("title"),
            "description": deal.get("summary") or deal.get("subtitle") or "",
            "inLanguage": "zh-Hant-HK",
            "dateModified": str(meta.get("updated") or ""),
            "author": {"@type": "Organization", "name": "Fly & Feast HK 編輯部"},
            "publisher": {"@type": "Organization", "name": "Fly & Feast HK"},
            "mainEntityOfPage": {"@type": "WebPage", "@id": site + url},
        },
    ]
    if deal.get("url") and isinstance(deal.get("priceValue"), (int, float)):
        offer = {
            "@context": "https://schema.org",
            "@type": "Offer",
            "name": deal.get("title"),
            "url": deal.get("url"),
            "price": deal.get("priceValue"),
            "priceCurrency": "HKD",
            "availabilityEnds": deal.get("endsAt"),
            "seller": {"@type": "Organization", "name": deal.get("sourceLabel") or "商戶"},
        }
        ld.append(offer)

    return layout(
        title=f"{deal.get('title')}｜{cat_label}｜Fly & Feast HK",
        desc=(deal.get("summary") or deal.get("subtitle") or str(deal.get("title")))[:155],
        path=url,
        body=body,
        meta=meta,
        active=cat_slug,
        ld=ld,
    )


def build_deals_index(deals: list[dict], meta: dict) -> str:
    live = [d for d in deals if d.get("status") != "expired"]
    expired = [d for d in deals if d.get("status") == "expired"]
    stats = meta.get("stats") or {}
    counts = {c: sum(1 for d in live if d.get("category") == c) for c in CAT_LABEL}
    nav = "".join(
        f'<a href="/deals/{CAT_SLUG[c]}/">{CAT_ICON[c]} {esc(CAT_LABEL[c])}（{counts[c]}）</a>'
        for c in ("flight", "dining", "hotel")
    )
    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("全部優惠", None)])
        + '<div class="page-head">'
        "<h1>香港優惠總覽：機票特價、餐廳與酒店優惠</h1>"
        '<p class="page-lede">這一頁收錄 Fly &amp; Feast HK 現時全部的優惠紀錄，'
        "每筆都有獨立的詳情頁，列出價格、期限、條款提醒、下單渠道與原始來源連結。"
        "收錄標準是「有明確官方報價、有明確期限、找得到原始出處」，查不到價格的一律不收。</p>"
        f'<div class="page-meta"><span>進行中：<b>{len(live)}</b> 筆</span>'
        f'<span>三日內結束：<b>{stats.get("ending", 0)}</b> 筆</span>'
        f'<span>歷史紀錄：<b>{len(expired)}</b> 筆</span>'
        f'<span>最後更新：<b>{esc(str(meta.get("updated") or "")[:10])}</b></span></div>'
        f'<div class="cat-nav">{nav}</div>'
        "</div>"
        '<h2 class="section-h2">✅ 進行中優惠</h2>'
        + grid_html(live)
        + (
            '<h2 class="section-h2">🗂 已結束優惠（僅作紀錄）</h2>'
            '<p class="section-note">這些優惠的預訂期或使用期已過，保留作價格參考；'
            "請注意現行方案未必相同。</p>"
            + grid_html(expired)
            if expired else ""
        )
        + "</main>"
    )
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    return layout(
        title="香港優惠總覽：機票特價、餐廳與酒店優惠｜Fly & Feast HK",
        desc=f"現時收錄 {len(live)} 筆香港進行中優惠，涵蓋機票特價、餐廳與酒店自助餐，"
             "每筆附價格、期限、條款提醒與原始來源連結。",
        path="/deals/",
        body=body,
        meta=meta,
        active="deals",
        ld=[breadcrumb_ld([("全部優惠", None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": "香港優惠總覽", "inLanguage": "zh-Hant-HK"}],
    )


def build_category_page(cat: str, deals: list[dict], meta: dict) -> str:
    live = [d for d in deals if d.get("category") == cat and d.get("status") != "expired"]
    expired = [d for d in deals if d.get("category") == cat and d.get("status") == "expired"]
    label = CAT_LABEL[cat]
    icon = CAT_ICON[cat]
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")

    # 焦點排行：有折扣的優先，再按人均成本
    ranked = sorted(
        live,
        key=lambda d: (-(d.get("discountPct") or 0), per_head(d) if per_head(d) is not None else 1e9),
    )[:3]
    rank_html = ""
    for i, d in enumerate(ranked, 1):
        why = []
        if d.get("discountPct"):
            f = fold_label(d["discountPct"])
            why.append(f"官方標示省 {d['discountPct']}%" + (f"（約 {f}）" if f else ""))
        ph = per_head(d)
        if ph is not None:
            why.append(f"折算約 {hk_num(ph)}／{'位' if cat == 'dining' else '單位'}")
        why.append("期限 " + ends_text(d))
        rank_html += (
            '<div class="rank-item">'
            f'<span class="rank-no">{i}</span>'
            '<div class="rank-body">'
            f'<h3><a href="/deals/{esc(d["id"])}/">{esc(d.get("title"))}</a></h3>'
            f'<p class="rank-meta">{esc(d.get("venue") or d.get("route") or "")}</p>'
            f'<p class="rank-why">{" · ".join(esc(w) for w in why)}</p>'
            "</div></div>"
        )

    prices = [per_head(d) for d in live if per_head(d) is not None]
    price_note = ""
    if prices:
        prices.sort()
        mid = prices[len(prices) // 2]
        price_note = (
            f'<p class="section-note">現時 {len(live)} 筆{esc(label)}中，'
            f"可折算單位成本的有 {len(prices)} 筆：最低 {hk_num(prices[0])}、"
            f"中位 {hk_num(mid)}、最高 {hk_num(prices[-1])}。"
            "排行以「官方標示折扣幅度」為第一排序，同分再按折算成本由低至高。</p>"
        )

    other = "".join(
        f'<a href="/deals/{CAT_SLUG[c]}/">{CAT_ICON[c]} {esc(CAT_LABEL[c])}</a>'
        for c in CAT_LABEL if c != cat
    )
    row_chunks = []
    for c in ("flight", "dining", "hotel"):
        cur = ' class="is-current"' if c == cat else ""
        row_chunks.append(
            f'<a href="/deals/{CAT_SLUG[c]}/"{cur}>{CAT_ICON[c]} {esc(CAT_LABEL[c])}</a>'
        )
    row_links = "".join(row_chunks)

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("全部優惠", "/deals/"), (label, None)])
        + '<div class="page-head">'
        f"<h1>{icon} 香港{esc(label)}：現時進行中一覽</h1>"
        f'<p class="page-lede">{esc(CAT_DESC[cat])}</p>'
        f'<div class="page-meta"><span>進行中：<b>{len(live)}</b> 筆</span>'
        f'<span>三日內結束：<b>{sum(1 for d in live if d.get("status") == "ending")}</b> 筆</span>'
        f'<span>最後更新：<b>{esc(str(meta.get("updated") or "")[:10])}</b></span></div>'
        f'<div class="cat-nav">{row_links}</div>'
        "</div>"
        + ('<h2 class="section-h2">🏆 焦點三選</h2>' + rank_html + price_note if ranked else "")
        + f'<h2 class="section-h2">📑 全部{esc(label)}</h2>'
        + grid_html(live)
        + (
            '<h2 class="section-h2">🗂 已結束紀錄</h2>'
            '<p class="section-note">僅作價格參考，現行方案未必相同。</p>'
            + grid_html(expired)
            if expired else ""
        )
        + f'<h2 class="section-h2">🔀 睇其他類別</h2><div class="cat-nav">{other}</div>'
        + "</main>"
    )
    return layout(
        title=f"香港{label}｜{len(live)} 筆進行中優惠｜Fly & Feast HK",
        desc=f"{CAT_DESC[cat]}現時收錄 {len(live)} 筆，附價格、折扣、期限與條款提醒。",
        path=f"/deals/{CAT_SLUG[cat]}/",
        body=body,
        meta=meta,
        active=CAT_SLUG[cat],
        ld=[breadcrumb_ld([("全部優惠", "/deals/"), (label, None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": f"香港{label}", "inLanguage": "zh-Hant-HK"}],
    )


# --------------------------------------------------------------------------
# 攻略頁
# --------------------------------------------------------------------------

GUIDES = [
    {
        "slug": "hotel-buffet-bogo",
        "icon": "🍽",
        "title": "香港酒店自助餐買一送一攻略",
        "desc": "把現時收錄的自助餐買一送一、買二送一與快閃折扣全部排出來比價，並說明「已連服務費」與「另收加一」實際差幾多。",
    },
    {
        "slug": "hk-departure-flights",
        "icon": "✈️",
        "title": "香港出發機票特價攻略",
        "desc": "廉航閃促、一口價機票與來回連稅價的判讀方法，附現時收錄的機票優惠與行李、改期陷阱清單。",
    },
    {
        "slug": "deal-terms-checklist",
        "icon": "🧾",
        "title": "落單前 12 項條款檢查表",
        "desc": "服務費點計、名額制、不適用日期、訂金與退款安排——出發前用這張表逐項對一次，避免到場才發現食唔到。",
    },
]


def guide_buffet(deals: list[dict], meta: dict) -> tuple[str, str]:
    pool = [d for d in deals if d.get("category") in ("dining", "hotel") and d.get("status") != "expired"]
    bogo = [
        d for d in pool
        if any(k in (str(d.get("title") or "") + str(d.get("priceLabel") or "")
                     + str(d.get("summary") or "") + " ".join(map(str, d.get("highlights") or [])))
               for k in ("買一送一", "買1送1", "買二送一", "買2送1", "買二送二", "買2送2",
                         "買三送一", "第二位", "1 折", "半價"))
    ]
    bogo.sort(key=lambda d: per_head(d) if per_head(d) is not None else 1e9)
    rows = ""
    for d in bogo:
        ph = per_head(d)
        rows += (
            "<tr>"
            f'<td><a href="/deals/{esc(d["id"])}/">{esc((d.get("title") or "")[:44])}</a></td>'
            f'<td>{esc((d.get("venue") or d.get("title") or "")[:34])}</td>'
            f'<td>{hk_num(ph) if ph is not None else "—"}</td>'
            f'<td>{esc(str(d.get("discountPct")) + "%" if d.get("discountPct") else "—")}</td>'
            f'<td>{esc(ends_text(d))}</td>'
            "</tr>"
        )
    prices = [per_head(d) for d in bogo if per_head(d) is not None]
    stats_line = ""
    if prices:
        prices.sort()
        stats_line = (
            f"現時表內 {len(bogo)} 筆，可折算人均的有 {len(prices)} 筆，"
            f"由 {hk_num(prices[0])} 到 {hk_num(prices[-1])}，"
            f"中位數約 {hk_num(prices[len(prices)//2])}。"
        )
    # 找「另收加一」與「已連服務費」的分野
    with_svc = [d for d in bogo if any(k in str(d.get("priceLabel") or "") + str(d.get("summary") or "")
                                      for k in ("已包", "已連", "已含", "已包括"))]
    without_svc = [d for d in bogo if any(k in str(d.get("priceLabel") or "") + str(d.get("summary") or "")
                                         for k in ("另收", "未連", "另計", "未含"))]
    svc_note = (
        f"其中 {len(with_svc)} 筆標明價格已包含服務費、"
        f"{len(without_svc)} 筆要另加或未連服務費。"
        if with_svc or without_svc else ""
    )
    body = (
        "<h2>點解自助餐買一送一比機票更值得追</h2>"
        "<p>機票的「特價」很多時候是淨價，未連稅、未連行李、限制改期，實際成本要加幾重。"
        "自助餐買一送一則通常是「照原價付一位、第二位免費」，而且多數已寫清楚用餐時段與可用日期，"
        "實際折扣相對容易核實。所以本站對自助餐的篩選標準較嚴：必須有明確折扣（7 折或以下）、"
        "明確期限，以及可追查的官方或媒體報價。</p>"
        '<div class="callout"><strong>睇價之前，先分清兩件事</strong>'
        "「已連服務費」代表你付的錢就是全部；「另收加一服務費」代表結帳時會多收一筆，"
        "而且不少餐廳是按<b>原價</b>計加一，不是按優惠價計——同一句「買一送一」，實付可以差三成以上。</div>"
        "<h2>現時收錄的自助餐與放題優惠</h2>"
        f"<p>{esc(stats_line + svc_note)}排行按折算人均成本由低至高。</p>"
        '<table><thead><tr><th>優惠</th><th>餐廳／地點</th><th>折算人均</th><th>折扣</th><th>期限</th></tr></thead>'
        f"<tbody>{rows or '<tr><td colspan=5>現時未有符合條件的紀錄。</td></tr>'}</tbody></table>"
        "<h2>揀自助餐的三條判斷準則</h2>"
        "<h3>一、先睇服務費寫法</h3>"
        "<p>標價下面有無「已連服務費」四個字，比折扣百分比更重要。以人均 HK$300 的午市自助餐為例，"
        "若另收原價一成加一，實付可能多 HK$50 以上；如果餐廳要求按原價 HK$600 計加一，差額就變成 HK$60。</p>"
        "<h3>二、再睇名額與可供日期</h3>"
        "<p>部分快閃是每日每時段限量（例如每節只有 10 個名額），亦有優惠不接受公眾假期或中秋正日。"
        "這兩點直接決定「買得到」與「用得到」，比價錢更影響實際體驗。</p>"
        "<h3>三、最後才比較菜式</h3>"
        "<p>同一個價位，海鮮陣容（生蠔、蟹腳、龍蝦）與即場煮食檯的差別可以很大。"
        "本站每筆優惠的詳情頁都列出了當次供應的焦點菜式，方便直接橫向比較。</p>"
        "<h2>常見問題</h2>"
        "<h3>買一送一可以兩個人食嗎？</h3>"
        "<p>可以，但多數要求同桌同時入座、同時落單，不能分開日子使用。亦有部分優惠限制必須二人或以上同行。</p>"
        "<h3>優惠可以與酒店會員折扣同時使用嗎？</h3>"
        "<p>通常不可以。絕大部分條款都寫明不可與其他優惠或會員折扣同用，落單前建議直接向餐廳確認。</p>"
        "<h3>買了之後可以退款或改期嗎？</h3>"
        "<p>視乎平台。酒店官網購買的自助餐券通常有明確的取消條款；第三方票券平台的特價券很多是不設退款的，"
        "詳情頁的條款區塊會標示來源，建議落單前先看平台的退款政策。</p>"
    )
    return body, stats_line


def guide_flights(deals: list[dict], meta: dict) -> tuple[str, str]:
    pool = [d for d in deals if d.get("category") == "flight" and d.get("status") != "expired"]
    expired = [d for d in deals if d.get("category") == "flight" and d.get("status") == "expired"]
    allf = pool + expired
    rows = ""
    for d in allf:
        rows += (
            "<tr>"
            f'<td><a href="/deals/{esc(d["id"])}/">{esc((d.get("title") or "")[:44])}</a></td>'
            f'<td>{esc((d.get("route") or "—")[:30])}</td>'
            f'<td>{esc((d.get("priceLabel") or "")[:46])}</td>'
            f'<td>{esc(ends_text(d))}</td>'
            "</tr>"
        )
    body = (
        "<h2>機票「特價」通常貴在你看不到的三個位</h2>"
        "<p>廉航與旅行社的閃促標價，很多時候只是票面價。真正要對清楚的是三樣："
        "稅項同燃油附加費包不包、寄艙行李要不要另外買、以及可不可以改期或退款。"
        "同一個「HK$600 台北來回」，連稅後可以變 HK$1,100 以上。</p>"
        '<div class="callout"><strong>一句記住</strong>'
        "唔好比較「標價」，要比較「落到付款頁的總額」。本站收錄機票優惠時，"
        "優先取用來回連稅價；只有淨價而查不到連稅金額的，通常不會收錄。</div>"
        "<h2>讀懂優惠標示</h2>"
        "<h3>來回連稅</h3>"
        "<p>最直接可比。代表你付款時見到的價錢已經包含機場稅與燃油附加費，"
        "只需再考慮行李與選位。見到「連稅」兩個字，先當它是可靠比較基準。</p>"
        "<h3>一口價</h3>"
        "<p>旅行社常見的玩法：指定日子、指定航線、固定價錢。要留意多數是"
        "<b>不包括寄艙行李</b>，而且通常只限 App 下單、限指定信用卡付款、每人限用一次。</p>"
        "<h3>淨價／未連稅</h3>"
        "<p>最易誤導。標價可能只是單程票面價，實際要加稅、加行李。"
        "看到這類標示，建議直接到航空公司官網模擬一次結帳，看真實總額。</p>"
        "<h2>現時收錄的機票優惠</h2>"
        '<table><thead><tr><th>優惠</th><th>航線</th><th>價格標示</th><th>期限</th></tr></thead>'
        f"<tbody>{rows or '<tr><td colspan=4>現時未有符合條件的紀錄。</td></tr>'}</tbody></table>"
        "<h2>搶票前要做好的三件事</h2>"
        "<ol>"
        "<li><b>預先填好旅客資料。</b>閃促名額通常幾十個，開搶時才輸入護照號碼基本上搶唔到。</li>"
        "<li><b>確認信用卡符合活動要求。</b>不少一口價限指定發卡機構，用錯卡會付款失敗。</li>"
        "<li><b>對清楚旅遊日期。</b>特價票多數限指定出行期間，例如「至 2027 年 3 月底的指定日子」，"
        "不是任何日子都可以飛。</li>"
        "</ol>"
        "<h2>常見問題</h2>"
        "<h3>為什麼你們收錄的機票優惠比自助餐少？</h3>"
        "<p>因為篩選門檻較嚴。單程連稅要低於 HK$700、來回連稅要低於 HK$1,600 才會收錄，"
        "而且必須有可查證的官方報價。折扣幅度不足或查不到連稅金額的，一律不收。</p>"
        "<h3>價格見到我截圖那個價，為什麼落單時不同了？</h3>"
        "<p>機票價格隨艙位供應即時浮動，特價艙位售完即回復原價。"
        "本頁只保證上架當時抄錄的資料正確，實際以航空公司或代理結帳頁為準。</p>"
    )
    return body, ""


def guide_checklist(deals: list[dict], meta: dict) -> tuple[str, str]:
    body = (
        "<p>以下 12 項是本站整理優惠時最常發現的「睇漏眼」位。"
        "落單前逐項對一次，可以避開大部分到場才發現用唔到的情況。</p>"
        "<h2>一、價錢相關</h2>"
        "<h3>1. 服務費是「已連」還是「另收」？</h3>"
        "<p>條款寫「已連服務費」代表標價就是實付；寫「另收加一」代表多收一成，"
        "而且<b>不少餐廳是按原價計算</b>。同一個買一送一，兩者實付可以差三成。</p>"
        "<h3>2. 加一是按優惠價還是原價計？</h3>"
        "<p>這是香港餐飲優惠最常見的陷阱。詳情頁若寫明「按原價計算之服務費」，"
        "就要用原價去估實付金額，不是用優惠價。</p>"
        "<h3>3. 價錢是每人還是每組？</h3>"
        "<p>「HK$598／3 位」與「HK$598／位」差三倍。本站詳情頁會列出折算人均，"
        "但商戶頁面才是最終依據。</p>"
        "<h2>二、可用性相關</h2>"
        "<h3>4. 預訂期與使用期是不同的日子</h3>"
        "<p>「預訂期」是你買券的窗口，「使用期」是你實際去食／去住的日期。"
        "兩者可以相差幾個月，快閃預訂期往往只有幾日。</p>"
        "<h3>5. 有無不適用日期</h3>"
        "<p>公眾假期、中秋正日、除夕、農曆新年通常不適用。想訂這些日子，先確認。</p>"
        "<h3>6. 名額是否有限</h3>"
        "<p>看到「每日每時段限量」、「名額 20 個」這類字眼，代表買到券不等於訂到位。"
        "建議買之前先查清楚想去的日子還有沒有位。</p>"
        "<h3>7. 小童與長者的計法</h3>"
        "<p>買一送一通常只適用成人。小童、長者往往另有價目，而且部分優惠寫明小童及長者不適用折扣。</p>"
        "<h2>三、付款與身分相關</h2>"
        "<h3>8. 付款方式有無限制</h3>"
        "<p>部分餐廳只收電子支付，部分優惠限指定信用卡或指定 App 下單。"
        "亦有要求現場以現金支付服務費的情況。</p>"
        "<h3>9. 要不要先付訂金</h3>"
        "<p>酒店官網的買一送一多數要求先付訂金（例如每位 HK$100）才算完成預留，"
        "只加入購物車不等於訂位成功。</p>"
        "<h3>10. 有無身分或憑證要求</h3>"
        "<p>長者優惠須出示身分證、會員優惠須出示會員卡、OpenRice 優惠券須出示手機或列印本。"
        "缺少憑證可能不獲優惠。</p>"
        "<h2>四、條款彈性</h2>"
        "<h3>11. 可否與其他優惠同用</h3>"
        "<p>絕大部分優惠都寫明不可與其他折扣、優惠碼或會員折扣同時使用。"
        "亦有每枱限用一次的規定。</p>"
        "<h3>12. 可否退款或改期</h3>"
        "<p>酒店官網購買的餐券通常有明確取消條款；第三方票券平台的特價券很多不設退款。"
        "落單前在平台的退款政策頁面確認一次。</p>"
        '<div class="callout"><strong>最後一步</strong>'
        "以上 12 項都可以在商戶官方頁面查到。本站每筆優惠的詳情頁都附有原始來源連結，"
        "就是為了讓你可以自己核實，而不用單憑我們的轉述。</div>"
        "<h2>這張表怎麼用</h2>"
        "<p>把你正在考慮的優惠打開，對著上面 12 點逐項打勾。"
        "如果第 1、2、4、6 項有任何一項寫得含糊，建議直接致電商戶確認，不要靠推測。</p>"
    )
    return body, ""


def build_guide_page(slug: str, deals: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    entry = next(g for g in GUIDES if g["slug"] == slug)
    if slug == "hotel-buffet-bogo":
        content, _ = guide_buffet(deals, meta)
    elif slug == "hk-departure-flights":
        content, _ = guide_flights(deals, meta)
    else:
        content, _ = guide_checklist(deals, meta)

    related = [g for g in GUIDES if g["slug"] != slug]
    rel_html = ""
    for g in related:
        rel_html += (
            '<div class="guide-card">'
            f'<span class="g-ico" aria-hidden="true">{g["icon"]}</span>'
            f'<h3><a href="/guides/{g["slug"]}/">{esc(g["title"])}</a></h3>'
            f"<p>{esc(g['desc'])}</p></div>"
        )

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("優惠攻略", "/guides/"), (entry["title"], None)])
        + '<div class="page-head">'
        f'<h1>{entry["icon"]} {esc(entry["title"])}</h1>'
        f'<p class="page-lede">{esc(entry["desc"])}</p>'
        f'<div class="page-meta"><span>最後更新：<b>{esc(str(meta.get("updated") or "")[:10])}</b></span>'
        "<span>由 <b>Fly &amp; Feast HK 編輯部</b> 整理</span></div>"
        "</div>"
        f'<div class="prose">{content}</div>'
        '<h2 class="section-h2">📚 其他攻略</h2>'
        f'<div class="guide-card-grid">{rel_html}</div>'
        "</main>"
    )
    return layout(
        title=f"{entry['title']}｜Fly & Feast HK",
        desc=entry["desc"],
        path=f"/guides/{slug}/",
        body=body,
        meta=meta,
        active="guides",
        ld=[breadcrumb_ld([("優惠攻略", "/guides/"), (entry["title"], None)], site),
            {"@context": "https://schema.org", "@type": "Article",
             "headline": entry["title"], "description": entry["desc"],
             "inLanguage": "zh-Hant-HK",
             "dateModified": str(meta.get("updated") or ""),
             "author": {"@type": "Organization", "name": "Fly & Feast HK 編輯部"},
             "publisher": {"@type": "Organization", "name": "Fly & Feast HK"}}],
    )


def build_guides_index(deals: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    cards = ""
    for g in GUIDES:
        cards += (
            '<div class="guide-card">'
            f'<span class="g-ico" aria-hidden="true">{g["icon"]}</span>'
            f'<h3><a href="/guides/{g["slug"]}/">{esc(g["title"])}</a></h3>'
            f"<p>{esc(g['desc'])}</p>"
            '<p class="g-foot">由 Fly &amp; Feast HK 編輯部整理</p>'
            "</div>"
        )
    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("優惠攻略", None)])
        + '<div class="page-head">'
        "<h1>📚 優惠攻略</h1>"
        '<p class="page-lede">優惠會過期，但判斷方法不會。這裡放的是「點樣睇一個優惠係唔係真抵」'
        "的長青內容：比較表、陷阱清單、落單前檢查步驟。"
        "同每日更新的優惠清單不同，這些頁面會持續補充與修訂。</p>"
        "</div>"
        f'<div class="guide-card-grid">{cards}</div>'
        '<h2 class="section-h2">🔗 快速入口</h2>'
        '<div class="cat-nav">'
        '<a href="/deals/">全部優惠</a>'
        '<a href="/deals/dining/">🍜 餐廳優惠</a>'
        '<a href="/deals/flight/">✈️ 機票特價</a>'
        '<a href="/deals/hotel/">🏨 酒店優惠</a>'
        "</div>"
        "</main>"
    )
    return layout(
        title="優惠攻略：自助餐買一送一、機票特價與條款檢查表｜Fly & Feast HK",
        desc="香港自助餐買一送一比價、機票特價判讀方法，以及落單前的 12 項條款檢查表。",
        path="/guides/",
        body=body,
        meta=meta,
        active="guides",
        ld=[breadcrumb_ld([("優惠攻略", None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": "優惠攻略", "inLanguage": "zh-Hant-HK"}],
    )


# --------------------------------------------------------------------------
# 合規頁
# --------------------------------------------------------------------------

def build_about(deals: list[dict], meta: dict) -> str:
    live = [d for d in deals if d.get("status") != "expired"]
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("關於本站", None)])
        + '<div class="page-head">'
        "<h1>關於 Fly &amp; Feast HK 飛嚐香港</h1>"
        '<p class="page-lede">香港出發的機票特價與餐廳優惠情報站。'
        "我們只做一件事：把散落在航空公司官網、酒店餐飲部公告、訂座與票券平台的優惠，"
        "逐項核對價格、期限與條款之後整理成可查證的清單。</p>"
        "</div>"
        '<div class="prose">'
        "<h2>我們做什麼</h2>"
        f"<p>現時站上收錄 <b>{len(live)}</b> 筆進行中優惠，每筆都有獨立的詳情頁，"
        "列明價格、折扣幅度、適用期限、條款提醒、下單渠道與原始來源連結。"
        "我們不會只寫一句「勁抵」就當完成，因為價格會不會變、名額夠不夠、"
        "有沒有隱藏收費，才是決定一個優惠值不值得出手的關鍵。</p>"
        "<h2>我們不做什麼</h2>"
        "<ul>"
        "<li><b>我們不是旅行社，也不是售票方。</b>不代收款項、不處理訂單，所有交易一律在商戶官方頁面完成。</li>"
        "<li><b>我們不發布查不到出處的價格。</b>如果找不到可查證的官方或媒體報價，"
        "即使聽起來很吸引，該筆優惠也不會收錄。</li>"
        "<li><b>我們不保證優惠在你查閱時仍然有效。</b>名額與價格隨時變動，"
        "這也是每筆優惠都附上原始來源連結的原因——讓你可以自己核實。</li>"
        "<li><b>我們不繞過任何網站的反爬機制，也不複製他人的完整內容。</b>"
        "站上每筆優惠的說明都是根據公開資料重新整理的。</li>"
        "</ul>"
        "<h2>收錄標準</h2>"
        "<p>不是所有折扣都會上架。現行的篩選門檻是：</p>"
        "<ul>"
        "<li><b>機票：</b>單程連稅低於 HK$700，或來回連稅低於 HK$1,600（香港出發的亞洲航線）。</li>"
        "<li><b>餐飲：</b>折扣達 7 折或以下，或有明確的買一送一安排。</li>"
        "<li><b>共通要求：</b>必須有可查證的官方報價、明確的適用期限，以及原始來源網址。</li>"
        "</ul>"
        "<p>達不到以上門檻的，即使是知名品牌的推廣也不會收錄；"
        "查不到明確價格的，一律略過，不會用估算或推測填補。</p>"
        "<h2>內容是怎樣產生的</h2>"
        "<p>我們每日以程式掃描公開情報源（航空公司官網優惠頁、酒店餐飲部公告、"
        "訂座與票券平台、公開的旅遊優惠 RSS），得出候選清單；"
        "之後由編輯逐項核對官方報價、適用期限與條款，通過篩選的才會寫入資料庫並上架。</p>"
        "<p>每一筆優惠在發布前都會檢查：價格是否可追溯到官方或可靠媒體來源、"
        "期限是否對得上、有沒有隱藏收費或特殊限制。"
        "站上的「編輯觀點」區塊是由優惠本身的金額、期限、折扣與條款文字推導出來的"
        "結構化分析（例如折算人均成本、服務費計法差異、同類橫向比較），"
        "不是商戶文案的轉載。</p>"
        "<h2>盈利模式</h2>"
        "<p>頁面上的部分連結為聯盟連結或推廣連結。你若經這些連結完成消費，"
        "我們可能獲得佣金。這不會令你付多一分錢，也不會影響我們對優惠的排序與評價——"
        "排序是按折扣幅度與折算成本計算，並非按佣金高低。"
        "詳見<a href=\"/terms/\">免責聲明</a>。</p>"
        "<h2>內容更正</h2>"
        "<p>如果你發現站上任何價格、期限或條款有誤，歡迎<a href=\"/contact/\">聯絡我們</a>。"
        "經核實後我們會即時更正，並在必要時下架該筆優惠。</p>"
        "</div>"
        '<h2 class="section-h2">🔗 繼續睇</h2>'
        '<div class="cat-nav">'
        '<a href="/deals/">全部優惠</a>'
        '<a href="/guides/">優惠攻略</a>'
        '<a href="/contact/">聯絡我們</a>'
        '<a href="/privacy/">隱私政策</a>'
        "</div>"
        "</main>"
    )
    return layout(
        title="關於本站｜Fly & Feast HK 飛嚐香港",
        desc="Fly & Feast HK 是香港出發的機票特價與餐廳優惠情報站。我們不是旅行社，"
             "不代收款項；所有優惠須有可查證的官方報價、明確期限與原始來源。",
        path="/about/",
        body=body,
        meta=meta,
        active="about",
        ld=[breadcrumb_ld([("關於本站", None)], site),
            {"@context": "https://schema.org", "@type": "AboutPage",
             "name": "關於 Fly & Feast HK", "inLanguage": "zh-Hant-HK"}],
    )


def build_contact(deals: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("聯絡我們", None)])
        + '<div class="page-head">'
        "<h1>聯絡我們</h1>"
        '<p class="page-lede">發現價格錯了、期限對不上，想補充一筆優惠，'
        "或者純粹想問下某個優惠的細節，都可以直接找我們。"
        "我們通常在兩個工作日內回覆。</p>"
        "</div>"
        '<div class="contact-card"><dl>'
        f"<dt>WhatsApp</dt><dd><a href=\"{esc(CONTACT['whatsapp_url'])}\" rel=\"noopener\">"
        f"{esc(CONTACT['whatsapp'])}</a></dd>"
        f"<dt>電郵</dt><dd><a href=\"mailto:{esc(CONTACT['email'])}\">{esc(CONTACT['email'])}</a></dd>"
        f"<dt>Facebook 專頁</dt><dd><a href=\"{esc(CONTACT['facebook'])}\" rel=\"noopener\">"
        f"{esc(CONTACT['facebook_label'])}</a></dd>"
        "</dl></div>"
        '<div class="prose">'
        "<h2>什麼情況適合找我們</h2>"
        "<ul>"
        "<li><b>資料更正：</b>某筆優惠的價格、期限、條款寫錯，或優惠已經結束／售罄。請附上優惠頁面連結。</li>"
        "<li><b>補充情報：</b>你見到一筆我們未收錄的優惠。請附上官方頁面連結、"
        "明確價格與期限，符合收錄標準的我們會補上。</li>"
        "<li><b>合作與廣告：</b>商戶、平台或旅行社想提供優惠資訊，歡迎直接聯絡。</li>"
        "<li><b>使用問題：</b>站上某個功能不正常、頁面顯示有誤。</li>"
        "</ul>"
        "<h2>什麼情況請直接找商戶</h2>"
        "<p>Fly &amp; Feast HK 不是旅行社，也不是售票方，<b>不代收款項、不處理訂單</b>。"
        "以下事項請直接向商戶或平台查詢，我們無法代為處理：</p>"
        "<ul>"
        "<li>訂單、付款、退款或改期安排</li>"
        "<li>訂位、留座、餐券兌換</li>"
        "<li>發票、收據或會員積分</li>"
        "<li>房間、座位或菜式的實際供應情況</li>"
        "</ul>"
        "<h2>想收到每週精選？</h2>"
        "<p>我們每日在 <a href=\"" + esc(CONTACT["facebook"]) + "\">Facebook 專頁</a> "
        "更新當日最抵的優惠，亦會在那裡回覆留言查詢。"
        "想看完整清單，可以直接前往<a href=\"/deals/\">優惠總覽</a>。</p>"
        "<h2>關於個人資料</h2>"
        "<p>你透過上述渠道提供的資料，我們只用於回覆該次查詢，"
        "不會出售或轉交第三方作推銷用途。詳見<a href=\"/privacy/\">隱私政策</a>。</p>"
        "</div>"
        "</main>"
    )
    return layout(
        title="聯絡我們｜Fly & Feast HK 飛嚐香港",
        desc="查詢、更正優惠資料或商戶合作，可經 WhatsApp、電郵或 Facebook 專頁聯絡 "
             "Fly & Feast HK。我們不是旅行社，不處理訂單與退款。",
        path="/contact/",
        body=body,
        meta=meta,
        active="about",
        ld=[breadcrumb_ld([("聯絡我們", None)], site),
            {"@context": "https://schema.org", "@type": "ContactPage",
             "name": "聯絡 Fly & Feast HK", "inLanguage": "zh-Hant-HK"}],
    )


def build_privacy(deals: list[dict], meta: dict) -> str:
    today = datetime.now(HK_TZ).date().isoformat()
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    ga4 = (meta.get("ga4MeasurementId") or "").strip()
    gtm = (meta.get("gtmContainerId") or "").strip()
    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("隱私政策", None)])
        + '<div class="page-head">'
        "<h1>隱私政策</h1>"
        f'<p class="updated-line">最後更新：{esc(today)}</p>'
        '<p class="page-lede">本政策說明 Fly &amp; Feast HK（下稱「本站」，網址 '
        f"{esc(site)}）如何處理你在使用本站時產生的資料。"
        "我們的原則是：只收集運作上真正需要的資料，並清楚告訴你用途。</p>"
        "</div>"
        '<div class="legal">'
        "<h2>一、我們收集什麼資料</h2>"
        "<h3>1. 瀏覽與分析資料</h3>"
        "<p>當你瀏覽本站，我們與我們使用的分析服務會自動收集部分技術資料，包括："
        "瀏覽的頁面與停留時間、來源網址（referrer）、裝置類型、瀏覽器與作業系統版本、"
        "大概的地理位置（例如城市層級）、以及一個隨機產生的識別碼。"
        "這些資料無法直接識別你的身分。</p>"
        "<h3>2. 你主動提供的資料</h3>"
        "<p>若你透過 WhatsApp、電郵或 Facebook 專頁聯絡我們，"
        "我們會收到你提供的姓名（或帳號名稱）、聯絡方式與訊息內容。"
        "這些資料只用於回覆該次查詢。</p>"
        "<h3>3. 訂閱資料（如適用）</h3>"
        "<p>若本站提供電郵通知服務而你選擇訂閱，我們會儲存你提供的電郵地址，"
        "只用於發送優惠提醒。你可以隨時要求取消訂閱。</p>"
        "<h2>二、Cookie 與同類技術</h2>"
        "<p>本站使用 Cookie 及類似技術（例如本機儲存）以維持網站正常運作、"
        "記住你的偏好（例如是否隱藏已結束的優惠），以及統計流量。"
        "你可以透過瀏覽器設定拒絕或刪除 Cookie，但部分功能可能因此無法正常使用。</p>"
        "<h2>三、第三方分析與廣告服務</h2>"
        "<p>本站使用 Google 提供的分析與廣告服務。這些服務可能存取或設定 Cookie，"
        "並收集你與本站及其他網站的互動資料，用於流量統計與（如適用）個人化廣告。</p>"
        "<table><thead><tr><th>服務</th><th>識別碼</th><th>用途</th></tr></thead><tbody>"
        "<tr><td>Google Analytics 4</td>"
        f"<td>{esc(ga4) or '未啟用'}</td>"
        "<td>統計瀏覽量、來源渠道與頁面表現，資料以彙總形式呈現</td></tr>"
        "<tr><td>Google Tag Manager</td>"
        f"<td>{esc(gtm) or '未啟用'}</td>"
        "<td>管理上述分析工具的載入</td></tr>"
        "<tr><td>Google AdSense（第三方廣告）</td>"
        "<td>發佈商 ID 見 ads.txt</td>"
        "<td>放送廣告。如啟用，Google 及其合作夥伴可能基於你對本網站及其他網站的"
        "先前瀏覽紀錄設定 Cookie，向您顯示個人化廣告</td></tr>"
        "</tbody></table>"
        "<h3>如何選擇退出個人化廣告</h3>"
        "<p>你可以透過以下方式管理或退出個人化廣告：</p>"
        "<ul>"
        "<li>前往 <a href=\"https://www.google.com/settings/ads\" rel=\"noopener nofollow\" target=\"_blank\">"
        "Google 廣告設定</a> 停用個人化廣告</li>"
        "<li>前往 <a href=\"https://www.aboutads.info/choices/\" rel=\"noopener nofollow\" target=\"_blank\">"
        "aboutads.info</a> 或 "
        "<a href=\"https://www.youronlinechoices.com/\" rel=\"noopener nofollow\" target=\"_blank\">"
        "youronlinechoices.com</a> 管理第三方廣告供應商的 Cookie</li>"
        "<li>在瀏覽器設定中封鎖或刪除 Cookie</li>"
        "</ul>"
        "<p>請注意，Google 作為第三方廣告供應商，會使用 Cookie 放送廣告。"
        "關於 Google 如何處理資料，可參閱 "
        "<a href=\"https://policies.google.com/technologies/partner-sites\" rel=\"noopener nofollow\" target=\"_blank\">"
        "Google 的合作夥伴網站資料使用說明</a>。</p>"
        "<h2>四、我們如何使用資料</h2>"
        "<ul>"
        "<li>維持網站運作與改善使用體驗</li>"
        "<li>了解哪些內容對讀者有用，以決定往後搜羅優惠的方向</li>"
        "<li>回覆你主動提出的查詢</li>"
        "<li>如你已訂閱，向你發送優惠提醒</li>"
        "<li>防止濫用與確保網站安全</li>"
        "</ul>"
        "<h2>五、我們不會做什麼</h2>"
        "<ul>"
        "<li>我們不會出售、出租或交換你的個人資料</li>"
        "<li>我們不會在你未主動提供的情況下收集姓名、電話或電郵</li>"
        "<li>我們不會代商戶收集訂單或付款資料——所有交易都在商戶官方頁面完成，"
        "付款資料由商戶或其平台直接處理，本站不會接觸</li>"
        "</ul>"
        "<h2>六、外部連結</h2>"
        "<p>本站的優惠內容大量引用商戶、酒店、航空公司與票券平台的官方頁面。"
        "當你點擊這些連結離開本站後，你的資料將受該網站的隱私政策管轄，本站無法控制。"
        "建議你在提供任何個人資料前先閱讀對方的政策。</p>"
        "<h2>七、資料保留</h2>"
        "<p>分析資料依服務供應商的預設保留期儲存。"
        "你主動提供的聯絡資料，我們會在處理完查詢後的一段合理時間內刪除，"
        "除非你要求保留（例如正在處理中的更正事項）。</p>"
        "<h2>八、你的權利</h2>"
        "<p>根據香港《個人資料（私隱）條例》（第 486 章），你有權查閱及更正"
        "我們持有的關於你的個人資料。如你提供的資料涉及訂閱，你亦有權隨時要求取消。"
        "如你希望行使上述權利，請經<a href=\"/contact/\">聯絡我們</a>提出，"
        "我們會在合理時間內處理。</p>"
        "<h2>九、兒童隱私</h2>"
        "<p>本站的內容以一般消費者為對象，並非針對兒童設計。"
        "我們不會故意收集兒童的個人資料；如你認為我們無意中收集了相關資料，"
        "請聯絡我們刪除。</p>"
        "<h2>十、政策更新</h2>"
        "<p>當本站新增功能或使用新的第三方服務時，我們會更新本政策並修改頁首的"
        "「最後更新」日期。建議你在使用本站時不時重看本頁。</p>"
        "<h2>十一、聯絡方式</h2>"
        "<p>如對本政策有任何疑問，請經 "
        f"<a href=\"mailto:{esc(CONTACT['email'])}\">{esc(CONTACT['email'])}</a> "
        f"或 <a href=\"{esc(CONTACT['whatsapp_url'])}\" rel=\"noopener\">WhatsApp "
        f"{esc(CONTACT['whatsapp'])}</a> 與我們聯絡。</p>"
        "</div>"
        "</main>"
    )
    return layout(
        title="隱私政策｜Fly & Feast HK 飛嚐香港",
        desc="Fly & Feast HK 的隱私政策：說明我們收集哪些資料、Cookie 與第三方"
             "分析及廣告服務（Google Analytics、AdSense）的用途，以及你選擇退出的方法。",
        path="/privacy/",
        body=body,
        meta=meta,
        active="about",
    )


def build_terms(deals: list[dict], meta: dict) -> str:
    today = datetime.now(HK_TZ).date().isoformat()
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("免責聲明", None)])
        + '<div class="page-head">'
        "<h1>免責聲明與使用條款</h1>"
        f'<p class="updated-line">最後更新：{esc(today)}</p>'
        '<p class="page-lede">使用本站即表示你已閱讀並同意以下條款。'
        "我們盡力確保資料準確，但優惠資訊本質上會變動，請務必以商戶官方公佈為準。</p>"
        "</div>"
        '<div class="legal">'
        "<h2>一、本站的性質</h2>"
        "<p>Fly &amp; Feast HK（網址 " + esc(site) + "）為<b>優惠情報整理平台</b>，"
        "並非旅行社、航空公司、酒店、餐廳或任何形式的銷售方。"
        "本站<b>不代收款項、不處理訂單、不提供訂位或退款服務</b>。"
        "所有交易一律在商戶或其指定平台的官方頁面完成。</p>"
        "<h2>二、價格與優惠資料</h2>"
        "<ul>"
        "<li>站上所有價格、折扣、期限與條款，均抄錄自商戶官方頁面或可靠媒體報導，"
        "並在收錄時經人手核對。</li>"
        "<li>優惠名額、價格、艙位與供應情況<b>隨時變動</b>。"
        "本站只反映資料收錄當時的狀態，無法保證你查閱或購買時仍然有效。</li>"
        "<li><b>一切以商戶官方公佈為準。</b>若本站資料與商戶頁面有出入，"
        "以商戶頁面為準。</li>"
        "<li>本站不會為任何未經官方確認的價格作保證。"
        "若因價格變動、名額售罄或條款修改而導致損失，本站不承擔責任。</li>"
        "</ul>"
        "<h2>三、聯盟連結與廣告披露</h2>"
        "<p>本站的營運成本來自兩部分，我們選擇公開說明：</p>"
        "<h3>1. 聯盟與推廣連結</h3>"
        "<p>站上部分「查看優惠」、「前往商戶頁面」等連結為聯盟連結或推廣連結。"
        "你若經這些連結完成消費，我們可能從商戶或平台獲得佣金。具體說明：</p>"
        "<ul>"
        "<li>這<b>不會令你付多一分錢</b>——價格與你直接到商戶頁面購買相同。</li>"
        "<li>這<b>不影響我們的排序與評價</b>。站上的焦點排行按折扣幅度與折算成本計算，"
        "並非按佣金高低排列。</li>"
        "<li>這<b>不影響收錄標準</b>。達不到價格門檻或查不到出處的優惠，"
        "即使佣金再高也不會上架。</li>"
        "<li>按搜尋引擎的建議，這類連結已標記 <code>rel=\"sponsored\"</code> 屬性。</li>"
        "</ul>"
        "<h3>2. 廣告</h3>"
        "<p>本站可能使用第三方廣告服務（例如 Google AdSense）放送廣告。"
        "廣告內容由廣告服務商決定，與本站的編輯內容無關。"
        "關於廣告 Cookie 的使用與選擇退出方式，請參閱<a href=\"/privacy/\">隱私政策</a>。</p>"
        "<h2>四、內容的原則與限制</h2>"
        "<ul>"
        "<li>我們只收錄有<b>可查證官方報價</b>、<b>明確適用期限</b>與"
        "<b>原始來源網址</b>的優惠。查不到明確價格的，一律不收錄，"
        "不會以估算或推測填補。</li>"
        "<li>我們不會偽造報價、評論或使用者評價。</li>"
        "<li>我們不會繞過任何網站的反爬機制，也不會複製他人的完整內容。</li>"
        "<li>站上引用的商標、品牌名稱與圖片版權，均屬其各自擁有人所有，"
        "本站僅作識別與報導用途。</li>"
        "</ul>"
        "<h2>五、你的責任</h2>"
        "<p>在依據本站資料作出消費決定前，<b>你有責任自行向商戶核實</b>"
        "價格、供應情況、適用期限與所有條款。"
        "本站的詳情頁在每筆優惠下方都附有原始來源連結，"
        "就是為了方便你自行核實。</p>"
        "<h2>六、責任限制</h2>"
        "<p>本站按「現況」提供內容，不對資料的完整性、準確性或適用性作任何明示或"
        "隱含的保證。在法律允許的最大範圍內，本站及其營運者"
        "不就因使用或無法使用本站內容而引致的任何直接或間接損失承擔責任，"
        "包括但不限於錯失優惠、價格差異、行程變更或訂單爭議。</p>"
        "<h2>七、外部連結</h2>"
        "<p>本站包含大量指向第三方網站的連結。我們無法控制該等網站的內容、"
        "可用性或政策，亦不對其內容負責。連結的存在不代表我們認可該網站。</p>"
        "<h2>八、內容更正與下架</h2>"
        "<p>我們力求準確。若你發現任何錯誤，或你是商戶並希望更正／移除"
        "關於你的優惠資訊，請經<a href=\"/contact/\">聯絡我們</a>提出。"
        "經核實後我們會即時更正，並在必要時下架該筆內容。</p>"
        "<h2>九、條款更新</h2>"
        "<p>我們可能不時修訂本條款，修訂後會更新頁首的「最後更新」日期。"
        "繼續使用本站即表示接受修訂後的條款。</p>"
        "<h2>十、適用法律</h2>"
        "<p>本條款受香港特別行政區法律管轄。</p>"
        "</div>"
        "</main>"
    )
    return layout(
        title="免責聲明與使用條款｜Fly & Feast HK 飛嚐香港",
        desc="Fly & Feast HK 的免責聲明、聯盟連結與廣告披露、收錄標準及責任限制。"
             "本站為優惠情報整理平台，並非旅行社，一切以商戶官方公佈為準。",
        path="/terms/",
        body=body,
        meta=meta,
        active="about",
    )


# --------------------------------------------------------------------------
# 日本美食專欄（/japan/）
# --------------------------------------------------------------------------

def load_japan() -> list[dict]:
    if not JAPAN_FILE.exists():
        return []
    try:
        payload = json.loads(JAPAN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    eats = payload.get("eats") or []
    return [e for e in eats if e.get("id") and e.get("name")]


def rating_line(e: dict) -> str:
    """★ 4.4 · 1,302 則 Google 評論（2026-09-24 核對）"""
    parts = [f"Google 評分 {e.get('rating'):.1f}"]
    if e.get("reviews"):
        n = e["reviews"]
        suffix = " 則評論以上" if e.get("reviewsApprox") else " 則評論"
        parts.append(f"{n:,}{suffix}")
    if e.get("ratingCheckedAt"):
        parts.append(f"{e['ratingCheckedAt']} 核對")
    return " · ".join(parts)


def maps_embed_src(e: dict) -> str | None:
    """由官方 mapsUrl 的 query 參數派生無需 API key 的嵌入地圖網址。

    Google Maps 官方嵌入（output=embed）可合法顯示該地點的地圖、
    實景相片與評分卡；查詢串直接沿用收錄時的同一組參數，定位一致。
    """
    src = str(e.get("mapsUrl") or "")
    q = None
    if "query=" in src:
        q = src.split("query=", 1)[1].split("&", 1)[0]
    if not q:
        name = e.get("name")
        city = e.get("city")
        if name and city:
            q = urllib.parse.quote(f"{name} {city}")
    if not q:
        return None
    return f"https://www.google.com/maps?q={q}&output=embed&hl=zh-HK"


def maps_embed_html(e: dict) -> str:
    src = maps_embed_src(e)
    if not src:
        return ""
    name = e.get("name") or "餐廳"
    return (
        '<figure class="maps-embed">'
        f'<iframe src="{esc(src)}" title="{esc(name)} 嘅 Google Maps 地圖與實景相片" '
        'loading="lazy" allowfullscreen referrerpolicy="no-referrer-when-downgrade"></iframe>'
        '<figcaption class="jp-note">地圖卡由 Google Maps 官方嵌入，可直接睇到店面實景相、'
        "評分同街景；以 Google Map 即時顯示為準。</figcaption>"
        "</figure>"
    )


def japan_rating_tier(rating: float) -> str:
    if rating >= 4.5:
        return ("4.5 分以上在 Google Maps 屬於極少數：通常要長期維持高水準先做得到，"
                "呢個分數本身就係最強嘅推薦理由。")
    if rating >= 4.3:
        return ("4.3 分以上已經爬得過 Google 大量評論嘅平均線——"
                "評論愈多，愈難靠少數好評拉高，呢個分數代表長期穩定。")
    return "4.2 分以上已屬優秀，配合評論數量一併睇更有參考價值。"


def japan_review_signal(e: dict) -> str:
    n = e.get("reviews")
    if not n:
        return "評論總數未有可靠數字，建議出發前直接喺 Google Maps 睇最新評價分佈。"
    if n >= 2000:
        return (f"評論數超過 {n:,} 則，樣本夠大，分數唔會因為幾單新評價就大幅波動；"
                "同時留意當中對排隊、服務節奏嘅評語，呢啲分店規模先會出現嘅特徵。")
    if n >= 800:
        return (f"約 {n:,} 則評論，樣本屬中大規模，分數有參考性；"
                "建議順手睇埋近三個月嘅評價，確認狀態冇回落。")
    return f"約 {n:,} 則評論，樣本有限，分數浮動會較大，去之前記得覆核。"


def japan_price_signal(e: dict) -> str:
    band = str(e.get("priceRange") or "")
    m = re.search(r"¥\s*([\d,]+)", band)
    lo = int(m.group(1).replace(",", "")) if m else None
    if lo is not None and lo < 1500:
        extra = "屬日常價位，當一頓普通飯食都唔會肉赤。"
    elif lo is not None and lo < 3000:
        extra = "屬一頓正餐價位，以質素計屬合理，當旅途中的小獎勵最啱。"
    elif lo is not None:
        extra = "屬專程消費價位，建議預好預算並確認套餐內容先落單。"
    else:
        extra = "價位以店家現場公佈為準。"
    return f"標示價位：{band or '未標示'}。{extra}"


def japan_editorial_blocks(e: dict, peers: list[dict]) -> list[tuple[str, list[str], list[str]]]:
    blocks: list[tuple[str, list[str], list[str]]] = []
    rating = e.get("rating")

    # 1) 評分點解讀
    paras = [japan_rating_tier(rating), japan_review_signal(e)]
    paras.append("評分與評論數會隨時間浮動，以上為收錄時抄錄的數字；出發前請以 Google Map 即時顯示為準。")
    blocks.append(("評分點解讀", paras, []))

    # 2) 消費預算
    blocks.append(("消費預算", [japan_price_signal(e)], []))

    # 3) 去之前要知道
    tips = [str(t) for t in (e.get("tips") or []) if str(t).strip()]
    if not tips:
        tips = ["暫時未有特別注意事項，建議出發前以 Google Map 與店家公佈為準。"]
    blocks.append(("去之前要知道", [], tips))

    # 4) 同城點揀
    same = [p for p in peers
            if p.get("id") != e.get("id")
            and p.get("city") == e.get("city")]
    if same:
        same.sort(key=lambda p: abs((p.get("rating") or 0) - (rating or 0)))
        lines = []
        for p in same[:3]:
            pr = p.get("priceRange") or "價位見詳情頁"
            lines.append(f"{p['name']}（{p.get('rating'):.1f} 分 · {pr}）")
        blocks.append(("同城仲有呢啲選擇",
                       [f"同一個城市收錄了 {len(same)} 間同樣高分的餐廳，分數與價位最接近的如下，"
                        "行程排得埋就值得一併考慮。"], lines))
    return blocks


def japan_editorial_html(e: dict, peers: list[dict]) -> str:
    blocks = japan_editorial_blocks(e, peers)
    parts = [
        '<section class="editorial" aria-labelledby="jp-ed-title">',
        '<h2 id="jp-ed-title">🧾 編輯觀點 <span class="ed-cat">由評分、價位與收錄資料推導</span></h2>',
    ]
    for title, paras, bullets in blocks:
        parts.append(f"<h3>{esc(title)}</h3>")
        for p in paras:
            parts.append(f"<p>{esc(p)}</p>")
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>")
    parts.append(
        '<p class="ed-foot">本頁評分、地址與注意事項由 Fly &amp; Feast HK 編輯部根據公開來源'
        "核對抄錄，最後核對日期見頁首資料。餐廳營業時間、價格與供應隨時變動，"
        "一切以店家及 Google Map 即時資訊為準。</p>"
    )
    parts.append("</section>")
    return "".join(parts)


def japan_card(e: dict) -> str:
    url = f"/japan/{esc(e['id'])}/"
    star = f"{e.get('rating'):.1f}" if isinstance(e.get("rating"), (int, float)) else "—"
    stars = f"★ {star}"
    reviews = ""
    if e.get("reviews"):
        n = e["reviews"]
        reviews = f" · {n:,}+ 則評論" if e.get("reviewsApprox") else f" · {n:,} 則評論"
    hl = ""
    if e.get("tips"):
        hl = "<ul>" + "".join(f"<li>{esc(t)}</li>" for t in e["tips"][:2]) + "</ul>"
    return (
        f'<article class="card" data-id="{esc(e["id"])}">'
        '<div class="card-top">'
        f'<span class="badge badge-dining">{esc(e.get("city") or "日本")}</span>'
        f'<span class="badge badge-rating" aria-label="Google 評分">{esc(star + " Google")}</span>'
        '<span class="card-sticker st-dining" aria-hidden="true">🇯🇵</span>'
        "</div>"
        f'<h3><a href="{url}">{esc(e["name"])}</a></h3>'
        + (f'<p class="sub">{esc(e["nameEn"])}</p>' if e.get("nameEn") else "")
        + f'<p class="route">{esc(e.get("cuisine") or "")}｜{esc(e.get("area") or "")}</p>'
        + '<div class="price-row">'
        f'<span class="price">{esc(e.get("priceRange") or "價位見詳情頁")}</span>'
        f'<span class="save">{esc(stars + reviews)}</span>'
        "</div>"
        + (f'<p class="summary">{esc(e["blurb"])}</p>' if e.get("blurb") else "")
        + hl
        + f'<div class="card-foot"><span class="period">{esc(rating_line(e))}</span>'
        f'<span class="actions"><a class="link-btn" href="{url}">睇詳情 →</a></span></div>'
        + "</article>"
    )


def japan_grid(eats: list[dict]) -> str:
    if not eats:
        return '<p class="empty">這個城市暫時未有收錄的餐廳。</p>'
    return '<div class="grid">' + "".join(japan_card(e) for e in eats) + "</div>"


def build_japan_index(eats: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    updated = str(meta.get("updated") or "")[:10]
    cities: list[str] = []
    for e in eats:
        c = str(e.get("city") or "其他")
        if c not in cities:
            cities.append(c)
    cities.sort(key=lambda c: (JAPAN_CITY_ORDER.index(c) if c in JAPAN_CITY_ORDER else 99))

    city_nav = "".join(
        f'<a href="#city-{i}">{esc(c)}（{sum(1 for e in eats if e.get("city") == c)}）</a>'
        for i, c in enumerate(cities)
    )
    sections = ""
    for i, c in enumerate(cities):
        pool = [e for e in eats if e.get("city") == c]
        pool.sort(key=lambda e: -(e.get("rating") or 0))
        sections += (
            f'<h2 class="section-h2" id="city-{i}">📍 {esc(c)}'
            f'<span class="ed-cat">共 {len(pool)} 間</span></h2>'
            + japan_grid(pool)
        )

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("日本美食", None)])
        + '<div class="page-head">'
        "<h1>🇯🇵 日本美食專欄：Google Maps 高分餐廳逐個講</h1>"
        '<p class="page-lede">香港人去日本，最難唔係搵唔到嘢食，係選擇太多唔知邊間值得去。'
        "這個專欄每星期收羅日本不同城市在 Google Maps 上高分的餐廳，"
        "每間有獨立詳情頁：評分點解讀、價位預算、排隊與預約貼士，"
        "並附上資料來源，等你唔使齋靠一句「好好食」做決定。</p>"
        f'<div class="page-meta"><span>已收錄：<b>{len(eats)}</b> 間</span>'
        f'<span>城市：<b>{len(cities)}</b> 個</span>'
        f'<span>最後更新：<b>{esc(updated)}</b></span></div>'
        f'<div class="cat-nav">{city_nav}</div>'
        "</div>"
        + '<div class="prose">'
        "<h2>收錄準則</h2>"
        "<ul>"
        "<li><b>評分以 Google Maps 為準</b>：評分與評論數由公開來源抄錄並附出處，"
        "優先收錄 4.3 分以上、評論數有相當規模的餐廳。</li>"
        "<li><b>評分會浮動</b>：每筆資料標明核對日期，出發前請以 Google Map 即時顯示為準。</li>"
        "<li><b>唔收閉門造車的評價</b>：我們不會自己「評分」，"
        "每頁的觀點都是由已核實的評分、價位與注意事項推導出來。</li>"
        "<li><b>每星期更新</b>：輪替加入不同城市的選擇，由東京、大阪等熱門城市開始，"
        "逐步覆蓋更多地區。</li>"
        "</ul>"
        "</div>"
        + sections
        + "</main>"
    )
    return layout(
        title="日本美食專欄：Google Maps 高分餐廳推薦｜Fly & Feast HK",
        desc=f"日本不同城市的 Google Maps 高分餐廳專欄，現收錄 {len(eats)} 間，"
             "每間附評分解讀、價位預算、排隊與預約貼士及資料來源，每星期更新。",
        path="/japan/",
        body=body,
        meta=meta,
        active="japan",
        ld=[breadcrumb_ld([("日本美食", None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": "日本美食專欄", "inLanguage": "zh-Hant-HK"}],
    )


def build_japan_eat_page(e: dict, peers: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    city = str(e.get("city") or "日本")
    url = f"/japan/{e['id']}/"
    updated = str(meta.get("updated") or "")[:10]
    star = f"{e.get('rating'):.1f}" if isinstance(e.get("rating"), (int, float)) else "—"

    facts = [
        ("城市／地區", f"{city} · {e.get('area') or '—'}"),
        ("菜式", e.get("cuisine") or "—"),
        ("招牌", e.get("signature") or "—"),
        ("Google 評分", rating_line(e)),
        ("價位", e.get("priceRange") or "—"),
        ("地址", e.get("address") or "—"),
    ]
    facts_html = "".join(
        f'<div class="deal-fact"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in facts
    )

    related = [p for p in peers
               if p.get("id") != e.get("id") and p.get("city") == e.get("city")]
    related.sort(key=lambda p: abs((p.get("rating") or 0) - (e.get("rating") or 0)))

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("日本美食", "/japan/"), (e.get("name", ""), None)])
        + '<article>'
        '<div class="deal-hero">'
        '<div class="card-top">'
        '<span class="badge badge-dining">日本美食</span>'
        f'<span class="badge badge-rating">★ {esc(star)} Google</span>'
        "</div>"
        f"<h1>{esc(e.get('name'))}</h1>"
        + (f'<p class="lede-line">{esc(e["nameEn"])}</p>' if e.get("nameEn") else "")
        + '<div class="price-panel">'
        f'<span class="p-now">{esc(e.get("priceRange") or "價位以店家公佈為準")}</span>'
        '<span class="p-note">價位與營業時間以店家及 Google Map 即時資訊為準。</span>'
        "</div>"
        f'<dl class="deal-facts">{facts_html}</dl>'
        "</div>"
        + maps_embed_html(e)
        + (f'<h2 class="section-h2">📖 編輯簡介</h2><p>{esc(e.get("blurb"))}</p>'
           if e.get("blurb") else "")
        + japan_editorial_html(e, peers)
        + (
            '<div class="deal-actions">'
            f'<a class="link-btn" href="{esc(e.get("mapsUrl") or "#")}" target="_blank" rel="noopener nofollow">'
            "在 Google Maps 打開（導航／睇最新評價）→</a>"
            '<a class="btn-ghost" href="/japan/">睇晒全部日本餐廳</a>'
            "</div>"
            '<div class="source-block"><p><strong>評分與資料來源：</strong>'
            + (
                f'<a href="{esc(e["sourceUrl"])}" target="_blank" rel="noopener nofollow">'
                f'{esc(e.get("sourceLabel") or e["sourceUrl"])}</a>'
                if e.get("sourceUrl") else esc(e.get("sourceLabel"))
            )
            + f"</p><p>評分與評論數於 {esc(e.get('ratingCheckedAt') or updated)} 核對抄錄，"
            "會隨時間浮動；營業時間、價格與供應隨時變動，一切以店家及 Google Map 即時資訊為準。</p></div>"
        )
        + "</article>"
        + (
            '<section class="related"><h2 class="section-h2">🔎 同城市仲有</h2>'
            '<p class="section-note">評分與價位最接近的同城選擇。</p>'
            + japan_grid(related[:3])
            + "</section>"
            if related else ""
        )
        + "</main>"
    )

    trail = [("日本美食", "/japan/"), (e.get("name", ""), None)]
    ld = [
        breadcrumb_ld(trail, site),
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": e.get("name"),
            "description": (e.get("blurb") or "")[:155],
            "inLanguage": "zh-Hant-HK",
            "dateModified": str(meta.get("updated") or ""),
            "author": {"@type": "Organization", "name": "Fly & Feast HK 編輯部"},
            "publisher": {"@type": "Organization", "name": "Fly & Feast HK"},
            "mainEntityOfPage": {"@type": "WebPage", "@id": site + url},
        },
    ]
    return layout(
        title=f"{e.get('name')}｜{city} Google Maps 高分餐廳｜Fly & Feast HK",
        desc=((e.get("blurb") or e.get("name") or "")[:155]),
        path=url,
        body=body,
        meta=meta,
        active="japan",
        ld=ld,
    )


def prune_stale_japan_pages(valid_ids: set[str]) -> int:
    """同優惠頁一樣，清除已不在 japan.json 的孤兒頁。資料少於 5 筆時不動。"""
    MIN_SIZE = 5
    if len(valid_ids) < MIN_SIZE:
        return 0
    base = PROJECT / "japan"
    if not base.exists():
        return 0
    removed = 0
    for child in base.iterdir():
        if child.is_dir() and child.name not in valid_ids:
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed


# --------------------------------------------------------------------------
# sitemap
# --------------------------------------------------------------------------

def build_sitemap(deals: list[dict], meta: dict, japan_eats: list[dict] | None = None) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    today = datetime.now(HK_TZ).date().isoformat()
    urls: list[tuple[str, str, str]] = [
        ("/", "1.0", "daily"),
        ("/deals/", "0.9", "daily"),
    ]
    for c in ("flight", "dining", "hotel"):
        urls.append((f"/deals/{CAT_SLUG[c]}/", "0.9", "daily"))
    urls.append(("/japan/", "0.8", "weekly"))
    for e in (japan_eats or []):
        urls.append((f"/japan/{e['id']}/", "0.6", "weekly"))
    urls.append(("/guides/", "0.8", "weekly"))
    for g in GUIDES:
        urls.append((f"/guides/{g['slug']}/", "0.7", "weekly"))
    for d in deals:
        urls.append((f"/deals/{d['id']}/", "0.6", "weekly"))
    urls += [
        ("/about/", "0.6", "monthly"),
        ("/contact/", "0.5", "monthly"),
        ("/privacy/", "0.3", "yearly"),
        ("/terms/", "0.3", "yearly"),
    ]
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, prio, freq in urls:
        parts += [
            "  <url>",
            f"    <loc>{site}{path}</loc>",
            f"    <lastmod>{today}</lastmod>",
            f"    <changefreq>{freq}</changefreq>",
            f"    <priority>{prio}</priority>",
            "  </url>",
        ]
    parts.append("</urlset>")
    SITEMAP.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return str(len(urls))


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def write_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load() -> tuple[dict, list[dict]]:
    if not DATA.joinpath("deals.json").exists():
        raise SystemExit("找不到 data/deals.json，請先執行 build_site.py")
    payload = json.loads(DATA.joinpath("deals.json").read_text(encoding="utf-8"))
    meta = dict(payload.get("meta") or {})
    meta.setdefault("siteUrl", SITE_FALLBACK)
    deals = payload.get("deals") or []
    # 補上 siteUrl 之外的來源設定（store.json 為權威）
    if STORE.exists():
        try:
            smeta = json.loads(STORE.read_text(encoding="utf-8")).get("meta") or {}
            for key in ("siteUrl", "ga4MeasurementId", "gtmContainerId", "disclaimer"):
                if smeta.get(key):
                    meta[key] = smeta[key]
        except (json.JSONDecodeError, OSError):
            pass
    return meta, deals


def prune_stale_pages(valid_ids: set[str]) -> int:
    """移除已不在資料庫內的優惠詳情頁，避免留下無入口的孤兒頁面。

    安全限制：資料筆數少於 MIN_PRUNE_SIZE 時完全不動，避免上游資料異常
    （例如 store.json 被截斷）時一次過刪掉大量頁面。
    """
    MIN_PRUNE_SIZE = 10
    if len(valid_ids) < MIN_PRUNE_SIZE:
        return 0
    base = PROJECT / "deals"
    if not base.exists():
        return 0
    keep = set(CAT_SLUG.values())
    removed = 0
    for child in base.iterdir():
        if not child.is_dir() or child.name in keep or child.name in valid_ids:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed += 1
    return removed


def build_all(meta: dict | None = None, deals: list[dict] | None = None) -> dict:
    if meta is None or deals is None:
        meta, deals = load()

    written = 0
    for d in deals:
        write_page(PROJECT / "deals" / d["id"] / "index.html", build_deal_page(d, deals, meta))
        written += 1

    pruned = prune_stale_pages({d["id"] for d in deals})
    write_page(PROJECT / "deals" / "index.html", build_deals_index(deals, meta))
    for c in ("flight", "dining", "hotel"):
        write_page(PROJECT / "deals" / CAT_SLUG[c] / "index.html",
                   build_category_page(c, deals, meta))
    write_page(PROJECT / "guides" / "index.html", build_guides_index(deals, meta))
    for g in GUIDES:
        write_page(PROJECT / "guides" / g["slug"] / "index.html",
                   build_guide_page(g["slug"], deals, meta))

    # 日本美食專欄
    eats = load_japan()
    jpruned = prune_stale_japan_pages({e["id"] for e in eats})
    if eats:
        write_page(PROJECT / "japan" / "index.html", build_japan_index(eats, meta))
        for e in eats:
            write_page(PROJECT / "japan" / e["id"] / "index.html",
                       build_japan_eat_page(e, eats, meta))
    else:
        print("  日本美食專欄：japan.json 無資料或不存在，已略過")

    write_page(PROJECT / "about" / "index.html", build_about(deals, meta))
    write_page(PROJECT / "contact" / "index.html", build_contact(deals, meta))
    write_page(PROJECT / "privacy" / "index.html", build_privacy(deals, meta))
    write_page(PROJECT / "terms" / "index.html", build_terms(deals, meta))

    total = build_sitemap(deals, meta, eats)
    result = {
        "deals": written,
        "pages": written + 4 + 3 + 1 + len(GUIDES) + 4 + len(eats) + (1 if eats else 0),
        "sitemap": total,
    }
    print(
        f"  多頁內容：{written} 個優惠詳情頁、4 個分類／總覽頁、"
        f"{len(eats)} 個日本美食頁、{len(GUIDES)} 篇攻略、4 個合規頁；"
        f"sitemap 收錄 {total} 條 URL"
        + (f"；已清除 {pruned} 個優惠孤兒頁面" if pruned else "")
        + (f"；已清除 {jpruned} 個日本美食孤兒頁面" if jpruned else "")
    )
    return result


def main() -> int:
    meta, deals = load()
    build_all(meta, deals)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
