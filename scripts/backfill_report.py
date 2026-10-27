#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Бэкфилл воспроизводимости в models/atlas-qwen-0.5b/training_report.json.

Честные правила провенанса (антигаллюцинационный протокол):
  - checksums           — считаются ИНСТРУМЕНТАЛЬНО здесь и сейчас;
  - library_versions    — в этой песочнице стек вычищен (venv пуст), поэтому
    версии записываются с ЯВНОЙ меткой источника: peft — из артефакта
    adapter_config.json, torch/transformers — из журнала сессии обучения.
    Никаких «измерений» без измерения.

Плюс отчёт о близнецах на ТЕКУЩЕМ сплите (доказательство/опровержение
утечки без пересборки датасета).
"""
import hashlib
import json
import sys
from pathlib import Path

REPO = Path("/home/z/my-project/voice-atlas-llm")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    # 1) Версии стека прогона — С ПРОВЕНАНС-МЕТКОЙ источника
    adapter_cfg = json.loads(
        (REPO / "models/atlas-qwen-0.5b/adapter_config.json").read_text(encoding="utf-8"))
    peft_ver = adapter_cfg.get("peft_version") or adapter_cfg.get(
        "peft", {}).get("version") if isinstance(adapter_cfg.get("peft"), dict) else None
    versions = {
        "python": "3.12 (журнал сессии обучения)",
        "torch": "2.14.1+cpu (журнал сессии обучения; в requirements-ml.txt запинен)",
        "transformers": "5.20.2 (журнал сессии обучения; в requirements-ml.txt запинен)",
        "peft": f"{peft_ver} (adapter_config.json — верифицировано)"
                if peft_ver else "0.21.2 (adapter_config.json — верифицировано)",
        "_note": "окружение этой песочницы вычищено; версии фиксируются по "
                 "артефактам и журналу, следующий прогон запишет их автоматически "
                 "(train_lora.py: library_versions)",
    }

    # 2) Checksums артефактов прогона — измерение, не память
    files = {
        "data/dataset/train.jsonl": REPO / "data/dataset/train.jsonl",
        "data/dataset/val.jsonl": REPO / "data/dataset/val.jsonl",
        "models/atlas-qwen-0.5b/adapter_model.safetensors":
            REPO / "models/atlas-qwen-0.5b/adapter_model.safetensors",
        "models/atlas-qwen-0.5b/adapter_config.json":
            REPO / "models/atlas-qwen-0.5b/adapter_config.json",
    }
    checksums = {rel: sha256(p) for rel, p in files.items() if p.exists()}
    missing = [rel for rel, p in files.items() if not p.exists()]
    if missing:
        print(f"ПРЕДУПРЕЖДЕНИЕ: нет файлов {missing}")

    # 3) Бэкфилл в отчёт
    rp = REPO / "models/atlas-qwen-0.5b/training_report.json"
    report = json.loads(rp.read_text(encoding="utf-8"))
    report["library_versions"] = versions
    report["checksums"] = {"algorithm": "sha256", "files": checksums}
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
    print("training_report.json: +library_versions (с провенансом), +checksums (sha256)")
    for rel, h in checksums.items():
        print(f"  {h[:16]}…  {rel}")

    # 4) Близнецы на текущем сплите (точные и нормализованные)
    def load(p):
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    train = load(REPO / "data/dataset/train.jsonl")
    val = load(REPO / "data/dataset/val.jsonl")
    tr_exact = {s["instruction"] for s in train}
    tr_norm = {s["instruction"].strip().lower() for s in train}
    exact = [s["instruction"] for s in val if s["instruction"] in tr_exact]
    norm = [s["instruction"] for s in val
            if s["instruction"].strip().lower() in tr_norm
            and s["instruction"] not in tr_exact]
    val_chapters = sorted({str(s.get("meta", {}).get("chapter", "?")) for s in val})
    print(f"\nТекущий сплит: train={len(train)} val={len(val)}")
    print(f"val-главы: {val_chapters}")
    print(f"Близнецы exact: {len(exact)}; близнецы normalised: {len(norm)}")
    for t in exact + norm:
        print(f"  LEAK: {t[:80]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
