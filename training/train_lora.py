# -*- coding: utf-8 -*-
"""
LoRA/QLoRA файнтюн Атлас-LLM на корпусе атласа клонирования голоса.

Работает на GPU (bf16) и CPU (fp32, smoke-режим). Зависимости:
torch, transformers, peft, pyyaml. TRL не используется — ручной цикл
устойчив к версиям.

Запуск (полное обучение, RTX 3060 12 ГБ):
    python training/train_lora.py --config training/configs/qwen2.5-0.5b-ru.yaml

Smoke-прогон на CPU (модель 8 МБ, проверка пайплайна):
    python training/train_lora.py --config training/configs/smoke-tiny.yaml
"""
import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from training.prompt_format import build_training_pair  # noqa: E402


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class SFTDataset(Dataset):
    """Токенизированные пары с маской лосса: лосс только на ответе."""

    def __init__(self, rows: list[dict], tokenizer, system: str, max_len: int):
        self.examples = []
        eos = tokenizer.eos_token_id
        tail = [eos] if eos is not None else []
        for row in rows:
            prompt_text, answer_text = build_training_pair(
                system, row["instruction"], row["output"])
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
            ans = tokenizer(answer_text, add_special_tokens=False)["input_ids"] + tail
            # Ответ должен поместиться целиком: промпт режем СЛЕВА.
            max_prompt = max_len - len(ans)
            if max_prompt <= 0:
                raise ValueError(
                    f"answer длиннее max_len ({len(ans)} > {max_len}); "
                    "увеличь max_len в конфиге")
            if len(prompt_ids) > max_prompt:
                prompt_ids = prompt_ids[-max_prompt:]
            input_ids = prompt_ids + ans
            labels = [-100] * len(prompt_ids) + ans
            if all(l == -100 for l in labels):
                raise ValueError("пример без обучающих токенов")
            self.examples.append({"input_ids": input_ids, "labels": labels})

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        return self.examples[idx]


def collate(batch: list[dict], pad_id: int) -> dict:
    max_len = max(len(b["input_ids"]) for b in batch)
    input_ids, labels, attn = [], [], []
    for b in batch:
        n = len(b["input_ids"])
        pad = max_len - n
        input_ids.append(b["input_ids"] + [pad_id] * pad)
        labels.append(b["labels"] + [-100] * pad)
        attn.append([1] * n + [0] * pad)
    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.long),
        "attention_mask": torch.tensor(attn, dtype=torch.long),
    }


