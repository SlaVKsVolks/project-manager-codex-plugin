# Project Manager Roadmap Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Build a polished ChatGPT Sites-ready roadmap website that bundles a local repository snapshot, can refresh from GitHub, exposes the plugin capabilities and evidence boundaries, compares Codex workflows, and makes the complete Markdown documentation searchable.

**Architecture:** A small React + Vite site lives under `site/` so the existing Python/PowerShell plugin remains isolated. A repository-owned Python generator scans an explicit Markdown allowlist and merges a curated manifest into a validated JSON dataset under `site/src/data/`; the browser renders that dataset and optionally replaces it after a validated GitHub fetch, falling back to the local snapshot on every remote failure.

**Tech Stack:** React 18, Vite 5, JavaScript ES modules, `marked`, `dompurify`, Node's built-in test runner, Python standard library, PowerShell wrapper.

## Global Constraints

- Preserve existing dirty worktree changes; only add or modify files owned by this site task.
- Do not commit, push, deploy, or publish without explicit authorization for that exact externally visible action.
- Local repository content is authoritative for the bundled snapshot; remote refresh is best-effort and must be labeled.
- Never include secrets, environment values, private URLs, credentials, crash packs, binaries, or arbitrary files outside the allowlist.
- Keep repository facts, generated metadata, runtime observations, and production claims visually and semantically distinct.
- The site must have one visible H1 with `data-uiux-id="task-heading"` and the exact text `See what Project Manager can do`.
- Use semantic controls, keyboard-visible focus, non-color status labels, responsive layouts, and reduced-motion support.
- Run each new behavioral test red before writing the production implementation, then green after the smallest implementation.

---

### Task 1: Establish the data model and failing generator tests

**Files:**
- Create: `site/content/site-manifest.json`
- Create: `tests/test_project_manager_roadmap_site_sync.py`

**Interfaces:**
- The manifest defines `capabilities`, `roadmap`, and `comparison` records.
- The Python implementation in Task 2 must expose `build_site_dataset(repo_root: Path, manifest_path: Path, generated_at: str | None = None) -> dict` and `write_site_dataset(dataset: dict, output_path: Path) -> None`.

- [ ] **Step 1: Write failing Python tests for the dataset contract.**

Add tests that create a temporary repository fixture containing `README.md`, `DEVELOPMENT_IMPROVEMENTS.md`, two Markdown files under `docs/`, one allowed `skills/project-manager/SKILL.md`, and one ignored `.env` file. Assert that `build_site_dataset` returns `schemaVersion == 1`, discovers exactly the four Markdown documents, emits normalized relative paths, includes non-empty bodies, preserves manifest capability/roadmap IDs, and does not include `.env`.

- [ ] **Step 2: Run the focused tests and verify the expected import failure.**

Run:

```powershell
python -m pytest tests/test_project_manager_roadmap_site_sync.py -q
```

Expected: collection fails because `scripts/sync_project_manager_roadmap_site.py` does not exist yet.

- [ ] **Step 3: Add the curated manifest.**

Create seven capability records and six roadmap records with stable IDs, concise outcomes, statuses, evidence ceilings, and source glob patterns. Include the two comparison workflows and the limitation notes from the approved specification. Keep the manifest free of generated document bodies; the generator resolves its source patterns against the repository.

- [ ] **Step 4: Re-run the focused tests and confirm they still fail for the missing generator.**

Run the same pytest command. Expected: the manifest is readable by the test fixture setup, but the import/implementation failure remains.

### Task 2: Implement and verify the local snapshot generator

**Files:**
- Create: `scripts/sync_project_manager_roadmap_site.py`
- Create: `scripts/Sync-ProjectManagerRoadmapSite.ps1`
- Modify: `tests/test_project_manager_roadmap_site_sync.py`

**Interfaces:**
- `build_site_dataset(repo_root, manifest_path, generated_at=None)` returns the JSON-compatible contract from the approved spec.
- `discover_documents(repo_root: Path) -> list[dict]` scans only the allowlisted paths and raises a clear `ValueError` for an empty body.
- `write_site_dataset(dataset, output_path)` creates parent directories and writes UTF-8 JSON with stable indentation.
- CLI arguments are `--repo-root`, `--manifest`, `--output`, and optional `--generated-at`.

- [ ] **Step 1: Add a failing test for deterministic metadata and output writing.**

