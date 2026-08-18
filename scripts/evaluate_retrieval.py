"""Run the small labeled retrieval regression set."""

from __future__ import annotations

import json
from pathlib import Path

from responsible_ai_capstone.evaluation import evaluate_retrieval
from responsible_ai_capstone.index import EvidenceIndex

if __name__ == "__main__":
    root = Path(__file__).parents[1]
    index = EvidenceIndex(root / "data" / "documents")
    questions = json.loads(
        (root / "evaluation" / "questions.json").read_text(encoding="utf-8")
    )
    rows, metrics = evaluate_retrieval(questions, index, top_k=3)
    report = {
        "corpus": {
            "path": "data/documents",
            "index": "deterministic TF-IDF",
            "chunk_count": len(index.chunks),
        },
        "metrics": metrics,
        "rows": rows,
    }
    report_path = root / "reports" / "retrieval_results.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    for row in rows:
        print(f"{'PASS' if row['passed'] else 'FAIL'}: {row['question']}")
    if not all(row["passed"] for row in rows):
        raise SystemExit("retrieval evaluation failed")
