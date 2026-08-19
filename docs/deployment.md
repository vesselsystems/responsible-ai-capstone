# Local deployment and rollback configuration

This document describes reproducible local packaging only. It does not authorize a
cloud deployment or make a production-availability claim. The Compose defaults bind to
`127.0.0.1`, use evidence-only mode, run as a non-root user, and apply a read-only
filesystem plus CPU, memory, and process limits.

## Configuration without secrets

The service reads non-secret settings from environment variables. `.env.example` is a
placeholder and contains no credentials. For a local authenticated run, set a temporary
value outside source control; for any shared environment, have the deployment's secret
manager inject the value at runtime rather than copying it into Compose, an image, or a
log.

| Variable | Local default | Behavior |
| --- | --- | --- |
| `CAPSTONE_IMAGE` | local image tag | Compose image reference; use an immutable digest for rollback. |
| `CAPSTONE_AUTH_ENABLED` | `false` | Protects `/ask` and `/metrics` when `true`. |
| `CAPSTONE_AUTH_TOKEN` | unset | Secret-manager injection for the Bearer token; there is no built-in token. |
| `CAPSTONE_RATE_LIMIT_ENABLED` | `true` | Enables the in-process per-client/IP `/ask` limiter. |
| `CAPSTONE_RATE_LIMIT_REQUESTS` | `60` | Maximum requests in the sliding window. |
| `CAPSTONE_RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding-window duration. |
| `CAPSTONE_TRUST_PROXY_HEADERS` | `false` | Only enable when a trusted proxy owns `X-Forwarded-For`; readiness fails if its CIDR allowlist is empty. |
| `CAPSTONE_TRUSTED_PROXY_CIDRS` | unset | Comma-separated exact proxy IP/CIDR allowlist required before forwarded client addresses are used. |
| `CAPSTONE_CORPUS_DIR` | image path | Read-only directory containing reviewed Markdown. |
| `CAPSTONE_CORPUS_MANIFEST_PATH` | manifest beside corpus directory | Optional explicit manifest path. |
| `CAPSTONE_CORPUS_VERSION` | `corpus-v1` | Non-secret corpus revision label; must match the manifest. |
| `CAPSTONE_CORPUS_MANIFEST_SHA256` | checked-in image pin | Non-secret SHA-256 pin for `data/corpus_manifest.json`. |
| `CAPSTONE_INDEX_VERSION` | `tfidf-markdown-v1` | Non-secret retrieval-index implementation boundary. |
| `OPENAI_API_KEY` | unset | Optional provider secret, injected by the secret manager when approved. |
| `OPENAI_MODEL` / `OPENAI_BASE_URL` | unset / `https://api.openai.com/v1` | Optional provider configuration; the endpoint must use HTTPS. |
| `CAPSTONE_PROVIDER_ALLOWED_HOSTS` | `api.openai.com` | Comma-separated exact HTTPS host allowlist for `OPENAI_BASE_URL`; custom hosts must be added explicitly. |

If authentication is enabled without a token, configuration is invalid: `/ready`
returns HTTP 503 and protected requests fail closed with HTTP 503. Invalid boolean or
rate-limit configuration is also not admitted. `/health` exposes only safe configuration
state (enabled/configured flags and error codes), never token or provider-key values.
The readiness endpoint remains unauthenticated so a local container health probe can
observe failure.

An authenticated request uses a runtime-injected header, for example:

```text
Authorization: Bearer <injected-at-runtime-token>
```

Do not replace the placeholder above with a real value in documentation, tests, CI, or a
shell history. The default local mode does not require this header.

## Immutable local image and embedded-corpus rollback

The Docker image in this repository embeds the reviewed corpus, manifest, static assets,
and Python package. A local rollback is therefore an image rollback: retain the exact
image digest together with the embedded manifest SHA-256, `corpus_version`,
`index_version`, source revision, and test output. A mutable `latest` tag is not a
rollback identifier. If an operator deliberately overrides `CAPSTONE_CORPUS_DIR` with an
external read-only mount, that corpus becomes a separately reviewed input and must be
verified as a matching pair before startup.

1. Build and record a reviewed local image digest; retain the source revision and test
   output with it.
2. Record the image's embedded `CAPSTONE_CORPUS_VERSION` and
   `CAPSTONE_CORPUS_MANIFEST_SHA256` values. Keep corpus changes reviewable and do not
   add untracked local documents to the image.
3. Start the exact image reference, then verify `/health`, `/ready`, an evidence-only
   `/ask`, and `pytest`/Ruff for the checked-out source.
4. To roll back, stop the current local service and restart the previously reviewed
   immutable image digest with its matching non-secret configuration and secret-manager
   references, if any. Do not mix an image with an unverified external corpus mount or
   override its version/checksum pins.
5. If `/ready` is HTTP 503 after a change, stop the process, inspect the safe `checks`
   and configuration error codes, and restore the last known reviewed image boundary. A
   provider failure should remain an evidence-only fallback and is not a reason to
   bypass readiness or expose a secret.

Example placeholders intentionally use shell variables rather than real references.
For the default image, the corpus is embedded; the corpus variables below are non-secret
pins, not a request to download or mount a cloud dataset:

