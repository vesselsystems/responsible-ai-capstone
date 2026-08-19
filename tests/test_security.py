import json
import logging

import pytest
from fastapi.testclient import TestClient

from responsible_ai_capstone import api
from responsible_ai_capstone.api import _credentials_match
from responsible_ai_capstone.security import RateLimiter, trusted_client_id
from responsible_ai_capstone.service import _safe_plain_text

client = TestClient(api.app)


@pytest.fixture(autouse=True)
def reset_security_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CAPSTONE_AUTH_ENABLED",
        "CAPSTONE_AUTH_REQUIRED",
        "CAPSTONE_AUTH_TOKEN",
        "CAPSTONE_RATE_LIMIT_ENABLED",
        "CAPSTONE_RATE_LIMIT_REQUESTS",
        "CAPSTONE_RATE_LIMIT_MAX_REQUESTS",
        "CAPSTONE_RATE_LIMIT_PER_MINUTE",
        "CAPSTONE_RATE_LIMIT_WINDOW_SECONDS",
        "CAPSTONE_TRUST_PROXY_HEADERS",
        "CAPSTONE_TRUSTED_PROXY_CIDRS",
        "CAPSTONE_PROVIDER_ALLOWED_HOSTS",
        "OPENAI_ALLOWED_HOSTS",
    ):
        monkeypatch.delenv(name, raising=False)
    api.rate_limiter.reset()


def test_auth_credentials_use_utf8_bytes_safely() -> None:
    assert _credentials_match("tökén", "tökén")
    assert not _credentials_match("tökén", "token")
    assert not _credentials_match("\ud800", "token")


