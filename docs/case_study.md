# System note: a citation-first governance assistant

## Problem

Governance guidance is useful only when a reviewer can check the basis for an answer. A fluent answer without a source can turn a small documentation question into an unsupported policy decision. This capstone tests a narrower alternative: retrieve local guidance, show the passages, and make the no-evidence path explicit.

This repository is a learning artifact, not a production governance service. Its two Markdown documents are demo material and are not legal advice or an organization's policy.

## Approach

The prototype uses a deterministic TF-IDF index over bounded Markdown chunks. `POST /ask` returns the answer mode, request ID, latency, citation, similarity score, and the retrieved text. By default it creates an evidence-only draft and requires no external service.

An OpenAI-compatible provider is optional. The provider receives the question and retrieved context, but its result is accepted only when it has the expected response shape, non-empty text, at least one citation, and citations that exactly match the current retrieved evidence. A provider outage, malformed result, or invented citation falls back to the evidence-only draft.

The static browser is intentionally small. It builds evidence rows with DOM APIs and `textContent`, which avoids treating returned corpus or provider text as HTML.

## Evidence and results

The measured checks in this checkout are limited to behavior and packaging hygiene:

- `pytest -q`: 10 tests passed; the run emitted one deprecation warning from the installed Starlette/httpx test-client dependency.
- `ruff check .`: passed.
- The static check found no `innerHTML` use and found the `textContent` rendering path.
- `/health` reported 2 indexed chunks during the local verification run.

There is no held-out question set, labeled relevance data, representative traffic sample, or provider benchmark in this repository. Consequently, it does not claim hit@k, MRR, citation-faithfulness rate, answer quality, latency SLO, uptime, or provider reliability. The per-request latency field is instrumentation, not a measured baseline.

## Responsible-use controls

1. Retrieval is visible: the response includes the exact text excerpts used for the answer.
2. Unsupported questions return a clear no-evidence message.
3. Provider citations are checked against retrieved evidence before an LLM answer is exposed.
4. Provider failure is fail-closed to an evidence-only draft rather than an ungrounded answer.
5. Secrets are environment-only, and the tests do not call a real provider.
6. Users are told that this is demo guidance and a human remains responsible for consequential decisions.

## Limitations and next steps

The corpus is small, the retrieval baseline is lexical, metrics are process-local, and the UI/API have no authentication or rate limiting. There is no hosted environment or durable monitoring to evaluate. Before any consequential use, an owner would need an approved corpus and change process, held-out relevance and citation-faithfulness evaluations, adversarial tests, access controls, secret management, durable metrics/logs, alert routing, deployment/recovery controls, and a documented human review process.
