import pytest
from fastapi.testclient import TestClient

import responsible_ai_capstone.service as service_module
from responsible_ai_capstone import api
from responsible_ai_capstone.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_external_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the test suite deterministic and never make a real provider call."""

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


def test_health_and_readiness() -> None:
    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["chunks"] > 0
    assert ready.json() == {"ready": True}


def test_ask_returns_citations_inspectable_evidence_and_request_metadata() -> None:
    response = client.post(
        "/ask",
        json={"question": "What should a release review check?", "top_k": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert body["mode"] == "evidence-only"
    assert body["evidence"]
    assert "citation" in body["evidence"][0]
    assert body["evidence"][0]["text"]
    assert body["latency_ms"] >= 0


def test_unknown_question_is_explicit() -> None:
    response = client.post("/ask", json={"question": "quantum banana orchestration", "top_k": 3})

    assert response.status_code == 200
    assert response.json()["evidence"] == []
    assert "could not find" in response.json()["answer"].lower()


def test_invalid_requests_are_rejected() -> None:
    blank = client.post("/ask", json={"question": "   "})
    too_short_after_trim = client.post("/ask", json={"question": " a "})
    invalid_top_k = client.post("/ask", json={"question": "valid question", "top_k": 0})
    too_long = client.post("/ask", json={"question": "x" * 2_001})

    assert blank.status_code == 422
    assert too_short_after_trim.status_code == 422
    assert invalid_top_k.status_code == 422
    assert too_long.status_code == 422


def test_provider_failure_falls_back_and_records_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    def fail(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("simulated provider outage")

    monkeypatch.setattr(api.service, "_llm_answer", fail)
    response = client.post("/ask", json={"question": "What belongs in an approval record?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "evidence-only"
    assert response.json()["evidence"]
    assert "capstone_llm_fallbacks_total" in client.get("/metrics").text


def test_malformed_provider_payload_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    class MalformedResponse:
        def __enter__(self) -> "MalformedResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return b'{"choices": [{"message": {"content": null}}]}'

    monkeypatch.setattr(service_module, "urlopen", lambda *_args, **_kwargs: MalformedResponse())
    response = client.post("/ask", json={"question": "What belongs in an approval record?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "evidence-only"
    assert response.json()["evidence"]


def test_untrusted_provider_citation_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    def cite_unretrieved(*_args: object, **_kwargs: object) -> str:
        return "Unsupported answer [not-retrieved.md#99]"

    monkeypatch.setattr(api.service, "_llm_answer", cite_unretrieved)
    response = client.post("/ask", json={"question": "What belongs in an approval record?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "evidence-only"
    assert "not-retrieved.md#99" not in response.json()["answer"]


def test_retrieved_provider_citation_can_be_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    def cite_retrieved(_question: str, evidence: list[object]) -> str:
        return f"Use the documented review steps {evidence[0].citation}."

    monkeypatch.setattr(api.service, "_llm_answer", cite_retrieved)
    response = client.post("/ask", json={"question": "What belongs in an approval record?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "llm"


def test_frontend_is_served_without_html_interpolation() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "textContent" in response.text
    assert "innerHTML" not in response.text


def test_metrics_expose_request_counter() -> None:
    client.post("/ask", json={"question": "What belongs in an approval record?"})
    metrics = client.get("/metrics")

    assert metrics.status_code == 200
    assert "capstone_requests_total" in metrics.text
