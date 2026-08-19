# Responsible AI Evidence Assistant — local containerized prototype

[![CI](https://github.com/vesselsystems/responsible-ai-capstone/actions/workflows/ci.yml/badge.svg)](https://github.com/vesselsystems/responsible-ai-capstone/actions/workflows/ci.yml)

This repository contains a small, runnable responsible-AI capstone. It retrieves passages from the Markdown files in `data/documents/`, returns source citations and inspectable excerpts, and can optionally ask an approved OpenAI-compatible endpoint to draft an answer.

**Scope:** this is a local/containerized prototype for learning and review. It is related to the [`governance-rag-assistant`](https://github.com/vesselsystems/governance-rag-assistant) retrieval work, but intentionally uses its own small corpus and index; evaluation results are not transferred between repositories. It is not a hosted deployment, authorization system, or production monitoring platform. It now includes configurable local authentication, an in-process per-client/IP limiter, request IDs, redacted structured request logs, and explicit configuration/readiness failures; these controls are not a claim of production readiness or multi-instance coordination. The local HTTP service was verified, but the approved Chrome DevTools browser tool was unavailable in this run, so no screenshot or hosted URL is claimed. No target platform or deployment credentials were authorized, so no cloud resource was created; the boundary remains the local/container package and documented checks, not a production deployment.

## Quick start without Docker

Run these commands from `projects/04_responsible_ai_capstone`:

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
uvicorn responsible_ai_capstone.api:app --reload --no-access-log
```

Open <http://127.0.0.1:8000/>. The default is deterministic evidence-only mode and needs no API key.

Example requests:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What belongs in an approval record?","top_k":3}'
curl http://127.0.0.1:8000/metrics
```

PowerShell users can replace the multiline `curl` command with `Invoke-RestMethod` or use the browser UI.

## Docker and Compose

The image embeds the corpus and browser assets beside the installed Python package. `CAPSTONE_CORPUS_DIR` and `CAPSTONE_STATIC_DIR` are set explicitly in the image and in Compose, so an installed-package layout does not rely on `__file__` pointing at the source checkout. The image declares a `/ready` healthcheck and runs as the non-root `app` user; Compose also uses a read-only root filesystem, drops Linux capabilities, enables no-new-privileges, and limits the service to 1 CPU, 512 MiB, and 128 processes for this local prototype. The embedded corpus and manifest pin are part of the local image rollback boundary.

```bash
docker build -t responsible-ai-capstone .
docker run --rm --publish 127.0.0.1:8000:8000 --read-only --tmpfs /tmp responsible-ai-capstone
```

Compose is usable without creating an untracked `.env` file:

```bash
docker compose up --build
```

Provider settings are optional. To try an approved compatible endpoint, copy `.env.example` to `.env` or export `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, and the matching exact `CAPSTONE_PROVIDER_ALLOWED_HOSTS` value before starting Compose. Provider URLs must use HTTPS and their host must be allowlisted. `.env` is ignored and secrets must not be committed. For a shared environment, inject provider credentials and `CAPSTONE_AUTH_TOKEN` from the environment's secret manager at runtime; do not bake them into an image, Compose file, logs, or documentation. See [`docs/deployment.md`](docs/deployment.md) for the variable contract and local embedded-corpus image rollback procedure.

## API and safety behavior

- `GET /health` reports process health, indexed chunk count, safe configuration, and non-secret corpus/index version metadata including the verified manifest SHA-256.
- `GET /ready` remains probe-friendly and returns `{"ready":true}` when the corpus, static assets, and critical configuration are valid. A failure returns HTTP 503 with safe check names; an enabled authentication policy without an injected token fails closed.
- `POST /ask` accepts a 3–2,000 character non-blank question and `top_k` from 1 to 5. It returns a request ID, answer mode, latency, citations, scores, bounded snippets, full retrieved chunks, and source/chunk metadata under the `retrieved-markdown-chunk-v1` evidence contract. When authentication is enabled, send `Authorization: Bearer <runtime-injected-token>`.
- `GET /metrics` returns process-local Prometheus text for request count, internal errors, no-evidence responses, provider fallbacks, authentication failures, rate-limit rejections, and average latency. `/ask` uses a configurable per-client/IP sliding window (60 requests per 60 seconds by default).
- Every response has an `X-Request-ID` header. The service emits JSON request events with method/path/status/timing and a pseudonymous client identifier; request bodies, query strings, authorization values, provider errors, and secrets are not logged.
- A question with no matching evidence returns an explicit no-evidence response.
- Provider/network errors, oversized or malformed provider payloads, empty or citation-only answers, instruction-like output, structurally uncited response segments, and answers without citations fall back to evidence-only mode with `fallback: true`.
- The provider boundary performs structural citation validation: citation tokens must exactly match retrieved evidence, and each sentence-like response segment must carry a retrieved citation. This does not establish semantic entailment or claim completeness; human review remains pending. The default evidence-only path does not call a provider and reports `fallback: false`.
- The browser renders answer and evidence values with DOM text APIs rather than interpolating them as HTML.

The optional provider is not required for the core demo. Do not place secrets, personal information, or unapproved production documents in the corpus.

## Verification and measured scope

The repository has a small deterministic corpus (the local `/health` check currently reports 2 indexed chunks) and a six-question labeled retrieval regression set. The set has four answerable and two explicitly unanswerable questions; the current local run records source hit@3 1.00, source precision@3 0.75, MRR 1.00, and an unanswerable no-evidence rate of 1.00. These are descriptive results for this tiny corpus and hand-authored set, not broad retrieval quality, answer quality, or an out-of-domain guarantee.

Run the checks with:

```bash
pytest -q
ruff check .
python scripts/verify_corpus_manifest.py
python scripts/validate_azure_template.py
python scripts/evaluate_retrieval.py
python scripts/local_verification.py --output docs/local_verification.md
```

The generated [`reports/retrieval_results.json`](reports/retrieval_results.json) records the labeled retrieval run. The latest local verification for this checkout is recorded in [`docs/local_verification.md`](docs/local_verification.md): 2 indexed chunks, a supported evidence-only request with one inspectable citation/snippet and returned latency field, an explicit unknown-question result, invalid-field rejection, and a safe static frontend check. Provider calls in that record were 0; the latency is one in-process observation, not a baseline.

```text
pytest -q  -> passed locally (the exact test count changes as coverage evolves)
ruff check . -> All checks passed
Docker -> not run locally; docker command unavailable
```

These checks demonstrate behavior covered by the repository tests; they are not evidence of production readiness, uptime, durable telemetry, or deployment. Local metrics and request logs reset or disappear with the process unless a separately configured managed collector retains them; they are diagnostic signals, not production monitoring. See [`docs/deployment.md`](docs/deployment.md) for the separate Azure wiring that would still be required.

## Further documentation

- [`docs/architecture.md`](docs/architecture.md) — local request flow, trust boundaries, and deployment gaps.
- [`docs/case_study.md`](docs/case_study.md) — evidence-based system narrative and limitations.
- [`docs/runbook.md`](docs/runbook.md) — local container operations and failure handling.
- [`docs/deployment.md`](docs/deployment.md) — corpus admission, secret-manager variables, inert Azure template, non-durable telemetry boundary, and local embedded-corpus image rollback guidance.
- [`deploy/azure-container-apps.yaml`](deploy/azure-container-apps.yaml) — inert ACA configuration with placeholders; not a deployment.
- [`monitoring/alerts.md`](monitoring/alerts.md) — available metrics and what is not implemented.

This is educational guidance, not legal advice, organizational policy, or approval for consequential decisions.

## License

The code and documentation are released under the [MIT License](LICENSE). Review the terms of any external corpus or provider used with the service separately.
