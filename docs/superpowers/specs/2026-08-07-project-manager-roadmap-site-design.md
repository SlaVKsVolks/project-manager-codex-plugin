# Project Manager Roadmap Site Design

**Date:** 2026-08-07
**Status:** Design approved; implementation pending specification review
**Target:** ChatGPT Sites with a hybrid local-snapshot/GitHub refresh model

## Objective

Create a trustworthy, visually clear website that explains what the Project Manager plugin does, compares working with and without the plugin in Codex, exposes a live development roadmap, and makes the repository documentation discoverable.

The website must preserve the distinction between repository facts, local development state, remote refresh state, and claims that require runtime or production evidence.

## Primary user and job

- **User:** A developer or operator evaluating Project Manager or tracking its development.
- **Primary job:** Understand the plugin's capabilities, inspect the evidence behind them, and choose the next roadmap or documentation area to explore.
- **Primary action:** `Explore the roadmap`.
- **Heading contract:** One visible H1 with `data-uiux-id="task-heading"`: `See what Project Manager can do`.
- **Success:** The visitor can explain the plugin's main capabilities, see the difference in workflow, identify the current roadmap state, and open the source documentation for a claim.
- **Highest-cost failure:** The site presents generated or stale content as live operational health, or silently omits local documentation from the published snapshot.

## Hybrid synchronization model

ChatGPT Sites cannot directly watch or read the user's Windows filesystem at runtime. The local repository therefore remains the authoritative source for local work, while the hosted site serves a generated snapshot and can optionally refresh from a remote GitHub mirror.

### Local sync flow

1. A repository-owned sync command scans the allowlisted Markdown sources.
2. It extracts document metadata, source paths, headings, dates, categories, and rendered Markdown content.
3. It validates that the expected document set was discovered and that no document has an empty body without an explicit reason.
4. It generates a versioned site data file containing the local snapshot, repository revision, generator timestamp, and provenance.
5. The site build consumes that generated data as its offline-capable baseline.
6. Publication remains a separate, explicitly authorized action; local edits do not silently publish themselves.

The initial allowlist includes:

- `README.md`
- `DEVELOPMENT_IMPROVEMENTS.md`
- `docs/**/*.md`
- `skills/project-manager/SKILL.md`
- selected generated capability/model catalogs when they are safe to expose and have source metadata

The generator must not include secrets, environment values, private URLs, credentials, crash dumps, binary blobs, or arbitrary files outside the allowlist.

### Remote refresh flow

The browser may attempt a best-effort refresh from the configured GitHub raw/API source. A successful refresh replaces the displayed dataset only after schema validation. Network failure, rate limiting, CORS failure, malformed data, or a stale remote revision leaves the bundled local snapshot visible and reports the state clearly.

The UI labels provenance explicitly:

- `LOCAL SNAPSHOT` — bundled from the last local sync.
- `GITHUB LIVE` — successfully refreshed from the configured remote source.
- `FALLBACK` — remote refresh failed and the local snapshot remains active.

The site must never imply that a remote refresh proves current Codex host health, plugin process health, authenticated tool availability, public uptime, or production deployment status.

## Information architecture

### 1. Overview

Hero content introduces the plugin and its operating boundary. It includes the sync-status strip, the `Explore the roadmap` primary action, and a compact capability signal showing the current documentation snapshot.

### 2. Capability map

Capabilities are grouped into inspectable families:

- Health and stability gates
- Dispatch and lane coordination
- Recovery, rebind, and loaded-turn rescue
- Model policy and transport health
- Objective Runner and durable objective state
- Release, export, install, and rollback checks
- Cross-project dashboards and operational audits

Each capability has a short explanation, supporting source documents, and an evidence label such as `repository`, `generated`, `runtime`, or `production`. Unsupported evidence levels are not inferred.

### 3. With Codex vs. without the plugin

The comparison is a visual workflow, not a marketing claim.

**With Project Manager:** health gate → lane packet → model/transport check → prepared action → host execution/readback → ledger or registry finalization.

**Without Project Manager:** manual prompt → ambiguous delivery → no durable lane ownership → repeated or stale retries → unclear final state.

The comparison includes limitations: the plugin cannot resurrect an already-loaded broken MCP binding, and source/package health is not proof of host or production health.

### 4. Live roadmap

