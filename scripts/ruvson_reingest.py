#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ре-инжест корпуса RUVSON 50/50 из манифеста после вайпа песочницы.

Карта (data/ruvson/MANIFEST.jsonl: name, drive_id, sha256, size) — источник
истины. Скачивание: drive.usercontent.google.com (confirm=t, gdown нестабилен
— проверено Таском 6/8). Приём: .part -> rename, отказ если пришёл HTML,
sha256 на приёме обязан совпасть с манифестом (иначе файл не принимается).
Идемпотентен: уже скачанные и сверкнувшиеся файлы пропускаются.
"""
import json
import hashlib
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

RAW = "/home/z/my-project/voice_data_raw/ruvson"
MANIFEST = "/home/z/my-project/voice-atlas-llm/data/ruvson/MANIFEST.jsonl"
URL = "https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(entry, attempts=3):
    name = entry["name"]
    dest = os.path.join(RAW, name)
    part = dest + ".part"
    # идемпотентность: уже есть и свернулся — пропускаем
    if os.path.exists(dest) and sha256(dest) == entry["sha256"]:
        return name, "OK_CACHE", entry["size_bytes"]
    for i in range(attempts):
        try:
            req = urllib.request.Request(URL.format(fid=entry["drive_id"]),
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r, open(part, "wb") as f:
                ctype = r.headers.get("Content-Type", "")
                head = b""
                ok = True
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    if not head:
                        head = chunk[:512]
                        # HTML-заглушка, а не байт '<' в бинарных данных:
                        # решает Content-Type и явные маркеры разметки
                        lowered = head.lstrip()[:9].lower()
                        if ("text/html" in ctype.lower()
                                or lowered.startswith((b"<!doctype", b"<html"))):
                            ok = False
                            break  # HTML-страница вместо файла
                    f.write(chunk)
            if not ok:
                os.remove(part)
                return name, "HTML_REFUSED", 0
            if sha256(part) != entry["sha256"]:
                os.remove(part)
                continue  # повтор
            os.rename(part, dest)
            return name, "OK", entry["size_bytes"]
        except Exception as e:
            if os.path.exists(part):
                os.remove(part)
            if i == attempts - 1:
                return name, f"FAIL:{type(e).__name__}", 0
    return name, "FAIL_RETRIES", 0


def main():
    os.makedirs(RAW, exist_ok=True)
    manifest = [json.loads(l) for l in open(MANIFEST, encoding="utf-8")]
    print(f"манифест: {len(manifest)} записей; запускаю ре-инжест (3 потока)")
    ok, fails, total = 0, [], 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(fetch, e): e["name"] for e in manifest}
        for fut in as_completed(futs):
            name, status, size = fut.result()
            total += size
            if status.startswith("OK"):
                ok += 1
            else:
                fails.append({"file": name, "status": status})
            print(f"  [{ok + len(fails)}/{len(manifest)}] {status}: {name[:58]}",
                  flush=True)
    rep = {"date": "2026-10-27", "manifest_entries": len(manifest),
           "downloaded_ok": ok, "failures": fails, "total_bytes": total}
    with open(os.path.join(RAW, "reingest_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"ИТОГ: {ok}/{len(manifest)} OK, {total / 1e9:.2f} ГБ, отказов: {len(fails)}")
    for x in fails:
        print("  ФЕЙЛ:", x)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
