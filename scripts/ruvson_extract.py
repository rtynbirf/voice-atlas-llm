#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Извлечение аудиодорожек корпуса RUVSON (после ре-инжеста).

mp4 -> audio/<base>.m4a (AAC stream-copy), mp3 -> audio/<base>.mp3 (remux).
Без перекодирования: -vn -c:a copy. Длительность меряет ffprobe (факты,
а не имена). Итоговая сумма сверяется с заявленными 168.8 мин.
"""
import json
import os
import subprocess

RAW = "/home/z/my-project/voice_data_raw/ruvson"
AUD = os.path.join(RAW, "audio")
MANIFEST = "/home/z/my-project/voice-atlas-llm/data/ruvson/MANIFEST.jsonl"


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def codec(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return out.stdout.strip() or "none"


def main():
    os.makedirs(AUD, exist_ok=True)
    manifest = [json.loads(l) for l in open(MANIFEST, encoding="utf-8")]
    total, n = 0.0, 0
    for e in manifest:
        src = os.path.join(RAW, e["name"])
        base = os.path.splitext(e["name"])[0]
        # кодек решает контейнер, а не расширение (трек 03: AAC в .mp3)
        ext = ".mp3" if codec(src) == "mp3" else ".m4a"
        dst = os.path.join(AUD, base + ext)
        if not os.path.exists(dst):
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", src, "-map", "0:a:0",
                 "-vn", "-c:a", "copy", dst],
                check=True, stderr=subprocess.DEVNULL)
        d = probe(dst)
        total += d
        n += 1
        print(f"  [{n}/50] {d:7.1f} c  {base[:60]}", flush=True)
    print(f"ИТОГ: {n} файлов, {total / 60:.1f} мин ({total / 3600:.2f} ч) аудио")


if __name__ == "__main__":
    main()
