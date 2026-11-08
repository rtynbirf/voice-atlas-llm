#!/usr/bin/env python3
"""Линт реестра голосов voices/manifest.json (П56, issue #7).

Std-only Python. Сверяет манифест с источниками и деревом; любое сомнение =
красный (fail-closed). Чеки:

  V0_SCHEMA          — схема: id уникальны, обязательные поля, seal.hex = 64 hex;
                       для kind=release без пломбы — честный seal_status=unsealed
  V1_SOURCE_CORPUS   — 50/50 записей source-corpus сходятся с
                       data/ruvson/MANIFEST.jsonl бит-в-бит (имя, drive_id,
                       sha256, размер); в обе стороны (нет фантомов карты)
  V2_LOCAL_SEALS     — для записей с local_path: файл существует и его
                       live-sha256 == seal.hex (храповик пломб)
  V3_ORPHANS         — аудиофайлы в voices/audio/ без записи в реестре = сироты
                       (сироты = 0 — машинная приёмка П56)
  V4_PHANTOMS        — local_path объявлен, файла нет = фантом (красный)
  V5_WORKS_CROSSCHECK— каждый 64-hex, упомянутый в docs/WORKS.md, обязан
                       существовать среди пломб реестра/манифеста корпуса
                       («WORKS.md хеши сходятся» — приёмка П56)

Запуск:  python3 voices/lint.py             # линт репо → VOICES_LINT=PASS/FAIL
         python3 voices/lint.py --selftest  # негативный тест: испорченная пломба,
                            # сирота, фантом и чужой хеш в WORKS обязаны дать красный
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "voices" / "manifest.json"
SRC_MANIFEST = REPO / "data" / "ruvson" / "MANIFEST.jsonl"
WORKS = REPO / "docs" / "WORKS.md"
AUDIO_DIR = REPO / "voices" / "audio"

AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus", ".aac"}
HEX64 = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{64}(?![0-9a-fA-F])")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.lines.append((name, ok, detail))

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.lines)

    def names(self) -> dict[str, bool]:
        return {n: ok for n, ok, _ in self.lines}

    def render(self) -> str:
        out = []
        for name, ok, detail in self.lines:
            mark = "PASS" if ok else "FAIL"
            out.append(f"{name}={mark}" + (f" :: {detail}" if detail and not ok else ""))
        out.append("VOICES_LINT=PASS" if self.ok else "VOICES_LINT=FAIL")
        return "\n".join(out)


def scan(root: Path) -> Report:
    rep = Report()
    reg_path = root / "voices" / "manifest.json"
    src_path = root / "data" / "ruvson" / "MANIFEST.jsonl"
    works_path = root / "docs" / "WORKS.md"
    audio_dir = root / "voices" / "audio"
    if not reg_path.is_file():
        rep.add("V0_SCHEMA", False, "нет voices/manifest.json")
        return rep
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        rep.add("V0_SCHEMA", False, f"реестр не читается: {e}")
        return rep

    # --- V0: схема ---
    voices = reg.get("voices")
    err = []
    if not isinstance(voices, list) or not voices:
        err.append("voices пуст или не список")
        voices = []
    ids = [v.get("id") for v in voices if isinstance(v, dict)]
    if len(ids) != len(set(ids)):
        err.append("дубликаты id")
    for v in voices:
        if not isinstance(v, dict):
            err.append("запись не объект"); continue
        for f in ("id", "kind", "artist", "title", "language", "license", "source"):
            if f not in v:
                err.append(f"{v.get('id')}: нет поля {f}")
        seal = v.get("seal")
        if seal is not None:
            hx = (seal or {}).get("hex", "")
            if not re.fullmatch(r"[0-9a-f]{64}", hx or ""):
                err.append(f"{v.get('id')}: пломба не 64 нижних hex")
        else:
            st = v.get("seal_status", "")
            if not (isinstance(st, str) and st.startswith("unsealed")):
                err.append(f"{v.get('id')}: seal=null, но seal_status не unsealed")
    rep.add("V0_SCHEMA", not err, "; ".join(err[:6]))

    # --- V1: корпус 50/50 бит-в-бит ---
    if not src_path.is_file():
        rep.add("V1_SOURCE_CORPUS", False, "нет data/ruvson/MANIFEST.jsonl")
        src_recs = []
    else:
        src_recs = [json.loads(ln) for ln in
                    src_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    corpus = [v for v in voices
              if isinstance(v, dict) and v.get("kind") == "source-corpus"]
    by_hex = {}
    bad = []
    for v in corpus:
        seal = (v.get("seal") or {}).get("hex")
        src = v.get("source") or {}
        match = [r for r in src_recs
                 if r.get("sha256") == seal
                 and r.get("name") == (v.get("file") or {}).get("name")
                 and r.get("drive_id") == (src or {}).get("drive_id")
                 and r.get("size_bytes") == (v.get("file") or {}).get("size_bytes")]
        if len(match) != 1:
            bad.append(f"{v.get('id')}: нет точного аналога в MANIFEST.jsonl")
        else:
            by_hex[seal] = v["id"]
    if len(corpus) != len(src_recs):
        bad.append(f"корпус в реестре {len(corpus)} против {len(src_recs)} в MANIFEST.jsonl")
    rep.add("V1_SOURCE_CORPUS", not bad and bool(src_recs), "; ".join(bad[:6]))

    all_seals = {r.get("sha256") for r in src_recs} | set(by_hex)

    # --- V2/V4: локальные пломбы и фантомы ---
    bad_seal, phantom = [], []
    for v in voices:
        lp = v.get("local_path")
        if not lp:
            continue
        p = root / lp
        if not p.is_file():
            phantom.append(f"{v.get('id')}: {lp} отсутствует")
            continue
        live = sha256_file(p)
        want = (v.get("seal") or {}).get("hex")
        if want != live:
            bad_seal.append(f"{v.get('id')}: файл {live[:12]}… ≠ пломба {str(want)[:12]}…")
    rep.add("V2_LOCAL_SEALS", not bad_seal, "; ".join(bad_seal[:6]))
    rep.add("V4_PHANTOMS", not phantom, "; ".join(phantom[:6]))

    # --- V3: сироты в voices/audio/ ---
    declared = {str((root / v.get("local_path")).relative_to(root))
                for v in voices if v.get("local_path")}
    orphans = []
    if audio_dir.is_dir():
        for p in sorted(audio_dir.rglob("*")):
            if p.is_file() and p.suffix.lower() in AUDIO_EXT:
                rel = p.relative_to(root).as_posix()
                if rel not in declared:
                    orphans.append(rel)
    rep.add("V3_ORPHANS_ZERO", not orphans, "; ".join(orphans[:6]))

    # --- V5: WORKS.md хеши сходятся ---
    bad_works = []
    if works_path.is_file():
        text = works_path.read_text(encoding="utf-8", errors="replace")
        for hx in set(HEX64.findall(text)):
            if hx not in all_seals:
                bad_works.append(f"WORKS.md: {hx[:12]}… нет среди пломб")
        rep.add("V5_WORKS_CROSSCHECK", not bad_works, "; ".join(bad_works[:6]))
    else:
        rep.add("V5_WORKS_CROSSCHECK", False, "нет docs/WORKS.md")
    return rep


# --------------------------------------------------------------------------
# негативный selftest
# --------------------------------------------------------------------------
def selftest() -> int:
    must_fail = ["V2_LOCAL_SEALS", "V3_ORPHANS_ZERO", "V4_PHANTOMS", "V5_WORKS_CROSSCHECK"]
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="voices-fx-") as td:
        root = Path(td)
        (root / "data" / "ruvson").mkdir(parents=True)
        (root / "docs").mkdir(parents=True)
        (root / "voices" / "audio").mkdir(parents=True)
        sample = b"RIFF....fake audio payload for seal"
        seal_hex = hashlib.sha256(sample).hexdigest()
        (root / "data" / "ruvson" / "MANIFEST.jsonl").write_text(
            json.dumps({"name": "s.mp3", "drive_id": "IDX", "size_bytes": len(sample),
                        "sha256": seal_hex, "container": "mp3", "has_video": False,
                        "audio_codec": "mp3", "duration_sec": 1.0,
                        "audio_bitrate_kbps": 64}) + "\n", encoding="utf-8")
        good = {
            "schema": "voice-registry/1", "seal_algo": "sha256",
            "counts": {"source-corpus": 1, "release": 0, "total": 1},
            "conventions": {},
            "voices": [{
                "id": "ruvson-src-001", "kind": "source-corpus", "artist": "RUVSON",
                "title": "s", "language": "ru", "license": "test",
                "source": {"kind": "google-drive", "drive_id": "IDX",
                           "ref": "data/ruvson/MANIFEST.jsonl"},
                "file": {"name": "s.mp3", "size_bytes": len(sample)},
                "seal": {"algo": "sha256", "hex": seal_hex},
                "seal_status": "sealed-at-ingest", "local_path": None,
            }],
        }
        import copy

        # 1) зелёная база: регистрируем локальный семпл честно
        ok_reg = copy.deepcopy(good)
        ok_reg["voices"][0]["local_path"] = "voices/audio/s.mp3"
        (root / "voices" / "audio" / "s.mp3").write_bytes(sample)
        (root / "voices" / "manifest.json").write_text(
            json.dumps(ok_reg, ensure_ascii=False), encoding="utf-8")
        (root / "docs" / "WORKS.md").write_text(
            f"Проверено: пломба {seal_hex} подтверждена.\n", encoding="utf-8")
        rep_ok = scan(root)
        print("--- база (ожидаем зелёный) ---")
        print(rep_ok.render())
        if not rep_ok.ok:
            failures.append("честное дерево не прошло линт")

        # 2) испорченная пломба
        tam = copy.deepcopy(ok_reg)
        tam["voices"][0]["seal"]["hex"] = "0" * 64
        (root / "voices" / "manifest.json").write_text(
            json.dumps(tam, ensure_ascii=False), encoding="utf-8")
        if scan(root).names().get("V2_LOCAL_SEALS") is not False:
            failures.append("испорченная пломба не дала красный (V2)")

        # 3) сирота
        (root / "voices" / "manifest.json").write_text(
            json.dumps(ok_reg, ensure_ascii=False), encoding="utf-8")
        (root / "voices" / "audio" / "orphan.mp3").write_bytes(b"orphan")
        if scan(root).names().get("V3_ORPHANS_ZERO") is not False:
            failures.append("сирота не дала красный (V3)")
        (root / "voices" / "audio" / "orphan.mp3").unlink()

        # 4) фантом
        ph = copy.deepcopy(ok_reg)
        ph["voices"][0]["local_path"] = "voices/audio/missing.mp3"
        (root / "voices" / "manifest.json").write_text(
            json.dumps(ph, ensure_ascii=False), encoding="utf-8")
        if scan(root).names().get("V4_PHANTOMS") is not False:
            failures.append("фантом не дал красный (V4)")

        # 5) чужой хеш в WORKS.md
        (root / "voices" / "manifest.json").write_text(
            json.dumps(ok_reg, ensure_ascii=False), encoding="utf-8")
        (root / "docs" / "WORKS.md").write_text(
            f"Проверено: пломба {seal_hex} и чужая "
            f"{'a' * 64}.\n", encoding="utf-8")
        if scan(root).names().get("V5_WORKS_CROSSCHECK") is not False:
            failures.append("чужой хеш в WORKS.md не дал красный (V5)")

    print("--- итог selftest ---")
    if failures:
        for f in failures:
            print(f"SELFTEST_NEGATIVE=FAIL :: {f}")
        print("SELFTEST=FAIL")
        return 1
    for name in must_fail:
        print(f"{name}_NEGATIVE=PASS")
    print("SELFTEST=PASS (испорченная пломба/сирота/фантом/чужой хеш дают красный)")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    rep = scan(REPO)
    print(rep.render())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
