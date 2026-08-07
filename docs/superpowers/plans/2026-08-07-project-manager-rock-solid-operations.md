# Project Manager Rock-Solid Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable Project Manager coordination state, safe workspace-metadata repair, a privacy-tested health snapshot, and a fail-closed 15-minute private roadmap publishing heartbeat.

**Architecture:** Keep runtime coordination state in ignored project-owned files under the canonical source checkout. Implement a pure allowlist-only Python health sanitizer and a PowerShell orchestration wrapper, render its generated snapshot in the existing React site, and maintain deployments from a clean `codex/project-manager-rock-solid` worktree while reading documentation and health from the live source checkout.

**Tech Stack:** Python 3 standard library, pytest, PowerShell 7, React 18, Vite 5, Node's built-in test runner, Project Manager MCP tools, Codex heartbeat automation, ChatGPT Sites.

## Global Constraints

- Preserve every existing unrelated modification and untracked file in `C:\Users\SlaVKs\Documents\Github\project-manager`.
- Make source edits only in `C:\Users\SlaVKs\Documents\Github\project-manager\.worktrees\project-manager-rock-solid` on branch `codex/project-manager-rock-solid`.
- Keep the live source checkout as the authoritative input for generated Markdown and runtime health.
- Never serialize absolute paths, usernames, emails, thread IDs, process IDs, logs, commands, environment values, credentials, tokens, or private URLs into site data.
- Do not create a D1 write endpoint, SIWC bypass token, public site, long-lived repository credential, localhost bridge, or app-owned authentication system.
- Do not restart Codex, kill processes, rewrite plugin caches/configuration, archive tasks, or change site access.
- Use Project Manager's atomic heartbeat plan/finalize contract around the Codex automation mutation.
- A blocked health gate, failed stability invariant, malformed snapshot, dirty deployment worktree, failed test/build, failed push, failed version save, or failed deployment stops the pipeline before later mutations.
- Use `gpt-5.6-luna` for the heartbeat and normal maintenance.
- Keep the existing private Sites project ID from `.openai/hosting.json` unchanged.

---

### Task 1: Create the isolated implementation worktree

**Files:**
- Verify only: `C:\Users\SlaVKs\Documents\Github\project-manager`
- Modify before worktree creation: `.gitignore`
- Create worktree: `C:\Users\SlaVKs\Documents\Github\project-manager\.worktrees\project-manager-rock-solid`
- Create branch: `codex/project-manager-rock-solid`

**Interfaces:**
- Consumes: committed `main` at or after design commit `9580001`.
- Produces: a clean worktree used for every code edit, test, build, and commit in Tasks 2-7.

- [ ] **Step 1: Verify the source checkout and target worktree path**

Run:

```powershell
git -C C:\Users\SlaVKs\Documents\Github\project-manager rev-parse --show-toplevel
git -C C:\Users\SlaVKs\Documents\Github\project-manager status --short
Test-Path -LiteralPath C:\Users\SlaVKs\Documents\Github\project-manager\.worktrees\project-manager-rock-solid
```

Expected: the repository root is exact, existing unrelated changes are visible, and the target worktree does not exist.

- [ ] **Step 2: Ignore the project-local worktree directory**

Run `git check-ignore -q .worktrees`. If it is not already ignored, add this exact line to `.gitignore`, verify the scoped diff, and commit it before creating the worktree:

```gitignore
.worktrees/
```

- [ ] **Step 3: Create the isolated branch and worktree**

Run:

```powershell
git -C C:\Users\SlaVKs\Documents\Github\project-manager worktree add -b codex/project-manager-rock-solid C:\Users\SlaVKs\Documents\Github\project-manager\.worktrees\project-manager-rock-solid HEAD
```

Expected: Git creates the branch without changing the source checkout.

- [ ] **Step 4: Verify isolation**

Run:

```powershell
git -C C:\Users\SlaVKs\Documents\Github\project-manager\.worktrees\project-manager-rock-solid status --short
git -C C:\Users\SlaVKs\Documents\Github\project-manager\.worktrees\project-manager-rock-solid branch --show-current
```

Expected: empty status and branch `codex/project-manager-rock-solid`.

### Task 2: Bootstrap durable runtime state without polluting Git

