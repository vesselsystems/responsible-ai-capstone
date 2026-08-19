"""Verify the checked-in corpus manifest and print deterministic metadata."""

from __future__ import annotations

import json
from pathlib import Path

from responsible_ai_capstone.corpus import (
    load_manifest,
    verify_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data" / "corpus_manifest.json"
CORPUS_DIR = ROOT / "data" / "documents"


def main() -> None:
    """Fail closed on drift; emit no timestamps or environment-specific values."""

    manifest = load_manifest(MANIFEST_PATH)
    entries = verify_manifest(manifest, CORPUS_DIR, require_checksum_lock=True)
    result = {
        "corpus_id": manifest.corpus_id,
        "corpus_version": manifest.corpus_version,
        "index_version": manifest.index_version,
        "manifest_sha256": manifest.sha256,
        "verified_documents": len(entries),
        "verified_paths": sorted(document.path for document in manifest.documents),
        "network_access": False,
        "status": "verified",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
