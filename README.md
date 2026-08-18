# Responsible AI Evidence Assistant — Deployed Capstone

A production-minded capstone that turns the governance RAG work into a monitored API and simple front end. It follows the AI Career Training Plan's fourth project:

> Deployed, monitored capstone (API + simple front end).

The service retrieves evidence from a small governance corpus, returns citations, exposes health/readiness/metrics endpoints, records latency and no-evidence events, and can optionally call an approved OpenAI-compatible endpoint. It runs safely in evidence-only mode without an API key.

## Quick start

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
uvicorn responsible_ai_capstone.api:app --reload
```

Open <http://127.0.0.1:8000/> for the front end.

API examples:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl -X POST http://127.0.0.1:8000/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"What belongs in an approval record?\",\"top_k\":3}"
curl http://127.0.0.1:8000/metrics
```

Run tests and lint:

```bash
pytest
ruff check .
```

## Docker

```bash
docker build -t responsible-ai-capstone .
docker run --rm -p 8000:8000 responsible-ai-capstone
```

## Operational design

- `/health` reports process health and index size.
- `/ready` reports whether the corpus is loaded.
- `/ask` returns an answer, mode, citations, request ID, and latency.
- `/metrics` exposes Prometheus-compatible counters for requests, errors, no-evidence responses, and LLM fallbacks.
- The default mode is deterministic evidence-only output.
- Optional LLM generation is controlled by environment variables; secrets are never committed.
- A failed external LLM call falls back to evidence-only output rather than returning an ungrounded answer.

## Portfolio case study

The final case study should explain:

1. The user problem and why governance evidence matters.
2. The retrieval architecture and evaluation results.
3. The deployment and monitoring choices.
4. How responsible-use controls limit the system.
5. What remains unproven and what would be required before production use.

This is an educational capstone. It is not legal advice, an organizational policy, or a production authorization system.
