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
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
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

    def __init__(self, rows: list[dict], tokenizer, system: str, max_len: int,
                 drop_long: bool = False):
        self.examples = []
        eos = tokenizer.eos_token_id
        tail = [eos] if eos is not None else []
        dropped = 0
        for row in rows:
            prompt_text, answer_text = build_training_pair(
                system, row["instruction"], row["output"])
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
            ans = tokenizer(answer_text, add_special_tokens=False)["input_ids"] + tail
            # Ответ должен поместиться целиком: промпт режем СЛЕВА.
            max_prompt = max_len - len(ans)
            if max_prompt <= 0:
                if drop_long:
                    dropped += 1
                    continue
                raise ValueError(
                    f"answer длиннее max_len ({len(ans)} > {max_len}); "
                    "увеличь max_len в конфиге или включи drop_long")
            if len(prompt_ids) > max_prompt:
                prompt_ids = prompt_ids[-max_prompt:]
            input_ids = prompt_ids + ans
            labels = [-100] * len(prompt_ids) + ans
            if all(l == -100 for l in labels):
                raise ValueError("пример без обучающих токенов")
            self.examples.append({"input_ids": input_ids, "labels": labels})
        if dropped:
            print(f"[data] drop_long: выброшено {dropped} примеров "
                  f"длиннее max_len={max_len} (громко, не молча)")

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


_CE_CHUNK = 64  # токенов на чанк lm_head+CE: live-логиты только одного чанка


def _chunk_ce(base, h_chunk: torch.Tensor, t_chunk: torch.Tensor) -> torch.Tensor:
    logits = base.lm_head(h_chunk).float()
    return F.cross_entropy(logits, t_chunk, reduction="sum")


def masked_lm_loss(model, batch: dict, device: str) -> torch.Tensor:
    """CE только на позициях ответа + чанкинг lm_head (memory-efficient SFT).

    1) Полный тензор логитов [B x seq x 152k] не материализуется никогда:
       lm_head вызывается точечно на сдвинутых позициях, где labels != -100.
       Математически эквивалентно стандартному CE с ignore_index=-100.
    2) Ответ дополнительно режется на чанки по _CE_CHUNK токенов; каждый чанк
       обёрнут в torch.utils.checkpoint(use_reentrant=False) — в backward
       логиты чанка рекомпутируются, поэтому в памяти живёт только ОДИН чанк
       (~140 МБ при чанке 64) независимо от длины ответа. Сумма CE по чанкам
       / N эквивалентна усреднённому CE по всем ответным токенам.
    LoRA-слои активны, т.к. живут внутри декодерных блоков базовой модели.
    """
    base = model.get_base_model()  # Qwen2ForCausalLM / GPT2LMHeadModel; LoRA активна
    # Бэкбон по семейству: Qwen2 -> .model, GPT2 -> .transformer (smoke-модель)
    backbone = getattr(base, "model", None) or base.transformer
    out = backbone(
        input_ids=batch["input_ids"].to(device),
        attention_mask=batch["attention_mask"].to(device),
        use_cache=False,
    )
    h = out.last_hidden_state[:, :-1, :]          # [B, T-1, H]
    targets = batch["labels"][:, 1:].to(device)   # [B, T-1]
    mask = targets != -100
    sel_h = h[mask]                               # [N, H] — только ответ
    sel_t = targets[mask]                         # [N]
    from torch.utils.checkpoint import checkpoint
    total = sel_t.new_zeros((), dtype=torch.float32)
    for i in range(0, sel_t.numel(), _CE_CHUNK):
        total = total + checkpoint(
            _chunk_ce, base, sel_h[i:i + _CE_CHUNK], sel_t[i:i + _CE_CHUNK],
            use_reentrant=False)
    return total / sel_t.numel()