**Files:**
- Modify: `.gitignore`
- Create: `docs/project-manager/README.md`
- Create locally and ignore: `docs/project-manager/worker-registry.json`
- Create locally and ignore: `docs/project-manager/manager-ledger.jsonl`

**Interfaces:**
- Consumes: Project Manager `manager_registry_maintenance`, `manager_append_ledger_event`, `manager_read_worker_registry`, and `manager_read_ledger`.
- Produces: an empty canonical registry plus a bootstrap decision event at stable absolute paths in the live source checkout.

- [ ] **Step 1: Add a failing runtime-path isolation test**

Add `tests/test_project_manager_runtime_state_contract.py`:

```python
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = (
    "docs/project-manager/worker-registry.json",
    "docs/project-manager/manager-ledger.jsonl",
    "docs/project-manager/transaction-journal.jsonl",
)


def test_runtime_state_paths_are_ignored_by_git() -> None:
    completed = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=ROOT,
        input="\n".join(RUNTIME_PATHS),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert tuple(completed.stdout.splitlines()) == RUNTIME_PATHS
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
uv run --isolated --no-project --with pytest -m pytest tests/test_project_manager_runtime_state_contract.py -q
```

Expected: FAIL because the runtime-state ignore entries do not exist.

- [ ] **Step 3: Add exact ignore rules and operating documentation**

Append these exact rules to `.gitignore`:

```gitignore
docs/project-manager/worker-registry.json
docs/project-manager/manager-ledger.jsonl
docs/project-manager/transaction-journal.jsonl
```

Create `docs/project-manager/README.md` documenting the three runtime files, the 15-minute cadence, `manager_environment_health` as the first gate, quiet `DONT_NOTIFY` rules, and the prohibition against treating delivery-only state as healthy.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Initialize the live registry and ledger through Project Manager tools**

Call `manager_registry_maintenance` with all archive switches false and the live-source registry path. Then call `manager_append_ledger_event` with:

```json
{
  "eventType": "decision",
  "projectRoot": "C:\\Users\\SlaVKs\\Documents\\Github\\project-manager",
  "managerThreadId": "019fdc00-0ddc-7472-bdbd-55c6d5daa983",
  "ledgerFile": "C:\\Users\\SlaVKs\\Documents\\Github\\project-manager\\docs\\project-manager\\manager-ledger.jsonl",
  "payload": {
    "record_kind": "operations_bootstrap",
    "architecture": "private_sanitized_snapshot",
    "heartbeat_interval_minutes": 15,
    "evidence_boundary": "hosted snapshot is not loaded-turn proof"
  }
}
```

Expected: registry and ledger files are created under the live source checkout.

- [ ] **Step 6: Read back durable state**

Call `manager_read_worker_registry` and `manager_read_ledger` with the exact live paths. Expected: zero workers and one decision event.

- [ ] **Step 7: Commit the tracked contract files**

```powershell
git add -- .gitignore docs/project-manager/README.md tests/test_project_manager_runtime_state_contract.py
git diff --cached --check
git commit -m "feat: define durable project manager runtime state"
```

### Task 3: Build the privacy-safe health sanitizer

**Files:**
- Create: `scripts/project_manager_public_health.py`
- Create: `tests/test_project_manager_public_health.py`
- Create generated seed: `site/src/data/project-manager-health.json`

**Interfaces:**
- Produces: `build_public_health_snapshot(health: dict, stability: dict, *, generated_at: str, max_age_minutes: int, source_revision: str, source_dirty: bool) -> dict`.
- Produces: `assert_public_snapshot_safe(snapshot: dict) -> None`.
- CLI consumes `--health-input`, `--stability-input`, `--output`, `--generated-at`, `--max-age-minutes`, `--source-revision`, and `--source-dirty`.
- Output schema uses `schemaVersion`, `generatedAt`, `maxAgeMinutes`, `contentDigest`, `source`, `environment`, `stability`, and `evidenceBoundary`.

- [ ] **Step 1: Write failing projection and digest tests**

Create fixtures containing safe top-level compact fields plus deliberately sensitive nested fields. Assert:

