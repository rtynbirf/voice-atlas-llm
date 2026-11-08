#!/usr/bin/env python3
# Task 18: финальная мелодия строфы «И вот однажды в тишине, / Поймёшь ты всё наедине»
# Строфа 104.2-111.6 (3 согласованные транскрипции). Окно с запасом: 103.8-112.2 (8.4с)
import json
import numpy as np
import soundfile as sf
import librosa
import parselmouth

STEM = "/tmp/my-project/voice_data_raw/ruvson/separation/htdemucs/01. Where Do the Years Fly By/vocals.wav"
SR = 22050
START, DUR = 103.8, 8.4
WORK = "/home/z/my-project/download/ruvson_singing_20langs/work"

y, _ = librosa.load(STEM, sr=SR, mono=True)
seg = y[int(START*SR): int((START+DUR)*SR)].copy()
seg = seg * (0.85 / max(np.abs(seg).max(), 1e-9))
sf.write(f"{WORK}/his_phrase_stem.wav", seg, SR, subtype="PCM_16")

f0, vf, vp = librosa.pyin(seg, fmin=65, fmax=600, sr=SR, frame_length=1024, hop_length=256)
snd = parselmouth.Sound(f"{WORK}/his_phrase_stem.wav")
p = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=600)
f0p = p.selected_array["frequency"]
med_pyin = float(np.nanmedian(f0[np.isfinite(f0)]))
med_praat = float(np.median(f0p[f0p > 0]))
assert abs(med_pyin - med_praat) < 25, "методы разошлись"
voiced_frac = float(np.isfinite(f0).mean())
print(f"melody: {DUR}s, voiced={voiced_frac:.2f}, median pyin={med_pyin:.1f}, praat={med_praat:.1f}")

meta = {
    "stem": STEM, "track": "01. Where Do the Years Fly By (RUVSON)",
    "lyric_ru": "И вот однажды в тишине, / Поймёшь ты всё наедине",
    "lyric_evidence": "faster-whisper small x3: stem-window, mix-window, stem-context — строки 2-3 совпали во всех; строки вне строфы отброшены (нестабильны)",
    "window_start_s": START, "window_dur_s": DUR, "sr": SR,
    "hop_f0_s": round(256/SR, 5),
    "f0_hz": [round(float(v), 2) if np.isfinite(v) else None for v in f0],
    "voiced_flag": [bool(v) for v in vf],
    "f0_median_hz": round(med_pyin, 2),
    "f0_median_praat_hz": round(med_praat, 2),
    "voiced_frac": round(voiced_frac, 3),
}
json.dump(meta, open(f"{WORK}/phrase_meta.json", "w", encoding="utf-8"), ensure_ascii=False)
print("saved: his_phrase_stem.wav (8.4s melody), phrase_meta.json")
