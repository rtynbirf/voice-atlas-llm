# Глава 18. Глоссарий

**Таблица 24. Аббревиатуры и термины**

| Термин | Расшифровка | Суть |
|---|---|---|
| TTS | Text-to-Speech | Синтез речи из текста |
| VC | Voice Conversion | Перекраска тембра готовой речи |
| SVC | Singing Voice Conversion | Перекраска тембра готового пения |
| SVS | Singing Voice Synthesis | Синтез вокала из текста и мелодии |
| SSL | Self-Supervised Learning | Обучение без разметки; источник контент-энкодеров |
| F0 | Fundamental frequency | Частота основного тона — «высота голоса» |
| CFM | Conditional Flow Matching | Обучение генератора «потоком»; быстрее диффузии |
| DiT | Diffusion Transformer | Трансформер-диффузия (U-DiT в Seed-VC) |
| AR | Autoregressive | Пошаговая генерация токенов (GPT-стиль) |
| RVQ | Residual Vector Quantization | Многоуровневое квантование в кодеках |
| SIM/SECS | Speaker Embedding Cosine Similarity | Метрика сходства голосов |
| WER/CER | Word/Character Error Rate | Ошибка распознавания — метрика разборчивости |
| MOS/CMOS | Mean/Comparison MOS | Субъективная оценка людьми |
| VAD | Voice Activity Detection | Детекция речи и тишины |
| FAISS | Facebook AI Similarity Search | Поиск ближайших соседей (индекс тембра в RVC) |
| LoRA/QLoRA | Low-Rank Adaptation (Quantized) | Адаптер-файнтюн малой доли параметров |
| DPO | Direct Preference Optimization | Выравнивание по предпочтениям без reward-модели |
| RAG | Retrieval-Augmented Generation | Генерация с подглядыванием в базу данных |
| Timbre leakage | Утечка тембра | Просачивание голоса источника в контент-фичи |
| Timbre shifter | Сдвигатель тембра | Внешнее перекрашивание при обучении против утечки |
| Голосбанк | Voicebank | Персональная модель пения (DiffSinger) |
| Вотермарк | Watermark | Невидимая метка синтетики в аудио |
| C2PA | Coalition for Content Provenance and Authenticity | Стандарт метаданных происхождения медиа |
| Дизентанглмент | Disentanglement | Разъятие сигнала на независимые управляемые слои |
