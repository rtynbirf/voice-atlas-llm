#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Метрики контрольной сепарации RUVSON (трек 01, htdemucs two-stems).

Принцип: в отчёт попадают только измеренные величины. Прослушивание в
песочнице невозможно — вместо слов о звучании считаются прокси-метрики,
и в отчёте они помечены как прокси (не как вердикт прослушиванием).
"""
import json
import hashlib
import subprocess
import sys
import numpy as np

SEP_DIR = "/home/z/my-project/voice_data_raw/ruvson/separation/htdemucs/01. Where Do the Years Fly By"
SRC = "/home/z/my-project/voice_data_raw/ruvson/audio/01. Where Do the Years Fly By.mp3"
SRC_ROOT = "/home/z/my-project/voice_data_raw/ruvson/01. Where Do the Years Fly By.mp3"
SRC_NAME = "01. Where Do the Years Fly By.mp3"
MANIFEST = "/home/z/my-project/voice-atlas-llm/data/ruvson/MANIFEST.jsonl"
OUT = "/home/z/my-project/voice-atlas-llm/data/ruvson/separation_01_report.json"


def pcm_md5(path):
    """md5 декодированного потока (s16le 44.1k stereo) — сравнение аудио,
    а не контейнера."""
    h = hashlib.md5()
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path,
                          "-f", "s16le", "-ar", "44100", "-ac", "2", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for chunk in iter(lambda: p.stdout.read(1 << 20), b""):
        h.update(chunk)
    p.wait()
    return h.hexdigest()


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-show_entries", "stream=sample_rate,channels,codec_name",
         "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def decode_mono_16k(path):
    """ffmpeg -> mono f32le 16kHz, numpy."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000",
         "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def per_sec_rms(x, sr=16000):
    n = len(x) // sr
    rms = np.array([np.sqrt(np.mean(x[i * sr:(i + 1) * sr] ** 2))
                    for i in range(n)])
    return rms


def dbfs(v):
    return round(20 * np.log10(max(v, 1e-10)), 1)


def main():
    voc = f"{SEP_DIR}/vocals.wav"
    mus = f"{SEP_DIR}/no_vocals.wav"

    rep = {"date": "2026-10-27", "model": "htdemucs", "two_stems": True,
           "segment_sec": 7, "shifts": 0, "device": "cpu 2 cores",
           "source_file": SRC.split("/")[-1]}

    # провенанс: вход сепарации + манифест-оригинал (две копии, 1 байт разницы)
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["name"] == SRC_NAME:
                rep["manifest_source_sha256"] = r["sha256"]
                rep["manifest_source_size"] = r["size_bytes"]
    rep["input_file"] = SRC
    h = hashlib.sha256()
    with open(SRC, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    rep["input_file_sha256"] = h.hexdigest()
    # сверка аудио-потока входа с манифест-оригиналом (root)
    pcm_in = pcm_md5(SRC)
    pcm_root = pcm_md5(SRC_ROOT)
    rep["integrity"] = {
        "input_sha256": rep["input_file_sha256"],
        "manifest_sha256": rep.get("manifest_source_sha256"),
        "container_bytes_differ": rep["input_file_sha256"] != rep.get("manifest_source_sha256"),
        "pcm_md5_input": pcm_in,
        "pcm_md5_manifest_original": pcm_root,
        "audio_stream_identical": pcm_in == pcm_root,
        "note": ("копия в audio/ отличается от манифест-оригинала 1 байтом "
                 "контейнера/тега; аудио-поток бит-в-бит — сепарация "
                 "валидна для манифест-источника; для полного корпуса "
                 "audio/ пересверить по чек-листу Ф4"),
    }

    for name, path in [("vocals", voc), ("no_vocals", mus)]:
        info = ffprobe(path)
        st = info["streams"][0]
        fmt = info["format"]
        rep[name] = {
            "file": path.split("/")[-1],
            "duration_sec": round(float(fmt["duration"]), 2),
            "codec": st["codec_name"],
            "sample_rate": int(st["sample_rate"]),
            "channels": int(st["channels"]),
        }

    xv = decode_mono_16k(voc)
    xm = decode_mono_16k(mus)
    n = min(len(xv), len(xm))
    xv, xm = xv[:n], xm[:n]

    rv, rm = per_sec_rms(xv), per_sec_rms(xm)
    rep["metrics"] = {
        "vocals_mean_rms_dbfs": dbfs(float(np.mean(rv))),
        "vocals_peak_dbfs": dbfs(float(np.max(np.abs(xv)))),
        "no_vocals_mean_rms_dbfs": dbfs(float(np.mean(rm))),
        "no_vocals_peak_dbfs": dbfs(float(np.max(np.abs(xm)))),
        # прокси-метрики (прослушивание недоступно — это НЕ вердикт уха):
        "voiced_ratio_vocal_-40dBFS": round(float(np.mean(rv > 10 ** (-40 / 20))), 3),
        "rms_corr_vocal_vs_music_per_sec": round(float(np.corrcoef(rv, rm)[0, 1]), 3),
        "vocal_share_of_energy_pct": round(float(100 * np.sum(xv ** 2) / (np.sum(xv ** 2) + np.sum(xm ** 2))), 1),
    }
    rep["metrics_note"] = ("voiced_ratio и rms_corr — прокси чистоты "
                           "сепарации; субъективное прослушивание не "
                           "выполнялось (UNVERIFIED-флаг по уху)")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
