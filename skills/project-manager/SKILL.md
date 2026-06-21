---
name: project-manager
description: Cross-project manager-thread workflow for Codex worker coordination, heartbeat checks, worker dispatch, stale-thread follow-up, and worker-final review.
---

# Project Manager

Use this skill for top-level Codex threads that manage worker threads across projects.

## Operating Model

Use a project-agnostic manager workflow:

1. Start with tick or state inspection before reading every worker thread.
2. Read worker threads only when they are stale, blocked, contradictory, interrupted, expired, or dispatch-required.
3. If a worker is healthy and moving, leave it alone.
4. Prefer the smallest shippable next slice.
5. Keep worker ownership narrow and avoid mixed scopes.
6. Use heartbeats to push implementation forward instead of passively monitoring.
7. If safe delegation is not possible, take direct ownership of the next slice.
8. Prefer a GPT manager thread for judgement, review, ownership decisions, and final acceptance.
9. Use DeepSeek worker threads for narrow implementation packets when speed or parallel execution helps.

## Tool Policy

- `manager_model_transport_health`: verify live transport confidence for a specific model (wrapper health, stale-session suspicion, recent MCP connectivity); should inform routing decisions before dispatch
- `manager_model_export_health`: verify canonical catalog, generated proxy exports, export metadata, source/cache parity, and disabled-model leakage before release or after crashes
- `manager_model_policy_validate`, `manager_model_policy_diff`, `manager_model_cost_policy`: validate model policy overlays, compare current policy/export state, and expose cheap/default/escalation/final-review tiers
- `manager_lane_health_from_readback`: given a thread observation and registry entry, classify lane health including the silent-after-delivery signal; returns healthy only when a visible assistant-authored acknowledgment or worker final turn exists
- `manager_dispatch_transaction_plan`: canonical fail-closed transaction planner over dispatch, readback, registry writes, and ledger writes; use this when managers need a single source for what is safe to mutate
- `manager_atomic_dispatch_prepare` and `manager_atomic_dispatch_finalize`: canonical host-action transaction contract for worker dispatch; prepare emits `create_thread`/`read_thread` actions, finalize writes registry/ledger only after host result evidence
- `manager_atomic_lane_recovery_prepare` and `manager_atomic_lane_recovery_finalize`: host-action transaction contract for dead or unreadable lane replacement
- `manager_host_action_result_validate`: validate Codex host action results before any atomic finalize call
- `manager_thread_supervisor_plan` and `manager_thread_supervisor_finalize`: bounded `read_thread` supervision contract for detecting stale, silent-after-delivery, dead-reference, and stuck-thinking lanes
- `manager_heartbeat_automation_plan` and `manager_heartbeat_automation_finalize`: fail-closed heartbeat automation update contract; records `automation_updated` only after host success
- `manager_transaction_journal_record`, `manager_transaction_journal_read`, `manager_transaction_resume_plan`, and `manager_transaction_close`: durable dispatcher journal tools; use them around every atomic host-action transaction so crashes and stale thinking turns resume from evidence instead of guesswork
- `manager_dispatcher_runbook`: returns the exact Codex-side dispatcher sequence and host-tool result shapes for dispatch, lane recovery, supervision, and heartbeat automation
- `manager_worker_packet_contract` and `manager_successor_packet_plan`: generate role/model packet contracts and deterministic successor packet decisions after accepted finals
- `manager_accept_worker_final_and_plan_next`: accept a validated worker final, append ledger event, and sequence the successor step (review, dispatch, or manager takeover)
- `manager_registry_reconcile`: reconcile the active registry against ledger events, archiving lanes with no recent activity and flagging lanes where delivery is visible but no ack/final turn exists (stale delivery)
- `manager_tick`: first pass for project state or manager heartbeat state; accepts `stateFile` or `stateJson` with generic `workers` data and returns attention classifications plus `heartbeatDecisionHint`
- `manager_prepare_dispatch`: prepare narrow worker packets
- `manager_select_worker_model`: choose the worker model from policy, preferring `deepseek-v4-flash` and escalating to `deepseek-v4-pro` only for higher-risk slices
- `manager_model_roster`: show supported manager/worker model roles, including `deepseek-v4-flash` and `deepseek-v4-pro`
- `manager_project_profile`: load optional profile defaults for generic, Minecraft, Conan, or SaaS-style projects
- `manager_load_project_profile`: merge a project-owned `.project-manager.json` style profile with built-in defaults
- `manager_environment_health`: verify plugin version, MCP log location, model routing, ledger/registry paths, and heartbeat readiness
- `manager_repair_plan`, `manager_self_repair`, and `manager_health_snapshot`: convert health findings into operator-safe repair steps, run safe local self-repair for wrapper/runtime/install drift, and produce compact crash/restart context
- `manager_loaded_turn_recovery_packet`: generate the exact message a stale already-loaded turn should follow when it needs a fresh rebind turn
- `manager_loaded_turn_rescue_plan` and `manager_loaded_turn_rescue_finalize`: same-thread rescue contract for a healthy external context or heartbeat to push a fresh rebind follow-up into a stale manager thread and verify that the new turn became visible
- `manager_operational_audit`: score lane health from registry plus ledger state and emit an ordered action queue instead of relying on ad hoc manager judgement
- `manager_operator_runbook`: turn transport-health recommendations such as `continue`, `reload session`, or `new thread recommended` into exact human steps
- `manager_cross_project_summary`: summarize multiple project-owned ledgers, registries, and worker lists into a dashboard payload
- `manager_cross_project_dashboard`: return a manager-facing dashboard view with summary cards, ranked projects, operator queue, and markdown for multi-project triage
- `manager_project_readiness_score`, `manager_next_best_action`, and `manager_operator_digest`: rank readiness and the next action across active projects without requiring a GUI
- `manager_heartbeat_bootstrap`: generate a recurring heartbeat prompt plus ledger/registry setup checklist
- `manager_automation_rollout_helper`: prepare rollout packets for live manager threads, including updated heartbeat prompts, notification messages, and ledger event plans
- `manager_rollout_execution_bundle`: prepare fail-closed rollout execution bundles with exact `send_message_to_thread`, `automation_update`, and post-success `manager_append_ledger_event` action plans
- `manager_release_checklist`: produce release gates covering source tests, cached tests, wrapper smoke, proxy export parity, export health, and disabled-model route checks
- `manager_score_worker_final`: score worker-final quality beyond required fields
- `manager_prepare_thread_action`: prepare `create_thread`, `send_message_to_thread`, or `read_thread` action plans with ledger guidance
- `manager_recommend_recovery`: recommend wait, read, recover, replace, or manager takeover from state plus ledger
- `manager_restart_recovery`: combine recovery recommendation with a restart handoff
- `manager_generate_handoff_pack`: generate a compact markdown handoff for restarts, crashes, or compaction
- `manager_compact_ledger`: compact long ledgers into checkpoint JSON while retaining recent events
- `manager_update_worker_registry`: create or update a project-owned worker lane registry
- `manager_read_worker_registry`: read the worker lane registry
- `manager_registry_maintenance`: archive dead, replaced, or completed lanes out of the active registry so heartbeat state stays trustworthy
- `manager_notification_packet`: generate concise update prompts for managers or workers after policy/model changes
- `manager_append_ledger_event`: append a durable JSONL event for dispatches, finals, observations, blockers, or decisions
- `manager_read_ledger`: read recent ledger events with optional assignment or event-type filters
- `manager_ledger_summary`: summarize event counts, latest event, active assignments, and latest blockers
- `manager_prepare_worker_thread`: prepare a `create_thread` request for a managed worker thread
- `manager_verified_dispatch`: canonical verified-delivery flow for new or existing worker dispatches; fail closed unless readback shows a visible new turn
- `manager_replace_dead_lane`: canonical replacement flow for unreadable or dead historical workers
- `manager_register_dispatch_after_send`: only after `send_message_to_thread` succeeds
- `manager_register_worker_final`: validate worker-final structure
- `manager_summarize_thread_observation`: normalize read-thread findings
- `manager_recent_events` and `manager_crash_forensics_pack`: gather MCP/proxy/model/export evidence after crashes or stale-thread incidents
- When a strict worker final is large, prefer `workerFinalPath` over a huge inline `workerFinalJson` string when calling worker-final review/acceptance tools. This reduces the chance of Codex-side JSON argument parse failures on long payloads.

