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
HOTELS_FILE = ROOT / "japan-hotels.json"
DRIVE_FILE = ROOT / "japan-drive.json"
BARS_FILE = ROOT / "japan-bars.json"
SITEMAP = PROJECT / "sitemap.xml"

# 日本美食專欄：城市顯示次序（未列出的城市按首次出現排在後面）
JAPAN_CITY_ORDER = ["東京", "大阪", "京都", "神戶", "名古屋", "橫濱", "福岡", "札幌", "沖繩"]

# 地區歸納：城市 → 地區頁（/japan/<key>/）。收錄新城市時，把城市加進對應地區即可；
# 新地區要同時在 JP_REGIONS 加條目（名稱與簡介），地區頁與 sitemap 會自動生成。
JP_REGIONS = {
    "kanto": {
        "name": "關東",
        "intro": "以東京領銜，連同橫濱等周邊城市。拉麵、壽司到深水埗式街坊食堂同高級割烹並存，"
                 "選擇多到唔使愁，最難係分辨邊間值得專程去——這頁的排行就係幫你收窄範圍。",
    },
    "kansai": {
        "name": "關西",
        "intro": "大阪、京都、神戶組成的美食重鎮：大阪燒與章魚燒的庶民味、京都的懷石與湯葉、"
                 "神戶牛的洋食傳統。關西人對飲食嘅執著全日本聞名，高分小店密度數一數二。",
    },
    "chubu": {
        "name": "中部／東海",
        "intro": "以名古屋為中心，味噌煮、味噌豬排與手羽先獨樹一幟，係日本國內都公認「食風自成一派」的地區。",
    },
    "kyushu": {
        "name": "九州",
        "intro": "豚骨拉麵的發源地，博多豚骨、熊本黑麻油與鹿兒島湯麵各有派系；"
                 "加上屋台文化與海鮮，福岡更被稱為日本最適合「食到扶牆走」的城市。",
    },
    "hokkaido": {
        "name": "北海道",
        "intro": "味噌拉麵發源地札幌、湯咖哩與函館鹽味拉麵，再配上全國頂級的海產同乳製品，"
                 "係「食材本身就是賣點」的地區。",
    },
    "chugoku": {
        "name": "中國／瀨戶內",
        "intro": "廣島蠔、尾道拉麵與瀨戶內海的海鮮料理，食風低調但水準極高。",
    },
    "okinawa": {
        "name": "沖繩",
        "intro": "琉球料理自成一格：沖繩麵、豬肉料理與塔可飯，混雜美式與亞洲風味，係日本最「唔日本」又最有趣嘅食區。",
    },
    "tohoku": {
        "name": "東北",
        "intro": "仙台牛舌、青森蘋果與秋田米鄉，山海食材豐富但觀光密度低，"
                 "係近年最多人「專程去食」的地區之一，價錢亦普遍比東京大阪親民。",
    },
    "shikoku": {
        "name": "四國",
        "intro": "香川的讚岐烏冬、愛媛的鯛魚飯與高知的鰹魚たたき，加上瀨戶內的島嶼與海鮮，"
                 "係日本最被低估的食區之一。",
    },
}
JP_REGION_ORDER = ["kanto", "kansai", "chubu", "kyushu", "hokkaido", "tohoku", "chugoku", "shikoku", "okinawa"]
JP_CITY_REGION = {
    "東京": "kanto", "橫濱": "kanto",
    "大阪": "kansai", "京都": "kansai", "神戶": "kansai",
    "名古屋": "chubu", "金澤": "chubu",
    "福岡": "kyushu",
    "札幌": "hokkaido",
    "仙台": "tohoku",
    "廣島": "chugoku",
    "沖繩": "okinawa",
}

# 酒店專欄的地區簡介與美食版分開寫：美食版講食風，酒店版要講住宿成本、
# 季節浮動與「住邊抵」的實際考量，直接沿用美食文案會完全離題。
JP_HOTEL_REGION_INTRO = {
    "kanto": "東京住宿貴而且房細，但揀對位置同房型，一樣有「唔肉赤又有質素」嘅選擇。"
             "關東一帶的高分酒店集中在山手線沿線，以及淺草、上野等舊區——"
             "本頁只收錄行去車站夠近、評論樣本夠大嘅一類。",
    "kansai": "大阪市中心房價比東京親民；京都就要看季節，賞楓賞櫻期間全城加價。"
              "關西最值得計嘅係「位置分」：心齋橋、四條步行圈內嘅酒店，"
              "省落嘅交通時間同車費就係實際回報。",
    "chubu": "名古屋係被低估嘅住宿城市：同級酒店價錢通常比東京大阪低一截，"
             "而且唔少酒店附設天然溫泉大浴場。市中心榮、伏見一帶步行距離短，"
             "商務同觀光都合用。",
    "kyushu": "福岡機場距離市中心只需地鐵兩個站，係全日本最方便嘅入境城市之一，"
              "所以「住市中心」嘅性價比特別高——博多、天神一帶行得到就唔使買地鐵日票。",
    "hokkaido": "札幌住宿最大嘅變數係雪季同週末：同一間房閒日同週六可以差一倍以上。"
                "揀狸小路、薄野一帶有蓋商店街旁邊嘅酒店，落雪天出入都唔使捱風。",
    "tohoku": "東北係全日本住宿最親民嘅地區之一，仙台市中心商務酒店價位通常只及東京一半。"
              "本頁優先收錄近仙台站、設大浴場嘅一類。",
    "chugoku": "廣島、岡山一帶酒店價錢平穩，適合以廣島為基地往返宮島、尾道。"
               "留意近路面電車站嘅選擇，出入比想像中方便。",
    "okinawa": "沖繩住宿要分「那霸市區」同「度假區」兩種玩法：市區酒店近單軌電車、"
               "價錢平；度假區房價高但設施多。本頁會講清楚你買緊邊種。",
}
HOTEL_REGION_INTRO_FALLBACK = (
    "本頁收錄此地區「評分 × 評論規模 × 車站距離 × 房型設施」同時達標嘅酒店，"
    "房價一律不寫死，請自行填日期格價。"
)

# 自駕專欄的地區簡介（第三份，與美食、酒店都不同）。
# 自駕版要講「條路本身值唔值得開」、季節風險與車種限制。
JP_DRIVE_REGION_INTRO = {
    "kanto": "東京近郊的山路密度係全日本最高——由市中心出發一個多小時，就可以上到箱根、"
             "伊豆一帶的山脊。呢區路線多數係私人經營嘅觀光收費道路，路面做得好，"
             "但車種限制同收站時間要特別留意，唔少路段禁止 125cc 以下電單車。",
    "chubu": "中部係自駕天堂：長野高原、靜岡伊豆、岐阜山區，海拔由海邊一路拉到近 2,000 米。"
             "但要記住呢區有全日本最嚴嘅一條規矩——部分高山道路全年禁止私家車同電單車進入，"
             "唔查清楚就白行一轉。",
    "kansai": "關西的山路多數集中在京都、滋賀同兵庫北部，多為有料觀光道路，"
              "坡度與彎道都溫和，適合新手。冬季有雪，部分路段會要求裝雪胎或鏈條。",
    "chugoku": "中國地方最出名嘅唔係山路，而係「跨海」——瀬戸内しまなみ海道係全日本唯一"
               "讓 125cc 以下原付都可以過海嘅本四連絡橋，對騎細車嘅人嚟講係難得嘅選項。",
    "kyushu": "九州嘅賣點係火山地形：阿蘇一帶嘅草原同火口景觀在日本其他地方睇唔到。"
              "呢區多數路線免費，但火口一帶通行會隨火山活動隨時封閉，出發前一定要查即時資訊。",
    "hokkaido": "北海道係「距離感」同「季節感」最強嘅自駕區：景點之間動輒一兩個鐘，"
                "而同一條路夏天同冬天係兩條完全唔同嘅路。呢區亦係唯一有 HEP 高速公路通行證"
                "的地區，長途走的話值得計一計數。",
    "tohoku": "東北自駕成本係全日本最低之一，國道車流量少、風景開揚，"
              "適合唔想同人爭路嘅人。冬季由 11 月起就開始落雪，山區路段會封閉。",
    "shikoku": "四國嘅山路以「窄、彎、車少」見稱，加上瀬戶内海嘅跨海大橋，"
               "係近年在日本車友之間冒起得最快嘅自駕區。",
    "okinawa": "沖繩係「開車先玩得到」嘅地方：公共交通覆蓋有限，景點之間靠車。"
               "好處係路況簡單、免費大橋多；壞處係北部路燈少、距離遠，唔好安排夜間長途。",
}
DRIVE_REGION_INTRO_FALLBACK = (
    "本頁收錄此地區已核實的自駕路線，包含里程、通行費、車種限制與季節封閉資訊，"
    "所有數字都附上來源與核對日期。"
)

# 自駕實務指南（/japan/drive/guide/）。全部內容都有下方 DRIVE_GUIDE_SOURCES 的來源，
# 數字類資料一律標明核對日期。
DRIVE_GUIDE_SECTIONS: list[tuple[str, list[str], list[str]]] = [
    (
        "一、證件：香港人自駕日本要帶三份正本",
        [
            "日本只承認「1949 年日內瓦公約」樣式的國際駕駛許可證（IDP）。"
            "東京警視廳寫得很清楚：即使係日內瓦公約締約國發出的 IDP，"
            "如果樣式係按其他公約（例如 1968 年維也納公約）發出，在日本一樣唔可以駕駛。",
            "有效期係「雙重一年」：IDP 由發出日起一年內，而且由入境日本當日起一年內。"
            "兩個條件要同時滿足，所以唔好帶住一張就快到期嘅 IDP 出發。",
        ],
        [
            "香港正式駕駛執照【正本】——影本、手機截圖一律唔接受，租車公司會直接拒租。",
            "國際駕駛許可證（IDP，1949 日內瓦公約樣式）【正本】。",
            "護照【正本】。",
            "實體信用卡（用作押金與身份核對，唔可以用親屬嘅卡）。",
        ],
    ),
    (
        "二、電單車：香港人騎得到，但有三個關卡",
        [
            "好消息係香港人可以騎：持香港或澳門的正式電單車駕駛執照，"
            "加上 IDP 與護照，就可以在日本租電單車。"
            "壞消息係有三個容易中招嘅關卡，出發前一定要逐項對清楚。",
        ],
        [
            "① 暫准駕駛執照（P 牌）唔接受。日本租車公司只接受正式駕駛執照，"
            "拎 P 牌去會直接被拒。",
            "② IDP 要「A 欄」蓋章。要騎 50cc 以上的電單車，"
            "IDP 的 A 欄（motorcycle）必須蓋有許可章；50cc 以下就只要 B、C、D 或 E 任何一欄即可。"
            "所以去運輸署辦 IDP 時，記得同職員講清楚要包括電單車類別。",
            "③ 個別道路會再額外限制排氣量。例如箱根ターンパイク同伊豆スカイライン都禁止 "
            "125cc 以下電單車、自行車及行人進入，即係話就算你證件齊全、"
            "租到的係 125cc 小車，呢兩條路都入唔到。",
            "年齡門檻：租車公司普遍要求 18 歲以上（部分要求 21 歲以上並持有駕照一年以上）；"
            "電單車押金通常要 ¥20,000–50,000 的信用卡額度。",
        ],
    ),
    (
        "三、電單車「唔可以行」的路段——最值得事先知道的坑",
        [
            "日本有幾條在網上極出名、但實際上外國旅客根本入唔到嘅山路。"
            "呢啲路經常出現在「日本十大最美山路」名單，但名單好少提管制，"
            "結果每年都有旅客白行一轉。出發前對一對以下名單。",
        ],
        [
            "乗鞍スカイライン（岐阜・長野）：全長 14.4 公里，由平湯峠（1,684 米）上到畳平"
            "（2,702 米，日本道路最高點）。2003 年 5 月 15 日起全面禁止私家車與電單車，"
            "全年適用——只有巴士、的士、自行車及獲授權車輛可以進入。"
            "電單車在法律上屬「私家車」，一樣唔准入。",
            "同系的乗鞍エコーライン（長野側）：三本滝以上路段同樣禁止。",
            "富士スバルライン：2026 年 7 月 3 日至 9 月 10 日期間曾實施私家車管制，"
            "要改乘接駁車。每年管制日期唔同，夏季去富士山五合目要先查。",
            "志賀草津高原ルート（國道 292 號）：免費，最高點渋峠 2,172 米係日本國道最高點。"
            "冬季封閉，2025–26 年度的封閉期為 11 月 12 日至 4 月 22 日。",
            "記住一個通則：山岳道路嘅入口標示牌有時只用日文小字列出月份與時段，"
            "「睇唔明就當唔准」，唔好用「冇寫明禁止」推斷可以入。",
        ],
    ),
    (
        "四、高速公路通行證：外國旅客專用的「吃到飽」",
        [
            "日本高速道路係按里程收費，長途走起來可以好貴，"
            "所以針對訪日旅客有幾種定額通行證（Expressway Pass）。"
            "重點係：通行證唔包車租，亦唔包 ETC 卡租金，兩樣都要另外俾。",
            "購買資格只有兩種人：持非日本護照的訪日旅客，或長居海外的日本國民。"
            "買嘅時候要出示護照同駕照，而且在租車時一次過買，唔可以中途加購或延長。",
        ],
        [
            "北海道（HEP）：4／5／6／7／8 日，普通車 ¥7,700／9,600／11,600／13,500／15,400；"
            "軽自動車等 ¥6,200／7,700／9,300／10,800／12,300。最短 4 日。",
            "東北（TEP）：4–8 日，普通車 ¥8,500–17,000；軽自動車等 ¥6,800–13,600。"
            "注意：官方公佈 TEP 於 2026 年 9 月 30 日結束受理，如要使用請先確認官方最新說明。",
            "新潟（NEP）：只有 3 日一種，普通車 ¥6,200、軽自動車等 ¥4,900。"
            "只限 Toyota Rent a Car 在新潟縣內指定分店發售。",
            "山陰・瀬戶內・四國（SEP）：3–10 日，¥10,700–17,700（不分車型）。",
            "九州（KEP）：2–10 日，普通車 ¥6,200–23,800（不分車型）。",
            "已經停售：全國版 Japan Expressway Pass（JEP）同中部版 Central Nippon "
            "Expressway Pass（CEP）都已停止提供。截至 2026 年 8 月，中部地區冇針對訪日旅客嘅定額通行證。",
        ],
    ),
    (
        "五、ETC、保險與冬季",
        [
            "租車公司一般可以借出 ETC 卡（收費約每日／每程小額費用，例如 ¥330 左右），"
            "插入車上的 ETC 車載器就可以不停車過收費站，費用還車時結算。"
            "ETC 本身有深夜與假日折扣，所以就算唔買通行證都值得借。"
            "留意少數觀光道路只收「ETCX」（多用途 ETC）而唔收一般 ETC，伊豆スカイライン就係例子。",
            "保險係最容易出事的一環。日本法律要求的第三者責任險已包含在租金內，"
            "但租賃車輛本身的損害通常要自己負——除非加購 CDW（免責補償）。"
            "更易忽略的是 NOC（營業損失費）：車輛維修期間無法出租，租車公司會按日收費，"
            "全損則多為一筆定額。呢筆錢獨立於維修費，就算你買了 CDW 都可能要付。"
            "所以建議直接買包含 CDW＋NOC 的全保障方案。",
            "冬季（約 12 月至 3 月）去北海道、東北、長野、北陸一帶，要預備雪胎或鏈條；"
            "比叡山ドライブウェイ 官方就明文要求落雪或積雪時裝雪胎或帶鏈條。"
            "另外，租車合約一般禁止行未鋪裝道路，保險亦唔保，所以火山砂石路要避開。",
        ],
        [],
    ),
    (
        "六、落地後最容易犯的三件事",
        [
            "以上都係文件層面，真正落地之後，最多人出事嘅其實係路面習慣。",
        ],
        [
            "靠左行駛、右舵車。香港人本身已經靠左駛，適應上比歐美旅客著數，"
            "但要注意日本方向燈桿與水撥桿位置與香港車相反，落雨時容易開錯。",
            "街邊幾乎完全唔可以停車。日本對違泊係「零容忍」，"
            "罰款可達 ¥15,000，車輛有機會在短時間內被拖走；"
            "一定用 coin parking（投幣停車場）或酒店車位。",
            "睇清「止まれ」標誌。日本停止標誌要求完全停定再左右確認，"
            "唔係慢車就當做咗。另外日本高速公路限速 100km/h、一般道路 50km/h，"
            "標誌優先，唔好靠「跟車流」判斷。",
        ],
    ),
]

