# -*- coding: utf-8 -*-
"""
Формат промпта Атлас-LLM.

Единый детерминированный шаблон «Вопрос/Ответ» — работает с любым
токенизатором (включая модели без chat-шаблона, например GPT-2).
Разделение prompt/answer нужно для маскировки лосса: модель учится
генерировать только ответ, а не вопрос.

Формат:
    {system}\nВопрос: {instruction}\nОтвет:{answer}
"""

MARK_Q = "\nВопрос: "
MARK_A = "\nОтвет:"


def build_prompt(system: str, instruction: str) -> str:
    """Текст, который подаётся на вход модели при инференсе."""
    return f"{system.strip()}{MARK_Q}{instruction.strip()}{MARK_A}"


def build_training_pair(system: str, instruction: str, output: str) -> tuple[str, str]:
    """(prompt_text, answer_text) для тренировочного примера.

    answer_text начинается с одного пробела — разделитель после «Ответ:»;
    EOS добавляет тренер отдельно.
    """
    prompt = build_prompt(system, instruction)
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
