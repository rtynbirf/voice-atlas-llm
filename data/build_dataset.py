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
        [--v3] [--out-dir data/dataset_v3]
        # v3 (MODEL_CARD §3): + процедурные QA (этапы гл. 12, эталон-псевдокод),
        # кэп table_qa ≈ 30% (взвешенное сэмплирование), парафразы авто-типов,
        # вал заморожен = вале-30 v2 (A/B честный). Сплит-флаги игнорируются.

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

# Корпус v3 (MODEL_CARD §3): целевая доля table_qa в train.
V3_TABLE_CAP = 0.30
# Главы вале-30 (заморозка): все их пары не попадают в train (антиутечка тем).
V3_VAL_CHAPTERS = {"9", "14"}

# Парафраз-шаблоны (v3): вторая формулировка вопроса при том же эталоне.
# Выбор варианта — sha256(instruction), детерминирован без seed-коллизий.
PARAPHRASES = {
    "law_qa": ["Что утверждает закон {num} атласа?", "Раскрой содержание закона {num} «{name}»."],
    "glossary_auto": ["Расшифруй аббревиатуру {term} из атласа.", "Что скрывается за аббревиатурой {term}?"],
    "bold_qa": ["Объясни, что такое {term}.", "Дай определение термина {term} (атлас)."],
    "stage_qa": ["Опиши этап {num} универсального алгоритма.", "Что делается на шаге {num} универсального алгоритма?"],
}


