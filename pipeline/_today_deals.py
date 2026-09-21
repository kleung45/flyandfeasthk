# -*- coding: utf-8 -*-
"""暫存腳本：寫入 2026-09-21 當日新優惠（draft + store 同步）"""
import json, os, sys, shutil, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = "2026-09-21"

DEALS = [
    {
        "id": "dining-hangfong-windowcafe-flashsale-20260921",
        "category": "dining",
        "title": "自助晚餐限量 1 折，低至 HK$74／位",
        "subtitle": "佐敦恆豐酒店 紅煙窗餐廳 · 紐西蘭「蠔」華盛宴",
        "venue": "紅煙窗餐廳 The Window Café · 佐敦彌敦道 222 號恆豐酒店 2 樓（佐敦站 E 出口）",
        "priceLabel": "KKday 快閃限量 1 折 HK$74／位；買一送一（碼 FBWPRUD／FBWPD50）折後人均低至 HK$376",
        "priceValue": 74,
        "originalLabel": "晚餐原價以 KKday 結帳頁為準；另設 2 大 1 小套票人均低至 HK$367",
        "discountPct": 90,
        "endsAt": "2026-09-21T23:59:00+08:00",
        "period": "KKday 預訂期 2026-09-15 12:00 至 09-21 23:59；用餐日期 2026-09-15 至 10-31（9/19、9/25 買一送一及套票不適用）",
        "summary": "佐敦恆豐酒店紅煙窗餐廳「紐西蘭『蠔』華盛宴」海鮮自助晚餐經 KKday 快閃：限量 1 折低至 HK$74／位；用優惠碼 FBWPRUD 或 FBWPD50 買一送一，折後人均低至 HK$376。任食即開紐西蘭生蠔、法國麵包蟹、鱈場蟹腳，熱盤有燒原條澳洲和牛西冷。",
        "highlights": [
            "限量 1 折低至 HK$74／位（名額極少，先到先得）",
            "買一送一用碼 FBWPRUD／FBWPD50 後人均低至 HK$376",
            "任食即開紐西蘭生蠔、法國麵包蟹、鱈場蟹腳、三文魚刺身",
            "Häagen-Dazs 雪糕及招牌北海道牛乳布甸",
            "預訂期只到 9/21 23:59，用餐日期去到 10/31；以 KKday 頁面為準"
        ],
        "url": "https://www.kkday.com/zh-hk/product/284215",
        "sourceLabel": "KKday 產品頁 · U Food 報導（2026-09-15）",
        "sourceUrl": "https://ufood.com.hk/restaurant/news/detail/20109966/",
        "tags": ["酒店自助餐", "1 折", "佐敦", "生蠔"],
        "sample": False
    },
    {
        "id": "dining-harbourplaza8degrees-buffet-20260921",
        "category": "dining",
        "title": "熱石海鮮自助晚餐 5 折，平日成人 HK$329／位",
        "subtitle": "土瓜灣 8 度海逸酒店 8 度餐廳 · 下午茶買一送一人均 HK$99",
        "venue": "8 度餐廳 Café 8 Degrees · 土瓜灣九龍城道 199 號 8 度海逸酒店地下大堂",
        "priceLabel": "KKday 低至 5 折：熱石海鮮自助晚餐 平日成人 HK$329／位、長者 HK$284、兒童 HK$249（週末成人 HK$369）",
        "priceValue": 329,
        "originalLabel": "晚餐原價成人 HK$768／位（現場另收原價加一服務費）；假日自助午餐原價 HK$528／位",
        "discountPct": 50,
        "endsAt": "2026-09-21T23:59:00+08:00",
        "period": "KKday 預訂期 2026-09-15 18:00 至 09-21 23:59；使用日期 2026-09-16 至 10-31",
        "summary": "土瓜灣 8 度海逸酒店 8 度餐廳經 KKday 快閃：熱石海鮮自助晚餐低至 5 折，平日成人 HK$329／位、週末 HK$369／位；同場假日自助午餐 5 折成人 HK$254，果漾蜜語下午茶套餐買一送一 HK$198／2 位（人均 HK$99）。",
        "highlights": [
            "熱石海鮮自助晚餐 5 折：平日成人 HK$329／位（原價 HK$768）",
            "假日自助午餐 5 折成人 HK$254／位（原價 HK$528）",
            "果漾蜜語下午茶套餐買一送一 HK$198／2 位，人均 HK$99（15:00–17:00）",
            "2 位成人可免費帶 1 位 5 歲或以下兒童入場（須自行向餐廳辦理訂位）",
            "冰鎮鱈場長腳蟹、蟹粉扣黃金鮑魚、即煎日本岩手牛；預訂期只到 9/21 23:59"
        ],
        "url": "https://www.kkday.com/zh-hk/product/115719",
        "sourceLabel": "KKday 產品頁 · myTV SUPER 東張+ 及 GroupBuya 報導（2026-09-15）",
        "sourceUrl": "https://www.mytvsuper.com/tc/scoopplus/lifestyle/jetso/17894458820886",
        "tags": ["酒店自助餐", "5 折", "土瓜灣", "海鮮"],
        "sample": False
    },
    {
        "id": "dining-conrad-gardencafe-bogo-20260921",
        "category": "dining",
        "title": "咖啡園自助午餐買一送一，人均 HK$299（已包加一）",
        "subtitle": "金鐘港麗酒店 Garden Café · 樂聚廊下午茶買一送一人均 HK$215",
        "venue": "咖啡園 Garden Café · 金鐘道 88 號太古廣場港麗酒店大堂低座（金鐘站 F 出口）",
        "priceLabel": "KKday 買1送1：咖啡園自助午餐平日 2 位 HK$598（人均 HK$299，已包加一）／週末 2 位 HK$622（人均 HK$311）",
        "priceValue": 299,
        "originalLabel": "午餐原價 HK$548／位（已包括加一）；樂聚廊下午茶原價 HK$757／2 位",
        "discountPct": 50,
        "endsAt": "2026-09-24T23:59:00+08:00",
        "period": "KKday 預訂期 2026-09-18 18:00 至 09-24 23:59；用餐日期 2026-09-19 至 11-30",
        "summary": "金鐘港麗酒店咖啡園 Garden Café 自助午餐經 KKday 買一送一：平日 2 位 HK$598、週末 2 位 HK$622，已包加一服務費。冰鎮海鮮有鱈場蟹腳、海蝦、青口、蜆，配日式刺身壽司、即煮喇沙、燒西冷牛肉；樂聚廊「仲夏果韻」下午茶同樣買一送一，2 位 HK$430（人均 HK$215）。",
        "highlights": [
            "咖啡園自助午餐買一送一：平日 2 位 HK$598（人均 HK$299，已包加一）",
            "週末及公眾假期 2 位 HK$622（人均 HK$311）",
            "樂聚廊「仲夏果韻」下午茶買一送一 2 位 HK$430（人均 HK$215，15:00–17:30）",
            "海鮮焦點：鱈場蟹腳、海蝦、青口、蜆、日式刺身壽司、即煮馬來西亞叻沙",
            "預訂期至 9/24 23:59，用餐日期去到 11/30；名額有限，以 KKday 頁面為準"
        ],
        "url": "https://www.kkday.com/zh-hk/product/135619",
        "sourceLabel": "KKday 產品頁 · myTV SUPER 東張+ 及 U Food 報導（2026-09-18）",
        "sourceUrl": "https://ufood.com.hk/restaurant/news/detail/3098019/",
        "tags": ["酒店自助餐", "買一送一", "金鐘", "下午茶"],
        "sample": False
    },
    {
        "id": "dining-bpinternational-parkcafe-bogo-20260921",
        "category": "dining",
        "title": "園林閣自助晚餐買一送一，人均 HK$293",
        "subtitle": "尖沙咀龍堡國際 園林閣咖啡室 · 東南亞主題自助晚餐",
        "venue": "園林閣咖啡室 Café by the Park · 尖沙咀柯士甸道 8 號龍堡國際（佐敦站 C1 出口）",
        "priceLabel": "Klook 買1送1：東南亞主題自助晚餐 2 位 HK$586（人均 HK$293）；自助午餐買1送1 人均 HK$173 起",
        "priceValue": 293,
        "originalLabel": "自助晚餐原價 HK$1,074／2 位（人均 HK$537）",
        "discountPct": 50,
        "endsAt": "2026-09-21T23:59:00+08:00",
        "period": "Klook 開售 2026-09-08 12:00 至 09-21；適用日期 2026-09-09 至 09-30",
        "summary": "尖沙咀龍堡國際園林閣咖啡室經 Klook 買一送一：東南亞主題自助晚餐 2 位 HK$586，人均 HK$293（原價 HK$1,074）。每位客人獲贈蟹肉素翅灌湯餃一客，冷盤有雪花蟹爪、凍熟青口、凍熟蜆、凍熟蝦，仲有泰式柚子沙律同三文魚中東米沙律，無限暢飲精選紅白酒。",
        "highlights": [
            "自助晚餐買1送1 2 位 HK$586，人均 HK$293（原價 HK$1,074）",
            "每位獲贈「蟹肉素翅灌湯餃」一客",
            "雪花蟹爪、凍熟青口、凍熟蜆、凍熟蝦、壽司刺身任食",
            "無限暢飲精選紅、白餐酒",
            "開售期只到 9/21；自助午餐買1送1 人均 HK$173 起，以 Klook 頁面為準"
        ],
        "url": "https://www.klook.com/zh-HK/activity/201891-bp-international-cafe-by-the-park-lunch-buffet-dinner-buffet/",
        "sourceLabel": "Klook 產品頁 · GroupBuya 報導 · HKBuffetHunter 買一送一合集（9/21 更新）",
        "sourceUrl": "https://www.groupbuya.com/jetso/554708",
        "tags": ["酒店自助餐", "買一送一", "尖沙咀", "東南亞"],
        "sample": False
    },
    {
        "id": "dining-parkhotel-parkcafe-bogo-20260921",
        "category": "dining",
        "title": "越法風味自助午餐買一送一，人均 HK$190.8（已含加一）",
        "subtitle": "尖沙咀百樂酒店 Park Café · 官網直接預訂最抵",
        "venue": "Park Café · 尖沙咀漆咸道南 61-65 號百樂酒店 4 樓（尖沙咀站 P3 出口）",
        "priceLabel": "官網買1送1（每位付 HK$100 訂金）：平日自助午餐 2 位 HK$381.6（人均 HK$190.8，已含加一）",
        "priceValue": 190.8,
        "originalLabel": "自助午餐原價平日成人 HK$318／位、週末及公眾假期 HK$348／位（另收加一）；晚餐買1送1 折後人均 HK$370.8 起",
        "discountPct": 50,
        "endsAt": "2026-10-01T23:59:00+08:00",
        "period": "官網買一送一優惠至 2026-10-01；自助午餐供應 2026-07-03 至 10-01（12:00–14:30）；須網上預訂並付每位 HK$100 訂金、提前 1 小時預訂",
        "summary": "尖沙咀百樂酒店 Park Café 官網推「邂逅越法滋味」自助午餐買一送一（星期一至五）：每人付 HK$100 訂金，2 位 HK$381.6、人均 HK$190.8 已含加一。主打越式燒豬頸肉濱海、越南蔗蝦、法式紅酒燴雞腿、法式蝦多士、即焗芝士蛋白撻。同場自助晚餐（一至日）及週末下午茶自助餐亦同步買一送一。",
        "highlights": [
            "平日自助午餐買一送一：2 位 HK$381.6，人均 HK$190.8（已含加一）",
            "晚餐買一送一折後每位低至 HK$370.8 起；週末下午茶自助餐同樣買一送一",
            "焦點：越式燒豬頸肉濱海、越南蔗蝦、法式紅酒燴雞腿、法式蝦多士、即焗芝士蛋白撻",
            "果汁、咖啡、茶無限暢飲",
            "須於酒店官網預訂並付每位 HK$100 訂金，提前 1 小時預訂；優惠至 10/1"
        ],
        "url": "https://www.parkhotelgroup.com/park-hotel-hong-kong/offers/savouring-viet-n-french-lunch-buffet",
        "sourceLabel": "百樂酒店官網優惠頁 · GroupBuya 報導",
        "sourceUrl": "https://www.groupbuya.com/jetso/554515",
        "tags": ["酒店自助餐", "買一送一", "尖沙咀", "越法"],
        "sample": False
    },
]

