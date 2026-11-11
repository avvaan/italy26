#!/usr/bin/env python3
"""Собирает сайт из data/trip.json.

    python3 tools/build.py            # публичная сборка: только одобренное
    python3 tools/build.py --preview  # для о. Андрея: всё, неодобренное помечено

Пишет index.html, days/<дата>.html и data/trip.js. Только стандартная библиотека.
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TRIP = ROOT / "data" / "trip.json"
SIZES = (400, 900, 1800)

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
KIND = {"town": "город", "stay": "жильё", "site": "место", "airport": "аэропорт", "transit": "пересадка"}

warnings = []


def warn(msg):
    warnings.append(msg)


USED_ASSETS = set()


def v(path):
    """Отпечаток содержимого прямо в имени файла: css/site.3a6ae7c7.css.
    Кэш Render/Cloudflare не смотрит на «?v=…», а новое имя он не перепутает."""
    import hashlib
    f = ROOT / path
    if not f.exists():
        return path
    h = hashlib.sha1(f.read_bytes()).hexdigest()[:8]
    out = f.with_name(f"{f.stem}.{h}{f.suffix}")
    if not out.exists():
        out.write_bytes(f.read_bytes())
    USED_ASSETS.add(out)
    return str(out.relative_to(ROOT))


def clean_assets():
    """Убрать старые копии с отпечатком, на которые страницы больше не ссылаются."""
    import re
    pat = re.compile(r"\.[0-9a-f]{8}\.(css|js)$")
    for d in ("css", "js", "data"):
        for f in (ROOT / d).glob("*.*.*"):
            if pat.search(f.name) and f not in USED_ASSETS:
                f.unlink()


def e(s):
    return html.escape(str(s or ""), quote=True)


def roman(n):
    out = ""
    for v, r in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                 (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + r, n - v
    return out


def ru_date(d, year=False):
    s = f"{d.day} {MONTHS[d.month - 1]}"
    return f"{s} {d.year}" if year else s


def excerpt(text, limit=150):
    if not text:
        return ""
    first = re.split(r"(?<=[.!?…])\s", text[0].strip(), maxsplit=1)[0]
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0] + "…"
    return first


# --------------------------------------------------------------- data model

def load(preview):
    trip = json.loads(TRIP.read_text(encoding="utf-8"))
    stops = {s["id"]: s for s in trip["stops"]}
    audio = {a["id"]: a for a in trip.get("audio", [])}
    pages = trip["pages"]
    for i, p in enumerate(pages):
        p["n"] = i + 1
        p["d"] = dt.date.fromisoformat(p["date"])
        p["url"] = f"days/{p['date']}.html"
        p["title"] = p.get("title") or f"День {i + 1}"
        for sid in p.get("stops", []):
            if sid not in stops:
                sys.exit(f"{p['date']}: неизвестная точка «{sid}» — добавьте её в stops")
        for aid in p.get("audio", []):
            if aid not in audio:
                sys.exit(f"{p['date']}: неизвестная запись «{aid}» — добавьте её в audio")
        # тексты и фото показываем только одобренные (в предпросмотре — всё, с пометкой)
        text_ok = p.get("text_approved", False)
        p["show_text"] = p.get("text", []) if (text_ok or preview) else []
        p["text_pending"] = bool(p.get("text")) and not text_ok
        shown = []
        for ph in p.get("photos", []):
            ok = ph.get("approved", False)
            if ok or preview:
                shown.append(dict(ph, pending=not ok))
            if not ok:
                warn(f"{p['date']}: фото {ph.get('src')} ждёт одобрения")
        p["show_photos"] = shown
        if p["text_pending"]:
            warn(f"{p['date']}: текст ждёт одобрения")
    for a in audio.values():
        a["exists"] = (ROOT / a["file"]).is_file()
        if not a["exists"]:
            warn(f"аудио {a['id']}: нет файла {a['file']}")
    return trip, stops, audio, pages


def route(pages, stops):
    """Маршрут — точки дней по порядку, без повторов подряд."""
    pts = []
    for p in pages:
        for sid in p.get("stops", []):
            if not pts or pts[-1]["id"] != sid:
                pts.append({"id": sid, "date": p["date"]})
    return pts


def roads():
    f = ROOT / "data" / "roads.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def write_trip_js(trip, stops, pages, rt):
    today = dt.datetime.now(ZoneInfo(trip["meta"]["timezone"])).date().isoformat()
    data = {
        "today": today,
        "stops": [{k: s.get(k) for k in ("id", "name", "lat", "lon", "kind", "note")} for s in stops.values()],
        "route": rt,
        # дороги между остановками (tools/road_routes.py); нет отрезка — карта рисует прямую
        "roads": {k: v["path"] for k, v in roads().items()},
        "days": [{"date": p["date"], "n": p["n"], "title": p["title"], "stops": p.get("stops", []),
                  "label": ru_date(p["d"])} for p in pages],
    }
    js = "window.TRIP=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (ROOT / "data" / "trip.js").write_text(js, encoding="utf-8")


# --------------------------------------------------------------- fragments

FONTS = ("https://fonts.googleapis.com/css2?family=Forum&family=Literata:ital,opsz,wght@"
         "0,7..72,400;0,7..72,600;1,7..72,400&display=swap&subset=cyrillic")
LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"


def head(trip, title, desc, base, extra=""):
    robots = "" if trip["meta"].get("published") else '<meta name="robots" content="noindex, nofollow">\n'
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<script>document.documentElement.classList.add("js")</script>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{robots}<meta name="theme-color" content="#000000">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="{base}{v('css/site.css')}">
{extra}</head>
<body>
<a class="skip" href="#main">К содержанию</a>
"""


