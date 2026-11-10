# Италия 2026

Сайт-память о семейной поездке: Андрей, Яна и Маша, 29 октября — 14 ноября 2026.
Статический, без фреймворков. Единственный источник правды — `data/trip.json`.

## Сборка

```bash
python3 tools/build.py            # публичная сборка: только одобренные фото и тексты
python3 tools/build.py --preview  # для о. Андрея: всё, неодобренное помечено
python3 tools/check_site.py       # ссылки, метаданные фото, вес главной
python3 -m http.server 8765       # http://localhost:8765
```

Пока `meta.published = false`, все страницы помечены `noindex`, а `robots.txt` закрывает сайт.

## Фото

Нужны `exiftool` (`brew install exiftool`) и venv: `python3 -m venv .venv && .venv/bin/pip install pillow pillow-heif imagehash`.

1. Скопировать Drive в `../italy-2026-media/originals/<автор>/` (вне репозитория). Оригиналы скрипты только читают.
2. `.venv/bin/python tools/media_catalog.py` — `catalog.csv`, `candidates.csv`, `REPORT.md`: время по Риму
   (с поправкой «времени Флориды»), день, ближайшая точка в радиусе 15 км или «в дороге», дубли, оценка, отбор 8–15 на день.
   Лица и тема кадра — локально через Apple Vision (`tools/vision.swift`).
3. Поправить отбор вручную в `catalog.csv` (`selected`, по желанию `cover = 1`).
4. `.venv/bin/python tools/export_photos.py` — `photos/<день>/<n>-{400,900,1800}.webp`, sRGB, без EXIF/GPS,
   запись в `trip.json`. Фото с людьми приходят с `approved: false`.
5. Дописать `alt` и подписи, после одобрения о. Андреем поставить `approved: true` / `text_approved: true`.

## Карта

Leaflet + Esri World Topo. Запасная картинка без JS: `.venv/bin/python tools/route_map.py` → `assets/route-map.png`.
Маршрут строится из точек дней (`pages[].stops`) по порядку.

## Публикация

`render.yaml` — статический сайт на Render, `autoDeploy: false`. Ничего не выкладывать без прямого «публикуй»
от о. Андрея и не раньше возвращения семьи домой.
