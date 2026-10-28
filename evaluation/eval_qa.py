# -*- coding: utf-8 -*-
"""
Оценка Атлас-LLM на held-out QA (data/dataset/val.jsonl).

Метрики (адаптация гейтов качества атласа, глава 11, под текстовую домен-задачу):
  - token_f1: F1 по токенам ответа против эталона
  - keyword_coverage: доля содержательных слов эталона, покрытых ответом
  - refusal_rate: доля генераций с явным «не подтверждено/неизвестно»
    (по правилу честности системного промпта)

Запуск:
    python evaluation/eval_qa.py --adapter models/atlas-qwen-0.5b \
        --max-samples 30 --out evaluation/report.json
Режим без модели:
    python evaluation/eval_qa.py --retrieval-only --max-samples 30
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inference.retriever import TfidfRetriever, load_corpus  # noqa: E402
from training.prompt_format import build_prompt, split_generated  # noqa: E402

STOP_RU = {"и", "в", "не", "на", "что", "это", "как", "по", "из", "у", "же",
           "то", "за", "с", "а", "о", "к", "от", "до", "для", "при", "или"}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[а-яёa-z0-9]+", text.lower()) if t not in STOP_RU]


def token_f1(pred: str, ref: str) -> float:
    p, r = tokenize(pred), tokenize(ref)
    if not p or not r:
        return 0.0
    common = {}
    for t in r:
        common[t] = common.get(t, 0) + 1
    overlap = 0
    for t in p:
        if common.get(t, 0) > 0:
            overlap += 1
            common[t] -= 1
    if overlap == 0:
        return 0.0
    prec = overlap / len(p)
    rec = overlap / len(r)
    return 2 * prec * rec / (prec + rec)


def keyword_coverage(pred: str, ref: str) -> float:
    ref_kw = [t for t in tokenize(ref) if len(t) >= 4]
    if not ref_kw:
        return 0.0
    pred_l = pred.lower()
    hit = sum(1 for kw in ref_kw if kw in pred_l)
    return hit / len(ref_kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--base", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--val", default="data/dataset/val.jsonl")
    ap.add_argument("--max-samples", type=int, default=30)
    ap.add_argument("--max-new-tokens", type=int, default=300)
    ap.add_argument("--out", default="evaluation/report.json")
    ap.add_argument("--retrieval-only", action="store_true",
                    help="оценить только RAG-покрытие без генерации")
    args = ap.parse_args()

    val_path = ROOT / args.val
    rows = [json.loads(l) for l in val_path.open(encoding="utf-8") if l.strip()]
    rows = rows[: args.max_samples]
    retriever = TfidfRetriever(load_corpus())

    results, t0 = [], time.time()
    if args.retrieval_only:
        # v2 «Гибрид»: метрика = покрытие ключевых слов эталона КОНТЕКСТОМ,
        # который реально получает модель (union top-k), + top1 для сравнения
        # со старым протоколом.
        for row in rows:
            hits = retriever.search(row["instruction"], 3)
            top1 = hits[0]["text"].lower() if hits else ""
            union = " ".join(h["text"] for h in hits).lower()
            ref_kw = [t for t in tokenize(row["output"]) if len(t) >= 4]
            covered_top1 = sum(1 for kw in ref_kw if kw in top1) / max(len(ref_kw), 1)
            covered_union = sum(1 for kw in ref_kw if kw in union) / max(len(ref_kw), 1)
            results.append({"question": row["instruction"],
                            "rag_coverage_top1": covered_top1,
                            "rag_coverage": covered_union})
    else:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        system = (ROOT / "data/curated/system_prompt.txt").read_text(encoding="utf-8")
        if args.adapter:
            saved = Path(args.adapter) / "system_prompt.txt"
            if saved.exists():
                system = saved.read_text(encoding="utf-8")
        tokenizer = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            args.base, torch_dtype=torch.float32, trust_remote_code=True)
        if args.adapter:
            model = PeftModel.from_pretrained(model, args.adapter)
        model.eval()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)

        for row in rows:
            hits = retriever.search(row["instruction"], 3)
            ctx = "\n\n".join(f"[{h['id']}] {h['text']}" for h in hits)[:2400]
            grounded = (system.strip()
                        + "\n\nСправка из атласа (используй, но не выдумывай сверх неё):\n"
                        + ctx)
            prompt = build_prompt(grounded, row["instruction"])
            inputs = tokenizer(prompt, return_tensors="pt").to(device)
            with torch.no_grad():
                out = model.generate(
                    **inputs, max_new_tokens=args.max_new_tokens, do_sample=False,
                    pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
            pred = split_generated(tokenizer.decode(out[0], skip_special_tokens=True),
                                   grounded)
            results.append({
                "question": row["instruction"],
                "reference": row["output"],
                "prediction": pred,
                "token_f1": token_f1(pred, row["output"]),
                "keyword_coverage": keyword_coverage(pred, row["output"]),
                "honest_uncertainty": bool(
                    re.search(r"не подтвержд|неизвестн|не проверен", pred.lower())),
            })

    agg = {}
    if results and "token_f1" in results[0]:
        agg["mean_token_f1"] = sum(r["token_f1"] for r in results) / len(results)
        agg["mean_keyword_coverage"] = sum(r["keyword_coverage"] for r in results) / len(results)
        agg["honest_uncertainty_rate"] = sum(
            1 for r in results if r.get("honest_uncertainty")) / len(results)
    if results and "rag_coverage" in results[0]:
        agg["mean_rag_coverage"] = sum(r["rag_coverage"] for r in results) / len(results)
    agg["n"] = len(results)
    agg["elapsed_sec"] = round(time.time() - t0, 1)

    report = {"mode": "retrieval_only" if args.retrieval_only else "generated",
              "adapter": args.adapter, "aggregate": agg, "details": results}
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(agg, ensure_ascii=False, indent=2))
    print(f"[eval] отчёт: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
