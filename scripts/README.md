# scripts/ · Код реально исполненных рецептов

> Каждому скрипту здесь соответствует запись в `docs/WORKS.md` (ветка
> `proven-recipes`) и доказательство: отчёт с числами в `data/ruvson/`
> и/или коммит. Это не «код, который должен работать» — это код, который
> реально выполнялся и дал проверяемый результат. Контрольные суммы —
> `scripts/SHA256SUMS.txt`.

## Цепочка корпуса RUVSON (WORKS.md, Фазы 0–9)

| Скрипт | Фаза | Что делает (как было на самом деле) | Доказательство |
|---|---|---|---|
| `ruvson_ids.py` | Ф2 | (file_id, имя) из HTML публичной папки Drive: каждому имени ближайший ID слева | MANIFEST.jsonl, 50 записей |
| `ruvson_ingest.py` | Ф2 | Инжест 50/50 с Drive (confirm=t), sha256 на приёме, ffprobe-sniffing | reingest_report.json; коммит b902a4a |
| `ruvson_reingest.py` | Ф2 | То же после вайпа: идемпотентно, .part→rename, HTML-детектор по Content-Type+doctype (не по байту `<` — ловушка трека 34) | 50/50 бит-в-бит; коммит b902a4a |
| `ruvson_probe_extract.py` | Ф3 | Промер корпуса ffprobe'ом (факты, не имена) + карта поставки | MANIFEST.jsonl |
| `ruvson_extract.py` | Ф3 | Извлечение аудио stream-copy `-c:a copy`; кодек решает контейнер (трек 03: AAC в .mp3 → .m4a) | 168.8 мин, сверено дважды |
| `audset_crosscheck.py` | Ф4 | Сверка каталога audset artist/96195 (65 позиций) с корпусом: нормализация названий + Δ≤1 с | audset_artist96195_report.json; коммит b835031 |
| `audset_final_report.py` | Ф4 | Итоговый JSON сверки для репозитория | тот же отчёт |
| `audset_download.py` | Ф5 | Скачивание с CDN audset: URL из сохранённых HTML, percent-encode ОБЯЗАТЕЛЕН (сырые пробелы = молча 0 файлов) | audset_download_manifest.json |
| `audset_content_check.py` | Ф5 | Контентная сверка «тот же ли взять»: per-second RMS → кросс-корреляция → Пирсон ВНУТРИ перекрытия ≥45 с (фикс ловушки corr>1.0) | audset_content_check.json: 01 corr 0.974, 05 corr 0.968 |
| `ruvson_sep_metrics.py` | Ф6 | Прокси-метрики сепарации: RMS, доля энергии, корреляция вокал↔музыка (прослушивание в песочнице невозможно — честный UNVERIFIED) | separation_01_report.json; коммит 053f260 |
| `ruvson_audio_resync.py` | Ф7 | Пересверка audio/ с манифестом: sha256 контейнера + md5 декодированного PCM («тег ≠ аудио») | audio_resync_report.json; коммиты b6c5ed9 и повторный прогон 2026-10-27 — IDENTICAL 52/52 |

## Цепочка Атлас-LLM (обучение адаптера, Tasks 1–3)

| Скрипт | Что делает | Доказательство |
|---|---|---|
| `measure_lengths.py` | Реальные длины пар в токенах Qwen → выбор max_len 640 (p100=601) | конфиг qwen2.5-0.5b-ru-cpu.yaml |
| `test_split_smoke.py` | Дым-проверка сплита в памяти, БЕЗ записей в data/dataset (канон соответствует обученному адаптеру) | вывод в logs сессии |
| `run_full_training.sh` | Полное обучение на CPU: MALLOC_ARENA_MAX=2, OMP_NUM_THREADS=2, venv-питон | training/logs/full_cpu_*.log; 40/40 шагов, 5098.7 c |
| `post_pipeline.sh` | Пост-конвейер после обучения (merge/eval/фиксация) | post_pipeline.log |
| `download_base.sh`, `download_foreground.sh`, `download_safetensors.sh` | Доставка базовых моделей/весов с HF в песочницу | логи закачек |
| `backfill_report.py` | Бэкфилл провенанса в training_report.json: чексуммы инструментально, версии — с ЯВНОЙ меткой источника | models/atlas-qwen-0.5b/training_report.json |

## Правила этой папки

1. Скрипт попадает сюда **после** реального выполнения с результатом —
   не до. Код хранится как исполнялся, включая захардкоженные пути
   песочницы: это историческая точность, а не неряшливость; для нового
   прогона пути адаптируются явной правкой, что само по себе честно
   отражается в отчёте.
2. Удаление/правка скрипта без отчёта-доказательства запрещена —
   правило жизни `docs/WORKS.md` распространяется на код.
3. HTML-снапшоты страниц-следов (audset_*.html, ~0.9 МБ) в репо не
   хранятся: провенанс URL и sha256 зафиксирован в
   `data/ruvson/audset_download_manifest.json`.
