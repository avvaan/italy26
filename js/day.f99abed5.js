/* Страница дня: кадры и абзацы проявляются при прокрутке, сверху тонкая полоса
   прочитанного, обложка чуть отстаёт при прокрутке. Без JS всё просто видно сразу. */
(function () {
  "use strict";
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var items = Array.prototype.slice.call(document.querySelectorAll("[data-reveal]"));

  // проявление
  if (!("IntersectionObserver" in window) || still) {
    items.forEach(function (el) { el.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    items.forEach(function (el) { io.observe(el); });
  }

  // полоса прочитанного и лёгкий параллакс обложки
  var bar = document.querySelector(".progress span");
  var hero = document.querySelector(".hero-media img");
  var heroBox = document.querySelector(".hero");
  var ticking = false;
  function frame() {
    ticking = false;
    var y = window.scrollY || window.pageYOffset;
    var max = document.documentElement.scrollHeight - window.innerHeight;
    if (bar) bar.style.transform = "scaleX(" + (max > 0 ? Math.min(1, y / max) : 0) + ")";
    if (hero && !still && heroBox) {
      var h = heroBox.offsetHeight;
      if (y < h) hero.style.transform = "translateY(" + (y * 0.18).toFixed(1) + "px) scale(1.04)";
    }
  }
  function onScroll() { if (!ticking) { ticking = true; window.requestAnimationFrame(frame); } }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  frame();
})();
