"""Generate a deterministic, in-process verification record for the local prototype."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

PROVIDER_VARIABLES = ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL")
UNSAFE_FRONTEND_APIS = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write")


def _client():
    """Load the app only after disabling optional provider settings for this check."""

    for variable in PROVIDER_VARIABLES:
        os.environ.pop(variable, None)

    from fastapi.testclient import TestClient

    from responsible_ai_capstone.api import app

    return TestClient(app)


def collect_observations() -> dict[str, object]:
    client = _client()
    health = client.get("/health")
    ready = client.get("/ready")
    supported = client.post(
        "/ask",
        json={"question": "What belongs in an approval record?", "top_k": 1},
    )
    unknown = client.post("/ask", json={"question": "quantum banana orchestration"})
    invalid = client.post("/ask", json={"question": "valid question", "unexpected": True})
    frontend = client.get("/")

    if health.status_code != 200 or ready.status_code != 200:
        raise RuntimeError("health/readiness verification failed")
    if supported.status_code != 200 or unknown.status_code != 200:
        raise RuntimeError("ask verification failed")
    if invalid.status_code != 422:
        raise RuntimeError("invalid request was not rejected")
    if frontend.status_code != 200:
        raise RuntimeError("frontend verification failed")

    supported_body = supported.json()
    unknown_body = unknown.json()
    if supported_body["mode"] != "evidence-only" or supported_body["fallback"]:
        raise RuntimeError("default request did not remain deterministic evidence-only mode")
    if not supported_body["evidence"]:
        raise RuntimeError("inspectable evidence was not returned")
    first_evidence = supported_body["evidence"][0]
    if not first_evidence["snippet"]:
        raise RuntimeError("inspectable evidence was not returned")
    if unknown_body["evidence"] or "could not find" not in unknown_body["answer"].lower():
        raise RuntimeError("unknown request did not produce an explicit no-evidence result")
    unsafe_apis_found = [api for api in UNSAFE_FRONTEND_APIS if api in frontend.text]
    if unsafe_apis_found:
        raise RuntimeError("frontend contains an unsafe HTML interpolation API")
    frontend_uses_text_apis = "textContent" in frontend.text and "createElement" in frontend.text
    if not frontend_uses_text_apis:
        raise RuntimeError("frontend text rendering APIs were not found")

    return {
        "health_status": health.status_code,
        "indexed_chunks": health.json()["chunks"],
        "ready_status": ready.status_code,
        "ready": ready.json()["ready"],
        "supported_status": supported.status_code,
        "supported_mode": supported_body["mode"],
        "supported_fallback": supported_body["fallback"],
        "supported_latency_ms": supported_body["latency_ms"],
        "evidence_contract": supported_body["evidence_contract"],
        "evidence_count": len(supported_body["evidence"]),
        "citation": first_evidence["citation"],
        "source": first_evidence["source"],
        "chunk_id": first_evidence["chunk_id"],
        "snippet_characters": len(first_evidence["snippet"]),
        "unknown_status": unknown.status_code,
        "unknown_evidence_count": len(unknown_body["evidence"]),
        "invalid_status": invalid.status_code,
        "frontend_status": frontend.status_code,
        "frontend_uses_text_apis": frontend_uses_text_apis,
        "frontend_unsafe_apis_found": unsafe_apis_found,
        "provider_calls": 0,
    }


def render_markdown(observations: dict[str, object]) -> str:
    """Render observations without adding quality or deployment claims."""

    rows = [
        (
            f"| `/health` | HTTP {observations['health_status']}; "
            f"`{observations['indexed_chunks']}` indexed chunks |"
        ),
        f"| `/ready` | HTTP {observations['ready_status']}; `ready={observations['ready']}` |",
        (
            f"| Supported `/ask` | HTTP {observations['supported_status']}; "
            f"mode `{observations['supported_mode']}`; "
            f"fallback `{observations['supported_fallback']}`; "
            f"latency `{observations['supported_latency_ms']}` ms |"
        ),
        (
            f"| Evidence contract | `{observations['evidence_contract']}`; "
            f"`{observations['evidence_count']}` returned item; "
            f"citation `{observations['citation']}` |"
        ),
        (
            f"| Source metadata | `{observations['source']}` chunk "
            f"`{observations['chunk_id']}`; "
            f"`{observations['snippet_characters']}`-character snippet |"
        ),
        (
            f"| Unknown `/ask` | HTTP {observations['unknown_status']}; "
            f"`{observations['unknown_evidence_count']}` evidence items |"
        ),
        f"| Extra request field | HTTP {observations['invalid_status']}; rejected |",
        (
            f"| Frontend | HTTP {observations['frontend_status']}; "
            f"DOM text APIs `{observations['frontend_uses_text_apis']}`; "
            "unsafe HTML API list empty |"
        ),
        f"| Provider calls | `{observations['provider_calls']}` |",
    ]
    return "\n".join(
        [
            "# Local verification record",
            "",
            (
                "Generated by `python scripts/local_verification.py` using FastAPI's "
                "in-process test client."
            ),
            (
                "The optional provider variables are cleared by the script, so this record "
                "does not call a"
            ),
            "remote service or measure provider behavior.",
            "",
            "| Check | Observation |",
            "| --- | --- |",
            *rows,
            "",
            (
                "This is a local behavior record for the checked source tree. It is not a "
                "retrieval-quality"
            ),
            (
                "benchmark, latency baseline, uptime result, monitoring result, or "
                "deployment evidence."
            ),
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the Markdown record to this path as well as stdout.",
    )
    args = parser.parse_args()
    rendered = render_markdown(collect_observations())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
