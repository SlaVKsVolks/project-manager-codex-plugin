# Project Manager Rock-Solid Operations Design

**Date:** 2026-08-07
**Status:** Approved for implementation

## Goal

Make Project Manager dependable and useful during normal Codex work by adding
durable coordination state, repairing safe host metadata drift, publishing a
sanitized health snapshot to the private roadmap site, and maintaining that
surface through a fail-closed 15-minute Codex heartbeat.

The result must improve operational visibility without claiming that source,
package, or hosted-snapshot health proves an already-loaded Codex turn,
authenticated workflow, device, public edge, or production environment is
healthy.

## Current Baseline

The live Project Manager health surface currently reports:

- `overallStatus=healthy`;
- `coordinationGate=allow`;
- `heartbeatReady=true`;
- `safeForManagerAutomation=true`;
- ten stability invariants passing and no failed invariant;
- two readable threads with missing workspace hints as a non-blocking
  maintenance item;
- an advisory stale browser/computer-use installed-version marker; and
- no project-owned manager ledger or worker registry at the default paths.

The private roadmap site is deployed and source-backed, but it is not a live
monitor of the local Windows host. Its browser refresh can replace the bundled
documentation dataset from GitHub, while local repository changes require a
new generated snapshot and deployment.

## Selected Architecture

Use a private, sanitized snapshot pipeline instead of a remotely writable
health-ingestion endpoint.

Every heartbeat reads live Project Manager health and stability through the
existing supported wrappers, converts the results into a strict public-safe
schema, and compares that output with the last deployed snapshot. If no
meaningful field changed, the heartbeat performs no source-control or Sites
mutation. If the snapshot or documentation changed, it validates the data,
tests and builds the site, commits only generated site-owned files in an
isolated deployment worktree, pushes the exact commit, and privately deploys
one new Sites version.

This design deliberately avoids a D1 write endpoint, a Sites SIWC bypass token,
a long-lived publishing credential, a localhost bridge, or a public health
endpoint. Sites source credentials remain short-lived and are requested only
during an authorized publish transaction.

## Components

### 1. Durable manager state

Create project-owned state under `docs/project-manager/`:

- `worker-registry.json` starts with an explicit empty active-worker set,
  archived-worker set, schema version, project root, and update timestamp.
- `manager-ledger.jsonl` starts with one bootstrap decision event recording the
  health baseline, the approved automation architecture, and the evidence
  boundary.

The Project Manager tools remain the only normal writers after bootstrap.
Automation must inspect the registry and ledger before recording coordination
claims. Empty state means no workers are active; it must never be interpreted
as proof that old or external tasks are healthy.

### 2. Safe host metadata repair

Run the existing `manager_self_repair` hot-repair path with bounded attempts.
The repair is allowed to update only Codex workspace-hint and projectless-output
metadata. It must create a backup, append provenance, perform read-back
verification, and avoid plugin installation, cache/config rewriting, process
cleanup, restart, thread replacement, or automation cutover.

After repair, rerun `manager_environment_health` and
`manager_stability_audit`. The repair is accepted only when the missing-hint
count is zero or the remaining condition is explicitly classified as
non-blocking with readable evidence. The browser/computer-use version marker is
bootstrap-owned: this implementation observes it and reports its advisory
state but does not manually rewrite it or restart Codex to manufacture a green
result.

### 3. Public-safe health snapshot

Add a pure Python sanitizer that consumes compact environment-health and
stability JSON and emits schema version 1 with only these fields:

- generation timestamp and configured maximum age;
- plugin version;
- overall health status;
- coordination gate;
- heartbeat readiness;
- fresh-thread and same-loaded-turn callability classifications;
- stability status, automation-safety boolean, invariant count, and failed
  invariant count;
- sorted blocking, advisory, and non-blocking finding codes;
- source revision and dirty-state boolean; and
- a deterministic content digest that excludes the generation timestamp.

The sanitizer must reject malformed inputs and recursively assert that output
contains no absolute paths, home-directory fragments, usernames, emails,
thread IDs, process IDs, command lines, log excerpts, environment values,
credentials, tokens, or private URLs. It must not copy arbitrary tool fields.

A PowerShell wrapper resolves a healthy bundled Python runtime, invokes the
supported Project Manager environment-health and stability wrappers in compact
mode, stores raw output only in temporary files, calls the sanitizer, and
removes temporary files in `finally` cleanup. Raw health output is never added
to Git or Sites.

### 4. Roadmap health experience

Add the generated snapshot at
`site/src/data/project-manager-health.json`. The roadmap site shows a compact
operator-health section with:

- a clear `HEALTHY`, `DEGRADED`, `UNHEALTHY`, or `STALE` label;
- coordination and heartbeat state as text, not color alone;
- snapshot age and the configured freshness ceiling;
- stability invariant totals;
- blocking and advisory codes with plain-language evidence boundaries; and
- a statement that the snapshot is not direct proof of the viewer's current
  Codex loaded-turn binding.

The browser computes staleness from the snapshot timestamp. A stale snapshot
must never display as healthy, even when its embedded health status was healthy
when generated. The site remains useful when the health file is absent or
invalid by showing `UNAVAILABLE` without replacing the documentation dataset.