def site_header(base, here=""):
    nav = [("Дни", f"{base}index.html#days"), ("Маршрут", f"{base}index.html#route"),
           ("Аудио", f"{base}index.html#audio"), ("Фильм", f"{base}index.html#film")]
    links = "".join(f'<a href="{u}">{t}</a>' for t, u in nav)
    return f"""<header class="site-head">
  <a class="wordmark" href="{base}index.html" aria-label="Италия 2026 — на главную">Italia<span aria-hidden="true">·</span>MMXXVI</a>
  <nav aria-label="Разделы">{links}</nav>
</header>
"""


def site_footer(trip):
    y = trip["meta"]["date_from"][:4]
    return f"""<footer class="site-foot">
  <p class="inscr">{e(trip['meta']['subtitle'])}<span aria-hidden="true"> · </span>{y}</p>
  <p class="fine">Карта: подложка © Esri. Фотографии — семейные, без разрешения не копировать.</p>
</footer>
"""


def stripe():
    return '<div class="stripe" aria-hidden="true"></div>\n'


def img_tag(ph, base, sizes, cls="", eager=False):
    src = ph["src"]
    srcset = ", ".join(f"{base}{src}-{w}.webp {w}w" for w in SIZES)
    w, h = ph.get("w"), ph.get("h")
    dims = f' width="{w}" height="{h}"' if w and h else ""
    load = 'fetchpriority="high"' if eager else 'loading="lazy" decoding="async"'
    return (f'<img class="{cls}" src="{base}{src}-900.webp" srcset="{srcset}" sizes="{sizes}"'
            f'{dims} alt="{e(ph.get("alt"))}" {load}>')


def stop_names(p, stops):
    return [stops[s]["name"] for s in p.get("stops", [])]


def audio_item(a, base):
    if not a["exists"]:
        return f'<li class="audio-item"><p class="audio-title">{e(a["title"])}</p><p class="muted">Запись появится позже.</p></li>'
    dur = f' <span class="muted">· {e(a["duration"])}</span>' if a.get("duration") else ""
    return (f'<li class="audio-item"><p class="audio-title">{e(a["title"])}{dur}</p>'
            f'<audio controls preload="none" src="{base}{e(a["file"])}"></audio></li>')


# --------------------------------------------------------------- pages

