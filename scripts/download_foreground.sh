#!/usr/bin/env bash
# Синхронная докачка safetensors: цикл curl -C - с max-time 100 c на попытку.
# Вызывается многократно; каждый вызов докачивает сколько успеет за бюджет.
set -u
DEST=/home/z/my-project/voice-atlas-llm/models/_base/Qwen2.5-0.5B-Instruct
URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/main/model.safetensors"
TARGET=988062536
END=$(($(date +%s) + 560))  # бюджет вызова ~9.3 мин
while [ "$(date +%s)" -lt "$END" ]; do
    SZ=$(stat -c%s "$DEST/model.safetensors" 2>/dev/null || echo 0)
    if [ "$SZ" -ge "$TARGET" ]; then echo "COMPLETE size=$SZ"; exit 0; fi
    echo "$(date +%H:%M:%S) resume from=$((SZ/1024/1024))MB"
    curl -sL -C - --max-time 100 -o "$DEST/model.safetensors" "$URL" || true
done
SZ=$(stat -c%s "$DEST/model.safetensors" 2>/dev/null || echo 0)
echo "budget end, size=$((SZ/1024/1024))MB"
