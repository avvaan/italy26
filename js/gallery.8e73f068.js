/* Полноэкранный просмотр фото: клик/Enter открывает, ← → листают, Esc закрывает,
   свайп влево-вправо на телефоне. Без JS ссылки ведут прямо на большой файл. */
(function () {
  "use strict";
  var UI = (window.TRIP && window.TRIP.ui) || { photo_by: "фото: {}", desc_pending: "Описание ещё не одобрено" };
  var links = Array.prototype.slice.call(document.querySelectorAll("a[data-lb]"));
  var box = document.getElementById("lightbox");
  if (!links.length || !box || typeof box.showModal !== "function") return;

  var img = box.querySelector("img");
  var cap = box.querySelector("figcaption");
  var count = box.querySelector(".lb-count");
  var desc = box.querySelector(".lb-desc");
  var cur = 0, opener = null, x0 = null, y0 = null;

  function show(i) {
    cur = (i + links.length) % links.length;
    var a = links[cur], thumb = a.querySelector("img");
    img.removeAttribute("src");
    img.srcset = a.getAttribute("data-srcset") || "";
    img.sizes = "100vw";
    img.src = a.href;
    img.alt = thumb ? thumb.alt : "";
    var c = a.getAttribute("data-caption"), by = a.getAttribute("data-author");
    cap.textContent = c + (c && by ? " · " : "") + (by ? UI.photo_by.replace("{}", by) : "");
    count.textContent = (cur + 1) + " / " + links.length;
    // описание фотографии — абзацами под кадром
    if (desc) {
      var text = a.getAttribute("data-desc") || "";
      desc.textContent = "";
      if (text) {
        if (a.hasAttribute("data-desc-pending")) {
          var mark = document.createElement("p"); mark.className = "pending"; mark.textContent = UI.desc_pending;
          desc.appendChild(mark);
        }
        text.split(/\n\s*\n/).forEach(function (t) {
          var p = document.createElement("p"); p.textContent = t.trim(); desc.appendChild(p);
        });
      }
      desc.hidden = !text;
      box.classList.toggle("has-desc", !!text);
      box.scrollTop = 0;
    }
    // подгружаем соседний кадр заранее
    var n = links[(cur + 1) % links.length];
    if (n) { var pre = new Image(); pre.srcset = n.getAttribute("data-srcset") || ""; pre.sizes = "100vw"; }
  }

  links.forEach(function (a, i) {
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      opener = a;
      show(i);
      box.showModal();
      box.querySelector(".lb-close").focus();
    });
  });

  box.querySelector(".lb-prev").addEventListener("click", function () { show(cur - 1); });
  box.querySelector(".lb-next").addEventListener("click", function () { show(cur + 1); });
  box.querySelector(".lb-close").addEventListener("click", function () { box.close(); });
  box.addEventListener("close", function () { if (opener) setTimeout(function () { opener.focus(); }, 0); });
  box.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowLeft") { ev.preventDefault(); show(cur - 1); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); show(cur + 1); }
  });
  // клик по тёмному полю вокруг фото закрывает
  box.addEventListener("click", function (ev) {
    if (ev.target === box || ev.target.tagName === "FIGURE") box.close();
  });

  box.addEventListener("touchstart", function (ev) {
    if (ev.touches.length !== 1) return;
    x0 = ev.touches[0].clientX; y0 = ev.touches[0].clientY;
  }, { passive: true });
  box.addEventListener("touchend", function (ev) {
    if (x0 === null) return;
    var dx = ev.changedTouches[0].clientX - x0, dy = ev.changedTouches[0].clientY - y0;
    x0 = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) show(cur + (dx < 0 ? 1 : -1));
    else if (dy > 90 && Math.abs(dy) > Math.abs(dx) * 1.5 && box.scrollTop <= 0) box.close();   // смахнуть вниз — закрыть (только с самого верха)
  }, { passive: true });
})();
