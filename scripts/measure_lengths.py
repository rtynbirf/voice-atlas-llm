# -*- coding: utf-8 -*-
"""Измерение реальных длин обучающих пар (токены Qwen) для выбора max_len."""
import json
import sys
from pathlib import Path

ROOT = Path("/home/z/my-project/voice-atlas-llm")
sys.path.insert(0, str(ROOT))
from transformers import AutoTokenizer
from training.prompt_format import build_training_pair

tok = AutoTokenizer.from_pretrained(str(ROOT / "models/_base/Qwen2.5-0.5B-Instruct"))
system = (ROOT / "data/curated/system_prompt.txt").read_text(encoding="utf-8")
sys_len = len(tok(system, add_special_tokens=False)["input_ids"])
print(f"system_prompt: {sys_len} токенов")

lens = []
for split in ["train", "val"]:
    rows = [json.loads(l) for l in (ROOT / f"data/dataset/{split}.jsonl").open(encoding="utf-8") if l.strip()]
    sl = []
    for r in rows:
        p, a = build_training_pair(system, r["instruction"], r["output"])
        n = len(tok(p, add_special_tokens=False)["input_ids"]) + len(tok(a, add_special_tokens=False)["input_ids"]) + 1
        sl.append(n)
    sl.sort()
    lens.append((split, sl))
    n = len(sl)
    print(f"{split}: n={n} min={sl[0]} p50={sl[n//2]} p90={sl[int(n*0.9)]} p99={sl[min(n-1,int(n*0.99))]} max={sl[-1]}")
