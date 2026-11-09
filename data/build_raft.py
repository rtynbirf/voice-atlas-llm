#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборщик RAFT-корпуса v4 (волна «RAFT-Гибрид», 2026-11-10).

Мировая практика RAFT (Retrieval Augmented Fine-Tuning; UC Berkeley,
arXiv:2403.10131): обучать модель на том же распределении, на котором она
работает на инференсе, — «вопрос + справка из ретривера (оракул-чанк +
дистракторы) -> ответ». Часть примеров специально БЕЗ оракула (только
дистракторы): модель отвечает из доменной памяти и учится честности при
неподтверждённом.

Что нашего («такого ни у кого нет»):
  - разрыв train/inference v1-v3 закрыт байт-в-байт: контекст строится теми
    же функциями, что на инференсе (prompt_format.make_context +
    prompt_format.grounded_system; top-3, кэп 2400 символов — как в eval_qa.py);
  - оракул НЕ генерируется LLM (в оригинальном RAFT — GPT-4), а
    детерминированно ИЗМЕРЯЕТСЯ: покрытие ключевых слов эталона чанком
    (та же keyword_coverage, что в eval_qa.py и eval-гейте);
  - режим «память» (RAFT 1-P): 3 случайных чанка ЧУЖИХ глав, выбор
    детерминирован sha256(instruction) — воспроизводимость без seed-коллизий;
  - вал не тронут: замороженные 30 пар копируются БИТ-В-БАЙТ (протокол A/B
    v1/v2/v3/v4 единый: eval_qa сам грундит контекст на инференсе).

Рецепт RAFT: P=0.6 примеров с оракулом (у нас — реальный top-3 ретривера,
ничего не подкрашиваем), 1-P=0.4 только дистракторы.

Запуск:
    python data/build_raft.py --train data/dataset_v3/train.jsonl \
        --val data/dataset/val.jsonl --out-dir data/dataset_v4

Выход:
    data/dataset_v4/train.jsonl  (те же пары + поле context + метаданные raft)
    data/dataset_v4/val.jsonl    (бит-в-байт источник)
    data/dataset_v4/dataset_stats.json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inference.retriever import TfidfRetriever, load_corpus  # noqa: E402
from training.prompt_format import make_context  # noqa: E402
from evaluation.eval_qa import keyword_coverage  # noqa: E402

P_ORACLE = 0.6      # доля примеров «rag» (реальный top-3, как на инференсе)
N_DISTRACTOR = 3    # чужих чанков в режиме «memory»
ORACLE_MIN = 0.5    # покрытие эталона лучшим чанком top-3 => оракул найден


def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest(), 16)


def _ch_key(source: str) -> str:
    """'12_universal.md' -> '12'; номер главы без ведущих нулей."""
    return source[:2].lstrip("0") or "0"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/dataset_v3/train.jsonl")
    ap.add_argument("--val", default="data/dataset/val.jsonl",
                    help="вал копируется бит-в-байт (замороженные 30 пар)")
    ap.add_argument("--out-dir", default="data/dataset_v4")
    ap.add_argument("--p-oracle", type=float, default=P_ORACLE)
    args = ap.parse_args()

    train_rows = [json.loads(l) for l in (ROOT / args.train).open(encoding="utf-8")
                  if l.strip()]
    if not train_rows:
        print("ОШИБКА: пустой train-источник", file=sys.stderr)
        return 2
    docs = load_corpus()
    if not docs:
        print("ОШИБКА: пустой корпус атласа", file=sys.stderr)
        return 2
    ret = TfidfRetriever(docs)
    foreign_by_key: dict[str, list[dict]] = {}
    for d in docs:
        foreign_by_key.setdefault(_ch_key(d["source"]), []).append(d)

    out_rows = []
    n_rag = n_memory = n_oracle = 0
    union_covers, ctx_chars = [], []
    for s in train_rows:
        q, a = s["instruction"], s["output"]
        hits = ret.search(q, 3)  # ровно как на инференсе (eval_qa.py)
        union_ctx = make_context(hits)
        cover = keyword_coverage(union_ctx, a)  # == rag_coverage в eval-гейте
        covers_one = max(keyword_coverage(h["text"], a) for h in hits)
        mode = "rag" if (_h(q) % 100) < round(args.p_oracle * 100) else "memory"
        if mode == "rag":
            ctx = union_ctx
            n_rag += 1
            if covers_one >= ORACLE_MIN:
                n_oracle += 1
        else:
            ch = str(s.get("meta", {}).get("chapter", ""))
            foreign = [d for k, ds in foreign_by_key.items() if k != ch for d in ds]
            if len(foreign) < N_DISTRACTOR:
                print("ОШИБКА: слишком мало чужих чанков для дистракторов",
                      file=sys.stderr)
                return 2
            pick = sorted(range(len(foreign)),
                          key=lambda i: _h(q + "#" + str(i)))[:N_DISTRACTOR]
            ctx = make_context([foreign[i] for i in pick])
            n_memory += 1
        union_covers.append(cover)
        ctx_chars.append(len(ctx))
        out_rows.append({
            "instruction": q, "output": a, "context": ctx,
            "meta": {**s.get("meta", {}), "raft_mode": mode,
                     "oracle_found": bool(covers_one >= ORACLE_MIN),
                     "rag_union_cover": round(cover, 4),
                     "ctx_chars": len(ctx)},
        })

    if len(out_rows) != len(train_rows):
        print("ОШИБКА: число пар изменилось — fail-loud", file=sys.stderr)
        return 2
    rag_share = n_rag / len(out_rows)
    if abs(rag_share - args.p_oracle) > 0.03:
        print(f"ОШИБКА: доля rag {rag_share:.3f} отклонилась от P="
              f"{args.p_oracle}", file=sys.stderr)
        return 2
    oracle_share = n_oracle / max(n_rag, 1)
    if oracle_share < 0.35:
        print(f"ОШИБКА: оракул найден лишь в {oracle_share:.2f} rag-примеров — "
              "ретривер не тянет корпус, чинить поиск, а не молчать",
              file=sys.stderr)
        return 2

    val_src = ROOT / args.val
    if not val_src.exists():
        print(f"ОШИБКА: нет {val_src}", file=sys.stderr)
        return 2
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "train.jsonl").open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out_dir / "val.jsonl").write_bytes(val_src.read_bytes())  # бит-в-байт

    union_sorted = sorted(union_covers)
    mid = union_sorted[len(union_sorted) // 2]
    stats = {
        "version": "v4-raft",
        "recipe": "RAFT (arXiv:2403.10131), P_oracle="
                  f"{args.p_oracle}, дистракторы={N_DISTRACTOR} чужих глав",
        "train": len(out_rows),
        "val": "бит-в-байт " + args.val,
        "modes": {"rag": n_rag, "memory": n_memory},
        "oracle_share_rag": round(oracle_share, 4),
        "rag_union_cover_mean": round(sum(union_covers) / len(union_covers), 4),
        "rag_union_cover_median": round(mid, 4),
        "rag_union_cover_min": round(min(union_covers), 4),
        "ctx_chars_mean": round(sum(ctx_chars) / len(ctx_chars), 1),
        "ctx_chars_max": max(ctx_chars),
        "determinism": "sha256(instruction): режим и выбор дистракторов",
    }
    (out_dir / "dataset_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
