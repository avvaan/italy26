#!/usr/bin/env python3
"""Листы-контакты отобранных фото по дням — для глазной проверки перед экспортом.

    .venv/bin/python tools/contact_sheets.py [--media ../italy-2026-media] [--all-candidates]

Пишет <media>/.work/sheets/<день>.jpg; под каждым кадром — номер строки в catalog.csv,
отметка «Л» (люди) и «Д» (дубль). Оригиналы только читаются.
"""
import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CELL, COLS, LABEL = 300, 5, 26


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", default=str(ROOT.parent / "italy-2026-media"))
    ap.add_argument("--all-candidates", action="store_true", help="лист из candidates.csv, а не только выбранные")
    a = ap.parse_args()
    media = Path(a.media)
    rows = list(csv.DictReader(open(media / "catalog.csv", encoding="utf-8")))
    idx = {r["file"]: i for i, r in enumerate(rows, 2)}
    if a.all_candidates:
        files = {r["file"] for r in csv.DictReader(open(media / "candidates.csv", encoding="utf-8"))}
        pick = [r for r in rows if r["file"] in files]
    else:
        pick = [r for r in rows if r["selected"] == "1"]
    out = media / ".work" / "sheets"
    out.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    by_day = {}
    for r in pick:
        by_day.setdefault(r["day"], []).append(r)
    for day, rs in sorted(by_day.items()):
        rs.sort(key=lambda r: r["taken_at_local"])
        n = len(rs)
        rows_n = (n + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * CELL, rows_n * (CELL + LABEL)), "white")
        d = ImageDraw.Draw(sheet)
        for k, r in enumerate(rs):
            src = Path(r["file"])
            th = media / ".work" / "thumbs" / (src.parent.name + "__" + src.name + ".jpg")
            x, y = (k % COLS) * CELL, (k // COLS) * (CELL + LABEL)
            if th.exists():
                im = Image.open(th)
                im.thumbnail((CELL - 6, CELL - 6))
                sheet.paste(im, (x + (CELL - im.width) // 2, y + (CELL - im.height) // 2))
            tag = f"#{idx[r['file']]} {r['taken_at_local'][11:16]} {r['stop_id']}"
            tag += " Л" if r["has_people"] == "1" else ""
            tag += " Д" if r["is_duplicate_of"] else ""
            d.text((x + 4, y + CELL + 3), tag, fill="black", font=font)
        p = out / f"{day}.jpg"
        sheet.save(p, quality=80)
        print(p, n)


if __name__ == "__main__":
    main()
