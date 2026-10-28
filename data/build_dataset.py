#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборщик обучающего датасета Атлас-LLM.

Собирает датасет инструкций (instruction-tuning) из двух источников:
  1. Кураторские QA-пары: data/curated/qa_part*.jsonl
  2. Автогенерация из глоссария атласа: data/atlas/18_glossary.md
     (таблица терминов -> пары «Что такое X?» / определение)

Валидация: непустые поля, минимальная длина ответа, кириллица,
дедупликация по instruction, антиутечечный train/val сплит.

Сплит (ROADMAP_v2 фаза 0.3, EVALUATION_PLAN §антиутечка):
  - group  (по умолчанию): валидация набирается ЦЕЛЫМИ главами — близнецы
    одного термина из одной главы не могут оказаться по обе стороны сплита;
  - random: прежний случайный сплит по seed (воспроизведение прогонов до фазы 0.3).
Плюс отчёт о «близнецах» — нормализованных инструкциях, встретившихся
и в train, и в val.

Запуск:
    python data/build_dataset.py [--seed 42] [--val-frac 0.06] [--split-mode group|random]
        [--auto glossary|full]   # full = глоссарий + таблицы/законы/термины (auto_qa)

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

try:
    import auto_qa  # type: ignore  # лежит рядом (data/)
except ImportError:  # pragma: no cover
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import auto_qa  # type: ignore


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
    if not samples:
        raise ValueError(
            f"{gl.name}: парсер GLOSSARY_ROW не извлёк ни одной строки — "
            "формат таблицы глоссария изменился; чинить разметку парсера, "
            "а не молча пропускать (ROADMAP_v2 ф1, fail-loud)")
    return samples


def group_key(s: dict) -> str:
    """Группа антиутечки: глава, если известна, иначе файл-источник."""
    m = s.get("meta", {})
    return str(m.get("chapter") or m.get("source") or "?")


def split_by_group(ok: list[dict], val_frac: float,
                   rng: random.Random) -> tuple[list[dict], list[dict], list[str]]:
    """Валидация набирается целыми главами; детерминировано по seed.
    Возвращает (train, val, главы_val)."""
    groups: dict[str, list[dict]] = {}
    for s in ok:
        groups.setdefault(group_key(s), []).append(s)
    keys = sorted(groups)
    rng.shuffle(keys)
    target = max(1, round(len(ok) * val_frac))
    val_keys: set[str] = set()
    size = 0
    for k in keys:
        if size >= target:
            break
        val_keys.add(k)
        size += len(groups[k])
    val = [s for k in keys if k in val_keys for s in groups[k]]
    train = [s for k in keys if k not in val_keys for s in groups[k]]
    return train, val, [k for k in keys if k in val_keys]


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
    ap.add_argument("--split-mode", choices=("group", "random"), default="group",
                    help="group: val целыми главами (антиутечка); "
                         "random: прежний случайный сплит")
    ap.add_argument("--auto", choices=("glossary", "full"), default="full",
                    help="glossary: только глоссарий (воспроизведение v1); "
                         "full: глоссарий + таблицы/законы/термины (волна «Гибрид»)")
    args = ap.parse_args()

    curated = load_curated()
    auto = generate_glossary_qa()
    extra: dict[str, list] = {}
    if args.auto == "full":
        extra = auto_qa.extract_all(ATLAS_DIR)
    all_samples = curated + auto + [s for part in extra.values() for s in part]

    ok, warns = validate(all_samples)
    for w in warns:
        print(f"  WARN {w}")

    rng = random.Random(args.seed)
    if args.split_mode == "group":
        train, val, val_chapters = split_by_group(ok, args.val_frac, rng)
    else:
        rng.shuffle(ok)
        n_val = max(1, int(len(ok) * args.val_frac))
        val, train = ok[:n_val], ok[n_val:]
        val_chapters = sorted({str(s.get("meta", {}).get("chapter", "?")) for s in val})

    # Отчёт о близнецах: нормализованная инструкция в ОБОИХ выборках = утечка.
    train_keys = {s["instruction"].strip().lower() for s in train}
    twins = [s["instruction"] for s in val
             if s["instruction"].strip().lower() in train_keys]
    for t in twins:
        print(f"  LEAK близнец train/val: {t[:70]!r}")

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
        "auto_extra": {k: len(v) for k, v in extra.items()},
        "dropped": len(all_samples) - len(ok),
        "warnings": len(warns),
        "by_chapter": dict(sorted(chapters.items(), key=lambda kv: str(kv[0]))),
        "seed": args.seed,
        "val_frac": args.val_frac,
        "split_mode": args.split_mode,
        "val_chapters": val_chapters,
        "twin_overlap_train_val": len(twins),
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
