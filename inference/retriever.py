# -*- coding: utf-8 -*-
"""
TF-IDF ретривер по корпусу атласа — «долговременная память» Атлас-LLM.

Не требует скачивания моделей эмбеддингов (чистый scikit-learn), поэтому
работает даже в офлайн-CI. Символьные n-граммы устойчивы к русской
морфологии («вокодер» / «вокодеры»).

CLI:
    python inference/retriever.py "какие пороги SIM?"
    python inference/retriever.py "чем SVC отличается от SVS" --k 3
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATLAS_DIR = ROOT / "data" / "atlas"

MAX_CHUNK_CHARS = 1400


def chunk_markdown(text: str, source: str, max_chars: int = MAX_CHUNK_CHARS) -> list[dict]:
    """Атлас -> чанки по заголовкам/абзацам с перекрытием контекста."""
    sections = re.split(r"\n(?=#{1,3}\s)", text)
    chunks = []
    for sec in sections:
        sec = sec.strip()
        if len(sec) < 40:
            continue
        while len(sec) > max_chars:
            cut = sec.rfind("\n", 0, max_chars)
            cut = cut if cut > 400 else max_chars
            chunks.append(sec[:cut].strip())
            sec = sec[cut:].strip()
        if len(sec) >= 40:
            chunks.append(sec)
    return [{"id": f"{source}#{i}", "source": source, "text": c}
            for i, c in enumerate(chunks)]


def load_corpus(atlas_dir: Path = ATLAS_DIR) -> list[dict]:
    docs = []
    for fp in sorted(atlas_dir.glob("*.md")):
        docs.extend(chunk_markdown(fp.read_text(encoding="utf-8"), fp.name))
    return docs


class TfidfRetriever:
    def __init__(self, docs: list[dict]):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.docs = docs
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), max_features=120000,
            sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform([d["text"] for d in docs])

    def search(self, query: str, k: int = 4) -> list[dict]:
        qv = self.vectorizer.transform([query])
        scores = (self.matrix @ qv.T).toarray().ravel()
        top = scores.argsort()[::-1][:k]
        return [{**self.docs[i], "score": float(scores[i])} for i in top]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--k", type=int, default=3)
    args = ap.parse_args()
    docs = load_corpus()
    if not docs:
        print("Пустой корпус — сначала положи главы в data/atlas/", file=sys.stderr)
        return 2
    r = TfidfRetriever(docs)
    for hit in r.search(args.query, args.k):
        preview = hit["text"][:300].replace("\n", " ")
        print(f"--- {hit['id']} (score={hit['score']:.3f}) ---")
        print(preview + ("…" if len(hit["text"]) > 300 else ""))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
