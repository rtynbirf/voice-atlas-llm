# -*- coding: utf-8 -*-
"""test_eval_gate — контракт eval-гейта влития (П-08, polimat-hub#26).

Четвёртый критерий приёмки П-08: «тест test_eval_gate присутствует».
Гейт — это не пожелание, а машина: порог приколот к baseline, регресс
и любая авария = отказ влития (fail-closed). Проверяем четыре контура:

1. Контракт реального evaluation/gate.json: оператор поддержан,
   threshold == baseline_value (гейт приколот к baseline, а не «на глаз»),
   baseline-файл существует, режим retrieval_only.
2. Зелёный ход: метрика на уровне порога → rc=0, вердикт PASS.
3. Негативный кейс (главный): метрика ниже порога → rc=1, вердикт FAIL.
4. Аварии fail-closed: subprocess упал или метрика отсутствует → rc=1.

Прогон реального eval_qa здесь не дублируется — его гонит CI
(шаг «П-08 · eval-гейт»); тест проверяет логику решения гейта
на подставном прогоне, детерминированно и без модели.
"""
from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))

import eval_gate  # noqa: E402


@pytest.fixture
def gate_run(monkeypatch):
    """Гейт, OUT и VERDICT — под корнем репо (eval_gate требует OUT.relative_to(ROOT)).

    Возвращает (out, verdict); после теста убирает за собой тестовые артефакты.
    """
    run_dir = ROOT / "evaluation" / "_test_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "out.json"
    verdict = run_dir / "verdict.json"
    gate_file = run_dir / "gate_tmp.json"
    monkeypatch.setattr(eval_gate, "GATE", gate_file)
    monkeypatch.setattr(eval_gate, "OUT", out)
    monkeypatch.setattr(eval_gate, "VERDICT", verdict)
    gate_file.write_text(json.dumps(_gate_dict(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["eval_gate.py"])
    yield out, verdict
    # уборка за собой: тестовые артефакты не оставляем в рабочем дереве
    for f in (out, verdict, gate_file):
        f.unlink(missing_ok=True)
    if run_dir.is_dir() and not any(run_dir.iterdir()):
        run_dir.rmdir()


def _gate_dict() -> dict:
    return {
        "metric": "mean_rag_coverage", "operator": ">=",
        "threshold": 0.5, "baseline": "x.json", "baseline_value": 0.5,
        "mode": "retrieval_only",
    }


def _fake_subprocess_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
    )


def test_gate_contract_real_file():
    """Реальный gate.json: оператор поддержан, порог == baseline, файл-эталон жив."""
    gate = json.loads(eval_gate.GATE.read_text(encoding="utf-8"))
    assert gate["operator"] in (">=", ">")
    assert gate["threshold"] == gate["baseline_value"], (
        "порог гейта обязан быть приколот к baseline (П-08), а не выставлен рукой"
    )
    assert (ROOT / gate["baseline"]).exists(), "baseline-файл отчёта отсутствует"
    assert gate["mode"] == "retrieval_only"
    assert isinstance(gate["metric"], str) and gate["metric"]


def test_gate_pass_on_baseline_equality(monkeypatch, gate_run):
    """Метрика == порог → rc=0, вердикт PASS (гейт зелёный на месте baseline)."""
    out, verdict = gate_run
    out.write_text(json.dumps({"aggregate": {"mean_rag_coverage": 0.5, "n": 30}}),
                   encoding="utf-8")
    _fake_subprocess_ok(monkeypatch)
    assert eval_gate.main() == 0
    v = json.loads(verdict.read_text(encoding="utf-8"))
    assert v["verdict"] == "PASS" and v["got"] == 0.5


def test_gate_fails_on_regression(monkeypatch, gate_run):
    """НЕГАТИВНЫЙ КЕЙС: метрика ниже порога → rc=1, вердикт FAIL (влитие валится)."""
    out, verdict = gate_run
    out.write_text(json.dumps({"aggregate": {"mean_rag_coverage": 0.42, "n": 30}}),
                   encoding="utf-8")
    _fake_subprocess_ok(monkeypatch)
    assert eval_gate.main() == 1
    v = json.loads(verdict.read_text(encoding="utf-8"))
    assert v["verdict"] == "FAIL" and v["got"] == pytest.approx(0.42)


def test_gate_unknown_metric_fails_closed(monkeypatch, gate_run):
    """Метрика не пришла из прогона → rc=1 (молча пропустить регресс нельзя)."""
    out, verdict = gate_run
    out.write_text(json.dumps({"aggregate": {"another_metric": 0.9, "n": 30}}),
                   encoding="utf-8")
    _fake_subprocess_ok(monkeypatch)
    assert eval_gate.main() == 1


def test_gate_aborted_subprocess_fails_closed(monkeypatch, gate_run):
    """Прогон eval_qa упал → rc=1 (fail-closed), вердикт не пишется как PASS."""
    out, verdict = gate_run
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=2, stderr="boom"),
    )
    assert eval_gate.main() == 1
    assert not verdict.exists(), "вердикт не должен писаться при упавшем прогоне"