def build_index(trip, stops, audio, pages, preview):
    m = trip["meta"]
    d0, d1 = dt.date.fromisoformat(m["date_from"]), dt.date.fromisoformat(m["date_to"])
    dates = f"{ru_date(d0)} — {ru_date(d1, year=True)}"
    out = [head(trip, m["title"], f"{m['subtitle']}: {dates}. Семейная книга о поездке.", "",
                f'<link rel="stylesheet" href="{LEAFLET_CSS}">\n'), site_header("")]
    out.append('<main id="main">\n')

    # обложка: фото из meta.cover (путь src одобренного фото) или первое одобренное
    cover = None
    allph = [ph for p in pages for ph in p["show_photos"]]
    if m.get("cover"):
        cover = next((ph for ph in allph if ph["src"] == m["cover"]), None)
    cover = cover or (allph[0] if allph else None)
    fig = ""
    if cover:
        fig = (f'<figure class="cover-photo">{img_tag(cover, "", "(min-width: 900px) 60vw, 100vw", eager=True)}'
               f'{"<figcaption>" + e(cover.get("caption")) + "</figcaption>" if cover.get("caption") else ""}</figure>')
    out.append(f"""<section class="cover{' has-photo' if cover else ''}">
  <div class="cover-text">
    <p class="eyebrow">Семейная поездка</p>
    <h1 class="display">Италия</h1>
    <p class="cover-dates">{e(dates)}</p>
    <p class="cover-who">{e(m['subtitle'])}</p>
  </div>
  {fig}
</section>
""")
    out.append(stripe())

    # карта
    out.append("""<section class="block" id="route" aria-labelledby="route-h">
  <div class="block-head"><p class="eyebrow">Iter</p><h2 id="route-h">Маршрут</h2></div>
  <div class="map map-route" id="route-map" data-fallback="assets/route-map.png" role="region" aria-label="Карта маршрута">
    <noscript><img src="assets/route-map.png" alt="Карта маршрута поездки по Италии"></noscript>
  </div>
  <p class="map-legend"><span class="lg lg-done"></span>пройдено <span class="lg lg-plan"></span>впереди <span class="lg lg-air"></span>перелёт</p>
</section>
""")

    # лента дней
    cards = []
    for p in pages:
        phs = p["show_photos"]
        date_on = (f'<span class="card-on"><span class="num">{p["d"].day}</span>'
                   f'<span class="mon">{MONTHS[p["d"].month - 1]}<br>Dies {roman(p["n"])}</span>'
                   f'{f"<span class=card-count>{len(phs)} фото</span>" if phs else ""}</span>')
        if len(phs) >= 2:
            visual = (f'<span class="card-vis card-pair">{img_tag(phs[0], "", "(min-width: 900px) 25vw, 50vw", "card-img")}'
                      f'{img_tag(phs[1], "", "(min-width: 900px) 25vw, 50vw", "card-img")}{date_on}</span>')
        elif phs:
            visual = f'<span class="card-vis">{img_tag(phs[0], "", "(min-width: 900px) 50vw, 100vw", "card-img")}{date_on}</span>'
        else:
            visual = f'<span class="card-vis card-blank" aria-hidden="true">{roman(p["n"])}{date_on}</span>'
        places = " · ".join(e(n) for n in stop_names(p, stops))
        line = excerpt(p["show_text"])
        cards.append(f"""<li data-reveal><a class="day-card" href="{p['url']}">
  {visual}
  <span class="card-title">{e(p['title'])}</span>
  {f'<span class="card-places">{places}</span>' if places else ''}
  {f'<span class="card-line">{e(line)}</span>' if line else ''}
</a></li>""")
    out.append(f"""<section class="block" id="days" aria-labelledby="days-h">
  <div class="block-head"><p class="eyebrow">Dies</p><h2 id="days-h">День за днём</h2></div>
  <ol class="day-list">
{chr(10).join(cards)}
  </ol>
</section>
""")

    # аудио
    if audio:
        groups = []
        for p in pages:
            items = [audio[a] for a in p.get("audio", [])]
            if items:
                groups.append(f'<div class="audio-group"><h3><a href="{p["url"]}">{ru_date(p["d"])} · {e(p["title"])}</a></h3>'
                              f'<ul class="audio-list">{"".join(audio_item(a, "") for a in items)}</ul></div>')
        loose = [a for a in audio.values() if not any(a["id"] in p.get("audio", []) for p in pages)]
        if loose:
            groups.append(f'<div class="audio-group"><h3>Без дня</h3><ul class="audio-list">'
                          f'{"".join(audio_item(a, "") for a in loose)}</ul></div>')
        out.append(f"""<section class="block" id="audio" aria-labelledby="audio-h">
  <div class="block-head"><p class="eyebrow">Vox</p><h2 id="audio-h">Аудиорассказы</h2></div>
  {''.join(groups)}
</section>
""")

    # фильм
    film = trip.get("film") or {}
    body = (f'<p><a class="chip" href="{e(film["url"])}">Смотреть фильм</a></p>' if film.get("url")
            else '<p class="soon">Скоро</p><p class="muted">Фильм о поездке монтируется отдельно.</p>')
    out.append(f"""<section class="block" id="film" aria-labelledby="film-h">
  <div class="block-head"><p class="eyebrow">Pictura</p><h2 id="film-h">Фильм</h2></div>
  <div class="film">{body}</div>
</section>
""")
    out.append("</main>\n")
    out.append(site_footer(trip))
    out.append(f'<script src="{v("data/trip.js")}"></script>\n<script defer src="{LEAFLET_JS}"></script>\n'
               f'<script defer src="{v("js/map.js")}"></script>\n<script defer src="{v("js/day.js")}"></script>\n</body>\n</html>\n')
    return "".join(out)


