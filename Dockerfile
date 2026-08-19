FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CAPSTONE_CORPUS_DIR=/service/data/documents \
    CAPSTONE_CORPUS_MANIFEST_PATH=/service/data/corpus_manifest.json \
    CAPSTONE_STATIC_DIR=/service/app/static \
    CAPSTONE_AUTH_ENABLED=false \
    CAPSTONE_RATE_LIMIT_ENABLED=true \
    CAPSTONE_RATE_LIMIT_REQUESTS=60 \
    CAPSTONE_RATE_LIMIT_WINDOW_SECONDS=60 \
    CAPSTONE_TRUST_PROXY_HEADERS=false \
    CAPSTONE_TRUSTED_PROXY_CIDRS="" \
    CAPSTONE_PROVIDER_ALLOWED_HOSTS=api.openai.com \
    CAPSTONE_CORPUS_VERSION=corpus-v1 \
    CAPSTONE_CORPUS_MANIFEST_SHA256=b137780a7e9a62e59fbb196c309dfff86fde30817797372470580237f441c532 \
    CAPSTONE_INDEX_VERSION=tfidf-markdown-v1

WORKDIR /service
COPY pyproject.toml README.md ./
COPY src ./src
COPY app ./app
COPY data ./data

RUN pip install --no-cache-dir . \
    && addgroup --system app \
    && adduser --system --ingroup app app \
    && chown -R app:app /service

USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import json, urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2))['ready'] is True"
CMD ["uvicorn", "responsible_ai_capstone.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
