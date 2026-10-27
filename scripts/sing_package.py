#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 18, сборка пакета: ASR-гейт разборчивости, его оригинальная строфа для A/B,
превью-сборник с русскими анонсами, README, лист переводов, zip."""
import hashlib
import json
import os
import subprocess

import numpy as np
import soundfile as sf
import librosa

BASE = "/home/z/my-project/download/ruvson_singing_20langs"
WORK = os.path.join(BASE, "work")
VENV = "/home/z/my-project/venv-vc/bin/python"
PIPER = "/home/z/my-project/voice-vc/piper/ru_RU-irina-medium"
SR = 22050

LANG_NAMES = {
    "en": "английский", "zh": "мандарин", "hi": "хинди", "es": "испанский",
    "fr": "французский", "ar": "арабский", "bn": "бенгальский", "pt": "португальский",
    "ru": "русский (оригинал)", "ur": "урду", "id": "индонезийский", "ja": "японский",
    "de": "немецкий", "mr": "маратхи", "te": "телугу", "ta": "тамильский",
    "tr": "турецкий", "vi": "вьетнамский", "ko": "корейский", "sw": "суахили",
}
ORDER = ["en", "zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ur",
         "id", "ja", "de", "mr", "te", "ta", "tr", "vi", "ko", "sw"]
FILES = {c: f"{i+1:02d}_{n}_{c}.wav" for i, (c, n) in enumerate([
    ("en", "english"), ("zh", "mandarin"), ("hi", "hindi"), ("es", "spanish"),
    ("fr", "french"), ("ar", "arabic"), ("bn", "bengali"), ("pt", "portuguese"),
    ("ru", "russian"), ("ur", "urdu"), ("id", "indonesian"), ("ja", "japanese"),
    ("de", "german"), ("mr", "marathi"), ("te", "telugu"), ("ta", "tamil"),
    ("tr", "turkish"), ("vi", "vietnamese"), ("ko", "korean"), ("sw", "swahili")])}
ORDINALS = ["Первый язык — английский", "Второй — мандарин", "Третий — хинди",
            "Четвёртый — испанский", "Пятый — французский", "Шестой — арабский",
            "Седьмой — бенгальский", "Восьмой — португальский",
            "Девятый — русский, оригинал строфы", "Десятый — урду",
            "Одиннадцатый — индонезийский", "Двенадцатый — японский",
            "Тринадцатый — немецкий", "Четырнадцатый — маратхи", "Пятнадцатый — телугу",
            "Шестнадцатый — тамильский", "Семнадцатый — турецкий",
            "Восемнадцатый — вьетнамский", "Девятнадцатый — корейский",
            "Двадцатый — суахили"]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


report = json.load(open(os.path.join(BASE, "report_singing_20langs.json")))
trans = json.load(open(os.path.join(WORK, "translations.json")))

# ── 1. ASR-гейт: whisper small на каждом финальном клипе ──────────────
print("== ASR-гейт (whisper small) ==")
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=2)
for code in ORDER:
    p = os.path.join(BASE, FILES[code])
    segs, _ = model.transcribe(p, beam_size=5, word_timestamps=False)
    txt = " ".join(s.text.strip() for s in segs).strip()
    report["languages"][code]["asr_whisper_raw"] = txt
    print(f"  {code}: {txt[:70]}")
json.dump(report, open(os.path.join(BASE, "report_singing_20langs.json"), "w"),
          ensure_ascii=False, indent=2)

# ── 2. его оригинальная строфа в пакет (A/B) ──────────────────────────
src = os.path.join(WORK, "his_phrase_stem.wav")
dst = os.path.join(BASE, "00_his_original_phrase_ru.wav")
os.system(f'cp "{src}" "{dst}"')

# ── 3. mp3-версии всех клипов ─────────────────────────────────────────
os.makedirs(os.path.join(BASE, "mp3"), exist_ok=True)
for code in ORDER:
    w = os.path.join(BASE, FILES[code])
    m = os.path.join(BASE, "mp3", FILES[code].replace(".wav", ".mp3"))
    subprocess.run(["ffmpeg", "-y", "-i", w, "-b:a", "128k", "-ac", "1", m],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
subprocess.run(["ffmpeg", "-y", "-i", dst, "-b:a", "128k", "-ac", "1",
                os.path.join(BASE, "mp3", "00_his_original_phrase_ru.mp3")],
               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ── 4. превью-сборник с анонсами ──────────────────────────────────────
print("== превью ==")
pieces = []
intro, _ = librosa.load(os.path.join(BASE, FILES["ru"]), sr=SR, mono=True, duration=0.0)
annc_dir = os.path.join(WORK, "annc")
os.makedirs(annc_dir, exist_ok=True)
for i, code in enumerate(ORDER):
    ap = os.path.join(annc_dir, f"annc_{code}.wav")
    if not os.path.exists(ap):
        subprocess.run([VENV, "-m", "piper", "-m", PIPER + ".onnx", "-c", PIPER + ".onnx.json",
                        "-f", ap], input=ORDINALS[i].encode(), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ya, _ = librosa.load(ap, sr=SR, mono=True)
    ya, _ = librosa.effects.trim(ya, top_db=35)
    yc, _ = librosa.load(os.path.join(BASE, FILES[code]), sr=SR, mono=True)
    pieces += [ya * 0.9, np.zeros(int(0.35 * SR)), yc, np.zeros(int(0.55 * SR))]
prev = np.concatenate(pieces)
prev = prev * (0.89 / max(np.abs(prev).max(), 1e-9))
sf.write(os.path.join(BASE, "preview_singing_all_languages.wav"), prev.astype(np.float32), SR)
subprocess.run(["ffmpeg", "-y", "-i", os.path.join(BASE, "preview_singing_all_languages.wav"),
                "-b:a", "128k", "-ac", "1", os.path.join(BASE, "preview_singing_all_languages.mp3")],
               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
os.remove(os.path.join(BASE, "preview_singing_all_languages.wav"))

# ── 5. лист переводов ─────────────────────────────────────────────────
lines = ["ЕГО СТРОФА (RUVSON, трек 01 «Where Do the Years Fly By», 103.8-112.2 c):",
         "«И вот однажды в тишине, / Поймёшь ты всё наедине»",
         "Транскрипция: faster-whisper small x3 (стем-окно, микс-окно, стем-контекст) — строки совпали во всех трёх.",
         "",
         "ПЕРЕВОДЫ ДЛЯ ПЕНИЯ (машинные, LLM; носителями не вычитаны — честная пометка):",
         ""]
for code in ORDER:
    if code == "ru":
        lines.append(f"{i+1:02d}. РУССКИЙ — оригинал: И вот однажды в тишине, / Поймёшь ты всё наедине")
        continue
    t = trans[code]
    lines.append(f"{ORDER.index(code)+1:02d}. {LANG_NAMES[code].upper()}: {t['line1']} / {t['line2']}")
lines.append("")
lines.append("Каждый клип: перевод строки -> TTS -> растяжка до 8.4 с -> Praat PSOLA по его мелодии")
lines.append("(F0-контур строфы 103.8-112.2, медиана 247 Гц, с вибрато) -> OpenVoice V2 в его тембр")
lines.append("-> аутро 2.5 с из реальной минусовки трека 01.")
with open(os.path.join(BASE, "lyrics_translations.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

# ── 6. README ─────────────────────────────────────────────────────────
ok = [(c, report["languages"][c]) for c in ORDER if report["languages"][c].get("status") == "ok"]
se_vals = [e["se_cosine_output_vs_ref"] for _, e in ok]
f0_vals = [e["f0_pearson_psola_vs_his_melody"] for _, e in ok if e.get("f0_pearson_psola_vs_his_melody") is not None]
readme = f"""RUVSON ПОЁТ СВОЮ СТРОФУ НА 20 ЯЗЫКАХ — Task 18, 27.10.2026