@torch.no_grad()
def eval_loss(model, loader: DataLoader, device: str) -> float:
    model.eval()
    total, ntok = 0.0, 0
    for batch in loader:
        n = (batch["labels"] != -100).sum().item()
        total += masked_lm_loss(model, batch, device).item() * n
        ntok += n
    model.train()
    return total / max(ntok, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--limit", type=int, default=None,
                    help="ограничить число train/val примеров (proof-run на CPU)")
    ap.add_argument("--resume", action="store_true",
                    help="продолжить из resume_state.pt в output_dir, если есть")
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="окно чанка: сохранить чекпоинт и чисто выйти по истечении")
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
    if cfg.get("gradient_checkpointing", False):
        # Явно use_reentrant=False: при reentrant-варианте чекпоинтинг с
        # замороженными эмбеддингами (LoRA не трогает embed_tokens) разрывает
        # градиентный поток — лосс не падает. False-вариант градиенты сохраняет.
        try:
            model.gradient_checkpointing_enable(
                gradient_checkpointing_kwargs={"use_reentrant": False})
            print("[train] gradient checkpointing: use_reentrant=False")
        except TypeError:
            model.enable_gradient_checkpointing()
            print("[train] gradient checkpointing: legacy API")
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
    train_ds = SFTDataset(train_rows, tokenizer, system, cfg["max_len"],
                          drop_long=bool(cfg.get("data", {}).get("drop_long", False)))
    val_ds = SFTDataset(val_rows, tokenizer, system, cfg["max_len"],
                        drop_long=bool(cfg.get("data", {}).get("drop_long", False)))
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

    history = {"train_loss": [], "val_loss": [], "lr": [], "elapsed_sec": 0.0}
    t0 = time.time()
    chunk_t0 = time.time()
    gstep, running = 0, 0.0
    start_epoch, start_bidx = 1, 0

    # --- РЕЗЮМ: песочница косит фоновые процессы после каждого вызова, поэтому
    # обучение идёт форграундными окнами (--max-minutes), состояние — в resume_state.pt
    train_params = {k for k, p in model.named_parameters() if p.requires_grad}

    def _save_resume(epoch: int, bidx: int) -> None:
        torch.save({
            "lora": {k: v.detach().cpu().clone()
                     for k, v in model.state_dict().items() if k in train_params},
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "torch_rng": torch.get_rng_state(),
            "py_rng": random.getstate(),
            "gstep": gstep, "running": running,
            "epoch": epoch, "bidx": bidx,
            "history": history,
            "elapsed_sec": history.get("elapsed_sec", 0.0) + (time.time() - t0),
        }, out_dir / "resume_state.pt")

    if args.resume:
        rs_path = out_dir / "resume_state.pt"
        if rs_path.exists():
            rs = torch.load(rs_path, map_location="cpu", weights_only=False)
            model.load_state_dict(rs["lora"], strict=False)
            optimizer.load_state_dict(rs["optimizer"])
            scheduler.load_state_dict(rs["scheduler"])
            torch.set_rng_state(rs["torch_rng"])
            random.setstate(rs["py_rng"])
            gstep, running = rs["gstep"], rs["running"]
            start_epoch, start_bidx = rs["epoch"], rs["bidx"]
            history = rs["history"]
            history["elapsed_sec"] = rs["elapsed_sec"]  # накопленное время всех чанков
            print(f"[resume] gstep={gstep}/{total_steps} epoch={start_epoch} "
                  f"bidx={start_bidx} elapsed={history.get('elapsed_sec', 0):.0f}s")
        else:
            print("[resume] состояния нет — старт с нуля")

    for epoch in range(start_epoch, tcfg["epochs"] + 1):
        # детерминизм: перестановка эпохи из отдельного генератора (seed*1000+epoch),
        # резюм продолжает с индекса bidx без пропуска forward-проходов
        gdata = torch.Generator()
        gdata.manual_seed(cfg.get("seed", 42) * 1000 + epoch)
        perm = torch.randperm(len(train_ds), generator=gdata).tolist()
        n = len(perm)
        i = start_bidx if epoch == start_epoch else 0
        while i < n:
            batch = coll([train_ds[perm[i]]])
            i += 1
            loss = masked_lm_loss(model, batch, device) / tcfg["grad_accum"]
            loss.backward()
            running += loss.item()
            if i % tcfg["grad_accum"] == 0 or i == n:
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
                    el = history.get("elapsed_sec", 0.0) + (time.time() - t0)
                    print(f"[step {gstep}/{total_steps}] loss={running:.4f} "
                          f"lr={scheduler.get_last_lr()[0]:.2e} elapsed={el:.0f}s")
                running = 0.0
                if args.max_minutes and (time.time() - chunk_t0) > args.max_minutes * 60:
                    _save_resume(epoch, i)
                    print(f"[chunk] окно {args.max_minutes} мин: чекпоинт "
                          f"gstep={gstep} epoch={epoch} bidx={i} сохранён, чистый выход")
                    return 0
        start_bidx = 0
        vl = eval_loss(model, val_loader, device)
        history["val_loss"].append({"epoch": epoch, "loss": vl})
        print(f"[epoch {epoch}] val_loss={vl:.4f}")
        if args.max_minutes and epoch < tcfg["epochs"] \
                and (time.time() - chunk_t0) > args.max_minutes * 60:
            _save_resume(epoch + 1, 0)
            print(f"[chunk] окно {args.max_minutes} мин: эпоха {epoch} закрыта, "
                  f"чекпоинт сохранён, чистый выход")
            return 0

    print(f"[train] save adapter -> {out_dir}")
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    (out_dir / "system_prompt.txt").write_text(
        (ROOT / cfg["system_prompt_file"]).read_text(encoding="utf-8"), encoding="utf-8")
    # Воспроизводимость (ROADMAP_v2 фаза 0.1/0.2): версии стека и sha256
    # артефактов пишутся автоматически, а не восстанавливаются по памяти.
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    versions = {"python": sys.version.split()[0]}
    try:
        import peft  # noqa: E402
        import transformers  # noqa: E402
        versions.update({
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "peft": peft.__version__,
        })
    except Exception as e:  # версии не должны ронять отчёт
        versions["error"] = repr(e)

    checksums = {}
    for rel in (cfg["data"]["train"], cfg["data"]["val"]):
        p = ROOT / rel
        if p.exists():
            checksums[rel] = _sha256(p)
    adapter_file = out_dir / "adapter_model.safetensors"
    if adapter_file.exists():
        checksums[f"{out_dir.name}/adapter_model.safetensors"] = _sha256(adapter_file)

    report = {
        "base_model": base_model,
        "config": cfg,
        "device": device,
        "trainable_params": trainable,
        "total_params": total,
        "train_examples": len(train_ds),
        "val_examples": len(val_ds),
        "elapsed_sec": round(history.get("elapsed_sec", 0.0) + (time.time() - t0), 1),
        "library_versions": versions,
        "checksums": {"algorithm": "sha256", "files": checksums},
        "history": history,
    }
    (out_dir / "training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[train] done in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
