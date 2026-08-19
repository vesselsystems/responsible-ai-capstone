"""FastAPI entry point for the local responsible-AI prototype."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .config import RuntimeConfig, configured_manifest_path, configured_path
from .index import EvidenceIndex
from .metrics import Metrics
from .security import RateLimiter, trusted_client_id
from .service import CapstoneService

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _configured_path(variable: str, relative_path: str) -> Path:
    """Backward-compatible path helper used by local scripts and deployments."""

    return configured_path(variable, relative_path)


CORPUS_DIR = _configured_path("CAPSTONE_CORPUS_DIR", "data/documents")
STATIC_DIR = _configured_path("CAPSTONE_STATIC_DIR", "app/static")
MANIFEST_PATH = configured_manifest_path(CORPUS_DIR)

metrics = Metrics()
startup_config = RuntimeConfig.from_env()
try:
    # Keep process startup alive when the corpus is absent or drifted so /ready can
    # report a useful failure instead of turning a configuration mistake into an
    # opaque crash.  The index still refuses to retrieve until the boundary verifies.
    index = EvidenceIndex(
        CORPUS_DIR,
        allow_empty=True,
        manifest_path=MANIFEST_PATH,
        require_manifest=True,
        require_checksum_lock=True,
        expected_manifest_sha256=startup_config.expected_manifest_sha256,
        expected_corpus_version=startup_config.expected_corpus_version,
    )
    index_load_error = not index.ready
except Exception:  # filesystem/decoding failures are represented by readiness
    index = EvidenceIndex.empty(CORPUS_DIR)
    index_load_error = True
service = CapstoneService(index, metrics)
rate_limiter = RateLimiter()
logger = logging.getLogger("responsible_ai_capstone.request")
app = FastAPI(
    title="Responsible AI Evidence Assistant",
    version="0.1.0",
    description="A citation-grounded local prototype with in-process metrics.",
)


EVIDENCE_CONTRACT_VERSION = "retrieved-markdown-chunk-v1"
PROTECTED_PATHS = frozenset({"/ask", "/metrics"})


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        min_length=3,
        max_length=2_000,
        description="A non-blank question used for local lexical retrieval.",
    )
    top_k: StrictInt = Field(
        default=3,
        ge=1,
        le=5,
        description="Number of evidence chunks to return.",
    )

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("question must contain at least 3 non-whitespace characters")
        return value


class SourceMetadata(BaseModel):
    """Stable, non-secret identifiers that let a reviewer locate the source."""

    source: str = Field(description="Repository-relative Markdown filename.")
    chunk_id: str = Field(description="Zero-based chunk identifier within the source.")
    media_type: Literal["text/markdown"] = "text/markdown"


class EvidenceResponse(BaseModel):
    """The evidence contract exposes both a bounded preview and the full chunk."""

    citation: str = Field(description="Exact citation token accepted by the provider validator.")
    source: str
    chunk_id: str
    score: float = Field(ge=0)
    snippet: str = Field(description="Verbatim bounded preview of `text` for quick review.")
    text: str = Field(description="Verbatim retrieved Markdown chunk.")
    source_metadata: SourceMetadata


class AskResponse(BaseModel):
    request_id: str
    answer: str
    mode: Literal["evidence-only", "llm"]
    fallback: bool = Field(
        description="True only when a configured provider result was rejected or unavailable."
    )
    evidence_contract: Literal["retrieved-markdown-chunk-v1"] = EVIDENCE_CONTRACT_VERSION
    evidence: list[EvidenceResponse]
    latency_ms: float


def _redacted_client_id(client_id: str) -> str:
    """Use a short process-independent pseudonym rather than logging a raw IP."""

    return hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:16]


def _request_client_id(request: Request, config: RuntimeConfig) -> str:
    direct_host = request.client.host if request.client else None
    return trusted_client_id(
        direct_host,
        request.headers.get("x-forwarded-for"),
        trust_proxy_headers=config.trust_proxy_headers,
        trusted_proxy_cidrs=config.trusted_proxy_cidrs,
    )


def _static_is_available(static_dir: Path) -> bool:
    """Check the frontend on each readiness request rather than only at import time."""

    try:
        return static_dir.is_dir() and (static_dir / "index.html").is_file()
    except OSError:
        return False


def _credentials_match(candidate: str, expected: str) -> bool:
    """Compare UTF-8 credential bytes without leaking malformed text errors."""

    try:
        candidate_bytes = candidate.encode("utf-8")
        expected_bytes = expected.encode("utf-8")
    except (AttributeError, UnicodeEncodeError):
        return False
    return hmac.compare_digest(candidate_bytes, expected_bytes)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def _safe_log_path(path: str) -> str:
    """Allowlist route names so user-controlled URL paths never enter logs."""

    return path if path in {"/", "/health", "/ready", "/ask", "/metrics"} else "/<unmatched>"


def _resource_checks(config: RuntimeConfig) -> dict[str, bool]:
    """Keep path, version, and post-import corpus changes from being reported ready."""

    versions_match = (
        (config.expected_corpus_version is None
         or config.expected_corpus_version == index.corpus_version)
        and (
            config.expected_manifest_sha256 is None
            or config.expected_manifest_sha256 == index.manifest_sha256
        )
        and (
            config.expected_index_version is None
            or config.expected_index_version == index.index_version
        )
    )
    return config.readiness_checks(
        corpus_loaded=(
            index.ready
            and not index_load_error
            and versions_match
            and _same_path(config.corpus_dir, CORPUS_DIR)
            and _same_path(configured_manifest_path(config.corpus_dir), MANIFEST_PATH)
        ),
        static_loaded=(_static_is_available(config.static_dir)
                       and _same_path(config.static_dir, STATIC_DIR)),
    )


def _security_response(request_id: str, config: RuntimeConfig, request: Request) -> tuple[
    JSONResponse, str
] | None:
    """Apply authentication and admission controls to a protected endpoint."""

    if not config.valid:
        return (
            JSONResponse(
                status_code=503,
                content={
                    "detail": "Service security configuration is unavailable",
                    "request_id": request_id,
                },
            ),
            "configuration_rejected",
        )

    # Admission control deliberately runs before authentication on /ask.  Failed
    # credentials must consume the same request budget as successful credentials.
    if request.url.path == "/ask" and config.rate_limit_enabled:
        decision = rate_limiter.check(
            _request_client_id(request, config),
            requests=config.rate_limit_requests,
            window_seconds=config.rate_limit_window_seconds,
        )
        if not decision.allowed:
            metrics.record_rejection(rate_limited=True)
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "request_id": request_id},
                headers={
                    "Retry-After": str(decision.retry_after_seconds),
                    "X-RateLimit-Limit": str(config.rate_limit_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )
            return response, "rate_limited"
        # The allowed response headers are attached by the middleware below.  Keeping
        # the decision on request state avoids changing the /ask response body contract.
        request.state.rate_limit_remaining = decision.remaining
        request.state.rate_limit_limit = config.rate_limit_requests

    if config.auth_enabled:
        authorization = request.headers.get("authorization", "")
        scheme, separator, credential = authorization.partition(" ")
        authenticated = (
            separator == " "
            and scheme.lower() == "bearer"
            and bool(credential)
            and _credentials_match(credential, config.auth_token)
        )
        # Compare UTF-8 bytes with constant-time comparison semantics without ever
        # writing either credential to a log or response.
        if not authenticated:
            metrics.record_rejection(authentication_failure=True)
            response = JSONResponse(
                status_code=401,
                content={"detail": "Authentication required", "request_id": request_id},
                headers={"WWW-Authenticate": "Bearer"},
            )
            return response, "authentication_rejected"

    if request.url.path == "/ask" and not _resource_checks(config)["corpus"]:
        return (
            JSONResponse(
                status_code=503,
                content={"detail": "Service is not ready", "request_id": request_id},
            ),
            "not_ready",
        )

    return None


@app.middleware("http")
async def request_controls(request: Request, call_next):
    """Add request IDs, redactable structured logs, auth, and local rate limiting."""

    request_id = str(uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    config = RuntimeConfig.from_env()
    response = None
    outcome = "completed"
    status_code = 500

    try:
        if request.url.path in PROTECTED_PATHS:
            rejection = _security_response(request_id, config, request)
            if rejection is not None:
                response, outcome = rejection
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        status_code = response.status_code
        if status_code >= 400 and outcome == "completed":
            outcome = "http_error"
        response.headers["X-Request-ID"] = request_id
        if hasattr(request.state, "rate_limit_remaining"):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
        return response
    except Exception:
        # Keep the error boundary generic and preserve the correlation identifier.
        # Uvicorn's outer error handler may otherwise replace the response before
        # this middleware can attach X-Request-ID.
        outcome = "internal_error"
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "The request could not be completed",
                "request_id": request_id,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        if response is not None:
            status_code = response.status_code
        event = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": _safe_log_path(request.url.path),
            "status_code": status_code,
            "duration_ms": round((time.perf_counter() - started) * 1_000, 3),
            "client_ip_hash": _redacted_client_id(_request_client_id(request, config)),
            "outcome": outcome,
        }
        # No query string, body, authorization header, provider error, or other
        # user-controlled content is included in the structured event.
        logger.info(json.dumps(event, sort_keys=True, separators=(",", ":")))


@app.get("/health")
def health() -> dict[str, object]:
    config = RuntimeConfig.from_env()
    checks = _resource_checks(config)
    return {
        "status": "ok",
        "chunks": len(index.chunks),
        "service": app.title,
        "corpus_version": index.corpus_version,
        "corpus_manifest_sha256": index.manifest_sha256,
        "index_version": index.index_version,
        "configuration": config.health_details(
            corpus_loaded=checks["corpus"],
            static_loaded=checks["static"],
            corpus_version=index.corpus_version,
            corpus_manifest_sha256=index.manifest_sha256,
            index_version=index.index_version,
        ),
        "ready": all(checks.values()),
    }


@app.get("/ready", response_model=None)
def ready() -> dict[str, object] | JSONResponse:
    config = RuntimeConfig.from_env()
    checks = _resource_checks(config)
    if not all(checks.values()):
        errors = list(config.errors)
        errors.extend(name for name, passed in checks.items() if not passed)
        errors = list(dict.fromkeys(errors))
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "checks": checks,
                "errors": errors,
                "reason": errors[0] if errors else "not_ready",
            },
        )
    # Keep the established successful response contract intentionally small.  The
    # failure response carries safe diagnostics for operators and health probes.
    return {"ready": True}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, http_request: Request) -> AskResponse | JSONResponse:
    started = time.perf_counter()
    request_id = getattr(http_request.state, "request_id", str(uuid4()))
    try:
        result = service.ask(request.question, top_k=request.top_k)
    except Exception:  # defensive boundary for the HTTP service
        metrics.record(latency_ms=(time.perf_counter() - started) * 1_000, error=True)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "The request could not be completed",
                "request_id": request_id,
            },
        )

    return AskResponse(
        request_id=request_id,
        answer=result.answer,
        mode=result.mode,
        fallback=result.fallback,
        evidence=[
            EvidenceResponse(
                citation=item.citation,
                source=item.source,
                chunk_id=item.chunk_id,
                score=round(item.score, 6),
                snippet=item.snippet,
                text=item.text,
                source_metadata=SourceMetadata(
                    source=item.source,
                    chunk_id=item.chunk_id,
                ),
            )
            for item in result.evidence
        ],
        latency_ms=round(result.latency_ms, 3),
    )


@app.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint() -> str:
    return metrics.prometheus()


# Mount without turning a missing startup directory into an import-time crash.  The
# readiness check remains dynamic and refuses service until index.html is present.
app.mount(
    "/",
    StaticFiles(directory=STATIC_DIR, html=True, check_dir=False),
    name="frontend",
)
