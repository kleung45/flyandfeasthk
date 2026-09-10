/* Fly & Feast HK — 前端邏輯
   資料來源優先序：window.DEAL_DATA（data/deals.js）
   若不存在則嘗試 fetch('data/deals.json')，方便部署在伺服器時使用。 */
(function () {
  "use strict";

  var state = { cat: "all", q: "", sort: "ending", hideExpired: true };
  var data = null;

  var el = {
    grid: document.getElementById("grid"),
    empty: document.getElementById("empty"),
    q: document.getElementById("q"),
    sort: document.getElementById("sort"),
    hideExpired: document.getElementById("hideExpired"),
    updated: document.getElementById("updated"),
    notice: document.getElementById("sampleNotice"),
    stats: {
      active: document.getElementById("statActive"),
      ending: document.getElementById("statEnding"),
      flight: document.getElementById("statFlight"),
      dining: document.getElementById("statDining")
    }
  };

  var CAT_LABEL = { flight: "機票", dining: "餐飲", hotel: "酒店" };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function categoryBadge(cat) {
    var cls = cat === "flight" ? "badge-flight" : cat === "dining" ? "badge-dining" : "badge-hotel";
    return '<span class="badge ' + cls + '">' + esc(CAT_LABEL[cat] || "優惠") + "</span>";
  }

  function statusBadge(deal) {
    if (deal.status === "expired") return '<span class="badge badge-expired">已結束</span>';
    if (deal.status === "ending") return '<span class="badge badge-urgent">' + esc(countdown(deal)) + "</span>";
    return "";
  }

  function countdown(deal) {
    if (deal.status === "expired") return "已結束";
    var d = deal.daysLeft;
    if (d === 0) return "今日結束";
    if (d === 1) return "明日結束";
    if (typeof d === "number") return "剩 " + d + " 日";
    return "";
  }

  function formatUpdated(iso) {
    if (!iso) return "";
    var dt = new Date(iso);
    if (isNaN(dt.getTime())) return "";
    var pad = function (n) { return n < 10 ? "0" + n : String(n); };
    return dt.getFullYear() + "-" + pad(dt.getMonth() + 1) + "-" + pad(dt.getDate()) +
      " " + pad(dt.getHours()) + ":" + pad(dt.getMinutes());
  }

  function card(deal) {
    var cls = "card" + (deal.status === "expired" ? " is-expired" : "");
    var route = deal.route || deal.venue || "";
    var badges = categoryBadge(deal.category) + statusBadge(deal);
    if (deal.sample) badges += '<span class="badge badge-sample">示範</span>';

    var save = "";
    if (deal.discountPct) save = '<span class="save">省 ' + esc(deal.discountPct) + "%</span>";

    var highlights = "";
    if (deal.highlights && deal.highlights.length) {
      highlights = "<ul>" + deal.highlights.map(function (h) {
        return "<li>" + esc(h) + "</li>";
      }).join("") + "</ul>";
    }

    var source = "";
    if (deal.sourceLabel) {
      source = '<p class="source">來源：' +
        (deal.sourceUrl
          ? '<a href="' + esc(deal.sourceUrl) + '" target="_blank" rel="noopener nofollow">' + esc(deal.sourceLabel) + "</a>"
          : esc(deal.sourceLabel)) +
        "</p>";
    }

    var share = "";
    if (deal.status !== "expired") {
      share = '<button class="icon-btn" type="button" data-share="' + esc(deal.id) + '">分享</button>';
    }

    var cta = deal.status === "expired"
      ? '<span class="period">優惠已結束</span>'
      : '<a class="link-btn" href="' + esc(deal.url || "#") + '" target="_blank" rel="noopener nofollow">查看優惠 →</a>';

    return '<article class="' + cls + '" data-id="' + esc(deal.id) + '">' +
      '<div class="card-top">' + badges + "</div>" +
      "<h3>" + esc(deal.title) + "</h3>" +
      (deal.subtitle ? '<p class="sub">' + esc(deal.subtitle) + "</p>" : "") +
      (route ? '<p class="route">' + esc(route) + "</p>" : "") +
      '<div class="price-row">' +
        '<span class="price">' + esc(deal.priceLabel || "") + "</span>" +
        (deal.originalLabel ? '<span class="price-was">' + esc(deal.originalLabel) + "</span>" : "") +
        save +
      "</div>" +
      (deal.summary ? '<p class="summary">' + esc(deal.summary) + "</p>" : "") +
      highlights +
      '<div class="card-foot">' +
        '<span class="period">' + esc(deal.period || countdown(deal)) + "</span>" +
        '<span class="actions">' + share + cta + "</span>" +
      "</div>" +
      source +
    "</article>";
  }

  function visibleDeals() {
    var list = (data && data.deals) || [];
    var q = state.q.trim().toLowerCase();

    list = list.filter(function (d) {
      if (state.cat !== "all" && d.category !== state.cat) return false;
      if (state.hideExpired && d.status === "expired") return false;
      if (!q) return true;
      var hay = [d.title, d.subtitle, d.route, d.venue, d.summary, d.sourceLabel,
        (d.tags || []).join(" ")].join(" ").toLowerCase();
      return hay.indexOf(q) !== -1;
    });

    var order = { ending: 0, active: 1, unknown: 2, expired: 3 };
    list.sort(function (a, b) {
      if (state.sort === "price") {
        return (a.priceValue || Infinity) - (b.priceValue || Infinity);
      }
      if (state.sort === "discount") {
        return (b.discountPct || 0) - (a.discountPct || 0);
      }
      var oa = order[a.status], ob = order[b.status];
      if (oa !== ob) return oa - ob;
      return String(a.endsAt || "9999").localeCompare(String(b.endsAt || "9999"));
    });

    return list;
  }

  function renderStats() {
    var deals = (data && data.deals) || [];
    var active = deals.filter(function (d) { return d.status === "active" || d.status === "ending"; });
    el.stats.active.textContent = active.length;
    el.stats.ending.textContent = deals.filter(function (d) { return d.status === "ending"; }).length;
    el.stats.flight.textContent = active.filter(function (d) { return d.category === "flight"; }).length;
    el.stats.dining.textContent = active.filter(function (d) { return d.category === "dining"; }).length;
  }

  function render() {
    var list = visibleDeals();
    el.grid.innerHTML = list.map(card).join("");
    el.empty.hidden = list.length > 0;
  }

  function bind() {
    document.querySelectorAll(".chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        document.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("is-active"); });
        chip.classList.add("is-active");
        state.cat = chip.dataset.cat;
        render();
      });
    });

    el.q.addEventListener("input", function () { state.q = el.q.value; render(); });
    el.sort.addEventListener("change", function () { state.sort = el.sort.value; render(); });
    el.hideExpired.addEventListener("change", function () {
      state.hideExpired = el.hideExpired.checked;
      render();
    });

    el.grid.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-share]");
      if (!btn) return;
      var id = btn.dataset.share;
      var deal = (data.deals || []).filter(function (d) { return d.id === id; })[0];
      if (!deal) return;
      var url = deal.url || (data.meta && data.meta.siteUrl) || location.href;
      var shareUrl = "https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(url);
      window.open(shareUrl, "_blank", "noopener,width=640,height=560");
    });

    if (el.notice) {
      var dismissed = false;
      try { dismissed = localStorage.getItem("ff-notice") === "1"; } catch (err) { dismissed = false; }
      if (data && data.meta && data.meta.sample && !dismissed) el.notice.hidden = false;
      var closeBtn = document.getElementById("noticeClose");
      if (closeBtn) {
        closeBtn.addEventListener("click", function () {
          el.notice.hidden = true;
          try { localStorage.setItem("ff-notice", "1"); } catch (err) { /* 忽略 */ }
        });
      }
    }

    var form = document.getElementById("subForm");
    var msg = document.getElementById("subMsg");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var email = document.getElementById("email").value.trim();
        var valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
        msg.classList.toggle("is-error", !valid);
        if (!valid) {
          msg.textContent = "請輸入有效的電郵地址。";
          return;
        }
        msg.textContent = "已記錄，接上郵件服務後即可開始發送提醒。";
        form.reset();
      });
    }

    var year = document.getElementById("year");
    if (year) year.textContent = new Date().getFullYear();
  }

  function start(payload) {
    data = payload || { meta: {}, deals: [] };
    if (el.updated) {
      var when = formatUpdated(data.meta && data.meta.updated);
      var n = (data.deals || []).length;
      el.updated.textContent = when ? "資料更新於 " + when + " · 共 " + n + " 筆紀錄" : "共 " + n + " 筆紀錄";
    }
    renderStats();
    render();
    bind();
  }

  if (window.DEAL_DATA) {
    start(window.DEAL_DATA);
  } else {
    fetch("data/deals.json")
      .then(function (r) { return r.json(); })
      .then(start)
      .catch(function () {
        el.grid.innerHTML = '<p class="empty">載入優惠資料失敗，請確認 data/deals.js 是否存在。</p>';
      });
  }
})();
