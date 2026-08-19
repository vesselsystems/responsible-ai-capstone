# Local operations runbook

This runbook covers the repository's local Python process and Docker Compose prototype.
It is not a hosted-service or production incident runbook.

## Start and verify

From `projects/04_responsible_ai_capstone`:

```bash
# local Python process
python -m pip install -e ".[dev]"
uvicorn responsible_ai_capstone.api:app --host 127.0.0.1 --port 8000 --no-access-log

# or the containerized prototype
docker compose up --build
```

Compose does not require `.env`. The optional provider variables are empty by default,
the auth policy is disabled by default, the in-process `/ask` limiter is enabled at 60
requests per 60 seconds, and the published port is bound to `127.0.0.1` for local use.
The image healthcheck calls `/ready`; the Compose service is non-root, read-only,
capability-dropped, and constrained to 1 CPU, 512 MiB, and 128 processes. There is no
automatic restart policy.

Verify a running process with:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
curl -i http://127.0.0.1:8000/metrics
curl -i -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What belongs in an approval record?","top_k":1}'
```

Expected local behavior is HTTP 200, a nonzero chunk count, `{"ready":true}`,
Prometheus text, and an `/ask` response with an evidence contract, citation, snippet,
source metadata, and `X-Request-ID`. `/metrics` is process-local and resets when the
process/container restarts.

## Authentication and rate-limit checks

To enable the optional Bearer-token gate, inject values outside source control:

```bash
CAPSTONE_AUTH_ENABLED=true CAPSTONE_AUTH_TOKEN="$TOKEN_FROM_SECRET_MANAGER" \
  uvicorn responsible_ai_capstone.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

The placeholder above is a shell variable reference, not a credential. Never put a real
value in this runbook, `.env.example`, a Dockerfile, or logs. `/health` and `/ready`
remain available to local probes. `/ask` and `/metrics` return HTTP 401 without the
correct runtime-injected Bearer token. If auth is enabled but the token is missing,
`/ready` returns HTTP 503 and protected requests return HTTP 503 rather than silently
disabling authentication.

The limiter runs before authentication on `/ask`, so failed credentials consume the
same admission budget as successful requests. It keys direct client IPs by default and
ignores spoofable forwarded headers. Only set `CAPSTONE_TRUST_PROXY_HEADERS=true` when a
trusted proxy owns and sanitizes `X-Forwarded-For`, and set
`CAPSTONE_TRUSTED_PROXY_CIDRS` to its exact IP/CIDR allowlist; the service refuses that
configuration without an allowlist. Configure `CAPSTONE_RATE_LIMIT_REQUESTS` and
`CAPSTONE_RATE_LIMIT_WINDOW_SECONDS` for a local exercise; HTTP 429 includes
`Retry-After`. This limiter is process-local and does not coordinate multiple workers.

## Request troubleshooting and safe logs

1. Use the `X-Request-ID` response header and, for `/ask`, the body `request_id` when
   correlating a request. Do not record a full question if it may contain sensitive data.
2. Structured request events contain only method, path, status, timing, outcome, and a
   pseudonymous client-IP hash. They intentionally omit request bodies, query strings,
   authorization values, provider response text, and exception details.
3. If `/ready` is false or startup is unhealthy, inspect its safe `checks` and `errors`
   fields. Check that `CAPSTONE_CORPUS_DIR` exists with readable `.md` files, the
   `corpus_manifest.json` and `corpus_manifest.sha256` boundary match, and that
   `CAPSTONE_CORPUS_VERSION`, `CAPSTONE_CORPUS_MANIFEST_SHA256`, and
   `CAPSTONE_INDEX_VERSION` match the reviewed pair. Run
   `python scripts/verify_corpus_manifest.py` before changing anything. Also check that
   `CAPSTONE_STATIC_DIR/index.html` is present. An auth token is required when auth is
   enabled. `/health` reports configuration state without secret values.
4. If `/` fails, check `CAPSTONE_STATIC_DIR` and `index.html`. In the image it should be
   `/service/app/static`.
5. If a question has no matches, confirm the reviewed corpus contents and query wording.
   The expected response is an explicit no-evidence result, not a guessed answer.
6. If an optional provider fails, returns invalid JSON/shape/content, emits an
   instruction-like response, fails structural citation validation, or cites a
   non-retrieved source, the expected mode is `evidence-only` with `fallback: true`.
   Provider URLs must be HTTPS and match `CAPSTONE_PROVIDER_ALLOWED_HOSTS`. Structural
   checks do not establish semantic entailment; keep human review pending. Check
   `capstone_llm_fallbacks_total`; do not bypass validation.
7. If an internal exception still produces HTTP 500, use the request ID and safe server
   event for diagnosis. The API returns generic error detail and does not return provider
   exception text.

## Local rollback and data changes

Stop the process with `Ctrl+C` or `docker compose down`. Rebuild after code or corpus
changes:

```bash
docker compose build --pull
docker compose up
```

For a reproducible local rollback, use the previously reviewed immutable image digest
(not a mutable `latest` tag) together with the manifest SHA-256, `CAPSTONE_CORPUS_VERSION`,
and `CAPSTONE_INDEX_VERSION` embedded in that image, plus the same
configuration/secret-manager references. If a corpus is externally mounted, review and
verify that input as part of the rollback pair. Record the whole boundary; treat corpus
edits as code changes. Do not mix a new image with an unverified corpus. Verify `/health`,
`/ready`, a representative evidence-only request, `python scripts/verify_corpus_manifest.py`,
`pytest`, and `ruff check .` after restoring the pair. See [`deployment.md`](deployment.md)
for the placeholder image/embedded-corpus procedure.

Do not place secrets, personal information, browser artifacts, or unapproved production
documents in `data/documents/`. No cloud resource, registry, durable log store, or
multi-instance recovery system is created by this repository.
