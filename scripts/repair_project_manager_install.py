#!/usr/bin/env python3
"""Repair and resync the local project-manager plugin install without restarting Codex."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


WRAPPER_COMMAND = "./scripts/project-manager-mcp.exe"


def _home() -> Path:
    return Path.home()


def _source_root() -> Path:
    return Path(
        os.environ.get(
            "PROJECT_MANAGER_SOURCE_ROOT",
            _home() / ".codex" / "plugins" / "local-marketplaces" / "personal" / "plugins" / "project-manager",
        )
    )


def _mirror_root() -> Path:
    return Path(
        os.environ.get(
            "PROJECT_MANAGER_MIRROR_ROOT",
            _home() / ".agents" / "plugins" / "plugins" / "project-manager",
        )
    )


def _marketplace_root() -> Path:
    return Path(os.environ.get("PROJECT_MANAGER_MARKETPLACE_ROOT", _home() / ".agents" / "plugins"))


def _cache_base() -> Path:
    return Path(os.environ.get("PROJECT_MANAGER_CACHE_BASE", _home() / ".codex" / "plugins" / "cache" / "personal" / "project-manager"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _ensure_mcp_config(plugin_root: Path, command: str = WRAPPER_COMMAND) -> dict[str, Any]:
    payload = {
        "mcpServers": {
            "project-manager": {
                "type": "stdio",
                "command": command,
                "args": [],
                "cwd": ".",
            }
        }
    }
    path = plugin_root / ".mcp.json"
    changed = True
    if path.exists():
        try:
            changed = json.loads(path.read_text(encoding="utf-8")) != payload
        except json.JSONDecodeError:
            changed = True
    if changed:
        _write_json(path, payload)
    return {"path": str(path), "changed": changed}


def _ensure_marketplace(marketplace_root: Path) -> dict[str, Any]:
    path = marketplace_root / "marketplace.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {"name": "personal", "interface": {"displayName": "Personal"}, "plugins": []}
    plugins = payload.setdefault("plugins", [])
    entry = {
        "name": "project-manager",
        "source": {"source": "local", "path": "./plugins/project-manager"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity",
    }
    changed = False
    for index, plugin in enumerate(plugins):
        if isinstance(plugin, dict) and plugin.get("name") == "project-manager":
            if plugin != entry:
                plugins[index] = entry
                changed = True
            break
    else:
        plugins.append(entry)
        changed = True
    if changed or not path.exists():
        _write_json(path, payload)
    return {"path": str(path), "changed": changed}


def _latest_cache_root(cache_base: Path) -> Path | None:
    if not cache_base.exists():
        return None
    candidates = [path for path in cache_base.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _invoke_sync_script(source_root: Path, cache_root: Path | None, mirror_root: Path) -> dict[str, Any]:
    script_path = source_root / "scripts" / "Sync-ProjectManagerPlugin.ps1"
    if not script_path.exists():
        return {"status": "failed", "error": f"missing sync script: {script_path}"}
    args = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-SourceRoot",
        str(source_root),
        "-MirrorRoot",
        str(mirror_root),
    ]
    if cache_root is not None:
        args.extend(["-CacheRoot", str(cache_root)])
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        cwd=source_root,
        timeout=120,
    )
    if proc.returncode != 0:
        return {
            "status": "failed",
            "error": proc.stderr.strip() or proc.stdout.strip() or f"sync script exited {proc.returncode}",
            "returncode": proc.returncode,
        }
    text = proc.stdout.strip()
    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError as exc:
        return {"status": "failed", "error": f"sync script returned invalid JSON: {exc}", "stdout": text}
    return {"status": "ok", **(payload if isinstance(payload, dict) else {"payload": payload})}


def repair() -> dict[str, Any]:
    source_root = _source_root()
    mirror_root = _mirror_root()
    marketplace_root = _marketplace_root()
    cache_root = _latest_cache_root(_cache_base())
    result = {
        "sourceRoot": str(source_root),
        "mirrorRoot": str(mirror_root),
        "marketplaceRoot": str(marketplace_root),
        "sourceMcp": _ensure_mcp_config(source_root),
        "mirrorMcp": _ensure_mcp_config(mirror_root),
        "marketplace": _ensure_marketplace(marketplace_root),
        "sync": _invoke_sync_script(source_root, cache_root, mirror_root),
    }
    if cache_root is not None:
        result["cacheRoot"] = str(cache_root)
        result["cacheMcp"] = _ensure_mcp_config(cache_root)
    sync_status = str((result.get("sync") or {}).get("status") or "failed")
    result["sourceAlignmentStatus"] = "aligned" if sync_status == "ok" else "repair_failed"
    return result


def main() -> int:
    print(json.dumps(repair(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
