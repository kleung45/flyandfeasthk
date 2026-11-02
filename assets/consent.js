/* 廣告與分析 Cookie 同意橫幅
 *
 * 設計取向：
 * 1. 預設「非個人化廣告」（NPA=1），由 <head> 的 inline script 在任何廣告請求之前設定。
 * 2. 用戶按「接受」才轉為個人化廣告；按「只接受必要」則維持非個人化。
 * 3. 選擇寫入 localStorage，180 日後重新詢問。
 * 4. 橫幅只控制個人化與否，不阻擋廣告代碼載入——AdSense 需要見到 script 才可驗證網站。
 *
 * 注意：這不是 Google 認證的 CMP。EEA／英國流量仍建議在 AdSense 後台啟用
 * Google 的隱私權訊息（Funding Choices）。此橫幅針對香港及亞洲主要流量。
 */
(function () {
  "use strict";

  var KEY = "ff_consent_v1";
  var DAYS = 180;

  function read() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return null;
      var obj = JSON.parse(raw);
      if (!obj || !obj.choice || !obj.ts) return null;
      var age = (Date.now() - obj.ts) / 86400000;
      if (age > DAYS) return null;
      return obj;
    } catch (e) {
      return null;
    }
  }

  function save(choice) {
    try {
      localStorage.setItem(KEY, JSON.stringify({ choice: choice, ts: Date.now() }));
    } catch (e) {
      /* 私密模式或封鎖儲存：本次有效即可 */
    }
    apply(choice);
  }

  function apply(choice) {
    var ads = (window.adsbygoogle = window.adsbygoogle || []);
    ads.requestNonPersonalizedAds = choice === "granted" ? 0 : 1;
    /* GA4：拒絕時不再送個人化廣告訊號（GA 本身已在頁面載入，這裡只調整廣告訊號） */
    if (typeof window.gtag === "function") {
      window.gtag("consent", "update", {
        ad_storage: choice === "granted" ? "granted" : "denied",
        ad_user_data: choice === "granted" ? "granted" : "denied",
        ad_personalization: choice === "granted" ? "granted" : "denied"
      });
    }
  }

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k)) n.setAttribute(k, attrs[k]);
      }
    }
    if (text) n.appendChild(document.createTextNode(text));
    return n;
  }

  function build() {
    if (document.getElementById("ff-consent")) return;

    var wrap = el("div", {
      id: "ff-consent",
      role: "dialog",
      "aria-modal": "false",
      "aria-label": "廣告與分析 Cookie 選擇",
      style: [
        "position:fixed",
        "left:16px",
        "right:16px",
        "bottom:16px",
        "z-index:2147483000",
        "max-width:760px",
        "margin:0 auto",
        "background:#1b1d21",
        "color:#f4f4f5",
        "border:1px solid rgba(255,255,255,.14)",
        "border-radius:14px",
        "box-shadow:0 18px 48px rgba(0,0,0,.42)",
        "padding:16px 18px",
        "font-size:14px",
        "line-height:1.6",
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans TC',sans-serif"
      ].join(";")
    });

    var title = el("strong", { style: "display:block;font-size:15px;margin-bottom:6px" }, "廣告與 Cookie 選擇");
    var p = el(
      "p",
      { style: "margin:0 0 12px;color:#c9ccd1" },
      "本站用 Cookie 顯示廣告（Google AdSense）及統計用量。你可以選擇接受個人化廣告，或只容許必要的非個人化廣告。"
    );
    var link = el(
      "a",
      { href: "/privacy/", style: "color:#9ecbff;text-decoration:underline" },
      "隱私政策"
    );

    var row = el("div", { style: "display:flex;flex-wrap:wrap;gap:8px;align-items:center" });
    var yes = el(
      "button",
      {
        type: "button",
        style: [
          "appearance:none",
          "border:0",
          "border-radius:9px",
          "padding:9px 16px",
          "font-size:14px",
          "font-weight:600",
          "cursor:pointer",
          "background:#E5484D",
          "color:#fff"
        ].join(";")
      },
      "接受個人化廣告"
    );
    var no = el(
      "button",
      {
        type: "button",
        style: [
          "appearance:none",
          "border:1px solid rgba(255,255,255,.28)",
          "border-radius:9px",
          "padding:9px 16px",
          "font-size:14px",
          "cursor:pointer",
          "background:transparent",
          "color:#f4f4f5"
        ].join(";")
      },
      "只接受必要"
    );

    yes.addEventListener("click", function () {
      save("granted");
      close();
    });
    no.addEventListener("click", function () {
      save("denied");
      close();
    });

    row.appendChild(yes);
    row.appendChild(no);
    wrap.appendChild(title);
    wrap.appendChild(p);
    wrap.appendChild(row);
    var foot = el("p", { style: "margin:10px 0 0;font-size:12px;color:#9aa0a6" });
    foot.appendChild(link);
    wrap.appendChild(foot);
    document.body.appendChild(wrap);
  }

  function close() {
    var n = document.getElementById("ff-consent");
    if (n && n.parentNode) n.parentNode.removeChild(n);
  }

  function init() {
    var saved = read();
    if (saved) {
      apply(saved.choice);
    } else {
      apply("denied");
      build();
    }
    window.ffConsent = {
      open: function () {
        build();
      },
      choice: function () {
        var s = read();
        return s ? s.choice : null;
      }
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
