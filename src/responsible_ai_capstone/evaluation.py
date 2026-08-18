"""Small labeled retrieval evaluation for the capstone's separate corpus."""

from __future__ import annotations

from typing import Any

from .index import EvidenceIndex


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_retrieval(
    questions: list[dict[str, Any]],
    index: EvidenceIndex,
    *,
    top_k: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Evaluate labeled source/citation retrieval and explicit abstention cases.

    This is a small regression set for the capstone's intentionally separate
    demo corpus.  It measures retrieval only; it does not evaluate provider
    generation, claim support, or generalization.
    """
    rows: list[dict[str, Any]] = []
    for item in questions:
        question = str(item["question"])
        answerable = bool(item.get("answerable", False))
        expected_source = item.get("expected_source")
        expected_citation = item.get("expected_citation")
        results = index.retrieve(question, top_k=top_k)
        sources = [result.source for result in results]
        citations = [result.citation for result in results]
        source_rank = (
            next(
                (position for position, source in enumerate(sources, start=1)
                 if source == expected_source),
                None,
            )
            if expected_source
            else None
        )
        citation_rank = (
            next(
                (position for position, citation in enumerate(citations, start=1)
                 if citation == expected_citation),
                None,
            )
            if expected_citation
            else None
        )
        passed = (
            bool(results)
            and (source_rank is not None if expected_source else citation_rank is not None)
            if answerable
            else not results
        )
        rows.append(
            {
                "id": item.get("id"),
                "question": question,
                "answerable": answerable,
                "expected_source": expected_source,
                "expected_citation": expected_citation,
                "retrieved_sources": sources,
                "retrieved_citations": citations,
                "retrieved_count": len(results),
                "source_hit_at_k": source_rank is not None if expected_source else None,
                "citation_hit_at_k": citation_rank is not None if expected_citation else None,
                "source_rank": source_rank,
                "citation_rank": citation_rank,
                "no_evidence": not results,
                "passed": passed,
            }
        )

    answerable_rows = [row for row in rows if row["answerable"]]
    unanswerable_rows = [row for row in rows if not row["answerable"]]
    source_precision = [
        sum(source == row["expected_source"] for source in row["retrieved_sources"])
        / len(row["retrieved_sources"])
        for row in answerable_rows
        if row["expected_source"] and row["retrieved_sources"]
    ]
    reciprocal_ranks = [
        1 / row["source_rank"] if row["source_rank"] is not None else 0.0
        for row in answerable_rows
    ]
    metrics = {
        "questions": float(len(rows)),
        "answerable_questions": float(len(answerable_rows)),
        "unanswerable_questions": float(len(unanswerable_rows)),
        "source_hit_at_k": _mean(
            [float(row["source_hit_at_k"]) for row in answerable_rows]
        ),
        "mean_reciprocal_rank": _mean(reciprocal_ranks),
        "source_precision_at_k": _mean(source_precision),
        "unanswerable_no_evidence_rate": _mean(
            [float(row["no_evidence"]) for row in unanswerable_rows]
        ),
        "case_pass_rate": _mean([float(row["passed"]) for row in rows]),
    }
    return rows, metrics
