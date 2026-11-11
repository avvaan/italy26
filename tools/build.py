#!/usr/bin/env python3
"""Собирает сайт из data/trip.json.

    python3 tools/build.py            # публичная сборка: только одобренное
    python3 tools/build.py --preview  # для о. Андрея: всё, неодобренное помечено

Пишет index.html, days/<дата>.html и data/trip.js. Если есть data/trip.en.json (переводы:
pages/photos/stops по ключам), рядом собирается английская версия: en/index.html, en/days/…,
data/trip.en.js. Только стандартная библиотека.
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

TRIP_EN = ROOT / "data" / "trip.en.json"

# Строки интерфейса на двух языках. Русский — основной (корень сайта), английский — в /en/.
STRINGS = {
    "ru": {
        "months": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
                   "августа", "сентября", "октября", "ноября", "декабря"],
        "weekdays": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
        "skip": "К содержанию", "home_aria": "Италия 2026 — на главную", "sections": "Разделы",
        "nav": ["Дни", "Маршрут", "Аудио", "Фильм"],
        "foot": "Карта: подложка © Esri. Фотографии — семейные, без разрешения не копировать.",
        "audio_soon": "Запись появится позже.",
        "index_desc": "Семейная книга о поездке.", "eyebrow_home": "Семейная поездка", "display": "Италия",
        "cue": "Листайте", "route": "Маршрут", "map_aria": "Карта маршрута",
        "map_alt": "Карта маршрута поездки по Италии",
        "legend": ("пройдено", "впереди", "перелёт"), "days_h": "День за днём", "n_photos": "{} фото",
        "audio_h": "Аудиорассказы", "no_day": "Без дня", "film_h": "Фильм", "film_watch": "Смотреть фильм",
        "film_soon": "Скоро", "film_note": "Фильм о поездке монтируется отдельно.",
        "photo_by": "фото: {}", "pending": "не одобрено", "what": "Что это?",
        "what_aria": "Что это? Описание фото {}", "no_story": "Рассказ этого дня появится позже.",
        "day_n": "День {}", "day_title": "День {}", "places": "Места", "text_pending": "Текст ещё не одобрен о. Андреем",
        "story_aria": "Рассказ дня", "audio_day": "Аудиорассказ", "where": "Где мы были", "day_map": "Карта дня",
        "next": "Следующий день", "nearby": "Соседние дни", "lb_aria": "Просмотр фотографии",
        "prev_photo": "Предыдущее фото", "next_photo": "Следующее фото", "close": "Закрыть",
        "open_full": "Открыть фото целиком", "lang_name": "Русский",
        "map_attr": "Подложка © Esri", "map_fail": "Карта не загрузилась.",
        "desc_pending": "Описание ещё не одобрено",
    },
    "en": {
        "months": ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"],
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "skip": "Skip to content", "home_aria": "Italy 2026 — home", "sections": "Sections",
        "nav": ["Days", "Route", "Audio", "Film"],
        "foot": "Map: base layer © Esri. Family photographs — please do not copy without permission.",
        "audio_soon": "The recording will appear later.",
        "index_desc": "A family book about the journey.", "eyebrow_home": "A family journey", "display": "Italy",
        "cue": "Scroll", "route": "Route", "map_aria": "Route map",
        "map_alt": "Map of the journey through Italy",
        "legend": ("travelled", "ahead", "flight"), "days_h": "Day by day", "n_photos": "{} photos",
        "audio_h": "Audio stories", "no_day": "Not tied to a day", "film_h": "Film", "film_watch": "Watch the film",
        "film_soon": "Coming soon", "film_note": "The film about the journey is being edited separately.",
        "photo_by": "photo: {}", "pending": "not approved", "what": "What is this?",
        "what_aria": "What is this? Description of photo {}", "no_story": "The story of this day will appear later.",
        "day_n": "Day {}", "day_title": "Day {}", "places": "Places", "text_pending": "Text not yet approved by Fr. Andrey",
        "story_aria": "The story of the day", "audio_day": "Audio story", "where": "Where we were", "day_map": "Map of the day",
        "next": "Next day", "nearby": "Neighbouring days", "lb_aria": "Photo viewer",
        "prev_photo": "Previous photo", "next_photo": "Next photo", "close": "Close",
        "open_full": "Open the full photo", "lang_name": "English",
        "map_attr": "Base layer © Esri", "map_fail": "The map did not load.",
        "desc_pending": "Description not yet approved",
    },
}
LANG = "ru"          # текущий язык сборки
A = ""               # добавка к пути до общих файлов (css, js, photos): "" для русского, "../" для /en/


def S(key):
    return STRINGS[LANG][key]


def other_lang():
    return "en" if LANG == "ru" else "ru"


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
    s = f"{d.day} {S('months')[d.month - 1]}"
    return f"{s} {d.year}" if year else s


def excerpt(text, limit=150):
    if not text:
        return ""
    first = re.split(r"(?<=[.!?…])\s", text[0].strip(), maxsplit=1)[0]
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0] + "…"
    return first


# --------------------------------------------------------------- data model

def load(preview, trip):
    stops = {s["id"]: s for s in trip["stops"]}
    audio = {a["id"]: a for a in trip.get("audio", [])}
    pages = trip["pages"]
    for i, p in enumerate(pages):
        p["n"] = i + 1
        p["d"] = dt.date.fromisoformat(p["date"])
        p["url"] = f"days/{p['date']}.html"
        p["title"] = p.get("title") or S("day_title").format(i + 1)
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
                d_ok = ph.get("description_approved", False)
                desc = ph.get("description", "") if (d_ok or preview) else ""
                shown.append(dict(ph, pending=not ok, show_desc=desc,
                                  desc_pending=bool(ph.get("description")) and not d_ok))
            if not ok:
                warn(f"{p['date']}: фото {ph.get('src')} ждёт одобрения")
        p["show_photos"] = shown
        nd = sum(1 for ph in p.get("photos", []) if ph.get("description") and not ph.get("description_approved"))
        if nd:
            warn(f"{p['date']}: описаний фото ждут одобрения: {nd}")
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
        "ui": {k: S(k) for k in ("photo_by", "desc_pending", "map_attr", "map_fail", "map_alt")},
    }
    js = "window.TRIP=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (ROOT / trip_js()).write_text(js, encoding="utf-8")


def trip_js():
    return "data/trip.js" if LANG == "ru" else f"data/trip.{LANG}.js"


# --------------------------------------------------------------- fragments

FONTS = ("https://fonts.googleapis.com/css2?family=Forum&family=Literata:ital,opsz,wght@"
         "0,7..72,400;0,7..72,600;1,7..72,400&display=swap&subset=cyrillic")
LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"


def alt_links(path):
    """hreflang: та же страница на другом языке. path — от корня языка (index.html, days/…)."""
    up = "../" * path.count("/")
    ru = (up + "../" if LANG == "en" else up) + path
    en = (up if LANG == "en" else up + "en/") + path
    return (f'<link rel="alternate" hreflang="ru" href="{ru}">\n'
            f'<link rel="alternate" hreflang="en" href="{en}">\n')


def lang_switch(path):
    up = "../" * path.count("/")
    href = (up + "../" + path) if LANG == "en" else (up + "en/" + path)
    o = other_lang()
    return (f'<a class="lang-switch" href="{href}" hreflang="{o}" lang="{o}" '
            f'title="{STRINGS[o]["lang_name"]}">{o.upper()}</a>')


def head(trip, title, desc, base, extra="", path="index.html"):
    robots = "" if trip["meta"].get("published") else '<meta name="robots" content="noindex, nofollow">\n'
    return f"""<!doctype html>
