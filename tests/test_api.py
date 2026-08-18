from fastapi.testclient import TestClient

from responsible_ai_capstone.api import app

client = TestClient(app)


def test_health_and_readiness() -> None:
    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["chunks"] > 0
    assert ready.json() == {"ready": True}


def test_ask_returns_citations_and_request_metadata() -> None:
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
    assert body["latency_ms"] >= 0


def test_unknown_question_is_explicit() -> None:
    response = client.post("/ask", json={"question": "quantum banana orchestration", "top_k": 3})

    assert response.status_code == 200
    assert response.json()["evidence"] == []
    assert "could not find" in response.json()["answer"].lower()


def test_metrics_expose_request_counter() -> None:
    client.post("/ask", json={"question": "What belongs in an approval record?"})
    metrics = client.get("/metrics")

    assert metrics.status_code == 200
    assert "capstone_requests_total" in metrics.text
