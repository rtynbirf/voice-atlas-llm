"""П56: тесты реестра голосов (pytest-обёртка над voices/lint.py и build_registry.py)."""
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint = _load("voices_lint", "voices/lint.py")
builder = _load("voices_build", "voices/build_registry.py")


def test_lint_green_on_real_repo():
    rep = lint.scan(REPO)
    assert rep.ok, rep.render()


def test_lint_selftest_negative_red():
    assert lint.selftest() == 0


def test_build_deterministic_double_run():
    a = builder.render()
    b = builder.render()
    assert a == b, "двойная сборка не байт-идентична"


def test_build_check_pass():
    # voices/manifest.json в репо обязан совпадать со сборкой
    assert (REPO / "voices" / "manifest.json").read_bytes() == builder.render()


def test_registry_counts_match_voices():
    reg = json.loads((REPO / "voices" / "manifest.json").read_text(encoding="utf-8"))
    voices = reg["voices"]
    assert reg["counts"]["total"] == len(voices)
    kinds: dict[str, int] = {}
    for v in voices:
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    for k, n in kinds.items():
        assert reg["counts"][k] == n, f"counts[{k}] расходится"


def test_seal_selftest_tamper_red():
    seal = _load("voices_seal", "voices/seal.py")
    assert seal.cmd_selftest() == 0