<html lang="{LANG}">
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
<link rel="stylesheet" href="{A}{base}{v('css/site.css')}">
{alt_links(path)}{extra}</head>
<body>
<a class="skip" href="#main">{S('skip')}</a>
"""


def site_header(base, path="index.html"):
    nav = list(zip(S("nav"), [f"{base}index.html#days", f"{base}index.html#route",
                              f"{base}index.html#audio", f"{base}index.html#film"]))
    links = "".join(f'<a href="{u}">{t}</a>' for t, u in nav)
    return f"""<header class="site-head">
  <a class="wordmark" href="{base}index.html" aria-label="{S('home_aria')}">Italia<span aria-hidden="true">·</span>MMXXVI</a>
  <nav aria-label="{S('sections')}">{links}{lang_switch(path)}</nav>
</header>
"""


def site_footer(trip):
    y = trip["meta"]["date_from"][:4]
    return f"""<footer class="site-foot">
  <p class="inscr">{e(trip['meta']['subtitle'])}<span aria-hidden="true"> · </span>{y}</p>
  <p class="fine">{S('foot')}</p>
</footer>
"""


def stripe():
    return '<div class="stripe" aria-hidden="true"></div>\n'


def img_tag(ph, base, sizes, cls="", eager=False):
    src = ph["src"]
    base = A + base
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
        return f'<li class="audio-item"><p class="audio-title">{e(a["title"])}</p><p class="muted">{S("audio_soon")}</p></li>'
    dur = f' <span class="muted">· {e(a["duration"])}</span>' if a.get("duration") else ""
    return (f'<li class="audio-item"><p class="audio-title">{e(a["title"])}{dur}</p>'
            f'<audio controls preload="none" src="{A}{base}{e(a["file"])}"></audio></li>')


# --------------------------------------------------------------- pages

def build_index(trip, stops, audio, pages, preview):
    m = trip["meta"]
    d0, d1 = dt.date.fromisoformat(m["date_from"]), dt.date.fromisoformat(m["date_to"])
    dates = f"{ru_date(d0)} — {ru_date(d1, year=True)}"
    out = [head(trip, m["title"], f"{m['subtitle']}: {dates}. {S('index_desc')}", "",
                f'<link rel="stylesheet" href="{LEAFLET_CSS}">\n'), site_header("")]
    out.append('<main id="main">\n')

    # обложка: фото из meta.cover (путь src одобренного фото) или первое одобренное
    cover = None
    allph = [ph for p in pages for ph in p["show_photos"]]
    if m.get("cover"):
        cover = next((ph for ph in allph if ph["src"] == m["cover"]), None)
    cover = cover or (allph[0] if allph else None)
    media = (f'<div class="hero-media">{img_tag(cover, "", "100vw", eager=True)}</div>' if cover else "")
    out.append(f"""<header class="hero hero-home{'' if cover else ' no-photo'}">
  {media}
  <div class="hero-text">
    <p class="eyebrow">{S('eyebrow_home')}</p>
    <h1 class="display">{S('display')}</h1>
    <p class="cover-dates">{e(dates)}</p>
    <p class="cover-who">{e(m['subtitle'])}</p>
  </div>
  <a class="hero-cue" href="#route">{S('cue')}</a>