@torch.no_grad()
def eval_loss(model, loader: DataLoader, device: str) -> float:
    model.eval()
    total, ntok = 0.0, 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        out = model(**batch)
        n = (batch["labels"] != -100).sum().item()
        total += out.loss.item() * n
        ntok += n
    model.train()
    return total / max(ntok, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--limit", type=int, default=None,
                    help="ограничить число train/val примеров (proof-run на CPU)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    set_seed(cfg.get("seed", 42))
    out_dir = ROOT / cfg["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if (cfg.get("allow_gpu", True) and torch.cuda.is_available()) else "cpu"
    bf16 = cfg.get("bf16", True) and device == "cuda" and torch.cuda.is_bf16_supported()
    if device == "cpu":
        torch.set_num_threads(os.cpu_count() or 4)
    print(f"[train] device={device} bf16={bf16}")

    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model

    base_model = cfg["base_model"]
    print(f"[train] tokenizer: {base_model}")
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[train] model: {base_model}")
    dtype = torch.bfloat16 if bf16 else torch.float32
    # CPU-proof режим: грузим веса в bfloat16, чтобы уложиться в малую RAM.
    if device == "cpu" and cfg.get("load_dtype_cpu", "float32") == "bfloat16":
        dtype = torch.bfloat16
        print("[train] CPU: веса в bfloat16 (экономия RAM)")
    model = AutoModelForCausalLM.from_pretrained(
        base_model, torch_dtype=dtype, trust_remote_code=True)
    model.to(device)

    lora_cfg = LoraConfig(
        r=cfg["lora"]["r"],
        lora_alpha=cfg["lora"]["alpha"],
        lora_dropout=cfg["lora"]["dropout"],
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=cfg["lora"]["target_modules"],
    )
    model = get_peft_model(model, lora_cfg)
    model.train()
    if cfg.get("gradient_checkpointing", False) and hasattr(model, "enable_gradient_checkpointing"):
        model.enable_gradient_checkpointing()
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"[train] LoRA trainable {trainable/1e6:.2f}M / total {total/1e6:.2f}M "
          f"({100*trainable/total:.2f}%)")

    system = (ROOT / cfg["system_prompt_file"]).read_text(encoding="utf-8")
    train_rows = load_jsonl(ROOT / cfg["data"]["train"])
    val_rows = load_jsonl(ROOT / cfg["data"]["val"])
    if args.limit:
        train_rows = train_rows[: args.limit]
        val_rows = val_rows[: max(1, args.limit // 8)]
    tcfg = cfg["training"]
    train_ds = SFTDataset(train_rows, tokenizer, system, cfg["max_len"])
    val_ds = SFTDataset(val_rows, tokenizer, system, cfg["max_len"])
    pad_id = tokenizer.pad_token_id
    coll = lambda b: collate(b, pad_id)
    train_loader = DataLoader(train_ds, batch_size=tcfg["batch_size"], shuffle=True,
                              collate_fn=coll, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=tcfg["batch_size"], shuffle=False,
                            collate_fn=coll)
    print(f"[train] examples: train={len(train_ds)} val={len(val_ds)}")

    steps_per_epoch = math.ceil(len(train_loader) / tcfg["grad_accum"])
    total_steps = steps_per_epoch * tcfg["epochs"]
    warmup = max(1, int(total_steps * tcfg.get("warmup_frac", 0.06)))
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=tcfg["lr"], weight_decay=tcfg.get("weight_decay", 0.0))
    from transformers import get_cosine_schedule_with_warmup
    scheduler = get_cosine_schedule_with_warmup(optimizer, warmup, total_steps)

    history = {"train_loss": [], "val_loss": [], "lr": []}
    t0 = time.time()
    gstep, running = 0, 0.0
    for epoch in range(1, tcfg["epochs"] + 1):
        for i, batch in enumerate(train_loader, 1):
            batch = {k: v.to(device) for k, v in batch.items()}
            loss = model(**batch).loss / tcfg["grad_accum"]
            loss.backward()
            running += loss.item()
            if i % tcfg["grad_accum"] == 0 or i == len(train_loader):
                torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad],
                    tcfg.get("max_grad_norm", 1.0))
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                gstep += 1
                history["train_loss"].append(running)
                history["lr"].append(scheduler.get_last_lr()[0])
                if gstep % tcfg.get("log_every", 10) == 0:
                    el = time.time() - t0
                    print(f"[step {gstep}/{total_steps}] loss={running:.4f} "
                          f"lr={scheduler.get_last_lr()[0]:.2e} elapsed={el:.0f}s")
                running = 0.0
        vl = eval_loss(model, val_loader, device)
        history["val_loss"].append({"epoch": epoch, "loss": vl})
        print(f"[epoch {epoch}] val_loss={vl:.4f}")

    print(f"[train] save adapter -> {out_dir}")
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    (out_dir / "system_prompt.txt").write_text(
        (ROOT / cfg["system_prompt_file"]).read_text(encoding="utf-8"), encoding="utf-8")
    report = {
        "base_model": base_model,
        "config": cfg,
        "device": device,
        "trainable_params": trainable,
        "total_params": total,
        "train_examples": len(train_ds),
        "val_examples": len(val_ds),
        "elapsed_sec": round(time.time() - t0, 1),
        "history": history,
    }
    (out_dir / "training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[train] done in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
