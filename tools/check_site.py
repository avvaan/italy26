#!/usr/bin/env python3
"""Проверка перед публикацией: ссылки, файлы, метаданные фото, вес главной.

    python3 tools/check_site.py

Ничего не меняет. Код выхода 1, если что-то сломано.
"""
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parent.parent
LIMIT_KB = 300


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for k in ("href", "src", "data-fallback"):
            if a.get(k):
                self.refs.append(a[k])
        for k in ("srcset", "data-srcset"):
            if a.get(k):
                self.refs += [part.strip().split(" ")[0] for part in a[k].split(",")]


def main():
    bad = []
    pages = [ROOT / "index.html"] + sorted((ROOT / "days").glob("*.html"))
    if (ROOT / "en" / "index.html").exists():
        pages += [ROOT / "en" / "index.html"] + sorted((ROOT / "en" / "days").glob("*.html"))
    ids = {}
    parsed = {}
    for p in pages:
        r = Refs()
        r.feed(p.read_text(encoding="utf-8"))
        parsed[p], ids[p.resolve()] = r, r.ids
    for p, r in parsed.items():
        for ref in r.refs:
            u = urlsplit(ref)
            if u.scheme in ("http", "https", "mailto") or ref.startswith("//"):
                continue
            target = (p.parent / unquote(u.path)).resolve() if u.path else p.resolve()
            if u.path and not target.exists():
                bad.append(f"{p.relative_to(ROOT)}: нет файла {ref}")
            elif u.fragment and target.suffix == ".html" and u.fragment not in ids.get(target, set()):
                bad.append(f"{p.relative_to(ROOT)}: нет якоря {ref}")
    print(f"Страниц: {len(pages)}, ссылок проверено: {sum(len(r.refs) for r in parsed.values())}")

    photos = ROOT / "photos"
    if any(photos.rglob("*.webp")):
        out = subprocess.run(["exiftool", "-q", "-gps:all", "-r", str(photos)], capture_output=True, text=True).stdout
        if out.strip():
            bad.append("в photos/ найдены GPS-данные:\n" + out)
        out = subprocess.run(["exiftool", "-q", "-exif:all", "-xmp:all", "-r", str(photos)],
                             capture_output=True, text=True).stdout
        if out.strip():
            bad.append("в photos/ найдены EXIF/XMP:\n" + out[:2000])
        print("Фото: метаданные проверены (exiftool -gps:all -r photos/ — пусто)" if not out.strip() else "")

    local = ["index.html", "css/site.css", "js/map.js", "data/trip.js"]
    kb = sum((ROOT / f).stat().st_size for f in local) / 1024
    print(f"Главная, свои файлы без фото: {kb:.0f} КБ (+ Leaflet ≈ 45 КБ gzip и шрифты с Google Fonts)")
    if kb > LIMIT_KB:
        bad.append(f"главная тяжелее {LIMIT_KB} КБ")

    if bad:
        print("\nПроблемы:")
        for b in bad:
            print("  ✗", b)
        sys.exit(1)
    print("Всё в порядке.")


if __name__ == "__main__":
    main()