</header>
""")

    # карта
    lg = S("legend")
    out.append(f"""<section class="block" id="route" aria-labelledby="route-h">
  <div class="block-head"><p class="eyebrow">Iter</p><h2 id="route-h">{S('route')}</h2></div>
  <div class="map map-route" id="route-map" data-fallback="{A}assets/route-map.png" role="region" aria-label="{S('map_aria')}">
    <noscript><img src="{A}assets/route-map.png" alt="{S('map_alt')}"></noscript>
  </div>
  <p class="map-legend"><span class="lg lg-done"></span>{lg[0]} <span class="lg lg-plan"></span>{lg[1]} <span class="lg lg-air"></span>{lg[2]}</p>
</section>
""")

    # лента дней
    cards = []
    for p in pages:
        phs = p["show_photos"]
        date_on = (f'<span class="card-on"><span class="num">{p["d"].day}</span>'
                   f'<span class="mon">{S("months")[p["d"].month - 1]}<br>Dies {roman(p["n"])}</span>'
                   f'{"<span class=card-count>" + S("n_photos").format(len(phs)) + "</span>" if phs else ""}</span>')
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
  <div class="block-head"><p class="eyebrow">Dies</p><h2 id="days-h">{S('days_h')}</h2></div>
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
            groups.append(f'<div class="audio-group"><h3>{S("no_day")}</h3><ul class="audio-list">'
                          f'{"".join(audio_item(a, "") for a in loose)}</ul></div>')
        out.append(f"""<section class="block" id="audio" aria-labelledby="audio-h">
  <div class="block-head"><p class="eyebrow">Vox</p><h2 id="audio-h">{S('audio_h')}</h2></div>
  {''.join(groups)}
