import json
from pathlib import Path

from responsible_ai_capstone.evaluation import evaluate_retrieval
from responsible_ai_capstone.index import EvidenceIndex

ROOT = Path(__file__).parents[1]


def test_labeled_retrieval_set_covers_answerable_and_abstention_cases() -> None:
    index = EvidenceIndex(ROOT / "data" / "documents")
    questions = json.loads(
        (ROOT / "evaluation" / "questions.json").read_text(encoding="utf-8")
    )

    rows, metrics = evaluate_retrieval(questions, index)

    assert len(rows) == 6
    assert metrics["answerable_questions"] == 4
    assert metrics["unanswerable_questions"] == 2
    assert metrics["source_hit_at_k"] == 1.0
    assert metrics["unanswerable_no_evidence_rate"] == 1.0
    assert metrics["case_pass_rate"] == 1.0
    assert all(row["passed"] for row in rows)
