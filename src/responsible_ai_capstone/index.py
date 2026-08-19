"""Local, deterministic retrieval index for the capstone service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .corpus import (
    INDEX_VERSION,
    CorpusDocument,
    CorpusManifest,
    default_manifest_path,
    load_manifest,
    verify_manifest,
)

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
    """Index Markdown documents only after passing the corpus boundary."""

    @classmethod
    def empty(cls, corpus_dir: Path) -> "EvidenceIndex":
        """Create an unavailable index for a health/readiness failure path."""

        instance = cls.__new__(cls)
        instance.corpus_dir = Path(corpus_dir)
        instance.manifest_path = default_manifest_path(instance.corpus_dir)
        instance.manifest = None
        instance.manifest_sha256 = None
        instance.corpus_version = None
        instance.index_version = INDEX_VERSION
        instance.chunks = []
        instance.vectorizer = None
        instance.matrix = None
        instance._verified = False
        instance._require_manifest = True
        instance._require_checksum_lock = True
        instance._expected_manifest_sha256 = None
        instance._expected_corpus_version = None
        instance._manifest_documents = {}
        return instance

    def __init__(
        self,
        corpus_dir: Path,
        chunk_words: int = 160,
        *,
        allow_empty: bool = False,
        manifest_path: Path | None = None,
        require_manifest: bool = False,
        require_checksum_lock: bool = False,
        expected_manifest_sha256: str | None = None,
        expected_corpus_version: str | None = None,
    ) -> None:
        self.corpus_dir = Path(corpus_dir)
        self.manifest_path = Path(manifest_path) if manifest_path else default_manifest_path(
            self.corpus_dir
        )
        self.manifest: CorpusManifest | None = None
        self.manifest_sha256: str | None = None
        self.corpus_version: str | None = None
        self.index_version = INDEX_VERSION
        self.chunks: list[tuple[str, str, str]] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix: Any = None
        self._verified = False
        self._require_manifest = require_manifest
        self._require_checksum_lock = require_checksum_lock
        self._expected_manifest_sha256 = expected_manifest_sha256
        self._expected_corpus_version = expected_corpus_version
        self._manifest_documents: dict[Path, CorpusDocument] = {}

        try:
            self._load(chunk_words=chunk_words)
        except Exception:
            if not allow_empty:
                raise
            self._verified = False
            self.chunks.clear()
            self.vectorizer = None
            self.matrix = None

    def _load(self, *, chunk_words: int) -> None:
        manifest: CorpusManifest | None = None
        manifest_documents: dict[Path, CorpusDocument] = {}
        if self.manifest_path.is_file():
            manifest = load_manifest(self.manifest_path)
            manifest_documents = verify_manifest(
                manifest,
                self.corpus_dir,
                expected_manifest_sha256=self._expected_manifest_sha256,
                expected_corpus_version=self._expected_corpus_version,
                require_checksum_lock=self._require_checksum_lock,
            )
            files = sorted(manifest_documents, key=lambda path: path.as_posix())
        elif self._require_manifest:
            raise ValueError(f"Corpus manifest does not exist: {self.manifest_path}")
        else:
            files = sorted(
                (path for path in self.corpus_dir.rglob("*")
                 if path.is_file() and path.suffix.lower() == ".md"),
                key=lambda path: path.as_posix(),
            )

        for path in files:
            words = path.read_text(encoding="utf-8").split()
            try:
                source = path.resolve().relative_to(self.corpus_dir.resolve()).as_posix()
            except ValueError:
                source = path.name
            for index, start in enumerate(range(0, len(words), chunk_words)):
                text = " ".join(words[start : start + chunk_words])
                if text:
                    self.chunks.append((source, str(index), text))
        if not self.chunks:
            raise ValueError(f"No Markdown documents found in {self.corpus_dir}")

        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform([chunk[2] for chunk in self.chunks])
        self.manifest = manifest
        self.manifest_sha256 = manifest.sha256 if manifest else None
        self.corpus_version = manifest.corpus_version if manifest else None
        self._manifest_documents = manifest_documents
        self._verified = True

    def _manifest_is_unchanged(self) -> bool:
        """Re-check the immutable source boundary for every readiness/retrieval use."""

        if self.manifest is None:
            return self._verified
        try:
            current_manifest = load_manifest(self.manifest_path)
            current_documents = verify_manifest(
                current_manifest,
                self.corpus_dir,
                expected_manifest_sha256=self._expected_manifest_sha256,
                expected_corpus_version=self._expected_corpus_version,
                require_checksum_lock=self._require_checksum_lock,
            )
        except (OSError, UnicodeError, ValueError):
            return False
        return (
            current_manifest.sha256 == self.manifest_sha256
            and current_manifest.corpus_version == self.corpus_version
            and current_manifest.index_version == self.index_version
            and current_documents == self._manifest_documents
        )

    @property
    def ready(self) -> bool:
        """Return false when startup or a later manifest/checksum check failed."""

        return bool(
            self._verified
            and self.chunks
            and self.vectorizer is not None
            and self.matrix is not None
            and self._manifest_is_unchanged()
        )

    def retrieve(self, question: str, top_k: int = 3) -> list[Evidence]:
        if not question.strip() or top_k < 1 or not self.ready:
            return []
        assert self.vectorizer is not None
        assert self.matrix is not None
        query = self.vectorizer.transform([question])
        scores = (self.matrix @ query.T).toarray().ravel()
        # Stable ordering makes equal-score results reproducible for reviewers.
        indices = np.argsort(-scores, kind="stable")[:top_k]
        return [
            Evidence(*self.chunks[index], float(scores[index]))
            for index in indices
            if scores[index] > 0
        ]
