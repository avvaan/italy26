#!/usr/bin/env python3
"""Дороги между остановками: один раз спрашивает маршрут у OSRM (OpenStreetMap)
и сохраняет упрощённые линии в data/roads.json. Сайт потом ничего не запрашивает.

    python3 tools/road_routes.py            # докачать недостающие отрезки
    python3 tools/road_routes.py --refresh  # перезапросить все

Перелёты (аэропорт/пересадка ↔ аэропорт/пересадка) не трогаются — на карте они пунктиром.
В запрос уходят только координаты остановок (города и достопримечательности).
"""
import argparse
import json
import math
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "roads.json"
OSRM = "https://router.project-osrm.org/route/v1/driving/{a};{b}?overview=full&geometries=geojson"
AIR = {"airport", "transit"}
TOLERANCE_M = 40          # упрощение линии: отклонение не больше ~40 м
UA = "italy-2026-static-site/1.0 (one-off route build)"


def key(a, b):
    return f"{a}>{b}"


def pairs(trip):
    """Те же отрезки, что рисует карта: точки дней по порядку без повторов подряд."""
    stops = {s["id"]: s for s in trip["stops"]}
    pts = []
    for p in trip["pages"]:
        for sid in p.get("stops", []):
            if not pts or pts[-1] != sid:
                pts.append(sid)
    out = []
    for a, b in zip(pts, pts[1:]):
        if stops[a]["kind"] in AIR and stops[b]["kind"] in AIR:
            continue
        if (a, b) not in out:
            out.append((a, b))
    return stops, out


def _xy(lat, lon, lat0):
    return (lon * 111320 * math.cos(math.radians(lat0)), lat * 110540)


def simplify(pts, tol):
    """Дуглас—Пекер в метрах. pts: [[lat, lon], ...]"""
    if len(pts) < 3:
        return pts
    lat0 = pts[0][0]
    xy = [_xy(la, lo, lat0) for la, lo in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        (x1, y1), (x2, y2) = xy[i], xy[j]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-9
        best, idx = 0.0, None
        for k in range(i + 1, j):
            x0, y0 = xy[k]
            d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
            if d > best:
                best, idx = d, k
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    return [p for p, k in zip(pts, keep) if k]


def fetch(a, b):
    url = OSRM.format(a=f"{a['lon']},{a['lat']}", b=f"{b['lon']},{b['lat']}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(data.get("message") or data.get("code"))
    rt = data["routes"][0]
    line = [[round(lat, 5), round(lon, 5)] for lon, lat in rt["geometry"]["coordinates"]]
    line = simplify(line, TOLERANCE_M)
    return {"km": round(rt["distance"] / 1000, 1), "min": round(rt["duration"] / 60),
            "path": [[round(la, 4), round(lo, 4)] for la, lo in line]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    trip = json.loads((ROOT / "data" / "trip.json").read_text(encoding="utf-8"))
    stops, need = pairs(trip)
    have = {} if args.refresh or not OUT.exists() else json.loads(OUT.read_text(encoding="utf-8"))
    roads = {}
    for a, b in need:
        k = key(a, b)
        if k in have:
            roads[k] = have[k]
            continue
        try:
            roads[k] = fetch(stops[a], stops[b])
            print(f"  {k}: {roads[k]['km']} км, {len(roads[k]['path'])} точек")
        except Exception as ex:
            print(f"  {k}: не получилось ({ex}) — на карте будет прямая")
        time.sleep(1.1)   # публичный сервер: не чаще раза в секунду
    OUT.write_text(json.dumps(roads, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    pts = sum(len(r["path"]) for r in roads.values())
    print(f"{OUT.relative_to(ROOT)}: {len(roads)} отрезков, {pts} точек, {OUT.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