### 5. Isolated publishing worktree

Create a dedicated deployment worktree and `codex/` branch outside the user's
dirty checkout. The live source workspace remains the input for documentation
and health generation, so uncommitted local Markdown can be represented in the
snapshot without staging or committing unrelated files.

The pipeline copies only these generated artifacts into the clean deployment
worktree:

- `site/src/data/project-manager.json`;
- `site/src/data/project-manager-health.json`.

The deployment branch contains the approved site implementation and publishing
scripts. Automation never stages broad globs and refuses to continue when the
deployment worktree has unrelated changes, a merge conflict, a detached HEAD,
or a non-fast-forward source state.

### 6. Fifteen-minute Codex heartbeat

Reuse the existing paused `project-manager-mcp-health-monitor` automation
instead of creating a duplicate. Retarget it to this task and run every 15
minutes.

Each run follows this sequence:

1. Read the durable registry and ledger.
2. Run environment health and stability audit.
3. If either critical gate is blocked, record a blocker and notify with the
   first actionable finding; do not publish.
4. Generate sanitized health and documentation snapshots from the live source
   workspace into temporary files.
5. Compare deterministic digests with the deployment worktree.
6. If unchanged, record a quiet tick and return `DONT_NOTIFY`.
7. If changed, copy only the two generated artifacts, run focused Python and
   Node tests, run the production build, inspect the scoped diff, commit, push,
   package, save one Sites version, and deploy privately.
8. Poll deployment status to a terminal result and record success or failure in
   the ledger.

The heartbeat must use Project Manager's automation plan/finalize contract so
durable state records an automation update only after the Codex host action
succeeds. It must not dispatch workers while Objective Runner owns execution,
while a transaction journal is incomplete, or while the coordination gate is
blocked.

### 7. Sites lifecycle

Keep the current roadmap site private and reuse its persisted project ID.
Publishing uses a new short-lived source credential for each needed push,
packages the exact validated commit, saves one version, deploys that version
privately, polls to success or failure, and opens the successful URL in Codex.

The extra empty Sites shell is not part of the deployment pipeline. The current
connector has no delete-site action, so the implementation records it as an
undeployed cleanup item and performs no speculative access or metadata changes
against it.

## Failure Handling

- Health or stability failure blocks publication and produces a notification.
- Malformed or privacy-unsafe snapshot output fails generation and preserves
  the previous deployed snapshot.
- Missing wrappers or bundled Python produce `UNAVAILABLE`; they do not trigger
  an alternate unreviewed runtime.
- A dirty deployment worktree blocks publication without cleaning or resetting
  user data.
- Test or build failure blocks commit, push, version save, and deployment.
- Push failure blocks Sites version creation.
- Sites save or deployment failure records the exact phase and preserves the
  previously live version.
- A stale snapshot is labeled stale by the browser even if the automation has
  stopped silently.
- Automation never repairs plugin caches, restarts Codex, kills processes,
  archives tasks, or changes site sharing.

## Security and Privacy

- The private Sites access policy remains owner-only.
- No inbound write endpoint or bypass credential is created.
- The health schema is allowlist-only and tested against path, identity, and
  secret leakage.
- Raw health and stability payloads exist only in temporary local files and are
  removed after use.
- Source repository credentials are per-command, short-lived, and never stored
  in Git configuration, remotes, files, logs, automation prompts, or ledger
  events.
- Local repository absolute paths are never serialized into site data.
- Health state is evidence-labeled and time-bounded.

## Verification Strategy

Implementation follows red-green-refactor cycles for every new function:

- Python unit tests cover allowlisted projection, malformed input, deterministic
  digesting, and recursive privacy rejection.
- PowerShell contract tests cover wrapper arguments, temporary-file cleanup,
  non-zero exit propagation, and output-path behavior.
- Node tests cover valid, stale, unavailable, degraded, and unhealthy display
  classifications plus the static UI contract.
- Worker tests confirm SPA fallback and health JSON asset delivery.
- Integration verification runs the public snapshot wrapper against the live
  health wrappers and scans the emitted JSON for forbidden data.
- Existing Project Manager release checks, model-export health, environment
  health, and stability audit run before automation activation.
- The final site build is packaged, privately deployed, polled to success, and
  opened in Codex.
- A post-activation heartbeat read-back must prove the automation exists,
  targets this task, uses a 15-minute cadence, and has a successful host result.

## Definition of Done

- Durable registry and ledger exist and are readable through Project Manager.
- Safe workspace metadata repair has backup and read-back evidence.
- Fresh health reports remain dispatch-safe and all critical stability
  invariants pass.
- A privacy-tested health snapshot is visible on the private roadmap site and
  becomes stale automatically when not refreshed.
- The existing health automation is active at a 15-minute cadence and points to
  this task.
- Unchanged runs make no commit or deployment.
- Changed runs are bounded to generated site artifacts and fail closed before
  every irreversible stage.
- The deployment succeeds privately and the exact URL opens in Codex.
- Existing unrelated working-tree changes remain untouched.