```python
snapshot = build_public_health_snapshot(
    health,
    stability,
    generated_at="2026-08-07T20:00:00Z",
    max_age_minutes=30,
    source_revision="a" * 40,
    source_dirty=True,
)
assert snapshot["schemaVersion"] == 1
assert snapshot["environment"]["overallStatus"] == "healthy"
assert snapshot["environment"]["coordinationGate"] == "allow"
assert snapshot["environment"]["heartbeatReady"] is True
assert snapshot["stability"]["failedInvariantCount"] == 0
assert len(snapshot["contentDigest"]) == 64
assert "C:\\Users" not in json.dumps(snapshot)
assert "thread-identifier" not in json.dumps(snapshot)
```

Build a second snapshot with a different `generated_at` and assert the same `contentDigest`.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
uv run --isolated --no-project --with pytest -m pytest tests/test_project_manager_public_health.py -q
```

Expected: import failure because the sanitizer does not exist.

- [ ] **Step 3: Implement strict field validation**

Use exact enums:

```python
HEALTH_STATUSES = {"healthy", "degraded", "unhealthy", "unknown"}
COORDINATION_GATES = {"allow", "block", "block_host_state", "unknown"}
CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,79}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,95}$")
```

Reject missing dictionaries, non-boolean readiness values, invalid timestamps, non-positive freshness ceilings, revisions other than `unknown` or forty lowercase hex characters, unsafe finding codes, and negative invariant counts.

- [ ] **Step 4: Implement allowlisted projection and deterministic digest**

Hash canonical JSON for every semantic field except `generatedAt` and `contentDigest`:

```python
canonical = json.dumps(digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Never traverse or copy arbitrary input keys.

- [ ] **Step 5: Add recursive privacy rejection tests**

Parametrize forbidden values for Windows paths, UNC paths, emails, UUID-style thread identifiers, bearer/token words, private URLs, and control characters. Expected: `ValueError` naming only the rejected field category, not the sensitive value.

- [ ] **Step 6: Implement CLI and atomic output writing**

Write UTF-8 JSON to a sibling temporary file, `flush`, `fsync`, and replace the destination. Remove the temporary file in `finally` after failures.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all sanitizer tests PASS.

- [ ] **Step 8: Commit the sanitizer**

```powershell
git add -- scripts/project_manager_public_health.py tests/test_project_manager_public_health.py
git diff --cached --check
git commit -m "feat: generate privacy-safe project manager health snapshots"
```

### Task 4: Add the live wrapper and bounded release preparation

**Files:**
- Create: `scripts/Sync-ProjectManagerPublicHealth.ps1`
- Create: `scripts/Prepare-ProjectManagerRoadmapRelease.ps1`
- Create: `tests/test_project_manager_public_health_wrappers.py`

**Interfaces:**
- `Sync-ProjectManagerPublicHealth.ps1` accepts `-ProjectRoot`, `-OutputPath`, `-MaxAgeMinutes`, optional `-PluginRoot`, and optional `-PythonExe`.
- `Prepare-ProjectManagerRoadmapRelease.ps1` accepts `-SourceRoot`, `-DeploymentRoot`, `-SkipBuild`, optional `-DocumentationInputPath`, and optional `-HealthInputPath`.
- Release preparation prints one compressed JSON object with `status`, `documentationChanged`, `healthChanged`, `changed`, `documentCount`, `healthDigest`, and `deploymentRoot`.

- [ ] **Step 1: Write failing behavioral wrapper tests**

Run the actual health wrapper against a temporary fake plugin root containing two PowerShell wrappers that emit complete compact fixture JSON. Pass `sys.executable` through `-PythonExe`, assert exit code zero, parse the output file, and assert the exact safe health fields and digest. Snapshot the temp directory before and after the call and assert that no raw health or stability file remains.

Create a temporary Git repository on branch `codex/project-manager-rock-solid` with the two generated destination files. Run the actual release wrapper with controlled `-DocumentationInputPath`, `-HealthInputPath`, and `-SkipBuild`; assert it changes only the two destination files and reports `changed=true`. Dirty an unrelated file, rerun, and assert non-zero exit without modifying either generated destination.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
uv run --isolated --no-project --with pytest -m pytest tests/test_project_manager_public_health_wrappers.py -q
```

Expected: FAIL because both production wrappers are absent.

- [ ] **Step 3: Implement active plugin-root resolution**

Resolution order is:

1. explicit `-PluginRoot` when both required wrappers exist;
2. source checkout when both wrappers exist;
3. newest installed cache directory under `C:\Users\SlaVKs\.codex\plugins\cache\personal\project-manager` containing both wrappers.

Fail with `Project Manager compact health wrappers are unavailable` when no complete pair exists.

- [ ] **Step 4: Implement temporary raw-payload handling**

Create two GUID-named files under `[System.IO.Path]::GetTempPath()`, redirect compact wrapper JSON into them, call the Python sanitizer, and delete both files in `finally`. Do not print raw payloads.

- [ ] **Step 5: Implement bounded release preparation**

The release wrapper must:

1. verify both roots are absolute directories;
2. verify the deployment root is on `codex/project-manager-rock-solid` and not detached;
3. reject existing changes outside the two generated files;
4. generate documentation and health into temporary files, or consume the two explicit controlled input paths when supplied;
5. compare SHA-256 hashes before copying;
6. copy only changed generated files;
7. run Python tests, site tests, and the site build unless `-SkipBuild` is passed; and
8. return machine-readable summary JSON.

- [ ] **Step 6: Run wrapper tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 7: Run a live integration generation**

```powershell
pwsh -NoProfile -File .\scripts\Sync-ProjectManagerPublicHealth.ps1 -ProjectRoot C:\Users\SlaVKs\Documents\Github\project-manager -OutputPath .\site\src\data\project-manager-health.json -MaxAgeMinutes 30
```

Expected: generated schema version 1, no raw wrapper output, and no forbidden privacy patterns.

- [ ] **Step 8: Commit wrappers and seed snapshot**

```powershell
git add -- scripts/Sync-ProjectManagerPublicHealth.ps1 scripts/Prepare-ProjectManagerRoadmapRelease.ps1 tests/test_project_manager_public_health_wrappers.py site/src/data/project-manager-health.json
git diff --cached --check
git commit -m "feat: prepare bounded roadmap health releases"
```

### Task 5: Render health truth and staleness in the site

**Files:**
- Create: `site/src/lib/health.js`
- Create: `site/src/lib/health.test.mjs`
- Modify: `site/src/App.jsx`
- Modify: `site/src/styles.css`
- Modify: `site/package.json`
- Modify: `site/src/lib/config.js`

**Interfaces:**
- `validateHealthSnapshot(value) -> value` rejects invalid schema/status fields.
- `classifyHealthSnapshot(snapshot, nowMs) -> { label, tone, stale, ageMinutes, explanation }`.
- Labels are exactly `HEALTHY`, `DEGRADED`, `UNHEALTHY`, `STALE`, and `UNAVAILABLE`.

- [ ] **Step 1: Write failing health classification tests**

Test exact cases:

```javascript
assert.equal(classifyHealthSnapshot(healthy, now).label, 'HEALTHY');
assert.equal(classifyHealthSnapshot(degraded, now).label, 'DEGRADED');
assert.equal(classifyHealthSnapshot(unhealthy, now).label, 'UNHEALTHY');
assert.equal(classifyHealthSnapshot(oldHealthy, now).label, 'STALE');
assert.equal(classifyHealthSnapshot(null, now).label, 'UNAVAILABLE');
```

Assert `coordinationGate !== 'allow'`, `heartbeatReady !== true`, or `safeForManagerAutomation !== true` cannot classify as healthy.

- [ ] **Step 2: Run site tests and verify RED**

```powershell
pnpm --ignore-workspace test
```

Expected: module-not-found for `health.js`.

- [ ] **Step 3: Implement validation and classification**

Compute age from `Date.parse(snapshot.generatedAt)` and classify stale when age exceeds `snapshot.maxAgeMinutes`. Return `UNAVAILABLE` for null or validation failure without throwing through React render.

- [ ] **Step 4: Add the operator-health section**

Import the bundled health JSON and render:

- visible heading `Environment health`;
- primary label and snapshot age;
- coordination gate, heartbeat, and stability totals;
- blocking/advisory code lists;
- exact evidence note `Snapshot evidence is not proof of this viewer's current loaded-turn binding.`

Use semantic `section`, `dl`, `time`, and status text. Color may reinforce but never replace labels.

- [ ] **Step 5: Update the package test command**

Add the behavioral `health.test.mjs` suite to the package test command. Keep existing sync and worker tests, and do not add source-text assertions for the React implementation.

- [ ] **Step 6: Run tests and build**

```powershell
pnpm --ignore-workspace test
pnpm --ignore-workspace build
```

Expected: all Node tests PASS and `dist/server/index.js` exists. Record existing non-blocking bundle warnings separately.

- [ ] **Step 7: Commit the site health experience**

```powershell
git add -- site/package.json site/src/App.jsx site/src/styles.css site/src/lib/config.js site/src/lib/health.js site/src/lib/health.test.mjs
git diff --cached --check
git commit -m "feat: show live project manager health on the roadmap"
```

### Task 6: Repair host metadata and prove current health

**Files:**
- Runtime mutation only: Codex workspace-hint/projectless-output metadata through Project Manager hot repair.
- Runtime evidence only: ignored registry, ledger, and Codex repair provenance/backup files.

**Interfaces:**
- Consumes: `manager_self_repair`, `manager_environment_health`, `manager_model_export_health`, and `manager_stability_audit`.
- Produces: backup/read-back evidence and a new site health snapshot.

- [ ] **Step 1: Capture pre-repair health**

Call environment health with host scanning enabled and the live ledger/registry paths. Record missing hint counts and finding codes in the ignored ledger as an `observation` event.

- [ ] **Step 2: Execute bounded hot repair**

Call:

```json
{
  "projectRoot": "C:\\Users\\SlaVKs\\Documents\\Github\\project-manager",
  "registryFile": "C:\\Users\\SlaVKs\\Documents\\Github\\project-manager\\docs\\project-manager\\worker-registry.json",
  "ledgerFile": "C:\\Users\\SlaVKs\\Documents\\Github\\project-manager\\docs\\project-manager\\manager-ledger.jsonl",
  "hotRepair": true,
  "hotRepairMaxAttempts": 3
}
```

Expected: no restart, backup and provenance paths reported, and read-back state returned.

- [ ] **Step 3: Run fresh post-repair gates**

Call environment health, model-export health, and stability audit. Acceptance requires:

```text
overallStatus=healthy
coordinationGate=allow
heartbeatReady=true
pluginOwnedStatus=healthy
safeForManagerAutomation=true
failedInvariants=[]
```

The cached browser version marker may remain an advisory until a genuine bootstrap; do not rewrite it manually.

- [ ] **Step 4: Regenerate the site health snapshot**

Run the live health wrapper into the deployment worktree and verify the output contains no forbidden patterns.

### Task 7: Configure and verify the 15-minute heartbeat

**Files:**
- Modify external automation: `project-manager-mcp-health-monitor-2`
- Write ignored runtime ledger event after successful finalize.

**Interfaces:**
- Consumes: `manager_heartbeat_bootstrap`, `manager_heartbeat_automation_plan`, `codex_app__automation_update`, and `manager_heartbeat_automation_finalize`.
- Produces: one active heartbeat targeted to task `019fdc00-0ddc-7472-bdbd-55c6d5daa983` with `FREQ=MINUTELY;INTERVAL=15`.

- [ ] **Step 1: Generate the canonical bootstrap prompt**

Call `manager_heartbeat_bootstrap` with the live source root, current task ID, 15-minute cadence, runtime ledger/registry paths, and automation ID `project-manager-mcp-health-monitor-2`.

- [ ] **Step 2: Extend the prompt with the authorized publish transaction**

Append instructions that explicitly authorize this heartbeat to run the bounded release preparation script, stage only the two generated files, commit only when changed, push the deployment branch to GitHub and Sites with non-persistent credentials, save one version, deploy privately, poll status, and record evidence. Preserve the generated health-first, fail-fast, Objective Runner, registry-maintenance, and notification rules.

- [ ] **Step 3: Prepare the atomic automation update**

Call `manager_heartbeat_automation_plan` with automation ID, current task ID, final prompt, 15-minute interval, and ledger path. Verify it returns exactly one required `automation_update` host action.

- [ ] **Step 4: Execute the host action**

Call `codex_app__automation_update` with the returned arguments. Preserve the existing automation name, set status `ACTIVE`, target this task, use `gpt-5.6-luna` with maximum reasoning, and set notifications to failed runs plus material blockers/completions described in the prompt.

- [ ] **Step 5: Finalize only after host success**

Pass the automation host result to `manager_heartbeat_automation_finalize`. Expected: an `automation_updated` ledger event.

- [ ] **Step 6: Read back the automation**

Call `codex_app__automation_update` in view mode. Verify ID, active status, target task, 15-minute recurrence, and prompt fingerprints.

### Task 8: Run the complete release and deploy privately

**Files:**
- Modify generated: `site/src/data/project-manager.json`
- Modify generated: `site/src/data/project-manager-health.json`
- Modify: `site/src/lib/config.js` if the raw GitHub source branch changes.
- Update plan/spec checkboxes only after evidence is collected.

**Interfaces:**
- Consumes: clean deployment worktree, GitHub `origin`, persisted Sites project ID, Sites source credential, package helper, version/deployment tools.
- Produces: pushed GitHub branch, exact Sites source commit, saved Sites version, private production URL, and deployment read-back.

- [ ] **Step 1: Run full release preparation**

```powershell
pwsh -NoProfile -File .\scripts\Prepare-ProjectManagerRoadmapRelease.ps1 -SourceRoot C:\Users\SlaVKs\Documents\Github\project-manager -DeploymentRoot C:\Users\SlaVKs\Documents\Github\project-manager\.worktrees\project-manager-rock-solid
```

Expected: valid summary JSON, full tests/build pass, and changes limited to generated site data plus any already-reviewed source changes.

- [ ] **Step 2: Run plugin release gates**

Run the Project Manager release checklist commands using the validated bundled Python. At minimum run focused public-health tests, complete site tests/build, model-export health, environment health, stability audit, and the repository's supported plugin test wrapper. Do not weaken or skip failing gates.

- [ ] **Step 3: Inspect and commit the final scoped diff**

```powershell
git diff --check
git status --short
git diff --stat
```

Stage only reviewed Task 2-5 source files and generated snapshots. Commit with:

```powershell
git commit -m "feat: automate private project manager health publishing"
```

- [ ] **Step 4: Push the GitHub deployment branch**

```powershell
git push -u origin codex/project-manager-rock-solid
```

Expected: fast-forward branch push succeeds. Do not force-push.

- [ ] **Step 5: Push the exact commit to Sites source**

Request one short-lived Sites source credential and use it only in a per-command Git authorization header. Push `HEAD` to the credential's branch without modifying Git remotes or configuration.

- [ ] **Step 6: Package the exact build**

Stage the deployment worktree's `site/dist` plus root `.openai/hosting.json` in a temporary directory outside Git. Invoke the bundled `scripts/package-site.sh` helper and verify archive entries include `dist/server/index.js` and `dist/.openai/hosting.json`.

- [ ] **Step 7: Save and privately deploy one version**

Call `sites_save_site_version` with the exact pushed commit and archive, then `sites_deploy_private_site_version`. Poll `sites_get_deployment_status` until `succeeded` or `failed`.

- [ ] **Step 8: Verify production and automation read-back**

On successful deployment:

1. open the exact URL in Codex;
2. verify the production worker has no recent error logs;
3. inspect the health JSON and page status through the authenticated browser when available;
4. view the heartbeat automation and confirm its active 15-minute configuration; and
5. rerun environment health and stability audit.

- [ ] **Step 9: Record final evidence**

Append a `decision` ledger event containing only safe outcome fields: deployment status, public health content digest, test counts, automation ID, cadence, and evidence ceiling. Do not record tokens, URLs classified as private internals, paths outside the project, or raw health payloads.

## Final Verification Checklist

- [ ] Runtime registry exists, reads successfully, and has zero invented active workers.
- [ ] Ledger contains bootstrap, repair observation, automation update, and release outcome events.
- [ ] Hot repair has backup/provenance/read-back evidence and did not restart Codex.
- [ ] Public snapshot privacy tests pass and a forbidden-data scan returns zero matches.
- [ ] Site displays health, coordination, heartbeat, stability, freshness, and evidence boundary.
- [ ] Old snapshots render `STALE`; malformed snapshots render `UNAVAILABLE`.
- [ ] Python tests, Node tests, production build, plugin release gates, model exports, environment health, and stability audit pass at their claimed evidence layer.
- [ ] Deployment worktree contains no unrelated changes.
- [ ] GitHub and Sites source both contain the exact deployed commit.
- [ ] Private Sites deployment succeeds and opens in Codex.
- [ ] Existing paused monitor is updated rather than duplicated.
- [ ] Automation is active, targets the current task, runs every 15 minutes, and is finalized in the ledger.
- [ ] Source checkout's pre-existing unrelated changes remain untouched and unstaged.