Assert that a fixed `generated_at` is preserved, `source.kind` is `local`, repository revision is either a 40-character SHA or `unknown`, the document count matches the document list, and `write_site_dataset` emits valid UTF-8 JSON.

- [ ] **Step 2: Run the focused test and verify it fails because the generator functions are absent.**

Run:

```powershell
python -m pytest tests/test_project_manager_roadmap_site_sync.py -q
```

Expected: FAIL with the missing function/module error.

- [ ] **Step 3: Implement the minimal generator.**

Use `pathlib`, `json`, `hashlib`, `re`, and `subprocess` only. Normalize paths with POSIX separators, derive document IDs from a SHA-256 of the relative path, extract the first Markdown heading as the title, classify documents from their directory/date, and attach body/headings. Resolve manifest glob patterns against the repository while rejecting paths outside the repository. Add a `generated` block containing counts and a source digest. Never serialize the absolute repository path.

- [ ] **Step 4: Implement the PowerShell wrapper.**

`Sync-ProjectManagerRoadmapSite.ps1` resolves its own repository root, accepts an optional `-OutputPath`, invokes the Python script with the manifest and output paths, preserves non-zero exit codes, and prints only the output path and count summary.

- [ ] **Step 5: Run the focused tests and verify green.**

Run:

```powershell
python -m pytest tests/test_project_manager_roadmap_site_sync.py -q
```

Expected: all generator tests pass.

- [ ] **Step 6: Generate the repository snapshot.**

Run:

```powershell
pwsh -NoProfile -File .\scripts\Sync-ProjectManagerRoadmapSite.ps1
```

Expected: `site/src/data/project-manager.json` is created with the repository's current allowlisted Markdown files and manifest records.

### Task 3: Establish the React/Vite package and sync-loader tests

**Files:**
- Create: `site/package.json`
- Create: `site/index.html`
- Create: `site/vite.config.js`
- Create: `site/src/lib/sync.test.mjs`
- Create: `site/src/lib/sync.js`

**Interfaces:**
- `validateDataset(dataset) -> dataset` throws an `Error` with a user-safe message for missing schema/version/arrays.
- `refreshDataset({ baseline, remoteUrl, fetchImpl }) -> Promise<{ dataset, status, message, fetchedAt }>` returns `github-live` on a valid HTTP JSON dataset and `fallback` for empty URL, non-OK response, parse failure, or schema failure.
- `site/package.json` scripts are `sync`, `dev`, `build`, `preview`, and `test`.

- [ ] **Step 1: Write failing Node tests for remote success and fallback behavior.**

Use Node's `node:test` and `assert/strict` with a small valid baseline fixture. Test that a successful injected `fetchImpl` returns the remote dataset and `github-live`, while a rejected fetch and malformed dataset return the exact baseline object and `fallback`.

- [ ] **Step 2: Run the tests and verify they fail because `sync.js` is absent.**

Run from `site/`:

```powershell
npm test -- --test-name-pattern="remote|fallback"
```

Expected: FAIL with module-not-found.

- [ ] **Step 3: Create the package and Vite entry files.**

Use React 18, Vite 5, `@vitejs/plugin-react`, `marked`, and `dompurify`. Keep the package under `site/` and do not alter the plugin's root tooling.

- [ ] **Step 4: Implement the validated sync loader.**

Keep the fetch boundary dependency-injected for tests, use a ten-second `AbortController` timeout in the browser path, and retain the baseline on every failure. Include a safe default raw GitHub URL for this repository plus `VITE_PROJECT_MANAGER_REMOTE_DATA_URL` override support in `site/src/lib/config.js`.

- [ ] **Step 5: Run the Node tests and verify green.**

Run:

```powershell
npm test
```

Expected: all sync-loader tests pass with no unhandled warnings.

### Task 4: Build the site shell and documentation renderer

**Files:**
- Create: `site/src/main.jsx`
- Create: `site/src/App.jsx`
- Create: `site/src/lib/markdown.js`
- Create: `site/src/styles.css`
- Create: `site/src/lib/config.js`

**Interfaces:**
- `renderMarkdown(markdown) -> string` returns sanitized HTML for a document detail view.
- `App` owns `dataset`, `syncState`, `query`, `categoryFilter`, `evidenceFilter`, and `selectedDocumentId` state.
- All external document links use relative repository paths or the configured remote source; no absolute local filesystem path is rendered into the site.

