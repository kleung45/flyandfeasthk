# -*- coding: utf-8 -*-
"""一次性寫入：日本美食（仙台／東北）＋日本酒店（仙台／東北）。
用完即刪。id 已存在即中止，避免重複條目。
"""
import json
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TODAY = "2026-10-05"


def q(text: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(text)


EATS = [
    {
        "id": "jp-sendai-kaku-burandom",
        "name": "牛たん料理 閣 ブランドーム本店",
        "nameEn": "Gyutan Ryori Kaku Burandom Honten",
        "city": "仙台",
        "area": "青葉區一番町（地下鐵廣瀨通站西4號出口步行約 3 分鐘，一番町拱廊地庫）",
        "cuisine": "牛舌",
        "signature": "炭烤厚切牛舌定食（たん焼き定食）、炙燒牛舌韃靼（たんタタキ）、牛舌刺身、牛舌咖喱",
        "rating": 4.5,
        "reviews": 2281,
        "ratingCheckedAt": TODAY,
        "priceRange": "¥2,000–5,000（たん焼き定食約 ¥2,280、特選炭燒約 ¥5,000）",
        "address": "宮城県仙台市青葉区一番町3-8-14 スズキアバンティビル B1F",
        "mapsUrl": q("牛たん料理 閣 ブランドーム本店 仙台市青葉区一番町3-8-14"),
        "blurb": "1988 年創業、只喺仙台市內開店嘅牛舌專門店，曾獲米芝蓮必比登推薦。佢係少數同時做「炭烤牛舌」同「炙燒牛舌韃靼」嘅店——定食只有一款，唔使諗厚切定薄切；招牌韃靼用半生熟手法上碟，厚切但軟到幾乎咬唔到筋。喺仙台一眾牛舌名店中，佢係本地人與識食旅客交叉票選得最前嘅一間。",
        "tips": [
            "唔接受訂位。平日開店前 15 分鐘到可以趕到第一輪，開店後人龍會好長，假日更要預一個鐘。",
            "炙燒牛舌韃靼（たんタタキ）係呢度嘅必點，套餐可加配或單點；注意韃靼只做晚市時段。",
            "「お通し」（座位小菜）要留意：只點定食唔收，但一叫酒或單品就會收 ¥418–500，會附一小碟燉牛舌。",
            "位置喺一番町拱廊地庫（地址寫作「スズキアバンティビル B1F」，舊稱鈴喜陶器店），唔熟路就用 Google Maps 帶路。",
        ],
        "sourceLabel": "Bigfang 仙台牛舌推薦排名表（列明 Google 評分 4.5／2,281 則，2026 年 3 月快照）；OMAKASE JapanEatinerary 亦列為仙台代表店家",
        "sourceUrl": "https://www.bigfang.tw/blog/post/sendai-gyutan",
        "addedAt": TODAY,
    },
    {
        "id": "jp-sendai-zenjiro-ekimae",
        "name": "たんや善治郎 仙台駅前本店",
        "nameEn": "Tanya Zenjiro Sendai Ekimae Honten",
        "city": "仙台",
        "area": "青葉區中央（JR 仙台站西口步行約 2 分鐘，AK 大廈 3F）",
        "cuisine": "牛舌",
        "signature": "上撰極厚真中たん定食（每時段限量）、牛舌香腸、牛尾湯配麥飯",
        "rating": 4.3,
        "reviews": 3108,
        "ratingCheckedAt": TODAY,
        "priceRange": "¥2,000–4,500（真中たん定食約 ¥3,500–3,960）",
        "address": "宮城県仙台市青葉区中央1-8-38 AKビル 3F",
        "mapsUrl": q("たんや善治郎 仙台駅前本店 仙台市青葉区中央1-8-38"),
        "blurb": "仙台牛舌兩大巨頭之一，站前本店出西口過天橋就到，係幾間分店中品質最穩定嘅一間。招牌「真中たん」取牛舌最厚嘅中段，切到接近一吋，咬落超軟、幾乎冇筋；全店只做鹽烤，唔靠醬汁遮味，所以肉味同炭香都食得出。餐牌仲有牛舌咖喱、牛舌餃子等變化，一家大細都啱。",
        "tips": [
            "唔接受訂位。先抽號碼牌，再用手機掃 QR 睇叫號進度，可以行去隔籬百貨商場逛住等。",
            "想食最靚部位就點「真中たん」，屬每時段限量，賣完就冇；午市同晚市高峰動輒等一個鐘以上。",
            "車站 3 樓「牛たん通り」分店座位只有廿幾個、排隊可以超過兩小時；行多兩分鐘去本店座位較多、更抵。",
            "可信用卡付款；麥飯通常可以免費添一碗，牛尾湯係標準配菜。",
        ],
        "sourceLabel": "Bigfang 仙台牛舌推薦排名表（列明 Google 評分 4.3／3,108 則，2026 年 3 月快照）",
        "sourceUrl": "https://www.bigfang.tw/blog/post/sendai-gyutan",
        "addedAt": TODAY,
    },
    {
        "id": "jp-sendai-tsukasa-higashiguchi",
        "name": "牛タン焼専門店 司 東口店（ダイワロイネットホテル店）",
        "nameEn": "Gyutan Yaki Senmonten Tsukasa Higashiguchi",
        "city": "仙台",
        "area": "宮城野區榴岡（JR 仙台站東口步行約 3–5 分鐘，Daiwa Roynet 酒店仙台 1F）",
        "cuisine": "牛舌",
        "signature": "牛舌定食（只分 2 枚4切／3 枚6切／4 枚8切）、牛舌漢堡扒咖喱",
        "rating": 4.3,
        "reviews": 2255,
        "ratingCheckedAt": TODAY,
        "priceRange": "¥2,000–4,000",
        "address": "宮城県仙台市宮城野区榴岡1-2-37 ダイワロイネットホテル仙台 1F",
        "mapsUrl": q("牛タン焼専門店 司 東口店 仙台市宮城野区榴岡1-2-37"),
        "blurb": "仙台牛舌「司」嘅東口店，開喺 Daiwa Roynet 酒店仙台一樓、Yodobashi 電器對面。佢唔玩厚切／牛舌芯／極上嘅花款——定食只有一款，淨係揀份量，靠澳洲最高級牛舌配特製醬汁醃足三日，再用日本產櫟炭燒到外脆內嫩。翻枱快、本地客多，行程趕嘅一餐最啱。",
        "tips": [
            "入口唔喺酒店正門，要繞到酒店側邊先見到店門；跟 Google Maps 行到最後一段要留意。",
            "冇外文菜單，唔識日文就跟圖片點最基本嘅「牛舌定食」，唔使煩惱揀部位。",
            "午市 11:00–14:00、晚市 17:00–22:30（L.O. 22:30），不定休；可信用卡付款。",
            "想加菜可以點山藥泥拌麥飯，或者牛舌漢堡扒咖喱（唔辣）。",
        ],
        "sourceLabel": "Bigfang 仙台牛舌推薦排名表（列明 Google 評分 4.3／2,255 則，2026 年 3 月快照）；Tabelog 店頁確認地址為 Daiwa Roynet 酒店仙台 1F",
        "sourceUrl": "https://www.bigfang.tw/blog/post/sendai-gyutan",
        "addedAt": TODAY,
    },
]

HOTELS = [
    {
        "id": "jp-sendai-onyado-nono",
        "name": "御宿 野乃 仙台（天然溫泉 杜都之湯）",
        "nameEn": "Onyado Nono Sendai Natural Hot Spring",
        "city": "仙台",
        "area": "青葉區本町（地下鐵南北線廣瀨通站東2號出口步行約 1 分鐘；JR 仙台站步行約 10–12 分鐘）",
        "type": "日式溫泉酒店（Dormy Inn 集團「御宿野乃」品牌，2022 年 3 月開業）",
        "highlight": "全館榻榻米赤腳行，頂樓 14 樓天然溫泉大浴場",
        "rating": 4.5,
        "reviews": 571,
        "ratingCheckedAt": TODAY,
        "priceBand": "以訂房平台即時報價為準（收錄時未見可靠公開參考價，故不列數字）",
        "address": "宮城県仙台市青葉区本町2-2-5",
        "mapsUrl": q("御宿野乃 仙台 仙台市青葉区本町2-2-5"),
        "blurb": "把日式旅館搬入市中心嘅一間：玄關脫鞋之後，由大堂到走廊到房間全部舖榻榻米，赤腳行足全間酒店。頂樓 14 樓係天然溫泉大浴場「杜都之湯」，有露天風呂、高溫乾桑拿同冷水池，泉水由同集團嘅 Dormy Inn 仙台海濱運送過來。早餐可以自己砌海鮮丼、食仙台名物烤牛舌，深夜仲有免費「夜鳴拉麵」。",
        "valuePoints": [
            "地下鐵廣瀨通站東 2 號出口就在門口（步行約 1 分鐘），落車即到酒店；由 JR 仙台站步行約 10–12 分鐘。",
            "頂樓 14 樓設天然溫泉大浴場「杜都之湯」，含露天風呂、高溫乾桑拿與冷水池——同價位帶市區商務酒店少有。",
            "房價已包：深夜免費夜鳴拉麵（21:30–23:00）、泡湯後免費冰棒與乳酸菌飲料、大堂免費飲品及漫畫區。",
            "全館 125 間房全部舖榻榻米（雙人房 69／Queen 房 11／雙床房 33／豪華雙床 11／無障礙房 1），館內設投幣式洗衣。",
            "Google 4.5 分、571 則評論；屬「御宿野乃」品牌東北首間分店，2022 年 3 月開業、硬件新。",
        ],
        "tips": [
            "由 JR 仙台站行過去要 10–12 分鐘，拖大件行李建議改用地鐵廣瀨通站（出口就在門口）。",
            "有住客反映大浴場繁忙時間會擠，想清靜就揀清晨或深夜時段。",
            "酒店不接受有紋身人士使用公共浴場，出發前留意政策。",
            "早餐以自助形式供應（加購房價較抵，約 ¥2,520–3,000／人），位置在 2 樓餐廳「旅籠」；唔加購都可以去附近商店街食。",
        ],
        "sourceLabel": "Wanderlog 地點頁（列明來自 Google 4.5 分／571 則評論）；GOJAPAN 酒店頁與 Dormy Inn 官網提供地址、房型與大浴場資料",
        "sourceUrl": "https://wanderlog.com/place/details/4843150",
        "addedAt": TODAY,
    },
    {
        "id": "jp-sendai-metropolitan-east",
        "name": "仙台東大都會酒店",
        "nameEn": "Hotel Metropolitan Sendai East",
        "city": "仙台",
        "area": "青葉區中央（JR 仙台站 3 樓直結，新幹線中央改札旁，步行約 0 分鐘）",
        "type": "車站直結 4 星酒店",
        "highlight": "同仙台站 3 樓直結，落新幹線幾分鐘入到房",
        "rating": 4.3,
        "reviews": 3450,
        "ratingCheckedAt": TODAY,
        "priceBand": "以訂房平台即時報價為準（收錄時未見可靠公開參考價，故不列數字）",
        "address": "宮城県仙台市青葉区中央1-1-1",
        "mapsUrl": q("ホテルメトロポリタン仙台イースト 仙台市青葉区中央1-1-1"),
        "blurb": "位置係全仙台最強：酒店本身就喺 JR 仙台站 3 樓，落新幹線之後唔使出閘、唔使淋雨，拖住行李幾分鐘就入到房。房間以車站酒店計偏大而且隔音好，大窗望市景。住客專用 Lounge 陳列宮城縣傳統工藝品，仲有免費咖啡；另有房客免費健身室。缺點係冇大浴場，同埋 check-in 有時要排隊。",
        "valuePoints": [
            "JR 仙台站 3 樓直結（新幹線中央改札旁），步行時間近乎 0 分鐘；樓下就係 S-PAL 百貨同郵局。",
            "住客專用 Lounge 全日免費咖啡，並展出宮城縣傳統工藝品——屬房價已包嘅附加價值。",
            "設房客免費健身室，同級車站酒店少見。",
            "房間以車站酒店計偏大、隔音好、有大窗景觀，浴室乾濕分離並附浴缸。",
            "Google 4.3 分、約 3,450 則評論，樣本極大，屬長期穩定高分而非靠少數好評拉高。",
        ],
        "tips": [
            "冇大浴場；想泡湯就要另揀有溫泉嘅酒店（同區的御宿野乃仙台就係一例）。",
            "Check-in 系統高峰期要排隊，建議避開 15:00–17:00 入住尖峰。",
            "早餐係自助形式，用宮城在地食材，評價「選擇充足但唔算驚喜」，唔一定要加購。",
            "酒店在車站東側，主要商店街同食街集中喺西口，行過去要預 5–10 分鐘（站內有通道）。",
        ],
        "sourceLabel": "Wanderlog 地點頁（列明來自 Google 4.3 分／3,450 則評論）＋ Google 酒店實體頁（4.3／3,452 則）",
        "sourceUrl": "https://wanderlog.com/place/details/842669",
        "addedAt": TODAY,
    },
]

EAT_ROTATION = [
    "高松", "金澤", "橫濱", "名古屋", "神戶", "廣島",
    "大阪", "京都", "沖繩", "福岡", "札幌", "東京", "仙台",
]
HOTEL_ROTATION = [
    "橫濱", "神戶", "金澤", "大阪", "京都", "名古屋",
    "札幌", "沖繩", "廣島", "東京", "福岡", "仙台",
]


def add(path: Path, key: str, items: list[dict], rotation: list[str]) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    have = {e.get("id") for e in data.get(key) or []}
    dup = [i["id"] for i in items if i["id"] in have]
    if dup:
        raise SystemExit(f"中止：{path.name} 已存在 id {dup}，可能本輪已執行過。")
    data.setdefault(key, []).extend(items)
    data.setdefault("meta", {})["updated"] = TODAY
    data["meta"]["rotation"] = rotation
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(data[key])


n_eat = add(ROOT / "japan.json", "eats", EATS, EAT_ROTATION)
n_hotel = add(ROOT / "japan-hotels.json", "hotels", HOTELS, HOTEL_ROTATION)
print(f"japan.json eats={n_eat}（新增 {len(EATS)}）")
print(f"japan-hotels.json hotels={n_hotel}（新增 {len(HOTELS)}）")