```bash
IMAGE_REF="responsible-ai-capstone@sha256:<reviewed-image-digest>"
CORPUS_VERSION="<embedded-corpus-version>"
MANIFEST_SHA256="<embedded-corpus-manifest-sha256>"
CAPSTONE_IMAGE="$IMAGE_REF" CAPSTONE_CORPUS_VERSION="$CORPUS_VERSION" \
CAPSTONE_CORPUS_MANIFEST_SHA256="$MANIFEST_SHA256" \
  docker compose up --no-build
```

The placeholders above are documentation, not commands that resolve a real image. No
cloud resource, registry, secret manager, durable log store, or multi-instance limiter is
created by this repository. The image digest and embedded corpus pins describe a local
rollback boundary, not a production release or availability guarantee.

## Corpus and index admission boundary

`data/corpus_manifest.json` is the executable record for the two tracked Markdown
snapshots. Each document has a SHA-256 digest, the manifest names the `corpus-v1` snapshot,
and `tfidf-markdown-v1` identifies the compatible index implementation. The companion
`data/corpus_manifest.sha256` pins the manifest bytes themselves. Verify the boundary
without network access with:

```bash
python scripts/verify_corpus_manifest.py
```

The index verifies manifest schema, manifest checksum, exact document membership, document
checksums, corpus version, and index version before building. Readiness rechecks the same
boundary, so a modified, missing, untracked, or newly rewritten manifest/document makes
`/ready` return HTTP 503 and `/ask` refuse service. The process may remain up so the probe
can report a safe failure; it does not serve the drifted index. `/health` exposes only the
non-secret corpus version, manifest SHA-256, index version, and safe loaded/ready state.
`CAPSTONE_CORPUS_MANIFEST_SHA256` is an optional deployment pin and should be set to the
reviewed value in an immutable image or revision.

## Inert Azure Container Apps template

[`../deploy/azure-container-apps.yaml`](../deploy/azure-container-apps.yaml) is an
inspectable ACA configuration template only. It contains no real subscription, resource
group, registry, Key Vault, managed-identity, provider, image, or credential values, and
this repository does not run it or create Azure resources. Validate its YAML shape and
placeholder contract deterministically:

```bash
python scripts/validate_azure_template.py
```

The template shows the controls an environment owner would need to wire: a user-assigned
managed identity and Key Vault references for `CAPSTONE_AUTH_TOKEN` and `OPENAI_API_KEY`,
an immutable `@sha256:<image-digest-placeholder>` image, a revision suffix carrying image
and corpus-manifest identifiers, `/health` startup/liveness probes, `/ready` readiness,
CPU/memory limits, and bounded replica/concurrency scale. The provider URL placeholder must be HTTPS and
paired with the exact provider-host-allowlist placeholder. Replace placeholders only in a
separate approved deployment process. A passing validator is not evidence that a template
was applied or that an Azure environment exists.

## Non-durable local telemetry boundary

The local `/metrics` counters, rate-limit state, and JSON request events are process-local.
Counters reset on restart, stdout/stderr is only a stream until a collector retains it, and
this repository provides no durable log store, time series, dashboard, alert routing, or
multi-instance aggregation. Local logs and metrics are therefore diagnostic signals, not
durable telemetry, production monitoring, or deployment evidence.

Before calling telemetry durable in Azure, an owner must at least:

1. Configure the managed Container Apps environment's
   `appLogsConfiguration.destination=log-analytics` and diagnostic settings to route
   `ContainerAppConsoleLogs` and `ContainerAppSystemLogs` to an approved Log Analytics
   workspace with documented retention, access, and alert rules. Keep the service's
   redacted JSON request events on stdout/stderr; never add request bodies, query strings,
   bearer tokens, provider payloads, or secrets to those events.
2. Configure Azure Monitor platform metrics plus an approved application-metrics path,
   such as an Azure Monitor managed Prometheus/OpenTelemetry collector or Application
   Insights exporter. Collect readiness/availability, HTTP status outcomes, latency
   distributions, fallback/no-evidence rates, resource saturation, and the exposed
   application metrics with retention and alert ownership. If `/metrics` is protected,
   the collector needs a separately controlled authentication arrangement; do not disable
   the service's boundary just to scrape it.
3. Test ingestion, retention, redaction, dashboards, alert notifications, and a recovery
   query from the target subscription. None of this wiring is created or verified here.

## Azure rollback pair

Record a release as a pair of immutable identifiers: the exact image digest and the exact
corpus manifest SHA-256 (along with `corpus_version` and `index_version`). To roll back,
route traffic to the previously reviewed ACA revision or apply the prior immutable image
digest in a new revision, restore its matching `CAPSTONE_CORPUS_MANIFEST_SHA256` and
`CAPSTONE_CORPUS_VERSION`, and keep the same approved secret references. Verify `/health`,
`/ready`, and an evidence-only request before sending traffic. Never use `latest`, mix a
new image with an unverified corpus hash, or bypass a 503 readiness result. The prior pair
must be retained in the release record so a failed revision can be restored without
reconstructing mutable tags. This is rollback guidance only; no Azure deployment or
rollback has been performed by this repository.
