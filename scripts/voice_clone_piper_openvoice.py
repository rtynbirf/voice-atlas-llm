#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Контур «текст → речь голосом RUVSON» на CPU: piper-TTS + OpenVoice V2.

Слои по атласу (гл. 7 TTS, гл. 6 VC): контент генерит нейтральный TTS,
тембр переносится tone-color конвертером; референс тембра — вокал трека 01
«Куда летят года» (htdemucs two-stems, separation_01_report.json).

Замеры честности:
- SE-cosine (спикер-энкодер OpenVoice): source↔ref ДОЛЖЕН быть низким,
  output↔ref — высоким. Это измеримое доказательство переноса тембра.
- F0-медианы (librosa.pyin): тембр/высота выхода против источника и референса.
- Прослушивание в песочнице невозможно: вердикт по уху — UNVERIFIED (правило
  проекта), метрики — прокси, не вердикт.
"""
import json
import os
import subprocess
import time

import numpy as np
import librosa

VENV = "/home/z/my-project/venv-vc/bin/python"
PIPER_DIR = "/home/z/my-project/voice-vc/piper"
CKPT_DIR = "/home/z/my-project/voice-vc"
REF_WAV = ("/tmp/my-project/voice_data_raw/ruvson/separation/htdemucs/"
           "01. Where Do the Years Fly By/vocals.wav")
OUT_DIR = "/home/z/my-project/voice_data_raw/ruvson/voice_clone_01"
DL_DIR = "/home/z/my-project/download/ruvson_voice_clone"
REPORT = "/home/z/my-project/voice-atlas-llm/data/ruvson/voice_clone_report.json"

TEXT = ("Куда летят года — туда и мы летим. Этот голос сохранён, "
        "чтобы говорить и после.")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(DL_DIR, exist_ok=True)
t_all = time.time()
report = {"date": "2026-10-27",
          "pipeline": "piper-TTS (ru_RU-irina-medium) -> OpenVoiceV2 ToneColorConverter",
          "text": TEXT, "reference": REF_WAV,
          "device": "cpu (2 cores / 4 GB RAM)"}


def rms_dbfs(y):
    return round(float(20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)), 1)


# ── Шаг 1. TTS: текст -> нейтральная русская речь (piper, onnxruntime) ──
t0 = time.time()
src_wav = os.path.join(OUT_DIR, "tts_source_neutral.wav")
subprocess.run([VENV, "-m", "piper",
                "-m", os.path.join(PIPER_DIR, "ru_RU-irina-medium.onnx"),
                "-c", os.path.join(PIPER_DIR, "ru_RU-irina-medium.onnx.json"),
                "-f", src_wav],
               input=TEXT.encode(), check=True, timeout=300)
src, sr_src = librosa.load(src_wav, sr=None)
report["tts"] = {"wall_sec": round(time.time() - t0, 1),
                 "duration_sec": round(len(src) / sr_src, 2),
                 "sample_rate": int(sr_src),
                 "rms_dbfs": rms_dbfs(src)}
print(f"[1/4] piper TTS: {report['tts']['duration_sec']} c за "
      f"{report['tts']['wall_sec']} c (sr {sr_src})", flush=True)

# ── Шаг 2. Референс тембра: вокал RUVSON (182 c, 44.1k) ──
ref, sr_ref = librosa.load(REF_WAV, sr=None, duration=30)
report["reference_info"] = {"duration_sec_full": 182.18,
                            "loaded_sec_for_metrics": round(len(ref) / sr_ref, 2),
                            "sample_rate": int(sr_ref),
                            "rms_dbfs": rms_dbfs(ref)}
print(f"[2/4] референс: вокал 01, {report['reference_info']['duration_sec_full']} c "
      f"(для метрик загружено {report['reference_info']['loaded_sec_for_metrics']} c)",
      flush=True)

# ── Шаг 3. Перенос тембра (OpenVoice V2, CPU) ──
from openvoice.api import ToneColorConverter  # noqa: E402

t0 = time.time()
conv = ToneColorConverter(os.path.join(CKPT_DIR, "converter_config.json"),
                          device="cpu")
conv.load_ckpt(os.path.join(CKPT_DIR, "converter_checkpoint.pth"))
t_load = time.time() - t0

t0 = time.time()
src_se = conv.extract_se(src_wav)                      # эмбеддинг источника
tgt_se = conv.extract_se(REF_WAV)                      # эмбеддинг RUVSON
t_se = time.time() - t0

out_wav = os.path.join(OUT_DIR, "output_ruvson_timbre.wav")
t0 = time.time()
conv.convert(audio_src_path=src_wav, src_se=src_se, tgt_se=tgt_se,
             output_path=out_wav)
t_conv = time.time() - t0
out, sr_out = librosa.load(out_wav, sr=None)
report["convert"] = {"model_load_sec": round(t_load, 1),
                     "embeddings_sec": round(t_se, 1),
                     "convert_wall_sec": round(t_conv, 1),
                     "output_duration_sec": round(len(out) / sr_out, 2),
                     "sample_rate": int(sr_out),
                     "rms_dbfs": rms_dbfs(out)}
print(f"[3/4] OpenVoice convert: {report['convert']['output_duration_sec']} c "
      f"за {report['convert']['convert_wall_sec']} c", flush=True)


# ── Шаг 4. Метрики: SE-cosine + F0 ──
def se_vec(path):
    se = conv.extract_se(path)
    v = se.squeeze().cpu().numpy().astype(np.float64)
    return v / (np.linalg.norm(v) + 1e-12)


se_src = se_vec(src_wav)
se_out = se_vec(out_wav)
tgt_v = tgt_se.squeeze().cpu().numpy().astype(np.float64)
tgt_v = tgt_v / (np.linalg.norm(tgt_v) + 1e-12)
cos = lambda a, b: float(np.dot(a, b))  # noqa: E731


def f0_stats(path, sec=15):
    y, sr = librosa.load(path, sr=22050, duration=sec)
    f0, _, _ = librosa.pyin(y, fmin=65, fmax=400, sr=sr)
    f0 = f0[~np.isnan(f0)]
    if len(f0) == 0:
        return None
    return {"median_hz": round(float(np.median(f0)), 1),
            "iqr_hz": round(float(np.subtract(*np.percentile(f0, [75, 25]))), 1),
            "voiced_frames": int(len(f0))}


def env_corr(y1, y2, sr, hop=512):
    n = min(len(y1), len(y2)) // hop
    e1 = np.sqrt(np.mean(y1[:n * hop].reshape(n, hop) ** 2, axis=1))
    e2 = np.sqrt(np.mean(y2[:n * hop].reshape(n, hop) ** 2, axis=1))
    a, b = e1 - e1.mean(), e2 - e2.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum()) + 1e-12
    return round(float(np.dot(a, b) / den), 3)


m = {
    "se_cosine_source_vs_ref": round(cos(se_src, tgt_v), 4),
    "se_cosine_output_vs_ref": round(cos(se_out, tgt_v), 4),
    "se_cosine_source_vs_output": round(cos(se_src, se_out), 4),
    "env_corr_source_vs_output": env_corr(src, out, sr_out),
    "f0_source": f0_stats(src_wav),
    "f0_output": f0_stats(out_wav),
    "f0_reference_first15s": f0_stats(REF_WAV),
}
report["metrics"] = m

# ── Шаг 5. Разборчивость: ASR (faster-whisper small, int8) + WER ──
import re as _re  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

t0 = time.time()
asr = WhisperModel("small", device="cpu", compute_type="int8")


def norm(t):
    return _re.sub(r"[^\w\s]", "", t.lower()).split()


def wer(ref_tokens, hyp_tokens):
    r, h = ref_tokens, hyp_tokens
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    d[:, 0] = np.arange(len(r) + 1)
    d[0, :] = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1,
                          d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return round(float(d[-1, -1] / max(1, len(r))), 3)


def asr_text(path):
    segs, _ = asr.transcribe(path, language="ru")
    return " ".join(s.text.strip() for s in segs)


ref_tokens = norm(TEXT)
asr_src = asr_text(src_wav)
asr_out = asr_text(out_wav)
m["asr_source_text"] = asr_src
m["asr_output_text"] = asr_out
m["wer_source_vs_text"] = wer(ref_tokens, norm(asr_src))
m["wer_output_vs_text"] = wer(ref_tokens, norm(asr_out))
report["asr_wall_sec"] = round(time.time() - t0, 1)
report["metrics_notes"] = (
    "env_corr НЕ годится как метрика качества при смене тембра (формантный "
    "сдвиг делает корреляцию огибающих околонулевой при полностью "
    "разборчивой речи — доказано ASR); решающая метрика контента — WER. "
    "pyin на выходе ненадёжен (мало озвученных кадров после смены тембра) — "
    "F0 выхода не интерпретируется. Основные метрики: WER и SE-cosine.")
print("[5/5] ASR WER: source", m["wer_source_vs_text"],
      "| output", m["wer_output_vs_text"], flush=True)

# ── Фиксация: sha256 артефактов ──
import hashlib  # noqa: E402


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


report["artifacts"] = {os.path.basename(p): {"sha256": sha256(p),
                       "bytes": os.path.getsize(p)}
                       for p in (src_wav, out_wav, REF_WAV)}
report["total_wall_sec"] = round(time.time() - t_all, 1)
report["honesty"] = ("метрики — прокси (SE-энкодер OpenVoice, pyin); "
                     "прослушивание в песочнице невозможно — вердикт по уху "
                     "UNVERIFIED; синтетика честно маркирована (закон 7: "
                     "результат — копия-наследник, не двойник)")

json.dump(report, open(REPORT, "w"), ensure_ascii=False, indent=2)

# копия артефактов для владельца
import shutil  # noqa: E402
shutil.copy(src_wav, os.path.join(DL_DIR, "tts_source_neutral.wav"))
shutil.copy(out_wav, os.path.join(DL_DIR, "output_ruvson_timbre.wav"))
shutil.copy(REF_WAV, os.path.join(DL_DIR, "reference_ruvson_vocal01_182s.wav"))

print("[4/4] МЕТРИКИ:", json.dumps(m, ensure_ascii=False, indent=1))
print("ИТОГ:", report["total_wall_sec"], "c; отчёт:", REPORT)