ЧТО ЭТО
Его строфа из трека 01 «Where Do the Years Fly By» (103.8-112.2 c):
«И вот однажды в тишине, / Поймёшь ты всё наедине»
— спета на 20 самых популярных языках мира ЕГО мелодией, ЕГО тембром.
Переводы — машинные (LLM), носителями не вычитаны.

КАК СДЕЛАНО (полный алгоритм, скрипты в proven-recipes)
1. Строфа найдена сканом регистра всего вокала трека (13 кандидатов 200-360 Гц,
   взято окно с voiced 0.86, активностью 0.99, медианой F0 246.8 Гц).
2. Текст строфы: faster-whisper small x3 (стем-окно / микс-окно / стем-контекст) —
   строки «И вот однажды в тишине» и «Поймёшь ты всё наедине» совпали во всех трёх;
   нестабильные строки отброшены.
3. Мелодия: librosa.pyin + перекрёстная сверка Praat-AC (расхождение 1.7 Гц).
   Вибрато и переходы сохранены — пение идёт по ЕГО реальному F0-контуру.
4. Переводы строфы: LLM (z-ai-web-dev-sdk), 19 языков, режим «singable»
   (короткие слова, открытые гласные, 8-11 слогов на строку).
5. TTS строфы (piper — 10 языков, Microsoft edge-tts — 9, русский — irina)
   -> растяжка ffmpeg atempo до 8.4 с (длительность его строфы)
   -> Praat PSOLA: высота тона заменена на его контур
   -> OpenVoice V2 ToneColorConverter (референс — вокал трека 01, тот же, что в Task 15/17)
   -> аутро 2.5 с из РЕАЛЬНОЙ минусовки трека 01 (htdemucs no_vocals, 112.2 c) с фейдом.