- [ ] **Step 1: Add a failing static UI contract test.**

Create a Node test that reads `site/src/App.jsx` and asserts the exact H1 contract, the `Explore the roadmap` primary action, the `Refresh from GitHub` button label, and the navigation labels `Capabilities`, `With / without`, `Roadmap`, and `Docs` are present.

- [ ] **Step 2: Run the contract test and verify it fails because `App.jsx` is absent.**

Run:

```powershell
npm test -- --test-name-pattern="UI contract"
```

Expected: FAIL with file-not-found.

- [ ] **Step 3: Implement the semantic page shell.**

Add the top navigation, sync strip, overview hero, capability map, workflow comparison, roadmap timeline, docs explorer, and sync center. Use real dataset values; no fake metrics. Wire capability/roadmap source links to the document explorer selection.

- [ ] **Step 4: Implement document rendering and selection.**

Use `marked` configured for headings, links, code, lists, and tables, then sanitize with DOMPurify. Provide a readable empty-search state and preserve the selected document through filter changes when still available.

- [ ] **Step 5: Add the visual system and responsive layout.**

Implement the approved command-surface recipe: ink background, paper surfaces, cyan signal, amber evidence warnings, open timeline/list structures, serif display headings, monospace provenance labels, no generic card wall. Add compact layout stacking, focus rings, status labels, and reduced-motion media rules.

- [ ] **Step 6: Run the UI contract and Node tests.**

Run:

```powershell
npm test
```

Expected: all loader and UI contract tests pass.

### Task 5: Build and local integration verification

**Files:**
- Modify: `site/package.json` only if script corrections are required by verification.
- Modify: `site/src/*` only for failures found by the focused build or browser smoke test.

**Interfaces:**
- `npm run sync` regenerates the checked-in local data file.
- `npm run build` creates a production Vite build under `site/dist/`.

- [ ] **Step 1: Run the complete data and site test cycle.**

Run from the repository root and site directory:

```powershell
python -m pytest tests/test_project_manager_roadmap_site_sync.py -q
pwsh -NoProfile -File .\scripts\Sync-ProjectManagerRoadmapSite.ps1
Set-Location .\site
npm test
npm run build
```

Expected: Python tests, Node tests, and Vite build all pass.

- [ ] **Step 2: Start a local preview without opening a visible terminal.**

Use a hidden non-interactive process with redirected output, then validate `http://127.0.0.1:<port>/` through the in-app Browser if available. The flow under test is: app loads → first meaningful screen renders → `Refresh from GitHub` changes the sync status → a capability source opens the Docs Explorer → a search filter updates the result count.

- [ ] **Step 3: Capture required responsive evidence.**

Check the first viewport at `1440x1024` and `390x844`, plus light/dark preference if supported by the browser. Record console errors, blank-page/framework-overlay status, and interaction results. If the in-app Browser is unavailable, use Playwright and record the exact fallback reason.

- [ ] **Step 4: Inspect the generated dataset and production build.**

Verify the generated document count, source digest, no absolute local path leakage, presence of capability/roadmap IDs, and `site/dist/index.html` plus asset files. Do not include screenshots or traces in the repository.

### Task 6: ChatGPT Sites preparation and handoff

**Files:**
- Create or modify only Sites metadata files requested by the Sites tool, such as `.openai/hosting.json`, after tool inspection.

- [ ] **Step 1: Inspect the Sites account and existing site list.**

Use the Sites connector read-only actions first. Do not create or deploy a site until the local build is verified.

- [ ] **Step 2: Create or select a private site target.**

Prefer private access. Persist the site identifier only through the Sites tool's supported metadata flow. Do not expose secrets or environment values.

- [ ] **Step 3: Stop before commit/push if publication requires them.**

Report the validated local build and the exact commit/push/publication action needed. Ask for explicit authorization before any commit, push, or externally visible deployment.

- [ ] **Step 4: After authorization, publish and poll deployment status.**

Use the Sites hosting workflow, open the deployed site in Codex, and report the public/private URL and deployment status separately from local source/build/runtime evidence.

## Review checkpoints

- After Task 2: review the generated JSON and document count before adding the frontend.
- After Task 4: review the first rendered screen and core interactions before Sites preparation.
- After Task 5: review test/build/browser evidence and remaining limitations before any external publication.