</section>
""")

    # фильм
    film = trip.get("film") or {}
    body = (f'<p><a class="chip" href="{e(film["url"])}">{S("film_watch")}</a></p>' if film.get("url")
            else f'<p class="soon">{S("film_soon")}</p><p class="muted">{S("film_note")}</p>')
    out.append(f"""<section class="block" id="film" aria-labelledby="film-h">
  <div class="block-head"><p class="eyebrow">Pictura</p><h2 id="film-h">{S('film_h')}</h2></div>
  <div class="film">{body}</div>
</section>
""")
    out.append("</main>\n")
    out.append(site_footer(trip))
    out.append(f'<script src="{A}{v(trip_js())}"></script>\n<script defer src="{LEAFLET_JS}"></script>\n'
               f'<script defer src="{A}{v("js/map.js")}"></script>\n<script defer src="{A}{v("js/day.js")}"></script>\n</body>\n</html>\n')
    return "".join(out)


def byline(cap, by):
    who = f'<span class="muted">{S("photo_by").format(e(by))}</span>' if by else ""
    return f"{e(cap)} · {who}" if cap and who else (e(cap) or who)


# --------------------------------------------------------------- день: сцены «текст + фото»

def is_tall(ph):
    return (ph.get("h") or 2) > (ph.get("w") or 3) * 1.05


def photo(ph, idx, total, sizes, cls="", eager=False, reveal=True):
    """Фото-ссылка для полноэкранного просмотра; подпись лежит прямо на кадре."""
    cap, by = ph.get("caption") or "", ph.get("author") or ""
    full = ", ".join(f"{A}../{ph['src']}-{s}.webp {s}w" for s in SIZES)
    mark = f'<span class="pending">{S("pending")}</span>' if ph.get("pending") else ""
    label = [f"{idx:02d} / {total:02d}"] + ([e(cap)] if cap else []) + ([S("photo_by").format(e(by))] if by else [])
    shape = " tall" if is_tall(ph) else ""
    rv = " data-reveal" if reveal else ""
    return (f'<figure class="ph {cls}{shape}"{rv}>'
            f'<a href="{A}../{ph["src"]}-1800.webp" data-lb data-srcset="{full}" data-caption="{e(cap)}" data-author="{e(by)}"'
            f'{desc_attr(ph)}>'
            f'{img_tag(ph, "../", sizes, eager=eager)}</a>'
            f'<figcaption class="ph-cap" aria-hidden="true">{" <span>·</span> ".join(label)}{mark}</figcaption>'
            f'{what_btn(ph, idx)}</figure>')


def what_btn(ph, idx):
    if not ph.get("show_desc"):
        return ""
    return (f'<button class="ph-what" type="button" aria-haspopup="dialog" '
            f'aria-label="{S("what_aria").format(idx)}">{S("what")}</button>')


def desc_attr(ph):
    d = ph.get("show_desc") or ""
    if not d:
        return ""
    return f' data-desc="{e(d)}"' + (' data-desc-pending' if ph.get("desc_pending") else "")


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
            return f'<section class="scene scene-text"><div class="sc-text"><p class="muted">{S("no_story")}</p></div></section>'
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
    path = f"days/{p['date']}.html"
    out = [head(trip, f"{p['title']} — {ru_date(d)} · {trip['meta']['title']}", desc, "../",
                f'<link rel="stylesheet" href="{LEAFLET_CSS}">\n', path=path), site_header("../", path)]
    out.append('<div class="progress" aria-hidden="true"><span></span></div>\n<main id="main" class="day">\n')
    place_html = "".join(f'<li>{e(stops[s]["name"])}</li>' for s in dict.fromkeys(p.get("stops", [])))
    photos = p["show_photos"]
    lead = photos[0] if photos else None
    count = f'<p class="hero-count">{S("n_photos").format(len(photos))}</p>' if photos else ""
    media = (f'<div class="hero-media">{photo(lead, 1, len(photos), "100vw", "ph-hero", eager=True, reveal=False)}</div>'
             if lead else "")
    out.append(f"""<header class="hero{'' if lead else ' no-photo'}">
  {media}
  <div class="hero-text">
    <p class="eyebrow">{S('day_n').format(p['n'])} <span aria-hidden="true">·</span> Dies {roman(p['n'])}</p>
    <p class="hero-date"><span class="num">{d.day}</span><span class="mon">{S('months')[d.month - 1]} {d.year}<br><i>{S('weekdays')[d.weekday()]}</i></span></p>
    <h1>{e(p['title'])}</h1>
    {f'<ul class="places" aria-label="{S("places")}">{place_html}</ul>' if place_html else ''}
  </div>
  {count}
  {f'<a class="hero-cue" href="#story">{S("cue")}</a>' if lead or p['show_text'] else ''}