DRIVE_GUIDE_SOURCES: list[tuple[str, str]] = [
    ("警視庁「外国で取得した国際運転免許証で日本国内を運転するには」"
     "（1949 日內瓦公約樣式、雙重一年有效期、3 個月規則）",
     "https://www.keishicho.metro.tokyo.lg.jp/menkyo/menkyo/kokugai/kokusaimenkyo.html"),
    ("Rental819「The 3 Fundamental Items to ride in Japan」"
     "（IDP 必須為 1949 日內瓦公約；A 欄蓋章才可騎 50cc 以上）",
     "https://rental819.com/doc/3items"),
    ("Rental819 香港站「Can I rent a motorcycle in Japan with a Hong Kong licence?」"
     "（香港／澳門正式電單車駕照＋IDP 可租；P 牌不接受）",
     "https://rental819.hk/en/guide/licence"),
    ("JADO Moto「Japan Alps Motorcycle Guide」（乗鞍スカイライン／エコーライン全年禁止私家車與電單車、"
     "志賀草津高原ルート冬季封閉期，2026 年 8 月核實）",
     "https://www.jadomoto.com/zh-hant/blogs/guides/japan-alps-motorcycle-guide"),
    ("JNTO（日本政府觀光局）「Expressway Passes」"
     "（HEP／TEP／NEP／SEP／KEP 價格與購買資格；JEP 與 CEP 已停售）",
     "https://www.japan.travel/en/au/plan/expressway-passes/"),
    ("一般社団法人 日本観光自動車道協会（各觀光收費道路的區間與料金官方登載）",
     "https://tourism-road.or.jp"),
    ("比叡山ドライブウェイ 官方料金與營業時間 PDF（雪胎／鏈條要求）",
     "https://www.hieizan.gr.jp/design/pdf/2023_2024_winter.pdf"),
]

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
        ("/japan/hotels/", "日本酒店", "japan-hotel"),
        ("/japan/drive/", "日本自駕", "japan-drive"),
        ("/japan/bars/", "日本酒吧", "japan-bar"),
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
        '<a href="/japan/hotels/">日本酒店</a>'
        '<a href="/japan/drive/">日本自駕</a>'
        '<a href="/japan/bars/">日本酒吧</a>'
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


def maps_embed_html(e: dict, kind: str = "餐廳") -> str:
    src = maps_embed_src(e)
    if not src:
        return ""
    name = e.get("name") or kind
    scene = {"餐廳": "店面實景相", "酒店": "外觀與周邊實景相",
             "酒吧": "店面實景與所在大廈位置"}.get(kind, "路線周邊實景與街景")
    return (
        '<figure class="maps-embed">'
        f'<iframe src="{esc(src)}" title="{esc(name)} 嘅 Google Maps 地圖與實景相片" '
        'loading="lazy" allowfullscreen referrerpolicy="no-referrer-when-downgrade"></iframe>'
        f'<figcaption class="jp-note">地圖卡由 Google Maps 官方嵌入，可直接睇到{scene}、'
        "評分同街景；以 Google Map 即時顯示為準。</figcaption>"
        "</figure>"
    )


def region_key_of(e: dict) -> str | None:
    return JP_CITY_REGION.get(str(e.get("city") or ""))


def japan_regions_in_use(eats: list[dict]) -> list[str]:
    """有收錄的地區 key，按展示次序排列。"""
    present = {region_key_of(e) for e in eats}
    present.discard(None)
    return [k for k in JP_REGION_ORDER if k in present]


def japan_ranked(pool: list[dict]) -> list[dict]:
    """誠實排序：先 Google 評分、同分按評論數，全由已核實數據推導，非編輯評選。"""
    return sorted(
        pool,
        key=lambda e: (-(e.get("rating") or 0), -(e.get("reviews") or 0)),
    )


