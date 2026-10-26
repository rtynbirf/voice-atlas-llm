#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборщик обучающего датасета Атлас-LLM.

Собирает датасет инструкций (instruction-tuning) из двух источников:
  1. Кураторские QA-пары: data/curated/qa_part*.jsonl
  2. Автогенерация из глоссария атласа: data/atlas/18_glossary.md
     (таблица терминов -> пары «Что такое X?» / определение)

Валидация: непустые поля, минимальная длина ответа, кириллица,
дедупликация по instruction, чистый train/val сплит.

Запуск:
    python data/build_dataset.py [--seed 42] [--val-frac 0.06]

Выход:
    data/dataset/train.jsonl
    data/dataset/val.jsonl
    data/dataset/dataset_stats.json
"""
import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURATED_DIR = ROOT / "data" / "curated"
ATLAS_DIR = ROOT / "data" / "atlas"
OUT_DIR = ROOT / "data" / "dataset"

MIN_OUTPUT_LEN = 25
MIN_INSTRUCTION_LEN = 8


def load_curated() -> list[dict]:
    """Кураторские QA-пары из всех qa_part*.jsonl."""
    samples = []
    files = sorted(CURATED_DIR.glob("qa_part*.jsonl"))
    if not files:
        raise FileNotFoundError(f"Не найдены кураторские файлы в {CURATED_DIR}")
    for fp in files:
        with fp.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{fp.name}:{line_no}: битый JSON — {e}") from e
                obj.setdefault("meta", {})
                obj["meta"]["source"] = fp.name
                samples.append(obj)
    return samples


GLOSSARY_ROW = re.compile(r"^\|\s*([^|`]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", re.M)


def generate_glossary_qa() -> list[dict]:
    """Автопары из таблицы глоссария (глава 18)."""
    gl = ATLAS_DIR / "18_glossary.md"
    if not gl.exists():
        return []
    text = gl.read_text(encoding="utf-8")
    samples = []
    for m in GLOSSARY_ROW.finditer(text):
        term, full, gist = (x.strip() for x in m.groups())
        if term in ("Термин", "---", "") or "---" in term:
            continue
        instruction = f"Что означает аббревиатура {term}?"
        output = f"{term} ({full}) — {gist}."
        samples.append({
            "instruction": instruction,
            "output": output,
            "meta": {"chapter": 18, "topic": "glossary_auto", "source": "18_glossary.md"},
        })
    return samples


def validate(samples: list[dict]) -> tuple[list[dict], list[str]]:
    """Фильтрация + сбор предупреждений."""
    ok, warns = [], []
    seen = set()
    for i, s in enumerate(samples):
        instr, out = s.get("instruction", "").strip(), s.get("output", "").strip()
        if len(instr) < MIN_INSTRUCTION_LEN:
            warns.append(f"[{i}] instruction слишком короткий: {instr[:40]!r}")
            continue
        if len(out) < MIN_OUTPUT_LEN:
            warns.append(f"[{i}] output слишком короткий: {out[:40]!r}")
            continue
        if not re.search(r"[А-Яа-яЁё]", instr) or not re.search(r"[А-Яа-яЁё]", out):
            warns.append(f"[{i}] нет кириллицы: {instr[:40]!r}")
            continue
        key = hashlib.sha256(instr.lower().encode()).hexdigest()
        if key in seen:
            warns.append(f"[{i}] дубликат instruction: {instr[:40]!r}")
            continue
        seen.add(key)
        ok.append({
            "instruction": instr,
            "output": out,
            "meta": s.get("meta", {}),
        })
    return ok, warns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--val-frac", type=float, default=0.06)
    args = ap.parse_args()

    curated = load_curated()
    auto = generate_glossary_qa()
    all_samples = curated + auto

    ok, warns = validate(all_samples)
    for w in warns:
        print(f"  WARN {w}")

    rng = random.Random(args.seed)
    rng.shuffle(ok)
    n_val = max(1, int(len(ok) * args.val_frac))
    val, train = ok[:n_val], ok[n_val:]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, part in (("train.jsonl", train), ("val.jsonl", val)):
        with (OUT_DIR / name).open("w", encoding="utf-8") as f:
            for s in part:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

    chapters = {}
    for s in ok:
        ch = s.get("meta", {}).get("chapter", "?")
        chapters[str(ch)] = chapters.get(str(ch), 0) + 1

    stats = {
        "total": len(ok),
        "train": len(train),
        "val": len(val),
        "curated": len(curated),
        "auto_glossary": len(auto),
        "dropped": len(all_samples) - len(ok),
        "warnings": len(warns),
        "by_chapter": dict(sorted(chapters.items(), key=lambda kv: str(kv[0]))),
        "seed": args.seed,
        "val_frac": args.val_frac,
    }
    (OUT_DIR / "dataset_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if len(ok) < 150:
        print("ОШИБКА: датасет подозрительно мал (<150 пар)", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
