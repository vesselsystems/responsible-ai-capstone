# Capstone incident response

This original demo document is not an operational runbook for a real organization.

Open an incident when the assistant exposes restricted information, loses citations, produces a materially misleading answer, or shows an unexpected quality, latency, or error regression.

Record the request ID, timestamp, mode, retrieved source identifiers, model/prompt version, and user-visible behavior. Avoid logging secrets or unnecessary sensitive text. Route the workflow to human review or disable the affected integration when containment is needed.

Reproduce the failure with a controlled test, identify whether the cause was data, retrieval, prompt, model, integration, or infrastructure, and add a regression test before restoring normal operation. Record the owner, residual risk, corrective action, and next review date.
