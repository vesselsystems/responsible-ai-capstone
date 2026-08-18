# Operations runbook

## Health checks

- `GET /health` should return HTTP 200 and a nonzero chunk count.
- `GET /ready` should return `{"ready": true}` before traffic is accepted.
- `GET /metrics` should remain reachable without an LLM key.

## First response to a regression

1. Capture the request ID, timestamp, mode, citations, and latency.
2. Check whether the issue is retrieval, corpus content, prompt/model, external endpoint, or infrastructure.
3. If answers lose grounding or citations, disable the optional LLM integration and run evidence-only mode.
4. Add a regression question to the test set before changing code.
5. Record the owner, impact, containment, residual risk, and next review date.

## Rollback

Deploy a previously tested Git commit or image. Do not modify the corpus in place without a versioned commit and evaluation run.

## Data handling

Do not put secrets, personal information, or unapproved production documents in `data/documents/`. Avoid logging full user questions when they may contain sensitive information.
