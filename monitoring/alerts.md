# Monitoring starter

The service exposes these Prometheus-compatible signals:

- `capstone_requests_total`
- `capstone_errors_total`
- `capstone_no_evidence_total`
- `capstone_llm_fallbacks_total`
- `capstone_request_latency_ms_average`

Starter review thresholds for a demo environment:

- investigate any increase in `capstone_errors_total`;
- investigate a sustained rise in no-evidence responses after a corpus or code change;
- investigate repeated LLM fallbacks before enabling the external provider;
- set a latency SLO only after collecting a representative baseline.

These are review signals, not production alert policy. Add authentication, durable metrics, rate limiting, and a managed secret store before exposing a consequential service.
