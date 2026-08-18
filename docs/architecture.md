# Capstone architecture

```text
Browser ──► FastAPI ──► TF-IDF evidence index ──► citation-grounded draft
                │                    │
                │                    └── versioned Markdown corpus
                │
                ├── optional OpenAI-compatible LLM (fallback on failure)
                ├── /health and /ready
                └── /metrics (Prometheus text)
```

## Request contract

`POST /ask` accepts a question and `top_k` between 1 and 5. It returns a request ID, answer mode, citations, similarity scores, and latency.

## Trust boundaries

The browser, document corpus, and optional external model endpoint are separate trust boundaries. The application never treats document instructions as system instructions. API keys are environment variables and are never returned in responses or logs.
