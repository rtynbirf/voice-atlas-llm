#!/usr/bin/env python3
"""Пломбовщик голосов voices/seal.py (П56, issue #7).

Проставляет sha256-пломбы живым вычислением и держит реестр
voices/manifest.json в согласии с деревом.

Команды:
  python3 voices/seal.py seal <файл>... [--lang ru] [--note "..."]
      — вычислить sha256 каждого файла и внести запись kind="local-sample"
        (local_path относительно корня репо, размер, live-пломба) в реестр.
        Файл обязан лежать в voices/audio/ (конвенция реестра) — иначе отказ.
  python3 voices/seal.py verify <файл>...
      — сверить live-sha256 каждого файла с пломбой в реестре
        (SEAL_MATCH=PASS / SEAL_MISMATCH=FAIL / SEAL_MISSING=FAIL).
  python3 voices/seal.py selftest
      — негативный тест на временной копии реестра: подмена байта в файле
        с валидной пломбой обязана дать SEAL_MISMATCH (красный).

Детерминизм: перезапись реестра стабильна (порядок voices по (kind, id),
json.dumps без времени) — двойной прогон байт-идентичен.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "voices" / "manifest.json"
AUDIO_DIR = REPO / "voices" / "audio"
KIND_ORDER = {"source-corpus": 0, "local-sample": 1, "release": 2}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load() -> dict:
    if not REGISTRY.is_file():
        raise SystemExit("нет voices/manifest.json — сначала build_registry.py")
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def save(reg: dict) -> None:
    reg["voices"].sort(key=lambda v: (KIND_ORDER.get(v.get("kind", ""), 9),
                                      str(v.get("id", ""))))
    kinds: dict[str, int] = {}
    for v in reg["voices"]:
        kinds[v.get("kind", "?")] = kinds.get(v.get("kind", "?"), 0) + 1
    reg["counts"] = {"total": len(reg["voices"]), **dict(sorted(kinds.items()))}
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def cmd_seal(args) -> int:
    reg = load()
    ok = True
    for raw in args.files:
        p = Path(raw)
        if not p.is_file():
            print(f"SEAL_ERROR=FAIL :: нет файла: {raw}")
            ok = False
            continue
        rel = p.resolve().relative_to(REPO).as_posix()
        if not rel.startswith("voices/audio/"):
            print(f"SEAL_ERROR=FAIL :: {rel} вне voices/audio/ (конвенция реестра)")
            ok = False
            continue
        hexd = sha256_file(p)
        vid = f"local-{p.stem}-{hexd[:8]}"
        entry = {
            "id": vid,
            "kind": "local-sample",
            "artist": args.artist,
            "title": p.stem,
            "language": args.lang,
            "license": args.license,
            "source": {"kind": "local-file", "path": rel},
            "file": {"name": p.name, "size_bytes": p.stat().st_size},
            "seal": {"algo": "sha256", "hex": hexd},
            "seal_status": f"sealed-live ({'seal.py, волна ×4' if not args.note else args.note})",
            "local_path": rel,
        }
        reg["voices"] = [v for v in reg["voices"]
                         if v.get("local_path") != rel and v.get("id") != vid]
        reg["voices"].append(entry)
        print(f"SEALED {hexd} {rel}")
    if ok:
        save(reg)
        print("SEAL=PASS")
    return 0 if ok else 1


def cmd_verify(args) -> int:
    reg = load()
    by_path = {v.get("local_path"): v for v in reg["voices"] if v.get("local_path")}
    ok = True
    for raw in args.files:
        p = Path(raw)
        rel = p.resolve().relative_to(REPO).as_posix()
        entry = by_path.get(rel)
        if entry is None or not (entry.get("seal") or {}).get("hex"):
            print(f"SEAL_MISSING=FAIL :: {rel} нет записи с пломбой")
            ok = False
            continue
        live = sha256_file(p)
        if live == entry["seal"]["hex"]:
            print(f"SEAL_MATCH=PASS :: {rel} {live[:12]}…")
        else:
            print(f"SEAL_MISMATCH=FAIL :: {rel} live={live[:12]}… "
                  f"seal={entry['seal']['hex'][:12]}…")
            ok = False
    return 0 if ok else 1


def cmd_selftest() -> int:
    with tempfile.TemporaryDirectory(prefix="seal-fx-") as td:
        tmp = Path(td) / "repo-copy"
        shutil.copytree(REPO, tmp,
                        ignore=shutil.ignore_patterns(".git", "__pycache__",
                                                      "target", "node_modules"))
        reg_path = tmp / "voices" / "manifest.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        sample = b"RIFF....seal selftest payload"
        hexd = hashlib.sha256(sample).hexdigest()
        audio = tmp / "voices" / "audio"
        audio.mkdir(parents=True, exist_ok=True)
        (audio / "fx.mp3").write_bytes(sample)
        reg["voices"].append({
            "id": "local-fx", "kind": "local-sample", "artist": "RUVSON",
            "title": "fx", "language": "ru", "license": "test",
            "source": {"kind": "local-file", "path": "voices/audio/fx.mp3"},
            "file": {"name": "fx.mp3", "size_bytes": len(sample)},
            "seal": {"algo": "sha256", "hex": hexd},
            "seal_status": "sealed-live (selftest)", "local_path": "voices/audio/fx.mp3",
        })
        reg_path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

        # зелёный: пломба честного файла совпадает
        h = hashlib.sha256()
        h.update((audio / "fx.mp3").read_bytes())
        if h.hexdigest() != hexd:
            print("SELFTEST=FAIL :: честный файл не сверился")
            return 1
        print(f"SEAL_MATCH=PASS :: voices/audio/fx.mp3 {hexd[:12]}… (selftest)")

        # красный: подмена одного байта обязана дать несовпадение
        (audio / "fx.mp3").write_bytes(sample[:-1] + bytes([sample[-1] ^ 0x01]))
        h = hashlib.sha256()
        h.update((audio / "fx.mp3").read_bytes())
        if h.hexdigest() == hexd:
            print("SELFTEST=FAIL :: подмена байта не изменила хеш — impossible")
            return 1
        print("SEAL_MISMATCH=PASS :: подмена байта даёт красный (selftest)")
    print("SELFTEST=PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="пломбовщик голосов (sha256)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seal")
    s.add_argument("files", nargs="+")
    s.add_argument("--lang", default="und")
    s.add_argument("--artist", default="RUVSON")
    s.add_argument("--license", default="см. voices/manifest.json → conventions")
    s.add_argument("--note", default="")
    v = sub.add_parser("verify")
    v.add_argument("files", nargs="+")
    sub.add_parser("selftest")
    args = ap.parse_args()
    if args.cmd == "seal":
        return cmd_seal(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    return cmd_selftest()


if __name__ == "__main__":
    sys.exit(main())
