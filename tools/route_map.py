#!/usr/bin/env python3
"""Рисует статичную карту маршрута assets/route-map.png (запасной вариант без JS).

    .venv/bin/python tools/route_map.py

Подложка — тайлы Esri World Topo (кэш в .cache/tiles), маршрут и точки — из data/trip.json.
Без сети рисует маршрут на ровном «каменном» фоне. Нужен Pillow.
"""
import io
import json
import math
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "route-map.png"
CACHE = ROOT / ".cache" / "tiles"
TILE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
W, H, PAD = 1600, 1200, 90
STONE, INK, INK2, TERRA, PAPER = (239, 231, 218), (35, 33, 30), (90, 81, 70), (154, 58, 30), (247, 242, 234)
FAR = {"transit"}
AIR = {"airport", "transit"}
FONTS = ["/System/Library/Fonts/Supplemental/Times New Roman.ttf", "/System/Library/Fonts/Supplemental/Georgia.ttf",
         "/Library/Fonts/Arial Unicode.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"]


def world(lat, lon, z):
    n = 256 * 2 ** z
    x = (lon + 180) / 360 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def tile(z, x, y):
    f = CACHE / f"{z}-{x}-{y}.jpg"
    if not f.exists():
        req = urllib.request.Request(TILE.format(z=z, x=x, y=y), headers={"User-Agent": "trip-site-builder/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(r.read())
    return Image.open(io.BytesIO(f.read_bytes())).convert("RGB")


def font(size):
    for p in FONTS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main():
    trip = json.loads((ROOT / "data" / "trip.json").read_text(encoding="utf-8"))
    stops = {s["id"]: s for s in trip["stops"]}
    route = []
    for p in trip["pages"]:
        for sid in p.get("stops", []):
            if not route or route[-1] != sid:
                route.append(sid)
    if not route:
        sys.exit("В trip.json нет точек маршрута")
    near = [stops[s] for s in dict.fromkeys(route) if stops[s]["kind"] not in FAR] or [stops[route[0]]]

    # самый крупный масштаб, при котором все точки влезают
    z = 12
    while z > 3:
        xs, ys = zip(*(world(s["lat"], s["lon"], z) for s in near))
        if max(xs) - min(xs) <= W - 2 * PAD and max(ys) - min(ys) <= H - 2 * PAD:
            break
        z -= 1
    xs, ys = zip(*(world(s["lat"], s["lon"], z) for s in near))
    ox = (max(xs) + min(xs)) / 2 - W / 2
    oy = (max(ys) + min(ys)) / 2 - H / 2

    img = Image.new("RGB", (W, H), STONE)
    try:
        for tx in range(int(ox // 256), int((ox + W) // 256) + 1):
            for ty in range(int(oy // 256), int((oy + H) // 256) + 1):
                img.paste(tile(z, tx, ty), (int(tx * 256 - ox), int(ty * 256 - oy)))
        # приглушаем подложку под камень, чтобы маршрут читался
        img = Image.blend(img, Image.new("RGB", (W, H), STONE), 0.35)
        source = "Esri World Topo"
    except Exception as ex:  # без сети — просто фон
        print("Подложка не загрузилась, рисую без неё:", ex)
        source = None

    d = ImageDraw.Draw(img)

    def pt(sid):
        s = stops[sid]
        x, y = world(s["lat"], s["lon"], z)
        return x - ox, y - oy

    for a, b in zip(route, route[1:]):
        (x1, y1), (x2, y2) = pt(a), pt(b)
        if stops[a]["kind"] in AIR and stops[b]["kind"] in AIR:
            steps = int(math.hypot(x2 - x1, y2 - y1) // 14)
            for i in range(steps):
                t = i / max(steps, 1)
                cx, cy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                d.ellipse([cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5], fill=INK)
        else:
            d.line([(x1, y1), (x2, y2)], fill=TERRA, width=6)

    f_lab, f_note = font(24), font(20)
    shown = [sid for sid in dict.fromkeys(route) if 0 <= pt(sid)[0] <= W and 0 <= pt(sid)[1] <= H]
    taken = []  # занятые прямоугольники: точки и подписи

    def free(b):
        return all(b[2] <= t[0] - 2 or b[0] >= t[2] + 2 or b[3] <= t[1] - 2 or b[1] >= t[3] + 2 for t in taken)

    for sid in shown:
        x, y = pt(sid)
        taken.append((x - 14, y - 14, x + 14, y + 14))
    for sid in shown:
        s = stops[sid]
        x, y = pt(sid)
        r = 11 if s["kind"] == "stay" else 9
        d.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill=PAPER)
        d.ellipse([x - r, y - r, x + r, y + r], fill=INK if s["kind"] == "stay" else TERRA)
        label = s["name"].upper()
        tw, th = d.textbbox((0, 0), label, font=f_lab)[2:]
        # справа, слева, сверху, снизу, по диагоналям — первое свободное место
        cands = [(x + dx - 6, y + dy - 4, x + dx + tw + 6, y + dy + th + 8)
                 for k in (1, 1.8, 2.6)
                 for dx, dy in ((22 * k, -th / 2), (-22 * k - tw, -th / 2), (-tw / 2, -th - 22 * k), (-tw / 2, 20 * k),
                                (18 * k, -th - 16 * k), (18 * k, 14 * k), (-18 * k - tw, -th - 16 * k), (-18 * k - tw, 14 * k))]
        bx = next((c for c in cands if free(c)), cands[0])
        taken.append(bx)
        d.rectangle(bx, fill=PAPER)
        d.text((bx[0] + 6, bx[1] + 2), label, font=f_lab, fill=INK)

    title = trip["meta"]["title"].upper()
    d.rectangle([0, 0, W, 64], fill=PAPER)
    d.text((28, 16), title, font=font(34), fill=INK)
    if source:
        d.text((W - 150, H - 34), "© Esri", font=f_note, fill=INK2)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(OUT, optimize=True)
    print(f"{OUT.relative_to(ROOT)}: {W}×{H}, масштаб z{z}, {OUT.stat().st_size // 1024} КБ, подложка: {source or 'нет'}")


if __name__ == "__main__":
    main()
