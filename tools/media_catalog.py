#!/usr/bin/env python3
"""Каталог фото и видео поездки: дата → день, GPS → место, дубли, оценка, отбор.

    .venv/bin/python tools/media_catalog.py [--media ../italy-2026-media]

Оригиналы в <media>/originals/ ТОЛЬКО читаются (раскладка по дням: «NN · ДД.ММ · …/подпапка/файл»;
старая раскладка по авторам «<автор>/файл» тоже понимается): ничего не удаляется,
не переименовывается и не перезаписывается. Всё производное пишется рядом:
    <media>/catalog.csv      — все файлы (колонки из задания + служебные)
    <media>/candidates.csv   — длинный список кандидатов по дням
    <media>/REPORT.md        — отчёт
    <media>/.work/thumbs/    — уменьшенные копии для анализа

Нужны: exiftool, Pillow, pillow-heif, imagehash; для лиц и тем кадра — .cache/vision
(собирается из tools/vision.swift, только macOS). Без него has_people = 1 у всех фото,
то есть всё уйдёт на просмотр о. Андрею.
"""
import argparse
import csv
import datetime as dt
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageFilter, ImageOps, ImageStat
import imagehash
import pillow_heif

pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parent.parent
ROME = ZoneInfo("Europe/Rome")
PHOTO = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".dng"}
VIDEO = {".mov", ".mp4", ".m4v"}
RADIUS_KM = 15
# Не публикуются никогда: скриншоты (чужие посты, карты с местоположением),
# сканы документов и папка «Без даты» с пересланными файлами.
PRIVATE_NAME = re.compile(r"(\bDL\b|\bgc\b|страница|паспорт|passport|license|boarding|билет|ticket|бронь|booking)", re.I)


FNAME_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})_")


def load_excludes(media):
    """<media>/exclude.csv: file,reason — исключено вручную (номера машин, жильё, посторонние)."""
    f = media / "exclude.csv"
    if not f.exists():
        return {}
    with open(f, encoding="utf-8") as fh:
        return {r["file"]: r["reason"] for r in csv.DictReader(fh)}


def private_reason(rel):
    if rel.suffix.lower() == ".png":
        return "скриншот — не публикуется"
    if PRIVATE_NAME.search(rel.name):
        return "похоже на документ/бронь — не публикуется"
    if rel.parts[0].startswith("99"):
        return "папка «Без даты» (пересланное) — не публикуется"
    return ""
COLUMNS = ["file", "author", "taken_at_local", "day", "stop_id", "lat", "lon", "is_duplicate_of",
           "has_people", "score", "selected"]
EXTRA = ["folder", "folder_day", "kind", "camera", "time_source", "time_fix", "duration_s", "category", "faces", "big_face",
         "sharpness", "exposure", "phash", "note"]
FOOD = ("food", "dish", "meal", "dessert", "pizza", "pasta", "bread", "cake", "wine", "coffee",
        "cheese", "fruit", "vegetable", "drink", "ice_cream", "gelato", "plate", "seafood")
WIDE = ("landscape", "cityscape", "sky", "mountain", "outdoor", "structure", "building", "architecture",
        "panorama", "hill", "lake", "sea", "coast", "field", "street", "town", "ruins", "church", "castle")


FOLDER_DAY = re.compile(r"^\d+\s*·\s*(\d{1,2})\.(\d{1,2})\b")


def folder_day(rel, year):
    m = FOLDER_DAY.match(rel.parts[0])
    if not m:
        return ""
    d, mth = int(m.group(1)), int(m.group(2))
    try:
        return dt.date(year, mth, d).isoformat()
    except ValueError:
        return ""


def load_authors(media):
    """<media>/authors.json: {"модель камеры": "автор"} — чей телефон чей."""
    f = media / "authors.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def zone_at(lat, lon):
    """Часовой пояс места съёмки: время на сайте — местное (Орландо, Лиссабон, Италия)."""
    if lat is None or in_italy(lat, lon):
        return ROME
    if lon < -30:
        return ZoneInfo("America/New_York")
    if -10 <= lon <= -6 and 36 <= lat <= 42.2:
        return ZoneInfo("Europe/Lisbon")
    return ROME


