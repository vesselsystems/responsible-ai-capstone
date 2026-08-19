import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_container_declares_non_root_readiness_and_hygiene_controls() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "['ready'] is True" in dockerfile
    assert "--no-access-log" in dockerfile
    assert "CAPSTONE_CORPUS_MANIFEST_PATH=/service/data/corpus_manifest.json" in dockerfile
    assert "CAPSTONE_CORPUS_MANIFEST_SHA256" in dockerfile
    assert "CAPSTONE_INDEX_VERSION" in dockerfile
    assert "pip install --no-cache-dir ." in dockerfile
    assert "*.key" in dockerignore
    assert "*.pem" in dockerignore
    assert "tests" in dockerignore
    assert "image: ${CAPSTONE_IMAGE:-responsible-ai-capstone:local}" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "mem_limit: 512m" in compose
    assert "cpus: \"1.0\"" in compose
    assert "--publish 127.0.0.1:8000:8000" in readme
    assert "--read-only" in readme
    assert "--tmpfs /tmp" in readme
    assert "CAPSTONE_TRUSTED_PROXY_CIDRS" in env_example
    assert "CAPSTONE_PROVIDER_ALLOWED_HOSTS" in env_example


def test_deployment_docs_define_secret_injection_and_immutable_rollback() -> None:
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    assert "CAPSTONE_AUTH_TOKEN" in deployment
    assert "secret manager" in deployment
    assert "CAPSTONE_CORPUS_VERSION" in deployment
    assert "sha256" in deployment
    assert "latest" in deployment


def test_azure_template_is_inert_and_has_deterministic_placeholder_validation() -> None:
    template = (ROOT / "deploy" / "azure-container-apps.yaml").read_text(encoding="utf-8")
    assert "@sha256:<image-digest-placeholder>" in template
    assert "<revision-name-placeholder>" in template
    assert "keyVaultUrl" in template
    assert "secretRef: capstone-auth-token" in template
    assert "path: /ready" in template
    assert "ContainerAppConsoleLogs" in template
    assert "Log Analytics" in template
    assert "subscription-id-placeholder" in template
    assert "resources:" not in template.split("properties:", 1)[0]
    assert ":latest" not in template.lower()

    result = subprocess.run(
        [sys.executable, "scripts/validate_azure_template.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "valid"
    assert "<image-digest-placeholder>" in payload["placeholders"]


def test_ci_container_smoke_checks_ready_health_and_ask() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "docker build --pull" in workflow
    assert "/ready" in workflow
    assert "/health" in workflow
    assert "http://127.0.0.1:8000/ask" in workflow
    assert 'payload["evidence"][0]["snippet"]' in workflow
    assert "{{.Config.User}}" in workflow