Roadmap items are generated from dated decisions, bug records, plans, and specifications. Each item includes:

- phase and date range
- status: `complete`, `in progress`, `next`, or `blocked`
- short outcome
- source-document links
- acceptance criteria
- evidence ceiling

The initial grouping follows the repository history: foundational v0.3.x work; July release and gate hardening; July host recovery and loaded-turn boundaries; August Objective Runner and no-restart repair; August canonical-source and health-classifier corrections; then future live executor, rollout, and hosted operator-surface work.

### 5. Docs Explorer

All synced Markdown documents are searchable and filterable by category, date, status, and evidence level. A selected document opens in a readable detail pane with:

- title and source path
- document type and date
- related roadmap items/capabilities
- rendered Markdown
- provenance and snapshot version

The explorer must retain the selected document and filter state across responsive layout changes.

### 6. Sync Center

The Sync Center shows:

- active dataset provenance
- local snapshot timestamp
- repository revision, when available
- remote refresh timestamp and result
- document count
- fallback/error details
- concise local sync instructions

The control for remote refresh is a semantic button with a visible pending state and an accessible result announcement.

## Visual direction

Use the `command-surface` recipe from UI/UX Engineering, adapted into an editorial operations console:

- dark ink foundation with warm paper/cream content surfaces
- cyan signal accents for active/verified states
- amber accents for warnings and evidence limits
- restrained red only for explicit failures
- strong typographic hierarchy with a readable display face and compact utility labels
- thin roadmap time-axis/grid details rather than a generic SaaS card wall
- compact monospace provenance labels for source and state

The wide layout uses a two-column command surface: the roadmap/capability narrative is primary, while docs and sync context form a supporting inspector. The compact layout stacks the same content in task order and preserves the primary action near the top.

## Data contract

The generator emits a validated JSON dataset, for example:

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-08-07T00:00:00Z",
  "source": {
    "kind": "local",
    "repositoryPath": "project-manager",
    "revision": "..."
  },
  "documents": [],
  "capabilities": [],
  "roadmap": [],
  "comparison": {}
}
```

Document records include stable IDs, title, relative source path, category, date, headings, body, related capability IDs, related roadmap IDs, and evidence tags. Roadmap records include stable IDs, status, phase, dates, outcome, criteria, source IDs, and evidence ceiling.

The browser validates `schemaVersion`, required arrays, stable IDs, and provenance before accepting remote data. Invalid remote data is treated as a refresh failure.

## Critical states

The implementation must design and test these states:

- bundled local snapshot ready
- remote refresh pending
- remote refresh succeeded
- remote refresh unavailable with local fallback
- stale or invalid remote dataset
- empty search result
- selected document loading/failed
- reduced-motion preference
- keyboard focus and visible focus ring
- narrow viewport with the docs inspector stacked below the main task

## Accessibility and interaction requirements

- Exactly one visible H1.
- Semantic navigation, buttons, headings, lists, and time/roadmap structures.
- Keyboard-accessible filters, document selection, refresh, and roadmap navigation.
- Focus must remain visible on the dark and light surfaces.
- Do not use color alone for status; pair color with text/icon/shape.
- Provide live announcements for refresh result and search result count.
- Respect `prefers-reduced-motion` and keep all information available without animation.
- Preserve readable line length, adequate contrast, and touch targets on compact layouts.

## Verification plan

Before claiming the site is ready:

1. Run the local sync generator and verify the expected repository document count and non-empty content.
2. Validate the generated JSON schema and ensure paths resolve only within the allowlist.
3. Run the site build from the site package.
4. Exercise the remote-refresh success and failure paths using a controlled fixture or mockable fetch boundary.
5. Run static accessibility checks for the heading contract, semantics, focus states, and reduced-motion behavior.
6. Inspect the final diff and report source/build/runtime evidence separately.

The site may be published privately to ChatGPT Sites only after the source and build checks pass and the user explicitly authorizes any required commit/push or other externally visible publication step.

## Non-goals

- Silent filesystem watching from the hosted site.
- Treating the hosted page as a live Project Manager health monitor.
- Claiming authenticated Codex, public production, device, or deployment acceptance from repository content alone.
- Automatically committing, pushing, or publishing local changes.
- Exposing arbitrary repository files or secrets.
