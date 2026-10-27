#!/usr/bin/env bash
# Пост-пайплайн полного обучения: верификация адаптера -> eval val -> демо-генерации.
# Запускается ПОСЛЕ завершения train_lora.py (память освобождена).
set -u
REPO=/home/z/my-project/voice-atlas-llm
cd "$REPO"
export MALLOC_ARENA_MAX=2 MALLOC_MMAP_THRESHOLD_=131072 OMP_NUM_THREADS=2
BASE=models/_base/Qwen2.5-0.5B-Instruct
ADAPTER=models/atlas-qwen-0.5b

echo "=== 1. Артефакты обучения ==="
ls -la "$ADAPTER"
python3.13 - "$ADAPTER/training_report.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
h = r["history"]
print("device:", r["device"], "| elapsed:", r["elapsed_sec"], "s")
print("train:", r["train_examples"], "val:", r["val_examples"], "| trainable:", round(r["trainable_params"]/1e6, 2), "M")
print("val_loss by epoch:", [round(e["loss"], 4) for e in h["val_loss"]])
print("first/last train step loss:", round(h["train_loss"][0], 4), "/", round(h["train_loss"][-1], 4))
PY

echo "=== 2. Eval на held-out val (9 вопросов, генерация) ==="
python3.13 evaluation/eval_qa.py --adapter "$ADAPTER" --base "$BASE" \
    --max-samples 9 --max-new-tokens 220 --out evaluation/report_full.json 2>&1 \
    | grep -Ev "Warning|Loading|torch_dtype|unauthenticated" | tail -12

echo "=== 3. Демо-генерации (3 вопроса) ==="
for Q in "чем SVC отличается от SVS?" "какие пороги SIM считаются хорошими?" "какие вокодеры подходят для пения?"; do
    echo "--- Вопрос: $Q"
    python3.13 inference/chat_cli.py --base "$BASE" --adapter "$ADAPTER" --max-new-tokens 220 "$Q" 2>&1 \
        | grep -Ev "Warning|Loading|torch_dtype|unauthenticated" | tail -14
done
echo "=== POST-PIPELINE DONE ==="
