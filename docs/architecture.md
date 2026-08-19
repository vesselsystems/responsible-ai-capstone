# Architecture and scope

## What is implemented here

This project is a local/containerized prototype. The request path is:

```text
Browser or curl
      │
      ▼
FastAPI /ask ──► TF-IDF index ──► retrieved Markdown chunks
      │                                  │
      │                                  └── citation + score + text excerpt
      │
      ├── no evidence ────────────────► explicit no-evidence response
      │
      └── optional provider ───────────► validated cited answer
                         │
                         └── failure, malformed output, or bad citation
                                      ▼
                              evidence-only fallback
```

`EvidenceIndex` admits only the two tracked Markdown documents after verifying
`data/corpus_manifest.json`, its companion SHA-256 lock, exact membership, document
checksums, `corpus-v1`, and the compatible `tfidf-markdown-v1` index boundary. It joins each
document into bounded word chunks and uses a deterministic TF-IDF similarity baseline with
stable tie ordering. Readiness repeats the verification so a post-startup manifest or
checksum drift is fail-closed rather than silently serving an old index. `/ask` advertises
the `retrieved-markdown-chunk-v1` contract and returns the exact citation, source filename,
chunk ID, score, bounded verbatim snippet, and full retrieved text so a reviewer can
inspect what was used.

The browser UI is served by FastAPI from `app/static`. It uses `textContent` and DOM construction for returned values; answer, source, citation, and corpus text are not inserted through `innerHTML`.

## Runtime paths

The Python package can be installed into a different directory from the corpus and static assets. The service therefore supports:

- `CAPSTONE_CORPUS_DIR` — directory containing the reviewed Markdown corpus;
- `CAPSTONE_CORPUS_MANIFEST_PATH` — optional explicit path to the corpus manifest;
- `CAPSTONE_CORPUS_VERSION`, `CAPSTONE_CORPUS_MANIFEST_SHA256`, and
  `CAPSTONE_INDEX_VERSION` — non-secret admission/version pins;
- `CAPSTONE_STATIC_DIR` — directory containing the frontend `index.html`; readiness
  checks this file dynamically;
- `CAPSTONE_TRUST_PROXY_HEADERS` and `CAPSTONE_TRUSTED_PROXY_CIDRS` — opt-in proxy
  forwarding with a required direct-peer allowlist;
- `CAPSTONE_PROVIDER_ALLOWED_HOSTS` — exact HTTPS host allowlist for the optional
  `OPENAI_BASE_URL` endpoint.

The Dockerfile and Compose file set both paths to `/service/data/documents` and `/service/app/static`, respectively. When running from a source checkout with the variables unset, the service uses the checkout paths (or the current working directory as a convenience fallback). A deployment should set explicit paths rather than depending on the fallback.

## Trust boundaries and controls

- **User input:** Pydantic rejects short, blank, oversized, and out-of-range requests before retrieval.
- **Corpus:** Markdown is data, not instructions. The provider prompt says not to treat document instructions as system instructions.
- **External provider:** credentials and endpoint configuration come from environment variables. The endpoint must use HTTPS and its exact host must be in `CAPSTONE_PROVIDER_ALLOWED_HOSTS`. The provider is untrusted: its payload must have the expected shape, contain substantive text, contain at least one citation, and cite only chunks retrieved for the current question.
- **Fallback:** provider/network failures and structurally invalid output produce an evidence-only draft rather than an ungrounded answer. The response marks configured-provider fallback with `fallback: true`; default evidence-only mode uses `fallback: false`. Structural citation validation checks identifier membership and presentation, but cannot establish semantic entailment or claim completeness; human review remains pending. No provider secret or exception detail is returned to the caller.
- **Human decision-making:** citations support review; the service is not an authorization or policy-enforcement system.

## Endpoints and state

- `/health` exposes process/index state, safe configuration flags/error codes, and only non-secret corpus version, manifest SHA-256, and index version metadata; it never returns credentials.
- `/ready` is an unauthenticated probe. It returns HTTP 200 only when critical configuration, corpus, and static assets are available; failures return HTTP 503 with safe check names.
- `/ask` returns a generated request ID, mode (`evidence-only` or `llm`), fallback flag, evidence contract version, inspectable evidence, and request latency.
- `/metrics` exposes in-process counters and an average latency gauge as Prometheus text. It is protected when authentication is enabled.

A middleware assigns an `X-Request-ID`, applies the `/ask` rate limiter before optional Bearer authentication, and protects `/metrics` with that authentication when enabled. The direct peer address is used unless `CAPSTONE_TRUST_PROXY_HEADERS=true` and the direct peer is in the `CAPSTONE_TRUSTED_PROXY_CIDRS` allowlist. Structured request events omit bodies, query strings, authorization values, provider text, and exception details; only a pseudonymous client identifier is logged.

Metrics, rate-limit state, and request events live only in the Python process/console stream and reset or disappear on restart. They are diagnostic signals, not durable telemetry or production monitoring. There is no Prometheus server, durable time series, trace store, dashboard, alert manager, log retention, or multi-instance coordination in this repository. Azure durability would require separately configured Container Apps diagnostic settings to Log Analytics plus Azure Monitor managed application-metrics collection; the inert template and this source tree do not create or verify that wiring.

## Deployment boundary

Docker demonstrates reproducible local packaging and a container entry point. The image embeds the reviewed corpus and has a local `/ready` healthcheck and non-root runtime user; Compose adds a read-only filesystem, dropped capabilities, no-new-privileges, and CPU/memory/process limits. Authentication and the limiter are configurable local controls, not evidence of hosted availability, authorization, durable monitoring, or multi-instance enforcement. Docker was unavailable in the local verification environment, so the image was not built there. [`deployment.md`](deployment.md) documents corpus admission, runtime secret-manager injection, an inert Azure Container Apps template, non-durable telemetry, and local image-plus-embedded-corpus rollback without creating cloud resources. A real deployment would still need an owner, environment-specific authorization, durable metrics and logs, alert routing, backup/recovery, dependency/image scanning, and an evaluation plan. None of those should be inferred from the local container; this project makes no production claim.