## Phase-Aware Lane Semantics

Lane health is determined by evidence of actual worker engagement, not by delivery alone:

- **Visible delivery is not healthy progress.** A message may be sent to a thread without any sign the worker has received or acted on it.
- **Assistant-authored acknowledgment or worker final is required** for a lane to be classified as healthy. A silent worker that received a dispatch but never replied is not healthy.
- **Silent-after-delivery must block quiet `DONT_NOTIFY`.** If a lane shows a dispatched message with no visible response turn, the manager must NOT return `DONT_NOTIFY`. The heartbeat must surface this as an attention item requiring follow-up (inspect, recovery, or replacement).

Use `manager_lane_health_from_readback` to classify lane health after thread observation, and `manager_registry_reconcile` to flag workflows that delivered but never heard back. When Codex exposes exact readback identifiers, preserve them through the plugin: `deliveryTurnId`, `deliveryMessageId`, `deliveryVerificationEvidence`, `acknowledgedTurnId`, and `acknowledgedMessageId` make durable lane state much more trustworthy than narrative summaries alone.

## Platform-Aware Routing

Model routing must consider both policy assignment and live transport confidence:

- **GPT remains manager/reviewer owner.** Keep the top project-manager thread on a GPT model such as `gpt-5.4` or `gpt-5.5`.
- **`deepseek-v4-flash` is the default implementation worker.** Use for narrow, fast, bounded implementation packets, small test fixes, exploration, and mechanical edits.
- **`deepseek-v4-pro` is escalation-only.** Route to Pro only for higher-risk, architecture-sensitive, or larger implementation slices that Flash cannot handle reliably.
- **`qwen3.7-plus` remains disabled.** This model must not be routed to worker threads under any circumstance.
- **Routing should consider live transport confidence, not only static preference.** Before dispatching to any worker model, run `manager_model_transport_health` for that model. If transport health is degraded (stale session, wrapper mismatch, MCP connectivity issues), consider a different model or take operator recovery steps before dispatch.

