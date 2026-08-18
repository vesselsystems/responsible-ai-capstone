FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CAPSTONE_CORPUS_DIR=/service/data/documents \
    CAPSTONE_STATIC_DIR=/service/app/static

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
CMD ["uvicorn", "responsible_ai_capstone.api:app", "--host", "0.0.0.0", "--port", "8000"]
