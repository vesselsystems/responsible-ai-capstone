# Contributing

This repository is a local/containerized prototype. Changes should preserve the explicit boundary between a reproducible demo and a public service.

Before opening a change:

1. Create an isolated Python 3.11+ environment and install `.[dev]`.
2. Run `pytest` and `ruff check .`.
3. Run `python scripts/local_verification.py --output docs/local_verification.md` with provider variables cleared; keep its observations tied to the checked source tree.
4. If Docker is available, run `docker compose up --build` and check `/health` and `/ready`; otherwise record that the image was not tested locally.
5. Add tests for request validation, provider fallback, evidence, or operational behavior affected by the change.
6. Never commit API keys, private documents, or personal information.

Do not describe a local change as deployed, durable, or production-ready without measured evidence and the controls documented for that environment.
