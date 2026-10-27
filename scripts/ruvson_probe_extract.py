#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Промер корпуса RUVSON (ffprobe, факты а не имена) + извлечение аудиодорожек
stream-copy (-c:a copy — без перекодирования, «неприкосновенность исходника»).

Выход:
- voice_data_raw/ruvson/audio/  — аудиодорожки (копии потоков);
- data/ruvson/MANIFEST.jsonl (в репо) — карта поставки: имя, drive_id, размер,
  sha256, реальный контейнер, длительность, кодеки, флаги-аномалии.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SRC = Path("/home/z/my-project/voice_data_raw/ruvson")
AUDIO = SRC / "audio"
IDS_FILE = Path("/home/z/my-project/voice_data_raw/ruvson_files.json")
REPO_MANIFEST = Path("/home/z/my-project/voice-atlas-llm/data/ruvson/MANIFEST.jsonl")


def ffprobe(path: Path) -> dict | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ids = json.loads(IDS_FILE.read_text(encoding="utf-8"))
    # id -> исходное имя; имя у нас санитизировано при скачивании тем же правилом
    import re
    SAFE = re.compile(r"[^\w\s.'\",()!\[\]—‣\-]", re.UNICODE)
    id_by_name = {}
    for fid, raw in ids.items():
        clean = re.sub(r"\s+", " ", SAFE.sub("", raw)).strip()
        id_by_name[clean] = fid

    # sha256 из инжест-манифеста
    sha = {}
    mf = SRC / "MANIFEST.jsonl"
    if mf.exists():
        for line in mf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("status") == "OK":
                    sha[rec["name"]] = rec["sha256"]

    AUDIO.mkdir(parents=True, exist_ok=True)
    REPO_MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in SRC.iterdir() if p.is_file() and p.suffix.lower() in (".mp3", ".mp4", ".m4a"))
    records, anomalies = [], []
    tot_dur, tot_audio_dur, tot_bytes = 0.0, 0.0, 0
    for p in files:
        probe = ffprobe(p)
        if probe is None:
            print(f"[PROBE-FAIL] {p.name}")
            continue
        fmt = probe.get("format", {})
        streams = probe.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)
        dur = float(fmt.get("duration") or 0)
        a_br = int(a.get("bit_rate") or 0) // 1000 if a else 0
        rec = {
            "name": p.name,
            "drive_id": id_by_name.get(p.name, "?"),
            "size_bytes": p.stat().st_size,
            "sha256": sha.get(p.name, "")[:64],
            "container": fmt.get("format_name", "?"),
            "has_video": bool(v),
            "audio_codec": a.get("codec_name") if a else None,
            "duration_sec": round(dur, 1),
            "audio_bitrate_kbps": a_br,
        }
        if dur < 5:
            rec["flag"] = "ANOMALY: длительность < 5 c"
            anomalies.append(p.name)
        if not a:
            rec["flag"] = "ANOMALY: нет аудиопотока"
            anomalies.append(p.name)
        records.append(rec)
        tot_dur += dur
        tot_bytes += rec["size_bytes"]

        # извлечение аудио: копия потока, без перекодирования
        if a:
            ext = ".mp3" if a.get("codec_name") == "mp3" else ".m4a"
            out = AUDIO / (p.stem + ext)
            if not out.exists():
                r = subprocess.run(
                    ["ffmpeg", "-v", "error", "-y", "-i", str(p),
                     "-vn", "-c:a", "copy", str(out)],
                    capture_output=True, text=True, timeout=120)
                if r.returncode != 0:
                    print(f"[EXTRACT-FAIL] {p.name}: {r.stderr[:120]}")
                    continue
            ap = ffprobe(out)
            if ap:
                tot_audio_dur += float(ap.get("format", {}).get("duration") or 0)

    REPO_MANIFEST.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8")

    print(f"файлов промерено: {len(records)}/50")
    print(f"суммарная длительность исходников: {tot_dur/60:.1f} мин ({tot_dur/3600:.2f} ч)")
    print(f"аудиодорожек извлечено, суммарно: {tot_audio_dur/60:.1f} мин")
    print(f"суммарный размер: {tot_bytes/1e9:.2f} ГБ")
    print(f"аномалии: {anomalies if anomalies else 'нет'}")
    print(f"манифест в репо: {REPO_MANIFEST}")
    return 0 if len(records) == 50 else 1


if __name__ == "__main__":
    sys.exit(main())
