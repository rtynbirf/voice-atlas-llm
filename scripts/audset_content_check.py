#!/usr/bin/env python3
# Контентная сверка файлов audset CDN с корпусом: тот же ли это взять?
# v2: temp wav на диске, float32, dot-product кросс-корреляция, guards, прогресс.
import subprocess, numpy as np, json, os, sys, tempfile

RAW = "/home/z/my-project/voice_data_raw/ruvson"
AUD = "/home/z/my-project/ruvson_audset"
OUT_JSON = os.path.join(AUD, "audset_content_check.json")
SR = 16000

def decode(path):
    """decode -> mono 16k -> float32, через temp wav, с лимитом 600с"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
        tmp = t.name
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-t", "600", "-i", path, "-ac", "1",
             "-ar", str(SR), "-y", tmp], capture_output=True, timeout=120)
        if r.returncode != 0 or os.path.getsize(tmp) < 1000:
            print(f"  [ffmpeg FAIL] {os.path.basename(path)}: {r.stderr.decode()[:120]}")
            return None
        raw = open(tmp, "rb").read()
        x = np.frombuffer(raw[len(raw) % 2:], dtype=np.int16).astype(np.float32) / 32768.0
        return x
    finally:
        os.unlink(tmp)

def env_per_sec(x):
    n = len(x) // SR
    if n < 5:
        return None
    e = np.sqrt(np.mean(x[:n * SR].reshape(n, SR).astype(np.float64) ** 2, axis=1))
    e[e < 1e-9] = 1e-9
    return e

def compare(p1, p2):
    x1, x2 = decode(p1), decode(p2)
    if x1 is None or x2 is None:
        return {"corr": 0.0, "offset_sec": 0, "error": "decode_fail"}
    e1, e2 = env_per_sec(x1), env_per_sec(x2)
    if e1 is None or e2 is None:
        return {"corr": 0.0, "offset_sec": 0, "error": "too_short"}
    z1 = ((e1 - e1.mean()) / (e1.std() + 1e-12)).astype(np.float64)
    z2 = ((e2 - e2.mean()) / (e2.std() + 1e-12)).astype(np.float64)
    best = (-2.0, 0, 0)
    for off in range(-len(z2) + 5, len(z1) - 4):
        if off >= 0:
            a, b = z1[off:], z2[:len(z1) - off]
        else:
            a, b = z1[:len(z2) + off], z2[-off:]
        n = min(len(a), len(b))
        if n < 45:  # минимальное перекрытие — корреляции на коротких хвостах лживы
            continue
        a, b = a[:n], b[:n]
        # Пирсон ВНУТРИ перекрытия (пере-стандартизация)
        a = a - a.mean(); b = b - b.mean()
        den = np.sqrt((a * a).sum() * (b * b).sum())
        if den < 1e-9:
            continue
        c = float(np.dot(a, b) / den)
        if c > best[0]:
            best = (c, off, n)
    return {"corr": round(best[0], 3), "offset_sec": int(best[1]),
            "overlap_sec": int(best[2]), "len_a_sec": len(z1), "len_b_sec": len(z2)}

PAIRS = [
    ("01x_Kudaleyatgoda_audset46344685.mp3", "01. Where Do the Years Fly By.mp3", "01"),
    ("05x_Krik_342_audset46344684.mp3", "05. RUVSON — Scream in the Silence ‣ (Remix 2026) .mp4", "05"),
    ("07x_Neigrayvlyubov_Remix_audset46682880.mp3", "07. RUVSON — What If YES ‣ (Remix 2026) .mp4", "07"),
    ("07x_Neigrayvlyubov_Remix_audset46682880.mp3", "48. Fear Is Not Weakness ‣ A Song About Embracing Fear _ RUVSON.mp4", "48 (гипотеза 257с)"),
    ("krik_249_audset45283972.mp3", "05. RUVSON — Scream in the Silence ‣ (Remix 2026) .mp4", "05 (по названию)"),
    ("krik_249_audset45283972.mp3", "20. RUVSON — You Don't Live My Life (Official Music Video).mp4", "20 (168с)"),
    ("krik_249_audset45283972.mp3", "18. RUVSON — Не спеши осуждать (Official Music Video).mp4", "18 (168с)"),
    ("krik_249_audset45283972.mp3", "47. The essence is simple ‣ A song about what's important in life _ RUVSON.mp4", "47 (гипотеза 201с)"),
]

res = []
for af, cf, label in PAIRS:
    pa, pc = os.path.join(AUD, af), os.path.join(RAW, cf)
    print(f"pair: {af[:40]} <-> {label}", flush=True)
    if not os.path.exists(pc):
        print("  [SKIP] нет файла корпуса"); continue
    r = compare(pa, pc)
    c = r["corr"]
    v = ("SAME TAKE" if c >= 0.85 else
         "SAME SONG / другой мастер" if c >= 0.5 else "РАЗНЫЙ материал")
    print(f"  corr={c:+.3f} off={r['offset_sec']:+d}s -> {v}", flush=True)
    res.append({"audset": af, "corpus": cf, "label": label, **r, "verdict": v})

json.dump(res, open(OUT_JSON, "w"), ensure_ascii=False, indent=1)
print("\nсохранено:", OUT_JSON)
