/* «Что это?» — кнопка на фото открывает панель с описанием кадра.
   Справа на компьютере, снизу на телефоне. Esc или крестик закрывает,
   «Открыть фото целиком» переходит в полноэкранный просмотр. */
(function () {
  "use strict";
  var box = document.getElementById("about");
  if (!box || typeof box.showModal !== "function") return;
  var title = box.querySelector(".about-title");
  var text = box.querySelector(".about-text");
  var thumb = box.querySelector(".about-thumb");
  var openBtn = box.querySelector(".about-open");
  var link = null, opener = null;

  function fill(a) {
    var img = a.querySelector("img");
    title.textContent = img ? img.alt : "";
    thumb.src = a.href.replace(/-1800\.webp$/, "-900.webp");
    thumb.alt = "";
    text.textContent = "";
    (a.getAttribute("data-desc") || "").split(/\n\s*\n/).forEach(function (t) {
      if (!t.trim()) return;
      var p = document.createElement("p"); p.textContent = t.trim(); text.appendChild(p);
    });
  }

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest(".ph-what");
    if (!btn) return;
    ev.preventDefault();
    link = btn.parentNode.querySelector("a[data-lb]");
    if (!link) return;
    opener = btn;
    fill(link);
    box.showModal();
    box.querySelector(".about-in").scrollTop = 0;
    box.querySelector(".about-close").focus();
  });

  box.querySelector(".about-close").addEventListener("click", function () { box.close(); });
  box.addEventListener("click", function (ev) { if (ev.target === box) box.close(); });   // клик мимо панели
  box.addEventListener("close", function () { if (opener) setTimeout(function () { opener.focus(); }, 0); });
  openBtn.addEventListener("click", function () {
    var a = link;
    opener = null;
    box.close();
    if (a) a.click();
  });
})();
