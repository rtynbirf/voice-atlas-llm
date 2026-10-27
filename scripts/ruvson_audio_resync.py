#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пересверка папки audio/ RUVSON с манифестом (чек-лист Ф4).

Каждый файл audio/ сопоставляется с записью манифеста по базовому имени.
Статусы:
  EXACT_COPY           — sha256 контейнера совпал (бит-в-бит файл);
  EXTRACT_BITIDENTICAL — mp4→m4a: контейнер другой, аудио-поток (PCM md5)
                         бит-в-бит = корректная extraction;
  TAG_ONLY_DIFF        — mp3-remux: контейнер отличается тегом, поток
                         бит-в-бит (ожидаемое поведение ffmpeg -c copy);
  CONTENT_DIFF         — аудио-поток РАЗЛИЧАЕТСЯ — дефект, перезакодировка;
  NO_MANIFEST_TWIN / COPY_UNDER_OTHER_NAME — имя не из манифеста.
"""
import json
import hashlib
import os
import subprocess
import collections

RAW = "/home/z/my-project/voice_data_raw/ruvson"
AUD = os.path.join(RAW, "audio")
MANIFEST = "/home/z/my-project/voice-atlas-llm/data/ruvson/MANIFEST.jsonl"
OUT = "/home/z/my-project/voice-atlas-llm/data/ruvson/audio_resync_report.json"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pcm_md5(path, timeout=120):
    """md5 декодированного аудио (s16le 44.1k stereo, дорожка a:0)."""
    h = hashlib.md5()
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0",
         "-f", "s16le", "-ar", "44100", "-ac", "2", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    import time
    t0 = time.time()
    while True:
        chunk = p.stdout.read(1 << 20)
        if not chunk:
            break
        h.update(chunk)
        if time.time() - t0 > timeout:
            p.kill()
            return "DECODE_TIMEOUT"
    p.wait()
    return h.hexdigest()


def main():
    manifest = [json.loads(l) for l in open(MANIFEST, encoding="utf-8")]
    # близнецы по базовому имени могут быть ДВОЕ (трек 01: mp3 + mp4).
    # Развязка: audio/.mp3 -> источник .mp3; audio/.m4a -> .mp4, иначе .mp3
    # (трек 03: AAC внутри .mp3). Если близнец один — берём его.
    from collections import defaultdict
    by_base = defaultdict(list)
    for r in manifest:
        by_base[os.path.splitext(r["name"])[0]].append(r)

    def pick(entries, audio_ext):
        if len(entries) == 1:
            return entries[0]
        want = ".mp3" if audio_ext == ".mp3" else None
        if want:
            for r in entries:
                if r["name"].lower().endswith(".mp3"):
                    return r
        # .m4a: сначала .mp4, потом .mp3
        for r in entries:
            if r["name"].lower().endswith(".mp4"):
                return r
        return entries[0]

    results, summary = [], collections.Counter()
    todo = sorted(os.listdir(AUD))
    for i, fn in enumerate(todo, 1):
        print(f"  [{i}/{len(todo)}] {fn[:56]}", flush=True)
        path = os.path.join(AUD, fn)
        base = os.path.splitext(fn)[0]
        ext = os.path.splitext(fn)[1]
        entry = pick(by_base[base], ext) if base in by_base else None
        rec = {"file": fn, "size_bytes": os.path.getsize(path),
               "sha256": sha256(path)}
        if entry is None:
            twin = next((r for r in manifest if r["sha256"] == rec["sha256"]), None)
            rec["status"] = "COPY_UNDER_OTHER_NAME" if twin else "NO_MANIFEST_TWIN"
            if twin:
                rec["manifest_name"] = twin["name"]
        else:
            rec["manifest_name"] = entry["name"]
            src = os.path.join(RAW, entry["name"])
            if rec["sha256"] == entry["sha256"]:
                rec["status"] = "EXACT_COPY"
            else:
                rec["pcm_md5"] = pcm_md5(path)
                rec["original_pcm_md5"] = pcm_md5(src)
                if rec["pcm_md5"] == rec["original_pcm_md5"]:
                    rec["status"] = ("EXTRACT_BITIDENTICAL"
                                     if entry["name"].lower().endswith(".mp4")
                                     else "TAG_ONLY_DIFF")
                else:
                    rec["status"] = "CONTENT_DIFF"
        summary[rec["status"]] += 1
        results.append(rec)

    report = {
        "date": "2026-10-27",
        "note": ("аудио-слой восстановлен после вайпа песочницы ре-инжестом "
                 "по манифесту (50/50, sha256 на приёме); пересверка — "
                 "контроль всего extraction-пути"),
        "checked_files": len(results),
        "manifest_entries": len(manifest),
        "summary": dict(summary),
        "defects": [r for r in results
                    if r["status"] in ("CONTENT_DIFF", "NO_MANIFEST_TWIN")],
        "results": results,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("проверено:", report["checked_files"], "| манифест:", report["manifest_entries"])
    print("сводка:", json.dumps(report["summary"], ensure_ascii=False))
    for d in report["defects"]:
        print("ДЕФЕКТ:", d["file"][:64], "->", d["status"])


if __name__ == "__main__":
    main()
