"""Versioned local corpus verification for the capstone index.

The service never downloads corpus content.  The checked-in manifest records the
small approved snapshot, and the companion ``.sha256`` file pins the manifest
itself.  Loading and readiness both re-verify those boundaries so a changed,
missing, or untracked document cannot silently remain indexed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

MANIFEST_FILENAME: Final[str] = "corpus_manifest.json"
MANIFEST_CHECKSUM_FILENAME: Final[str] = "corpus_manifest.sha256"
MANIFEST_SCHEMA_VERSION: Final[int] = 1
INDEX_VERSION: Final[str] = "tfidf-markdown-v1"
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{64}$")
_VERSION_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


@dataclass(frozen=True)
class CorpusDocument:
    """One local document and the digest recorded for its exact bytes."""

    path: str
    sha256: str


@dataclass(frozen=True)
class CorpusManifest:
    """Validated metadata for one reproducible corpus/index boundary."""

    schema_version: int
    corpus_id: str
    corpus_version: str
    index_version: str
    documents: tuple[CorpusDocument, ...]
    path: Path

    @property
    def sha256(self) -> str:
        """Return the digest of the manifest bytes, not the document contents."""

        return sha256_file(self.path)

    @classmethod
    def from_path(cls, path: Path) -> "CorpusManifest":
        path = Path(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise ValueError(f"Could not read corpus manifest {path}") from error
        except json.JSONDecodeError as error:
            raise ValueError(f"Corpus manifest {path} is not valid JSON") from error

        if not isinstance(raw, dict):
            raise ValueError("Corpus manifest must be a JSON object")
        if raw.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported corpus manifest schema_version; expected "
                f"{MANIFEST_SCHEMA_VERSION}"
            )

        corpus_id = raw.get("corpus_id")
        corpus_version = raw.get("corpus_version")
        index_version = raw.get("index_version")
        for field, value in (
            ("corpus_id", corpus_id),
            ("corpus_version", corpus_version),
            ("index_version", index_version),
        ):
            if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
                raise ValueError(f"Corpus manifest {field} must be a safe non-empty version label")

        raw_documents = raw.get("documents")
        if not isinstance(raw_documents, list) or not raw_documents:
            raise ValueError("Corpus manifest documents must be a non-empty list")
        documents: list[CorpusDocument] = []
        for raw_document in raw_documents:
            if not isinstance(raw_document, dict):
                raise ValueError("Each corpus manifest document must be an object")
            document_path = raw_document.get("path")
            digest = raw_document.get("sha256")
            if not isinstance(document_path, str) or not document_path.strip():
                raise ValueError("Corpus manifest document path must be a non-empty string")
            if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                raise ValueError(
                    f"Corpus manifest sha256 for {document_path!r} must be 64 "
                    "hexadecimal characters"
                )
            documents.append(CorpusDocument(document_path, digest.lower()))

        paths = [document.path for document in documents]
        if len(paths) != len(set(paths)):
            raise ValueError("Corpus manifest document paths must be unique")
        return cls(
            schema_version=MANIFEST_SCHEMA_VERSION,
            corpus_id=corpus_id,
            corpus_version=corpus_version,
            index_version=index_version,
            documents=tuple(documents),
            path=path,
        )


def sha256_file(path: Path) -> str:
    """Hash a file in bounded blocks so verification does not load it all at once."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> CorpusManifest:
    """Load and validate a manifest without accessing any network resource."""

    return CorpusManifest.from_path(Path(path))


def default_manifest_path(corpus_dir: Path) -> Path:
    """Return the conventional manifest beside ``data/documents``."""

    return Path(corpus_dir).resolve().parent / MANIFEST_FILENAME


