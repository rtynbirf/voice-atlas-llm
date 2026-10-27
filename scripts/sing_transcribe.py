#!/usr/bin/env python3
# Task 18: транскрипция фразы RUVSON (два источника — стем и микс, перекрёстная сверка)
import json
from faster_whisper import WhisperModel

WORK = "/home/z/my-project/download/ruvson_singing_20langs/work"
model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=2)

out = {}
for name in ("his_phrase_stem.wav", "his_phrase_mix.wav"):
    segments, info = model.transcribe(
        f"{WORK}/{name}", language="ru", beam_size=5,
        vad_filter=False, word_timestamps=True)
    segs = [{"start": round(s.start, 2), "end": round(s.end, 2),
             "text": s.text.strip(),
             "words": [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for w in s.words]}
            for s in segments]
    out[name] = {"lang": info.language, "lang_prob": round(info.language_probability, 3), "segments": segs}
    print(f"--- {name} (lang={info.language} p={info.language_probability:.2f})")
    for s in segs:
        print(f"  [{s['start']:.1f}-{s['end']:.1f}] {s['text']}")
        print("   words:", " | ".join(w["w"] for w in s["words"]))

json.dump(out, open(f"{WORK}/phrase_lyrics_raw.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
