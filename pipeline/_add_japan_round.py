# -*- coding: utf-8 -*-
"""一次性寫入腳本：為日本專欄（美食＋酒店）加入本輪新條目。
用完即刪。id 去重保護：任何一個 id 已存在就整支中止，唔會寫入。
"""
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
FOOD = ROOT / "pipeline" / "japan.json"
HOTEL = ROOT / "pipeline" / "japan-hotels.json"
TODAY = "2026-10-07"


def maps(name, area):
    return "https://www.google.com/maps/search/?api=1&query=" + quote(f"{name} {area}")


# ---------------------------------------------------------------- 美食 A 線
NEW_EATS = [
    {
        "id": "jp-takamatsu-ueharaya-honten",
        "name": "讚岐烏龍麵 上原屋本店",
        "nameEn": "Sanuki Udon Ueharaya Honten",
        "city": "高松",
        "area": "栗林町（栗林公園東側；琴電栗林公園站步行約 5 分鐘、路線巴士「室北口」站步行約 3 分鐘）",
        "cuisine": "讚岐烏龍麵（自助式）",
        "signature": "生醬油烏龍、冷かけ烏龍、釜玉烏龍、現炸天婦羅（じゃこかつ、高野豆腐天）、關東煮",
        "rating": 4.3,
        "reviews": 2932,
        "ratingCheckedAt": TODAY,
        "priceRange": "¥300–1,000（烏龍麵約 ¥300 起，天婦羅與關東煮逐件另計）",
        "address": "香川県高松市栗林町1-18-8",
        "mapsUrl": maps("讃岐うどん 上原屋本店", "香川県高松市栗林町1-18-8"),
        "blurb": "栗林公園東門外、行完米芝蓮三星庭園就到的自助烏龍麵老店，在高松市內屬「幾乎冇一刻唔排隊」的一批。流程好簡單：先拎托盤夾天婦羅同關東煮，再到櫃檯講玉數拎麵，最後自己加湯加蔥。湯頭每朝用沙丁魚同醬油熬，清得見底但鮮味足；天婦羅係現炸，じゃこかつ同高野豆腐天係熟客指定。Google 4.3 分、接近三千則評論，係四國烏龍麵店中樣本數最大的一批。",
        "tips": [
            "自助流程：入門取托盤 → 揀天婦羅／關東煮 → 到櫃檯講玉數（小／中／大）→ 自己加湯、蔥、天かす → 最後付款。牆上有圖示，第一次去都唔會亂。",
            "營業時間各來源寫法唔一致（09:00–16:00 或 09:30–14:30），共通點係「麵或湯賣完即收」，實際以店家當日公佈為準，太晏去有機會扑空。",
            "定休日為星期四及星期日（以店家公佈為準）；星期日休息係旅客最常中招的一點。",
            "店旁有約 18 個免費車位但午市經常爆滿；唔開車可由琴電栗林公園站行約 5 分鐘，或路線巴士「室北口」站行約 3 分鐘。",
        ],
        "sourceLabel": "Wanderlog 地點頁（引用 Google 評分 4.3 與 2,932 則評論）＋ yenYus Diary（列明 Google 4.3 星、2,000 多則評論；Tabelog 3.77）",
        "sourceUrl": "https://wanderlog.com/zh/place/details/2668553/sanuki-udon-ueharaya",
        "addedAt": TODAY,
    },
    {
        "id": "jp-kanazawa-menya-taiga",
        "name": "麺屋大河",
        "nameEn": "Menya Taiga",
        "city": "金澤",
        "area": "堀川町（JR 金澤站東口步行約 4–5 分鐘）",
        "cuisine": "拉麵",
        "signature": "特製味噌拉麵（赤白味噌混合湯底）、能登豚炭火吊燒叉燒、能登豚叉燒丼、蝦湯／烏賊墨口味",
        "rating": 4.4,
        "reviews": 3470,
        "ratingCheckedAt": TODAY,
        "priceRange": "¥1,000 以內（拉麵大多 ¥1,000 內，叉燒丼另計）",
        "address": "石川県金沢市堀川町6-3",
        "mapsUrl": maps("麺屋大河", "石川県金沢市堀川町6-3"),
        "blurb": "金澤拉麵界最有名的一碗，離 JR 金澤站東口只係行四、五分鐘，車站酒店圈步行可達。招牌濃厚味噌用赤、白味噌混合再加動物系湯底，入口醇厚但尾韻有淡淡柚香；麵係中太縮麵、彈牙掛湯，配能登豚炭火吊燒叉燒。入座會送一杯免費生薑汁。有中英文菜單。開店前已經有人排，想唔排就 11:30 前到。",
        "tips": [
            "開店前已有人龍：午市 11:00 開門、晚市 17:30 開始，兩段都要排；想避人潮就 11:30 前到。",
            "有中文／英文菜單，唔識日文都點得到；點餐採飯後結帳，可用現金與 PayPay 等無現金方式。",
            "招牌係特製味噌拉麵，另可試蝦湯或烏賊墨等限定口味；食量大的可以加點能登豚叉燒丼。",
            "全年無休（以店家公佈為準）；營業時間各來源寫法略有出入，出發前先查店家最新公佈。",
        ],
        "sourceLabel": "Wanderlog 地點頁（引用 Google 評分 4.4 與 3,470 則評論）＋ Yuku Japan（Google 4.4／3,411 則）；Retty match score 4.41",
        "sourceUrl": "https://wanderlog.com/zh/place/details/1184365/ramen-taiga",
        "addedAt": TODAY,
    },
]

