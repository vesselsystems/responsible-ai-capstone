# One-page case study template

## Problem

Describe who needs grounded answers from governance documentation and why unsupported answers are risky.

## Approach

Describe the corpus, chunking, TF-IDF retrieval baseline, evidence-only fallback, optional LLM path, API, front end, and monitoring endpoints.

## Results

Report retrieval hit@k/MRR from the evaluation set, average latency, no-evidence behavior, and any LLM fallback rate. Do not report a quality claim without the test design.

## Responsible-use controls

State that the corpus is demo guidance, show citations, refuse unsupported questions, avoid secrets/sensitive logs, and keep a human owner for consequential decisions.

## Limitations and next step

The current corpus and evaluation set are small. Next steps are held-out questions, embedding comparison, citation faithfulness review, adversarial tests, authentication, persistent metrics, and a licensed production corpus.