def in_italy(lat, lon):
    return lat is not None and 36 <= lat <= 47.2 and 6.5 <= lon <= 18.6


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def parse_dt(s):
    """'2026:11:10 14:03:22[.123][+01:00|Z]' → datetime (aware, если есть пояс)."""
    if not s or not isinstance(s, str) or s.startswith("0000"):
        return None
    s = s.strip().replace("Z", "+00:00")
    date, _, rest = s.partition(" ")
    if not rest:
        return None
    tz = None
    for sign in "+-":
        if sign in rest[1:]:
            i = rest.rindex(sign)
            rest, tz = rest[:i], rest[i:]
            break
    rest = rest.split(".")[0]
    try:
        d = dt.datetime.strptime(f"{date} {rest}", "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    if tz:
        h, _, m = tz[1:].partition(":")
        off = dt.timedelta(hours=int(h), minutes=int(m or 0)) * (1 if tz[0] == "+" else -1)
        d = d.replace(tzinfo=dt.timezone(off))
    return d


def parse_offset(s):
    if not s or not isinstance(s, str) or len(s) < 3:
        return None
    try:
        h, _, m = s[1:].partition(":")
        off = dt.timedelta(hours=int(h), minutes=int(m or 0)) * (1 if s[0] == "+" else -1)
        return dt.timezone(off)
    except ValueError:
        return None


def local_time(m, lat, lon):
    """Время съёмки по Риму + откуда оно взято + описание поправки (если была)."""
    fix = ""
    # 1) фото: DateTimeOriginal + OffsetTimeOriginal
    t = parse_dt(m.get("DateTimeOriginal") or m.get("SubSecDateTimeOriginal"))
    off = parse_offset(m.get("OffsetTimeOriginal") or m.get("OffsetTime"))
    src = "DateTimeOriginal"
    if t and t.tzinfo is None and off:
        t = t.replace(tzinfo=off)
    # 2) видео Apple: CreationDate с поясом; иначе QuickTime CreateDate в UTC
    if not t:
        t, src = parse_dt(m.get("CreationDate")), "CreationDate"
    if not t:
        t, src = parse_dt(m.get("CreateDate")), "CreateDate"
        if t and t.tzinfo is None and m.get("_video"):
            t = t.replace(tzinfo=dt.timezone.utc)
    if not t:
        return None, "", ""
    if t.tzinfo is None:
        # пояс неизвестен: считаем, что камера шла по местному времени
        if in_italy(lat, lon) or lat is None:
            t = t.replace(tzinfo=ROME)
            src += " (без пояса, принято Europe/Rome)"
        return t, src, fix
    offh = t.utcoffset().total_seconds() / 3600
    if in_italy(lat, lon) and -7 <= offh <= -4:
        fix = f"смещение {offh:+.0f} ч (время Флориды) при GPS в Италии → пересчитано в Europe/Rome"
    elif in_italy(lat, lon) and offh not in (1, 2):
        fix = f"смещение {offh:+.1f} ч при GPS в Италии → пересчитано в Europe/Rome"
    return t.astimezone(zone_at(lat, lon)), src, fix


def exif(paths):
    tags = ["-DateTimeOriginal", "-SubSecDateTimeOriginal", "-OffsetTimeOriginal", "-OffsetTime",
            "-CreationDate", "-CreateDate", "-GPSLatitude", "-GPSLongitude", "-Make", "-Model",
            "-Duration", "-ImageWidth", "-ImageHeight", "-MIMEType"]
    out = []
    for i in range(0, len(paths), 400):
        r = subprocess.run(["exiftool", "-j", "-n", "-api", "QuickTimeUTC", *tags, *map(str, paths[i:i + 400])],
                           capture_output=True, text=True)
        if r.stdout.strip():
            out += json.loads(r.stdout)
    return {Path(x["SourceFile"]).resolve(): x for x in out}


def thumb(src, work):
    """Уменьшенная копия 768 px для анализа (оригинал только читается)."""
    dst = work / "thumbs" / (src.parent.name + "__" + src.name + ".jpg")
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((768, 768))
            im.save(dst, quality=85)
    return dst


def quality(path):
    with Image.open(path) as im:
        g = im.convert("L")
        sharp = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]
        hist = g.histogram()
        n = sum(hist)
        clipped = (sum(hist[:6]) + sum(hist[250:])) / n
        mean = ImageStat.Stat(g).mean[0]
        # экспозиция 0..1: середина гистограммы хорошо, пересвет/провал плохо
        expo = max(0.0, 1 - abs(mean - 120) / 120) * (1 - min(clipped * 3, 0.9))
        return sharp, expo, imagehash.phash(im)


