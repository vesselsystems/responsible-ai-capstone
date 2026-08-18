"""FastAPI entry point for the local responsible-AI prototype."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .index import EvidenceIndex
from .metrics import Metrics
from .service import CapstoneService

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _configured_path(variable: str, relative_path: str) -> Path:
    """Resolve a runtime directory without assuming where the package was installed.

    A wheel contains Python code, while this prototype keeps its corpus and browser
    assets beside the service.  Docker sets these variables explicitly; the source
    checkout remains convenient when the variables are unset.
    """

    configured = os.getenv(variable, "").strip()
    if configured:
        return Path(configured).expanduser()

    checkout_path = SOURCE_ROOT / relative_path
    if checkout_path.exists():
        return checkout_path
    return Path.cwd() / relative_path


CORPUS_DIR = _configured_path("CAPSTONE_CORPUS_DIR", "data/documents")
STATIC_DIR = _configured_path("CAPSTONE_STATIC_DIR", "app/static")

metrics = Metrics()
index = EvidenceIndex(CORPUS_DIR)
service = CapstoneService(index, metrics)
app = FastAPI(
    title="Responsible AI Evidence Assistant",
    version="0.1.0",
    description="A citation-grounded local prototype with in-process metrics.",
)


EVIDENCE_CONTRACT_VERSION = "retrieved-markdown-chunk-v1"


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


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "chunks": len(index.chunks), "service": app.title}


@app.get("/ready")
def ready() -> dict[str, object]:
    return {"ready": bool(index.chunks)}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    started = time.perf_counter()
    request_id = str(uuid4())
    try:
        result = service.ask(request.question, top_k=request.top_k)
    except Exception as error:  # defensive boundary for the HTTP service
        metrics.record(latency_ms=(time.perf_counter() - started) * 1_000, error=True)
        raise HTTPException(status_code=500, detail="The request could not be completed") from error

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


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