def _manifest_document_path(
    document: CorpusDocument,
    manifest: CorpusManifest,
    corpus_dir: Path,
) -> Path:
    relative = Path(document.path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Corpus manifest path escapes its data boundary: {document.path!r}")

    candidates = (manifest.path.parent / relative, Path(corpus_dir) / relative)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _load_manifest_checksum(path: Path) -> str:
    """Read a deterministic ``sha256  filename`` lock-file format."""

    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except OSError as error:
        raise ValueError(f"Could not read corpus manifest checksum {path}") from error
    entries = [line for line in lines if line]
    if len(entries) != 1:
        raise ValueError(f"Corpus manifest checksum {path} must contain one entry")
    parts = entries[0].split()
    if len(parts) not in {1, 2} or not _SHA256_RE.fullmatch(parts[0]):
        raise ValueError(f"Corpus manifest checksum {path} is not valid sha256 output")
    if len(parts) == 2 and Path(parts[1].lstrip("*")) != Path(MANIFEST_FILENAME):
        raise ValueError(f"Corpus manifest checksum {path} names an unexpected file")
    return parts[0].lower()


def _discover_documents(corpus_dir: Path) -> set[Path]:
    """Discover every Markdown file below the corpus boundary.

    Manifest paths may identify nested documents, so membership checks must use the
    same recursive scope rather than silently ignoring a new file in a subdirectory.
    """

    try:
        paths = list(Path(corpus_dir).rglob("*"))
    except OSError:
        return set()
    return {
        path.resolve()
        for path in paths
        if path.is_file() and path.suffix.lower() == ".md"
    }


def _display_document_path(path: Path, corpus_dir: Path) -> str:
    """Render a deterministic path in a manifest error, including subdirectories."""

    try:
        return path.relative_to(corpus_dir).as_posix()
    except ValueError:
        return path.as_posix()


def verify_manifest(
    manifest: CorpusManifest,
    corpus_dir: Path,
    *,
    expected_manifest_sha256: str | None = None,
    expected_corpus_version: str | None = None,
    expected_index_version: str = INDEX_VERSION,
    require_checksum_lock: bool = False,
) -> dict[Path, CorpusDocument]:
    """Verify manifest bytes, versions, exact membership, and document checksums.

    ``expected_manifest_sha256`` is the deployment pin.  When it is absent, a
    sibling ``corpus_manifest.sha256`` lock file is used when present.  The
    caller can require that lock for an immutable image boundary.
    """

    if expected_manifest_sha256 is not None and not _SHA256_RE.fullmatch(
        expected_manifest_sha256
    ):
        raise ValueError("Expected corpus manifest sha256 must be 64 hexadecimal characters")
    if expected_index_version != manifest.index_version:
        raise ValueError(
            "Corpus manifest index_version does not match the running index version"
        )
    if expected_corpus_version is not None and expected_corpus_version != manifest.corpus_version:
        raise ValueError("Corpus manifest corpus_version does not match the configured version")

    actual_manifest_sha256 = manifest.sha256
    lock_path = manifest.path.with_name(MANIFEST_CHECKSUM_FILENAME)
    locked_manifest_sha256: str | None = None
    if lock_path.is_file():
        locked_manifest_sha256 = _load_manifest_checksum(lock_path)
    elif require_checksum_lock and expected_manifest_sha256 is None:
        raise ValueError("Corpus manifest checksum lock is missing")

    if locked_manifest_sha256 is not None and locked_manifest_sha256 != actual_manifest_sha256:
        raise ValueError("Corpus manifest checksum mismatch")
    if (
        expected_manifest_sha256 is not None
        and expected_manifest_sha256.lower() != actual_manifest_sha256
    ):
        raise ValueError("Configured corpus manifest checksum mismatch")
    if (
        expected_manifest_sha256 is not None
        and locked_manifest_sha256 is not None
        and expected_manifest_sha256.lower() != locked_manifest_sha256
    ):
        raise ValueError("Configured corpus manifest checksum disagrees with checksum lock")

    resolved_corpus_dir = Path(corpus_dir).resolve()
    entries: dict[Path, CorpusDocument] = {}
    for document in manifest.documents:
        path = _manifest_document_path(document, manifest, resolved_corpus_dir)
        resolved_path = path.resolve()
        if resolved_corpus_dir not in resolved_path.parents:
            raise ValueError(f"Corpus manifest path escapes its data boundary: {document.path!r}")
        if not path.is_file():
            raise ValueError(f"Corpus manifest document does not exist: {document.path!r}")
        if path.suffix.lower() != ".md":
            raise ValueError(f"Corpus manifest document is not Markdown: {document.path!r}")
        if sha256_file(path) != document.sha256:
            raise ValueError(
                f"Corpus document checksum mismatch for {document.path!r}; review the snapshot"
            )
        if resolved_path in entries:
            raise ValueError(f"Corpus manifest resolves multiple entries to {path}")
        entries[resolved_path] = document

    discovered = _discover_documents(resolved_corpus_dir)
    missing = sorted(set(entries) - discovered)
    untracked = sorted(discovered - set(entries))
    if missing:
        names = ", ".join(_display_document_path(path, resolved_corpus_dir) for path in missing)
        raise ValueError(f"Corpus manifest documents are not in the corpus directory: {names}")
    if untracked:
        names = ", ".join(_display_document_path(path, resolved_corpus_dir) for path in untracked)
        raise ValueError(f"Corpus files are missing from the manifest: {names}")
    return entries


__all__ = [
    "INDEX_VERSION",
    "MANIFEST_CHECKSUM_FILENAME",
    "MANIFEST_FILENAME",
    "CorpusDocument",
    "CorpusManifest",
    "default_manifest_path",
    "load_manifest",
    "sha256_file",
    "verify_manifest",
]
