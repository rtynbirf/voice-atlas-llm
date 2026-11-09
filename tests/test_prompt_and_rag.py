# -*- coding: utf-8 -*-
"""Тесты формата промпта и RAG-ретривера."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training.prompt_format import (  # noqa: E402
    build_prompt, build_training_pair, split_generated,
    make_context, grounded_system, GROUNDING_HEADER,
)
from inference.retriever import TfidfRetriever, chunk_markdown  # noqa: E402


def test_grounded_matches_inference_format():
    """v4 RAFT: grounding в train == grounding на инференсе, байт-в-байт."""
    system, ctx = "Ты эксперт.", "[a#0] Текст справки."
    expected = (system.strip()
                + "\n\nСправка из атласа (используй, но не выдумывай сверх неё):\n"
                + ctx)
    assert grounded_system(system, ctx) == expected
    assert GROUNDING_HEADER == "\n\nСправка из атласа (используй, но не выдумывай сверх неё):\n"


def test_make_context_cap_and_ids():
    hits = [{"id": f"a#{i}", "text": "x" * 1500} for i in range(3)]
    ctx = make_context(hits)
    assert len(ctx) == 2400
    assert ctx.startswith("[a#0] ")
    assert "[a#1]" in ctx


def test_training_pair_with_context():
    pt, at = build_training_pair("Ты эксперт.", "Вопрос?", "Ответ.",
                                 context="[a#0] Справка.")
    assert "Справка из атласа" in pt
    assert pt.endswith("Ответ:")
    assert at.startswith(" Ответ.")
    # без контекста — прежний вслотный формат
    pt2, _ = build_training_pair("Ты эксперт.", "Вопрос?", "Ответ.")
    assert "Справка из атласа" not in pt2


def test_prompt_format_roundtrip():
    system = "Ты эксперт."
    prompt = build_prompt(system, "Что такое тембр?")
    assert prompt.startswith("Ты эксперт.")
    assert "Вопрос: Что такое тембр?" in prompt
    assert prompt.endswith("Ответ:")

    prompt_text, answer_text = build_training_pair(system, "Что такое тембр?", "Это окраска голоса.")
    assert prompt_text.endswith("Ответ:")
    assert answer_text.startswith(" Это окраска")
    assert len(answer_text) > 5


def test_split_generated_cuts_followup_question():
    system = "Ты эксперт."
    full = build_prompt(system, "Вопрос?") + " Ответ модели.\nВопрос: Что дальше?\nОтвет: продолжение"
    assert split_generated(full, system) == "Ответ модели."


DOCS = [
    {"id": "a#0", "source": "a.md", "text": "Вокодер NSF-HiFiGAN принимает контур F0 и важен для певучести в RVC и so-vits-svc."},
    {"id": "b#0", "source": "b.md", "text": "Датасет LibriTTS-R содержит 585 часов английских аудиокниг под лицензией CC-BY-4.0."},
]


def test_tfidf_retriever_finds_relevant_chunk():
    r = TfidfRetriever(DOCS)
    hits = r.search("какой вокодер важен для пения", k=1)
    assert hits[0]["id"] == "a#0"
    hits = r.search("сколько часов в LibriTTS-R", k=1)
    assert hits[0]["id"] == "b#0"


def test_chunk_markdown_splits_long_sections():
    text = "# Заголовок\n" + ("Абзац про клонирование голоса и тембр. " * 200)
    chunks = chunk_markdown(text, "test.md")
    assert len(chunks) >= 2
    assert all(c["source"] == "test.md" for c in chunks)