def _para_fields(s: dict) -> dict | None:
    """Парафраз инструкции для пары (v3) либо None, если тип не шаблонизируется."""
    topic = s.get("meta", {}).get("topic", "")
    instr, out = s["instruction"], s["output"]
    if topic == "law_qa":
        m = re.search(r"закон (\d+)[^«]*«([^»]+)»", instr)
        num = m.group(1) if m else None
        name = m.group(2) if m else ""
        if not num:
            return None
        t = PARAPHRASES["law_qa"][int(hashlib.sha256(instr.encode()).hexdigest(), 16) % 2]
        return {"instruction": t.format(num=num, name=name)}
    if topic == "glossary_auto":
        m = re.search(r"аббревиатура ([^?]+)\?", instr)
        if not m:
            return None
        term = m.group(1).strip()
        t = PARAPHRASES["glossary_auto"][int(hashlib.sha256(instr.encode()).hexdigest(), 16) % 2]
        return {"instruction": t.format(term=term)}
    if topic == "bold_qa":
        m = re.search(r"Что такое ([^(]+) \(атлас", instr)
        if not m:
            return None
        term = m.group(1).strip()
        t = PARAPHRASES["bold_qa"][int(hashlib.sha256(instr.encode()).hexdigest(), 16) % 2]
        return {"instruction": t.format(term=term)}
    if topic == "stage_qa":
        m = re.search(r"этап[а-яё]*\s+(\d+)", instr)
        if not m or "по порядку" in instr or "обязательны" in instr.lower():
            return None
        t = PARAPHRASES["stage_qa"][int(hashlib.sha256(instr.encode()).hexdigest(), 16) % 2]
        return {"instruction": t.format(num=m.group(1))}
    return None


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
    ap.add_argument("--v3", action="store_true",
                    help="корпус v3 (MODEL_CARD §3): процедурные QA + кэп "
                         "table_qa 30% + парафразы; вал заморожен = вале-30 v2")
    ap.add_argument("--out-dir", default="data/dataset",
                    help="каталог вывода (v3 использует data/dataset_v3)")
    args = ap.parse_args()

    curated = load_curated()
    auto = generate_glossary_qa()
    extra: dict[str, list] = {}
    if args.auto == "full":
        extra = auto_qa.extract_all(ATLAS_DIR, v3=args.v3)
    all_samples = curated + auto + [s for part in extra.values() for s in part]

    ok, warns = validate(all_samples)
    for w in warns:
        print(f"  WARN {w}")

    out_dir = ROOT / args.out_dir

    if args.v3:
        # ---- КОРПУС v3 (MODEL_CARD §3) ----
        # 1. Вал заморожен: те же 30 инструкций, что в вале v2 (A/B честный).
        v2_val_path = ROOT / "data" / "dataset" / "val.jsonl"
        frozen = [json.loads(l) for l in v2_val_path.open(encoding="utf-8") if l.strip()]
        frozen_instr = [s["instruction"] for s in frozen]
        pool_by_instr = {}
        for s in ok:
            pool_by_instr.setdefault(s["instruction"], []).append(s)
        missing = [q for q in frozen_instr if q not in pool_by_instr]
        if missing:
            print(f"ОШИБКА: {len(missing)} вале-инструкций не найдены в пуле v3 "
                  f"(вал не собрать — fail-loud): {missing[:3]}", file=sys.stderr)
            return 2
        val = [pool_by_instr[q][0] for q in frozen_instr]
        val_instr = set(frozen_instr)

        # 2. Train: пул минус вале-пары минус все пары вале-глав (антиутечка тем).
        train = [s for s in ok
                 if s["instruction"] not in val_instr
                 and str(s.get("meta", {}).get("chapter")) not in V3_VAL_CHAPTERS]

        # 3. Взвешенное сэмплирование: кэп table_qa = 30% train.
        tables = [s for s in train if s.get("meta", {}).get("topic") == "table_qa"]
        rest = [s for s in train if s.get("meta", {}).get("topic") != "table_qa"]
        n_table_keep = min(len(tables), int(V3_TABLE_CAP * len(rest) / (1 - V3_TABLE_CAP)))
        rng3 = random.Random(args.seed)
        rng3.shuffle(tables)
        dropped_tables = len(tables) - n_table_keep
        train = rest + tables[:n_table_keep]

        # 4. Парафразы авто-типов (те же эталоны, другая формулировка вопроса).
        paras = []
        for s in train:
            pf = _para_fields(s)
            if pf:
                paras.append({"instruction": pf["instruction"], "output": s["output"],
                              "meta": dict(s["meta"], topic=s["meta"]["topic"] + "_para")})
        paras_ok, paras_warns = validate(paras)
        train = train + paras_ok

        # Близнецы: нормализованная инструкция в train и val = утечка.
        train_keys = {s["instruction"].strip().lower() for s in train}
        twins = [q for q in frozen_instr if q.strip().lower() in train_keys]
        for t in twins:
            print(f"  LEAK близнец train/val: {t[:70]!r}")

        out_dir.mkdir(parents=True, exist_ok=True)
        for name, part in (("train.jsonl", train), ("val.jsonl", val)):
            with (out_dir / name).open("w", encoding="utf-8") as f:
                for s in part:
                    f.write(json.dumps(s, ensure_ascii=False) + "\n")

        topics: dict[str, int] = {}
        for s in train:
            tp = s.get("meta", {}).get("topic", "?")
            topics[tp] = topics.get(tp, 0) + 1
        table_share = topics.get("table_qa", 0) / max(len(train), 1)
        stats = {
            "version": "v3",
            "total": len(train) + len(val), "train": len(train), "val": len(val),
            "frozen_val": True, "val_chapters": sorted(V3_VAL_CHAPTERS),
            "table_cap": V3_TABLE_CAP, "table_kept": n_table_keep,
            "table_dropped": dropped_tables, "table_share_train": round(table_share, 4),
            "paraphrases": len(paras_ok), "paraphrases_dropped": len(paras) - len(paras_ok),
            "topics_train": dict(sorted(topics.items())),
            "seed": args.seed, "twin_overlap_train_val": len(twins),
        }
        (out_dir / "dataset_stats.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        if table_share > V3_TABLE_CAP + 0.02:
            print("ОШИБКА: кэп table_qa не сработал", file=sys.stderr)
            return 2
        return 0

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