Project profiles can override `managerModels`, `workerModels`, `defaultManagerModel`, `defaultWorkerModel`, and `seniorWorkerModel`. Use `manager_model_roster` with `profileFile` when a project defines custom routing so workers are selected from project policy instead of plugin defaults.

The plugin should prepare worker-thread creation payloads, but the manager must still call Codex thread tools explicitly. Prefer `manager_verified_dispatch` instead of manual `prepare -> create/send -> readback -> registry/ledger update` stitching. If readback does not show a visible new turn, fail closed and do not update durable lane state.

## Host-Action Atomic Dispatcher

The plugin does not call Codex host APIs directly. Instead, the manager acts as the dispatcher:

1. Call `manager_atomic_dispatch_prepare` or `manager_atomic_lane_recovery_prepare`.
2. Call `manager_transaction_journal_record` with phase `prepared` before executing host actions.
3. Execute each returned `hostActions` item using Codex app tools such as `create_thread`, `send_message_to_thread`, `read_thread`, or `automation_update`.
4. Append host result fragments with `manager_transaction_journal_record` using phase `host_action_started` or `readback_pending`.
5. Pass the collected `hostResults` to the matching finalize tool.
6. Call `manager_transaction_close` as `finalized` only with finalize evidence, or as `failed`/`abandoned` with an explicit reason.
7. Trust registry/ledger changes only from finalize output.

