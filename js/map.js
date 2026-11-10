/* Карта маршрута (главная) и карта дня. Данные — window.TRIP из data/trip.js.
   Если Leaflet не загрузился, показываем статичную assets/route-map.png. */
(function () {
  "use strict";
  var T = window.TRIP;
  var TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}";
  var ATTR = "Подложка © Esri";
  var FAR = { transit: 1 };          // пересадки вне Италии: не влияют на масштаб
  var AIR = { airport: 1, transit: 1 };

  function fallback(el) {
    var src = el.getAttribute("data-fallback");
    if (!src) { el.innerHTML = '<p class="muted" style="padding:16px">Карта не загрузилась.</p>'; return; }
    var img = new Image();
    img.src = src;
    img.alt = "Карта маршрута поездки по Италии";
    el.innerHTML = "";
    el.appendChild(img);
  }

  function base(el) {
    var map = L.map(el, { scrollWheelZoom: false, zoomSnap: 0.25, attributionControl: true });
    map.attributionControl.setPrefix(false);
    L.tileLayer(TILES, { attribution: ATTR, maxZoom: 17 }).addTo(map);
    // колесо мыши — только после клика по карте, чтобы страница прокручивалась
    map.once("focus click", function () { map.scrollWheelZoom.enable(); });
    return map;
  }

  // подгоняем масштаб под точки; если размер карты меняется до того, как её тронули, — подгоняем снова
  function fit(map, pts, opts) {
    var touched = false;
    function go() {
      if (pts.length > 1) map.fitBounds(pts, opts);
      else if (pts.length) map.setView(pts[0], opts.single || 11);
      else map.setView([42.5, 12.5], 6);
    }
    map.getContainer().addEventListener("pointerdown", function () { touched = true; });
    map.getContainer().addEventListener("keydown", function () { touched = true; });
    map.on("resize", function () { if (!touched) go(); });
    go();
  }

  function stopById(id) {
    for (var i = 0; i < T.stops.length; i++) if (T.stops[i].id === id) return T.stops[i];
  }

  function pin(stop, future) {
    var cls = "map-pin" + (stop.kind === "stay" ? " stay" : "") + (future ? " future" : "");
    return L.divIcon({ className: "", html: '<span class="' + cls + '"></span>', iconSize: [16, 16], iconAnchor: [8, 8] });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // подпись слева, если справа рядом (≈ до 25 км, та же широта) стоит другая точка
  function labelSide(s) {
    var crowded = T.stops.some(function (o) {
      return o !== s && o.lon > s.lon && o.lon - s.lon < 0.3 && Math.abs(o.lat - s.lat) < 0.06;
    });
    return crowded ? "left" : "right";
  }

  function daysAt(id) {
    return T.days.filter(function (d) { return d.stops.indexOf(id) >= 0; });
  }

  function drawRoute(map, prefix, onlyDate) {
    var r = T.route, bounds = [];
    for (var i = 1; i < r.length; i++) {
      var a = stopById(r[i - 1].id), b = stopById(r[i].id);
      if (onlyDate && r[i].date !== onlyDate) continue;
      var flight = AIR[a.kind] && AIR[b.kind];
      var done = r[i].date <= T.today;
      L.polyline([[a.lat, a.lon], [b.lat, b.lon]], {
        color: flight ? "#23211e" : (done ? "#9a3a1e" : "#5a5146"),
        weight: flight ? 2 : 3,
        opacity: 0.9,
        dashArray: flight ? "2 6" : (done ? null : "6 6"),
        interactive: false
      }).addTo(map);
    }
    var seen = {};
    r.forEach(function (pt) {
      if (seen[pt.id]) return;
      if (onlyDate && daysAt(pt.id).every(function (d) { return d.date !== onlyDate; })) return;
      seen[pt.id] = 1;
      var s = stopById(pt.id);
      var days = daysAt(s.id);
      var future = days.length && days[0].date > T.today;
      var html = "<h3>" + esc(s.name) + "</h3>" + (s.note ? "<p>" + esc(s.note) + "</p>" : "") +
        days.map(function (d) {
          return '<a href="' + prefix + "days/" + d.date + '.html">' + esc(d.label) + " · " + esc(d.title) + "</a>";
        }).join("<br>");
      L.marker([s.lat, s.lon], { icon: pin(s, future), title: s.name, keyboard: true })
        .bindPopup(html)
        .bindTooltip(esc(s.name), { permanent: true, direction: labelSide(s), offset: labelSide(s) === "left" ? [-8, 0] : [8, 0], className: "map-label" })
        .addTo(map);
      if (!FAR[s.kind]) bounds.push([s.lat, s.lon]);
    });
    return bounds;
  }

  function init() {
    var route = document.getElementById("route-map");
    var day = document.getElementById("day-map");
    if (!route && !day) return;
    if (!window.L || !T) { if (route) fallback(route); if (day) fallback(day); return; }

    if (route) {
      route.innerHTML = "";
      var m = base(route);
      var b = drawRoute(m, "", null);
      fit(m, b, { padding: [40, 40], maxZoom: 11 });
    }
    if (day) {
      day.innerHTML = "";
      var date = day.getAttribute("data-date");
      var dm = base(day);
      var info = T.days.filter(function (d) { return d.date === date; })[0];
      var pts = [];
      drawRoute(dm, "../", date);
      // точки дня без сегментов маршрута (например, единственная точка)
      info.stops.forEach(function (id) {
        var s = stopById(id);
        if (!FAR[s.kind] || info.stops.length === 1) pts.push([s.lat, s.lon]);
      });
      fit(dm, pts, { padding: [36, 36], maxZoom: 12, single: 11 });
    }
  }

  if (document.readyState === "complete") init();
  else window.addEventListener("load", init);
})();
