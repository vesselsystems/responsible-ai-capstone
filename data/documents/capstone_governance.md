# Capstone governance guidance

This original demo document is not legal advice or an approved organizational policy.

A responsible AI service should define its intended use, excluded uses, data owner, evidence source, review owner, and escalation path. It should show users what evidence supports an answer and make uncertainty visible instead of presenting a generated response as authoritative.

Sensitive data should be minimized, access should follow least privilege, and secrets must remain outside source control. Logs should avoid unnecessary sensitive content while preserving enough request metadata to investigate failures.

A release review should check retrieval quality, unsupported-answer behavior, prompt-injection resistance, latency, error rate, and the ability to disable or roll back a problematic model, prompt, source, or integration.