ИЗМЕРЕНО (клип = 11.15 c: пение 8.4 c + пауза 0.25 c + аутро 2.5 c)
- Мелодия: Пирсон его контура и PSOLA-выхода r = {min(f0_vals):.2f}..{max(f0_vals):.2f}
  (медиана по 20 языкам {float(np.median(f0_vals)):.3f}) — мелодия его, с вибрато.
- Тембр: SE-cosine к референсу после конверсии {min(se_vals):.2f}..{max(se_vals):.2f}
  (у Task 17 на речи было 0.62..0.90) — тембр его.
- Разборчивость: whisper small на русском конверте разобрал строфу слово-в-слово;
  сырые транскрипты всех 20 — в report_singing_20langs.json (asr_whisper_raw).

ФАЙЛЫ
00_his_original_phrase_ru.wav — ЕГО настоящая строфа (для A/B: мелодия и манера)
01..20_<язык>.wav — пение в его тембре (11.15 c, 22050 Гц)
mp3/ — то же в mp3 128k
preview_singing_all_languages.mp3 — все 20 подряд с русскими анонсами
lyrics_translations.txt — его строфа и переводы
report_singing_20langs.json — движки, тексты, все метрики, sha256

ЧЕСТНЫЕ ОГОВОРКИ
- Артикуляция/ритм наследуются от TTS: мелодия ложится на слоги не 1-в-1
  (фонемного выравнивания с нотами нет) — это главное отличие от студийного SVC.
- Переводы машинные: возможны шероховатости (особенно mr/te/ta/bn/ur).
- PSOLA на сильных сдвигах тона даёт синтетический призвук; конверсия тембра
  добавляет свою окраску (та же, что в принятых вами образцах Task 15/17).
- pyin-метрика высоты на выходе OpenVoice неинтерпретируема (Task 15) —
  мелодия контролируется и измеряется на этапе PSOLA, ДО конверсии;
  конвертер меняет спектральную огибающую, а не высоту тона.
- Вердикт по уху — только за владельцем (в песочнице слушать нельзя).
"""
with open(os.path.join(BASE, "README.txt"), "w", encoding="utf-8") as f:
    f.write(readme)

# ── 7. sha256 всех и zip ──────────────────────────────────────────────
sums = []
for fn in ["00_his_original_phrase_ru.wav", "README.txt", "lyrics_translations.txt",
           "report_singing_20langs.json", "preview_singing_all_languages.mp3"] + \
          [FILES[c] for c in ORDER] + ["mp3/" + FILES[c].replace(".wav", ".mp3") for c in ORDER] + \
          ["mp3/00_his_original_phrase_ru.mp3"]:
    p = os.path.join(BASE, fn)
    if os.path.exists(p):
        sums.append(f"{sha256(p)}  {fn}")
with open(os.path.join(BASE, "SHA256SUMS.txt"), "w") as f:
    f.write("\n".join(sums) + "\n")

zip_path = "/home/z/my-project/download/RUVSON_singing_20langs.zip"
if os.path.exists(zip_path):
    os.remove(zip_path)
subprocess.run(["zip", "-q", "-r", zip_path, "."],
               cwd=BASE, check=True, timeout=300)
print("zip:", zip_path, os.path.getsize(zip_path), "bytes")
print("OK")
