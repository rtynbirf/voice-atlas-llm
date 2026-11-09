# -*- coding: utf-8 -*-
"""
Формат промпта Атлас-LLM.

Единый детерминированный шаблон «Вопрос/Ответ» — работает с любым
токенизатором (включая модели без chat-шаблона, например GPT-2).
Разделение prompt/answer нужно для маскировки лосса: модель учится
генерировать только ответ, а не вопрос.

Формат (вслоту):
    {system}\nВопрос: {instruction}\nОтвет:{answer}

Формат с заземлением (v4, волна «RAFT-Гибрид»; ровно тот же, что на
инференсе eval_qa.py / chat_cli.py):
    {system}+Справка из атласа...\nВопрос: ...\nОтвет: ...

Одна точка правды: GROUNDING_HEADER / make_context / grounded_system
используются сборщиком RAFT-корпуса, тренером, эвалом и CLI-чатом —
train и inference физически не могут разъехаться.
"""

MARK_Q = "\nВопрос: "
MARK_A = "\nОтвет:"

# Заголовок справки: единственный источник (раньше был скопирован в
# eval_qa.py и chat_cli.py — теперь все берут отсюда, байт-в-байт).
GROUNDING_HEADER = "\n\nСправка из атласа (используй, но не выдумывай сверх неё):\n"


def make_context(hits: list[dict], max_chars: int = 2400) -> str:
    """Чанки ретривера -> текст справки. Переехало из chat_cli.py без
    изменений (кэп 2400 символов, как на инференсе с волны «Гибрид»)."""
    parts = []
    for h in hits:
        parts.append(f"[{h['id']}] {h['text']}")
    ctx = "\n\n".join(parts)
    return ctx[:max_chars]


def grounded_system(system: str, context: str) -> str:
    """Системный промпт со справкой ретривера — байт-в-байт как на инференсе."""
    return system.strip() + GROUNDING_HEADER + context


def build_prompt(system: str, instruction: str) -> str:
    """Текст, который подаётся на вход модели при инференсе."""
    return f"{system.strip()}{MARK_Q}{instruction.strip()}{MARK_A}"


def build_training_pair(system: str, instruction: str, output: str,
                        context: str | None = None) -> tuple[str, str]:
    """(prompt_text, answer_text) для тренировочного примера.

    context — справка ретривера (RAFT-корпус v4): промпт строится ровно
    как на инференсе. answer_text начинается с одного пробела —
    разделитель после «Ответ:»; EOS добавляет тренер отдельно.
    """
    sys_text = grounded_system(system, context) if context else system
    prompt = build_prompt(sys_text, instruction)
    answer = f" {output.strip()}"
    return prompt, answer


def split_generated(text: str, system: str) -> str:
    """Достаёт ответ из сырой генерации модели.

    Ищет маркер «Ответ:» после системного промпта и обрезает всё после
    следующего «Вопрос:» (модель иногда продолжает диалог сама).
    """
    marker = build_prompt(system, "")
    if text.startswith(marker):
        text = text[len(marker):]
    else:
        idx = text.find(MARK_A)
        if idx != -1:
            text = text[idx + len(MARK_A):]
    if MARK_Q in text:
        text = text.split(MARK_Q)[0]
    return text.strip()
