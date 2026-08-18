# System note: a citation-first governance assistant

## Problem

Governance guidance is useful only when a reviewer can check the basis for an answer. A fluent answer without a source can turn a small documentation question into an unsupported policy decision. This capstone tests a narrower alternative: retrieve local guidance, show the passages, and make the no-evidence path explicit.

This repository is a learning artifact, not a production governance service. Its two Markdown documents are demo material and are not legal advice or an organization's policy.

## Approach

The prototype uses a deterministic TF-IDF index over bounded Markdown chunks. `POST /ask` returns the answer mode, request ID, latency, citation, similarity score, a bounded verbatim snippet, the full retrieved chunk, and source metadata (Markdown filename and chunk ID). The response advertises the `retrieved-markdown-chunk-v1` evidence contract. By default it creates an evidence-only draft and does not call a provider.

An OpenAI-compatible provider is optional. The provider receives explicitly delimited untrusted context, but its result is accepted only when it has the expected response shape, bounded response size, substantive plain text, at least one citation, and citations that exactly match the current retrieved evidence. A provider outage, malformed or instruction-like result, or invented citation falls back to the evidence-only draft with `fallback: true`; default evidence-only responses have `fallback: false`.

The static browser is intentionally small. It builds evidence rows with DOM APIs and `textContent`, which avoids treating returned corpus or provider text as HTML.

## Evidence and results

The measured checks in this checkout are limited to behavior, a small labeled retrieval regression set, and local packaging hygiene. The generated [`local_verification.md`](local_verification.md) record captures an in-process run with provider variables cleared:

- `/health`: HTTP 200 with 2 indexed chunks; `/ready`: HTTP 200 with `ready=True`.
- A supported question: HTTP 200, `evidence-only`, `fallback=False`, one evidence item, citation `[capstone_incident_response.md#0]`, and a 700-character snippet.
- An unknown question: HTTP 200 with zero evidence items and the explicit no-evidence answer.
- An extra request field: HTTP 422. The frontend: HTTP 200 with DOM text APIs and no listed unsafe HTML API.
- Provider calls in that check: 0. It did not measure an external provider.
- `pytest -q`: 16 tests passed; the run emitted one deprecation warning from the installed Starlette/httpx test-client dependency.
- `ruff check .`: passed.

Docker was not run locally because the `docker` command was unavailable in this checkout. The CI workflow contains a container build, non-root assertion, readiness/health checks, and an evidence-only `/ask` smoke request; this repository does not claim that CI or a hosted environment has run.

The labeled set in [`../reports/retrieval_results.json`](../reports/retrieval_results.json) has four answerable and two unanswerable questions. Its local regression run records source hit@3 1.00, source precision@3 0.75, MRR 1.00, and unanswerable no-evidence rate 1.00. These figures are not a broad benchmark, citation-faithfulness rate, answer-quality result, out-of-domain detector, representative traffic sample, or provider benchmark. The per-request latency field is instrumentation, not a measured baseline.

## Responsible-use controls

1. Retrieval is visible: the response includes a bounded verbatim snippet, the exact retrieved chunk, and source/chunk metadata.
2. Unsupported questions return a clear no-evidence message.
3. Provider citations are checked against retrieved evidence before an LLM answer is exposed.
4. Provider failure is fail-closed to an evidence-only draft rather than an ungrounded answer, and the response marks configured-provider fallback explicitly.
5. Secrets are environment-only, and the tests do not call a real provider.
6. Users are told that this is demo guidance and a human remains responsible for consequential decisions.

## Limitations and next steps

The corpus is small, the retrieval baseline is lexical, metrics are process-local, and the UI/API have no authentication or rate limiting. There is no hosted environment or durable monitoring to evaluate. Before any consequential use, an owner would need an approved corpus and change process, held-out relevance and citation-faithfulness evaluations, adversarial tests, access controls, secret management, durable metrics/logs, alert routing, deployment/recovery controls, and a documented human review process.