Atomic finalize must fail closed when a host action fails, readback is missing, or readback does not prove a visible turn. `workerAcknowledged=true` requires an assistant-authored worker turn or strict worker final; manager-authored delivery alone is not healthy progress.

If Codex host tooling does not support a requested third-party worker model, record `modelRoutingUnavailable` in the registry or transaction payload and fail closed unless a project profile explicitly allows native GPT fallback.

For recurring heartbeats, use `manager_heartbeat_automation_plan`, execute its `automation_update` action, then call `manager_heartbeat_automation_finalize`. Do not record `automation_updated` from intent alone.

Use `manager_dispatcher_runbook` whenever a manager thread needs the exact Codex-side execution sequence or expected result shape. Quiet heartbeat is forbidden while any transaction journal entry remains `prepared`, `host_action_started`, or `readback_pending`.

## Model Export Boundaries

The plugin owns model identity, aliases, policy roles, disabled status, provider labels, runtime guidance, and proxy-facing generated exports. The proxy is transport plumbing and should consume generated exports rather than becoming a second policy source.

- `tool_manager_model_catalog(writeExports=true)` writes exports only under the active plugin root by default.
- Do not mirror exports from tests, temporary `LIVE_MODELS_PATH` values, or monkeypatched paths into the source plugin or cache.
- Use `manager_model_export_health` before release, after model routing changes, and after Codex crashes. It flags poisoned pytest/temp paths, source/cache export mismatches, disabled-model route leakage, and catalog/export drift.
- `qwen3.7-plus` must remain visible only as disabled policy metadata. It must not appear in proxy model lists or routeable worker surfaces.

## Subagent-Driven Execution Roles

When a task needs decomposition into multiple worker packets, use explicit subagent roles:

- **implementer**: receives a narrow, bounded packet with a concrete goal, constraints, and definition of done. Does one bounded task, verifies it, and returns a worker final.
- **spec reviewer**: receives the same packet plus the output. Reviews for correctness against spec, identifies gaps, and returns structured findings.
- **code quality reviewer**: receives the same packet plus the output. Reviews for code quality, maintainability, test coverage, and returns structured findings.
- **One task per worker packet.** A single worker receives exactly one assignment. Do not batch multiple tasks into one dispatch. If a task is too large, decompose into independent packets and dispatch sequentially, allowing the manager to accept each final before sequencing the next review or dispatch.

The manager accepts worker finals through `manager_accept_worker_final_and_plan_next`, which sequences the successor step: route to spec reviewer, route to code quality reviewer, or dispatch the next implementation packet.

## State Shape

For `manager_tick`, pass project-owned state instead of embedding project rules in the plugin. A compact state can include:

- `project_root`, `manager_thread_id`, `mode`, `observed_state`
- `dispatch_required`
- `stale_after_minutes`
- `workers` as either an array or object keyed by manager labels

Each worker may include `label`, `thread_id` or `threadId`, `assignment_id` or `assignmentId`, `status`, `last_progress_at`, and `blockers`.

## Project Profiles

Projects can keep a small JSON profile such as `.project-manager.json` and pass it to `manager_load_project_profile`. Use it for stale thresholds, ledger path hints, registry path hints, heartbeat interval, preferred manager/worker models, lane names, and final-quality expectations. Keep project-specific policy in the profile or project docs, not in the base plugin.

## Ledger Shape

Use a project-owned JSONL ledger when heartbeat memory matters. Recommended location is inside the project workspace or manager artifacts directory, not inside the plugin cache.

Supported event types:

- `tick`
- `dispatch_prepared`
- `dispatch_sent`
- `dispatch_failed`
- `worker_final`
- `thread_observation`
- `model_route`
- `blocker`
- `decision`

Write ledger events after real actions. For dispatches, preserve the send-then-register discipline: append `dispatch_sent` only after `create_thread` or `send_message_to_thread` succeeds; append `dispatch_failed` when delivery fails.

