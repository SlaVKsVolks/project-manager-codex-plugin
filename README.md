# Project Manager

`project-manager` is a local Codex plugin for running top-level manager threads across multiple projects. It adds:

- manager-only MCP tools for health, dispatch, recovery, journals, and dashboards
- model-aware worker routing with DeepSeek and GPT policy
- fail-closed host-action transaction planning for `create_thread`, `send_message_to_thread`, `read_thread`, and heartbeat automation
- release and export checks for the local Codex proxy/model stack

## Install

1. Clone this repository into your Codex personal marketplace plugin directory:

```powershell
git clone https://github.com/SlaVKsVolks/project-manager-codex-plugin "$HOME\\.codex\\plugins\\local-marketplaces\\personal\\plugins\\project-manager"
```

2. From the cloned plugin root, sync the current source install into Codex cache:

```powershell
powershell -ExecutionPolicy Bypass -File .\\scripts\\Sync-ProjectManagerPlugin.ps1
```

3. Run the release smoke:

```powershell
powershell -ExecutionPolicy Bypass -File .\\scripts\\Test-ProjectManagerPlugin.ps1
```

4. Restart or reload Codex so the fresh plugin/runtime is rebound.

## Update

```powershell
git pull --ff-only
powershell -ExecutionPolicy Bypass -File .\\scripts\\Sync-ProjectManagerPlugin.ps1
powershell -ExecutionPolicy Bypass -File .\\scripts\\Test-ProjectManagerPlugin.ps1
```

If an already-loaded manager turn still reports missing MCP or `Transport closed`, end that stale turn and let the next fresh turn or heartbeat rebind the plugin.

## Canonical Release Gate

Run these from the plugin root:

```powershell
python -m pytest .\\tests\\test_project_manager_mcp_server.py
powershell -ExecutionPolicy Bypass -File .\\scripts\\Test-ProjectManagerPlugin.ps1
```

`Test-ProjectManagerPlugin.ps1` covers source tests, cached-install tests, export validation, atomic transaction smokes, journal/resume smokes, and the packaged wrapper JSON-RPC smoke.

## Notes

- The plugin root under `~/.codex/plugins/local-marketplaces/personal/plugins/project-manager` is the canonical maintained source on this machine.
- `qwen3.7-plus` remains hard-disabled in policy.
- `deepseek-v4-flash` is the default cheap implementation worker and `deepseek-v4-pro` is escalation-only.
- Public release packaging is intentionally separate from machine-local Codex launcher/watchdog scripts under `~/.codex`.
