"""Deterministically validate the inert Azure Container Apps YAML template."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "deploy" / "azure-container-apps.yaml"
PLACEHOLDER_RE = re.compile(r"<[^<>]+>")
SUBSCRIPTION_ID_RE = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])",
    re.IGNORECASE,
)
REGISTRY_RE = re.compile(r"\b[\w.-]+\.azurecr\.io\b", re.IGNORECASE)
REQUIRED_PLACEHOLDERS = {
    "<azure-region-placeholder>",
    "<container-app-name-placeholder>",
    "<corpus-manifest-sha256-placeholder>",
    "<corpus-manifest-short-placeholder>",
    "<corpus-version-placeholder>",
    "<image-digest-placeholder>",
    "<image-digest-short-placeholder>",
    "<key-vault-name-placeholder>",
    "<managed-environment-name-placeholder>",
    "<managed-identity-name-placeholder>",
    "<provider-base-url-placeholder>",
    "<provider-host-allowlist-placeholder>",
    "<provider-model-placeholder>",
    "<registry-login-server-placeholder>",
    "<resource-group-placeholder>",
    "<revision-name-placeholder>",
    "<subscription-id-placeholder>",
}


def _env_by_name(container: dict[str, Any], name: str) -> dict[str, Any]:
    for item in container.get("env", []):
        if isinstance(item, dict) and item.get("name") == name:
            return item
    raise ValueError(f"Azure template is missing environment variable {name}")


def validate_template(path: Path = TEMPLATE_PATH) -> list[str]:
    """Return the sorted placeholder set after validating required controls."""

    text = path.read_text(encoding="utf-8")
    if ":latest" in text.lower():
        raise ValueError("The ACA image must use an immutable digest, not latest")
    if SUBSCRIPTION_ID_RE.search(text) or REGISTRY_RE.search(text):
        raise ValueError("The ACA template contains a concrete subscription or registry value")
    for phrase in ("stdout", "Log Analytics", "Application Insights", "does not create"):
        if phrase not in text:
            raise ValueError(f"The ACA template is missing inspectable guidance: {phrase}")

    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("The ACA template root must be a YAML object")
    if "resources" in raw:
        raise ValueError("The inspectable ACA YAML must not contain a resource collection")
    if raw.get("type") != "Microsoft.App/containerApps":
        raise ValueError("The ACA template type must be Microsoft.App/containerApps")
    properties = raw.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("The ACA template is missing properties")
    configuration = properties.get("configuration")
    template = properties.get("template")
    if not isinstance(configuration, dict) or not isinstance(template, dict):
        raise ValueError("The ACA template needs configuration and template objects")
    if configuration.get("activeRevisionsMode") != "Multiple":
        raise ValueError("The ACA template must permit immutable revision rollback")
    traffic = configuration.get("ingress", {}).get("traffic", [{}])
    if traffic[0].get("revisionName") != "<revision-name-placeholder>":
        raise ValueError("Traffic must point at an explicit revision placeholder")

    registry = configuration.get("registries", [{}])[0]
    if (
        not isinstance(registry, dict)
        or registry.get("server") != "<registry-login-server-placeholder>"
    ):
        raise ValueError("The registry server must remain a placeholder")
    secrets = configuration.get("secrets")
    if not isinstance(secrets, list) or {
        item.get("name") for item in secrets if isinstance(item, dict)
    } != {"capstone-auth-token", "openai-api-key"}:
        raise ValueError("Key Vault secret references are incomplete")
    for secret in secrets:
        if not isinstance(secret, dict) or "keyVaultUrl" not in secret or "identity" not in secret:
            raise ValueError("Each secret must use a Key Vault URL and managed identity")

    containers = template.get("containers")
    if (
        not isinstance(containers, list)
        or len(containers) != 1
        or not isinstance(containers[0], dict)
    ):
        raise ValueError("The ACA template must define exactly one application container")
    container = containers[0]
    image = container.get("image")
    if not isinstance(image, str) or "@sha256:<image-digest-placeholder>" not in image:
        raise ValueError("The container image must use the immutable digest placeholder")
    if container.get("resources") != {"cpu": 0.5, "memory": "1Gi"}:
        raise ValueError("The container resource limits are not the reviewed values")

    probes = container.get("probes")
    probe_types = {probe.get("type") for probe in probes or [] if isinstance(probe, dict)}
    if not {"Startup", "Liveness", "Readiness"}.issubset(probe_types):
        raise ValueError("Startup, liveness, and readiness probes are required")
    readiness = next(probe for probe in probes if probe.get("type") == "Readiness")
    if readiness.get("httpGet", {}).get("path") != "/ready":
        raise ValueError("Readiness must call /ready")

    scale = template.get("scale")
    if (
        not isinstance(scale, dict)
        or scale.get("minReplicas") != 1
        or scale.get("maxReplicas") != 3
    ):
        raise ValueError("The ACA scale bounds are not the reviewed values")
    env = {
        name: _env_by_name(container, name)
        for name in (
            "CAPSTONE_AUTH_TOKEN",
            "CAPSTONE_CORPUS_VERSION",
            "CAPSTONE_CORPUS_MANIFEST_SHA256",
            "CAPSTONE_INDEX_VERSION",
            "CAPSTONE_PROVIDER_ALLOWED_HOSTS",
            "OPENAI_API_KEY",
        )
    }
    if env["CAPSTONE_AUTH_TOKEN"].get("secretRef") != "capstone-auth-token":
        raise ValueError("CAPSTONE_AUTH_TOKEN must be a Key Vault secret reference")
    if env["OPENAI_API_KEY"].get("secretRef") != "openai-api-key":
        raise ValueError("OPENAI_API_KEY must be a Key Vault secret reference")

    placeholders = sorted(set(PLACEHOLDER_RE.findall(text)))
    missing = REQUIRED_PLACEHOLDERS - set(placeholders)
    if missing:
        raise ValueError(f"ACA template is missing placeholders: {', '.join(sorted(missing))}")
    return placeholders


def main() -> None:
    placeholders = validate_template()
    print(
        json.dumps(
            {
                "status": "valid",
                "template": "deploy/azure-container-apps.yaml",
                "placeholders": placeholders,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
