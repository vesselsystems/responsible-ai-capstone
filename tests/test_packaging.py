from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_container_declares_non_root_readiness_and_hygiene_controls() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "['ready'] is True" in dockerfile
    assert "pip install --no-cache-dir ." in dockerfile
    assert "*.key" in dockerignore
    assert "*.pem" in dockerignore
    assert "tests" in dockerignore
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose


def test_ci_container_smoke_checks_ready_health_and_ask() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "docker build --pull" in workflow
    assert "/ready" in workflow
    assert "/health" in workflow
    assert "http://127.0.0.1:8000/ask" in workflow
    assert 'payload["evidence"][0]["snippet"]' in workflow
    assert "{{.Config.User}}" in workflow
