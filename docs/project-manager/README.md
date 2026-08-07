# Project Manager runtime state

This directory is the project-owned home for Project Manager coordination state. The JSON and JSONL files below are intentionally ignored by Git and must be read or written through Project Manager's supported tools during normal operation.

- `worker-registry.json` is the canonical active and archived worker registry. An empty registry means that no project workers are registered; it is not evidence that unrelated or historical tasks are healthy.
- `manager-ledger.jsonl` is the append-only coordination and operations ledger.
- `transaction-journal.jsonl` records in-flight transactional coordination when a Project Manager workflow requires it.

The Codex heartbeat runs every 15 minutes. Each run must call `manager_environment_health` first and fail closed unless `overallStatus=healthy`, `coordinationGate=allow`, and `heartbeatReady=true`. Delivery-only, source-only, package-only, or hosted-snapshot evidence must never be reported as proof that the current loaded Codex turn is healthy.

Quiet healthy ticks and unchanged roadmap snapshots return exactly `DONT_NOTIFY`. Material blockers, failed release stages, and completed deployments may notify with concise evidence. Automation must not invent workers, clear state, restart Codex, repair plugin caches, or publish while a coordination or transaction gate is blocked.
