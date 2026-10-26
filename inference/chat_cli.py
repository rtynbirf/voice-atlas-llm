# -*- coding: utf-8 -*-
"""
Атлас-LLM: CLI-чат с RAG по корпусу атласа и опциональным LoRA-адаптером.

Режимы:
  --dry            только RAG (без загрузки модели; работает в CI/офлайн)
  --adapter PATH   подключить обученный LoRA-адаптер (models/atlas-qwen-0.5b)
  без --adapter    базовая модель из --base + RAG-контекст

Примеры:
  python inference/chat_cli.py --dry "чем SVC отличается от SVS?"
  python inference/chat_cli.py --base Qwen/Qwen2.5-0.5B-Instruct \
      --adapter models/atlas-qwen-0.5b "какие пороги SIM?"
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inference.retriever import TfidfRetriever, load_corpus  # noqa: E402
from training.prompt_format import build_prompt, split_generated  # noqa: E402


def make_context(hits: list[dict], max_chars: int = 2400) -> str:
    parts = []
    for h in hits:
        parts.append(f"[{h['id']}] {h['text']}")
    ctx = "\n\n".join(parts)
    return ctx[:max_chars]


def answer_dry(query: str, k: int) -> int:
    hits = TfidfRetriever(load_corpus()).search(query, k)
    print("=== RAG-режим (без генерации): релевантные главы атласа ===")
    for h in hits:
        print(f"\n--- {h['id']} (score={h['score']:.3f}) ---")
        print(h["text"][:600].replace("\n", " ") + "…")
    return 0


def answer_llm(query: str, base: str, adapter: str | None, k: int,
               max_new_tokens: int, temperature: float) -> int:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    system = (ROOT / "data/curated/system_prompt.txt").read_text(encoding="utf-8")
    retriever = TfidfRetriever(load_corpus())
    hits = retriever.search(query, k)
    context = make_context(hits)
    grounded_system = (
        system.strip()
        + "\n\nСправка из атласа (используй, но не выдумывай сверх неё):\n"
        + context
    )

    print(f"[chat] загрузка модели {base} ...", file=sys.stderr)
    tokenizer = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        base, torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        trust_remote_code=True)
    if adapter:
        from peft import PeftModel
        print(f"[chat] подключение адаптера {adapter}", file=sys.stderr)
        model = PeftModel.from_pretrained(model, adapter)
        # system_prompt.txt из адаптера приоритетнее локального
        sp = Path(adapter) / "system_prompt.txt"
        if sp.exists():
            system_saved = sp.read_text(encoding="utf-8")
            grounded_system = (
                system_saved.strip()
                + "\n\nСправка из атласа (используй, но не выдумывай сверх неё):\n"
                + context)
    model.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    prompt = build_prompt(grounded_system, query)
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=temperature > 0,
            temperature=max(temperature, 1e-4), top_p=0.9,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
    text = tokenizer.decode(out[0], skip_special_tokens=True)
    print("=== Атлас-LLM ===")
    print(split_generated(text, grounded_system))
    print("\n=== Источники атласа ===")
    for h in hits:
        print(f"- {h['id']} (score={h['score']:.3f})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--base", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--max-new-tokens", type=int, default=400)
    ap.add_argument("--temperature", type=float, default=0.2)
    args = ap.parse_args()
    if args.dry:
        return answer_dry(args.query, args.k)
    return answer_llm(args.query, args.base, args.adapter, args.k,
                      args.max_new_tokens, args.temperature)


if __name__ == "__main__":
    sys.exit(main())
