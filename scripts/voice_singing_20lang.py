#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 18: RUVSON ПОЁТ свою строфу на 20 языках.

Пайплайн на каждый язык:
  1. TTS его строфы («И вот однажды в тишине, / Поймёшь ты всё наедине»)
     в переводе на язык L (переводы — LLM, помечены как машинные)
  2. обрезка тишины + растяжка ffmpeg-atempo до длительности ЕГО фразы (8.4 c)
  3. Praat PSOLA: замена высоты тона на ЕГО F0-контур со строфы 103.8-112.2
     трека 01 (с вибрато, медиана 247 Гц) — «он поёт свою мелодию»
  4. OpenVoice V2 ToneColorConverter -> ЕГО тембр (референс — вокал трека 01)
  5. аутро 2.5 с из РЕАЛЬНОЙ минусовки трека 01 (htdemucs no_vocals) + фейд

Честные оговорки (в отчёте и README):
- артикуляция/ритм наследуются от TTS: мелодия ложится на слоги не 1-в-1;
- переводы машинные, не вычитаны носителями;
- PSOLA + конверсия тембра = синтетика, артефакты возможны;
- вердикт по уху — только за владельцем.
"""
import hashlib
import json
import os
import subprocess
import time

import numpy as np
import soundfile as sf
import librosa
import parselmouth
from parselmouth.praat import call

VENV = "/home/z/my-project/venv-vc/bin/python"
PIPER_DIR = "/home/z/my-project/voice-vc/piper"
CKPT_DIR = "/home/z/my-project/voice-vc"
REF_WAV = "/home/z/my-project/download/ruvson_voice_clone/reference_ruvson_vocal01_182s.wav"
NO_VOCALS = "/tmp/my-project/voice_data_raw/ruvson/separation/htdemucs/01. Where Do the Years Fly By/no_vocals.wav"
WORK = "/home/z/my-project/download/ruvson_singing_20langs/work"
OUT_DIR = "/home/z/my-project/download/ruvson_singing_20langs"
RAW_DIR = os.path.join(WORK, "raw")
MP3_DIR = os.path.join(OUT_DIR, "mp3")
REPORT = os.path.join(OUT_DIR, "report_singing_20langs.json")
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

MELODY_DUR = 8.4          # длительность его строфы, сек
OUTRO_DUR = 2.5           # аутро из минусовки, сек
OUTRO_AT = 112.2          # откуда в no_vocals.wav (сразу после строфы)
SR = 22050

LYRIC_RU = "И вот однажды в тишине, поймёшь ты всё наедине"

# движки Task 17 (проверены): piper -> en zh es fr ar pt ru de tr vi sw; edge -> hi bn ur id ja mr te ta ko
LANGS = [
    dict(rank=1, code="en", file="01_english_en.wav", name_ru="английский",
         candidates=[("piper", "en_US-lessac-medium")]),
    dict(rank=2, code="zh", file="02_mandarin_zh.wav", name_ru="мандарин",
         candidates=[("piper", "zh_CN-huayan-medium"), ("edge", "zh-CN-XiaoxiaoNeural")]),
    dict(rank=3, code="hi", file="03_hindi_hi.wav", name_ru="хинди",
         candidates=[("edge", "hi-IN-SwaraNeural"), ("edge", "hi-IN-MadhurNeural")]),
    dict(rank=4, code="es", file="04_spanish_es.wav", name_ru="испанский",
         candidates=[("piper", "es_MX-ald-medium"), ("edge", "es-MX-JorgeNeural")]),
    dict(rank=5, code="fr", file="05_french_fr.wav", name_ru="французский",
         candidates=[("piper", "fr_FR-siwis-medium"), ("edge", "fr-FR-HenriNeural")]),
    dict(rank=6, code="ar", file="06_arabic_ar.wav", name_ru="арабский",
         candidates=[("piper", "ar_JO-kareem-medium")]),
    dict(rank=7, code="bn", file="07_bengali_bn.wav", name_ru="бенгальский",
         candidates=[("edge", "bn-IN-NabanitaNeural"), ("edge", "bn-IN-BashkarNeural")]),
    dict(rank=8, code="pt", file="08_portuguese_pt.wav", name_ru="португальский",
         candidates=[("piper", "pt_BR-faber-medium")]),
    dict(rank=9, code="ru", file="09_russian_ru.wav", name_ru="русский (оригинал строфы)",
         candidates=[("piper", "ru_RU-irina-medium")]),
    dict(rank=10, code="ur", file="10_urdu_ur.wav", name_ru="урду",
         candidates=[("edge", "ur-PK-AsadNeural"), ("edge", "ur-IN-GulNeural")]),
    dict(rank=11, code="id", file="11_indonesian_id.wav", name_ru="индонезийский",
         candidates=[("edge", "id-ID-ArdiNeural"), ("edge", "id-ID-GadisNeural")]),
    dict(rank=12, code="ja", file="12_japanese_ja.wav", name_ru="японский",
         candidates=[("edge", "ja-JP-KeitaNeural"), ("edge", "ja-JP-NanamiNeural")]),
    dict(rank=13, code="de", file="13_german_de.wav", name_ru="немецкий",
         candidates=[("piper", "de_DE-thorsten-medium")]),
    dict(rank=14, code="mr", file="14_marathi_mr.wav", name_ru="маратхи",
         candidates=[("edge", "mr-IN-ManoharNeural"), ("edge", "mr-IN-AarohiNeural")]),
    dict(rank=15, code="te", file="15_telugu_te.wav", name_ru="телугу",
         candidates=[("edge", "te-IN-MohanNeural"), ("edge", "te-IN-ShrutiNeural")]),
    dict(rank=16, code="ta", file="16_tamil_ta.wav", name_ru="тамильский",
         candidates=[("edge", "ta-IN-ValluvarNeural"), ("edge", "ta-IN-PallaviNeural")]),
    dict(rank=17, code="tr", file="17_turkish_tr.wav", name_ru="турецкий",
         candidates=[("piper", "tr_TR-dfki-medium"), ("edge", "tr-TR-AhmetNeural")]),
    dict(rank=18, code="vi", file="18_vietnamese_vi.wav", name_ru="вьетнамский",
         candidates=[("piper", "vi_VN-vais1000-medium"), ("edge", "vi-VN-NamMinhNeural")]),
    dict(rank=19, code="ko", file="19_korean_ko.wav", name_ru="корейский",
         candidates=[("edge", "ko-KR-InJoonNeural"), ("edge", "ko-KR-HyunsuNeural")]),
    dict(rank=20, code="sw", file="20_swahili_sw.wav", name_ru="суахили",
         candidates=[("piper", "sw_CD-lanfrica-medium")]),
]

PIPER_URL_DIR = {
    "en_US-lessac-medium": "en/en_US/lessac/medium",
    "zh_CN-huayan-medium": "zh/zh_CN/huayan/medium",
    "es_MX-ald-medium": "es/es_MX/ald/medium",
    "fr_FR-siwis-medium": "fr/fr_FR/siwis/medium",
    "ar_JO-kareem-medium": "ar/ar_JO/kareem/medium",
    "pt_BR-faber-medium": "pt/pt_BR/faber/medium",
    "de_DE-thorsten-medium": "de/de_DE/thorsten/medium",
    "tr_TR-dfki-medium": "tr/tr_TR/dfki/medium",
    "vi_VN-vais1000-medium": "vi/vi_VN/vais1000/medium",
    "sw_CD-lanfrica-medium": "sw/sw_CD/lanfrica/medium",
    "ru_RU-irina-medium": "ru/ru_RU/irina/medium",
}


def log(m):
    print(m, flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def dur(path):
    info = sf.info(path)
    return info.frames / info.samplerate


def ensure_piper_voice(voice, force=False):
    onnx = os.path.join(PIPER_DIR, voice + ".onnx")
    conf = os.path.join(PIPER_DIR, voice + ".onnx.json")
    if not force and os.path.exists(onnx) and os.path.getsize(onnx) > 1_000_000 and os.path.exists(conf):
        return
    if os.path.exists(onnx):
        os.remove(onnx)
    base = f"{HF_BASE}/{PIPER_URL_DIR[voice]}/{voice}"
    for attempt in (1, 2):
        try:
            subprocess.run(["curl", "-sL", "--fail", "-o", onnx, base + ".onnx"],
                           check=True, timeout=600)
            subprocess.run(["curl", "-sL", "--fail", "-o", conf, base + ".onnx.json"],
                           check=True, timeout=120)
            if os.path.getsize(onnx) > 1_000_000:
                log(f"  скачан {voice}")
                return
        except Exception as e:
            log(f"  попытка {attempt} скачки {voice}: {e}")
            time.sleep(3)
    raise RuntimeError(f"не удалось скачать piper-голос {voice}")


def synth_piper(text, voice, out_wav, scale=None):
    cmd = [VENV, "-m", "piper", "-m", os.path.join(PIPER_DIR, voice + ".onnx"),
           "-c", os.path.join(PIPER_DIR, voice + ".onnx.json"), "-f", out_wav]
    if scale:
        cmd += ["--length_scale", str(scale)]
    try:
        subprocess.run(cmd, input=text.encode(), check=True, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        # битый onnx (INVALID_PROTOBUF и т.п.) -> перекачать и повторить ОДИН раз
        log(f"  piper {voice} упал — перекачиваю голос")
        ensure_piper_voice(voice, force=True)
        subprocess.run(cmd, input=text.encode(), check=True, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if not os.path.exists(out_wav) or os.path.getsize(out_wav) < 2000:
        raise RuntimeError("piper вернул пустой файл")


def synth_edge(text, voice, out_wav, rate=None):
    mp3 = out_wav + ".mp3"
    cmd = [VENV, "-m", "edge_tts", "--voice", voice, "--text", text,
           "--write-media", mp3]
    if rate:
        cmd.append(f"--rate={rate}")
    subprocess.run(cmd, check=True, timeout=180,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(mp3) or os.path.getsize(mp3) < 2000:
        raise RuntimeError("edge-tts вернул пустой файл")
    subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", "22050", "-ac", "1", out_wav],
                   check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.remove(mp3)


def clean_text(line1, line2):
    punct = ".,;:!?…，。！？؛،"
    t1 = " ".join(line1.split()).strip().rstrip(punct)
    t2 = " ".join(line2.split()).strip().rstrip(punct)
    return f"{t1}, {t2}."


def atempo_chain(f):
    parts = []
    while f < 0.5:
        parts.append("atempo=0.5")
        f /= 0.5
    while f > 2.0:
        parts.append("atempo=2.0")
        f /= 2.0
    parts.append(f"atempo={f:.5f}")
    return ",".join(parts)


def psola_to_melody(src_wav, out_wav, mel_f0, mel_hop_s):
    """Растянутый TTS -> PSOLA c целевой мелодией (сетка 10 мс)."""
    snd = parselmouth.Sound(src_wav)
    manip = call(snd, "To Manipulation", 0.01, 60.0, 600.0)
    # целевой контур: None (безголосые) -> интерполяция по озвученным
    arr = np.array([np.nan if v is None else v for v in mel_f0])
    idx = np.arange(len(arr))
    good = np.isfinite(arr)
    arr = np.interp(idx, idx[good], arr[good])
    # сетка Praat 10 мс
    n_pts = int(np.floor(snd.duration / 0.01)) + 1
    t_src = np.arange(n_pts) * 0.01
    t_mel = np.clip(t_src / max(snd.duration, 1e-6) * (len(arr) - 1) * mel_hop_s,
                    0, (len(arr) - 1) * mel_hop_s)
    f_tgt = np.interp(t_mel, idx * mel_hop_s, arr)
    pitch_tier = call(manip, "Extract pitch tier")
    call(pitch_tier, "Remove points between", 0.0, snd.duration)
    for t, f in zip(t_src, f_tgt):
        call(pitch_tier, "Add point", float(t), float(max(f, 50.0)))
    call([manip, pitch_tier], "Replace pitch tier")
    sung = call(manip, "Get resynthesis (overlap-add)")
    sung.save(out_wav, "WAV")


def f0_pearson(out_wav, mel_f0, mel_hop_s):
    """Честная метрика переноса мелодии: Пирсон в полутонах по озвученным кадрам."""
    y, _ = librosa.load(out_wav, sr=SR, mono=True)
    f0, vf, _ = librosa.pyin(y, fmin=65, fmax=600, sr=SR, frame_length=1024, hop_length=256)
    t_out = np.arange(len(f0)) * (256 / SR)
    t_mel = np.arange(len(mel_f0)) * mel_hop_s
    arr = np.array([np.nan if v is None else v for v in mel_f0])
    idx = np.arange(len(arr))
    good = np.isfinite(arr)
    arr_i = np.interp(idx, idx[good], arr[good])
    mel_on_out = np.interp(t_out, t_mel, arr_i)
    m = np.isfinite(f0)
    if m.sum() < 20:
        return None, None
    a = 12 * np.log2(f0[m] / 440.0)
    b = 12 * np.log2(mel_on_out[m] / 440.0)
    r = float(np.corrcoef(a, b)[0, 1])
    mad = float(np.median(np.abs(a - b)))
    return round(r, 3), round(mad, 2)


def make_outro(total_need):
    """Аутро из реальной минусовки трека 01 с фейдом."""
    y, _ = librosa.load(NO_VOCALS, sr=SR, mono=True, offset=OUTRO_AT, duration=OUTRO_DUR)
    y = y * (0.5 / max(np.abs(y).max(), 1e-9))
    n_fade = int(1.2 * SR)
    if len(y) > n_fade:
        y[-n_fade:] *= np.linspace(1, 0, n_fade) ** 1.5
    return y


def to_mp3(wav_path, mp3_path):
    subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-b:a", "128k", "-ac", "1", mp3_path],
                   check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ─────────────────────────── ОСНОВНОЙ ХОД ───────────────────────────
def main():
    t_all = time.time()
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(MP3_DIR, exist_ok=True)

    meta = json.load(open(os.path.join(WORK, "phrase_meta.json")))
    mel_f0 = meta["f0_hz"]
    mel_hop = meta["hop_f0_s"]
    trans = json.load(open(os.path.join(WORK, "translations.json")))
    assert trans.get("en"), "нет перевода en"

    report = {
        "date": "2026-10-27",
        "task": "RUVSON SINGING x 20 languages (his lyric, his melody, his timbre)",
        "lyric_ru": LYRIC_RU,
        "lyric_evidence": (meta.get("selection_evidence") or
                           "окно 103.8-112.2 из sing_scan_register.py (13 кандидатов 200-360 Гц)") +
                          "; " + (meta.get("lyric_evidence") or ""),
        "melody": {
            "track": meta["track"], "window_s": [meta["window_start_s"], meta["window_dur_s"]],
            "f0_median_hz": meta["f0_median_hz"], "voiced_frac": meta["voiced_frac"],
            "extraction": "librosa.pyin + Praat AC cross-check (расхождение < 25 Гц)",
        },
        "translations_provenance": trans.get("_provenance", {}),
        "pipeline": ("TTS строфы -> trim -> ffmpeg atempo -> Praat PSOLA (его F0-контур) "
                     "-> OpenVoiceV2 -> аутро из минусовки трека 01"),
        "reference": REF_WAV,
        "honest_limits": [
            "мелодия ложится на слоги TTS не 1-в-1 (нет фонемного выравнивания)",
            "переводы машинные, носителями не вычитаны",
            "PSOLA+конверсия — синтетика; артефакты на сильных сдвигах тона",
            "pyin-метрика высоты на выходе OpenVoice неинтерпретируема (Task 15): мелодия меряется на PSOLA-этапе до конверсии тембра — конвертер меняет огибающую, не высоту",
            "вердикт по уху — только за владельцем",
        ],
        "languages": {},
    }
    if os.path.exists(REPORT):
        old = json.load(open(REPORT))
        if old.get("languages"):
            report["languages"] = old["languages"]

    log("== piper-голоса ==")
    for v in sorted({v for L in LANGS for e, v in L["candidates"] if e == "piper"}):
        ensure_piper_voice(v)

    log("== OpenVoice V2 ==")
    import torch
    torch.set_num_threads(2)
    from openvoice.api import ToneColorConverter
    conv = ToneColorConverter(os.path.join(CKPT_DIR, "converter_config.json"), device="cpu")
    conv.load_ckpt(os.path.join(CKPT_DIR, "converter_checkpoint.pth"))
    tgt_se = conv.extract_se(REF_WAV)
    tgt_v = tgt_se.squeeze().cpu().numpy().astype(np.float64)
    tgt_v /= (np.linalg.norm(tgt_v) + 1e-12)

    def se_cos(path):
        v = conv.extract_se(path).squeeze().cpu().numpy().astype(np.float64)
        v /= (np.linalg.norm(v) + 1e-12)
        return round(float(np.dot(v, tgt_v)), 4)

    outro = make_outro(OUTRO_DUR)

    for L in LANGS:
        code, fname = L["code"], L["file"]
        done = report["languages"].get(code, {})
        out_path = os.path.join(OUT_DIR, fname)
        if done.get("status") == "ok" and os.path.exists(out_path):
            log(f"[{L['rank']:02d}/20] {code}: готово, скип")
            continue
        t0 = time.time()
        entry = {"rank": L["rank"], "name_ru": L["name_ru"]}
        try:
            if code == "ru":
                text = LYRIC_RU
                entry["translation"] = "оригинал (транскрипция whisper x3)"
            else:
                tr = trans[code]
                text = clean_text(tr["line1"], tr["line2"])
                entry["translation"] = {"line1": tr["line1"], "line2": tr["line2"]}
            entry["text_tts"] = text

            # -- TTS c одной подгонкой темпа синтеза --
            raw1 = os.path.join(RAW_DIR, fname.replace(".wav", "_tts.wav"))
            engine, voice, note = None, None, None
            for engine, voice in L["candidates"]:
                try:
                    if engine == "piper":
                        synth_piper(text, voice, raw1)
                    else:
                        synth_edge(text, voice, raw1)
                    break
                except Exception as e:
                    log(f"  [{code}] фолбэк: {engine}:{voice}: {e}")
            y, _ = librosa.load(raw1, sr=SR, mono=True)
            y, _ = librosa.effects.trim(y, top_db=35)
            d_src = len(y) / SR
            factor = d_src / MELODY_DUR
            # если TTS сильно короче/длиннее цели — правим темп синтеза и пересинтезируем
            if factor < 0.55 and d_src < 6.0:
                try:
                    if engine == "piper":
                        synth_piper(text, voice, raw1, scale=1.35)
                    else:
                        synth_edge(text, voice, raw1, rate="-15%")
                    y, _ = librosa.load(raw1, sr=SR, mono=True)
                    y, _ = librosa.effects.trim(y, top_db=35)
                    d_src = len(y) / SR
                    factor = d_src / MELODY_DUR
                    note = f"пересинтез замедлен (был {d_src:.1f}с)"
                except Exception as e:
                    log(f"  [{code}] пересинтез не удался: {e}")
            entry.update({"engine": engine, "voice": voice, "tts_dur": round(d_src, 2),
                          "retake_note": note})
            if not (0.45 <= factor <= 1.65):
                entry["stretch_warning"] = f"сильная растяжка atempo={factor:.2f}"

            # -- растяжка до 8.4 c --
            stretched = os.path.join(RAW_DIR, fname.replace(".wav", "_stretch.wav"))
            af = atempo_chain(factor)
            sf.write(raw1, y.astype(np.float32), SR)
            subprocess.run(["ffmpeg", "-y", "-i", raw1, "-filter:a", af,
                            "-ar", "22050", "-ac", "1", stretched],
                           check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # добор/обрез до точной длины мелодии
            ys, _ = librosa.load(stretched, sr=SR, mono=True)
            need = int(MELODY_DUR * SR)
            if len(ys) < need:
                ys = np.concatenate([ys, np.zeros(need - len(ys))])
            ys = ys[:need]
            sf.write(stretched, ys.astype(np.float32), SR)

            # -- PSOLA по его мелодии --
            sung = os.path.join(RAW_DIR, fname.replace(".wav", "_sung_raw.wav"))
            psola_to_melody(stretched, sung, mel_f0, mel_hop)
            entry["se_cosine_sungraw_vs_ref"] = se_cos(sung)

            # -- тембр RUVSON (конвертированный вокал отдельно, метрики на нём) --
            conv_path = os.path.join(RAW_DIR, fname.replace(".wav", "_conv.wav"))
            conv.convert(audio_src_path=sung, src_se=conv.extract_se(sung),
                         tgt_se=tgt_se, output_path=conv_path)

            # -- аутро из его минусовки --
            yv, sr2 = librosa.load(conv_path, sr=SR, mono=True)
            gap = np.zeros(int(0.25 * SR))
            full = np.concatenate([yv, gap, outro])
            full = full[:int((MELODY_DUR + 0.25 + OUTRO_DUR) * SR)]
            full = full * (0.89 / max(np.abs(full).max(), 1e-9))
            n_f = int(0.12 * SR)
            full[:n_f] *= np.linspace(0, 1, n_f)
            sf.write(out_path, full.astype(np.float32), SR)

            # -- метрики: мелодия — на PSOLA-выходе (pyin на выходе конвертера
            #    неинтерпретируем — сигнатура OpenVoice, Task 15/17); тембр — SE-cosine на конверте --
            r, mad = f0_pearson(sung, mel_f0, mel_hop)
            entry["f0_pearson_psola_vs_his_melody"] = r
            entry["f0_median_absdiff_semitones_psola"] = mad
            entry["se_cosine_output_vs_ref"] = se_cos(conv_path)
            entry["duration_final_sec"] = round(dur(out_path), 2)
            entry["sample_rate"] = SR
            entry["sha256"] = sha256(out_path)
            entry["bytes"] = os.path.getsize(out_path)
            entry["status"] = "ok"
            entry["wall_sec"] = round(time.time() - t0, 1)
            log(f"[{L['rank']:02d}/20] {code} OK: {engine}/{voice} f0r={r} "
                f"se={entry['se_cosine_output_vs_ref']} {entry['duration_final_sec']}с "
                f"за {entry['wall_sec']}с")
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)[:300]
            log(f"[{L['rank']:02d}/20] {code} FAIL: {e}")
        report["languages"][code] = entry
        json.dump(report, open(REPORT, "w"), ensure_ascii=False, indent=2)

    ok_n = sum(1 for e in report["languages"].values() if e.get("status") == "ok")
    log(f"== ГОТОВО {ok_n}/20 за {time.time()-t_all:.0f}c ==")


if __name__ == "__main__":
    main()