</header>
""")
    mark = f'<p class="pending">{S("text_pending")}</p>' if p["text_pending"] else ""
    out.append(f'<div class="story" id="story" aria-label="{S("story_aria")}">{mark}\n{story_scenes(p)}\n</div>\n')

    items = [audio[a] for a in p.get("audio", [])]
    if items:
        out.append(f"""<section class="block" aria-labelledby="au-h">
  <div class="block-head"><p class="eyebrow">Vox</p><h2 id="au-h">{S('audio_day')}</h2></div>
  <ul class="audio-list">{''.join(audio_item(a, '../') for a in items)}</ul>
</section>
""")
    if p.get("stops"):
        out.append(f"""<section class="block" aria-labelledby="mm-h">
  <div class="block-head"><p class="eyebrow">Locus</p><h2 id="mm-h">{S('where')}</h2></div>
  <div class="map map-day" id="day-map" data-date="{p['date']}" role="region" aria-label="{S('day_map')}"></div>
</section>
""")
    # дальше: следующий день крупно, с его кадром; предыдущий — тихой ссылкой
    nxt = ""
    if next_p:
        nph = next_p["show_photos"][0] if next_p["show_photos"] else None
        bg = img_tag(nph, "../", "100vw") if nph else ""
        nxt = (f'<a class="next-day{"" if nph else " no-photo"}" href="{next_p["date"]}.html" rel="next">{bg}'
               f'<span class="nd-text"><span class="eyebrow">{S("next")} · Dies {roman(next_p["n"])}</span>'
               f'<span class="nd-title">{e(next_p["title"])}</span><span class="nd-date">{ru_date(next_p["d"])} →</span></span></a>')
    prv = (f'<a class="prev-day" href="{prev_p["date"]}.html" rel="prev">← {ru_date(prev_p["d"])} · {e(prev_p["title"])}</a>'
           if prev_p else "")
    nearby = S("nearby")
    out.append(f'<nav class="daynav" aria-label="{nearby}">{nxt}{prv}</nav>\n')
    out.append("</main>\n")
    out.append(site_footer(trip))
    out.append(f"""<dialog class="lightbox" id="lightbox" aria-label="{S('lb_aria')}">
  <figure><img alt=""><figcaption></figcaption></figure>
  <div class="lb-desc" hidden></div>
  <button class="lb-btn lb-prev" type="button" aria-label="{S('prev_photo')}">‹</button>
  <button class="lb-btn lb-next" type="button" aria-label="{S('next_photo')}">›</button>
  <button class="lb-btn lb-close" type="button" aria-label="{S('close')}">×</button>
  <p class="lb-count" aria-live="polite"></p>
</dialog>
<dialog class="about" id="about" aria-labelledby="about-title">
  <div class="about-in">
    <button class="about-close" type="button" aria-label="{S('close')}">×</button>
    <p class="eyebrow">{S('what')}</p>
    <img class="about-thumb" alt="">
    <h2 class="about-title" id="about-title"></h2>
    <div class="about-text"></div>
    <button class="about-open" type="button">{S('open_full')}</button>
  </div>
