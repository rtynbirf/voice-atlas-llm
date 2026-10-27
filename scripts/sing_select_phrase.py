#!/usr/bin/env python3
# Task 18, шаг 1-2: выбрать лучшую спетую фразу RUVSON (хорус) из стема трека 01,
# снять её F0-контур (pyin, с вибрато) и сохранить мету.
# Соседний шаг (транскрипция faster-whisper) — отдельный скрипт.
import json, os
import numpy as np
import soundfile as sf
import librosa

STEM = "/tmp/my-project/voice_data_raw/ruvson/separation/htdemucs/01. Where Do the Years Fly By/vocals.wav"
SR = 22050
OUT_DIR = "/home/z/my-project/download/ruvson_singing_20langs/work"
os.makedirs(OUT_DIR, exist_ok=True)

y, _ = librosa.load(STEM, sr=SR, mono=True)
dur = len(y) / SR
print(f"vocals: {dur:.1f}s @ {SR}")

# --- pass 1: короткий список окон по RMS ---
hop = 512
rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
t_rms = librosa.frames_to_time(np.arange(len(rms)), sr=SR, hop_length=hop)

WIN_MIN, WIN_MAX = 9.0, 13.5
step = 0.25
cands = []
for w in np.arange(WIN_MIN, WIN_MAX + 1e-9, step):
    for start in np.arange(0.0, dur - w, 0.5):
        i0 = int(start * SR / hop)
        i1 = int((start + w) * SR / hop)
        seg = rms[i0:i1]
        if len(seg) < 10:
            continue
        # активность: доля кадров выше 40% медианной энергии трека
        thr = 0.4 * np.median(rms[rms > 0])
        active = float((seg > thr).mean())
        cands.append((active, float(start), float(w), float(seg.mean())))
cands.sort(reverse=True)
shortlist = cands[:12]
print("top windows (active, start, dur):")
for c in shortlist[:6]:
    print(f"  {c[0]:.3f}  {c[1]:7.2f}  {c[2]:.2f}")

# --- pass 2: pyin на коротком списке, скор = voiced_frac * активность ---
def pyin_seg(start, w):
    y0 = y[int(start * SR): int((start + w) * SR)]
    f0, vflag, vprob = librosa.pyin(
        y0, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
        sr=SR, frame_length=1024, hop_length=256, center=True)
    return f0, vflag, vprob

best = None
for active, start, w, _e in shortlist:
    f0, vflag, vprob = pyin_seg(start, w)
    voiced = np.nan_to_num(vflag.astype(float)).mean()
    f0m = np.nanmedian(f0) if np.isfinite(f0).any() else np.nan
    # штраф если медиана F0 далеко от его регистра (Task 15: ~288 Гц)
    reg = 0.0
    if np.isfinite(f0m):
        reg = float(np.exp(-abs(np.log2(f0m / 288.0)) * 1.2))
    score = 0.5 * voiced + 0.3 * active + 0.2 * reg
    print(f"  win {start:6.2f}+{w:.1f}: voiced={voiced:.2f} f0med={f0m if np.isfinite(f0m) else -1:6.1f} reg={reg:.2f} score={score:.3f}")
    if best is None or score > best[0]:
        best = (score, start, w, f0, vflag)

score, start, w, f0, vflag = best
print(f"CHOSEN: start={start:.2f}s dur={w:.2f}s score={score:.3f}")

# --- сохранение фразы и меты ---
t0 = int(start * SR); t1 = int((start + w) * SR)
phrase = y[t0:t1]
peak = np.abs(phrase).max()
if peak > 0:
    phrase = phrase * (0.85 / peak)
sf.write(f"{OUT_DIR}/his_phrase_stem.wav", phrase, SR, subtype="PCM_16")

# полный микс того же окна (для транскрипции-сверки)
MIX = "/home/z/my-project/voice_data_raw/ruvson/01_Where_Do_the_Years_Fly_By.mp3"
mix_ok = os.path.exists(MIX)
if mix_ok:
    ym, _ = librosa.load(MIX, sr=SR, mono=True, offset=start, duration=w)
    sf.write(f"{OUT_DIR}/his_phrase_mix.wav", ym, SR, subtype="PCM_16")

f0_seg = f0
hop_f0 = 256 / SR
meta = {
    "stem": STEM,
    "track": "01. Where Do the Years Fly By (RUVSON)",
    "window_start_s": round(float(start), 3),
    "window_dur_s": round(float(w), 3),
    "sr": SR,
    "hop_f0_s": round(hop_f0, 5),
    "f0_hz": [round(float(v), 2) if np.isfinite(v) else None for v in f0_seg],
    "voiced_flag": [bool(v) for v in vflag],
    "f0_median_hz": round(float(np.nanmedian(f0_seg)), 2) if np.isfinite(f0_seg).any() else None,
    "mix_transcribe_avail": mix_ok,
}
with open(f"{OUT_DIR}/phrase_meta.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False)
print(f"saved: his_phrase_stem.wav, phrase_meta.json (f0 {int(np.sum(np.isfinite(f0_seg)))} voiced frames)")
