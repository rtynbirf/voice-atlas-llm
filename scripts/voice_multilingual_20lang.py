#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 17: тембр RUVSON × 20 самых популярных языков мира.

Пайплайн на каждый язык (тот же, что дал проверенный русский результат Task 15):
  нейтральный TTS (piper / edge-tts / espeak-аварийный)
  -> OpenVoice V2 ToneColorConverter (референс = вокал трека 01, htdemucs)
  -> клип 10-15 с в тембре RUVSON.

Движки выбраны по фактической доступности (HEAD-проверки 27.10.2026):
- piper (офлайн, HF rhasspy): en zh es fr ar pt de tr vi sw ru
- edge-tts (Microsoft Azure Neural): hi bn ur id ja mr te ta ko
- filebin.net забанен по IP песочницы (Task 16) -> доставка GitHub Release.

Честность: высота тона наследуется от базового TTS-голоса, переносится только
тембр (спектральная огибающая); метрика переноса — SE-cosine к референсу;
вердикт по уху — только за владельцем (в песочнице слушать нельзя).
"""
import hashlib
import json
import os
import shutil
import subprocess
import time
import zipfile

import numpy as np
import soundfile as sf
import librosa

VENV = "/home/z/my-project/venv-vc/bin/python"
PIPER_DIR = "/home/z/my-project/voice-vc/piper"
CKPT_DIR = "/home/z/my-project/voice-vc"
REF_WAV = "/home/z/my-project/download/ruvson_voice_clone/reference_ruvson_vocal01_182s.wav"
OUT_DIR = "/home/z/my-project/download/ruvson_voice_20langs"
RAW_DIR = os.path.join(OUT_DIR, "raw")
MP3_DIR = os.path.join(OUT_DIR, "mp3")
REPORT = os.path.join(OUT_DIR, "report_20langs.json")
ZIP_PATH = "/home/z/my-project/download/RUVSON_voice_20langs.zip"
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

MIN_D, MAX_D = 9.8, 15.2  # целевое окно длительности, сек


# ─────────────────────────── ЯЗЫКИ ───────────────────────────
# candidates: список (engine, voice) в порядке приоритета.
# piper voice: имя файлов в PIPER_DIR; edge voice: Azure Neural; espeak: код espeak-ng.
LANGS = [
    dict(rank=1, code="en", file="01_english_en.wav", name_ru="английский",
         candidates=[("piper", "en_US-lessac-medium"), ("edge", "en-US-GuyNeural")],
         text=("Hello! This is a sample of the same voice speaking English. "
               "A neural network generates every word you hear, and then a special "
               "model converts the sound into the target timbre. Listen carefully "
               "and decide for yourself how natural it sounds.")),
    dict(rank=2, code="zh", file="02_mandarin_zh.wav", name_ru="китайский (мандарин)",
         candidates=[("piper", "zh_CN-huayan-medium"), ("edge", "zh-CN-XiaoxiaoNeural")],
         text=("大家好，这是一段中文语音样本。神经网络先把你听到的每个字生成出来，"
               "然后由专门的模型把音色转换成目标音色。请仔细听，看看听起来是否自然流畅。")),
    dict(rank=3, code="hi", file="03_hindi_hi.wav", name_ru="хинди",
         candidates=[("edge", "hi-IN-SwaraNeural"), ("edge", "hi-IN-MadhurNeural"), ("espeak", "hi")],
         text=("नमस्ते! यह उसी आवाज़ का हिंदी नमूना है। तंत्रिका जाल पहले आपके सुने हर शब्द को बनाता है, "
               "फिर एक विशेष मॉडल ध्वनि को लक्षित आवाज़ में बदल देता है। ध्यान से सुनिए और स्वयं तय कीजिए "
               "कि यह कितना स्वाभाविक लगता है।")),
    dict(rank=4, code="es", file="04_spanish_es.wav", name_ru="испанский",
         candidates=[("piper", "es_MX-ald-medium"), ("edge", "es-MX-JorgeNeural")],
         text=("¡Hola! Esta es una muestra de la misma voz hablando español. "
               "Una red neuronal genera cada palabra y después un modelo especial "
               "convierte el sonido al timbre objetivo. Escucha con atención y "
               "decide tú mismo si suena natural.")),
    dict(rank=5, code="fr", file="05_french_fr.wav", name_ru="французский",
         candidates=[("piper", "fr_FR-siwis-medium"), ("edge", "fr-FR-HenriNeural")],
         text=("Bonjour ! Voici un échantillon de la même voix qui parle français. "
               "Un réseau de neurones génère chaque mot, puis un modèle spécial "
               "transforme le son vers le timbre cible. Écoutez attentivement et "
               "jugez vous-même si cela semble naturel.")),
    dict(rank=6, code="ar", file="06_arabic_ar.wav", name_ru="арабский",
         candidates=[("piper", "ar_JO-kareem-medium"), ("edge", "ar-EG-ShakirNeural")],
         text=("مرحبًا! هذا نموذج للصوت نفسه يتحدث العربية. تولّد الشبكة العصبية كل كلمة تسمعها، "
               "ثم يحوّل نموذج خاص الصوت إلى الطابع الصوتي المطلوب. استمع جيدًا واحكم بنفسك هل يبدو طبيعيًا.")),
    dict(rank=7, code="bn", file="07_bengali_bn.wav", name_ru="бенгальский",
         candidates=[("edge", "bn-BD-NabanitaNeural"), ("edge", "bn-IN-TanishaaNeural"), ("espeak", "bn")],
         text=("নমস্কার! এই একই কণ্ঠস্বরের বাংলা নমুনা। নিউরাল নেটওয়ার্ক প্রথমে আপনার শোনা প্রতিটি শব্দ তৈরি করে, "
               "তারপর একটি বিশেষ মডেল শব্দটিকে লক্ষ্য কণ্ঠে রূপান্তর করে। মন দিয়ে শুনুন এবং নিজেই বিচার করুন "
               "এটি কতটা স্বাভাবিক শোনাচ্ছে।")),
    dict(rank=8, code="pt", file="08_portuguese_pt.wav", name_ru="португальский",
         candidates=[("piper", "pt_BR-faber-medium"), ("edge", "pt-BR-AntonioNeural")],
         text=("Olá! Esta é uma amostra da mesma voz falando português. "
               "Uma rede neural gera cada palavra e depois um modelo especial "
               "converte o som para o timbre desejado. Ouça com atenção e decida "
               "você mesmo se parece natural.")),
    dict(rank=9, code="ru", file="09_russian_ru.wav", name_ru="русский",
         candidates=[("piper", "ru_RU-irina-medium")],
         text=("Куда летят года — туда и мы летим. Этот голос сохранён, чтобы говорить и после. "
               "Теперь он звучит на двадцати языках, но тембр остаётся тем же самым — "
               "слушайте и решайте сами, насколько это похоже.")),
    dict(rank=10, code="ur", file="10_urdu_ur.wav", name_ru="урду",
         candidates=[("edge", "ur-PK-AsadNeural"), ("edge", "ur-IN-GulNeural"), ("espeak", "ur")],
         text=("سلام! یہ اُسی آواز کا اردو نمونہ ہے۔ عصبی جال پہلے آپ کے سُنے ہوئے ہر لفظ کو بناتا ہے، "
               "پھر ایک خاص ماڈل آواز کو مطلوبہ آواز میں بدل دیتا ہے۔ غور سے سنیے اور خود فیصلہ کیجیے "
               "کہ یہ کتنا قدرتی لگتا ہے۔")),
    dict(rank=11, code="id", file="11_indonesian_id.wav", name_ru="индонезийский",
         candidates=[("edge", "id-ID-ArdiNeural"), ("edge", "id-ID-GadisNeural"), ("espeak", "id")],
         text=("Halo! Ini adalah sampel suara yang sama berbahasa Indonesia. "
               "Jaringan saraf menghasilkan setiap kata yang Anda dengar, lalu "
               "model khusus mengubah suaranya menjadi timbre target. Dengarkan "
               "baik-baik dan nilai sendiri apakah terdengar alami.")),
    dict(rank=12, code="de", file="12_german_de.wav", name_ru="немецкий",
         candidates=[("piper", "de_DE-thorsten-medium"), ("edge", "de-DE-ConradNeural")],
         text=("Hallo! Das ist eine Probe derselben Stimme auf Deutsch. "
               "Ein neuronales Netz erzeugt jedes Wort, danach wandelt ein "
               "spezielles Modell den Klang in den Ziel-Timbre um. Höre genau "
               "hin und entscheide selbst, wie natürlich das klingt.")),
    dict(rank=13, code="ja", file="13_japanese_ja.wav", name_ru="японский",
         candidates=[("edge", "ja-JP-KeitaNeural"), ("edge", "ja-JP-NanamiNeural"), ("espeak", "ja")],
         text=("こんにちは！これは同じ声色による日本語のサンプルです。ニューラルネットワークがまず聞こえる言葉をすべて生成し、"
               "そのあと特別なモデルが音声を目標の声色に変換します。よく聞いて、自然に聞こえるか自分で判断してください。")),
    dict(rank=14, code="mr", file="14_marathi_mr.wav", name_ru="маратхи",
         candidates=[("edge", "mr-IN-ManoharNeural"), ("edge", "mr-IN-AarohiNeural"), ("espeak", "mr")],
         text=("नमस्कार! हा त्याच आवाजाचा मराठी नमुना आहे. मज्जातंत्रजाल प्रथम तुम्ही ऐकत असलेला प्रत्येक शब्द तयार करते, "
               "आणि नंतर एक विशेष मॉडेल आवाजाला लक्ष्य आवाजात रूपांतरित करते. लक्षपूर्वक ऐका आणि ते किती नैसर्गिक "
               "वाटते ते स्वतः ठरवा.")),
    dict(rank=15, code="te", file="15_telugu_te.wav", name_ru="телугу",
         candidates=[("edge", "te-IN-MohanNeural"), ("edge", "te-IN-ShrutiNeural"), ("espeak", "te")],
         text=("నమస్కారం! ఇది అదే స్వరం యొక్క తెలుగు నమూనా. న్యూరల్ నెట్‌వర్క్ ముందుగా మీరు వినే ప్రతి పదాన్ని సృష్టిస్తుంది, "
               "తర్వాత ప్రత్యేక మోడల్ శబ్దాన్ని లక్ష్య స్వరంగా మార్చుతుంది. జాగ్రత్తగా విని, అది ఎంత సహజంగా ఉందో మీరే నిర్ణయించండి.")),
    dict(rank=16, code="tr", file="16_turkish_tr.wav", name_ru="турецкий",
         candidates=[("piper", "tr_TR-dfki-medium"), ("edge", "tr-TR-AhmetNeural")],
         text=("Merhaba! Bu, aynı sesin Türkçe örneğidir. Bir sinir ağı önce duyduğunuz her kelimeyi üretir, "
               "sonra özel bir model sesi hedef tınıya dönüştürür. Dikkatle dinleyin ve ne kadar doğal "
               "durduğuna kendiniz karar verin.")),
    dict(rank=17, code="ta", file="17_tamil_ta.wav", name_ru="тамильский",
         candidates=[("edge", "ta-IN-ValluvarNeural"), ("edge", "ta-IN-PallaviNeural"), ("espeak", "ta")],
         text=("வணக்கம்! இது அதே குரலின் தமிழ் மாதிரி. நரம்பியல் வலையமைப்பு முதலில் நீங்கள் கேட்கும் ஒவ்வொரு சொல்லையும் "
               "உருவாக்குகிறது, பின்னர் ஒரு சிறப்பு மாதிரி ஒலியை இலக்கு குரலாக மாற்றுகிறது. கவனமாகக் கேட்டு, "
               "அது எவ்வளவு இயல்பானது என்று நீங்களே முடிவு செய்யுங்கள்.")),
    dict(rank=18, code="vi", file="18_vietnamese_vi.wav", name_ru="вьетнамский",
         candidates=[("piper", "vi_VN-vais1000-medium"), ("edge", "vi-VN-NamMinhNeural")],
         text=("Xin chào! Đây là mẫu của cùng một giọng nói bằng tiếng Việt. "
               "Mạng nơ-ron tạo ra từng từ bạn nghe, sau đó một mô hình đặc biệt "
               "chuyển âm thanh sang giọng mục tiêu. Hãy lắng nghe kỹ và tự đánh "
               "giá xem nó có tự nhiên không.")),
    dict(rank=19, code="ko", file="19_korean_ko.wav", name_ru="корейский",
         candidates=[("edge", "ko-KR-InJoonNeural"), ("edge", "ko-KR-HyunsuNeural"), ("espeak", "ko")],
         text=("안녕하세요! 이것은 같은 음색으로 말하는 한국어 샘플입니다. 신경망이 먼저 여러분이 듣는 모든 단어를 생성하고, "
               "그다음 특별한 모델이 음성을 목표 음색으로 변환합니다. 잘 들어 보고 얼마나 자연스러운지 직접 판단해 보세요.")),
    dict(rank=20, code="sw", file="20_swahili_sw.wav", name_ru="суахили",
         candidates=[("piper", "sw_CD-lanfrica-medium"), ("espeak", "sw")],
         text=("Habari! Hii ni sampuli ya sauti ileile inayozungumza Kiswahili. "
               "Mtandao wa neva kwanza hutengeneza kila neno unalosikia, kisha "
               "mfumo maalum unabadilisha sauti kuwa sauti inayolengwa. Sikiliza "
               "kwa makini na uamue wewe mwenyewe kama inasikia kama asilia.")),
]

# piper voice -> подкаталог в rhasspy/piper-voices
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

ORDINALS = ["Первый", "Второй", "Третий", "Четвёртый", "Пятый", "Шестой",
            "Седьмой", "Восьмой", "Девятый", "Десятый", "Одиннадцатый",
            "Двенадцатый", "Тринадцатый", "Четырнадцатый", "Пятнадцатый",
            "Шестнадцатый", "Семнадцатый", "Восемнадцатый", "Девятнадцатый",
            "Двадцатый"]


def log(msg):
    print(msg, flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def dur(path):
    info = sf.info(path)
    return info.frames / info.samplerate


# ─────────────────────────── СКАЧИВАНИЕ PIPER-ГОЛОСОВ ───────────────────────────
def ensure_piper_voice(voice):
    onnx = os.path.join(PIPER_DIR, voice + ".onnx")
    conf = os.path.join(PIPER_DIR, voice + ".onnx.json")
    if os.path.exists(onnx) and os.path.getsize(onnx) > 1_000_000 \
            and os.path.exists(conf):
        return
    base = f"{HF_BASE}/{PIPER_URL_DIR[voice]}/{voice}"
    for attempt in (1, 2):
        try:
            subprocess.run(["curl", "-sL", "--fail", "-o", onnx, base + ".onnx"],
                           check=True, timeout=600)
            subprocess.run(["curl", "-sL", "--fail", "-o", conf, base + ".onnx.json"],
                           check=True, timeout=120)
            if os.path.getsize(onnx) > 1_000_000:
                log(f"  скачан {voice}: {os.path.getsize(onnx)} байт")
                return
        except Exception as e:
            log(f"  попытка {attempt} скачки {voice} не удалась: {e}")
            time.sleep(3)
    raise RuntimeError(f"не удалось скачать piper-голос {voice}")


# ─────────────────────────── СИНТЕЗ ───────────────────────────
def synth_piper(text, voice, out_wav, scale=None):
    cmd = [VENV, "-m", "piper",
           "-m", os.path.join(PIPER_DIR, voice + ".onnx"),
           "-c", os.path.join(PIPER_DIR, voice + ".onnx.json"),
           "-f", out_wav]
    if scale:
        cmd += ["--length_scale", str(scale)]
    subprocess.run(cmd, input=text.encode(), check=True, timeout=300)


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
                   check=True, timeout=180, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    os.remove(mp3)


def synth_espeak(text, code, out_wav):
    subprocess.run(["espeak-ng", "-v", code, "-s", "145", "-w", out_wav, text],
                   check=True, timeout=180)


def synthesize_with_control(text, engine, voice, raw_path):
    """Синтез с подгонкой длительности под окно 10-15 c. Возвращает (длительность, параметры)."""
    if engine == "piper":
        tried = []
        for sc in (None, 1.2, 1.4):
            synth_piper(text, voice, raw_path, scale=sc)
            d = dur(raw_path)
            tried.append(f"ls={sc}:{d:.1f}s")
            if d > MAX_D and sc is None:
                synth_piper(text, voice, raw_path, scale=0.9)
                d = dur(raw_path)
                tried.append(f"ls=0.9:{d:.1f}s")
                return d, {"engine": engine, "voice": voice,
                           "length_scale": 0.9, "attempts": tried}
            if MIN_D <= d <= MAX_D:
                return d, {"engine": engine, "voice": voice,
                           "length_scale": sc, "attempts": tried}
        return d, {"engine": engine, "voice": voice,
                   "length_scale": 1.4, "attempts": tried}
    if engine == "edge":
        tried = []
        for rt in (None, "-10%", "-18%"):
            synth_edge(text, voice, raw_path, rate=rt)
            d = dur(raw_path)
            tried.append(f"rate={rt}:{d:.1f}s")
            if d > MAX_D and rt is None:
                synth_edge(text, voice, raw_path, rate="+12%")
                d = dur(raw_path)
                tried.append(f"rate=+12%:{d:.1f}s")
                return d, {"engine": engine, "voice": voice,
                           "rate": "+12%", "attempts": tried}
            if MIN_D <= d <= MAX_D:
                return d, {"engine": engine, "voice": voice,
                           "rate": rt, "attempts": tried}
        return d, {"engine": engine, "voice": voice,
                   "rate": "-18%", "attempts": tried}
    # espeak-ng: аварийный синтез без управления скоростью
    synth_espeak(text, voice, raw_path)
    return dur(raw_path), {"engine": "espeak-ng", "voice": voice, "attempts": ["raw"]}


def fit_duration(path):
    """Обрезать до 15.0 c (с затуханием) или дополнить тишиной до 10.0 c."""
    y, sr = sf.read(path)
    n = len(y) / sr
    note = None
    if n > MAX_D:
        k = int(15.0 * sr)
        fade = int(0.12 * sr)
        y = y[:k].astype(np.float64)
        y[-fade:] *= np.linspace(1.0, 0.0, fade)
        note = f"обрезано с {n:.1f} до 15.0 c (fade 120 мс)"
        sf.write(path, y.astype(np.float32), sr)
        n = 15.0
    elif n < MIN_D:
        need = int(10.0 * sr) - len(y)
        y = np.concatenate([y, np.zeros(need)])
        note = f"тишина добавлена: речь {n:.1f} c, файл 10.0 c"
        sf.write(path, y.astype(np.float32), sr)
        n = 10.0
    return n, note


def to_mp3(wav_path, mp3_path):
    subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-b:a", "128k", "-ac", "1",
                    mp3_path], check=True, timeout=180,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ─────────────────────────── ОСНОВНОЙ ХОД ───────────────────────────
def main():
    t_all = time.time()
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(MP3_DIR, exist_ok=True)

    report = {"date": "2026-10-27",
              "task": "RUVSON timbre x 20 languages",
              "pipeline": ("нейтральный TTS (piper/edge-tts) -> OpenVoiceV2 "
                           "ToneColorConverter; референс — вокал трека 01"),
              "reference": REF_WAV,
              "reference_sha256": sha256(REF_WAV),
              "device": "cpu (2 cores / 4 GB RAM)",
              "duration_window_sec": [10.0, 15.0],
              "languages": {}}
    if os.path.exists(REPORT):  # чекпоинт для повторного запуска
        old = json.load(open(REPORT))
        if old.get("languages"):
            report["languages"] = old["languages"]

    # 1. Голоса piper
    log("== Шаг 1: piper-голоса ==")
    needed = sorted({v for L in LANGS for e, v in L["candidates"] if e == "piper"})
    for v in needed:
        ensure_piper_voice(v)

    # 2. OpenVoice
    log("== Шаг 2: OpenVoice V2 ==")
    import torch
    torch.set_num_threads(2)
    from openvoice.api import ToneColorConverter
    conv = ToneColorConverter(os.path.join(CKPT_DIR, "converter_config.json"),
                              device="cpu")
    conv.load_ckpt(os.path.join(CKPT_DIR, "converter_checkpoint.pth"))
    tgt_se = conv.extract_se(REF_WAV)
    tgt_v = tgt_se.squeeze().cpu().numpy().astype(np.float64)
    tgt_v = tgt_v / (np.linalg.norm(tgt_v) + 1e-12)

    def se_cos(path):
        v = conv.extract_se(path).squeeze().cpu().numpy().astype(np.float64)
        v = v / (np.linalg.norm(v) + 1e-12)
        return round(float(np.dot(v, tgt_v)), 4)

    # 3. Языки
    log("== Шаг 3: синтез и конверсия 20 языков ==")
    for L in LANGS:
        code, fname = L["code"], L["file"]
        done = report["languages"].get(code, {})
        out_path = os.path.join(OUT_DIR, fname)
        if done.get("status") == "ok" and os.path.exists(out_path):
            log(f"[{L['rank']:02d}/20] {code}: уже готово, пропуск")
            continue
        t0 = time.time()
        raw_path = os.path.join(RAW_DIR, fname.replace(".wav", "_raw.wav"))
        entry = {"rank": L["rank"], "name_ru": L["name_ru"], "text": L["text"]}
        try:
            last_err = None
            ok = False
            for engine, voice in L["candidates"]:
                try:
                    d0, params = synthesize_with_control(L["text"], engine, voice, raw_path)
                    ok = True
                    break
                except Exception as e:
                    last_err = f"{engine}:{voice}: {e}"
                    log(f"  [{code}] фолбэк после сбоя: {last_err}")
            if not ok:
                raise RuntimeError(f"все движки не сработали: {last_err}")
            entry.update(params)
            dfinal, note = fit_duration(raw_path)
            if note:
                entry["duration_note"] = note
            # конверсия тембра
            src_se = conv.extract_se(raw_path)
            conv.convert(audio_src_path=raw_path, src_se=src_se, tgt_se=tgt_se,
                         output_path=out_path)
            entry["se_cosine_raw_vs_ref"] = se_cos(raw_path)
            entry["se_cosine_output_vs_ref"] = se_cos(out_path)
            entry["duration_final_sec"] = round(dfinal, 2)
            entry["sample_rate"] = int(sf.info(out_path).samplerate)
            entry["sha256"] = sha256(out_path)
            entry["bytes"] = os.path.getsize(out_path)
            entry["status"] = "ok"
            entry["wall_sec"] = round(time.time() - t0, 1)
            log(f"[{L['rank']:02d}/20] {code} OK: {entry['engine']} {entry['voice']} "
                f"{dfinal:.1f}с se {entry['se_cosine_raw_vs_ref']}->"
                f"{entry['se_cosine_output_vs_ref']} за {entry['wall_sec']}с")
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)
            log(f"[{L['rank']:02d}/20] {code} FAIL: {e}")
        report["languages"][code] = entry
        json.dump(report, open(REPORT, "w"), ensure_ascii=False, indent=2)

    # 4. Превью с русскими анонсами (piper irina) + mp3 + README + zip
    log("== Шаг 4: превью / mp3 / README / zip ==")
    ann_cache = {}
    preview = []
    SR = 22500
    for L in LANGS:
        code, fname = L["code"], L["file"]
        out_path = os.path.join(OUT_DIR, fname)
        if not (report["languages"].get(code, {}).get("status") == "ok"
                and os.path.exists(out_path)):
            continue
        if code not in ann_cache:
            ann_path = os.path.join(RAW_DIR, f"_ann_{code}.wav")
            synth_piper(f"{ORDINALS[L['rank']-1]} язык — {L['name_ru']}.",
                        "ru_RU-irina-medium", ann_path)
            ann_cache[code] = ann_path
        ann, _ = librosa.load(ann_cache[code], sr=SR, mono=True)
        clip, _ = librosa.load(out_path, sr=SR, mono=True)
        peak = np.max(np.abs(clip)) + 1e-9
        clip = clip / peak * 0.84
        gap1 = np.zeros(int(0.35 * SR))
        gap2 = np.zeros(int(0.65 * SR))
        preview.extend([ann.astype(np.float32), gap1, clip.astype(np.float32), gap2])
    pv = np.concatenate(preview).astype(np.float32)
    pv_path = os.path.join(OUT_DIR, "preview_all_languages.wav")
    sf.write(pv_path, pv, SR)
    to_mp3(pv_path, os.path.join(OUT_DIR, "preview_all_languages.mp3"))
    log(f"превью: {len(pv)/SR:.1f} c")

    for L in LANGS:  # mp3-версии клипов
        out_path = os.path.join(OUT_DIR, L["file"])
        if os.path.exists(out_path):
            try:
                to_mp3(out_path, os.path.join(MP3_DIR, L["file"].replace(".wav", ".mp3")))
            except Exception as e:
                log(f"  mp3 fail {L['code']}: {e}")

    ok_n = sum(1 for e in report["languages"].values() if e.get("status") == "ok")
    report["summary"] = {
        "languages_ok": ok_n, "languages_total": len(LANGS),
        "engines": {e: sum(1 for x in report["languages"].values()
                           if x.get("engine") == e) for e in ("piper", "edge", "espeak-ng")},
        "total_wall_sec": round(time.time() - t_all, 1),
        "honesty": ("переносится ТОЛЬКО тембр (спектральная огибающая); высота тона и "
                    "интонация наследуются от базового TTS-голоса каждого языка; "
                    "арабский — модель kareem (иорданский арабский), текст — MSA; "
                    "испанский — латиноамериканский (es_MX); суахили включён по прямому "
                    "запросу владельца (в Ethnologue top-20 вместо него кантонский юэ); "
                    "демо-тексты написаны ассистентом, не носителем (возможны "
                    "шероховатости в ta/te/mr/bn/ur); прослушивание в песочнице "
                    "невозможно — вердикт по уху за владельцем; метрики — прокси "
                    "(SE-энкодер OpenVoice), WER по 20 языкам не считался: whisper-small "
                    "для te/ta/sw/bn ненадёжен."),
    }
    json.dump(report, open(REPORT, "w"), ensure_ascii=False, indent=2)

    readme = ["RUVSON voice — 20 языков (тембр × топ-20 языков мира)",
              "=" * 60, "",
              "Пайплайн: нейтральный TTS -> OpenVoice V2 ToneColorConverter",
              "Референс тембра: вокал трека 01 «Куда летят года» (htdemucs stem).",
              "Первый (русский) образец: релиз voice-result-20261027.", "",
              "Файлы 01–20 — клипы 10–15 c в тембре RUVSON.",
              "raw/ — речь ДО конверсии тембра (нейтральный TTS) для сравнения A/B.",
              "mp3/ — сжатые версии для телефона.",
              "preview_all_languages.mp3 — всё подряд с русскими анонсами («Первый язык — английский»).",
              "report_20langs.json — движок, длительности, SE-cosine, sha256 каждого файла.", "",
              "Движки по языкам:"]
    for L in LANGS:
        e = report["languages"].get(L["code"], {})
        eng = e.get("engine", "?")
        mdl = e.get("voice", "?")
        dst = e.get("duration_final_sec", "?")
        sec = e.get("se_cosine_output_vs_ref", "?")
        readme.append(f"  {L['rank']:02d}. {L['name_ru']} — {eng} ({mdl}), "
                      f"{dst} c, SE-cosine к референсу {sec}")
    readme += ["", "Честные оговорки:", "  " + report["summary"]["honesty"]]
    open(os.path.join(OUT_DIR, "README.txt"), "w", encoding="utf-8").write(
        "\n".join(readme) + "\n")

    if os.path.exists(ZIP_PATH):
        os.remove(ZIP_PATH)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(OUT_DIR):
            for f in sorted(files):
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, OUT_DIR))
    log(f"zip: {os.path.getsize(ZIP_PATH)} байт")
    log(f"ВСЁ ГОТОВО за {round(time.time()-t_all,1)} c; ok {ok_n}/20")


if __name__ == "__main__":
    main()
