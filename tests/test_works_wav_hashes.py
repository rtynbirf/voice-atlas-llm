# -*- coding: utf-8 -*-
"""Ловушка WORKS.md по хешам (П-08, polimat-hub#26).

«Wav-хеши WORKS.md — это уже контракт; оформляется как тест, а не как
ручная сверка». Три контура:

1. Каждый wav, лежащий в репо (data/ruvson/**), сверяется байт-в-байт
   с sha256-эталоном из data/ruvson/voice_clone_report.json (artifacts).
2. Регресс CRLF-ловушки: .gitattributes обязан содержать *.wav binary,
   *.onnx binary, *.pth binary, *.mp3 binary; глобальный `* text …`
   ЗАПРЕЩЁН — он делает бинарные файлы «текстом» и молча портит байты
   CRLF→LF (хроника: 300588 → 300579, коммит 956fba8 / rebase 8571812).
3. data/ruvson/MANIFEST.jsonl — 50 записей корпуса RUVSON: каждый
   sha256 — 64 hex, size_bytes > 0; эталонные отчёты voice_20langs /
   singing_20langs содержат по 20 языков со статусом ok.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_repo_wavs_bite_identical_vs_report():
    """Wav-файлы репо == sha256-эталонам отчёта (контракт WORKS.md)."""
    report = json.loads(
        (ROOT / "data/ruvson/voice_clone_report.json").read_text(encoding="utf-8"))
    artifacts = report["artifacts"]
    checked = 0
    for name, meta in artifacts.items():
        matches = sorted((ROOT / "data/ruvson").rglob(name))
        if not matches:
            # референс/исходники вне git (vocals.wav 182 c и т.п.) — не репо-контракт
            continue
        wav = matches[0]
        assert _sha256(wav) == meta["sha256"], (
            f"{wav}: sha256 {meta['sha256'][:12]}… ≠ факт {_sha256(wav)[:12]}… "
            "— байты тронуты (CRLF-ловушка?)")
        assert wav.stat().st_size == meta["bytes"], f"{wav}: размер ≠ эталону"
        checked += 1
    # контрактом покрыты именно репо-файлы voice_clone_01
    assert checked >= 2, f"ожидали ≥2 wav-контракта, сверили {checked}"


def test_gitattributes_wav_binary_no_global_text():
    """Регресс CRLF-ловушки: binary-правила на месте, глобальный `* text` убран."""
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rule in ("*.wav binary", "*.onnx binary", "*.pth binary", "*.mp3 binary"):
        assert rule in attrs, f".gitattributes: нет правила {rule!r}"
    for line in attrs.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        assert not s.startswith("* text"), (
            f".gitattributes: глобальный {s!r} — та самая CRLF-мина "
            "(волна ×5-ХОЗЯИН, П-08)")


def test_manifest_jsonl_hashes_shape():
    """MANIFEST.jsonl корпуса RUVSON: sha256 — 64 hex, size_bytes > 0."""
    rows = [json.loads(line) for line in
            (ROOT / "data/ruvson/MANIFEST.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == 50, f"ожидали 50 записей корпуса, получили {len(rows)}"
    for row in rows:
        assert HEX64.fullmatch(row["sha256"]), f"{row['name']}: sha256 не 64 hex"
        assert row["size_bytes"] > 0, f"{row['name']}: size_bytes <= 0"


def test_reports_cover_20_languages_each():
    """voice_20langs и singing_20langs: по 20 языков, статусы ok/заполнены."""
    for rep, key in (("data/ruvson/voice_20langs_report.json", "languages"),
                     ("data/ruvson/singing_20langs/report_singing_20langs.json",
                      "languages")):
        data = json.loads((ROOT / rep).read_text(encoding="utf-8"))
        langs = data[key]
        assert len(langs) == 20, f"{rep}: {len(langs)} языков вместо 20"
        for code, rec in langs.items():
            if "status" in rec:
                assert rec["status"] == "ok", f"{rep}[{code}]: status={rec['status']}"
            if "sha256" in rec:
                assert HEX64.fullmatch(rec["sha256"]), f"{rep}[{code}]: sha256 битый"
