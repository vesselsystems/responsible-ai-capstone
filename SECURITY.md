# Security

This repository is a local/containerized prototype, not an internet-facing or production
service. Its low-risk defaults bind Compose to loopback, keep provider generation
optional, run the container as non-root with a read-only filesystem, enable a small
process-local per-client/IP rate limit, and leave authentication disabled for the local
demo. Authentication can be enabled with `CAPSTONE_AUTH_ENABLED=true` and a runtime
injected `CAPSTONE_AUTH_TOKEN`; if the token is missing, readiness and protected requests
fail closed. `/ask` and `/metrics` are protected when enabled while `/health` and `/ready`
remain available to probes.

Request IDs and JSON request events are provided for local diagnosis. Events omit request
bodies, query strings, authorization values, provider response text, and exception
messages. `/ask` admission limiting runs before authentication. Forwarded client headers
are ignored unless the direct peer matches the configured `CAPSTONE_TRUSTED_PROXY_CIDRS`
allowlist. Provider URLs must use HTTPS and an exact host allowlist. The rate limiter and
metrics are in-process only; they do not provide multi-instance enforcement, durable audit
logs, or an alerting service. Do not expose the prototype publicly based on these controls.

Please do not open a public issue containing API keys, private documents, or sensitive
security details. Revoke exposed credentials immediately, then contact the repository
owner through a private GitHub channel with the repository name, affected revision, and a
minimal reproduction. There is no security response SLA for this learning repository.

The optional provider receives user questions and retrieved context. Review the endpoint,
data handling, secret-manager injection, and access controls before enabling it. Never
commit a provider key or auth token, put one in a Docker image, or add one to tests,
fixtures, logs, or documentation.
