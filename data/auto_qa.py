# -*- coding: utf-8 -*-
"""
Автогенераторы QA-пар из глав атласа (расширение корпуса, волна «Гибрид»).

Источники (кроме глоссария 18 — он в build_dataset):
  1. Таблицы «**Таблица N. Название**» + markdown-таблица -> QA по столбцам
     (лицензия, объём, гейты, требования) + сводная QA по строке.
  2. Законы «**Закон N. Название.** Текст» (глава 13) -> QA на формулировку.
  3. Жирные термины «**Термин** — определение» / «**Термин**: определение»
     -> «Что такое Термин?» (главы 4–10, 12, 14, 17).

Все пары детерминированы (порядок = порядок в файлах), meta хранит главу,
тему и файл — антиутечечный сплит по главам работает как раньше.
Fail-loud: если экстрактор не нашёл НИЧЕГО в главе, где по разметке
должен (таблица/закон) — RaiseValueError, молчаливых пропусков нет.
"""
import re
from pathlib import Path

# --- парсеры разметки ---

TABLE_TITLE = re.compile(r"\*\*Таблица\s+\d+\.\s*([^*]+?)\*\*", re.M)
TABLE_BODY = re.compile(
    r"(\n\|[^\n]+\|\n\|[ :\-\|]+\|\n(?:\|[^\n]*\|\n?)+)", re.M)
LAW = re.compile(r"\*\*Закон\s+(\d+)\.\s*([^*]+?)\.\*\*\s*([^\n]+)")
BOLD_TERM = re.compile(r"(?:^|\n)\s*(?:-+\s*)?\*\*([А-ЯЁA-Z][^*\n]{1,60}?)\*\*\s*[—:-]\s*([^\n]+)")


def _clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell.replace("**", "").strip())


def extract_tables(atlas_dir: Path) -> list[dict]:
    """QA из всех таблиц атласа: атрибутные (по заголовкам столбцов) + сводная.

    Заголовок «**Таблица N. Название**» опционален: если перед телом таблицы
    маркера нет (разметка атласа неоднородна — напр., глава 14), таблица
    получает автоматическое имя «Таблица главы N». Жёсткий fail только если
    тел таблиц нет вовсе (проверяется в extract_all)."""
    samples = []
    for fp in sorted(atlas_dir.glob("*.md")):
        mch = re.match(r"(\d+)", fp.name)
        chapter = int(mch.group(1)) if mch else "?"
        text = fp.read_text(encoding="utf-8")
        titles = [(m.start(), m.group(1).strip()) for m in TABLE_TITLE.finditer(text)]
        bodies = list(TABLE_BODY.finditer(text))
        for body in bodies:
            name = None
            for pos, t in titles:
                if pos < body.start():
                    name = t
            if name is None:
                name = f"Таблица главы {chapter}"
            lines = [l for l in body.group(1).strip().splitlines()
                     if l.strip().startswith("|")]
            if len(lines) < 3:
                continue
            headers = [_clean(c) for c in lines[0].strip("|").split("|")]
            for line in lines[2:]:
                cells = [_clean(c) for c in line.strip("|").split("|")]
                if len(cells) != len(headers):
                    continue
                subject = cells[0]
                if not subject or subject in ("---", "—"):
                    continue
                row_full = "; ".join(f"{h}: {v}" for h, v in zip(headers, cells))
                base_meta = {"chapter": chapter, "topic": "table_qa",
                             "source": fp.name, "table": name}
                # сводная QA — что таблица говорит про объект
                samples.append({
                    "instruction": f"Что сказано в атласе про «{subject}» (таблица «{name}»)?",
                    "output": f"{subject}: {row_full}.",
                    "meta": dict(base_meta),
                })
                # атрибутные QA — по столбцам-ключевым словам
                for j, h in enumerate(headers):
                    if j == 0 or not cells[j]:
                        continue
                    hl = h.lower()
                    if "лиценз" in hl:
                        q, a = f"Какая лицензия у {subject}?", cells[j]
                    elif "объ" in hl or "час" in hl or "размер" in hl:
                        q, a = f"Какой объём у {subject}?", cells[j]
                    elif "гейт" in hl or "порог" in hl or "целев" in hl:
                        q, a = f"Какой гейт/порог для «{h}» ({subject})?", cells[j]
                    elif "язык" in hl:
                        q, a = f"Какие языки у {subject}?", cells[j]
                    else:
                        continue
                    samples.append({
                        "instruction": q,
                        "output": f"{subject} — {h}: {a}.",
                        "meta": dict(base_meta),
                    })
    return samples


def extract_laws(atlas_dir: Path) -> list[dict]:
    """QA из законов (глава 13): формулировка и противоядие."""
    samples = []
    for fp in sorted(atlas_dir.glob("13_*.md")):
        chapter = 13
        text = fp.read_text(encoding="utf-8")
        found = 0
        for m in LAW.finditer(text):
            num, name, body = m.group(1), m.group(2).strip(), m.group(3).strip()
            found += 1
            samples.append({
                "instruction": f"Сформулируй закон {num} атласа «не испорти оригинал».",
                "output": f"Закон {num}. {name}. {body}",
                "meta": {"chapter": chapter, "topic": "law_qa", "source": fp.name},
            })
            samples.append({
                "instruction": f"О чём закон {num} «{name}» — в чём суть?",
                "output": f"Закон {num} («{name}»): {body}",
                "meta": {"chapter": chapter, "topic": "law_qa", "source": fp.name},
            })
        if found < 7:
            raise ValueError(f"{fp.name}: найдено законов {found} (<7) — "
                             "разметка главы изменилась (fail-loud)")
    return samples


SKIP_BOLD_CHAPTERS = {13, 18}  # законы и глоссарий — свои экстракторы


def extract_bold_terms(atlas_dir: Path) -> list[dict]:
    """«**Термин** — определение» -> «Что такое Термин?» (кроме гл. 13/18)."""
    samples = []
    for fp in sorted(atlas_dir.glob("*.md")):
        m = re.match(r"(\d+)", fp.name)
        if not m or int(m.group(1)) in SKIP_BOLD_CHAPTERS:
            continue
        chapter = int(m.group(1))
        text = fp.read_text(encoding="utf-8")
        seen_terms = set()
        for m2 in BOLD_TERM.finditer(text):
            term, desc = _clean(m2.group(1)), m2.group(2).strip()
            if term.lower() in seen_terms or len(desc) < 30:
                continue
            if any(ch in term.lower() for ch in ("http", "таблица")):
                continue
            seen_terms.add(term.lower())
            samples.append({
                "instruction": f"Что такое {term} (атлас, глава {chapter})?",
                "output": f"{term} — {desc}",
                "meta": {"chapter": chapter, "topic": "bold_qa", "source": fp.name},
            })
    return samples


def extract_all(atlas_dir: Path) -> dict[str, list[dict]]:
    tables = extract_tables(atlas_dir)
    laws = extract_laws(atlas_dir)
    bolds = extract_bold_terms(atlas_dir)
    if not tables:
        raise ValueError("extract_tables: 0 пар — атлас пуст или парсер сломан")
    if not laws:
        raise ValueError("extract_laws: 0 пар")
    if not bolds:
        raise ValueError("extract_bold_terms: 0 пар")
    return {"table_qa": tables, "law_qa": laws, "bold_qa": bolds}