</dialog>
<script src="{A}../{v(trip_js())}"></script>
<script defer src="{A}../{v('js/day.js')}"></script>
""")
    if p.get("stops"):
        out.append(f'<script defer src="{LEAFLET_JS}"></script>\n<script defer src="{A}../{v("js/map.js")}"></script>\n')
    if photos:
        out.append(f'<script defer src="{A}../{v("js/gallery.js")}"></script>\n')
        if any(ph.get("show_desc") for ph in photos):
            out.append(f'<script defer src="{A}../{v("js/about.js")}"></script>\n')
    out.append("</body>\n</html>\n")
    return "".join(out)


def apply_en(trip, en):
    """Английская версия: русские данные + переводы из data/trip.en.json.
    Чего нет в переводе, того нет и на английской странице (текст, описание); alt — по-русски."""
    import copy
    t = copy.deepcopy(trip)
    t["meta"].update(en.get("meta", {}))
    for s in t["stops"]:
        s.update(en.get("stops", {}).get(s["id"], {}))
    for a in t.get("audio", []):
        if a["id"] in en.get("audio", {}):
            a["title"] = en["audio"][a["id"]]
    miss_text = miss_desc = 0
    for p in t["pages"]:
        tr = en.get("pages", {}).get(p["date"], {})
        if tr.get("title"):
            p["title"] = tr["title"]
        if p.get("text"):
            if tr.get("text") and len(tr["text"]) == len(p["text"]):
                p["text"] = tr["text"]
            else:
                p["text"], miss_text = [], miss_text + 1
        for ph in p.get("photos", []):
            tp = en.get("photos", {}).get(ph["src"], {})
            for k in ("alt", "caption"):
                if tp.get(k):
                    ph[k] = tp[k]
            if ph.get("description"):
                if tp.get("description"):
                    ph["description"] = tp["description"]
                else:
                    ph["description"], miss_desc = "", miss_desc + 1
            if ph.get("author"):
                ph["author"] = en.get("authors", {}).get(ph["author"], ph["author"])
    if miss_text or miss_desc:
        warn(f"EN: без перевода текстов дней: {miss_text}, описаний фото: {miss_desc}")
    return t


def build_lang(trip_data, preview, lang):
    global LANG, A
    LANG, A = lang, ("" if lang == "ru" else "../")
    out_root = ROOT if lang == "ru" else ROOT / lang
    out_root.mkdir(exist_ok=True)
    trip, stops, audio, pages = load(preview, trip_data)
    rt = route(pages, stops)
    write_trip_js(trip, stops, pages, rt)
    (out_root / "index.html").write_text(build_index(trip, stops, audio, pages, preview), encoding="utf-8")
    days = out_root / "days"
    days.mkdir(exist_ok=True)
    for old in days.glob("*.html"):
        old.unlink()
    for i in range(len(pages)):
        (days / f"{pages[i]['date']}.html").write_text(build_day(trip, stops, audio, pages, i, preview),
                                                       encoding="utf-8")
    return trip, pages, rt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="показать неодобренные фото и тексты с пометкой")
    args = ap.parse_args()
    base = json.loads(TRIP.read_text(encoding="utf-8"))
    trip, pages, rt = build_lang(json.loads(json.dumps(base)), args.preview, "ru")
    if TRIP_EN.exists():
        en = json.loads(TRIP_EN.read_text(encoding="utf-8"))
        build_lang(apply_en(base, en), args.preview, "en")
    robots = "User-agent: *\nAllow: /\n" if trip["meta"].get("published") else "User-agent: *\nDisallow: /\n"
    (ROOT / "robots.txt").write_text(robots, encoding="utf-8")
    clean_assets()
    mode = "предпросмотр" if args.preview else "публичная"
    print(f"Собрано ({mode}): index.html, {len(pages)} страниц дней, data/trip.js, точек маршрута: {len(rt)}"
          + (" + английская версия в en/" if TRIP_EN.exists() else ""))
    if not trip["meta"].get("published"):
        print("meta.published = false → страницы помечены noindex")
    for w in dict.fromkeys(warnings):
        print("  ·", w)


if __name__ == "__main__":
    main()