FOOD_ROTATION = [
    "橫濱", "名古屋", "神戶", "廣島", "大阪", "京都",
    "沖繩", "福岡", "札幌", "東京", "仙台", "高松", "金澤",
]

# ---------------------------------------------------------------- 酒店 B 線
NEW_HOTELS = [
    {
        "id": "jp-yokohama-bay-hotel-tokyu",
        "name": "橫濱灣東急大飯店",
        "nameEn": "The Yokohama Bay Hotel Tokyu",
        "city": "橫濱",
        "area": "西區港未來（港未來線港未來站步行約 1 分鐘，與 Queen's Square 商場直結）",
        "type": "港未來地標 4 星酒店（1997 年開業）",
        "highlight": "港未來區唯一全房型附陽台，房內直望摩天輪與海灣",
        "rating": 4.4,
        "reviews": 6197,
        "ratingCheckedAt": TODAY,
        "priceBand": "以訂房平台即時報價為準（收錄時未見可靠公開參考價，故不列數字）",
        "address": "神奈川県横浜市西区みなとみらい2-3-7",
        "mapsUrl": maps("横浜ベイホテル東急", "神奈川県横浜市西区みなとみらい2-3-7"),
        "blurb": "港未來站正上方的老牌地標酒店，行出閘一分鐘、穿過 Queen's Square 商場就到，落雨都唔使開遮。全館最大賣點係「港未來區唯一全房型都有陽台」——陽台正面對住 Cosmo Clock 摩天輪同海灣，夜景係同區其他酒店換唔到的。館內有 4 間餐廳、spa 同健身室；自助早餐的鮮榨橙汁同鮮果係住客最常提的一項。Google 4.4 分、逾六千則評論，樣本數在橫濱港未來一帶數一數二。",
        "valuePoints": [
            "港未來站步行約 1 分鐘，並與 Queen's Square 商場室內直結；去 Landmark Tower、Pacifico 會議中心、紅磚倉庫全部步行範圍。",
            "港未來區唯一全房型附陽台：陽台正望摩天輪與海灣夜景，同區同級酒店冇呢個配置。",
            "Google 4.4 分、6,197 則評論，係橫濱港未來一帶樣本數最大的酒店之一，分數唔會因為幾則新評價就大上大落。",
            "館內設 4 間餐廳、spa 與健身室；自助早餐有即榨橙汁與鮮果，屬房價內已包的加分項。",
            "酒店 1997 年開業，部分住客反映裝潢風格偏舊，但房間面積與景觀在港未來一帶仍屬前段。",
        ],
        "tips": [
            "部分房型窗戶唔開得；對通風有要求就入住時同櫃檯講，請職員協助。",
            "館內冇自助洗衣房，長住或帶小朋友要留意。",
            "每年草莓甜品自助（Strawberry Buffet）一開放預約就滿，想食要早訂。",
            "大堂在 2 樓；的士落客後如冇人手即時幫手搬行李，可以主動請職員協助寄存。",
            "評分與評論數為第三方引用快照，出發前請以 Google Map 即時顯示為準。",
        ],
        "sourceLabel": "Wanderlog 地點頁（引用 Google 評分 4.4 與 6,197 則評論；Tripadvisor 3.8／43 則）",
        "sourceUrl": "https://wanderlog.com/place/details/120399/the-yokohama-bay-hotel-tokyu",
        "addedAt": TODAY,
    },
    {
        "id": "jp-yokohama-sotetsu-splaisir",
        "name": "相鐵飯店 THE SPLAISIR 橫濱",
        "nameEn": "SOTETSU HOTELS THE SPLAISIR YOKOHAMA",
        "city": "橫濱",
        "area": "神奈川區鶴屋町（THE YOKOHAMA FRONT 4F；JR 橫濱站北西口步行約 3 分鐘，有天橋接駁）",
        "type": "公寓式 4 星酒店（2024 年 6 月開業）",
        "highlight": "2024 新開，房內附廚房與獨立洗衣機，橫濱站步行 3 分鐘",
        "rating": 4.6,
        "reviews": 427,
        "ratingCheckedAt": TODAY,
        "priceBand": "以訂房平台即時報價為準（收錄時未見可靠公開參考價，故不列數字）",
        "address": "神奈川県横浜市神奈川区鶴屋町1-41 THE YOKOHAMA FRONT 4F",
        "mapsUrl": maps("相鉄ホテルズ ザ・スプラジール 横浜", "神奈川県横浜市神奈川区鶴屋町1-41"),
        "blurb": "2024 年 6 月開幕、開在橫濱站北西口 THE YOKOHAMA FRONT 商場 4 樓的新酒店，主打公寓式房型：部分房間有廚房（kitchenette）同房內獨立洗衣機，長住或帶小朋友嘅實際方便程度同區無人比。4.6 分係橫濱站周邊酒店中少見的高分（同區多數落在 4.2–4.4）；館內另有健身室、投幣洗衣、麵包店同餐廳，行李可用 IC 卡自助寄存，入住退房一律自助機，唔使排隊。",
        "valuePoints": [
            "JR 橫濱站北西口步行約 3 分鐘，並有天橋／商場通道接駁，拖行李唔使行馬路。",
            "2024 年 6 月開業，硬件全新；同區同年份的新酒店房價通常貴一截。",
            "公寓式房型：部分房間附廚房（kitchenette）與房內獨立洗衣機，長住或帶小朋友最實用——橫濱站周邊商務酒店少見。",
            "Google 4.6 分、427 則評論；4.6 明顯高於橫濱站周邊酒店平均（多數 4.2–4.4）。",
            "館內設健身室、投幣洗衣、麵包店與餐廳；行李用 IC 卡自助寄存，check-in／check-out 用自助機，效率高。",
        ],
        "tips": [
            "非營業時間使用健身室要行側門、上四層樓梯，訂之前留意。",
            "房內空調約 30 分鐘後會重設為預設設定，介意自己控溫要留意。",
            "酒店在 THE YOKOHAMA FRONT 商場 4 樓，樓上樓下都有餐廳同店舖，落雨可以直接在樓內解決食買。",
            "評分與評論數為第三方引用快照，出發前請以 Google Map 即時顯示為準。",
        ],
        "sourceLabel": "Wanderlog 地點頁（引用 Google 評分 4.6 與 427 則評論）",
        "sourceUrl": "https://wanderlog.com/zh/place/details/9675745/sotetsu-hotels-the-splaisir-yokohama",
        "addedAt": TODAY,
    },
    {
        "id": "jp-yokohama-mitsui-garden-minatomirai",
        "name": "三井花園飯店橫濱港未來普米爾",
        "nameEn": "Mitsui Garden Hotel Yokohama Minatomirai PREMIER",
        "city": "橫濱",
        "area": "西區港未來（港未來站步行約 5 分鐘；櫻木町站約 750 米）",
        "type": "設計系 4 星酒店（2023 年 5 月開業）",
        "highlight": "20 樓大堂連戶外露台，天台室內外泳池加按摩池",
        "rating": 4.4,
        "reviews": 1036,
        "ratingCheckedAt": TODAY,
        "priceBand": "以訂房平台即時報價為準（收錄時未見可靠公開參考價，故不列數字）",
        "address": "神奈川県横浜市西区みなとみらい3-3-3",
        "mapsUrl": maps("三井ガーデンホテル横浜みなとみらいプレミア", "神奈川県横浜市西区みなとみらい3-3-3"),
        "blurb": "2023 年 5 月開業的設計系酒店，賣點集中在頂樓：20 樓大堂連戶外露台，可以一路望住富士山方向同港未來天際線；天台有室內外加熱泳池同按摩池，喺呢個價位帶嘅橫濱酒店入面屬罕見配置。房間由 25 平方米起，對日本市區酒店算偏大，部分房型天氣好可以望到富士山。地點在港未來核心，行去 Cosmo World、杯麵博物館同紅磚倉庫都在步行圈。",
        "valuePoints": [
            "港未來站步行約 5 分鐘、櫻木町站約 750 米；去 Cosmo World、杯麵博物館、紅磚倉庫全部行得到。",
            "2023 年 5 月開業，硬件新；20 樓大堂連戶外露台係住客最常提的打卡位。",
            "天台設室內外加熱泳池與按摩池——同區同價位帶酒店極少見；另設住客免費健身室。",
            "房間由 25 平方米起，對日本市區酒店屬偏大；部分房型晴天可望富士山。",
            "Google 4.4 分、1,036 則評論，樣本足夠，屬穩定高分而非開幕虛高。",
            "2 樓有 Lawson，附近有 7-11 同 FamilyMart，宵夜唔使周圍搵。",
        ],
        "tips": [
            "館內冇大浴場／溫泉，想泡湯要另揀有溫泉的酒店。",
            "重視私隱的話，訂房時要求唔好訂面向公共區域或窗戶有遮擋的房型。",
            "位置在辦公區一帶，夜晚較靜；如果主要行程在 Pacifico 會議中心，留意步行距離。",
            "早餐自助評價「選擇充足但變化唔多」，唔一定要加購。",
            "評分與評論數為第三方引用快照，出發前請以 Google Map 即時顯示為準。",
        ],
        "sourceLabel": "Wanderlog 地點頁（引用 Google 評分 4.4 與 1,036 則評論）",
        "sourceUrl": "https://wanderlog.com/place/details/6303448",
        "addedAt": TODAY,
    },
]