Use `manager_compact_ledger` when a ledger grows too large. Store the checkpoint beside project manager artifacts and continue with the live JSONL ledger for new events.

## Recovery And Handoff

Use `manager_recommend_recovery` when a heartbeat repeats without material progress or when thread delivery becomes unreliable. Prefer changing workflow over looping on the same blocker:

- wait when workers are healthy
- read thread when a worker is stale
- send recovery when a worker is blocked
- replace the worker or take manager ownership after repeated delivery failures
- review worker finals before accepting completion

When `manager_tick` returns `attentionRequired=true` or `heartbeatDecisionHint=NOTIFY`, do not return a quiet `DONT_NOTIFY` heartbeat. Unknown, unreadable, stale, blocked, or review-needed workers require inspection, recovery, replacement, or explicit notification. Do not synthesize conceptual aliveness from missing or unreadable thread ids. In addition, per phase-aware lane semantics, silent-after-delivery workers (delivery visible but no ack/final turn) must also produce NOTIFY, not DONT_NOTIFY.

Use `manager_generate_handoff_pack` before restarts, compaction, or long pauses. The handoff should include project root, manager id, worker status, recent ledger events, and the next resume instruction.

Use `manager_restart_recovery` after a crash or restart. It combines ledger/state recovery with a handoff so the manager can resume without rereading every worker thread.

Use `manager_environment_health` at the start of a new manager session or after a plugin/model-routing change. Its transport health block should be the first place to check fresh wrapper viability, source/cache mismatch, stale-session suspicion, recent MCP log health, orphan processes, and the recommended operator action. Follow that with `manager_model_export_health`, `manager_repair_plan`, or `manager_operator_runbook` when the operator action is anything other than a simple `continue`. Use `manager_health_snapshot` when a compact crash/restart summary needs to be pasted into another manager thread. Use `manager_heartbeat_bootstrap` when creating or repairing recurring manager heartbeat prompts, and treat its maintenance policy block as the canonical cadence for `manager_registry_reconcile` plus `manager_registry_maintenance`.

Crash recovery order:

1. Run `manager_health_snapshot`.
2. Run `manager_model_export_health`.
3. Run wrapper smoke or `manager_release_checklist` gates if export or wrapper status is degraded.
4. Inspect active managers from durable registry/ledger state only.
5. Resume from verified lane state; do not trust in-memory “thinking” turns or stale active flags.
6. If a specific loaded turn still lacks project-manager MCP after the repair, use `manager_loaded_turn_recovery_packet` inside that stale turn and, from any healthy external manager context or heartbeat, prefer `manager_loaded_turn_rescue_plan/finalize` to push and verify a same-thread fresh rebind follow-up before abandoning the manager thread.

Incomplete atomic transaction recovery:

1. Inspect the transaction id from the manager prompt, ledger, or registry `activeTransactionId`.
2. Call `manager_transaction_resume_plan` against the project-owned transaction journal.
3. Re-run the returned `read_thread` action for the target thread if a host dispatch may have succeeded.
4. Append the recovered host result with `manager_transaction_journal_record`.
5. Call `manager_host_action_result_validate` or the matching finalize tool only if validation proves visible readback.
6. Otherwise close or preserve the transaction as failed and do not mark the lane active.

Do not trust:

- delivery-only turns with no assistant-authored worker acknowledgment
- stale registry `active` flags without `evidenceSource`
- source/cache mismatches
- test-generated exports or temp `liveModelsPath` metadata
- disabled model route leakage

MCP startup and defensive errors are written to the MCP log file reported by `manager_environment_health`. The packaged MCP entry must launch through `./scripts/project-manager-mcp.exe`, a windowless stdio-preserving wrapper; do not switch it to `pythonw`, because hiding the Python console that way can break stdio MCP startup and leave Codex waiting indefinitely.

## Worker Lane Registry