def byline(cap, by):
    who = f'<span class="muted">фото: {e(by)}</span>' if by else ""
    return f"{e(cap)} · {who}" if cap and who else (e(cap) or who)


# --------------------------------------------------------------- день: сцены «текст + фото»

def is_tall(ph):
    return (ph.get("h") or 2) > (ph.get("w") or 3) * 1.05


def photo(ph, idx, total, sizes, cls="", eager=False, reveal=True):
    """Фото-ссылка для полноэкранного просмотра; подпись лежит прямо на кадре."""
    cap, by = ph.get("caption") or "", ph.get("author") or ""
    full = ", ".join(f"../{ph['src']}-{s}.webp {s}w" for s in SIZES)
    mark = '<span class="pending">не одобрено</span>' if ph.get("pending") else ""
    label = [f"{idx:02d} / {total:02d}"] + ([e(cap)] if cap else []) + ([f"фото: {e(by)}"] if by else [])
    shape = " tall" if is_tall(ph) else ""
    rv = " data-reveal" if reveal else ""
    return (f'<figure class="ph {cls}{shape}"{rv}>'
            f'<a href="../{ph["src"]}-1800.webp" data-lb data-srcset="{full}" data-caption="{e(cap)}" data-author="{e(by)}">'
            f'{img_tag(ph, "../", sizes, eager=eager)}</a>'
            f'<figcaption class="ph-cap" aria-hidden="true">{" <span>·</span> ".join(label)}{mark}</figcaption></figure>')


def pair(items, total, cls=""):
    """Пара кадров рядом в общей скруглённой рамке (приём BAM)."""
    tall = any(is_tall(ph) for ph, _ in items)
    figs = "".join(photo(ph, i, total, "(min-width: 700px) 50vw, 100vw") for ph, i in items)
    return f'<div class="pair{" pair-tall" if tall else ""} {cls}">{figs}</div>'


def media_run(items, total):
    """Несколько кадров подряд: крупный, потом пара, потом снова крупный…"""
    out, k, single = [], 0, True
    while k < len(items):
        if not single and k + 1 < len(items):
            out.append(pair(items[k:k + 2], total)); k += 2
        else:
            ph, i = items[k]
            out.append(photo(ph, i, total, "(min-width: 900px) 58vw, 100vw", "ph-col")); k += 1
        single = not single
    return "".join(out)


