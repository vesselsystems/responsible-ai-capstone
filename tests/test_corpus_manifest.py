import json
import shutil
from pathlib import Path

import pytest

from responsible_ai_capstone import api
from responsible_ai_capstone.corpus import load_manifest, sha256_file, verify_manifest
from responsible_ai_capstone.index import EvidenceIndex

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCUMENTS = DATA / "documents"
MANIFEST = DATA / "corpus_manifest.json"


def _copy_boundary(tmp_path: Path) -> tuple[Path, Path]:
    data_dir = tmp_path / "data"
    documents_dir = data_dir / "documents"
    documents_dir.mkdir(parents=True)
    for source in DOCUMENTS.glob("*.md"):
        shutil.copyfile(source, documents_dir / source.name)
    shutil.copyfile(MANIFEST, data_dir / MANIFEST.name)
    shutil.copyfile(DATA / "corpus_manifest.sha256", data_dir / "corpus_manifest.sha256")
    return documents_dir, data_dir / MANIFEST.name


def test_tracked_corpus_manifest_verifies_exactly_two_documents() -> None:
    manifest = load_manifest(MANIFEST)
    entries = verify_manifest(manifest, DOCUMENTS, require_checksum_lock=True)

    assert manifest.corpus_version == "corpus-v1"
    assert manifest.index_version == "tfidf-markdown-v1"
    assert len(entries) == 2
    assert {path.name for path in entries} == {
        "capstone_governance.md",
        "capstone_incident_response.md",
    }
    assert manifest.sha256 == "b137780a7e9a62e59fbb196c309dfff86fde30817797372470580237f441c532"
    assert all(len(document.sha256) == 64 for document in manifest.documents)


def test_index_becomes_unready_when_a_document_checksum_drifts(tmp_path: Path) -> None:
    documents_dir, manifest_path = _copy_boundary(tmp_path)
    index = EvidenceIndex(
        documents_dir,
        manifest_path=manifest_path,
        require_manifest=True,
        require_checksum_lock=True,
    )
    assert index.ready

    with (documents_dir / "capstone_governance.md").open("a", encoding="utf-8") as handle:
        handle.write(" drift")

    assert index.ready is False
    assert index.retrieve("approval record") == []


def test_index_startup_rejects_manifest_checksum_drift(tmp_path: Path) -> None:
    documents_dir, manifest_path = _copy_boundary(tmp_path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["corpus_version"] = "corpus-v2"
    manifest_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest checksum mismatch"):
        EvidenceIndex(
            documents_dir,
            manifest_path=manifest_path,
            require_manifest=True,
            require_checksum_lock=True,
        )


def test_untracked_document_is_not_admitted(tmp_path: Path) -> None:
    documents_dir, manifest_path = _copy_boundary(tmp_path)
    (documents_dir / "untracked.md").write_text("not reviewed", encoding="utf-8")

    with pytest.raises(ValueError, match="missing from the manifest"):
        EvidenceIndex(
            documents_dir,
            manifest_path=manifest_path,
            require_manifest=True,
            require_checksum_lock=True,
        )


def test_nested_untracked_document_is_not_admitted(tmp_path: Path) -> None:
    documents_dir, manifest_path = _copy_boundary(tmp_path)
    nested_dir = documents_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "untracked.md").write_text("not reviewed", encoding="utf-8")

    with pytest.raises(ValueError, match="nested/untracked.md"):
        EvidenceIndex(
            documents_dir,
            manifest_path=manifest_path,
            require_manifest=True,
            require_checksum_lock=True,
        )


def test_nested_manifest_document_is_admitted_and_keeps_relative_source(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    documents_dir = data_dir / "documents"
    nested_dir = documents_dir / "nested"
    nested_dir.mkdir(parents=True)
    nested_document = nested_dir / "review.md"
    nested_document.write_text("nested approval review", encoding="utf-8")
    manifest_path = data_dir / "corpus_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_id": "nested-test",
                "corpus_version": "corpus-v1",
                "index_version": "tfidf-markdown-v1",
                "documents": [
                    {
                        "path": "documents/nested/review.md",
                        "sha256": sha256_file(nested_document),
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "corpus_manifest.sha256").write_text(
        f"{sha256_file(manifest_path)}  corpus_manifest.json\n",
        encoding="utf-8",
    )

    index = EvidenceIndex(
        documents_dir,
        manifest_path=manifest_path,
        require_manifest=True,
        require_checksum_lock=True,
    )

    assert index.ready
    assert index.chunks[0][0] == "nested/review.md"


def test_health_exposes_only_non_secret_corpus_and_index_metadata() -> None:
    payload = api.health()
    configuration = payload["configuration"]

    assert configuration["corpus_version"] == "corpus-v1"
    assert configuration["corpus_manifest_sha256"] == sha256_file(MANIFEST)
    assert configuration["index_version"] == "tfidf-markdown-v1"
    assert payload["corpus_version"] == "corpus-v1"
    assert payload["corpus_manifest_sha256"] == configuration["corpus_manifest_sha256"]
    assert payload["index_version"] == "tfidf-markdown-v1"
    assert "auth_token" not in json.dumps(payload)
    assert "OPENAI_API_KEY" not in json.dumps(payload)


def test_readiness_fails_closed_when_loaded_boundary_reports_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "index_load_error", False)
    monkeypatch.setattr(api.index, "_manifest_is_unchanged", lambda: False)

    from fastapi.testclient import TestClient

    probe = TestClient(api.app).get("/ready")
    assert probe.status_code == 503
    assert probe.json()["ready"] is False
    assert probe.json()["checks"]["corpus"] is False
