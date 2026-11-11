#!/usr/bin/env python3
"""Экспорт выбранных фото на сайт: photos/<день>/<n>-{400,900,1800}.webp, без метаданных.

    .venv/bin/python tools/export_photos.py [--media ../italy-2026-media] [--day 2026-11-10]

Берёт строки catalog.csv с selected = 1 (порядок — по времени съёмки, первым идёт кадр
с колонкой cover = 1, если она есть, иначе лучший по score). Переводит цвет в sRGB,
поворачивает по EXIF, сохраняет WebP без EXIF/XMP/ICC и затем ещё раз чистит
всё через exiftool -all=. Оригиналы только читаются.

В trip.json у страницы обновляется photos: [{src, alt, caption, author, w, h, people, approved}].
Уже написанные alt/caption/approved сохраняются для тех же кадров. Фото с людьми
приходят с approved = false — их одобряет о. Андрей. Соответствие «кадр сайта ↔ оригинал»
хранится вне сайта, в <media>/export-map.csv.
"""
import argparse
import csv
import io
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageCms, ImageOps
import pillow_heif

pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parent.parent
SIZES = (400, 900, 1800)
SRGB = ImageCms.createProfile("sRGB")


def to_srgb(im):
    icc = im.info.get("icc_profile")
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            im = ImageCms.profileToProfile(im, src, SRGB, outputMode="RGB")
        except Exception:
            im = im.convert("RGB")
    return im.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", default=str(ROOT.parent / "italy-2026-media"))
    ap.add_argument("--day", help="только этот день (YYYY-MM-DD)")
    ap.add_argument("--replace-all", action="store_true",
                    help="на сайте только эти фото: у дней без выбранных фото галерея очищается")
    args = ap.parse_args()
    media = Path(args.media).resolve()
    rows = list(csv.DictReader(open(media / "catalog.csv", encoding="utf-8")))
    picked = defaultdict(list)
    for r in rows:
        if r.get("selected") == "1" and r.get("day") and (not args.day or r["day"] == args.day):
            picked[r["day"]].append(r)
    if not picked:
        sys.exit("В catalog.csv нет выбранных фото (selected = 1)")

    trip_path = ROOT / "data" / "trip.json"
    trip = json.loads(trip_path.read_text(encoding="utf-8"))
    pages = {p["date"]: p for p in trip["pages"]}
    map_path = media / "export-map.csv"
    old_map = {}
    if map_path.exists():
        for m in csv.DictReader(open(map_path, encoding="utf-8")):
            old_map[(m["day"], m["file"])] = m["src"]
    new_map = [m for m in csv.DictReader(open(map_path, encoding="utf-8"))] if map_path.exists() else []
    new_map = [m for m in new_map if m["day"] not in picked]

    if args.replace_all:
        for day, page in pages.items():
            if day not in picked and page.get("photos"):
                for old in (ROOT / "photos" / day).glob("*.webp"):
                    old.unlink()
                page["photos"] = []
                print(f"{day}: фото убраны")

    for day, rs in sorted(picked.items()):
        page = pages[day]
        prev = {ph["src"]: ph for ph in page.get("photos", [])}
        lead = next((r for r in rs if r.get("cover") == "1"), max(rs, key=lambda r: float(r["score"] or 0)))
        rest = sorted((r for r in rs if r is not lead), key=lambda r: r["taken_at_local"])
        out_dir = ROOT / "photos" / day
        out_dir.mkdir(parents=True, exist_ok=True)
        for old in out_dir.glob("*.webp"):
            old.unlink()
        photos = []
        for n, r in enumerate([lead] + rest, 1):
            src_file = media / "originals" / r["file"]
            with Image.open(src_file) as im:
                im = to_srgb(im)
            w0, h0 = im.size
            for size in SIZES:
                k = min(1, size / max(w0, h0))
                out = im.resize((round(w0 * k), round(h0 * k)), Image.LANCZOS) if k < 1 else im
                q = (86 if size == 1800 else 84) if n == 1 else (72 if size == 1800 else 70)
                out.save(out_dir / f"{n}-{size}.webp", "WEBP", quality=q, method=6)  # без exif/icc/xmp
            k = min(1, 1800 / max(w0, h0))
            src = f"photos/{day}/{n}"
            before = prev.get(old_map.get((day, r["file"]), ""), {})
            people = r.get("has_people") == "1"
            photos.append({
                "src": src,
                "alt": before.get("alt", ""),
                "caption": before.get("caption", ""),
                "author": "" if r["author"] in ("?", "") else r["author"],
                "w": round(w0 * k), "h": round(h0 * k),
                "people": people,
                "approved": before.get("approved", not people),
            })
            new_map.append({"day": day, "src": src, "file": r["file"]})
        page["photos"] = photos
        print(f"{day}: {len(photos)} фото")

    # метаданные: вычищаем всё ещё раз и проверяем, что GPS нет
    subprocess.run(["exiftool", "-q", "-all=", "-overwrite_original", "-r", "-ext", "webp", str(ROOT / "photos")],
                   check=True)
    gps = subprocess.run(["exiftool", "-q", "-gps:all", "-r", str(ROOT / "photos")], capture_output=True, text=True)
    if gps.stdout.strip():
        sys.exit("ВНИМАНИЕ: в photos/ остались GPS-данные:\n" + gps.stdout)

    trip_path.write_text(json.dumps(trip, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with open(map_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["day", "src", "file"])
        w.writeheader()
        w.writerows(sorted(new_map, key=lambda m: (m["day"], m["src"])))
    missing = sum(1 for p in trip["pages"] for ph in p.get("photos", []) if not ph["alt"])
    print(f"trip.json обновлён. Без alt: {missing} — их нужно написать по-русски до публикации.")


if __name__ == "__main__":
    main()
