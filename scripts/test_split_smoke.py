#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Дым-проверка split_by_group в памяти: НИКАКИХ записей в data/dataset —
канонические файлы соответствуют обученному адаптеру. Печатаем размер val,
главы val и число близнецов для нового режима."""
import random
import sys
from pathlib import Path

REPO = Path("/home/z/my-project/voice-atlas-llm")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "data"))

from data.build_dataset import (  # noqa: E402
    generate_glossary_qa, load_curated, split_by_group, validate)

ok, warns = validate(load_curated() + generate_glossary_qa())
print(f"после валидации: {len(ok)} пар, WARN={len(warns)}")

train, val, val_chapters = split_by_group(ok, 0.06, random.Random(42))
tr = {s["instruction"].strip().lower() for s in train}
twins = [s["instruction"] for s in val if s["instruction"].strip().lower() in tr]
print(f"group-сплит: train={len(train)} val={len(val)} ({len(val)/len(ok):.0%})")
print(f"главы val: {val_chapters}")
print(f"близнецы train/val: {len(twins)}")
chapters_train = {s.get("meta", {}).get("chapter") for s in train}
overlap = set(map(str, val_chapters)) & {str(c) for c in chapters_train}
print(f"пересечение глав train∩val (должно быть 0): {len(overlap)} {overlap if overlap else ''}")
assert not overlap, "УТЕЧКА: глава в обоих множествах"
assert len(val) >= 1 and len(train) > len(val)
print("SMOKE OK")
