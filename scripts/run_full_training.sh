#!/usr/bin/env bash
# Запуск полного обучения Атлас-LLM на CPU-хосте (2 ядра / 4 ГБ RAM).
# MALLOC_ARENA_MAX=2 и MALLOC_MMAP_THRESHOLD_ — гигиена памяти (проверено:
# без них фрагментация арен glibc добавляет ~0.5 ГБ RSS).
# Интерпретатор: python3.13 (в песочнице venv-python 3.12 без ML-стека).
set -u
REPO=/home/z/my-project/voice-atlas-llm
LOG_DIR="$REPO/training/logs"
mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/full_cpu_$TS.log"
export MALLOC_ARENA_MAX=2
export MALLOC_MMAP_THRESHOLD_=131072
export OMP_NUM_THREADS=2
cd "$REPO"
nohup python3.13 training/train_lora.py --config training/configs/qwen2.5-0.5b-ru-cpu.yaml \
    > "$LOG" 2>&1 &
PID=$!
echo "$PID" > "$LOG_DIR/full_cpu.pid"
echo "PID=$PID"
echo "LOG=$LOG"
