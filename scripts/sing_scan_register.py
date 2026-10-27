#!/usr/bin/env python3
# Task 18: полное сканирование регистра вокала трека 01 + поиск лучшей высокой фразы
import json
import numpy as np
import soundfile as sf
import librosa

STEM = "/tmp/my-project/voice_data_raw/ruvson/separation/htdemucs/01. Where Do the Years Fly By/vocals.wav"
SR = 22050
OUT = "/home/z/my-project/download/ruvson_singing_20langs/work"

y, _ = librosa.load(STEM, sr=SR, mono=True)
dur = len(y) / SR

# грубая карта F0 по всему треку (дешёво)
f0, vf, _ = librosa.pyin(y, fmin=65, fmax=600, sr=SR, frame_length=2048, hop_length=512)
t = librosa.frames_to_time(np.arange(len(f0)), sr=SR, hop_length=512)
fin = np.isfinite(f0)
print(f"full: voiced={fin.mean():.2f}, median={np.nanmedian(f0):.1f} Hz")

# гистограмма нот
notes = 12 * np.log2(f0[fin] / 440) + 69
hist, edges = np.histogram(notes, bins=np.arange(40, 70, 1))
mx = max(hist.max(), 1)
for h, e in zip(hist, edges[:-1]):
    if h > 0:
        print(f"  midi {e:5.0f} ({440*2**((e-69)/12):6.1f} Hz): {'#'*int(h*48/mx)}")

# поиск окон 9-13с с регистром 200-360 Гц и voiced>0.55
hop = 512
rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
thr = 0.4 * np.median(rms[rms > 0])
results = []
for start in np.arange(0, dur - 9.5, 0.5):
    for w in (9.5, 11.0, 12.5):
        i0, i1 = int(start*SR/hop), int((start+w)*SR/hop)
        seg = rms[i0:i1]
        if len(seg) < 10:
            continue
        active = float((seg > thr).mean())
        if active < 0.75:
            continue
        j0, j1 = np.searchsorted(t, start), np.searchsorted(t, start + w)
        fs, vs = f0[j0:j1], vf[j0:j1]
        if len(fs) < 10:
            continue
        voiced = np.isfinite(fs).mean()
        if voiced < 0.55:
            continue
        med = np.nanmedian(fs)
        if not (200 <= med <= 360):
            continue
        results.append((voiced, active, float(start), float(w), float(med)))
results.sort(key=lambda r: -(r[0] + r[1]))
print(f"high-register candidates: {len(results)}")
for r in results[:10]:
    print(f"  start={r[2]:6.1f} dur={r[3]:.1f} voiced={r[0]:.2f} active={r[1]:.2f} f0med={r[4]:.1f}")
json.dump(results[:20], open(f"{OUT}/high_reg_windows.json", "w"))
