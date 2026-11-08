#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eval_gate.py — eval-гейт влития (П-08, polimat-hub#26).

Прогоняет evaluation/eval_qa.py в retrieval-only режиме на val30 и сверяет
метрику с порогом из evaluation/gate.json (метрика, оператор, порог).
rc=0 — гейт зелёный (не хуже baseline), rc=1 — регресс или авария.

Запуск:
    python evaluation/eval_gate.py
    python evaluation/eval_gate.py --max-samples 10   # быстрый дым
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "evaluation" / "gate.json"
OUT = ROOT / "evaluation" / "report_gate_run.json"
VERDICT = ROOT / "evaluation" / "gate_verdict.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-samples", type=int, default=30)
    args = parser.parse_args()

    gate = json.loads(GATE.read_text(encoding="utf-8"))
    metric, operator, threshold = gate["metric"], gate["operator"], gate["threshold"]

    cmd = [sys.executable, str(ROOT / "evaluation" / "eval_qa.py"),
           "--retrieval-only", "--max-samples", str(args.max_samples),
           "--out", str(OUT.relative_to(ROOT))]
    run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    if run.returncode != 0:
        print("[eval-gate] eval_qa упал:", run.stderr[-800:], file=sys.stderr)
        return 1

    aggregate = json.loads(OUT.read_text(encoding="utf-8"))["aggregate"]
    if metric not in aggregate:
        print(f"[eval-gate] метрика {metric} отсутствует в прогоне", file=sys.stderr)
        return 1
    got = aggregate[metric]

    if operator == ">=":
        ok = got >= threshold
    elif operator == ">":
        ok = got > threshold
    else:
        print(f"[eval-gate] оператор {operator!r} не поддержан", file=sys.stderr)
        return 1

    verdict = {
        "gate": {"metric": metric, "operator": operator, "threshold": threshold,
                 "baseline": gate.get("baseline"), "mode": gate.get("mode")},
        "got": got,
        "samples": aggregate.get("n"),
        "verdict": "PASS" if ok else "FAIL",
    }
    VERDICT.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