HOTEL_ROTATION = [
    "神戶", "金澤", "大阪", "京都", "名古屋", "札幌",
    "沖繩", "廣島", "東京", "福岡", "仙台", "橫濱",
]


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    food = load(FOOD)
    hotel = load(HOTEL)

    # --- 去重保護 ---
    existing_eats = {e["id"] for e in food["eats"]}
    existing_hotels = {h["id"] for h in hotel["hotels"]}
    clash = [e["id"] for e in NEW_EATS if e["id"] in existing_eats]
    clash += [h["id"] for h in NEW_HOTELS if h["id"] in existing_hotels]
    if clash:
        print("[ABORT] 以下 id 已存在，未有寫入任何檔案：")
        for c in clash:
            print("  -", c)
        sys.exit(1)

    # --- 地區平衡檢查（城市是否都在 JP_CITY_REGION）---
    food["eats"].extend(NEW_EATS)
    food["meta"]["updated"] = TODAY
    food["meta"]["rotation"] = FOOD_ROTATION
    dump(FOOD, food)

    hotel["hotels"].extend(NEW_HOTELS)
    hotel["meta"]["updated"] = TODAY
    hotel["meta"]["rotation"] = HOTEL_ROTATION
    dump(HOTEL, hotel)

    print("[OK] 美食新增", len(NEW_EATS), "筆 → 總數", len(food["eats"]))
    print("[OK] 酒店新增", len(NEW_HOTELS), "筆 → 總數", len(hotel["hotels"]))
    for e in NEW_EATS:
        print("   A:", e["city"], e["name"], e["rating"], e["reviews"])
    for h in NEW_HOTELS:
        print("   B:", h["city"], h["name"], h["rating"], h["reviews"])


if __name__ == "__main__":
    main()
