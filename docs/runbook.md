# Local operations runbook

This runbook covers the repository's local Python process and Docker Compose prototype. It is not a hosted-service or production incident runbook.

## Start and verify

From `projects/04_responsible_ai_capstone`:

```bash
# local Python process
python -m pip install -e ".[dev]"
uvicorn responsible_ai_capstone.api:app --host 127.0.0.1 --port 8000

# or the containerized prototype
docker compose up --build
```

Compose does not require `.env`. The optional provider variables are empty by default, and the published port is bound to `127.0.0.1` for local use. The image healthcheck calls `/ready`; the Compose service is non-root, read-only, capability-dropped, and has no automatic restart policy. Verify a running process with:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
curl -i http://127.0.0.1:8000/metrics
curl -i -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What belongs in an approval record?","top_k":1}'
```

Expected local behavior is HTTP 200, a nonzero chunk count, `{"ready":true}`, Prometheus text, and an `/ask` response with an evidence contract, citation, snippet, and source metadata. `/metrics` is process-local and resets when the process/container restarts.

## Request troubleshooting

1. Capture the request ID, timestamp, mode, returned citations, and latency. Do not capture a full question if it may contain sensitive information.
2. If `/ready` is false or startup fails, check that `CAPSTONE_CORPUS_DIR` exists and contains readable `.md` files. In the image it should be `/service/data/documents`.
3. If `/` fails, check `CAPSTONE_STATIC_DIR` and `index.html`. In the image it should be `/service/app/static`.
4. If a question has no matches, confirm the corpus contents and query wording. The expected response is an explicit no-evidence result, not a guessed answer.
5. If an optional provider fails, returns invalid JSON/shape/content, or cites a non-retrieved source, the expected mode is `evidence-only` with `fallback: true`. Check `capstone_llm_fallbacks_total`; do not disable the safe fallback to force a fluent answer.
6. If an internal exception still produces HTTP 500, use the request ID and server logs for diagnosis. The API intentionally returns a generic error detail and does not return provider exception text.

## Local rollback and data changes

Stop the process with `Ctrl+C` or `docker compose down`. Rebuild after code or corpus changes:

```bash
docker compose build --no-cache
docker compose up
```

For a reproducible code rollback, use a previously reviewed checkout and rerun `pytest` and `ruff check .`. Treat corpus edits as code changes: review them, keep them versioned, and rerun the relevant retrieval and citation tests. Do not place secrets, personal information, or unapproved production documents in `data/documents/`.

## What this runbook does not cover

The repository has no hosted deployment, authentication, authorization, durable log/metric store, rate limiter, secret manager, backup process, alert router, or multi-instance coordination. Before exposing a consequential service, add those controls and write an environment-specific runbook with owners, escalation paths, recovery objectives, and tested rollback procedures.
