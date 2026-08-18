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

`EvidenceIndex` loads `data/documents/*.md`, joins each document into bounded word chunks, and uses a deterministic TF-IDF similarity baseline with stable tie ordering. The current corpus is intentionally small. `/ask` advertises the `retrieved-markdown-chunk-v1` contract and returns the exact citation, source filename, chunk ID, score, bounded verbatim snippet, and full retrieved text so a reviewer can inspect what was used.

The browser UI is served by FastAPI from `app/static`. It uses `textContent` and DOM construction for returned values; answer, source, citation, and corpus text are not inserted through `innerHTML`.

## Runtime paths

The Python package can be installed into a different directory from the corpus and static assets. The service therefore supports:

- `CAPSTONE_CORPUS_DIR` — directory containing Markdown corpus files;
- `CAPSTONE_STATIC_DIR` — directory containing the frontend `index.html`.

The Dockerfile and Compose file set both paths to `/service/data/documents` and `/service/app/static`, respectively. When running from a source checkout with the variables unset, the service uses the checkout paths (or the current working directory as a convenience fallback). A deployment should set explicit paths rather than depending on the fallback.

## Trust boundaries and controls

- **User input:** Pydantic rejects short, blank, oversized, and out-of-range requests before retrieval.
- **Corpus:** Markdown is data, not instructions. The provider prompt says not to treat document instructions as system instructions.
- **External provider:** credentials and endpoint configuration come from environment variables. The provider is untrusted: its payload must have the expected shape, contain substantive text, contain at least one citation, and cite only chunks retrieved for the current question.
- **Fallback:** provider/network failures and invalid output produce an evidence-only draft rather than an ungrounded answer. The response marks configured-provider fallback with `fallback: true`; default evidence-only mode uses `fallback: false`. No provider secret or exception detail is returned to the caller.
- **Human decision-making:** citations support review; the service is not an authorization or policy-enforcement system.

## Endpoints and state

- `/health` and `/ready` expose process/index state.
- `/ask` returns a generated request ID, mode (`evidence-only` or `llm`), fallback flag, evidence contract version, inspectable evidence, and request latency.
- `/metrics` exposes in-process counters and an average latency gauge as Prometheus text.

Metrics live only in the Python process and reset on restart. There is no Prometheus server, durable time series, trace store, dashboard, alert manager, authentication layer, or multi-instance aggregation in this repository.

## Deployment boundary

Docker demonstrates reproducible local packaging and a container entry point. The image has a local `/ready` healthcheck and non-root runtime user; Compose adds a read-only filesystem, dropped capabilities, and no-new-privileges. These are packaging checks, not evidence of hosted availability or monitoring. Docker was unavailable in the local verification environment, so the image was not built there. A real deployment would still need an owner, authentication and authorization, secret management, rate limiting, resource limits, a versioned/approved corpus, durable metrics and logs, alert routing, backup/recovery, dependency/image scanning, and an evaluation plan. None of those should be inferred from the local container.
