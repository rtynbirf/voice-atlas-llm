# -*- coding: utf-8 -*-
"""Слияние LoRA-адаптера с базовой моделью -> самостоятельная модель.

    python training/merge_lora.py --base Qwen/Qwen2.5-0.5B-Instruct \
        --adapter models/atlas-qwen-0.5b --out models/atlas-qwen-0.5b-merged
"""
import argparse
import sys
from pathlib import Path

import torch


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"[merge] base: {args.base}")
    model = AutoModelForCausalLM.from_pretrained(
        args.base, torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32)
    model = PeftModel.from_pretrained(model, args.adapter)
    print("[merge] merge_and_unload ...")
    model = model.merge_and_unload()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok = AutoTokenizer.from_pretrained(args.adapter)
    tok.save_pretrained(out)
    print(f"[merge] saved -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