Use `manager_update_worker_registry` after creating, replacing, or reassigning a worker. Track worker id, thread id, assignment id, model, status, last progress, `lastVisibleTurnAt`, `lastVerifiedHealthyAt`, `deliveryVerified`, `deliveryTurnId`, `deliveryMessageId`, `deliveryVerificationEvidence`, `acknowledgedTurnId`, `acknowledgedMessageId`, `replacementOfThreadId`, `deadReferenceReason`, and `staleConfidence`. Use `manager_read_worker_registry` before deciding whether to reuse, replace, or interrupt a lane, and run `manager_registry_maintenance` periodically so dead or superseded workers move into `archivedWorkers` instead of polluting live lane decisions.

## Canonical Flow

Treat this as the default manager loop:

1. Run `manager_environment_health` at manager-session start or after plugin/model changes.
2. Run `manager_model_export_health` after plugin/model changes, releases, or crashes.
3. If health recommends anything other than `continue`, run `manager_repair_plan` or `manager_operator_runbook`. When the action is `run codex self repair` and the issue is local project-manager MCP runtime/install buildup, prefer `manager_self_repair` before abandoning the manager thread.
4. Run `manager_model_transport_health` for the intended dispatch model to verify live transport confidence before routing.
5. Use `manager_operational_audit` on the project registry and ledger to decide whether a lane is healthy, stale, dead, blocked, or unverified.
6. Use `manager_dispatcher_runbook` when the manager needs the exact host-action sequence.
7. Use `manager_atomic_dispatch_prepare`, immediately journal phase `prepared`, execute returned host actions, journal host results, then call `manager_atomic_dispatch_finalize`; do not manually write registry or ledger state before verified readback.
8. Use `manager_transaction_resume_plan` before new dispatch if any journal transaction is incomplete.
9. Use `manager_atomic_lane_recovery_prepare/finalize` for unreadable historical workers.
10. Use `manager_thread_supervisor_plan/finalize` for bounded live lane supervision and stuck-thinking detection.
11. Use `manager_lane_health_from_readback` after ad hoc thread observations to classify lane health with silent-after-delivery detection.
12. After worker finals arrive, call `manager_accept_worker_final_and_plan_next` and `manager_successor_packet_plan` to validate, log, and sequence the successor step.
13. Run `manager_registry_reconcile` periodically to flag lanes with silent-after-delivery and archive truly dead lanes.
14. After meaningful churn, run `manager_registry_maintenance` so only active lanes stay in the live registry.
15. For recurring heartbeats, use `manager_heartbeat_automation_plan/finalize` plus the transaction journal instead of recording automation changes from intent.
16. After plugin workflow or policy releases, use `manager_release_checklist`, `manager_automation_rollout_helper`, and `manager_rollout_execution_bundle` to package verification and live rollout.
17. When supervising multiple projects, use `manager_cross_project_dashboard`, `manager_project_readiness_score`, `manager_next_best_action`, or `manager_operator_digest` as the first triage surface, then drill into per-project audits only where needed.
18. If a manager thread is healthy in durable state but its loaded turn still returns missing MCP or `Transport closed`, use `manager_loaded_turn_rescue_plan`, execute its same-thread `send_message_to_thread` plus `read_thread` steps, then call `manager_loaded_turn_rescue_finalize` before trusting that thread again.

## Notifications

Use `manager_notification_packet` when plugin policy, model routing, or coordination rules change. Send the generated prompt to manager/worker threads that need the update, then record a `decision` or `model_route` ledger event if the update changes execution behavior.

## Worker Final Quality

`manager_register_worker_final` checks required fields. `manager_score_worker_final` checks whether the final is useful enough for manager review. Prefer finals with concrete artifact paths, verification commands/results, explicit blockers, and a non-vague next action.

## Boundaries

- Do not assume one project's runtime, release, or queue rules apply to another project.
- Use project-local docs, artifacts, queues, and verification outputs as the truth when that project defines them.
- Do not use this plugin to install repo-specific hooks globally.