def test_authentication_rejects_missing_and_wrong_tokens_then_allows_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "unit-test-token"
    monkeypatch.setenv("CAPSTONE_AUTH_ENABLED", "true")
    monkeypatch.setenv("CAPSTONE_AUTH_TOKEN", token)

    missing = client.post("/ask", json={"question": "approval record"})
    wrong = client.post(
        "/ask",
        headers={"Authorization": "Bearer wrong-token"},
        json={"question": "approval record"},
    )
    allowed = client.post(
        "/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "approval record"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert allowed.status_code == 200
    assert allowed.json()["request_id"] == allowed.headers["x-request-id"]
    assert token not in client.get("/health").text


def test_proxy_forwarding_requires_a_cidr_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPSTONE_TRUST_PROXY_HEADERS", "true")

    ready = client.get("/ready")

    assert ready.status_code == 503
    assert "trusted_proxy_cidrs_missing" in ready.json()["errors"]


def test_enabled_auth_without_a_secret_fails_closed_and_marks_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPSTONE_AUTH_ENABLED", "true")

    ready = client.get("/ready")
    request = client.post("/ask", json={"question": "approval record"})

    assert ready.status_code == 503
    assert ready.json()["ready"] is False
    assert "configuration" in ready.json()["errors"]
    assert request.status_code == 503
    assert "Authentication" not in request.text


def test_rate_limit_is_per_trusted_proxy_client_and_returns_retry_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPSTONE_RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("CAPSTONE_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("CAPSTONE_TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("CAPSTONE_TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    proxy = TestClient(api.app, client=("192.0.2.1", 50000))
    first_client = {"X-Forwarded-For": "198.51.100.10"}
    second_client = {"X-Forwarded-For": "198.51.100.11"}

    first = proxy.post(
        "/ask", headers=first_client, json={"question": "approval record"}
    )
    second = proxy.post(
        "/ask", headers=first_client, json={"question": "approval record"}
    )
    other_client = proxy.post(
        "/ask", headers=second_client, json={"question": "approval record"}
    )
    limited = proxy.post(
        "/ask", headers=first_client, json={"question": "approval record"}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert other_client.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["retry-after"]
    assert limited.json()["request_id"] == limited.headers["x-request-id"]


def test_forwarded_for_is_ignored_for_an_untrusted_direct_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPSTONE_RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("CAPSTONE_TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("CAPSTONE_TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    untrusted = TestClient(api.app, client=("203.0.113.1", 50000))

    first = untrusted.post(
        "/ask",
        headers={"X-Forwarded-For": "198.51.100.10"},
        json={"question": "approval record"},
    )
    second = untrusted.post(
        "/ask",
        headers={"X-Forwarded-For": "198.51.100.11"},
        json={"question": "approval record"},
    )

    assert first.status_code == 200
    assert second.status_code == 429


def test_rate_limit_runs_before_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPSTONE_AUTH_ENABLED", "true")
    monkeypatch.setenv("CAPSTONE_AUTH_TOKEN", "unit-test-token")
    monkeypatch.setenv("CAPSTONE_RATE_LIMIT_REQUESTS", "1")

    rejected_auth = client.post(
        "/ask",
        headers={"Authorization": "Bearer wrong"},
        json={"question": "approval record"},
    )
    bypass_attempt = client.post(
        "/ask",
        headers={"Authorization": "Bearer unit-test-token"},
        json={"question": "approval record"},
    )

    assert rejected_auth.status_code == 401
    assert bypass_attempt.status_code == 429


def test_trusted_client_id_requires_the_direct_peer_to_match_the_allowlist() -> None:
    assert trusted_client_id(
        "192.0.2.4",
        "198.51.100.8, 198.51.100.9",
        trust_proxy_headers=True,
        trusted_proxy_cidrs=("192.0.2.0/24",),
    ) == "198.51.100.8"
    assert trusted_client_id(
        "203.0.113.4",
        "198.51.100.8",
        trust_proxy_headers=True,
        trusted_proxy_cidrs=("192.0.2.0/24",),
    ) == "203.0.113.4"


def test_rate_limiter_expires_a_client_window() -> None:
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])

    assert limiter.check("one", requests=1, window_seconds=10).allowed
    blocked = limiter.check("one", requests=1, window_seconds=10)
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 10

    now[0] = 10.1
    assert limiter.check("one", requests=1, window_seconds=10).allowed
    assert limiter.check("two", requests=1, window_seconds=10).allowed


def test_request_logs_are_structured_and_do_not_contain_body_or_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = "unit-test-token"
    monkeypatch.setenv("CAPSTONE_AUTH_ENABLED", "true")
    monkeypatch.setenv("CAPSTONE_AUTH_TOKEN", token)
    caplog.set_level(logging.INFO, logger="responsible_ai_capstone.request")

    response = client.post(
        "/ask?not-a-secret=super-secret-query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "super-secret-question"},
    )

    assert response.status_code == 200
    events = [json.loads(record.getMessage()) for record in caplog.records]
    event = next(item for item in events if item["request_id"] == response.headers["x-request-id"])
    assert event["event"] == "http_request"
    assert event["path"] == "/ask"
    assert "super-secret" not in json.dumps(event)
    assert token not in json.dumps(event)
    assert "client_ip_hash" in event


def test_request_logs_allowlisted_routes_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="responsible_ai_capstone.request")

    response = client.get("/secret-token-value")

    assert response.status_code == 404
    events = [json.loads(record.getMessage()) for record in caplog.records]
    event = next(item for item in events if item["request_id"] == response.headers["x-request-id"])
    assert event["path"] == "/<unmatched>"
    assert "secret-token-value" not in json.dumps(event)


def test_readiness_reports_a_safe_failure_when_the_corpus_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api.index, "chunks", [])
    monkeypatch.setattr(api, "index_load_error", False)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["checks"]["corpus"] is False
    assert client.post("/ask", json={"question": "approval record"}).status_code == 503


def test_internal_errors_return_a_correlation_id_without_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("private provider detail")

    monkeypatch.setattr(api.service, "ask", fail)
    response = client.post("/ask", json={"question": "approval record"})

    assert response.status_code == 500
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert response.json()["detail"] == "The request could not be completed"
    assert "private provider detail" not in response.text


def test_multiline_provider_text_normalizes_real_line_endings() -> None:
    assert _safe_plain_text("first\r\nsecond\rthird") == "first\nsecond\nthird"


def test_readiness_rechecks_static_assets_dynamically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    available = [True]
    monkeypatch.setattr(api, "_static_is_available", lambda _path: available[0])

    assert client.get("/ready").status_code == 200
    available[0] = False
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["static"] is False
