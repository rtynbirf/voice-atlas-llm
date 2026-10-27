#!/usr/bin/env python3
# Task 18: извлечение выбранной фразы (101.5s, 9.5s — из sing_scan_register.py)
import json
import numpy as np
import soundfile as sf
import librosa
import parselmouth

STEM = "/tmp/my-project/voice_data_raw/ruvson/separation/htdemucs/01. Where Do the Years Fly By/vocals.wav"
MIX = "/home/z/my-project/voice_data_raw/ruvson/01_Where_Do_the_Years_Fly_By.mp3"
SR = 22050
START, DUR = 101.5, 9.5
OUT = "/home/z/my-project/download/ruvson_singing_20langs/work"

y, _ = librosa.load(STEM, sr=SR, mono=True)
t0, t1 = int(START * SR), int((START + DUR) * SR)
phrase = y[t0:t1].copy()
phrase = phrase * (0.85 / max(np.abs(phrase).max(), 1e-9))
sf.write(f"{OUT}/his_phrase_stem.wav", phrase, SR, subtype="PCM_16")

ym, _ = librosa.load(MIX, sr=SR, mono=True, offset=START, duration=DUR)
sf.write(f"{OUT}/his_phrase_mix.wav", ym, SR, subtype="PCM_16")

# мелодия: pyin (плотная сетка, для PSOLA) + Praat AC (сверка)
f0, vf, vp = librosa.pyin(phrase, fmin=65, fmax=600, sr=SR, frame_length=1024, hop_length=256)
snd = parselmouth.Sound(f"{OUT}/his_phrase_stem.wav")
p = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=600)
f0p = p.selected_array["frequency"]
vp_mask = f0p > 0
med_pyin = float(np.nanmedian(f0[np.isfinite(f0)]))
med_praat = float(np.median(f0p[vp_mask]))
print(f"pyin median {med_pyin:.1f} | praat median {med_praat:.1f} | praat voiced {vp_mask.mean():.2f}")
assert abs(med_pyin - med_praat) < 25, "расхождение методов > 25 Гц — стоп"

meta = {
    "stem": STEM, "track": "01. Where Do the Years Fly By (RUVSON)",
    "window_start_s": START, "window_dur_s": DUR, "sr": SR,
    "hop_f0_s": round(256 / SR, 5),
    "f0_hz": [round(float(v), 2) if np.isfinite(v) else None for v in f0],
    "voiced_flag": [bool(v) for v in vf],
    "f0_median_hz": round(med_pyin, 2),
    "f0_median_praat_hz": round(med_praat, 2),
    "selection_evidence": "sing_scan_register.py: voiced=0.86 active=0.99 из 13 кандидатов 200-360 Гц",
}
json.dump(meta, open(f"{OUT}/phrase_meta.json", "w", encoding="utf-8"), ensure_ascii=False)
print(f"saved phrase {DUR}s, f0 voiced frames: {int(np.isfinite(f0).sum())}")
