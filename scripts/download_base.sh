#!/usr/bin/env bash
# Загрузка базовой модели Qwen2.5-0.5B-Instruct (954 МБ) прямым curl.
set -u
DEST=/home/z/my-project/voice-atlas-llm/models/_base/Qwen2.5-0.5B-Instruct
mkdir -p "$DEST"
BASE="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/main"
for f in config.json generation_config.json merges.txt tokenizer.json tokenizer_config.json vocab.json; do
    curl -sL --retry 3 -o "$DEST/$f" "$BASE/$f" &
done
wait
echo "$(date +%H:%M:%S) мелкие файлы готовы, качаю model.safetensors..."
curl -sL --retry 3 -o "$DEST/model.safetensors" "$BASE/model.safetensors" && \
    echo "$(date +%H:%M:%S) DONE" && ls -la "$DEST"