def run_vision(thumbs):
    exe = ROOT / ".cache" / "vision"
    if not exe.exists():
        src = ROOT / "tools" / "vision.swift"
        try:
            subprocess.run(["swiftc", "-O", str(src), "-o", str(exe)], check=True, capture_output=True)
        except Exception:
            return None
    r = subprocess.run([str(exe)], input="\n".join(map(str, thumbs)), capture_output=True, text=True)
    res = {}
    for line in r.stdout.splitlines():
        try:
            x = json.loads(line)
            res[Path(x["path"])] = x
        except (ValueError, KeyError):
            pass
    return res


def category(v):
    if not v:
        return ""
    labels = " ".join(v.get("labels", [])).lower()
    if v.get("faces", 0) or v.get("humans", 0):
        return "люди"
    if "document" in labels or "printed_page" in labels:
        return "текст"   # меню, таблички, листовки — в галерею только если больше нечего
    if any(w in labels for w in FOOD):
        return "еда"
    if any(w in labels for w in WIDE):
        return "общий план"
    return "детали"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", default=str(ROOT.parent / "italy-2026-media"))
    ap.add_argument("--videos-from", help="папка-источник, откуда читать видео без копирования")
    ap.add_argument("--min", type=int, default=8)
    ap.add_argument("--max", type=int, default=15)
    args = ap.parse_args()
    media = Path(args.media).resolve()
    orig = media / "originals"
    work = media / ".work"
    if not orig.is_dir():
        sys.exit(f"Нет папки с оригиналами: {orig}")

    trip = json.loads((ROOT / "data" / "trip.json").read_text(encoding="utf-8"))
    days = {p["date"] for p in trip["pages"]}
    year = int(trip["meta"]["date_from"][:4])
    authors = load_authors(media)
    excludes = load_excludes(media)
    stops = [s for s in trip["stops"]]

    files = sorted(p for p in orig.rglob("*") if p.is_file() and p.suffix.lower() in PHOTO | VIDEO
                   and not p.name.startswith("."))
    if args.videos_from:
        # видео не копируем (место на диске): метаданные читаем прямо из источника, путь — как в originals
        vroot = Path(args.videos_from)
        files += sorted(p for p in vroot.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO
                        and not p.name.startswith(".") and not p.relative_to(vroot).parts[0].startswith("98"))
    skipped = sorted(p for p in orig.rglob("*") if p.is_file() and p.suffix.lower() not in PHOTO | VIDEO
                     and not p.name.startswith("."))
    print(f"Файлов: {len(files)} (пропущено других: {len(skipped)}). Читаю метаданные…")
    meta = exif(files)

    rows = []
    for f in files:
        m = dict(meta.get(f.resolve(), {}))
        kind = "video" if f.suffix.lower() in VIDEO else "photo"
        m["_video"] = kind == "video"
        lat, lon = m.get("GPSLatitude"), m.get("GPSLongitude")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or (lat == 0 and lon == 0):
            lat = lon = None
        t, tsrc, fix = local_time(m, lat, lon)
        if not t:
            mt = FNAME_TIME.match(f.name)
            if mt:
                t = dt.datetime(*map(int, mt.groups()), tzinfo=ROME)
                tsrc = "имя файла (принято Europe/Rome)"
        rel = f.relative_to(orig) if f.is_relative_to(orig) else f.relative_to(Path(args.videos_from))
        fday = folder_day(rel, year)
        day = t.date().isoformat() if t and t.date().isoformat() in days else ""
        note = []
        if t and not day:
            note.append("дата вне поездки")
        priv = private_reason(rel) or (excludes.get(str(rel)) and f"исключено вручную: {excludes[str(rel)]}")
        if priv:
            note.append(priv)
        if not t and fday in days:
            day = fday
            note.append("дата по папке")
        elif t and fday and day and fday != day:
            note.append(f"папка говорит {fday}")
        stop_id = ""
        if lat is not None:
            best = min(stops, key=lambda s: km((lat, lon), (s["lat"], s["lon"])))
            stop_id = best["id"] if km((lat, lon), (best["lat"], best["lon"])) <= RADIUS_KM else "в дороге"
        camera = " ".join(x for x in (m.get("Make"), m.get("Model")) if x)
        if fday or rel.parts[0][:2].isdigit():
            author = authors.get(camera) or authors.get(m.get("Model") or "") or "?"
        else:
            author = rel.parts[0]   # старая раскладка: папка = автор
        rows.append({
            "file": str(rel), "author": author, "folder": "/".join(rel.parts[1:-1]), "folder_day": fday,
            "taken_at_local": t.strftime("%Y-%m-%d %H:%M:%S") if t else "", "day": day,
            "stop_id": stop_id, "lat": f"{lat:.5f}" if lat is not None else "",
            "lon": f"{lon:.5f}" if lon is not None else "", "is_duplicate_of": "", "has_people": "",
            "score": "", "selected": "", "kind": kind,
            "camera": camera,
            "time_source": tsrc, "time_fix": fix,
            "duration_s": f"{m['Duration']:.1f}" if isinstance(m.get("Duration"), (int, float)) else "",
            "category": "", "faces": "", "big_face": "", "sharpness": "", "exposure": "", "phash": "",
            "note": "; ".join(note), "_path": f, "_t": t, "_private": bool(priv),
        })

    photos = [r for r in rows if r["kind"] == "photo"]
    print(f"Анализирую {len(photos)} фото…")
    thumbs = {}
    for i, r in enumerate(photos, 1):
        try:
            th = thumb(r["_path"], work)
            sharp, expo, ph = quality(th)
            thumbs[r["file"]] = th
            r.update(sharpness=f"{sharp:.0f}", exposure=f"{expo:.2f}", phash=str(ph), _ph=ph,
                     _sharp=sharp, _expo=expo)
        except Exception as ex:
            r["note"] = (r["note"] + "; " if r["note"] else "") + f"не открылось: {ex}"
        if i % 200 == 0:
            print(f"  {i}/{len(photos)}")

    vis = run_vision(list(thumbs.values()))
    for r in photos:
        th = thumbs.get(r["file"])
        v = vis.get(th) if (vis is not None and th) else None
        if v and "error" not in v:
            r["faces"], r["big_face"] = v.get("faces", 0), int(bool(v.get("big_face")))
            r["has_people"] = int(v.get("faces", 0) > 0 or v.get("humans", 0) > 0)
            r["category"] = category(v)
        else:
            r["has_people"] = 1  # не смогли проверить → считаем, что люди есть (на одобрение)

    # оценка 0..100 внутри дня: резкость (по рангу) + экспозиция
    by_day = defaultdict(list)
    for r in photos:
        if "_ph" in r:
            by_day[r["day"]].append(r)
    for group in by_day.values():
        order = sorted(group, key=lambda r: r["_sharp"])
        for rank, r in enumerate(order):
            sharp_rank = rank / max(len(order) - 1, 1)
            r["_score"] = 100 * (0.6 * sharp_rank + 0.4 * r["_expo"])
            r["score"] = f"{r['_score']:.0f}"

    # дубли: почти одинаковый phash в пределах дня; серии (≤ 5 с) — с порогом мягче
    for group in by_day.values():
        group.sort(key=lambda r: -r["_score"])
        keepers = []
        for r in group:
            dup = None
            for k in keepers:
                d = r["_ph"] - k["_ph"]
                close = r["_t"] and k["_t"] and abs((r["_t"] - k["_t"]).total_seconds()) <= 5
                if d <= 8 or (close and d <= 14):
                    dup = k
                    break
            if dup:
                r["is_duplicate_of"] = dup["file"]
            else:
                keepers.append(r)

    # отбор: лучшие недубли, с разнообразием тем и разносом по времени
    candidates = []
    for day, group in by_day.items():
        if not day:
            continue
        pool = sorted((r for r in group if not r["is_duplicate_of"] and not r["_private"]), key=lambda r: -r["_score"])
        want = min(args.max, max(args.min, len(pool) // 6))
        picked, cats = [], Counter()
        while pool and len(picked) < want:
            def gain(r):
                g = r["_score"] - 12 * cats[r["category"]]
                if "чат" in r["file"] or not r["camera"]:
                    g -= 25   # пересланная копия: хуже качеством, часто меню/витрины
                if r["category"] == "текст":
                    g -= 30
                if r.get("big_face") == 1 and r["has_people"]:
                    g -= 5
                near = [p for p in picked if r["_t"] and p["_t"] and abs((r["_t"] - p["_t"]).total_seconds()) < 120]
                return g - 10 * len(near)
            best = max(pool, key=gain)
            pool.remove(best)
            picked.append(best)
            cats[best["category"]] += 1
        for r in group:
            r["selected"] = 1 if r in picked else 0
        for r in sorted((r for r in group if not r["is_duplicate_of"] and not r["_private"]),
                        key=lambda r: -r["_score"])[:60]:
            candidates.append(r)
    for r in rows:
        if r["kind"] == "video":
            r["selected"] = ""
        elif r["selected"] == "":
            r["selected"] = 0

    media.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["taken_at_local"] or "9999", r["file"]))
    with open(media / "catalog.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS + EXTRA, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(media / "candidates.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["day", "file", "author", "score", "category", "has_people", "selected"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(candidates, key=lambda r: (r["day"], -r["_score"])))
    report(media, rows, skipped, trip)
    print(f"Готово: {media / 'catalog.csv'}, {media / 'candidates.csv'}, {media / 'REPORT.md'}")


def report(media, rows, skipped, trip):
    L = ["# Фото и видео поездки: отчёт", "",
         f"Собрано {dt.datetime.now(ROME):%d.%m.%Y %H:%M}. Оригиналы не изменялись.", "",
         "## Сколько файлов", "", "| Автор | Фото | Видео | Без даты | Без GPS | Вне дат поездки |",
         "|---|---:|---:|---:|---:|---:|"]
    for a in sorted({r["author"] for r in rows}):
        rs = [r for r in rows if r["author"] == a]
        L.append(f"| {a} | {sum(r['kind'] == 'photo' for r in rs)} | {sum(r['kind'] == 'video' for r in rs)} | "
                 f"{sum(not r['taken_at_local'] for r in rs)} | {sum(not r['lat'] for r in rs)} | "
                 f"{sum(bool(r['taken_at_local']) and not r['day'] for r in rs)} |")
    if skipped:
        L += ["", f"Пропущено файлов других типов: {len(skipped)} (" +
              ", ".join(sorted({p.suffix.lower() or 'без расширения' for p in skipped})) + ")."]
    unknown = Counter(r["camera"] or "камера не указана" for r in rows if r["author"] == "?")
    if unknown:
        L += ["", "## Чьи это камеры?", "",
              "Фото разложены по дням, а не по людям, поэтому автор определяется по модели камеры. "
              "Впишите соответствие в `authors.json` рядом с каталогом (например `{\"Apple iPhone 15 Pro\": \"Андрей\"}`) "
              "и запустите каталог снова.", ""]
        L += [f"- {cam}: {n}" for cam, n in unknown.most_common()]
    mism = [r for r in rows if "папка говорит" in r["note"]]
    if mism:
        L += ["", f"Дата съёмки не совпадает с папкой дня у {len(mism)} файлов (на сайте — по дате съёмки):", ""]
        for (fd, d), n in Counter((r["folder_day"], r["day"]) for r in mism).most_common(20):
            L.append(f"- папка {fd}, снято {d}: {n}")
    byfolder = [r for r in rows if "дата по папке" in r["note"]]
    if byfolder:
        L += ["", f"Без даты в файле, день взят из названия папки: {len(byfolder)}."]
    fixes = [r for r in rows if r["time_fix"]]
    L += ["", "## Поправки времени", ""]
    if fixes:
        for (a, cam, fx), n in Counter((r["author"], r["camera"], r["time_fix"]) for r in fixes).most_common():
            L.append(f"- {a}, {cam or 'камера не указана'}: {n} файлов — {fx}")
    else:
        L.append("Не понадобились.")
    guessed = [r for r in rows if "без пояса" in r["time_source"]]
    if guessed:
        L.append(f"- У {len(guessed)} файлов нет часового пояса; принято, что камера шла по римскому времени.")
    noplace = [r for r in rows if r["taken_at_local"] and not r["day"]]
    if noplace:
        L += ["", "Файлы с датой вне 29.10–14.11 (проверьте часы камеры):", ""]
        L += [f"- {r['file']} — {r['taken_at_local']}" for r in noplace[:40]]
        if len(noplace) > 40:
            L.append(f"- … и ещё {len(noplace) - 40}")
    priv = [r for r in rows if r.get("_private")]
    L += ["", "## Не публикуются никогда", "",
          f"Исключено из отбора: {len(priv)} (скриншоты, сканы документов, папка «Без даты»). "
          "В каталоге они остаются, на сайт не попадут.", ""]
    for why, n in Counter(r["note"].split("; ")[-1] for r in priv).most_common():
        L.append(f"- {why}: {n}")
    dups = [r for r in rows if r["is_duplicate_of"]]
    cross = [r for r in dups if r["author"] != next((x["author"] for x in rows if x["file"] == r["is_duplicate_of"]), r["author"])]
    L += ["", "## Дубли", "", f"Помечено дублями: {len(dups)} (из них снято разными людьми: {len(cross)}). "
          "Ничего не удалено, в catalog.csv у дубля указан лучший кадр."]
    L += ["", "## Отбор по дням", "", "| День | Фото | Не дубли | Выбрано | С людьми среди выбранных | Темы выбранных |",
          "|---|---:|---:|---:|---:|---|"]
    for p in trip["pages"]:
        rs = [r for r in rows if r["day"] == p["date"] and r["kind"] == "photo"]
        sel = [r for r in rs if r["selected"] == 1]
        cats = ", ".join(f"{c or '?'} {n}" for c, n in Counter(r["category"] for r in sel).most_common())
        L.append(f"| {p['date']} | {len(rs)} | {sum(not r['is_duplicate_of'] for r in rs)} | {len(sel)} | "
                 f"{sum(r['has_people'] == 1 for r in sel)} | {cats} |")
    vids = [r for r in rows if r["kind"] == "video"]
    L += ["", "## Видео (только каталог, на сайт не идут)", "",
          f"Всего {len(vids)}, общая длительность {sum(float(r['duration_s'] or 0) for r in vids) / 60:.0f} мин."]
    L += ["", "## На одобрение о. Андрею", "",
          f"- Выбранных фото с людьми: {sum(r['selected'] == 1 and r['has_people'] == 1 for r in rows)}. "
          "Без одобрения они не публикуются.",
          f"- Крупные лица среди выбранных: {sum(r['selected'] == 1 and str(r['big_face']) == '1' for r in rows)} — "
          "проверьте, нет ли посторонних.",
          "- Проверьте вручную: номера машин, билеты, документы, вывески жилья в кадре."]
    (media / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
