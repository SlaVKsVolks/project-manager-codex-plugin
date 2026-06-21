# Project Manager Plugin Testing And Improvements

Date: 2026-06-19

## This Phase Landed (v0.3.2)

- Added policy-driven worker routing with `deepseek-v4-flash` as the default cheap worker, `deepseek-v4-pro` for higher-risk slices, and `qwen3.7-plus` hard-disabled.
- Added fail-closed verified-dispatch flows: `manager_verified_dispatch` and `manager_replace_dead_lane`.
- Expanded `manager_environment_health` with wrapper smoke, source/cache mismatch reporting, stale-session suspicion, recent MCP log summary, orphan-process diagnostics, and recommended operator action.
- Enriched worker registry semantics with `lastVisibleTurnAt`, `lastVerifiedHealthyAt`, `deliveryVerified`, `replacementOfThreadId`, `deadReferenceReason`, and `staleConfidence`.
- Added release/dev tooling:
  - `scripts\Test-ProjectManagerPlugin.ps1`
  - `scripts\Check-ProjectManagerCacheConsistency.ps1`
  - `scripts\Get-ProjectManagerMcpLogSummary.ps1`
- Added operator-grade maintenance and diagnostics:
  - `manager_registry_maintenance`
  - `manager_operational_audit`
  - `manager_operator_runbook`
- Added regression coverage for transport health, verified dispatch, replacement of dead lanes, model policy, and quiet-heartbeat gating.
- **New in this phase:** Documented phase-aware lane semantics: visible delivery alone is not healthy progress; assistant-authored acknowledgment or worker final is required; silent-after-delivery must block quiet `DONT_NOTIFY`.
- **New in this phase:** Standardized subagent-driven execution roles: implementer, spec reviewer, and code quality reviewer, with one task per worker packet and manager sequencing successors.
- **New in this phase:** Documented platform-aware routing constraints: GPT stays manager/reviewer owner, `deepseek-v4-flash` is default implementer, `deepseek-v4-pro` is escalation-only, `qwen3.7-plus` remains disabled, and routing considers live transport confidence via `manager_model_transport_health`.
- **New in this phase:** Added four new documented MCP tools to the skill: `manager_model_transport_health`, `manager_lane_health_from_readback`, `manager_accept_worker_final_and_plan_next`, and `manager_registry_reconcile`.
- **New in this phase:** Updated canonical manager loop to include transport health verification, lane health from readback, worker final acceptance with successor sequencing, and registry reconciliation for silent-after-delivery detection.
- **New in this phase:** Implemented server parity for the new MCP tools: `manager_model_transport_health`, `manager_worker_canary`, `manager_lane_health_from_readback`, `manager_registry_reconcile`, and `manager_accept_worker_final_and_plan_next`.
- **New in this phase:** Tightened registry evidence gating so active lanes now require allowed evidence sources, while verified dispatch records only delivery visibility until assistant-authored progress is observed.
- **New in this phase:** Added test coverage for silent-after-delivery detection, progressing-lane registry writes, registry reconciliation repair, transport-health per-model viability, worker-final successor sequencing, and active-lane evidence rejection.
- **New in this phase:** Verified the full release path on this machine: source pytest passed, cached pytest passed, and packaged wrapper JSON-RPC smoke passed through `scripts\Test-ProjectManagerPlugin.ps1`.
- **New in this phase:** Upgraded `manager_cross_project_summary` into a triage dashboard payload with ranked projects, project health scores, top recommended actions, delivery-failure totals, and an ordered operator queue.
- **New in this phase:** Added `manager_automation_rollout_helper` so plugin releases can generate live manager-thread rollout packets, heartbeat replacement prompts, and decision-ledger event plans instead of relying on manual stitching.
- **New in this phase:** Added `manager_rollout_execution_bundle` so rollout work now ships as fail-closed action bundles over the native Codex host surfaces: `send_message_to_thread`, `automation_update`, and post-success `manager_append_ledger_event`.
- **New in this phase:** Added maintenance policy output to `manager_heartbeat_bootstrap` so long-running automations have an explicit cadence for `manager_registry_reconcile` and `manager_registry_maintenance`.
- **New in this phase:** Added richer delivery-verification metadata across registry state, verified dispatch, lane-health readback, and ledger events: `deliveryTurnId`, `deliveryMessageId`, `deliveryVerificationEvidence`, `acknowledgedTurnId`, `acknowledgedMessageId`, and `lastReadbackSummary` are now preserved whenever the host surfaces them.
- **New in this phase:** Added `manager_cross_project_dashboard`, a manager-facing rendered dashboard payload with summary cards, ranked projects, operator queue, per-project rows, and markdown output so multi-project triage no longer depends on reading raw summary JSON.
- **New in this phase:** Added `manager_self_repair`, a safe local recovery tool that cleans overflow same-version MCP wrapper groups, refreshes install wiring, and re-checks environment health in one MCP flow instead of only recommending manual self-repair.

## Recommended Next Improvements

- Add live validation around `manager_self_repair` against a disposable bounded MCP buildup scenario, so the new safe local repair path is proven not only in unit tests but also against a controlled live runtime case on this machine.

- Add a live-thread integration probe if Codex exposes a stable API for testing already-bound MCP transports, because fresh wrapper smoke still cannot prove a stale in-memory thread will self-heal.
- Add a higher-level live dispatch executor if Codex exposes stable create/send/read transaction primitives inside one surface; that would let the plugin move from verified planning to verified execution.
- Add a live rollout executor only if Codex exposes a safe atomic host surface for thread-message plus automation mutation, because the plugin can now package exact execution bundles but still cannot force those host actions to run transactionally from inside MCP.
- Add a richer hosted/operator UI surface on top of `manager_cross_project_dashboard`, such as a widget or artifact renderer, if Codex exposes a stable native dashboard handoff for plugin tools.

## Important Boundary

- The plugin can diagnose stale-session symptoms and prove that a fresh packaged wrapper is healthy.
- It still cannot force an already-poisoned in-memory Codex MCP binding to refresh from inside the plugin itself.
- Server parity for the current documented tool surface is now in place; remaining gaps are mostly host-surface limitations and higher-level live rollout automation.
- Add a public repo release flow with README/install/update docs and keep the repo clean of cache/build-only artifacts so external installs stay reproducible.
- Extend `manager_environment_health` with local Codex host bootstrap status so plugin users can see whether Startup, watchdog state, and the hidden health task are actually armed.