def story_scenes(p):
    paras = p["show_text"]
    photos = p["show_photos"]
    total = len(photos)
    rest = [(ph, i) for i, ph in enumerate(photos, 1)][1:]          # первый кадр — на обложке дня
    n, m = len(paras), len(rest)
    if not n:
        if not rest:
            return '<section class="scene scene-text"><div class="sc-text"><p class="muted">Рассказ этого дня появится позже.</p></div></section>'
        return f'<section class="scene scene-sticky scene-notext"><div class="sc-media">{media_run(rest, total)}</div></section>'
    out, used = [], 0
    for i, t in enumerate(paras):
        k = (i + 1) * m // n - i * m // n                              # кадры поровну между абзацами
        chunk, used = rest[used:used + k], used + k
        cls = ' class="first"' if i == 0 else ""
        para = f"<p{cls}>{e(t)}</p>"
        side = "left" if i % 2 == 0 else "right"
        if not chunk:
            out.append(f'<section class="scene scene-text"><div class="sc-text" data-reveal>{para}</div></section>')
        elif len(chunk) == 1 and not is_tall(chunk[0][0]):
            ph, j = chunk[0]
            out.append(f'<section class="scene scene-over {side}">{photo(ph, j, total, "100vw", "ph-full")}'
                       f'<div class="sc-card" data-reveal>{para}</div></section>')
        elif len(chunk) == 2:
            out.append(f'<section class="scene scene-pair"><div class="sc-text" data-reveal>{para}</div>{pair(chunk, total)}</section>')
        else:
            out.append(f'<section class="scene scene-sticky {side}"><div class="sc-side"><div class="sc-card" data-reveal>{para}</div></div>'
                       f'<div class="sc-media">{media_run(chunk, total)}</div></section>')
    return "\n".join(out)


