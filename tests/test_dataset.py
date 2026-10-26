# -*- coding: utf-8 -*-
"""Тесты датасета: сборка, валидация, сплит, формат JSONL."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data"))

from data.build_dataset import load_curated, generate_glossary_qa, validate  # noqa: E402


def test_curated_files_exist_and_parse():
    samples = load_curated()
    assert len(samples) >= 120, f"слишком мало кураторских пар: {len(samples)}"


def test_validate_filters_garbage():
    samples = [
        {"instruction": "Нормальный вопрос про голос?", "output": "Нормальный достаточно длинный ответ про тембр.", "meta": {}},
        {"instruction": "ок", "output": "Короткий ответ.", "meta": {}},
        {"instruction": "English only question about voice?", "output": "No cyrillic answer about timbre at all.", "meta": {}},
    ]
    ok, warns = validate(samples)
    assert len(ok) == 1
    assert len(warns) == 2


def test_validate_dedupes_by_instruction():
    samples = [
        {"instruction": "Что такое тембр голоса?", "output": "Окраска и резонансы голосового аппарата человека.", "meta": {}},
        {"instruction": "что такое тембр голоса?", "output": "Повтор вопроса другой раскладкой клавиатуры.", "meta": {}},
    ]
    ok, _ = validate(samples)
    assert len(ok) == 1


def test_build_dataset_end_to_end(tmp_path):
    curated = load_curated()
    auto = generate_glossary_qa()
    ok, _ = validate(curated + auto)
    assert len(ok) >= 150
    assert auto, "глоссарий не распарсился"
    for s in ok:
        assert s["instruction"] and s["output"]
        assert "meta" in s


def test_dataset_files_if_present_are_valid_jsonl():
    ds = ROOT / "data" / "dataset"
    train, val = ds / "train.jsonl", ds / "val.jsonl"
    if not train.exists():
        pytest.skip("датасет ещё не собран")
    seen = set()
    for fp in (train, val):
        with fp.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                assert obj["instruction"] not in seen, "дубликат между train и val"
                seen.add(obj["instruction"])
