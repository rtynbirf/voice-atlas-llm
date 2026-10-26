# Глава 19. Репозитории и первоисточники · Чек-лист запуска

Ссылки собраны по слоям конвейера; перед использованием проверяйте актуальную лицензию и статус поддержки на странице проекта. Для архивированных репозиториев (Seed-VC, so-vits-svc, Demucs) код и веса остаются доступными, но закладывайте форки.

## Репозитории

- **Seed-VC:** github.com/Plachtaa/seed-vc (архив 21.11.2025; модели — на Hugging Face: Plachtaa/seed-vc; лицензия GPL-3.0 — см. главу 20)
- **RVC:** github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI; форк Applio: github.com/IAHispano/Applio
- **so-vits-svc:** github.com/svc-develop-team/so-vits-svc (архив; живы форки 4.1/5.0)
- **F5-TTS:** github.com/SWivid/F5-TTS
- **GPT-SoVITS:** github.com/RVC-Boss/GPT-SoVITS
- **CosyVoice:** github.com/FunAudioLLM/CosyVoice (актуальный поток CosyVoice 3 — в орге QwenAudio)
- **Qwen3-TTS:** github.com/QwenLM/Qwen3-TTS (Apache-2.0; блог и technical report — на странице)
- **MOSS-TTS:** github.com/OpenMOSS/MOSS-TTS
- **XTTS-v2:** huggingface.co/coqui/XTTS-v2
- **StyleTTS 2:** github.com/yl4579/StyleTTS2
- **MegaTTS 3:** github.com/bytedance/MegaTTS3
- **MaskGCT / Amphion:** github.com/open-mmlab/Amphion
- **Fish Speech / OpenAudio:** github.com/fishaudio/fish-speech
- **Chatterbox:** github.com/resemble-ai/chatterbox
- **kNN-VC:** github.com/bshall/knn-vc; **OpenVoice:** github.com/myshell-ai/OpenVoice
- **DiffSinger:** github.com/MoonInTheRiver/DiffSinger; OpenUtau: github.com/stark81/OpenUtau (основной форк-экосистема)
- **basic-pitch:** github.com/spotify/basic-pitch
- **Сепарация:** github.com/facebookresearch/demucs (архив); BS/Mel-Band RoFormer — lucidrains/BS-RoFormer и ZFTurba/Music-Source-Separation-Training; витрина MVSep: mvsep.com; UVR5: github.com/Anjok07/ultimatevocalremovergui
- **Реставрация:** github.com/resemble-ai/resemble-enhance; DeepFilterNet: github.com/Rikorose/DeepFilterNet; AudioSR: github.com/haoheliu/AudioSR
- **Вокодеры:** github.com/NVIDIA/BigVGAN; Vocos: github.com/gemelo-ai/vocos
- **Эмбеддинги:** 3D-Speaker (CAMPPlus): github.com/modelscope/3D-Speaker; SpeechBrain (ECAPA): github.com/speechbrain/speechbrain; Resemblyzer: github.com/resemble-ai/Resemblyzer
- **Разметка:** WhisperX: github.com/m-bain/whisperX; MFA: github.com/MontrealCorpusTools/Montreal-Forced-Aligner; pyannote: github.com/pyannote/pyannote-audio; Silero VAD: github.com/snakers4/silero-vad
- **Защита:** AudioSeal: github.com/facebookresearch/audioseal; WavMark: github.com/wavmark/wavmark; AntiFake: antifake.net (проект защиты от несанкционированной записи голоса)

## Чек-лист запуска проекта

1. Согласие носителя голоса подписано до любой работы с записями (этап 1, глава 12).
2. Задача названа корректно: TTS / VC / SVC / SVS / персона текста (глава 2).
3. Мастер-набор оригинала сохранён read-only с SHA-256 (закон 1, глава 13).
4. Референс соответствует стандарту: моно, 44.1/48 кГц, SNR ≥ 35 дБ (глава 4).
5. Лицензии кода, весов и датасетов проверены по актуальным редакциям (глава 17, глава 20).
6. Выбран стек по лестнице: zero-shot → few-shot файнтюн → персональная модель (главы 6–7).
7. Hold-out 10% отделён до начала обучения; раннее расширение запрещено (этап 6).
8. Гейт качества настроен: SIM, WER, UTMOS, для пения F0 COR/RCA (глава 11); пороги откалиброваны по паре «оригинал vs второй дубль».
9. Слепой CMOS с 10+ слушателями проведён на финальных кандидатах (глава 11).
10. Вотермарк/маркировка синтетики включены; C2PA-происхождение записано (глава 17).
11. Версии копии живут в ветках с возможностью отката; рубильник носителя работает (закон 7).
