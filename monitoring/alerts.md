# Monitoring starter for the local prototype

`GET /metrics` exposes Prometheus-compatible text generated from counters held in the current Python process:

- `capstone_requests_total` — accepted `/ask` requests that reached the service function;
- `capstone_errors_total` — `/ask` requests that crossed the defensive HTTP boundary with an internal exception;
- `capstone_no_evidence_total` — requests for which retrieval returned no chunks;
- `capstone_llm_fallbacks_total` — configured provider attempts that fell back to evidence-only mode after provider failure or structural response validation;
- `capstone_request_latency_ms_average` — average in-process `/ask` latency for recorded requests.
- `capstone_authentication_failures_total` — protected requests rejected by the optional auth gate.
- `capstone_rate_limited_total` — `/ask` requests rejected by the in-process limiter.

Provider fallback is intentionally not counted as an internal error: it is the safe, expected response to provider/network failure or malformed/untrusted provider output. Validation errors rejected by FastAPI do not reach the service function.

## What can be reviewed locally

For a local demo, inspect `/metrics` after representative manual or test requests. Review changes in no-evidence responses, provider fallbacks, internal errors, and latency while comparing them with the corpus/code change that preceded them. The repository's current corpus is small and no traffic baseline or held-out evaluation set is included, so there is no defensible SLO or alert threshold here.

The counters and limiter state reset on process/container restart. `/metrics` is an exposition endpoint only; this project does not include Prometheus storage, a dashboard, an alert manager, logs with retention, traces, or notification routing. Request events are structured and redacted for local diagnosis, written to the process console stream (stdout/stderr depending on logging configuration), and are not retained by this repository. Local metrics/log events are therefore not durable telemetry or production monitoring. For Azure, an owner must configure the managed environment's `appLogsConfiguration.destination=log-analytics`, then route Container Apps console/system logs to Log Analytics through managed-environment diagnostic settings and configure Azure Monitor managed application-metrics collection (managed Prometheus/OpenTelemetry or Application Insights) with retention, redaction, dashboards, and alert ownership. That wiring is guidance, not an implemented or verified service here.

## Before a real deployment

An environment owner would need to choose and document thresholds using measured traffic and evaluation data, then add durable collection and alerting. At minimum, that design should cover availability/readiness, request errors, latency distributions rather than only an average, no-evidence and retrieval-quality regressions, provider failure rate, resource saturation, corpus/index version/manifest hash, audit-safe logs, and escalation/notification ownership. It would also need environment-specific authentication/authorization, a shared rate limiter, secret management, retention rules, and a tested response process. Rollback records should pair the prior immutable image digest with its matching corpus manifest SHA-256; a mutable tag or a new image with an unverified corpus is not a rollback.
