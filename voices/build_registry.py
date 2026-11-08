#!/usr/bin/env python3
"""Генератор реестра голосов voices/manifest.json (П56, issue #7).

Источники (только факты, ничего не выдумывается):
  1. data/ruvson/MANIFEST.jsonl — 50 записей исходного корпуса RUVSON
     (имя, drive_id, sha256-пломба на приёме, размер, контейнер, кодек,
     длительность). Пломбы проставлены при инжесте и подтверждены
     повторным реинжестом 50/50 бит-в-бит (docs/WORKS.md, фаза 1–2).
  2. GitHub-релизы репо с голосовыми артефактами — фиксируются как
     kind="release". Честно: assets на релизах отсутствуют (проверка API
     2026-11-09, волна ×4), поэтому seal=null, seal_status="unsealed: ..."
     — мёртвых/выдуманных пломб нет.

Детерминизм: на выход не попадают ни время, ни путь песочницы, ни git-SHA;
двойная сборка байт-идентична (покрыто selftest линта и pytest).

Запуск:  python3 voices/build_registry.py            # собрать в voices/manifest.json
         python3 voices/build_registry.py --check    # собрать и сравнить с существующим
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "voices" / "manifest.json"
SRC_MANIFEST = REPO / "data" / "ruvson" / "MANIFEST.jsonl"

LICENSE_TEXT = (
    "репо (код и датасет) — MIT (LICENSE); корпус RUVSON — авторизованный "
    "источник по директиве владельца 2026-10-27 (docs/MISSION.md, "
    "docs/DATA_CARD.md §4); права артиста Ruslan Bilous (RUVSON) учтены в "
    "docs/RUVSON_VOICE_PLAN.md"
)

# Голосовые релизы (API-срез 2026-11-09, волна ×4): assets = 0 на каждом —
# артефакты недоступны для прямого хеширования, пломбы НЕ выдумываем.
VOICE_RELEASES = [
    {"tag": "voice-result-20261027",
     "title": "Результат: текст → речь голосом RUVSON (первый прогон)",
     "language_count": None, "note": "первый прогон TTS голосом RUVSON"},
    {"tag": "voice-20langs-20261027",
     "title": "RUVSON voice x 20 языков мира (топ-20)",
     "language_count": 20, "note": "партия v1: регистры разлетались, см. релиз v2"},
    {"tag": "singing-20langs-20261027",
     "title": "RUVSON поёт свою строфу на 20 языках (его мелодия, его тембр)",
     "language_count": 20, "note": "пение, партия v1"},
    {"tag": "one-voice-20langs-20261028",
     "title": "RUVSON: один голос — 20 языков (v2, приборные проверки)",
     "language_count": 20,
     "note": "один голос, регистр 240–259 Гц, whisper-раундтрип медиана 0.83 "
             "(docs/WORKS.md, Task 19-v2)"},
    {"tag": "ruvson-live-vocal-20261028",
     "title": "RUVSON — его живой вокал, воспроизведённый (голос отдельно)",
     "language_count": None, "note": "живой вокал, конверсия голоса"},
    {"tag": "ruvson-road-to-hell-20261028",
     "title": "RUVSON — Дорога в ад (The Road to Hell, Chris Rea) — демо v1",
     "language_count": None, "note": "демо-кавер; права оригинала — Chris Rea, "
                                     "артефакт помечен как демо"},
]


def build_dict() -> dict:
    voices = []
    n = 0
    if not SRC_MANIFEST.is_file():
        raise SystemExit(f"нет источника: {SRC_MANIFEST}")
    for line in SRC_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        n += 1
        name = rec["name"]
        stem = name.rsplit(".", 1)[0]
        voices.append({
            "id": f"ruvson-src-{n:03d}",
            "kind": "source-corpus",
            "artist": "RUVSON",
            "title": stem,
            "language": "ru",
            "license": LICENSE_TEXT,
            "source": {"kind": "google-drive", "drive_id": rec["drive_id"],
                       "ref": "data/ruvson/MANIFEST.jsonl"},
            "file": {"name": name,
                     "size_bytes": rec["size_bytes"],
                     "container": rec.get("container"),
                     "audio_codec": rec.get("audio_codec"),
                     "duration_sec": rec.get("duration_sec"),
                     "has_video": rec.get("has_video")},
            "seal": {"algo": "sha256", "hex": rec["sha256"]},
            "seal_status": "sealed-at-ingest (sha256 на приёме; реинжест 50/50 бит-в-бит)",
            "local_path": None,
        })
    for r in VOICE_RELEASES:
        voices.append({
            "id": f"release-{r['tag']}",
            "kind": "release",
            "artist": "RUVSON",
            "title": r["title"],
            "language": "multi",
            "language_count": r["language_count"],
            "license": LICENSE_TEXT,
            "source": {"kind": "github-release", "repo": "rtynbirf/voice-atlas-llm",
                       "tag": r["tag"]},
            "file": None,
            "seal": None,
            "seal_status": "unsealed: assets отсутствуют на релизе "
                           "(API-срез 2026-11-09, волна ×4) — пломба появится "
                           "после повторной публикации assets и прогона seal.py",
            "local_path": None,
            "note": r["note"],
        })
    return {
        "schema": "voice-registry/1",
        "seal_algo": "sha256",
        "counts": {"source-corpus": n,
                   "release": len(VOICE_RELEASES),
                   "total": n + len(VOICE_RELEASES)},
        "conventions": {
            "local_samples": "файлы в voices/audio/ регистрируются пломбовщиком "
                             "voices/seal.py (local_path + live-sha256); линт "
                             "voices/lint.py считает файл без записи сиротой",
            "seals": "seal.hex — sha256 в нижнем регистре; при несовпадении "
                     "файла и пломбы линт красный (fail-closed)",
            "releases": "для kind=release пломба ставится только по факту "
                        "доступного asset; иначе seal=null и честный "
                        "seal_status=unsealed",
        },
        "voices": voices,
    }


def render() -> bytes:
    return (json.dumps(build_dict(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> int:
    if "--check" in sys.argv:
        if not OUT.is_file():
            print("BUILD_CHECK=FAIL :: voices/manifest.json отсутствует")
            return 1
        if OUT.read_bytes() == render():
            print("BUILD_CHECK=PASS :: двойная сборка байт-идентична")
            return 0
        print("BUILD_CHECK=FAIL :: voices/manifest.json расходится со сборкой")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(render())
    d = build_dict()
    print(f"BUILD=PASS :: {d['counts']['total']} голосов "
          f"({d['counts']['source-corpus']} корпус + {d['counts']['release']} релизов)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
