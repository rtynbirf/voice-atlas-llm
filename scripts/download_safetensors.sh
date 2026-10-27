#!/usr/bin/env bash
# Докачка model.safetensors с resume (-C -) и автоповторами.
set -u
DEST=/home/z/my-project/voice-atlas-llm/models/_base/Qwen2.5-0.5B-Instruct
mkdir -p "$DEST"
URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/main/model.safetensors"
TARGET=988062536  # точный размер model.safetensors Qwen2.5-0.5B-Instruct
for attempt in 1 2 3 4 5 6 7 8; do
    SZ=$(stat -c%s "$DEST/model.safetensors" 2>/dev/null || echo 0)
    echo "$(date +%H:%M:%S) attempt=$attempt from=$((SZ/1024/1024))MB"
    if [ "$SZ" -ge "$TARGET" ]; then echo "DONE size=$SZ"; exit 0; fi
    curl -sL -C - --retry 3 --retry-delay 2 --max-time 3600 -o "$DEST/model.safetensors" "$URL"
    RC=$?
    echo "$(date +%H:%M:%S) curl rc=$RC size=$(stat -c%s "$DEST/model.safetensors" 2>/dev/null || echo 0)"
done
echo "DONE size=$(stat -c%s "$DEST/model.safetensors" 2>/dev/null || echo 0)"
