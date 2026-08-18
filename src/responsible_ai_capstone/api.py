"""FastAPI entry point for the deployed capstone."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .index import EvidenceIndex
from .metrics import Metrics
from .service import CapstoneService

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data" / "documents"
STATIC_DIR = ROOT / "app" / "static"

metrics = Metrics()
index = EvidenceIndex(CORPUS_DIR)
service = CapstoneService(index, metrics)
app = FastAPI(
    title="Responsible AI Evidence Assistant",
    version="0.1.0",
    description="A citation-grounded, monitored capstone service.",
)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)
    top_k: int = Field(default=3, ge=1, le=5)


class EvidenceResponse(BaseModel):
    citation: str
    source: str
    score: float


class AskResponse(BaseModel):
    request_id: str
    answer: str
    mode: str
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
        evidence=[
            EvidenceResponse(
                citation=item.citation,
                source=item.source,
                score=round(item.score, 6),
            )
            for item in result.evidence
        ],
        latency_ms=round(result.latency_ms, 3),
    )


@app.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint() -> str:
    return metrics.prometheus()


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
