#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Полный инжест корпуса RUVSON из Drive-папки (50 файлов, ~3.6 ГБ).

Правила (по директиве владельца 2026-10-27, «карта → территория»):
- вопрос о lossless-оригиналах создателю НЕ блокер; собираем все доступные следы;
- недостающее находим сами.

Технические правила:
- gdown нестабилен для этой папки (проверено) → drive.usercontent.google.com
  с confirm=t;
- скачивание во временное имя *.part, переименование только после успеха
  (частичные файлы не маскируются под готовые);
- ответ-HTML = отказ, не файл: помечаем FAILURE и идём дальше;
- sha256 считается сразу после приёма; манифест — JSONL, дописывается;
- повторный запуск продолжает: готовые файлы пропускаются;
- дедлайн на прогон (сек) — не стартовать новые файлы после его истечения.
"""
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

OUT_DIR = Path("/home/z/my-project/voice_data_raw/ruvson")
IDS_FILE = Path("/home/z/my-project/voice_data_raw/ruvson_files.json")
MANIFEST = OUT_DIR / "MANIFEST.jsonl"
DEADLINE_SEC = float(os.environ.get("INGEST_DEADLINE", "500"))
WORKERS = 3
URL = ("https://drive.usercontent.google.com/download"
       "?id={fid}&export=download&confirm=t")

SAFE = re.compile(r"[^\w\s.'\",()!\[\]—‣\-]", re.UNICODE)


def sanitize(name: str) -> str:
    name = SAFE.sub("", name)
    return re.sub(r"\s+", " ", name).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    done = {}
    if MANIFEST.exists():
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("status") == "OK":
                    done[rec["drive_id"]] = rec
    return done


def fetch(task: tuple[str, str]) -> dict:
    fid, raw_name = task
    name = sanitize(raw_name)
    target = OUT_DIR / name
    part = target.with_suffix(target.suffix + ".part")
    rec = {"name": name, "drive_id": fid, "status": "FAILURE",
           "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        if part.exists():
            part.unlink()
        t0 = time.time()
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "300", "--retry", "2",
             URL.format(fid=fid), "-o", str(part)],
            capture_output=True, text=True, timeout=310)
        size = part.stat().st_size if part.exists() else 0
        head = part.open("rb").read(64) if size else b""
        if r.returncode != 0 or size < 1024 or head.lstrip().startswith((b"<!DOCTYPE", b"<html")):
            if part.exists():
                part.unlink()
            rec["error"] = f"rc={r.returncode} size={size} html={head[:5]!r}"
            return rec
        part.rename(target)
        rec.update(status="OK", size_bytes=size,
                   sha256=sha256(target),
                   elapsed_sec=round(time.time() - t0, 1))
        return rec
    except Exception as e:  # noqa: BLE001
        if part.exists():
            part.unlink()
        rec["error"] = repr(e)
        return rec


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = json.loads(IDS_FILE.read_text(encoding="utf-8"))
    done = load_manifest()
    todo = [(fid, name) for fid, name in sorted(files.items(), key=lambda kv: kv[1])
            if fid not in done]
    print(f"всего: {len(files)}, готово по манифесту: {len(done)}, к загрузке: {len(todo)}")
    t_start = time.time()
    new_ok = 0
    with MANIFEST.open("a", encoding="utf-8") as mf:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = {}
            it = iter(todo)
            def submit_more():
                for t in it:
                    if time.time() - t_start > DEADLINE_SEC:
                        break
                    futures[ex.submit(fetch, t)] = t
            submit_more()
            while futures:
                for fut in concurrent.futures.as_completed(list(futures)):
                    rec = fut.result()
                    futures.pop(fut)
                    mf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    mf.flush()
                    mark = "OK" if rec["status"] == "OK" else f"FAIL ({rec.get('error','')})"
                    print(f"  [{rec['status']}] {rec['name']} {mark}")
                    if rec["status"] == "OK":
                        new_ok += 1
                submit_more()
    total_ok = len(load_manifest())
    print(f"\nитог прогона: +{new_ok}, готово всего {total_ok}/{len(files)}")
    print(f"elapsed: {time.time()-t_start:.0f}s")
    return 0 if total_ok == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