draft_path = os.path.join(ROOT, "pipeline", "drafts", TODAY + ".json")
store_path = os.path.join(ROOT, "pipeline", "store.json")

# ---- 1. 讀取既有 draft（同日手動補跑過就合併，不覆蓋）----
existing = []
if os.path.exists(draft_path):
    with open(draft_path, encoding="utf-8") as f:
        existing = json.load(f).get("deals", [])
    print("既有 draft：%d 筆" % len(existing))

store = json.load(open(store_path, encoding="utf-8"))
store_ids = {d["id"] for d in store["deals"]}

merged = list(existing)
merged_ids = {d["id"] for d in existing}
added = []
for d in DEALS:
    if d["id"] in merged_ids:
        continue
    if d["id"] in store_ids:
        print("略過（已在 store）：", d["id"])
        continue
    merged.append(d)
    merged_ids.add(d["id"])
    added.append(d)

with open(draft_path, "w", encoding="utf-8") as f:
    json.dump({"date": TODAY, "deals": merged}, f, ensure_ascii=False, indent=2)
print("draft 已寫入：%s（%d 筆）" % (draft_path, len(merged)))

# ---- 2. 同步寫入 store.json（postedFacebook／postedThreads 不預設）----
shutil.copy2(store_path, store_path + ".bak")
for d in added:
    store["deals"].append(d)
store["meta"]["sample"] = False
store["meta"]["updated"] = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
store["meta"]["updatedAt"] = store["meta"]["updated"]
with open(store_path, "w", encoding="utf-8") as f:
    json.dump(store, f, ensure_ascii=False, indent=2)
print("store 已更新：新增 %d 筆，總數 %d 筆" % (len(added), len(store["deals"])))
for d in added:
    print("  +", d["id"])