def build_day(trip, stops, audio, pages, i, preview):
    p = pages[i]
    d = p["d"]
    prev_p, next_p = (pages[i - 1] if i else None), (pages[i + 1] if i + 1 < len(pages) else None)
    places = stop_names(p, stops)
    desc = f"{ru_date(d, True)}. " + (", ".join(places) if places else trip["meta"]["title"])
    out = [head(trip, f"{p['title']} — {ru_date(d)} · {trip['meta']['title']}", desc, "../",
                f'<link rel="stylesheet" href="{LEAFLET_CSS}">\n'), site_header("../")]
    out.append('<div class="progress" aria-hidden="true"><span></span></div>\n<main id="main" class="day">\n')
    place_html = "".join(f'<li>{e(stops[s]["name"])}</li>' for s in dict.fromkeys(p.get("stops", [])))
    photos = p["show_photos"]
    lead = photos[0] if photos else None
    count = f'<p class="hero-count">{len(photos)} фото</p>' if photos else ""
    media = (f'<div class="hero-media">{photo(lead, 1, len(photos), "100vw", "ph-hero", eager=True, reveal=False)}</div>'
             if lead else "")
    out.append(f"""<header class="hero{'' if lead else ' no-photo'}">
  {media}
  <div class="hero-text">
    <p class="eyebrow">День {p['n']} <span aria-hidden="true">·</span> Dies {roman(p['n'])}</p>
    <p class="hero-date"><span class="num">{d.day}</span><span class="mon">{MONTHS[d.month - 1]} {d.year}<br><i>{WEEKDAYS[d.weekday()]}</i></span></p>
    <h1>{e(p['title'])}</h1>
    {f'<ul class="places" aria-label="Места">{place_html}</ul>' if place_html else ''}
  </div>
  {count}
  {'<a class="hero-cue" href="#story">Листайте</a>' if lead or p['show_text'] else ''}
</header>
""")
    mark = '<p class="pending">Текст ещё не одобрен о. Андреем</p>' if p["text_pending"] else ""
    out.append(f'<div class="story" id="story" aria-label="Рассказ дня">{mark}\n{story_scenes(p)}\n</div>\n')

    items = [audio[a] for a in p.get("audio", [])]
    if items:
        out.append(f"""<section class="block" aria-labelledby="au-h">
  <div class="block-head"><p class="eyebrow">Vox</p><h2 id="au-h">Аудиорассказ</h2></div>
  <ul class="audio-list">{''.join(audio_item(a, '../') for a in items)}</ul>
</section>
""")
    if p.get("stops"):
        out.append(f"""<section class="block" aria-labelledby="mm-h">
  <div class="block-head"><p class="eyebrow">Locus</p><h2 id="mm-h">Где мы были</h2></div>
  <div class="map map-day" id="day-map" data-date="{p['date']}" role="region" aria-label="Карта дня"></div>
</section>
""")
    # дальше: следующий день крупно, с его кадром; предыдущий — тихой ссылкой
    nxt = ""
    if next_p:
        nph = next_p["show_photos"][0] if next_p["show_photos"] else None
        bg = img_tag(nph, "../", "100vw") if nph else ""
        nxt = (f'<a class="next-day{"" if nph else " no-photo"}" href="{next_p["date"]}.html" rel="next">{bg}'
               f'<span class="nd-text"><span class="eyebrow">Следующий день · Dies {roman(next_p["n"])}</span>'
               f'<span class="nd-title">{e(next_p["title"])}</span><span class="nd-date">{ru_date(next_p["d"])} →</span></span></a>')
    prv = (f'<a class="prev-day" href="{prev_p["date"]}.html" rel="prev">← {ru_date(prev_p["d"])} · {e(prev_p["title"])}</a>'
           if prev_p else "")
    out.append(f'<nav class="daynav" aria-label="Соседние дни">{nxt}{prv}</nav>\n')
    out.append("</main>\n")
    out.append(site_footer(trip))
    out.append(f"""<dialog class="lightbox" id="lightbox" aria-label="Просмотр фотографии">
  <figure><img alt=""><figcaption></figcaption></figure>
  <button class="lb-btn lb-prev" type="button" aria-label="Предыдущее фото">‹</button>
  <button class="lb-btn lb-next" type="button" aria-label="Следующее фото">›</button>
  <button class="lb-btn lb-close" type="button" aria-label="Закрыть">×</button>
  <p class="lb-count" aria-live="polite"></p>
</dialog>
<script src="../{v('data/trip.js')}"></script>
<script defer src="../{v('js/day.js')}"></script>
""")
    if p.get("stops"):
        out.append(f'<script defer src="{LEAFLET_JS}"></script>\n<script defer src="../{v("js/map.js")}"></script>\n')
    if photos:
        out.append(f'<script defer src="../{v("js/gallery.js")}"></script>\n')
    out.append("</body>\n</html>\n")
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="показать неодобренные фото и тексты с пометкой")
    args = ap.parse_args()
    trip, stops, audio, pages = load(args.preview)
    rt = route(pages, stops)
    write_trip_js(trip, stops, pages, rt)
    (ROOT / "index.html").write_text(build_index(trip, stops, audio, pages, args.preview), encoding="utf-8")
    days = ROOT / "days"
    days.mkdir(exist_ok=True)
    for old in days.glob("*.html"):
        old.unlink()
    for i in range(len(pages)):
        (days / f"{pages[i]['date']}.html").write_text(build_day(trip, stops, audio, pages, i, args.preview),
                                                       encoding="utf-8")
    robots = "User-agent: *\nAllow: /\n" if trip["meta"].get("published") else "User-agent: *\nDisallow: /\n"
    (ROOT / "robots.txt").write_text(robots, encoding="utf-8")
    clean_assets()
    mode = "предпросмотр" if args.preview else "публичная"
    print(f"Собрано ({mode}): index.html, {len(pages)} страниц дней, data/trip.js, точек маршрута: {len(rt)}")
    if not trip["meta"].get("published"):
        print("meta.published = false → страницы помечены noindex")
    for w in warnings:
        print("  ·", w)


if __name__ == "__main__":
    main()
