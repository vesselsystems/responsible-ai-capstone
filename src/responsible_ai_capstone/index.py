"""Local, deterministic retrieval index for the capstone service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

SNIPPET_MAX_CHARS = 700


@dataclass(frozen=True)
class Evidence:
    source: str
    chunk_id: str
    text: str
    score: float

    @property
    def citation(self) -> str:
        return f"[{self.source}#{self.chunk_id}]"

    @property
    def snippet(self) -> str:
        """Return a bounded, verbatim preview of the retrieved chunk."""

        return self.text[:SNIPPET_MAX_CHARS].strip()


class EvidenceIndex:
    """Index Markdown documents and return source-traceable evidence."""

    def __init__(self, corpus_dir: Path, chunk_words: int = 160) -> None:
        self.corpus_dir = corpus_dir
        self.chunks: list[tuple[str, str, str]] = []
        for path in sorted(corpus_dir.glob("*.md")):
            words = path.read_text(encoding="utf-8").split()
            for index, start in enumerate(range(0, len(words), chunk_words)):
                text = " ".join(words[start : start + chunk_words])
                if text:
                    self.chunks.append((path.name, str(index), text))
        if not self.chunks:
            raise ValueError(f"No Markdown documents found in {corpus_dir}")
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform([chunk[2] for chunk in self.chunks])

    def retrieve(self, question: str, top_k: int = 3) -> list[Evidence]:
        if not question.strip() or top_k < 1:
            return []
        query = self.vectorizer.transform([question])
        scores = (self.matrix @ query.T).toarray().ravel()
        # Stable ordering makes equal-score results reproducible for reviewers.
        indices = np.argsort(-scores, kind="stable")[:top_k]
        return [
            Evidence(*self.chunks[index], float(scores[index]))
            for index in indices
            if scores[index] > 0
        ]
