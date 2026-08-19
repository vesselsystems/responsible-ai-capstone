"""Environment-backed runtime configuration for the local prototype.

The service intentionally keeps configuration small and dependency-free.  Values are
read from the environment so a local run can use safe defaults while a deployment can
inject secrets from its secret manager.  Secret values are never included in the
health/readiness representation or configuration error messages.
"""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .corpus import default_manifest_path

SOURCE_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
DEFAULT_PROVIDER_ALLOWED_HOSTS: Final[tuple[str, ...]] = ("api.openai.com",)


def configured_path(variable: str, relative_path: str) -> Path:
    """Resolve a runtime path without assuming a source-checkout layout."""

    configured = os.getenv(variable, "").strip()
    if configured:
        return Path(configured).expanduser()

    checkout_path = SOURCE_ROOT / relative_path
    if checkout_path.exists():
        return checkout_path
    return Path.cwd() / relative_path


def configured_manifest_path(corpus_dir: Path) -> Path:
    """Resolve the corpus manifest without exposing its path in API responses."""

    configured = os.getenv("CAPSTONE_CORPUS_MANIFEST_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return default_manifest_path(corpus_dir)


def _environment_value(*names: str) -> str:
    """Return the first configured value, allowing a small compatibility alias set."""

    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value.strip()
    return ""


def _safe_version_label(raw_value: str) -> str:
    """Bound the non-secret label returned by /health."""

    if not raw_value:
        return "unspecified"
    if not _VERSION_RE.fullmatch(raw_value):
        return "invalid"
    return raw_value


def _optional_version(raw_value: str) -> str | None:
    """Return a configured version only when an operator supplied one."""

    return raw_value or None


def _optional_sha256(raw_value: str, errors: list[str]) -> str | None:
    """Validate an optional non-secret deployment checksum pin."""

    if not raw_value:
        return None
    if not _SHA256_RE.fullmatch(raw_value):
        errors.append("corpus_manifest_sha256_invalid")
        return None
    return raw_value.lower()


def _parse_bool(name: str, raw_value: str, default: bool, errors: list[str]) -> bool:
    if not raw_value:
        return default
    normalized = raw_value.lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    errors.append(f"{name}_invalid")
    # A malformed security setting must not accidentally enable an endpoint.  The
    # overall configuration remains invalid, so protected requests fail closed.
    return default


def _normalise_provider_host(raw_value: str) -> str | None:
    """Return a canonical exact host or ``None`` for an invalid host label."""

    value = raw_value.strip().lower().rstrip(".")
    if not value or any(character in value for character in "/@?#"):
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        try:
            value = value.encode("idna").decode("ascii")
        except UnicodeError:
            return None
        if not _HOSTNAME_RE.fullmatch(value):
            return None
        return value


def _parse_provider_allowed_hosts(
    raw_value: str | None,
    errors: list[str],
) -> tuple[str, ...]:
    """Parse an exact host allowlist without accepting URL or wildcard syntax."""

    if raw_value is None:
        return DEFAULT_PROVIDER_ALLOWED_HOSTS
    values = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not values:
        errors.append("provider_allowed_hosts_missing")
        return ()
    hosts: list[str] = []
    for value in values:
        host = _normalise_provider_host(value)
        if host is None:
            errors.append("provider_allowed_hosts_invalid")
            continue
        if host not in hosts:
            hosts.append(host)
    return tuple(hosts)


def _parse_trusted_proxy_cidrs(
    raw_value: str,
    *,
    trust_proxy_headers: bool,
    errors: list[str],
) -> tuple[str, ...]:
    """Parse proxy networks and require an allowlist when forwarding is enabled."""

    values = [item.strip() for item in raw_value.split(",") if item.strip()]
    networks: list[str] = []
    for value in values:
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError:
            errors.append("trusted_proxy_cidrs_invalid")
            continue
        canonical = str(network)
        if canonical not in networks:
            networks.append(canonical)
    if trust_proxy_headers and not networks:
        errors.append("trusted_proxy_cidrs_missing")
    return tuple(networks)


def _parse_positive_int(
    name: str,
    raw_value: str,
    default: int,
    errors: list[str],
    *,
    maximum: int,
) -> int:
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        errors.append(f"{name}_invalid")
        return default
    if value < 1 or value > maximum:
        errors.append(f"{name}_invalid")
        return default
    return value


@dataclass(frozen=True)
class RuntimeConfig:
    """Validated non-secret runtime settings.

    ``auth_token`` is retained only for the in-process constant-time comparison.  It
    is deliberately excluded from ``health_details`` and from all error messages.
    """

    corpus_dir: Path
    static_dir: Path
    corpus_version: str
    expected_corpus_version: str | None
    expected_manifest_sha256: str | None
    expected_index_version: str | None
    auth_enabled: bool
    auth_token: str
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    trust_proxy_headers: bool
    trusted_proxy_cidrs: tuple[str, ...] = ()
    provider_allowed_hosts: tuple[str, ...] = DEFAULT_PROVIDER_ALLOWED_HOSTS
    errors: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        errors: list[str] = []
        auth_enabled = _parse_bool(
            "CAPSTONE_AUTH_ENABLED",
            _environment_value("CAPSTONE_AUTH_ENABLED", "CAPSTONE_AUTH_REQUIRED"),
            False,
            errors,
        )
        auth_token = _environment_value("CAPSTONE_AUTH_TOKEN")
        if auth_enabled and not auth_token:
            errors.append("auth_token_missing")

        raw_corpus_version = _environment_value("CAPSTONE_CORPUS_VERSION")
        expected_corpus_version = _optional_version(raw_corpus_version)
        if expected_corpus_version is not None and not _VERSION_RE.fullmatch(
            expected_corpus_version
        ):
            errors.append("corpus_version_invalid")
        expected_manifest_sha256 = _optional_sha256(
            _environment_value("CAPSTONE_CORPUS_MANIFEST_SHA256"), errors
        )
        raw_index_version = _environment_value("CAPSTONE_INDEX_VERSION")
        expected_index_version = _optional_version(raw_index_version)
        if expected_index_version is not None and not _VERSION_RE.fullmatch(expected_index_version):
            errors.append("index_version_invalid")

        rate_limit_enabled = _parse_bool(
            "CAPSTONE_RATE_LIMIT_ENABLED",
            _environment_value("CAPSTONE_RATE_LIMIT_ENABLED"),
            True,
            errors,
        )
        rate_limit_requests = _parse_positive_int(
            "CAPSTONE_RATE_LIMIT_REQUESTS",
            _environment_value(
                "CAPSTONE_RATE_LIMIT_REQUESTS",
                "CAPSTONE_RATE_LIMIT_MAX_REQUESTS",
                "CAPSTONE_RATE_LIMIT_PER_MINUTE",
            ),
            60,
            errors,
            maximum=100_000,
        )
        rate_limit_window_seconds = _parse_positive_int(
            "CAPSTONE_RATE_LIMIT_WINDOW_SECONDS",
            _environment_value("CAPSTONE_RATE_LIMIT_WINDOW_SECONDS"),
            60,
            errors,
            maximum=86_400,
        )
        trust_proxy_headers = _parse_bool(
            "CAPSTONE_TRUST_PROXY_HEADERS",
            _environment_value("CAPSTONE_TRUST_PROXY_HEADERS"),
            False,
            errors,
        )
        trusted_proxy_cidrs = _parse_trusted_proxy_cidrs(
            _environment_value("CAPSTONE_TRUSTED_PROXY_CIDRS"),
            trust_proxy_headers=trust_proxy_headers,
            errors=errors,
        )
        provider_allowed_hosts_raw = None
        for variable in ("CAPSTONE_PROVIDER_ALLOWED_HOSTS", "OPENAI_ALLOWED_HOSTS"):
            if variable in os.environ:
                provider_allowed_hosts_raw = os.environ[variable].strip()
                break
        provider_allowed_hosts = _parse_provider_allowed_hosts(
            provider_allowed_hosts_raw,
            errors,
        )

        return cls(
            corpus_dir=configured_path("CAPSTONE_CORPUS_DIR", "data/documents"),
            static_dir=configured_path("CAPSTONE_STATIC_DIR", "app/static"),
            corpus_version=_safe_version_label(raw_corpus_version),
            expected_corpus_version=expected_corpus_version,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_index_version=expected_index_version,
            auth_enabled=auth_enabled,
            auth_token=auth_token,
            rate_limit_enabled=rate_limit_enabled,
            rate_limit_requests=rate_limit_requests,
            rate_limit_window_seconds=rate_limit_window_seconds,
            trust_proxy_headers=trust_proxy_headers,
            trusted_proxy_cidrs=trusted_proxy_cidrs,
            provider_allowed_hosts=provider_allowed_hosts,
            errors=tuple(dict.fromkeys(errors)),
        )

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def provider_state(self) -> str:
        key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
        model_present = bool(os.getenv("OPENAI_MODEL", "").strip())
        if key_present and model_present:
            return "configured"
        if key_present or model_present:
            return "incomplete"
        return "disabled"

    def health_details(
        self,
        *,
        corpus_loaded: bool,
        static_loaded: bool,
        corpus_version: str | None = None,
        corpus_manifest_sha256: str | None = None,
        index_version: str | None = None,
    ) -> dict[str, object]:
        """Return safe operational detail without returning credentials or paths."""

        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "authentication": {
                "enabled": self.auth_enabled,
                "configured": bool(self.auth_token),
            },
            "rate_limiting": {
                "enabled": self.rate_limit_enabled,
                "requests": self.rate_limit_requests,
                "window_seconds": self.rate_limit_window_seconds,
            },
            "proxy_headers": {
                "trusted": self.trust_proxy_headers,
                "trusted_cidrs": list(self.trusted_proxy_cidrs),
            },
            "provider": self.provider_state,
            "provider_allowed_hosts": list(self.provider_allowed_hosts),
            "corpus_version": corpus_version or self.corpus_version,
            "corpus_manifest_sha256": corpus_manifest_sha256,
            "index_version": index_version,
            "corpus_loaded": corpus_loaded,
            "static_loaded": static_loaded,
        }

    def readiness_checks(self, *, corpus_loaded: bool, static_loaded: bool) -> dict[str, bool]:
        return {
            "configuration": self.valid,
            "corpus": corpus_loaded,
            "static": static_loaded,
        }