def build_japan_region_page(rkey: str, pool: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    info = JP_REGIONS[rkey]
    rname = info["name"]
    updated = str(meta.get("updated") or "")[:10]
    ranked = japan_ranked(pool)
    top, rest = ranked[:10], ranked[10:]
    is_top10 = len(ranked) >= 10
    heading = f"🏆 {rname}十大最佳餐廳" if is_top10 else f"🏆 {rname}高分餐廳排行"
    heading_note = (
        f"已收錄 {len(ranked)} 間，排行按 Google 評分（同分按評論數）自動排序，非編輯評選；"
        "滿 10 間後此頁會自動成為「地區十大」。"
        if not is_top10 else
        f"已收錄 {len(ranked)} 間，頭十名按 Google 評分（同分按評論數）自動排序，非編輯評選；"
        "排名每星期隨收錄與評分核對更新。"
    )

    def ranked_card(i: int, e: dict) -> str:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "　")
        return (
            '<div class="ranked-item">'
            f'<div class="rank-tag" aria-label="第 {i} 位">{"#" if i > 3 else medal}'
            f'{"" if i <= 3 else i}</div>'
            + japan_card(e)
            + "</div>"
        )

    sections = "".join(ranked_card(i, e) for i, e in enumerate(top, 1))
    if rest:
        sections += (
            f'<h2 class="section-h2">更多收錄（第 {len(top) + 1} 位起）</h2>'
            + japan_grid(rest)
        )

    others = [k for k in japan_regions_in_use(pool) if k != rkey]
    other_nav = "".join(
        f'<a href="/japan/{esc(k)}/">{esc(JP_REGIONS[k]["name"])}</a>' for k in others
    )

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("日本美食", "/japan/"), (rname, None)])
        + '<div class="page-head">'
        f"<h1>{heading}</h1>"
        f'<p class="page-lede">{esc(info["intro"])}</p>'
        f'<div class="page-meta"><span>已收錄：<b>{len(ranked)}</b> 間</span>'
        f'<span>城市：<b>{len({e.get("city") for e in pool})}</b> 個</span>'
        f'<span>最後更新：<b>{esc(updated)}</b></span></div>'
        f'<p class="section-note">{esc(heading_note)}</p>'
        + (f'<div class="cat-nav">{other_nav}</div>' if other_nav else "")
        + "</div>"
        + '<div class="ranked-list">' + sections + "</div>"
        + '<div class="prose">'
        "<h2>點樣睇呢個排行</h2>"
        "<ul>"
        "<li><b>排法係透明的</b>：先按 Google 評分由高至低，同分再按評論數多寡；"
        "全由已核實的公開數據推導，我們不會憑喜好調位。</li>"
        "<li><b>評分高唔等於適合你</b>：排第一嗰間可能要排一個鐘隊。"
        "每間店嘅詳情頁有排隊、預約與付款貼士，出發前花一分鐘睇清楚。</li>"
        "<li><b>收錄係持續進行</b>：每星期加入新餐廳，收錄唔代表全區最好食，"
        "只代表通過我們嘅評分同評論數門檻；排名會隨更新浮動。</li>"
        "<li><b>出發前以 Google Map 即時資訊為準</b>：評分、營業時間同供應都會變，"
        "每筆資料標明核對日期。</li>"
        "</ul>"
        "</div>"
        + "</main>"
    )
    return layout(
        title=f"{rname}{'十大最佳' if is_top10 else '高分餐廳'}"
              f"：Google Maps 高分推薦｜Fly & Feast HK",
        desc=f"{rname}地區的 Google Maps 高分餐廳排行，現收錄 {len(ranked)} 間，"
             "按已核實評分與評論數排序，附評分解讀、價位預算與排隊貼士，每星期更新。",
        path=f"/japan/{rkey}/",
        body=body,
        meta=meta,
        active="japan",
        ld=[breadcrumb_ld([("日本美食", "/japan/"), (rname, None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": f"日本美食專欄：{rname}", "inLanguage": "zh-Hant-HK"}],
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

    region_nav = "".join(
        f'<a href="/japan/{esc(rk)}/">🏆 {esc(JP_REGIONS[rk]["name"])}'
        f'（{sum(1 for e in eats if region_key_of(e) == rk)}）</a>'
        for rk in japan_regions_in_use(eats)
    )
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
        + (f'<div class="cat-nav region-nav"><b>地區排行：</b>{region_nav}</div>'
           if region_nav else "")
        + f'<div class="cat-nav">{city_nav}</div>'
        '<div class="cat-nav region-nav"><b>住邊？</b>'
        f'<a href="{HOTEL_INDEX_PATH}">🏨 日本高性價比酒店推介（所有城市）</a>'
        "　搵到好嘢食，順手睇埋附近住邊最抵。</div>"
        '<div class="cat-nav region-nav"><b>點去？</b>'
        f'<a href="{DRIVE_INDEX_PATH}">🛣️ 日本自駕遊路線專欄</a>'
        f'　<a href="{DRIVE_GUIDE_PATH}">📋 自駕實務指南（證件・電單車・ETC）</a>'
        "　想自駕逐間掃，記得先睇證件同車種限制。</div>"
        '<div class="cat-nav region-nav"><b>飲咩？</b>'
        f'<a href="{BARS_INDEX_PATH}">🍸 日本各地必去威士忌與雞尾酒吧</a>'
        f'　<a href="{BARS_GUIDE_PATH}">📋 酒吧禮儀與點酒指南（座位費・點酒用語）</a>'
        "　食完飯想飲一杯，呢度有按地區收錄的威士忌吧同雞尾酒吧。</div>"
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


# --------------------------------------------------------------------------
# 日本酒店專欄（/japan/hotels/）
# --------------------------------------------------------------------------
# 與日本美食分開一份資料檔（pipeline/japan-hotels.json）。
# 酒店房價浮動極大，所以本欄一律不寫死價錢：只寫來源明確講過的參考價並標明
# 查價日期，其餘一律「以訂房平台即時報價為準」；「性價比」全部由可量化硬指標
# 推導（Google 評分、評論規模、車站步行分鐘、房型與設施亮點），
# 不是編輯主觀評選，亦不會自行評分。

# /japan/ 之下屬於「非餐廳 id、亦非地區 key」的固定目錄；清除孤兒頁時要保留。
JAPAN_RESERVED_DIRS = {"hotels", "drive", "bars"}

HOTEL_INDEX_PATH = "/japan/hotels/"


def load_hotels() -> list[dict]:
    if not HOTELS_FILE.exists():
        return []
    try:
        payload = json.loads(HOTELS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    hotels = payload.get("hotels") or []
    return [h for h in hotels if h.get("id") and h.get("name")]


def hotel_walk_minutes(h: dict) -> int | None:
    """由 area 文字抽取「步行 N 分鐘」——可量化、可查證的性價比訊號。"""
    area = str(h.get("area") or "")
    m = re.search(r"步行\s*約?\s*(\d+)\s*分鐘", area)
    if not m:
        m = re.search(r"(\d+)\s*分鐘", area)
    return int(m.group(1)) if m else None


def _has_price_number(h: dict) -> bool:
    band = str(h.get("priceBand") or "")
    if not band or "未見可靠公開參考價" in band:
        return False
    return bool(re.search(r"(?:HK\$|NT\$|US\$|€|¥|JPY|約\s*\d|\d[\d,]{2,})", band))


def hotel_rating_tier(rating) -> str:
    try:
        r = float(rating)
    except (TypeError, ValueError):
        return "評分資料未齊，建議以 Google Maps 即時顯示為準。"
    if r >= 4.5:
        return ("4.5 分以上喺酒店嚟講屬極少數——酒店每日要處理大量住客、清潔、"
                "隔音同前檯服務，任何一環長期失手都會拖低分數，"
                "所以呢個分數本身就係最強嘅品質保證。")
    if r >= 4.3:
        return ("4.3 分以上已經爬得過 Google 上大量酒店嘅平均線；酒店評論通常集中講"
                "位置、清潔同床褥，而且評論愈多愈難拉高，代表水準長期穩定，"
                "唔係靠幾則好評撐出嚟。")
    return "4.2 分以上已屬良好，配合評論數量同位置一併睇更有參考價值。"


def hotel_review_signal(h: dict) -> str:
    n = h.get("reviews")
    if not n:
        return "評論總數未有可靠數字，建議訂之前直接喺 Google Maps 睇最新評價分佈。"
    if n >= 2000:
        return (f"評論數超過 {n:,} 則，係同級酒店中樣本極大嘅一類；"
                "分數唔會因為幾則新評價就大幅波動，參考價值最高。")
    if n >= 800:
        return (f"約 {n:,} 則評論，樣本屬中大規模；建議順手睇埋近半年嘅評價，"
                "確認翻新或換管理後狀態有冇回落。")
    if n >= 300:
        return (f"約 {n:,} 則評論，樣本中等，分數有參考性，但要留意淡旺季嘅落差。")
    return (f"約 {n:,} 則評論，樣本有限（多數係新開幕酒店），"
            "分數浮動會較大，訂之前記得覆核一次。")


def hotel_value_signal(h: dict) -> str:
    """性價比拆成三條可查證嘅線，唔用一個自創嘅「性價比分」。"""
    bits = []
    if isinstance(h.get("rating"), (int, float)):
        bits.append(f"Google 評分 {h['rating']:.1f}")
    if h.get("reviews"):
        bits.append(f"{h['reviews']:,} 則評論")
    walk = hotel_walk_minutes(h)
    if walk is not None:
        bits.append(f"車站步行約 {walk} 分鐘")
    core = "、".join(bits) if bits else "已核實嘅公開資料"
    if _has_price_number(h):
        tail = ("呢三項加埋價位一齊睇，先叫「性價比」——"
                "本頁嘅價位參考已標明查價日期，落單前請再格一次價。")
    else:
        tail = ("本頁刻意唔填價錢：同一間酒店淡旺季可以差兩三倍，"
                "寫死一個數字反而會誤導。請直接喺訂房平台輸入實際日期格價，"
                "再同呢三項訊號對照。")
    return f"本站對「性價比」嘅定義係：{core}，三者同時達標。{tail}"


def hotel_price_signal(h: dict) -> str:
    band = str(h.get("priceBand") or "").strip()
    if not _has_price_number(h):
        if band:
            return f"價位說明：{band}。酒店房價浮動極大，落單前請以訂房平台即時報價為準。"
        return ("房價浮動極大，收錄時未見可靠嘅公開參考價，所以本頁刻意不列數字。"
                "請直接喺訂房平台輸入實際入住日期格價。")
    return (f"價位參考：{band}。以上係收錄時抄錄嘅數字，只作預算參考；"
            "酒店房價隨時浮動，一律以訂房平台即時報價為準。")


def hotel_region_pool(hotels: list[dict], rkey: str) -> list[dict]:
    return [h for h in hotels if region_key_of(h) == rkey]


def hotel_region_nav(hotels: list[dict], exclude: str | None = None) -> str:
    return "".join(
        f'<a href="{HOTEL_INDEX_PATH}{esc(k)}/">🏨 {esc(JP_REGIONS[k]["name"])}'
        f'（{len(hotel_region_pool(hotels, k))}）</a>'
        for k in japan_regions_in_use(hotels) if k != exclude
    )


def hotel_card(h: dict) -> str:
    url = f"{HOTEL_INDEX_PATH}{esc(h['id'])}/"
    star = f"{h.get('rating'):.1f}" if isinstance(h.get("rating"), (int, float)) else "—"
    reviews = f" · {h['reviews']:,} 則評論" if h.get("reviews") else ""
    walk = hotel_walk_minutes(h)
    bullets = [str(v) for v in (h.get("valuePoints") or []) if str(v).strip()]
    hl = "<ul>" + "".join(f"<li>{esc(v)}</li>" for v in bullets[:2]) + "</ul>" if bullets else ""
    walk_badge = (f'<span class="badge badge-value">🚉 步行 {walk} 分鐘</span>'
                  if walk is not None else "")
    return (
        f'<article class="card" data-id="{esc(h["id"])}">'
        '<div class="card-top">'
        f'<span class="badge badge-hotel">{esc(h.get("city") or "日本")}</span>'
        f'<span class="badge badge-rating" aria-label="Google 評分">{esc(star + " Google")}</span>'
        + walk_badge +
        '<span class="card-sticker st-hotel" aria-hidden="true">🏨</span>'
        "</div>"
        f'<h3><a href="{url}">{esc(h["name"])}</a></h3>'
        + (f'<p class="sub">{esc(h["nameEn"])}</p>' if h.get("nameEn") else "")
        + f'<p class="route">{esc(h.get("type") or "")}｜{esc(h.get("area") or "")}</p>'
        + '<div class="price-row">'
        f'<span class="price hotel-hl">💡 {esc(h.get("highlight") or "性價比之選")}</span>'
        f'<span class="save">★ {esc(star + reviews)}</span>'
        "</div>"
        + (f'<p class="summary">{esc(h["blurb"])}</p>' if h.get("blurb") else "")
        + hl
        + f'<div class="card-foot"><span class="period">{esc(rating_line(h))}</span>'
        f'<span class="actions"><a class="link-btn" href="{url}">睇詳情 →</a></span></div>'
        + "</article>"
    )


def hotel_grid(hotels: list[dict]) -> str:
    if not hotels:
        return '<p class="empty">這個地區暫時未有收錄的酒店。</p>'
    return '<div class="grid">' + "".join(hotel_card(h) for h in hotels) + "</div>"


def hotel_related(h: dict, peers: list[dict], limit: int = 3) -> list[dict]:
    """先同城，唔夠再補其他城市的高分選擇，確保詳情頁有足夠站內連結。"""
    same = [p for p in peers
            if p.get("id") != h.get("id") and p.get("city") == h.get("city")]
    same.sort(key=lambda p: abs((p.get("rating") or 0) - (h.get("rating") or 0)))
    out = same[:limit]
    if len(out) < limit:
        rest = [p for p in japan_ranked(peers)
                if p.get("id") != h.get("id") and p not in out]
        out += rest[:limit - len(out)]
    return out


def hotel_editorial_blocks(h: dict, peers: list[dict]) -> list[tuple[str, list[str], list[str]]]:
    blocks: list[tuple[str, list[str], list[str]]] = []

    # 1) 評分點解讀
    paras = [hotel_rating_tier(h.get("rating")), hotel_review_signal(h)]
    paras.append("評分與評論數會隨時間浮動，以上為收錄時抄錄的數字；訂房前請以 Google Map 即時顯示為準。")
    blocks.append(("評分點解讀", paras, []))

    # 2) 性價比點解成立
    blocks.append(("性價比點解成立", [hotel_value_signal(h)], []))

    # 3) 房型與設施亮點
    vp = [str(v) for v in (h.get("valuePoints") or []) if str(v).strip()]
    if vp:
        blocks.append(("點解揀呢間（硬指標）", 
                       ["以下每一點都對應一個可查證嘅事實（位置、房型、設施或評論規模），唔係形容詞。"],
                       vp))

    # 4) 價位與落單
    blocks.append(("價位與落單", [hotel_price_signal(h)], []))

    # 5) 去之前要知道
    tips = [str(t) for t in (h.get("tips") or []) if str(t).strip()]
    if not tips:
        tips = ["暫時未有特別注意事項，建議訂房前以酒店及訂房平台公佈為準。"]
    blocks.append(("去之前要知道", [], tips))

    # 6) 同城／同區點揀
    same = [p for p in peers
            if p.get("id") != h.get("id") and p.get("city") == h.get("city")]
    if same:
        same.sort(key=lambda p: -(p.get("rating") or 0))
        lines = [f"{p['name']}（{p.get('rating'):.1f} 分 · {p.get('highlight') or '—'}）"
                 for p in same[:3]]
        blocks.append(("同城仲有呢啲選擇",
                       [f"同一個城市收錄了 {len(same)} 間同樣達標的酒店，"
                        "分數與位置最接近的如下，行程排得埋就值得一併比較。"], lines))
    return blocks


def hotel_editorial_html(h: dict, peers: list[dict]) -> str:
    parts = [
        '<section class="editorial" aria-labelledby="jp-hotel-ed-title">',
        '<h2 id="jp-hotel-ed-title">🧾 編輯觀點 <span class="ed-cat">由評分、位置與收錄資料推導</span></h2>',
    ]
    for title, paras, bullets in hotel_editorial_blocks(h, peers):
        parts.append(f"<h3>{esc(title)}</h3>")
        for p in paras:
            parts.append(f"<p>{esc(p)}</p>")
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>")
    parts.append(
        '<p class="ed-foot">本頁評分、地址與注意事項由 Fly &amp; Feast HK 編輯部根據公開來源核對抄錄，'
        "最後核對日期見頁首資料。酒店房價、設施與供應隨時變動，"
        "一切以酒店及訂房平台即時資訊為準。本頁不構成任何訂房建議。</p>"
    )
    parts.append("</section>")
    return "".join(parts)


def build_hotels_index(hotels: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    updated = str(meta.get("updated") or "")[:10]
    ranked = japan_ranked(hotels)
    cities: list[str] = []
    for h in hotels:
        c = str(h.get("city") or "其他")
        if c not in cities:
            cities.append(c)
    cities.sort(key=lambda c: (JAPAN_CITY_ORDER.index(c) if c in JAPAN_CITY_ORDER else 99))

    region_nav = hotel_region_nav(hotels)
    city_nav = "".join(
        f'<a href="#hcity-{i}">{esc(c)}（{sum(1 for h in hotels if h.get("city") == c)}）</a>'
        for i, c in enumerate(cities)
    )
    sections = ""
    for i, c in enumerate(cities):
        pool = [h for h in hotels if h.get("city") == c]
        pool.sort(key=lambda h: (-(h.get("rating") or 0), -(h.get("reviews") or 0)))
        sections += (
            f'<h2 class="section-h2" id="hcity-{i}">🏨 {esc(c)}'
            f'<span class="ed-cat">共 {len(pool)} 間</span></h2>'
            + hotel_grid(pool)
        )

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("日本酒店推介", None)])
        + '<div class="page-head">'
        "<h1>🏨 日本高性價比酒店推介：高分 × 近車站 × 唔靠包裝</h1>"
        '<p class="page-lede">日本酒店價錢浮動得誇張——同一間房淡季同旺季可以差兩三倍，'
        "所以這個專欄刻意唔寫死價錢，改為只收錄「硬指標同時達標」嘅酒店："
        "Google 評分夠高、評論樣本夠大、行去車站夠近、房型或設施有實質賣點。"
        "每間酒店有獨立詳情頁，講清楚評分點解讀、性價比點成立、落單前要注意咩，"
        "並附上資料來源——你只需要填日期格價，唔使再逐間爬評論。</p>"
        f'<div class="page-meta"><span>已收錄：<b>{len(hotels)}</b> 間</span>'
        f'<span>城市：<b>{len(cities)}</b> 個</span>'
        f'<span>地區：<b>{len(japan_regions_in_use(hotels))}</b> 個</span>'
        f'<span>最後更新：<b>{esc(updated)}</b></span></div>'
        + (f'<div class="cat-nav region-nav"><b>地區排行：</b>{region_nav}</div>'
           if region_nav else "")
        + (f'<div class="cat-nav">{city_nav}</div>' if city_nav else "")
        + "</div>"
        + '<div class="prose">'
        "<h2>「性價比高」係點定義</h2>"
        "<p>「性價比」係一個好易講、但好難驗證嘅詞。本欄唔靠形容詞，"
        "只用四條可以逐項查證嘅線去判斷，四項同時達標才收錄：</p>"
        "<ul>"
        "<li><b>Google 評分</b>：需有公開來源明確寫出評分，並優先收錄 4.3 分以上；"
        "兩個來源評分有矛盾就唔收錄。</li>"
        "<li><b>評論規模</b>：評論數太少，分數容易浮動。同級之下，樣本愈大愈可信。</li>"
        "<li><b>車站距離</b>：由酒店步行至最近車站嘅分鐘數（取自來源描述），"
        "直接影響每日來回同搬行李嘅成本。</li>"
        "<li><b>房型與設施</b>：例如大浴場、免費宵夜、洗衣設備、行李轉運等"
        "——呢啲通常係「同價位入面幫你慳返一筆」嘅實質賣點。</li>"
        "</ul>"
        "<h2>點解唔寫實價</h2>"
        "<p>酒店房價隨日期浮動，寫死一個數字只會誤導。"
        "所以本欄嘅價位一律標明「參考價＋查價日期」，並註明以訂房平台即時報價為準；"
        "查不到可靠公開參考價嘅，索性唔填數字。"
        "你落單前請自己填日期格一次價——呢一步冇人可以代你做。</p>"
        "<h2>收錄準則與更新</h2>"
        "<ul>"
        "<li><b>唔自行評分</b>：所有分數都係抄錄自可引用嘅公開來源，並附出處連結；"
        "本站唔會「我覺得有 4.6 分」。</li>"
        "<li><b>評分會浮動</b>：每筆標明核對日期，訂房前請以 Google Map 即時顯示為準。</li>"
        "<li><b>持續更新</b>：每次加入幾個城市，優先補未覆蓋嘅地區，逐步覆蓋全日本。</li>"
        "<li><b>利益申報</b>：本頁可能包含聯盟連結，若你透過連結訂房，"
        "本站或會獲得佣金，但不會影響收錄與排序準則。</li>"
        "</ul>"
        "</div>"
        + sections
        + '<div class="prose"><h2>仲想睇多啲</h2>'
        '<ul><li><a href="/japan/">日本美食專欄</a>：同一個城市的 Google Maps 高分餐廳排行。</li>'
        '<li><a href="/guides/">優惠攻略</a>：落單前的條款檢查表與比價方法。</li></ul></div>'
        + "</main>"
    )
    return layout(
        title="日本高性價比酒店推介：高分 × 近車站 × 附資料來源｜Fly & Feast HK",
        desc=f"日本高性價比酒店推介專欄，現收錄 {len(hotels)} 間，"
             "每間附 Google 評分解讀、車站步行時間、房型與設施賣點、價位說明及資料來源，"
             "按已核實數據排序，唔寫死價錢，持續更新。",
        path="/japan/hotels/",
        body=body,
        meta=meta,
        active="japan-hotel",
        ld=[breadcrumb_ld([("日本酒店推介", None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": "日本高性價比酒店推介", "inLanguage": "zh-Hant-HK"}],
    )


def build_hotel_region_page(rkey: str, pool: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    info = JP_REGIONS[rkey]
    rname = info["name"]
    updated = str(meta.get("updated") or "")[:10]
    ranked = japan_ranked(pool)
    top, rest = ranked[:10], ranked[10:]
    is_top10 = len(ranked) >= 10
    heading = (f"🏨 {rname}高性價比酒店十大排行" if is_top10
               else f"🏨 {rname}高性價比酒店推介")
    heading_note = (
        f"已收錄 {len(ranked)} 間，排行按 Google 評分（同分按評論數）自動排序，非編輯評選；"
        "滿 10 間後此頁會自動成為「地區十大」。"
        if not is_top10 else
        f"已收錄 {len(ranked)} 間，頭十名按 Google 評分（同分按評論數）自動排序，非編輯評選；"
        "排名每星期隨收錄與評分核對更新。"
    )

    def ranked_card(i: int, h: dict) -> str:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "　")
        return (
            '<div class="ranked-item">'
            f'<div class="rank-tag" aria-label="第 {i} 位">{"#" if i > 3 else medal}'
            f'{"" if i <= 3 else i}</div>'
            + hotel_card(h)
            + "</div>"
        )

    sections = "".join(ranked_card(i, h) for i, h in enumerate(top, 1))
    if rest:
        sections += (
            f'<h2 class="section-h2">更多收錄（第 {len(top) + 1} 位起）</h2>'
            + hotel_grid(rest)
        )

    other_nav = hotel_region_nav(pool, exclude=rkey)

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("日本酒店推介", HOTEL_INDEX_PATH), (rname, None)])
        + '<div class="page-head">'
        f"<h1>{heading}</h1>"
        f'<p class="page-lede">'
        f'{esc(JP_HOTEL_REGION_INTRO.get(rkey, HOTEL_REGION_INTRO_FALLBACK))}</p>'
        f'<div class="page-meta"><span>已收錄：<b>{len(ranked)}</b> 間</span>'
        f'<span>城市：<b>{len({h.get("city") for h in pool})}</b> 個</span>'
        f'<span>最後更新：<b>{esc(updated)}</b></span></div>'
        f'<p class="section-note">{esc(heading_note)}</p>'
        f'<div class="cat-nav region-nav"><b>其他地區：</b>{other_nav}'
        f'<a href="{HOTEL_INDEX_PATH}">睇晒全部</a></div>'
        + "</div>"
        + '<div class="ranked-list">' + sections + "</div>"
        + '<div class="prose">'
        "<h2>呢個排行點睇</h2>"
        "<ul>"
        "<li><b>排法係透明的</b>：先按 Google 評分，同分再按評論數，"
        "全由已核實的公開數據推導，我們不會憑喜好調位。</li>"
        "<li><b>高分 ≠ 最啱你</b>：設有大浴場、房內洗衣設備或近地鐵出口，"
        "對唔同行程嘅價值差好遠。每間嘅詳情頁有房型與設施賣點，落單前睇一睇。</li>"
        "<li><b>價錢一定要自己格</b>：本頁刻意唔寫死價位，同一間酒店淡旺季可以差幾倍，"
        "請輸入實際入住日期再比較。</li>"
        "<li><b>利益申報</b>：本頁可能包含聯盟連結，我們或會獲得佣金，"
        "但不影響收錄門檻與排序準則。</li>"
        "</ul>"
        "</div>"
        + "</main>"
    )
    return layout(
        title=f"{rname}高性價比酒店{'十大排行' if is_top10 else '推介'}"
              f"：Google 高分 × 近車站｜Fly & Feast HK",
        desc=f"{rname}地區的日本高性價比酒店推介，現收錄 {len(ranked)} 間，"
             "按已核實的 Google 評分與評論數排序，附車站步行時間、房型設施賣點與價位說明。",
        path=f"{HOTEL_INDEX_PATH}{rkey}/",
        body=body,
        meta=meta,
        active="japan-hotel",
        ld=[breadcrumb_ld([("日本酒店推介", HOTEL_INDEX_PATH), (rname, None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": f"日本酒店推介：{rname}", "inLanguage": "zh-Hant-HK"}],
    )


def build_hotel_page(h: dict, peers: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    city = str(h.get("city") or "日本")
    rkey = region_key_of(h)
    rname = JP_REGIONS[rkey]["name"] if rkey else ""
    url = f"{HOTEL_INDEX_PATH}{h['id']}/"
    updated = str(meta.get("updated") or "")[:10]
    star = f"{h.get('rating'):.1f}" if isinstance(h.get("rating"), (int, float)) else "—"
    walk = hotel_walk_minutes(h)

    facts = [
        ("城市／地區", f"{city} · {h.get('area') or '—'}"),
        ("酒店類型", h.get("type") or "—"),
        ("最大賣點", h.get("highlight") or "—"),
        ("Google 評分", rating_line(h)),
        ("價位參考", h.get("priceBand") or "以訂房平台即時報價為準"),
        ("地址", h.get("address") or "—"),
    ]
    facts_html = "".join(
        f'<div class="deal-fact"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in facts
    )

    tier_badges = "".join([
        f'<span class="badge badge-rating">★ {esc(star)} Google</span>',
        (f'<span class="badge badge-value">🚉 車站步行 {walk} 分鐘</span>'
         if walk is not None else ""),
        (f'<span class="badge badge-hotel">{h["reviews"]:,} 則評論</span>'
         if h.get("reviews") else ""),
    ])

    related = hotel_related(h, peers)

    trail = ([("日本酒店推介", HOTEL_INDEX_PATH)] + ([ (rname, f"{HOTEL_INDEX_PATH}{rkey}/")] if rkey and rname else [])
             + [(h.get("name", ""), None)])

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html(trail)
        + '<article>'
        '<div class="deal-hero">'
        '<div class="card-top">'
        f'<span class="badge badge-hotel">日本酒店推介</span>'
        + tier_badges +
        "</div>"
        f"<h1>{esc(h.get('name'))}</h1>"
        + (f'<p class="lede-line">{esc(h["nameEn"])}</p>' if h.get("nameEn") else "")
        + '<div class="price-panel">'
        f'<span class="p-now hotel-hl">💡 {esc(h.get("highlight") or "性價比之選")}</span>'
        '<span class="p-note">價位一律標明參考價與查價日期，以訂房平台即時報價為準。'
        "本頁不構成訂房建議。</span>"
        "</div>"
        f'<dl class="deal-facts">{facts_html}</dl>'
        "</div>"
        + maps_embed_html(h, kind="酒店")
        + (f'<h2 class="section-h2">📖 編輯簡介</h2><p>{esc(h.get("blurb"))}</p>'
           if h.get("blurb") else "")
        + hotel_editorial_html(h, peers)
        + (
            '<div class="deal-actions">'
            f'<a class="link-btn" href="{esc(h.get("mapsUrl") or "#")}" target="_blank" rel="noopener nofollow">'
            "在 Google Maps 打開（導航／睇最新評價）→</a>"
            f'<a class="btn-ghost" href="{HOTEL_INDEX_PATH}">睇晒全部日本酒店推介</a>'
            "</div>"
            '<div class="source-block"><p><strong>評分與資料來源：</strong>'
            + (
                f'<a href="{esc(h["sourceUrl"])}" target="_blank" rel="noopener nofollow">'
                f'{esc(h.get("sourceLabel") or h["sourceUrl"])}</a>'
                if h.get("sourceUrl") else esc(h.get("sourceLabel"))
            )
            + f"</p><p>評分與評論數於 {esc(h.get('ratingCheckedAt') or updated)} 核對抄錄，"
            "會隨時間浮動；房價、設施與供應隨時變動，一切以酒店及訂房平台即時資訊為準。</p></div>"
        )
        + "</article>"
        + (
            '<section class="related"><h2 class="section-h2">🔎 仲有咩選擇</h2>'
            '<p class="section-note">同城優先，唔夠再補其他城市的高分酒店。</p>'
            + hotel_grid(related)
            + "</section>"
            if related else ""
        )
        + "</main>"
    )

    ld = [
        breadcrumb_ld(trail, site),
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": h.get("name"),
            "description": (h.get("blurb") or "")[:155],
            "inLanguage": "zh-Hant-HK",
            "dateModified": str(meta.get("updated") or ""),
            "author": {"@type": "Organization", "name": "Fly & Feast HK 編輯部"},
            "publisher": {"@type": "Organization", "name": "Fly & Feast HK"},
            "mainEntityOfPage": {"@type": "WebPage", "@id": site + url},
        },
    ]
    return layout(
        title=f"{h.get('name')}｜{city}高性價比酒店推介（Google {star} 分）｜Fly & Feast HK",
        desc=((h.get("blurb") or h.get("name") or "")[:155]),
        path=url,
        body=body,
        meta=meta,
        active="japan-hotel",
        ld=ld,
    )


# --------------------------------------------------------------------------
# 日本自駕專欄（/japan/drive/）
# --------------------------------------------------------------------------
# 資料檔 pipeline/japan-drive.json。與美食、酒店最大的分別：
# 自駕內容的「硬事實」是里程、通行費、開放時間、車種限制與冬季封閉，
# 全部會變，所以每筆都帶 checkedAt，頁面一律註明出發前查官方即時資訊。
# 另設 /japan/drive/guide/ 實務指南（證件、電單車關卡、高速通行證、ETC、保險、冬季）。

DRIVE_INDEX_PATH = "/japan/drive/"
DRIVE_GUIDE_PATH = "/japan/drive/guide/"

DRIVE_VEHICLE_LABEL = {
    "car": "🚗 汽車",
    "bike": "🏍️ 電單車",
    "both": "🚗🏍️ 汽車／電單車",
}
DRIVE_VEHICLE_SHORT = {"car": "汽車", "bike": "電單車", "both": "汽車＋電單車"}


def load_routes() -> list[dict]:
    if not DRIVE_FILE.exists():
        return []
    try:
        payload = json.loads(DRIVE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    routes = payload.get("routes") or []
    out = []
    for r in routes:
        if not r.get("id") or not r.get("name"):
            continue
        # region 一定要在 JP_REGIONS 之內，否則地區頁與導覽會出錯。
        if r.get("region") not in JP_REGIONS:
            print(f"  ⚠️ 自駕路線 {r.get('id')} 的 region「{r.get('region')}」不在 JP_REGIONS，已略過")
            continue
        out.append(r)
    return out


def drive_region_of(r: dict) -> str:
    return str(r.get("region") or "")


def drive_regions_in_use(routes: list[dict]) -> list[str]:
    present = {drive_region_of(r) for r in routes}
    present.discard("")
    return [k for k in JP_REGION_ORDER if k in present]


def drive_sorted(routes: list[dict]) -> list[dict]:
    """按地區展示次序、再按里程長短排列（與評分無關，自駕路線沒有評分這回事）。"""
    order = {k: i for i, k in enumerate(JP_REGION_ORDER)}
    return sorted(
        routes,
        key=lambda r: (order.get(drive_region_of(r), 99), -(r.get("lengthKm") or 0)),
    )


def drive_region_pool(routes: list[dict], rkey: str) -> list[dict]:
    return [r for r in routes if drive_region_of(r) == rkey]


def drive_region_nav(routes: list[dict], exclude: str | None = None) -> str:
    return "".join(
        f'<a href="{DRIVE_INDEX_PATH}{esc(k)}/">🛣️ {esc(JP_REGIONS[k]["name"])}'
        f'（{len(drive_region_pool(routes, k))}）</a>'
        for k in drive_regions_in_use(routes) if k != exclude
    )


def drive_len_text(r: dict) -> str:
    km = r.get("lengthKm")
    if isinstance(km, (int, float)):
        if km < 10:
            # 短程（例如單一條大橋）以公尺表達更準確
            return f"約 {km * 1000:,.0f} 公尺"
        return f"約 {km:g} 公里"
    return "里程未列"


def drive_pref_text(r: dict) -> str:
    prefs = [str(p) for p in (r.get("prefectures") or []) if str(p).strip()]
    return "・".join(prefs)


def drive_card(r: dict) -> str:
    url = f"{DRIVE_INDEX_PATH}{esc(r['id'])}/"
    veh = DRIVE_VEHICLE_LABEL.get(str(r.get("vehicle")), "🚗")
    bullets = [str(h) for h in (r.get("highlights") or []) if str(h).strip()]
    hl = "<ul>" + "".join(f"<li>{esc(h)}</li>" for h in bullets[:2]) + "</ul>" if bullets else ""
    rname = JP_REGIONS[drive_region_of(r)]["name"] if drive_region_of(r) in JP_REGIONS else "日本"
    return (
        f'<article class="card drive-card" data-id="{esc(r["id"])}">'
        '<div class="card-top">'
        f'<span class="badge badge-drive">{esc(rname)}</span>'
        f'<span class="badge badge-vehicle">{esc(veh)}</span>'
        '<span class="card-sticker st-drive" aria-hidden="true">🛣️</span>'
        "</div>"
        f'<h3><a href="{url}">{esc(r["name"])}</a></h3>'
        + (f'<p class="sub">{esc(r["nameEn"])}</p>' if r.get("nameEn") else "")
        + f'<p class="route">{esc(drive_pref_text(r))}｜{esc(r.get("roadType") or "")}</p>'
        + '<div class="price-row">'
        f'<span class="price hotel-hl">📏 {esc(drive_len_text(r))}</span>'
        f'<span class="save">{esc(r.get("season") or "全年")}</span>'
        "</div>"
        + (f'<p class="summary">{esc(r["blurb"])}</p>' if r.get("blurb") else "")
        + hl
        + f'<div class="card-foot"><span class="period">{esc(r.get("startPoint") or "")} → '
        f'{esc(r.get("endPoint") or "")}</span>'
        f'<span class="actions"><a class="link-btn" href="{url}">睇路線詳情 →</a></span></div>'
        + "</article>"
    )


def drive_grid(routes: list[dict]) -> str:
    if not routes:
        return '<p class="empty">這個地區暫時未有收錄的自駕路線。</p>'
    return '<div class="grid">' + "".join(drive_card(r) for r in drive_sorted(routes)) + "</div>"


def drive_related(r: dict, peers: list[dict], limit: int = 3) -> list[dict]:
    """先同地區，唔夠再補最近的地區（按 JP_REGION_ORDER 距離），確保詳情頁有足夠站內連結。"""
    rkey = drive_region_of(r)
    idx = {k: i for i, k in enumerate(JP_REGION_ORDER)}
    base = idx.get(rkey, 99)
    others = [
        p for p in peers
        if p.get("id") != r.get("id") and drive_region_of(p) != rkey
    ]
    others.sort(key=lambda p: abs(idx.get(drive_region_of(p), 99) - base))
    same = [p for p in drive_sorted(peers)
            if p.get("id") != r.get("id") and drive_region_of(p) == rkey]
    return (same + others)[:limit]


def drive_fact_grid(r: dict) -> str:
    dl = r.get("days") or "—"
    facts = [
        ("所在地區", f'{JP_REGIONS[drive_region_of(r)]["name"]}・{drive_pref_text(r)}'),
        ("適用車種", DRIVE_VEHICLE_SHORT.get(str(r.get("vehicle")), "汽車")),
        ("道路類型", r.get("roadType") or "—"),
        ("路線長度", drive_len_text(r)),
        ("起點", r.get("startPoint") or "—"),
        ("終點", r.get("endPoint") or "—"),
        ("建議季節", r.get("season") or "—"),
        ("建議天數", dl),
        ("開放時間", r.get("openingHours") or "—"),
        ("通行費", r.get("tollNote") or "以官方公佈為準"),
    ]
    return "".join(
        f'<div class="deal-fact"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in facts
    )


def drive_editorial_html(r: dict, peers: list[dict]) -> str:
    blocks: list[tuple[str, list[str], list[str]]] = []

    # 1) 呢條路點解值得開
    blocks.append(("呢條路點解值得開", [], [str(h) for h in (r.get("highlights") or [])]))

    # 2) 沿途停邊度
    stops = [str(s) for s in (r.get("stops") or []) if str(s).strip()]
    if stops:
        blocks.append((
            "沿途值得停低嘅位",
            ["以下地點均在路線範圍內，可以按時間自行加減；建議先在地圖標好再出發。"],
            stops,
        ))

    # 3) 車種同規矩限制（最易中招）
    restr = [str(x) for x in (r.get("restrictions") or []) if str(x).strip()]
    if restr or r.get("vehicleNote"):
        paras = []
        if r.get("vehicleNote"):
            paras.append(f"車種限制：{r['vehicleNote']}")
        paras.append("同一條路唔同季節、唔同車種嘅待遇可以差好遠，"
                     "以下係收錄時已核實嘅限制，出發前請再對一次官方公佈。")
        blocks.append(("車種規矩同限制", paras, restr))

    # 4) 通行費同時間
    blocks.append((
        "通行費、開放時間與季節",
        [
            f"通行費：{r.get('tollNote') or '以官方公佈為準'}",
            f"開放時間：{r.get('openingHours') or '以官方公佈為準'}",
            f"建議季節：{r.get('season') or '全年'}　建議天數：{r.get('days') or '—'}",
            "所有金額與時間均為收錄時抄錄，會隨政策調整；"
            "實際以道路公司或自治體官方即時資訊為準。",
        ],
        [],
    ))

    # 5) 出發前貼士
    tips = [str(t) for t in (r.get("tips") or []) if str(t).strip()]
    if tips:
        blocks.append(("出發前要知道", [], tips))

    # 6) 附近仲有咩路線
    near = [p for p in peers if p.get("id") != r.get("id")
            and drive_region_of(p) == drive_region_of(r)]
    if near:
        lines = [f"{p['name']}（{drive_len_text(p)}・{DRIVE_VEHICLE_SHORT.get(str(p.get('vehicle')), '汽車')}）"
                 for p in drive_sorted(near)[:3]]
        blocks.append((
            "同地區仲有呢啲路線",
            [f"同一個地區另外收錄了 {len(near)} 條路線，可以考慮串成兩日行程。"],
            lines,
        ))

    parts = [
        '<section class="editorial" aria-labelledby="jp-drive-ed-title">',
        '<h2 id="jp-drive-ed-title">🧾 路線詳解 '
        '<span class="ed-cat">由官方道路資料與已核實限制推導</span></h2>',
    ]
    for title, paras, bullets in blocks:
        parts.append(f"<h3>{esc(title)}</h3>")
        for p in paras:
            parts.append(f"<p>{esc(p)}</p>")
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>")
    parts.append(
        '<p class="ed-foot">本頁的里程、通行費、開放時間與車種限制由 Fly &amp; Feast HK 編輯部'
        "根據官方道路公司與自治體資料核對抄錄，核對日期見頁首。道路管制、收費與封閉期隨時變動，"
        "出發前請以官方即時資訊為準。本頁不構成任何駕駛建議；請遵守當地交通法規，安全駕駛。</p>"
    )
    parts.append("</section>")
    return "".join(parts)


def build_drive_index(routes: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    updated = str(meta.get("updated") or "")[:10]
    regions = drive_regions_in_use(routes)
    n_car = sum(1 for r in routes if r.get("vehicle") in ("car", "both"))
    n_bike = sum(1 for r in routes if r.get("vehicle") in ("bike", "both"))

    region_nav = drive_region_nav(routes)
    sections = ""
    for rk in regions:
        pool = drive_region_pool(routes, rk)
        sections += (
            f'<h2 class="section-h2" id="dregion-{esc(rk)}">🛣️ {esc(JP_REGIONS[rk]["name"])}'
            f'<span class="ed-cat">共 {len(pool)} 條</span></h2>'
            + drive_grid(pool)
        )

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("日本自駕遊", None)])
        + '<div class="page-head">'
        "<h1>🛣️ 日本自駕遊路線專欄：汽車同電單車，揀啱條路先出發</h1>"
        '<p class="page-lede">日本有兩種完全唔同嘅自駕體驗：一種係「跑到爽」嘅山脊線，'
        "另一種係「停到夠」嘅田園同海岸線。呢個專欄每條路線都會講清楚四件事——"
        "里程有幾長、通行費幾多、咩車種入得、幾時會封路。"
        "特別係車種限制：日本唔少出名嘅觀光道路禁止 125cc 以下電單車、單車同行人，"
        "亦有高山道路全年禁止私家車同電單車進入；唔查清楚就白行一轉。"
        "另外仲有一頁「自駕實務指南」，講齊證件、電單車關卡、高速公路通行證同保險陷阱。</p>"
        f'<div class="page-meta"><span>已收錄：<b>{len(routes)}</b> 條路線</span>'
        f'<span>地區：<b>{len(regions)}</b> 個</span>'
        f'<span>汽車適用：<b>{n_car}</b> 條</span>'
        f'<span>電單車適用：<b>{n_bike}</b> 條</span>'
        f'<span>最後更新：<b>{esc(updated)}</b></span></div>'
        + (f'<div class="cat-nav region-nav"><b>按地區：</b>{region_nav}</div>'
           if region_nav else "")
        + f'<div class="cat-nav region-nav"><b>出發前必讀：</b>'
        f'<a href="{DRIVE_GUIDE_PATH}">📋 日本自駕實務指南（證件・電單車・ETC・保險）</a></div>'
        '<p class="section-note">租車格價之前，建議先睇實務指南再揀路線——'
        "證件唔齊係租唔到車嘅，而且唔同租車公司對電單車排氣量嘅要求唔一樣。</p>"
        "</div>"
        + '<div class="prose">'
        "<h2>呢個專欄點揀路線</h2>"
        "<ul>"
        "<li><b>唔用自創評分</b>：自駕路線冇「幾多星」呢回事。"
        "本頁只列可核實嘅事實——里程、收費、車種限制、封閉期，然後按地區分組，"
        "唔會排一個主觀嘅「二十大必去」。</li>"
        "<li><b>車種限制優先講</b>：日本觀光道路嘅限制差異極大，"
        "同一條箱根山路，126cc 以上入得、125cc 以下唔准入。"
        "每條路線嘅詳情頁第一段就會講清楚。</li>"
        "<li><b>貴的唔一定好</b>：日本九成道路網係免費嘅，"
        "好多最有名嘅高原路線（例如ビーナスライン）其實早已免費開放。"
        "本欄會標明邊條要收費、邊條免費。</li>"
        "<li><b>數字會變</b>：通行費與封閉日期每年調整，每筆都標明核對日期，"
        "出發前請以官方即時資訊為準。</li>"
        "</ul>"
        "</div>"
        + sections
        + '<div class="prose"><h2>仲想睇多啲</h2><ul>'
        f'<li><a href="{DRIVE_GUIDE_PATH}">日本自駕實務指南</a>：'
        "證件正本要求、電單車 IDP 蓋章、高速通行證價格、NOC 保險陷阱。</li>"
        '<li><a href="/japan/">日本美食專欄</a>：沿途城市的 Google Maps 高分餐廳。</li>'
        '<li><a href="/japan/hotels/">日本酒店推介</a>：'
        "自駕行程通常住郊區酒店，泊車同房型要另計。</li>"
        "</ul></div>"
        + "</main>"
    )
    return layout(
        title="日本自駕遊路線推介：汽車・電單車・里程通行費與車種限制｜Fly & Feast HK",
        desc=f"日本自駕遊路線專欄，現收錄 {len(routes)} 條，涵蓋汽車與電單車。"
             "每條路線附里程、起終點、通行費、車種限制、開放時間與季節封閉資訊，"
             "全部標明來源與核對日期。",
        path=DRIVE_INDEX_PATH,
        body=body,
        meta=meta,
        active="japan-drive",
        ld=[breadcrumb_ld([("日本自駕遊", None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": "日本自駕遊路線", "inLanguage": "zh-Hant-HK"}],
    )


def build_drive_region_page(rkey: str, pool: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    rname = JP_REGIONS[rkey]["name"]
    updated = str(meta.get("updated") or "")[:10]
    ranked = drive_sorted(pool)

    other_nav = drive_region_nav(pool, exclude=rkey)
    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("日本自駕遊", DRIVE_INDEX_PATH), (rname, None)])
        + '<div class="page-head">'
        f"<h1>🛣️ {rname}自駕路線推介</h1>"
        f'<p class="page-lede">'
        f'{esc(JP_DRIVE_REGION_INTRO.get(rkey, DRIVE_REGION_INTRO_FALLBACK))}</p>'
        f'<div class="page-meta"><span>已收錄：<b>{len(pool)}</b> 條路線</span>'
        f'<span>汽車適用：<b>{sum(1 for r in pool if r.get("vehicle") in ("car", "both"))}</b></span>'
        f'<span>電單車適用：<b>{sum(1 for r in pool if r.get("vehicle") in ("bike", "both"))}</b></span>'
        f'<span>最後更新：<b>{esc(updated)}</b></span></div>'
        f'<p class="section-note">本頁按地區收錄，順序為里程由長至短，非編輯評選。</p>'
        f'<div class="cat-nav region-nav"><b>其他地區：</b>{other_nav}'
        f'<a href="{DRIVE_INDEX_PATH}">睇晒全部路線</a></div>'
        "</div>"
        + drive_grid(ranked)
        + '<div class="prose">'
        "<h2>出發前請先確認</h2>"
        "<ul>"
        "<li><b>車種限制</b>：呢一區唔少觀光道路禁止 125cc 以下電單車、自行車及行人，"
        "亦有高山道路全年禁止私家車與電單車。逐條路線的詳情頁有列明。</li>"
        "<li><b>季節封閉</b>：高原路線普遍在 11 月下旬至 4 月下旬封閉，"
        "實際日期每年不同。</li>"
        "<li><b>冬季裝備</b>：降雪地區要雪胎或鏈條，部分道路會強制要求。</li>"
        "<li><b>證件</b>：香港駕照正本 ＋ 1949 日內瓦公約 IDP 正本 ＋ 護照正本，"
        f'缺一不可。<a href="{DRIVE_GUIDE_PATH}">睇自駕實務指南 →</a></li>'
        "</ul>"
        "</div>"
        + "</main>"
    )
    return layout(
        title=f"{rname}自駕路線推介：里程・通行費・車種限制｜Fly & Feast HK",
        desc=f"{rname}的日本自駕路線推介，現收錄 {len(pool)} 條，"
             "包含汽車與電單車適用資訊、里程、通行費與季節封閉提醒。",
        path=f"{DRIVE_INDEX_PATH}{rkey}/",
        body=body,
        meta=meta,
        active="japan-drive",
        ld=[breadcrumb_ld([("日本自駕遊", DRIVE_INDEX_PATH), (rname, None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": f"日本自駕路線：{rname}", "inLanguage": "zh-Hant-HK"}],
    )


def build_drive_route_page(r: dict, peers: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    updated = str(meta.get("updated") or "")[:10]
    rkey = drive_region_of(r)
    rname = JP_REGIONS[rkey]["name"]
    url = f"{DRIVE_INDEX_PATH}{r['id']}/"
    veh = DRIVE_VEHICLE_LABEL.get(str(r.get("vehicle")), "🚗")
    related = drive_related(r, peers)

    trail = [("日本自駕遊", DRIVE_INDEX_PATH), (rname, f"{DRIVE_INDEX_PATH}{rkey}/"),
             (r.get("name", ""), None)]

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html(trail)
        + "<article>"
        '<div class="deal-hero">'
        '<div class="card-top">'
        f'<span class="badge badge-drive">{esc(rname)}</span>'
        f'<span class="badge badge-vehicle">{esc(veh)}</span>'
        f'<span class="badge badge-value">📏 {esc(drive_len_text(r))}</span>'
        "</div>"
        f"<h1>{esc(r.get('name'))}</h1>"
        + (f'<p class="lede-line">{esc(r["nameEn"])}</p>' if r.get("nameEn") else "")
        + '<div class="price-panel">'
        f'<span class="p-now hotel-hl">📍 {esc(r.get("startPoint") or "")} → '
        f'{esc(r.get("endPoint") or "")}</span>'
        '<span class="p-note">里程、通行費、開放時間與車種限制均附官方來源與核對日期；'
        "出發前請以官方即時資訊為準。</span>"
        "</div>"
        f'<dl class="deal-facts">{drive_fact_grid(r)}</dl>'
        "</div>"
        + maps_embed_html(r, kind="路線")
        + (f'<h2 class="section-h2">📖 路線簡介</h2><p>{esc(r.get("blurb"))}</p>'
           if r.get("blurb") else "")
        + drive_editorial_html(r, peers)
        + (
            '<div class="deal-actions">'
            f'<a class="link-btn" href="{esc(r.get("routeUrl") or r.get("mapsUrl") or "#")}" '
            'target="_blank" rel="noopener nofollow">開導航路線（Google Maps）→</a>'
            f'<a class="btn-ghost" href="{esc(r.get("mapsUrl") or "#")}" '
            'target="_blank" rel="noopener nofollow">睇地圖同最新資訊</a>'
            f'<a class="btn-ghost" href="{DRIVE_INDEX_PATH}">睇晒全部自駕路線</a>'
            "</div>"
            '<div class="source-block"><p><strong>資料來源：</strong>'
            + (
                f'<a href="{esc(r["sourceUrl"])}" target="_blank" rel="noopener nofollow">'
                f'{esc(r.get("sourceLabel") or r["sourceUrl"])}</a>'
                if r.get("sourceUrl") else esc(r.get("sourceLabel"))
            )
            + f"</p><p>里程、通行費、開放時間與車種限制於 "
            f"{esc(r.get('checkedAt') or updated)} 核對抄錄，會隨政策調整；"
            "道路管制、收費與封閉期隨時變動，一切以道路公司及自治體官方即時資訊為準。"
            "本頁不構成任何駕駛建議。</p></div>"
        )
        + "</article>"
        + (
            '<section class="related"><h2 class="section-h2">🔎 附近仲有咩路線</h2>'
            '<p class="section-note">同地區優先，唔夠再補相鄰地區。</p>'
            + drive_grid(related)
            + "</section>"
            if related else ""
        )
        + "</main>"
    )

    ld = [
        breadcrumb_ld(trail, site),
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": r.get("name"),
            "description": (r.get("blurb") or "")[:155],
            "inLanguage": "zh-Hant-HK",
            "dateModified": str(meta.get("updated") or ""),
            "author": {"@type": "Organization", "name": "Fly & Feast HK 編輯部"},
            "publisher": {"@type": "Organization", "name": "Fly & Feast HK"},
            "mainEntityOfPage": {"@type": "WebPage", "@id": site + url},
        },
    ]
    return layout(
        title=f"{r.get('name')}｜{rname}自駕路線（{drive_len_text(r)}）｜Fly & Feast HK",
        desc=((r.get("blurb") or r.get("name") or "")[:155]),
        path=url,
        body=body,
        meta=meta,
        active="japan-drive",
        ld=ld,
    )


def build_drive_guide(routes: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    updated = str(meta.get("updated") or "")[:10]

    parts = [
        '<main class="wrap page-main">',
        breadcrumb_html([("日本自駕遊", DRIVE_INDEX_PATH), ("自駕實務指南", None)]),
        '<div class="page-head">',
        "<h1>📋 日本自駕實務指南：證件、電單車、ETC 與保險</h1>",
        '<p class="page-lede">揀路線之前，先要過「租得到車」呢一關。'
        "呢頁集中講香港人去日本自駕最常撞板嘅位："
        "國際駕駛許可證（IDP）到底要邊一種、電單車要點樣先租得到、"
        "高速公路通行證值唔值得買，同埋保險最貴嘅陷阱 NOC。"
        "所有數字都標明核對日期，日本呢邊嘅規定改得幾密，出發前請再對一次官方資料。</p>",
        f'<div class="page-meta"><span>最後核對：<b>{esc(updated)}</b></span>'
        f'<span>資料來源：<b>警視廳・JNTO・道路公司・租車公司</b></span></div>',
        "</div>",
        '<div class="prose">',
        "<h2>三句講完重點</h2>",
        "<ul>",
        "<li><b>證件要正本</b>：香港駕照正本 ＋ 1949 日內瓦公約 IDP 正本 ＋ 護照正本。"
        "影本同手機照片一律唔接受，租車公司會直接拒租。</li>",
        "<li><b>電單車要 A 欄蓋章</b>：要騎 50cc 以上，IDP 的 A 欄必須有電單車許可章；"
        "P 牌（暫准駕駛執照）完全唔接受。</li>",
        "<li><b>保險要包 NOC</b>：只買 CDW 唔夠，營業損失費（NOC）係另一筆錢，"
        "建議直接買全保障方案。</li>",
        "</ul>",
        "</div>",
        '<section class="editorial" aria-labelledby="drive-guide-title">',
        '<h2 id="drive-guide-title">📋 逐項拆解 '
        '<span class="ed-cat">全部附官方來源</span></h2>',
    ]
    for title, paras, bullets in DRIVE_GUIDE_SECTIONS:
        parts.append(f"<h3>{esc(title)}</h3>")
        for p in paras:
            parts.append(f"<p>{esc(p)}</p>")
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>")
    parts.append(
        '<p class="ed-foot">本頁規定與價格由 Fly &amp; Feast HK 編輯部根據日本官方機構'
        "（警視廳、JNTO 日本政府觀光局）、道路公司（NEXCO、JB本四高速）"
        "及租車公司官方頁面核對抄錄，核對日期見頁首。"
        "簽證、駕駛資格與保險條款隨時變動，一切以官方最新公佈為準，本頁不構成法律或保險建議。</p>"
    )
    parts.append("</section>")

    # 來源清單
    parts.append('<section class="sources-block"><h2 class="section-h2">🔗 資料來源</h2><ul>')
    for label, link in DRIVE_GUIDE_SOURCES:
        parts.append(
            f'<li><a href="{esc(link)}" target="_blank" rel="noopener nofollow">{esc(label)}</a></li>'
        )
    parts.append("</ul></section>")

    # 相關路線
    if routes:
        parts.append(
            '<section class="related"><h2 class="section-h2">🛣️ 開始揀路線</h2>'
            '<p class="section-note">已收錄的路線，全部列明車種限制與季節封閉期。</p>'
            + drive_grid(routes[:3])
            + "</section>"
        )

    parts.append(
        '<div class="prose"><h2>仲想睇多啲</h2><ul>'
        f'<li><a href="{DRIVE_INDEX_PATH}">日本自駕路線總覽</a>：按地區收錄，附里程與通行費。</li>'
        '<li><a href="/japan/">日本美食專欄</a>：沿途城市的 Google Maps 高分餐廳。</li>'
        '<li><a href="/japan/hotels/">日本酒店推介</a>：自駕記得留意酒店有冇停車位。</li>'
        "</ul></div>"
    )
    parts.append("</main>")

    return layout(
        title="日本自駕實務指南：國際駕照 IDP、電單車限制、ETC 與保險陷阱｜Fly & Feast HK",
        desc="香港人去日本自駕的實務指南：1949 日內瓦公約 IDP 要求、電單車 A 欄蓋章與 P 牌限制、"
             "北海道／九州等高速公路通行證價格、ETC 與 NOC 保險陷阱、冬季雪胎規定，全部附官方來源。",
        path=DRIVE_GUIDE_PATH,
        body="".join(parts),
        meta=meta,
        active="japan-drive",
        ld=[breadcrumb_ld([("日本自駕遊", DRIVE_INDEX_PATH), ("自駕實務指南", None)], site),
            {"@context": "https://schema.org", "@type": "Article",
             "headline": "日本自駕實務指南",
             "inLanguage": "zh-Hant-HK",
             "dateModified": str(meta.get("updated") or "")}],
    )


# --------------------------------------------------------------------------
# 日本酒吧專欄（/japan/bars/、/japan/bars/<地區>/、/japan/bars/<id>/）
# 另設 /japan/bars/guide/ 酒吧禮儀與點酒指南。
# --------------------------------------------------------------------------

BARS_INDEX_PATH = "/japan/bars/"
BARS_GUIDE_PATH = "/japan/bars/guide/"

BAR_TYPE_LABEL = {
    "whisky": "🥃 威士忌專門",
    "cocktail": "🍸 雞尾酒專門",
    "both": "🥃🍸 兩者兼備",
}
BAR_TYPE_SHORT = {
    "whisky": "威士忌專門",
    "cocktail": "雞尾酒專門",
    "both": "威士忌＋雞尾酒",
}

# 第四份地區簡介（美食、酒店、自駕各有一份，呢份講飲酒文化，唔可以共用）。
JP_BAR_REGION_INTRO = {
    "kanto": "東京係全球雞尾酒同威士忌吧密度最高嘅城市之一，但銀座、新宿、池袋各走一條完全唔同嘅路線："
             "銀座走高級正統吧，新宿有大量藏身大廈高層嘅小店，池袋就聚集咗一批以稀有酒藏取勝嘅專門店。"
             "東京嘅難處唔係冇得揀，而係大部分好店都要預約，而且藏身大廈三樓以上、冇招牌，"
             "要睇大廈指示牌搭電梯。",
    "kansai": "大阪同京都嘅酒吧性格差好遠。大阪（北新地、中崎町一帶）嘅正統吧多數老闆親自落場，"
              "氣氛較外向、英文較好；京都就偏靜，speakeasy 設計特別多，有店直接用紅色電話亭做入口。"
              "京都另一條線係專做日本威士忌嘅小店，座位少但選酒極精，店主會逐款同你講。",
    "chubu": "名古屋嘅酒吧集中在名駅同榮一帶，最大優點係方便——新幹線落車行幾分鐘就有得飲。"
             "相比東京，呢度嘅正統吧多數唔需要預約，價位亦較平，"
             "適合行程緊、只想飲一杯就走的旅客。",
    "kyushu": "福岡嘅酒吧場景在九州最成熟，大名一帶係核心。呢度嘅特色係「水果系」——"
              "唔少店會用九州時令水果（甘王草莓、柑橘）入酒，季節一變酒單就跟住變。"
              "收費普遍有座位費，屬日本正統吧慣例。",
    "hokkaido": "札幌係 Nikka 嘅地盤——創辦人竹鶴政孝當年就係覺得北海道氣候似蘇格蘭，"
                "先喺余市開第一間蒸餾所。所以札幌嘅威士忌吧普遍同蒸餾廠有直接關係，"
                "東京大阪賣斷市嘅酒，喺呢度櫃上仲有。缺點係大部分店藏身薄野一帶大廈高層，"
                "要睇指示牌搭電梯。",
    "tohoku": "仙台嘅國分町係東北最大娛樂街區，聚集數千家食店同酒吧。"
              "呢度嘅正統吧多數由大師級調酒師坐鎮，價位比東京相宜，而且多數冇酒單——"
              "靠你講口味即場調，反而係最好嘅體驗。",
    "chugoku": "廣島嘅酒吧集中在流川町同中町一帶，規模唔算大但質素高，評分 4.7 以上嘅小店唔少。"
               "呢度嘅特色係店主親自坐鎮、同客傾酒，對外國客人普遍友善；"
               "部分店會用本地食材（例如配甜豆醬）做原創雞尾酒。",
    "shikoku": "四國嘅高松同松山都有各自嘅老牌酒吧同爵士吧，但公開可查核嘅 Google 評分資料較少。"
               "本專欄以「有可引用評分來源」為收錄前提，所以呢一區仍在陸續補上。",
    "okinawa": "沖繩嘅夜晚以國際通一帶為主。泡盛（沖繩蒸餾酒）係本地特色，"
               "唔少酒吧會用泡盛做原創雞尾酒；同時亦有主打威士忌同雪茄嘅成熟系酒吧。"
               "本區公開可查核嘅評分資料仍在補齊中。",
}
BAR_REGION_INTRO_FALLBACK = (
    "這個地區的酒吧收錄正在陸續增加。以下每間都附 Google 評分、評論數與查核日期，"
    "並註明以 Google Maps 即時顯示為準；收費、營業時間與吸煙規定以店家即時資訊為準。"
)

BAR_GUIDE_SECTIONS: list[tuple[str, list[str], list[str]]] = [
    (
        "「酒吧」在日本分三種，先分清楚再入去",
        [
            "你講「去酒吧」，日本人會先問你指邊一種——因為價錢、氣氛同規矩都唔同。"
            "呢個專欄介紹嘅，絕大部分係第一類。",
        ],
        [
            "オーセンティックバー（正統吧）：有吧檯有座位、收座位費、調酒師穿背心，多數安靜，"
            "一杯一杯慢慢嚟。本專欄收錄的多數屬這一類。",
            "スタンディングバー／立ち飲み（站立吧）：企位、多數免座位費、快飲快走，價錢最平。",
            "ホテルバー（酒店吧）：景觀好、服務標準化、價位最高，適合第一次體驗日本酒吧文化。",
        ],
    ),
    (
        "座位費（チャージ）是什麼？點解一定要收？",
        [
            "日本正統吧普遍收「座位費」或「チャージ」，約 ¥500–1,500，"
            "通常會包一碟小食、堅果或毛巾。呢筆錢唔係小費，係座位本身的費用，"
            "所以你坐幾久都係收一次。本專欄每間酒吧的詳情頁都會寫明有冇座位費。",
        ],
        [
            "收費名目各店唔同：チャージ／席料／テーブルチャージ／お通し，見到呢啲字就係座位費。",
            "入座前問一句「チャージはいくらですか？」最穩陣，唔會埋單先嚇一跳。",
            "部分店另外收 10% 服務費（例如札幌的 THE NIKKA BAR 同時收座位費、瓶費同服務費）。",
            "日本冇小費文化，唔需要另外加錢。",
        ],
    ),
    (
        "點威士忌的基本用語",
        [
            "日本酒吧嘅威士忌通常以 15ml 或 30ml 計價，唔少店可以點半份（ハーフ）。"
            "想一次試多幾款蒸餾所，點小份其實最划算。",
        ],
        [
            "ストレート（straight）：純飲，唔加任何嘢。",
            "ロック（rock）：加冰。日本多數用手鑿冰球，溶得慢。",
            "水割り（mizuwari）：加水，通常會用同蒸餾所水源相近嘅水。",
            "ハイボール（highball）：加蘇打水，最易入口，配炸物一流。",
            "「ハーフで」（半份）——想試多幾款就講呢句。",
            "「おすすめは？」（有咩推介？）——比你自己估酒單準確得多。",
        ],
    ),
    (
        "冇酒單的時候點算？",
        [
            "日本唔少名店根本冇酒單（例如仙台的 Le Bar Kawagoe）。呢個唔係服務差，"
            "而係佢哋想按你嘅口味即場調。遇到呢種店，講清楚自己鍾意咩就係最好的點酒方式。",
        ],
        [
            "講口味關鍵詞：smoky／peaty（煙燻泥煤）、fruity（果香）、sherry（雪莉桶）、"
            "smooth（順口易飲）、spicy（辛口）。",
            "講預算最實際：「予算は 5,000 円くらい」（預算大約 5,000 円）。",
            "講「おまかせ」（交給你決定）——多數會得到當晚最好的體驗。",
            "唔好怕問，店主一般樂意講解，甚至會拎埋酒瓶出嚟同你講產地。",
        ],
    ),
    (
        "規矩同禁忌（呢幾條最容易得罪人）",
        [
            "日本正統吧係安靜場所，唔係香港嘅酒吧——呢點係最多香港旅客撞板嘅位。",
        ],
        [
            "唔好大聲講話、唔好講電話。正統吧當係可以靜靜飲一杯嘅地方。",
            "部分店全店可吸煙（日本飲食店嘅吸煙規定同香港唔同），唔慣煙味入去前先問清楚。",
            "部分店唔可以影相，見到「撮影禁止」就唔好影，包括影酒瓶。",
            "唔好催單。一杯一杯慢慢嚟係正常節奏，催反而失禮。",
            "唔好自備酒水，亦唔好要求調酒師做酒單以外嘅複雜嘢。",
            "20 歲以下唔准入內（日本法定飲酒年齡），帶小朋友就唔好安排酒吧行程。",
        ],
    ),
    (
        "預約、語言同最後一班車",
        [
            "銀座、京都嘅高級店多數要預約，非日語客人尤其建議先訂位；"
            "新宿、池袋、名古屋嘅小店相對容易 Walk-in，但熱門時段一樣會滿。",
        ],
        [
            "預約主要靠電話，部分店用 TableCheck 等網上平台（例如東京的 Bar Benfiddich 每月 20 號開放訂位）。",
            "最實用嘅一招：請酒店前台幫你打電話訂位，順便幫你講清楚人數同時間。",
            "英文能力各店差異極大。池袋的 Aloha Whisky 以英語為主，"
            "部分老牌小店店主只講日文但非常友善，用翻譯 App 都溝通得到。",
            "日本對酒後駕駛嘅標準極嚴，而且同車乘客同供酒者一樣有責任——"
            "飲酒就唔好開車，改搭的士或地鐵。",
            "大城市地鐵／地下鐵多數在午夜前後收車，最後一班車時間要先查清楚，"
            "唔好飲到興起先發現冇車返酒店。",
        ],
    ),
]

BAR_GUIDE_SOURCES: list[tuple[str, str]] = [
    ("Sip Japan：京都威士忌吧指南（含 Google 評分與評論數）", "https://sipjapan.com/blog/best-whisky-bars-kyoto"),
    ("Sip Japan：札幌威士忌吧指南（含 Google 評分與評論數）", "https://sipjapan.com/blog/best-whisky-bars-sapporo"),
    ("Restaurant Guru：Bar Benfiddich（引用 Google 評分 4.4、934 則）", "https://restaurantguru.com/Bar-Benfiddich-Shinjuku"),
    ("Wanderlog：各地酒吧評分與 Google 評論彙整", "https://wanderlog.com/"),
    ("Tabelog：日本餐廳與酒吧資料庫（收費、座位數、營業時間）", "https://tabelog.com/"),
    ("byFood：京都酒吧與雞尾酒吧指南", "https://www.byfood.com/zh-tw/blog/best-cocktail-bar-kyoto-p-749"),
    ("Fukuoka Now：福岡酒吧介紹（座位費與吸煙規定）", "https://www.fukuoka-now.com/en/bar-oscar"),
    ("Tokyo Deep Nightlife：東京威士忌吧導覽（15ml 計價與營業時間）", "https://tokyodeepnightlife.jp/tokyo-whisky-bar-tour/"),
    ("GUSTO webzine：東京威士忌 flight 指南（蒸餾所收藏規模）", "https://gustowebzine.com/japanese-whisky-flights-in-tokyo-hotel-bars/"),
]


def load_bars() -> list[dict]:
    if not BARS_FILE.exists():
        return []
    try:
        payload = json.loads(BARS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for b in (payload.get("bars") or []):
        if not b.get("id") or not b.get("name"):
            continue
        # region 一定要在 JP_REGIONS 之內，否則地區頁與導覽會出錯。
        if b.get("region") not in JP_REGIONS:
            print(f"  ⚠️ 酒吧 {b.get('id')} 的 region「{b.get('region')}」不在 JP_REGIONS，已略過")
            continue
        out.append(b)
    return out


def bar_region_of(b: dict) -> str:
    return str(b.get("region") or "")


def bar_regions_in_use(bars: list[dict]) -> list[str]:
    present = {bar_region_of(b) for b in bars}
    present.discard("")
    return [k for k in JP_REGION_ORDER if k in present]


def bar_sorted(bars: list[dict]) -> list[dict]:
    """誠實排序：先 Google 評分、同分按評論數，全由已核實數據推導，非編輯評選。"""
    return sorted(
        bars,
        key=lambda b: (-(b.get("rating") or 0), -(b.get("reviews") or 0)),
    )


def bar_region_pool(bars: list[dict], rkey: str) -> list[dict]:
    return [b for b in bars if bar_region_of(b) == rkey]


def bar_region_nav(bars: list[dict], exclude: str | None = None) -> str:
    return "".join(
        f'<a href="{BARS_INDEX_PATH}{esc(k)}/">🍸 {esc(JP_REGIONS[k]["name"])}'
        f'（{len(bar_region_pool(bars, k))}）</a>'
        for k in bar_regions_in_use(bars) if k != exclude
    )


def bar_rating_text(b: dict) -> str:
    r = b.get("rating")
    if not isinstance(r, (int, float)):
        return "評分未列"
    rv = b.get("reviews")
    return f"⭐ {r:g}" + (f"（{rv:,} 則）" if isinstance(rv, int) else "")


def bar_card(b: dict) -> str:
    url = f"{BARS_INDEX_PATH}{esc(b['id'])}/"
    btype = BAR_TYPE_LABEL.get(str(b.get("barType")), "🍸")
    bullets = [str(h) for h in (b.get("highlights") or []) if str(h).strip()]
    hl = "<ul>" + "".join(f"<li>{esc(h)}</li>" for h in bullets[:2]) + "</ul>" if bullets else ""
    rname = JP_REGIONS[bar_region_of(b)]["name"] if bar_region_of(b) in JP_REGIONS else "日本"
    where = "・".join(x for x in (str(b.get("city") or ""), str(b.get("area") or "")) if x)
    return (
        f'<article class="card bar-card" data-id="{esc(b["id"])}">'
        '<div class="card-top">'
        f'<span class="badge badge-bar">{esc(rname)}</span>'
        f'<span class="badge badge-bartype">{esc(btype)}</span>'
        '<span class="card-sticker st-bar" aria-hidden="true">🍸</span>'
        "</div>"
        f'<h3><a href="{url}">{esc(b["name"])}</a></h3>'
        + (f'<p class="sub">{esc(b["nameEn"])}</p>' if b.get("nameEn") else "")
        + f'<p class="route">📍 {esc(where)}</p>'
        + '<div class="price-row">'
        f'<span class="price bar-hl">{esc(bar_rating_text(b))}</span>'
        f'<span class="save">{esc(BAR_TYPE_SHORT.get(str(b.get("barType")), ""))}</span>'
        "</div>"
        + (f'<p class="summary">{esc(b["blurb"])}</p>' if b.get("blurb") else "")
        + hl
        + f'<div class="card-foot"><span class="period">'
        f'🥃 {esc(b.get("signature") or "以現場酒單為準")}</span>'
        f'<span class="actions"><a class="link-btn" href="{url}">睇酒吧詳情 →</a></span></div>'
        + "</article>"
    )


def bar_grid(bars: list[dict]) -> str:
    if not bars:
        return '<p class="empty">這個地區暫時未有收錄的酒吧。</p>'
    return '<div class="grid">' + "".join(bar_card(b) for b in bar_sorted(bars)) + "</div>"


def bar_related(b: dict, peers: list[dict], limit: int = 3) -> list[dict]:
    """先同地區，唔夠再補最近的地區（按 JP_REGION_ORDER 距離），確保詳情頁有足夠站內連結。"""
    rkey = bar_region_of(b)
    idx = {k: i for i, k in enumerate(JP_REGION_ORDER)}
    base = idx.get(rkey, 99)
    others = [p for p in peers if p.get("id") != b.get("id") and bar_region_of(p) != rkey]
    others.sort(key=lambda p: abs(idx.get(bar_region_of(p), 99) - base))
    same = [p for p in bar_sorted(peers)
            if p.get("id") != b.get("id") and bar_region_of(p) == rkey]
    return (same + others)[:limit]


def bar_fact_grid(b: dict) -> str:
    where = "・".join(x for x in (str(b.get("city") or ""), str(b.get("area") or "")) if x)
    facts = [
        ("所在地區", f'{JP_REGIONS[bar_region_of(b)]["name"]}・{where}'),
        ("類型", BAR_TYPE_SHORT.get(str(b.get("barType")), "—")),
        ("招牌／必點", b.get("signature") or "—"),
        ("Google 評分", f'{b.get("rating"):g}' if isinstance(b.get("rating"), (int, float)) else "—"),
        ("評論數", f'{b.get("reviews"):,}' if isinstance(b.get("reviews"), int) else "未列"),
        ("費用參考", b.get("priceBand") or "以現場酒單為準"),
        ("地址", b.get("address") or "—"),
        ("評分查核日", b.get("ratingCheckedAt") or "—"),
    ]
    return "".join(
        f'<div class="deal-fact"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in facts
    )


def bar_editorial_html(b: dict, peers: list[dict]) -> str:
    blocks: list[tuple[str, list[str], list[str]]] = []

    blocks.append(("呢間酒吧點解值得去", [], [str(h) for h in (b.get("highlights") or [])]))

    if b.get("signature"):
        blocks.append((
            "入到去做咩",
            [f"招牌／必點：{b['signature']}",
             "日本酒吧普遍可以按你口味即場調整，唔一定跟足酒單。"
             "如果冇酒單，直接講口味關鍵詞（smoky／fruity／sherry／smooth）最有效。"],
            [],
        ))

    blocks.append((
        "收費同規矩",
        [
            f"費用參考：{b.get('priceBand') or '以現場酒單為準'}",
            "日本正統吧普遍收座位費（チャージ／席料），約 ¥500–1,500，通常包小食或毛巾；"
            "日本冇小費文化，唔需要另加。",
            "營業時間、吸煙規定與座位費各店差異大，出發前請以店家 Google 即時資訊為準。",
        ],
        [],
    ))

    tips = [str(t) for t in (b.get("tips") or []) if str(t).strip()]
    if tips:
        blocks.append(("去之前要知道", [], tips))

    near = [p for p in peers if p.get("id") != b.get("id")
            and bar_region_of(p) == bar_region_of(b)]
    if near:
        lines = [f"{p['name']}（{bar_rating_text(p)}・{BAR_TYPE_SHORT.get(str(p.get('barType')), '')}）"
                 for p in bar_sorted(near)[:3]]
        blocks.append((
            "同地區仲有呢幾間",
            [f"同一個地區另外收錄了 {len(near)} 間酒吧，可以一晚串兩間。"],
            lines,
        ))

    parts = [
        '<section class="editorial" aria-labelledby="jp-bar-ed-title">',
        '<h2 id="jp-bar-ed-title">🧾 酒吧詳解 '
        '<span class="ed-cat">由已核實評分與公開資料推導</span></h2>',
    ]
    for title, paras, bullets in blocks:
        parts.append(f"<h3>{esc(title)}</h3>")
        for p in paras:
            parts.append(f"<p>{esc(p)}</p>")
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{esc(bl)}</li>" for bl in bullets) + "</ul>")
    parts.append(
        '<p class="ed-foot">本頁的評分與評論數由 Fly &amp; Feast HK 編輯部'
        "根據上列來源網站引用的 Google 資料核對抄錄，查核日期見頁首。"
        "酒吧的營業時間、收費與吸煙規定變動頻繁，一切以店家及 Google Maps 即時資訊為準。"
        "本頁不構成任何推薦或品質保證；請理性飲酒，酒後不駕駛。未滿 20 歲不得飲酒。</p>"
    )
    parts.append("</section>")
    return "".join(parts)


def build_bars_index(bars: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    updated = str(meta.get("updated") or "")[:10]
    regions = bar_regions_in_use(bars)
    n_whisky = sum(1 for b in bars if b.get("barType") in ("whisky", "both"))
    n_cocktail = sum(1 for b in bars if b.get("barType") in ("cocktail", "both"))

    region_nav = bar_region_nav(bars)
    sections = ""
    for rk in regions:
        pool = bar_region_pool(bars, rk)
        sections += (
            f'<h2 class="section-h2" id="bregion-{esc(rk)}">🍸 {esc(JP_REGIONS[rk]["name"])}'
            f'<span class="ed-cat">共 {len(pool)} 間</span></h2>'
            + bar_grid(pool)
        )

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("日本酒吧", None)])
        + '<div class="page-head">'
        "<h1>🍸 日本各地必去威士忌與雞尾酒吧</h1>"
        '<p class="page-lede">日本酒吧最麻煩嘅唔係冇好酒，而係「唔知門路」——'
        "好店多數藏身大廈三樓以上、冇招牌、冇酒單、仲要收一筆唔知係咩嘅座位費。"
        "呢個專欄按地區收錄威士忌同雞尾酒吧，每間都寫清楚三件事："
        "Google 評分同評論數（附查核日期）、招牌係咩、收費同規矩係點。"
        "另外仲有一頁「酒吧禮儀與點酒指南」，講齊座位費、點威士忌用語同最容易失禮嘅位。</p>"
        f'<div class="page-meta"><span>已收錄：<b>{len(bars)}</b> 間</span>'
        f'<span>地區：<b>{len(regions)}</b> 個</span>'
        f'<span>威士忌專門：<b>{n_whisky}</b> 間</span>'
        f'<span>雞尾酒專門：<b>{n_cocktail}</b> 間</span>'
        f'<span>最後更新：<b>{esc(updated)}</b></span></div>'
        + (f'<div class="cat-nav region-nav"><b>按地區：</b>{region_nav}</div>'
           if region_nav else "")
        + f'<div class="cat-nav region-nav"><b>入場前必讀：</b>'
        f'<a href="{BARS_GUIDE_PATH}">📋 酒吧禮儀與點酒指南（座位費・點酒用語・禁忌）</a></div>'
        '<p class="section-note">本頁按地區分組，地區內按 Google 評分排序（同分按評論數），'
        "排序由已核實數據推導，並非編輯主觀評選。</p>"
        "</div>"
        + '<div class="prose">'
        "<h2>呢個專欄點揀酒吧</h2>"
        "<ul>"
        "<li><b>唔用自創評分</b>：只收有公開來源明確寫出 Google 評分的店，"
        "並標明查核日期；兩個來源評分矛盾就跳過，查不到就不收錄。</li>"
        "<li><b>威士忌同雞尾酒都要有</b>：日本酒吧兩條線的性格差很遠——"
        "威士忌專門店講酒藏深度，雞尾酒吧講調酒師手法同季節水果，兩種都值得去。</li>"
        "<li><b>規矩先講清楚</b>：座位費幾多、可唔可以影相、係唔係全店吸煙，"
        "呢啲係香港旅客最常撞板嘅位，每間詳情頁都會寫。</li>"
        "<li><b>評分會變</b>：每筆都標明查核日期，以 Google Maps 即時顯示為準。</li>"
        "</ul>"
        "</div>"
        + sections
        + '<div class="prose"><h2>仲想睇多啲</h2><ul>'
        f'<li><a href="{BARS_GUIDE_PATH}">酒吧禮儀與點酒指南</a>：'
        "座位費係咩、點威士忌用語、冇酒單點算、最容易失禮嘅六件事。</li>"
        '<li><a href="/japan/">日本美食專欄</a>：飲完想去食宵夜，呢度有各城市的高分餐廳。</li>'
        '<li><a href="/japan/hotels/">日本酒店推介</a>：飲到夜，揀一間行得返酒店的最實際。</li>'
        '<li><a href="/japan/drive/">日本自駕路線</a>：自駕要注意酒後駕駛規定極嚴，'
        "飲酒當日唔好開車。</li>"
        "</ul></div>"
        + "</main>"
    )
    return layout(
        title="日本必去威士忌與雞尾酒吧推介：按地區收錄・附 Google 評分｜Fly & Feast HK",
        desc=f"日本各地區必去的威士忌與雞尾酒吧，現收錄 {len(bars)} 間、涵蓋 {len(regions)} 個地區。"
             "每間附 Google 評分與評論數、查核日期、招牌酒、座位費與規矩提醒。",
        path=BARS_INDEX_PATH,
        body=body,
        meta=meta,
        active="japan-bar",
        ld=[breadcrumb_ld([("日本酒吧", None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": "日本必去威士忌與雞尾酒吧", "inLanguage": "zh-Hant-HK"}],
    )


def build_bar_region_page(rkey: str, pool: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    rname = JP_REGIONS[rkey]["name"]
    updated = str(meta.get("updated") or "")[:10]
    ranked = bar_sorted(pool)

    other_nav = bar_region_nav(pool, exclude=rkey)
    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html([("日本酒吧", BARS_INDEX_PATH), (rname, None)])
        + '<div class="page-head">'
        f"<h1>🍸 {rname}必去威士忌與雞尾酒吧</h1>"
        f'<p class="page-lede">'
        f'{esc(JP_BAR_REGION_INTRO.get(rkey, BAR_REGION_INTRO_FALLBACK))}</p>'
        f'<div class="page-meta"><span>已收錄：<b>{len(pool)}</b> 間</span>'
        f'<span>威士忌專門：<b>{sum(1 for b in pool if b.get("barType") in ("whisky", "both"))}</b></span>'
        f'<span>雞尾酒專門：<b>{sum(1 for b in pool if b.get("barType") in ("cocktail", "both"))}</b></span>'
        f'<span>最後更新：<b>{esc(updated)}</b></span></div>'
        f'<p class="section-note">本頁按 Google 評分排序（同分按評論數），'
        "排序由已核實數據推導，非編輯主觀評選。</p>"
        f'<div class="cat-nav region-nav"><b>其他地區：</b>{other_nav}'
        f'<a href="{BARS_INDEX_PATH}">睇晒全部酒吧</a></div>'
        "</div>"
        + bar_grid(ranked)
        + '<div class="prose">'
        "<h2>入去之前請先確認</h2>"
        "<ul>"
        "<li><b>座位費</b>：日本正統吧普遍收約 ¥500–1,500，通常包小食或毛巾；"
        "日本冇小費文化。詳情頁有寫明該店情況。</li>"
        "<li><b>吸煙規定</b>：部分店全店可吸煙，日本飲食店的吸煙規定與香港不同，"
        "唔慣煙味要先問清楚。</li>"
        "<li><b>影相</b>：部分店禁止拍攝，見到「撮影禁止」就唔好影。</li>"
        f'<li><b>第一次去</b>：可以先睇<a href="{BARS_GUIDE_PATH}">酒吧禮儀與點酒指南</a>，'
        "座位費、點酒用語、冇酒單點處理都講齊。</li>"
        "</ul>"
        "</div>"
        + "</main>"
    )
    return layout(
        title=f"{rname}必去威士忌與雞尾酒吧推介：Google 評分・座位費提醒｜Fly & Feast HK",
        desc=f"{rname}的日本威士忌與雞尾酒吧推介，現收錄 {len(pool)} 間，"
             "附 Google 評分與評論數、查核日期、招牌酒與收費規矩提醒。",
        path=f"{BARS_INDEX_PATH}{rkey}/",
        body=body,
        meta=meta,
        active="japan-bar",
        ld=[breadcrumb_ld([("日本酒吧", BARS_INDEX_PATH), (rname, None)], site),
            {"@context": "https://schema.org", "@type": "CollectionPage",
             "name": f"日本酒吧：{rname}", "inLanguage": "zh-Hant-HK"}],
    )


def build_bar_page(b: dict, peers: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    updated = str(meta.get("updated") or "")[:10]
    rkey = bar_region_of(b)
    rname = JP_REGIONS[rkey]["name"]
    url = f"{BARS_INDEX_PATH}{b['id']}/"
    btype = BAR_TYPE_LABEL.get(str(b.get("barType")), "🍸")
    related = bar_related(b, peers)
    where = "・".join(x for x in (str(b.get("city") or ""), str(b.get("area") or "")) if x)

    trail = [("日本酒吧", BARS_INDEX_PATH), (rname, f"{BARS_INDEX_PATH}{rkey}/"),
             (b.get("name", ""), None)]

    body = (
        '<main class="wrap page-main">'
        + breadcrumb_html(trail)
        + "<article>"
        '<div class="deal-hero">'
        '<div class="card-top">'
        f'<span class="badge badge-bar">{esc(rname)}</span>'
        f'<span class="badge badge-bartype">{esc(btype)}</span>'
        f'<span class="badge badge-value">{esc(bar_rating_text(b))}</span>'
        "</div>"
        f"<h1>{esc(b.get('name'))}</h1>"
        + (f'<p class="lede-line">{esc(b["nameEn"])}</p>' if b.get("nameEn") else "")
        + '<div class="price-panel">'
        f'<span class="p-now bar-hl">📍 {esc(where)}</span>'
        '<span class="p-note">評分與評論數附來源與查核日期，以 Google Maps 即時顯示為準；'
        "座位費、營業時間與吸煙規定請以店家即時資訊為準。</span>"
        "</div>"
        f'<dl class="deal-facts">{bar_fact_grid(b)}</dl>'
        "</div>"
        + maps_embed_html(b, kind="酒吧")
        + (f'<h2 class="section-h2">📖 酒吧簡介</h2><p>{esc(b.get("blurb"))}</p>'
           if b.get("blurb") else "")
        + bar_editorial_html(b, peers)
        + (
            '<div class="deal-actions">'
            f'<a class="link-btn" href="{esc(b.get("mapsUrl") or "#")}" '
            'target="_blank" rel="noopener nofollow">睇 Google Maps 位置與即時資訊 →</a>'
            f'<a class="btn-ghost" href="{BARS_INDEX_PATH}">睇晒全部日本酒吧</a>'
            f'<a class="btn-ghost" href="{BARS_GUIDE_PATH}">酒吧禮儀與點酒指南</a>'
            "</div>"
            '<div class="source-block"><p><strong>資料來源：</strong>'
            + (
                f'<a href="{esc(b["sourceUrl"])}" target="_blank" rel="noopener nofollow">'
                f'{esc(b.get("sourceLabel") or b["sourceUrl"])}</a>'
                if b.get("sourceUrl") else esc(b.get("sourceLabel"))
            )
            + f"</p><p>評分與評論數於 {esc(b.get('ratingCheckedAt') or updated)} 核對抄錄，"
            "並以 Google Maps 即時顯示為準。酒吧的營業時間、收費與吸煙規定變動頻繁，"
            "一切以店家官方資訊為準。本頁不構成任何推薦或品質保證；"
            "請理性飲酒，酒後不駕駛。未滿 20 歲不得飲酒。</p></div>"
        )
        + "</article>"
        + (
            '<section class="related"><h2 class="section-h2">🔎 附近仲有咩酒吧</h2>'
            '<p class="section-note">同地區優先，唔夠再補相鄰地區。</p>'
            + bar_grid(related)
            + "</section>"
            if related else ""
        )
        + "</main>"
    )

    ld = [
        breadcrumb_ld(trail, site),
        {
            "@context": "https://schema.org",
            "@type": "BarOrPub",
            "name": b.get("name"),
            "description": (b.get("blurb") or "")[:155],
            "address": b.get("address"),
            "inLanguage": "zh-Hant-HK",
            "dateModified": str(meta.get("updated") or ""),
            "mainEntityOfPage": {"@type": "WebPage", "@id": site + url},
        },
    ]
    if isinstance(b.get("rating"), (int, float)):
        ld.append({
            "@context": "https://schema.org",
            "@type": "AggregateRating",
            "ratingValue": b.get("rating"),
            "reviewCount": b.get("reviews") or 1,
            "bestRating": 5,
        })
    return layout(
        title=f"{b.get('name')}｜{rname}酒吧推介（{bar_rating_text(b)}）｜Fly & Feast HK",
        desc=((b.get("blurb") or b.get("name") or "")[:155]),
        path=url,
        body=body,
        meta=meta,
        active="japan-bar",
        ld=ld,
    )


def build_bars_guide(bars: list[dict], meta: dict) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    updated = str(meta.get("updated") or "")[:10]

    parts = [
        '<main class="wrap page-main">',
        breadcrumb_html([("日本酒吧", BARS_INDEX_PATH), ("酒吧禮儀與點酒指南", None)]),
        '<div class="page-head">',
        "<h1>📋 日本酒吧禮儀與點酒指南：座位費、點酒用語與禁忌</h1>",
        '<p class="page-lede">日本酒吧同香港酒吧係兩種動物。好多人第一次去會撞板嘅唔係酒，'
        "而係規矩：唔知點解要收座位費、冇酒單唔知點算、飲完一杯想再叫但店主唔理你。"
        "呢頁集中講香港人去日本酒吧最常撞板嘅位，令你第一晚就識玩。"
        "日本呢邊嘅收費同規定各店差異極大，所以本文只講通則，"
        "個別店舖的收費、營業時間與吸煙規定一律以店家即時資訊為準。</p>",
        f'<div class="page-meta"><span>最後核對：<b>{esc(updated)}</b></span>'
        f'<span>收錄酒吧：<b>{len(bars)}</b> 間</span></div>',
        "</div>",
        '<div class="prose">',
        "<h2>三句講完重點</h2>",
        "<ul>",
        "<li><b>座位費要問清楚</b>：日本正統吧普遍收 ¥500–1,500 座位費（チャージ／席料），"
        "通常包小食；呢筆錢唔係小費，日本亦冇小費文化。</li>",
        "<li><b>冇酒單係正常</b>：唔少名店根本冇酒單，靠你講口味即場調。"
        "講 smoky／fruity／sherry／smooth 加預算，比你自己估更準。</li>",
        "<li><b>安靜係規矩</b>：正統吧唔係傾大聲嘢嘅地方，唔好大聲講話、唔好講電話、"
        "見到「撮影禁止」就唔好影。</li>",
        "</ul>",
        "</div>",
        '<section class="editorial" aria-labelledby="bar-guide-title">',
        '<h2 id="bar-guide-title">📋 逐項拆解 '
        '<span class="ed-cat">收費與規矩各店不同，以店家為準</span></h2>',
    ]
    for title, paras, bullets in BAR_GUIDE_SECTIONS:
        parts.append(f"<h3>{esc(title)}</h3>")
        for p in paras:
            parts.append(f"<p>{esc(p)}</p>")
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{esc(bl)}</li>" for bl in bullets) + "</ul>")
    parts.append(
        '<p class="ed-foot">本頁內容由 Fly &amp; Feast HK 編輯部參考日本餐飲業慣例'
        "及各店公開收費說明整理，核對日期見頁首。"
        "收費、營業時間、吸煙規定與入場年齡限制各店不同且會變動，"
        "一切以店家官方及 Google Maps 即時資訊為準。"
        "本頁不構成任何推薦或品質保證；請理性飲酒，酒後不駕駛，未滿 20 歲不得飲酒。</p>"
    )
    parts.append("</section>")

    parts.append('<section class="sources-block"><h2 class="section-h2">🔗 評分與資料來源</h2><ul>')
    for label, link in BAR_GUIDE_SOURCES:
        parts.append(
            f'<li><a href="{esc(link)}" target="_blank" rel="noopener nofollow">{esc(label)}</a></li>'
        )
    parts.append("</ul></section>")

    if bars:
        parts.append(
            '<section class="related"><h2 class="section-h2">🍸 開始揀酒吧</h2>'
            '<p class="section-note">已收錄的酒吧，全部附 Google 評分、評論數與查核日期。</p>'
            + bar_grid(bar_sorted(bars)[:3])
            + "</section>"
        )

    parts.append(
        '<div class="prose"><h2>仲想睇多啲</h2><ul>'
        f'<li><a href="{BARS_INDEX_PATH}">日本酒吧總覽</a>：按地區收錄威士忌與雞尾酒吧。</li>'
        '<li><a href="/japan/">日本美食專欄</a>：飲完想食宵夜，呢度有各城市高分餐廳。</li>'
        '<li><a href="/japan/hotels/">日本酒店推介</a>：飲到夜，揀一間行得返的最實際。</li>'
        "</ul></div>"
    )
    parts.append("</main>")

    return layout(
        title="日本酒吧禮儀與點酒指南：座位費、點威士忌用語與禁忌｜Fly & Feast HK",
        desc="香港人去日本酒吧的實務指南：座位費（チャージ）是什麼、威士忌點酒用語、"
             "遇到冇酒單怎辦、最容易失禮的六件事、預約與最後一班車安排。",
        path=BARS_GUIDE_PATH,
        body="".join(parts),
        meta=meta,
        active="japan-bar",
        ld=[breadcrumb_ld([("日本酒吧", BARS_INDEX_PATH), ("酒吧禮儀與點酒指南", None)], site),
            {"@context": "https://schema.org", "@type": "Article",
             "headline": "日本酒吧禮儀與點酒指南",
             "inLanguage": "zh-Hant-HK",
             "dateModified": str(meta.get("updated") or "")}],
    )


def prune_stale_japan_pages(valid_ids: set[str]) -> int:
    """同優惠頁一樣，清除已不在資料檔的孤兒頁。資料少於 5 筆時不動。

    注意：JAPAN_RESERVED_DIRS（例如 hotels）一定要在 valid_ids 之內，
    否則 /japan/hotels/ 整個專欄會被當成孤兒頁刪走（無錯誤訊息，極難察覺）。
    """
    MIN_SIZE = 5
    if len(valid_ids) < MIN_SIZE:
        return 0
    base = PROJECT / "japan"
    if not base.exists():
        return 0
    keep = set(valid_ids) | set(JAPAN_RESERVED_DIRS)
    removed = 0
    for child in base.iterdir():
        if child.is_dir() and child.name not in keep:
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed


# --------------------------------------------------------------------------
# sitemap
# --------------------------------------------------------------------------

def build_sitemap(deals: list[dict], meta: dict, japan_eats: list[dict] | None = None,
                  japan_hotels: list[dict] | None = None,
                  japan_routes: list[dict] | None = None,
                  japan_bars: list[dict] | None = None) -> str:
    site = (meta.get("siteUrl") or SITE_FALLBACK).rstrip("/")
    today = datetime.now(HK_TZ).date().isoformat()
    urls: list[tuple[str, str, str]] = [
        ("/", "1.0", "daily"),
        ("/deals/", "0.9", "daily"),
    ]
    for c in ("flight", "dining", "hotel"):
        urls.append((f"/deals/{CAT_SLUG[c]}/", "0.9", "daily"))
    urls.append(("/japan/", "0.8", "weekly"))
    for rk in japan_regions_in_use(japan_eats or []):
        urls.append((f"/japan/{rk}/", "0.7", "weekly"))
    for e in (japan_eats or []):
        urls.append((f"/japan/{e['id']}/", "0.6", "weekly"))
    if japan_hotels:
        urls.append((HOTEL_INDEX_PATH, "0.8", "weekly"))
        for rk in japan_regions_in_use(japan_hotels):
            urls.append((f"{HOTEL_INDEX_PATH}{rk}/", "0.7", "weekly"))
        for h in japan_hotels:
            urls.append((f"{HOTEL_INDEX_PATH}{h['id']}/", "0.6", "weekly"))
    if japan_routes:
        urls.append((DRIVE_INDEX_PATH, "0.8", "weekly"))
        urls.append((DRIVE_GUIDE_PATH, "0.7", "monthly"))
        for rk in drive_regions_in_use(japan_routes):
            urls.append((f"{DRIVE_INDEX_PATH}{rk}/", "0.7", "weekly"))
        for r in japan_routes:
            urls.append((f"{DRIVE_INDEX_PATH}{r['id']}/", "0.6", "weekly"))
    if japan_bars:
        urls.append((BARS_INDEX_PATH, "0.8", "weekly"))
        urls.append((BARS_GUIDE_PATH, "0.7", "monthly"))
        for rk in bar_regions_in_use(japan_bars):
            urls.append((f"{BARS_INDEX_PATH}{rk}/", "0.7", "weekly"))
        for b in japan_bars:
            urls.append((f"{BARS_INDEX_PATH}{b['id']}/", "0.6", "weekly"))
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

    # 日本美食專欄 + 日本酒店專欄（同一棵 /japan/ 樹）
    eats = load_japan()
    hotels = load_hotels()
    bars = load_bars()
    jpruned = prune_stale_japan_pages(
        {e["id"] for e in eats}
        | set(japan_regions_in_use(eats))
        | {h["id"] for h in hotels}
        | set(japan_regions_in_use(hotels))
        | {b["id"] for b in bars}
        | set(bar_regions_in_use(bars))
    )
    n_region_pages = 0
    if eats:
        write_page(PROJECT / "japan" / "index.html", build_japan_index(eats, meta))
        for e in eats:
            write_page(PROJECT / "japan" / e["id"] / "index.html",
                       build_japan_eat_page(e, eats, meta))
        for rkey in japan_regions_in_use(eats):
            pool = [e for e in eats if region_key_of(e) == rkey]
            write_page(PROJECT / "japan" / rkey / "index.html",
                       build_japan_region_page(rkey, pool, meta))
            n_region_pages += 1
    else:
        print("  日本美食專欄：japan.json 無資料或不存在，已略過")

    # 日本酒店專欄（/japan/hotels/、/japan/hotels/<地區>/、/japan/hotels/<id>/）
    n_hotel_region_pages = 0
    if hotels:
        write_page(PROJECT / "japan" / "hotels" / "index.html",
                   build_hotels_index(hotels, meta))
        for h in hotels:
            write_page(PROJECT / "japan" / "hotels" / h["id"] / "index.html",
                       build_hotel_page(h, hotels, meta))
        for rkey in japan_regions_in_use(hotels):
            pool = [h for h in hotels if region_key_of(h) == rkey]
            write_page(PROJECT / "japan" / "hotels" / rkey / "index.html",
                       build_hotel_region_page(rkey, pool, meta))
            n_hotel_region_pages += 1
    else:
        print("  日本酒店專欄：japan-hotels.json 無資料或不存在，已略過")

    # 日本自駕專欄（/japan/drive/、/japan/drive/<地區>/、/japan/drive/<id>/、/japan/drive/guide/）
    routes = load_routes()
    n_drive_region_pages = 0
    if routes:
        write_page(PROJECT / "japan" / "drive" / "index.html",
                   build_drive_index(routes, meta))
        write_page(PROJECT / "japan" / "drive" / "guide" / "index.html",
                   build_drive_guide(routes, meta))
        for r in routes:
            write_page(PROJECT / "japan" / "drive" / r["id"] / "index.html",
                       build_drive_route_page(r, routes, meta))
        for rkey in drive_regions_in_use(routes):
            pool = drive_region_pool(routes, rkey)
            write_page(PROJECT / "japan" / "drive" / rkey / "index.html",
                       build_drive_region_page(rkey, pool, meta))
            n_drive_region_pages += 1
    else:
        print("  日本自駕專欄：japan-drive.json 無資料或不存在，已略過")

    # 日本酒吧專欄（/japan/bars/、/japan/bars/<地區>/、/japan/bars/<id>/、/japan/bars/guide/）
    n_bar_region_pages = 0
    if bars:
        write_page(PROJECT / "japan" / "bars" / "index.html",
                   build_bars_index(bars, meta))
        write_page(PROJECT / "japan" / "bars" / "guide" / "index.html",
                   build_bars_guide(bars, meta))
        for b in bars:
            write_page(PROJECT / "japan" / "bars" / b["id"] / "index.html",
                       build_bar_page(b, bars, meta))
        for rkey in bar_regions_in_use(bars):
            pool = bar_region_pool(bars, rkey)
            write_page(PROJECT / "japan" / "bars" / rkey / "index.html",
                       build_bar_region_page(rkey, pool, meta))
            n_bar_region_pages += 1
    else:
        print("  日本酒吧專欄：japan-bars.json 無資料或不存在，已略過")

    write_page(PROJECT / "about" / "index.html", build_about(deals, meta))
    write_page(PROJECT / "contact" / "index.html", build_contact(deals, meta))
    write_page(PROJECT / "privacy" / "index.html", build_privacy(deals, meta))
    write_page(PROJECT / "terms" / "index.html", build_terms(deals, meta))

    total = build_sitemap(deals, meta, eats, hotels, routes, bars)
    result = {
        "deals": written,
        "pages": written + 4 + 3 + 1 + len(GUIDES) + 4 + len(eats)
                 + (1 if eats else 0) + n_region_pages
                 + len(hotels) + (1 if hotels else 0) + n_hotel_region_pages
                 + len(routes) + (1 if routes else 0) + (1 if routes else 0)
                 + n_drive_region_pages
                 + len(bars) + (1 if bars else 0) + (1 if bars else 0)
                 + n_bar_region_pages,
        "sitemap": total,
    }
    print(
        f"  多頁內容：{written} 個優惠詳情頁、4 個分類／總覽頁、"
        f"{len(eats)} 個日本美食頁（另 {n_region_pages} 個地區排行頁）、"
        f"{len(hotels)} 個日本酒店頁（另 {n_hotel_region_pages} 個地區排行頁）、"
        f"{len(routes)} 個日本自駕頁（另 {n_drive_region_pages} 個地區頁＋1 篇實務指南）、"
        f"{len(bars)} 個日本酒吧頁（另 {n_bar_region_pages} 個地區頁＋1 篇禮儀指南）、"
        f"{len(GUIDES)} 篇攻略、4 個合規頁；"
        f"sitemap 收錄 {total} 條 URL"
        + (f"；已清除 {pruned} 個優惠孤兒頁面" if pruned else "")
        + (f"；已清除 {jpruned} 個日本孤兒頁面" if jpruned else "")
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
