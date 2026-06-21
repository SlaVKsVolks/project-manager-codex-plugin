import json
import os
import subprocess
import sys
import time
import importlib.util
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = PLUGIN_ROOT / "scripts" / "project_manager_mcp_server.py"
SPEC = importlib.util.spec_from_file_location("project_manager_mcp_server", SERVER_PATH)
SERVER_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SERVER_MODULE)
EXPECTED_TOOL_NAMES = list(SERVER_MODULE.TOOLS.keys())


def _resolve_manifest_command(command: str) -> str:
    candidate = Path(command)
    if candidate.is_absolute():
        return str(candidate)
    return str((PLUGIN_ROOT / candidate).resolve())


def _run_server(*messages: object, env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    assert SERVER_PATH.exists(), f"Missing server file: {SERVER_PATH}"
    payload = "\n".join(json.dumps(message) for message in messages) + "\n"
    proc = subprocess.run(
        [sys.executable, str(SERVER_PATH)],
        input=payload,
        text=True,
        capture_output=True,
        cwd=PLUGIN_ROOT,
        env=env,
        check=False,
    )
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    return proc, responses


def _tool_call(name: str, arguments: dict, env: dict[str, str] | None = None) -> dict:
    proc, responses = _run_server(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    result = responses[-1]["result"]
    assert len(result["content"]) == 1
    return json.loads(result["content"][0]["text"])


def test_tools_list_exposes_only_manager_tools() -> None:
    proc, responses = _run_server(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )

    assert proc.returncode == 0, proc.stderr
    tool_names = [tool["name"] for tool in responses[-1]["result"]["tools"]]
    assert tool_names == EXPECTED_TOOL_NAMES
    assert all(not name.startswith("voxy_") for name in tool_names)


def test_packaged_mcp_config_launches_with_wrapper_and_logs_startup(tmp_path: Path) -> None:
    mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = mcp_config["mcpServers"]["project-manager"]
    log_file = tmp_path / "project-manager-mcp.log"
    wrapper_log_file = tmp_path / "project-manager-mcp-wrapper.log"
    env = {
        **os.environ,
        "PROJECT_MANAGER_MCP_LOG": str(log_file),
        "PROJECT_MANAGER_WRAPPER_LOG": str(wrapper_log_file),
    }
    payload = "\n".join(
        json.dumps(message)
        for message in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
    ) + "\n"
    proc = subprocess.run(
        [_resolve_manifest_command(server["command"]), *server["args"]],
        input=payload,
        text=True,
        capture_output=True,
        cwd=PLUGIN_ROOT,
        env=env,
        check=False,
        timeout=20,
    )

    assert proc.returncode == 0, proc.stderr
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert responses[0]["result"]["serverInfo"]["name"] == "project-manager"
    assert len(responses[1]["result"]["tools"]) == len(EXPECTED_TOOL_NAMES)
    log_events = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    server_start = next(event for event in log_events if event["event"] == "server_start")
    assert server_start["resolvedPluginRoot"] == str(PLUGIN_ROOT)
    assert server_start["sourceAlignmentStatus"] in {"aligned", "aligned_via_cache"}
    wrapper_text = wrapper_log_file.read_text(encoding="utf-8")
    assert "server_start" in wrapper_text
    assert "duplicateMonitorEnabled=True" in wrapper_text
    assert "wrapperHash=" in wrapper_text
    assert "stdin bridge stopped" not in wrapper_text


def test_packaged_wrapper_survives_exclusive_wrapper_log_lock(tmp_path: Path) -> None:
    mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = mcp_config["mcpServers"]["project-manager"]
    log_file = tmp_path / "project-manager-mcp.log"
    wrapper_log_file = tmp_path / "project-manager-mcp-wrapper.log"
    env = {
        **os.environ,
        "PROJECT_MANAGER_MCP_LOG": str(log_file),
        "PROJECT_MANAGER_WRAPPER_LOG": str(wrapper_log_file),
    }
    payload = "\n".join(
        json.dumps(message)
        for message in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
    ) + "\n"
    lock_script = """
import ctypes
import os
import time

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_ALWAYS = 4
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

path = os.environ["LOCK_PATH"]
create_file = ctypes.windll.kernel32.CreateFileW
create_file.restype = ctypes.c_void_p
handle = create_file(path, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, None)
if handle == INVALID_HANDLE_VALUE:
    raise OSError("CreateFileW failed for exclusive lock")
try:
    time.sleep(15)
finally:
    ctypes.windll.kernel32.CloseHandle(handle)
"""
    lock_proc = subprocess.Popen(
        [sys.executable, "-c", lock_script],
        env={**os.environ, "LOCK_PATH": str(wrapper_log_file)},
        cwd=PLUGIN_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1)
        proc = subprocess.run(
            [_resolve_manifest_command(server["command"]), *server["args"]],
            input=payload,
            text=True,
            capture_output=True,
            cwd=PLUGIN_ROOT,
            env=env,
            check=False,
            timeout=20,
        )
    finally:
        lock_proc.terminate()
        try:
            lock_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            lock_proc.kill()
            lock_proc.wait(timeout=5)

    assert proc.returncode == 0, proc.stderr
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert responses[0]["result"]["serverInfo"]["name"] == "project-manager"
    assert len(responses[1]["result"]["tools"]) == len(EXPECTED_TOOL_NAMES)
    log_events = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert any(event["event"] == "server_start" for event in log_events)


def test_register_dispatch_after_send_rejects_unsent_dispatch() -> None:
    result = _tool_call(
        "manager_register_dispatch_after_send",
        {
            "sendSucceeded": False,
            "assignmentId": "assign-123",
            "targetThreadId": "thread-123",
            "assignmentPath": "C:/tmp/assignment.md",
        },
    )

    assert result["status"] == "failed"
    assert "sendSucceeded=true" in result["error"]


def test_manager_tick_normalizes_state_file_and_recommends_recovery(tmp_path: Path) -> None:
    state_file = tmp_path / "manager-state.json"
    state_file.write_text(
        json.dumps(
            {
                "project_root": "C:/work/example",
                "manager_thread_id": "manager-1",
                "mode": "active",
                "workers": {
                    "worker-a": {
                        "threadId": "thread-a",
                        "assignment_id": "A1",
                        "status": "active",
                        "last_progress_at": "2026-06-19T15:30:00Z",
                    },
                    "worker-b": {
                        "thread_id": "thread-b",
                        "assignment_id": "B1",
                        "status": "blocked",
                        "blockers": ["missing fixture"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call(
        "manager_tick",
        {
            "stateFile": str(state_file),
            "now": "2026-06-19T16:19:00Z",
            "staleAfterMinutes": 60,
        },
    )

    assert result["status"] == "ok"
    assert result["projectRoot"] == "C:/work/example"
    assert result["managerThreadId"] == "manager-1"
    assert result["attentionRequired"] is True
    assert result["quietHeartbeatAllowed"] is False
    assert result["heartbeatDecisionHint"] == "NOTIFY"
    assert result["nextRecommendedAction"] == "read_or_recover_blocked_worker:worker-b"
    assert [worker["worker"] for worker in result["workers"]] == ["worker-a", "worker-b"]
    assert result["workers"][0]["attention"] == "healthy"
    assert result["workers"][0]["minutesSinceProgress"] == 49
    assert result["workers"][0]["deliveryVerified"] is False
    assert result["workers"][0]["workerAcknowledged"] is False
    assert result["workers"][1]["attention"] == "blocked"
    assert result["workers"][1]["blockers"] == ["missing fixture"]


def test_manager_tick_marks_stale_worker_from_state_json() -> None:
    result = _tool_call(
        "manager_tick",
        {
            "stateJson": json.dumps(
                {
                    "workers": [
                        {
                            "label": "worker-c",
                            "status": "active",
                            "last_progress_at": "2026-06-19T14:00:00Z",
                        }
                    ]
                }
            ),
            "now": "2026-06-19T16:19:00Z",
            "staleAfterMinutes": 60,
        },
    )

    assert result["status"] == "ok"
    assert result["attentionRequired"] is True
    assert result["quietHeartbeatAllowed"] is False
    assert result["heartbeatDecisionHint"] == "NOTIFY"
    assert result["nextRecommendedAction"] == "read_or_reassign_stale_worker:worker-c"
    assert result["workers"][0]["attention"] == "stale"
    assert result["workers"][0]["minutesSinceProgress"] == 139


def test_manager_tick_marks_unknown_worker_as_notify_only() -> None:
    result = _tool_call(
        "manager_tick",
        {
            "stateJson": json.dumps(
                {
                    "workers": [
                        {
                            "label": "worker-d",
                            "status": "conceptually_alive_unknown_freshness",
                        }
                    ]
                }
            ),
            "now": "2026-06-19T16:19:00Z",
            "staleAfterMinutes": 60,
        },
    )

    assert result["status"] == "ok"
    assert result["attentionRequired"] is True
    assert result["quietHeartbeatAllowed"] is False
    assert result["heartbeatDecisionHint"] == "NOTIFY"
    assert result["nextRecommendedAction"] == "inspect_unknown_worker:worker-d"
    assert result["workers"][0]["attention"] == "unknown"


def test_model_roster_exposes_deepseek_worker_models() -> None:
    result = _tool_call("manager_model_roster", {"managerModel": "gpt-5.5"})

    assert result["status"] == "ok"
    assert result["managerModel"] == "gpt-5.5"
    assert [model["model"] for model in result["workerModels"]] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "glm-5.2",
        "kimi-k2.7-code",
        "mimo-v2.5",
    ]
    assert "GPT manager threads" in result["policy"]


def test_model_catalog_exposes_enabled_and_disabled_entries(monkeypatch, tmp_path: Path) -> None:
    live_models = tmp_path / "models.json"
    live_models.write_text(
        json.dumps(
            {
                "models": [
                    {"slug": "gpt-5.5", "display_name": "GPT-5.5"},
                    {"slug": "deepseek-v4-flash", "display_name": "DeepSeek V4 Flash"},
                    {"slug": "deepseek-v4-pro", "display_name": "DeepSeek V4 Pro"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(SERVER_MODULE, "LIVE_MODELS_PATH", live_models)

    result = _tool_call("manager_model_catalog", {"includeDisabled": True})
    flash = next(model for model in result["models"] if model["slug"] == "deepseek-v4-flash")
    qwen = next(model for model in result["models"] if model["slug"] == "qwen3.7-plus")

    assert result["status"] == "ok"
    assert result["modelCount"] >= 11
    assert flash["enabled"] is True
    assert flash["providerLabel"] == "OpenCode Go"
    assert flash["transportRoute"] == "chat"
    assert flash["localAvailability"]["presentInLiveCatalog"] is True
    assert qwen["enabled"] is False
    assert "disabled" in qwen["disabledReason"].lower()
    assert qwen["transportRoute"] == "messages"


def test_model_catalog_can_write_proxy_exports(monkeypatch, tmp_path: Path) -> None:
    export_dir = tmp_path / "exports"
    live_models = tmp_path / "models.json"
    live_models.write_text(json.dumps({"models": [{"slug": "deepseek-v4-flash"}]}), encoding="utf-8")
    monkeypatch.setattr(SERVER_MODULE, "LIVE_MODELS_PATH", live_models)
    monkeypatch.setattr(SERVER_MODULE, "MODEL_EXPORT_DIR", export_dir)
    monkeypatch.setattr(SERVER_MODULE, "MODEL_CATALOG_EXPORT_PATH", export_dir / "canonical-model-catalog.json")
    monkeypatch.setattr(SERVER_MODULE, "PROXY_MODEL_LIST_EXPORT_PATH", export_dir / "proxy-model-list.json")
    monkeypatch.setattr(SERVER_MODULE, "PROXY_RUNTIME_EXPORT_PATH", export_dir / "proxy-runtime-instructions.json")

    result = SERVER_MODULE.tool_manager_model_catalog({"writeExports": True})

    assert result["status"] == "ok"
    assert result["exports"]["proxyModelList"]["exists"] is True
    assert result["exports"]["proxyRuntimeInstructions"]["exists"] is True
    model_list = json.loads((export_dir / "proxy-model-list.json").read_text(encoding="utf-8"))
    runtime = json.loads((export_dir / "proxy-runtime-instructions.json").read_text(encoding="utf-8"))
    flash_runtime = runtime["models"]["deepseek-v4-flash"]
    assert any(model["slug"] == "deepseek-v4-flash" for model in model_list["models"])
    assert flash_runtime["transportRoute"] == "chat"
    assert "immediate-tool-use" in flash_runtime["runtimeRules"][0]
    assert model_list["metadata"]["generatedFromRoot"] == str(PLUGIN_ROOT)
    assert model_list["metadata"]["exportMode"] == "active_root"
    assert model_list["metadata"]["liveModelsPath"] == str(live_models)


def test_model_catalog_does_not_mirror_test_exports_to_source_by_default(monkeypatch, tmp_path: Path) -> None:
    source_export_dir = tmp_path / "source-generated"
    export_dir = tmp_path / "active-generated"
    live_models = tmp_path / "models.json"
    live_models.write_text(json.dumps({"models": [{"slug": "deepseek-v4-flash"}]}), encoding="utf-8")
    monkeypatch.setattr(SERVER_MODULE, "LIVE_MODELS_PATH", live_models)
    monkeypatch.setattr(SERVER_MODULE, "SOURCE_PLUGIN_ROOT", tmp_path / "source-plugin")
    monkeypatch.setattr(SERVER_MODULE, "MODEL_EXPORT_DIR", export_dir)
    monkeypatch.setattr(SERVER_MODULE, "MODEL_CATALOG_EXPORT_PATH", export_dir / "canonical-model-catalog.json")
    monkeypatch.setattr(SERVER_MODULE, "PROXY_MODEL_LIST_EXPORT_PATH", export_dir / "proxy-model-list.json")
    monkeypatch.setattr(SERVER_MODULE, "PROXY_RUNTIME_EXPORT_PATH", export_dir / "proxy-runtime-instructions.json")

    result = SERVER_MODULE.tool_manager_model_catalog({"writeExports": True})

    assert result["status"] == "ok"
    assert (export_dir / "proxy-model-list.json").exists()
    assert not (source_export_dir / "proxy-model-list.json").exists()
    assert result["exports"]["metadata"]["exportMode"] == "active_root"


def test_model_export_health_flags_poisoned_test_live_models(monkeypatch, tmp_path: Path) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    temp_live_models = tmp_path / "pytest-123" / "models.json"
    temp_live_models.parent.mkdir()
    payload = {
        "metadata": {
            "generatedFromRoot": str(PLUGIN_ROOT),
            "liveModelsPath": str(temp_live_models),
            "exportMode": "active_root",
            "sha256": "bad",
        },
        "models": [{"slug": "deepseek-v4-flash", "transport_route": "chat"}],
    }
    runtime = {
        "metadata": payload["metadata"],
        "models": {"qwen3.7-plus": {"enabled": False, "transportRoute": "messages"}},
    }
    (export_dir / "proxy-model-list.json").write_text(json.dumps(payload), encoding="utf-8")
    (export_dir / "proxy-runtime-instructions.json").write_text(json.dumps(runtime), encoding="utf-8")
    monkeypatch.setattr(SERVER_MODULE, "PROXY_MODEL_LIST_EXPORT_PATH", export_dir / "proxy-model-list.json")
    monkeypatch.setattr(SERVER_MODULE, "PROXY_RUNTIME_EXPORT_PATH", export_dir / "proxy-runtime-instructions.json")

    result = SERVER_MODULE.tool_manager_model_export_health({})

    assert result["status"] == "ok"
    assert result["overallStatus"] == "degraded"
    assert any(finding["code"] == "poisoned_live_models_path" for finding in result["findings"])
    assert result["disabledModelRouteLeak"] is False


def test_model_roster_rejects_hard_disabled_qwen_when_profile_requests_it(tmp_path: Path) -> None:
    profile_file = tmp_path / ".project-manager.json"
    profile_file.write_text(
        json.dumps(
            {
                "settings": {
                    "workerModels": ["qwen3.7-plus"],
                    "defaultWorkerModel": "qwen3.7-plus",
                }
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call("manager_model_roster", {"profileFile": str(profile_file)})

    assert result["status"] == "failed"
    assert result["error"] == "disabled worker model requested"
    assert result["workerModel"] == "qwen3.7-plus"


def test_model_roster_can_be_profile_driven(tmp_path: Path) -> None:
    profile_file = tmp_path / ".project-manager.json"
    profile_file.write_text(
        json.dumps(
            {
                "profile": "generic",
                "settings": {
                    "defaultManagerModel": "gpt-5.5",
                    "managerModels": ["gpt-5.5"],
                    "workerModels": ["deepseek-v4-pro", "custom-worker-model"],
                    "defaultWorkerModel": "custom-worker-model",
                },
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call("manager_model_roster", {"profileFile": str(profile_file)})

    assert result["status"] == "ok"
    assert result["managerModel"] == "gpt-5.5"
    assert [model["model"] for model in result["managerModels"]] == ["gpt-5.5"]
    assert [model["model"] for model in result["workerModels"]] == ["deepseek-v4-pro", "custom-worker-model"]
    assert result["defaultWorkerModel"] == "custom-worker-model"


def test_prepare_worker_thread_builds_deepseek_create_thread_request() -> None:
    result = _tool_call(
        "manager_prepare_worker_thread",
        {
            "assignmentId": "A1",
            "assignmentPath": "docs/assignments/a1.md",
            "goal": "Implement the parser",
            "constraints": "Stay in repo scope",
            "definitionOfDone": "Tests pass and report blockers",
            "workerModel": "pro",
            "managerModel": "gpt-5.5",
            "targetType": "projectless",
            "directoryName": "deepseek-worker-a1",
        },
    )

    assert result["status"] == "ok"
    assert result["workerModel"] == "deepseek-v4-pro"
    assert result["managerModel"] == "gpt-5.5"
    request = result["createThreadRequest"]
    assert request["model"] == "deepseek-v4-pro"
    assert request["thinking"] == "high"
    assert request["target"] == {"type": "projectless", "directoryName": "deepseek-worker-a1"}
    assert "managed by a GPT project-manager thread" in request["prompt"]
    assert "assignment_id: A1" in request["prompt"]
    assert result["promptSafety"]["promptChars"] <= SERVER_MODULE.MAX_INLINE_PROMPT_CHARS
    assert result["threadCreationSurface"] == {
        "surface": "create_thread.model",
        "modelAware": True,
        "consistency": "native",
        "requestedModel": "deepseek-v4-pro",
    }


def test_prepare_worker_thread_compacts_nested_delegation_fields() -> None:
    result = SERVER_MODULE.tool_manager_prepare_worker_thread(
        {
            "assignmentId": "A3",
            "assignmentPath": "docs/assignments/a3.md",
            "goal": "<codex_delegation><input>Actual inner assignment text that should survive compaction.</input></codex_delegation>",
            "constraints": "<codex_delegation><input>" + ("Keep scope narrow. " * 300) + "</input></codex_delegation>",
            "definitionOfDone": "Return a strict worker final.",
        }
    )

    assert result["status"] == "ok"
    prompt = result["createThreadRequest"]["prompt"]
    assert "<codex_delegation>" not in prompt
    assert "Actual inner assignment text that should survive compaction." in prompt
    assert result["promptSafety"]["compacted"] is True
    assert any("nested_codex_delegation_compacted" in warning for warning in result["promptSafety"]["warnings"])
    assert result["promptSafety"]["promptChars"] <= SERVER_MODULE.MAX_INLINE_PROMPT_CHARS


def test_prepare_worker_thread_uses_profile_default_worker_model(tmp_path: Path) -> None:
    profile_file = tmp_path / ".project-manager.json"
    profile_file.write_text(
        json.dumps(
            {
                "settings": {
                    "workerModels": ["custom-worker-model"],
                    "defaultWorkerModel": "custom-worker-model",
                    "defaultManagerModel": "gpt-5.5",
                }
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call(
        "manager_prepare_worker_thread",
        {
            "profileFile": str(profile_file),
            "assignmentId": "A2",
            "assignmentPath": "docs/assignments/a2.md",
            "goal": "Implement the profile-routed worker",
            "constraints": "Stay in repo scope",
            "definitionOfDone": "Tests pass",
        },
    )

    assert result["status"] == "ok"
    assert result["workerModel"] == "custom-worker-model"
    assert result["managerModel"] == "gpt-5.5"
    assert result["createThreadRequest"]["model"] == "custom-worker-model"


def test_prepare_worker_thread_requires_project_id_for_project_target() -> None:
    result = _tool_call(
        "manager_prepare_worker_thread",
        {
            "assignmentId": "A1",
            "assignmentPath": "docs/assignments/a1.md",
            "goal": "Implement the parser",
            "constraints": "Stay in repo scope",
            "definitionOfDone": "Tests pass and report blockers",
            "workerModel": "deepseek-v4-flash",
            "targetType": "project",
        },
    )

    assert result["status"] == "failed"
    assert result["error"] == "projectId is required when targetType=project"


def test_project_profile_returns_optional_defaults() -> None:
    result = _tool_call("manager_project_profile", {"profile": "minecraft"})

    assert result["status"] == "ok"
    assert result["profile"] == "minecraft"
    assert result["settings"]["defaultWorkerModel"] == "deepseek-v4-flash"
    assert "generic" in result["knownProfiles"]


def test_load_project_profile_merges_file_defaults(tmp_path: Path) -> None:
    profile_file = tmp_path / ".project-manager.json"
    profile_file.write_text(
        json.dumps(
            {
                "profile": "generic",
                "settings": {
                    "staleAfterMinutes": 12,
                    "ledgerPathHint": "work/custom-ledger.jsonl",
                    "defaultWorkerModel": "deepseek-v4-pro",
                },
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call("manager_load_project_profile", {"profileFile": str(profile_file)})

    assert result["status"] == "ok"
    assert result["settings"]["staleAfterMinutes"] == 12
    assert result["settings"]["ledgerPathHint"] == "work/custom-ledger.jsonl"
    assert result["settings"]["seniorWorkerModel"] == "deepseek-v4-pro"


def test_load_project_profile_rejects_hard_disabled_qwen(tmp_path: Path) -> None:
    profile_file = tmp_path / ".project-manager.json"
    profile_file.write_text(
        json.dumps(
            {
                "settings": {
                    "workerModels": ["deepseek-v4-flash", "qwen3.7-plus"],
                    "defaultWorkerModel": "qwen3.7-plus",
                }
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call("manager_load_project_profile", {"profileFile": str(profile_file)})

    assert result["status"] == "failed"
    assert result["error"] == "disabled worker model requested"
    assert result["workerModel"] == "qwen3.7-plus"


def test_prepare_worker_thread_uses_flash_default_for_conan_profile() -> None:
    result = _tool_call(
        "manager_prepare_worker_thread",
        {
            "profile": "conan",
            "assignmentId": "A3",
            "assignmentPath": "docs/assignments/a3.md",
            "goal": "Implement the conan worker task",
            "constraints": "Stay in repo scope",
            "definitionOfDone": "Tests pass",
        },
    )

    assert result["status"] == "ok"
    assert result["workerModel"] == "deepseek-v4-flash"
    assert result["createThreadRequest"]["model"] == "deepseek-v4-flash"


def test_prepare_worker_thread_rejects_hard_disabled_qwen(tmp_path: Path) -> None:
    profile_file = tmp_path / ".project-manager.json"
    profile_file.write_text(
        json.dumps(
            {
                "settings": {
                    "workerModels": ["qwen3.7-plus"],
                    "defaultWorkerModel": "qwen3.7-plus",
                }
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call(
        "manager_prepare_worker_thread",
        {
            "profileFile": str(profile_file),
            "assignmentId": "A4",
            "assignmentPath": "docs/assignments/a4.md",
            "goal": "Implement the profile-routed worker",
            "constraints": "Stay in repo scope",
            "definitionOfDone": "Tests pass",
        },
    )

    assert result["status"] == "failed"
    assert result["error"] == "disabled worker model requested"
    assert result["workerModel"] == "qwen3.7-plus"


def test_select_worker_model_prefers_flash_for_routine_slice() -> None:
    result = _tool_call(
        "manager_select_worker_model",
        {
            "profile": "conan",
            "assignmentRisk": "routine",
            "packetShape": "narrow",
        },
    )

    assert result["status"] == "ok"
    assert result["workerModel"] == "deepseek-v4-flash"
    assert result["escalated"] is False


def test_select_worker_model_escalates_to_pro_for_high_risk_slice() -> None:
    result = _tool_call(
        "manager_select_worker_model",
        {
            "profile": "minecraft",
            "assignmentRisk": "high",
            "packetShape": "large",
            "architectureSensitive": True,
        },
    )

    assert result["status"] == "ok"
    assert result["workerModel"] == "deepseek-v4-pro"
    assert result["escalated"] is True


def test_model_advisory_recommends_glm_for_long_context_and_avoids_disabled_qwen() -> None:
    result = _tool_call(
        "manager_model_advisory",
        {
            "goal": "Read a large repo and synthesize architecture constraints before code changes.",
            "packetRole": "repo_explorer",
            "needLongContext": True,
            "assignmentRisk": "routine",
        },
    )

    assert result["status"] == "ok"
    assert result["recommendedModel"] == "glm-5.2"
    assert result["fallbackModel"] == "deepseek-v4-flash"
    assert "qwen3.7-plus" in result["avoidedModels"]


def test_model_policy_validate_diff_and_cost_policy(tmp_path: Path) -> None:
    profile_file = tmp_path / ".project-manager.json"
    profile_file.write_text(
        json.dumps(
            {
                "settings": {
                    "workerModels": ["deepseek-v4-flash", "qwen3.7-plus"],
                    "defaultWorkerModel": "deepseek-v4-flash",
                }
            }
        ),
        encoding="utf-8",
    )

    validate = _tool_call("manager_model_policy_validate", {"profileFile": str(profile_file)})
    diff = _tool_call("manager_model_policy_diff", {"profile": "generic"})
    cost = _tool_call("manager_model_cost_policy", {"profile": "generic"})

    assert validate["status"] == "failed"
    assert validate["error"] == "disabled worker model requested"
    assert diff["status"] == "ok"
    assert "deepseek-v4-flash" in diff["enabledWorkerModels"]
    assert cost["status"] == "ok"
    assert cost["tiers"]["default_implementation"] == ["deepseek-v4-flash"]
    assert "gpt-5.5" in cost["tiers"]["manager_or_final_review"]


def test_model_compatibility_reports_picker_visibility_and_route(monkeypatch, tmp_path: Path) -> None:
    live_models = tmp_path / "models.json"
    live_models.write_text(
        json.dumps({"models": [{"slug": "deepseek-v4-pro"}, {"slug": "gpt-5.5"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(SERVER_MODULE, "LIVE_MODELS_PATH", live_models)

    result = _tool_call("manager_model_compatibility", {"model": "deepseek-v4-pro"})

    assert result["status"] == "ok"
    assert result["model"] == "deepseek-v4-pro"
    assert result["pickerVisible"] is True
    assert result["transportRoute"] == "chat"
    assert result["providerLabel"] == "OpenCode Go"


def test_prepare_dispatch_injects_model_aware_guidance_for_repo_explorer() -> None:
    result = _tool_call(
        "manager_prepare_dispatch",
        {
            "assignmentId": "A-REPO",
            "assignmentPath": "docs/assignments/repo.md",
            "goal": "Map the call paths for the runtime boot flow.",
            "constraints": "Read-only exploration only",
            "definitionOfDone": "Return touched paths, risks, and next slice",
            "packetRole": "repo_explorer",
            "workerModel": "glm-5.2",
        },
    )

    assert result["status"] == "ok"
    assert "packet_role: repo_explorer" in result["prompt"]
    assert "worker_model: glm-5.2" in result["prompt"]
    assert "long-context" in result["prompt"].lower()


def test_prepare_worker_thread_adds_deepseek_runtime_guidance() -> None:
    result = _tool_call(
        "manager_prepare_worker_thread",
        {
            "assignmentId": "A5",
            "assignmentPath": "docs/assignments/a5.md",
            "goal": "Fix the failing worker loop.",
            "constraints": "Stay in repo scope",
            "definitionOfDone": "Tests pass",
            "workerModel": "deepseek-v4-flash",
            "packetRole": "implementer",
        },
    )

    assert result["status"] == "ok"
    assert "DeepSeek Codex worker rule" in result["createThreadRequest"]["prompt"]
    assert "immediate-tool-use" in result["modelGuidance"].lower()


def test_worker_packet_contract_returns_role_specific_guidance() -> None:
    result = _tool_call(
        "manager_worker_packet_contract",
        {
            "packetRole": "log_analyst",
            "workerModel": "mimo-v2.5",
        },
    )

    assert result["status"] == "ok"
    assert result["packetRole"] == "log_analyst"
    assert result["workerModel"] == "mimo-v2.5"
    assert "log" in result["expectedEvidence"].lower()
    assert "bounded" in result["modelGuidance"].lower()


def test_score_worker_final_flags_vague_payload() -> None:
    result = _tool_call(
        "manager_score_worker_final",
        {
            "workerFinalJson": json.dumps(
                {
                    "assignment_id": "A1",
                    "status": "blocked",
                    "summary": "Blocked",
                    "artifacts": [],
                    "verification": [],
                    "blockers": [],
                    "next_recommended_action": "help",
                }
            )
        },
    )

    assert result["status"] == "ok"
    assert result["score"] < 65
    assert result["verdict"] == "reject_or_request_revision"
    assert any("artifacts" in finding for finding in result["findings"])
    assert any("blocked/failed" in finding for finding in result["findings"])


def test_score_worker_final_accepts_worker_final_path(tmp_path: Path) -> None:
    worker_final_path = tmp_path / "worker-final.json"
    worker_final_path.write_text(
        json.dumps(
            {
                "assignment_id": "A2",
                "status": "completed",
                "summary": "Implemented the bounded packet.",
                "artifacts": ["src/example.py"],
                "verification": ["pytest tests/example.py"],
                "blockers": [],
                "next_recommended_action": "dispatch spec review",
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call("manager_score_worker_final", {"workerFinalPath": str(worker_final_path)})

    assert result["status"] == "ok"
    assert result["workerFinalInput"]["source"] == "path"
    assert result["workerFinalInput"]["workerFinalPath"] == str(worker_final_path)
    assert result["score"] >= 65


def test_prepare_thread_action_for_send_message() -> None:
    result = _tool_call(
        "manager_prepare_thread_action",
        {
            "actionType": "send_message_to_thread",
            "threadId": "thread-a",
            "prompt": "Continue the assignment.",
            "model": "pro",
            "thinking": "high",
        },
    )

    assert result["status"] == "ok"
    assert result["ledgerEventType"] == "dispatch_sent"
    assert result["failureLedgerEventType"] == "dispatch_failed"
    assert result["actionPlan"]["threadId"] == "thread-a"
    assert "Continue the assignment." in result["actionPlan"]["prompt"]
    assert result["actionPlan"]["model"] == "deepseek-v4-pro"
    assert result["actionPlan"]["thinking"] == "high"
    assert result["promptSafety"]["promptChars"] <= SERVER_MODULE.MAX_INLINE_PROMPT_CHARS
    assert result["executionChecklist"][0] == "Call send_message_to_thread with actionPlan."


def test_prepare_thread_action_compacts_nested_delegation_prompt() -> None:
    nested_prompt = "<codex_delegation><input>" + ("Repair only the live issue. " * 400) + "</input></codex_delegation>"

    result = _tool_call(
        "manager_prepare_thread_action",
        {
            "actionType": "send_message_to_thread",
            "threadId": "thread-b",
            "prompt": nested_prompt,
        },
    )

    assert result["status"] == "ok"
    assert "<codex_delegation>" not in result["actionPlan"]["prompt"]
    assert "Repair only the live issue." in result["actionPlan"]["prompt"]
    assert result["promptSafety"]["changed"] is True
    assert any("nested_codex_delegation_compacted" in warning for warning in result["promptSafety"]["warnings"])
    assert result["promptSafety"]["promptChars"] <= SERVER_MODULE.MAX_INLINE_PROMPT_CHARS


def test_recommend_recovery_prefers_replacing_after_repeated_dispatch_failures(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    for event_id in ("evt-1", "evt-2"):
        _tool_call(
            "manager_append_ledger_event",
            {
                "ledgerFile": str(ledger_file),
                "eventType": "dispatch_failed",
                "eventId": event_id,
                "payload": {"assignment_id": "A1"},
            },
        )

    result = _tool_call(
        "manager_recommend_recovery",
        {
            "ledgerFile": str(ledger_file),
            "stateJson": json.dumps({"workers": [{"label": "worker-a", "status": "active"}]}),
        },
    )

    assert result["status"] == "ok"
    assert result["action"] == "replace_thread_or_manager_takeover"
    assert "dispatch failures" in result["rationale"]
    assert result["suggestedLedgerEvent"]["eventType"] == "decision"


def test_generate_handoff_pack_uses_state_and_ledger(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(ledger_file),
            "eventType": "dispatch_sent",
            "eventId": "evt-1",
            "recordedAt": "2026-06-19T17:00:00Z",
            "assignmentId": "A1",
            "threadId": "thread-a",
            "payload": {"assignment_id": "A1"},
        },
    )

    result = _tool_call(
        "manager_generate_handoff_pack",
        {
            "title": "Restart Handoff",
            "ledgerFile": str(ledger_file),
            "stateJson": json.dumps(
                {
                    "project_root": "C:/work/example",
                    "manager_thread_id": "manager-1",
                    "workers": [{"label": "worker-a", "status": "active"}],
                }
            ),
        },
    )

    assert result["status"] == "ok"
    assert result["eventCount"] == 1
    assert "# Restart Handoff" in result["markdown"]
    assert "worker-a: active" in result["markdown"]
    assert "dispatch_sent assignment=A1 thread=thread-a" in result["markdown"]


def test_restart_recovery_combines_recovery_and_handoff(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(ledger_file),
            "eventType": "dispatch_failed",
            "eventId": "evt-1",
            "payload": {"assignment_id": "A1"},
        },
    )

    result = _tool_call(
        "manager_restart_recovery",
        {
            "ledgerFile": str(ledger_file),
            "stateJson": json.dumps({"workers": [{"label": "worker-a", "status": "blocked"}]}),
            "title": "Crash Resume",
        },
    )

    assert result["status"] == "ok"
    assert result["nextStep"] == "send_recovery_prompt"
    assert "# Crash Resume" in result["handoff"]


def test_compact_ledger_writes_checkpoint(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    output_file = tmp_path / "checkpoint.json"
    for index in range(3):
        _tool_call(
            "manager_append_ledger_event",
            {
                "ledgerFile": str(ledger_file),
                "eventType": "decision",
                "eventId": f"evt-{index}",
                "payload": {"assignment_id": f"A{index}"},
            },
        )

    result = _tool_call(
        "manager_compact_ledger",
        {"ledgerFile": str(ledger_file), "outputFile": str(output_file), "keepLast": 2},
    )

    assert result["status"] == "ok"
    assert result["checkpoint"]["original_event_count"] == 3
    assert len(result["checkpoint"]["retained_events"]) == 2
    assert output_file.exists()


def test_worker_registry_update_and_read(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"

    update = _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "threadId": "thread-a",
            "assignmentId": "A1",
            "model": "deepseek-v4-flash",
            "status": "active",
            "evidenceSource": "verified_readback",
            "updatedAt": "2026-06-19T17:30:00Z",
        },
    )
    read = _tool_call("manager_read_worker_registry", {"registryFile": str(registry_file), "workerId": "worker-a"})

    assert update["status"] == "ok"
    assert update["workerCount"] == 1
    assert read["worker"]["thread_id"] == "thread-a"
    assert read["worker"]["assignment_id"] == "A1"
    assert read["worker"]["deliveryVerified"] is False
    assert read["worker"]["evidenceSource"] == "verified_readback"
    assert read["worker"]["replacementOfThreadId"] is None
    assert read["worker"]["deadReferenceReason"] is None
    assert read["worker"]["staleConfidence"] == 0.0


def test_worker_registry_backfills_new_semantics_for_older_entries(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    registry_file.write_text(
        json.dumps(
            {
                "updated_at": "2026-06-19T17:30:00Z",
                "workers": {
                    "worker-a": {
                        "thread_id": "thread-a",
                        "assignment_id": "A1",
                        "status": "active",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    read = _tool_call("manager_read_worker_registry", {"registryFile": str(registry_file), "workerId": "worker-a"})

    assert read["status"] == "ok"
    assert read["worker"]["lastVisibleTurnAt"] is None
    assert read["worker"]["lastVerifiedHealthyAt"] is None
    assert read["worker"]["deliveryVerified"] is False
    assert read["worker"]["deliveryTurnId"] is None
    assert read["worker"]["deliveryMessageId"] is None
    assert read["worker"]["deliveryVerificationEvidence"] is None
    assert read["worker"]["acknowledgedMessageId"] is None
    assert read["worker"]["lastReadbackSummary"] is None
    assert read["worker"]["replacementOfThreadId"] is None
    assert read["worker"]["deadReferenceReason"] is None
    assert read["worker"]["staleConfidence"] == 0.0


def test_worker_registry_rejects_active_lane_without_allowed_evidence_source(tmp_path: Path) -> None:
    result = _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(tmp_path / "workers.json"),
            "workerId": "worker-a",
            "threadId": "thread-a",
            "assignmentId": "A1",
            "status": "active",
        },
    )

    assert result["status"] == "failed"
    assert "evidenceSource" in result["error"]


def test_verified_dispatch_registers_only_after_visible_readback(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"

    prepared = _tool_call(
        "manager_verified_dispatch",
        {
            "profile": "conan",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "projectRoot": "C:/work/conan",
            "managerThreadId": "manager-1",
            "workerId": "worker-a",
            "assignmentId": "A1",
            "assignmentPath": "docs/assignments/a1.md",
            "goal": "Implement the packet",
            "constraints": "Stay narrow",
            "definitionOfDone": "Tests pass",
        },
    )

    assert prepared["status"] == "ok"
    assert prepared["phase"] == "prepare"
    assert prepared["dispatchAction"]["type"] == "create_thread"

    verified = _tool_call(
        "manager_verified_dispatch",
        {
            "profile": "conan",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "projectRoot": "C:/work/conan",
            "managerThreadId": "manager-1",
            "workerId": "worker-a",
            "assignmentId": "A1",
            "assignmentPath": "docs/assignments/a1.md",
            "goal": "Implement the packet",
            "constraints": "Stay narrow",
            "definitionOfDone": "Tests pass",
            "dispatchSucceeded": True,
            "deliveryVerified": True,
            "observedThreadId": "thread-a",
            "visibleTurnAt": "2026-06-19T18:00:00Z",
            "readbackSummary": "New worker prompt is visible in the thread.",
        },
    )

    ledger = _tool_call("manager_read_ledger", {"ledgerFile": str(ledger_file), "limit": 10})
    registry = _tool_call("manager_read_worker_registry", {"registryFile": str(registry_file), "workerId": "worker-a"})

    assert verified["status"] == "ok"
    assert verified["phase"] == "verified"
    assert registry["worker"]["thread_id"] == "thread-a"
    assert registry["worker"]["deliveryVerified"] is True
    assert registry["worker"]["lastVisibleTurnAt"] == "2026-06-19T18:00:00Z"
    assert ledger["eventCount"] == 1
    assert ledger["events"][0]["event_type"] == "dispatch_sent"


def test_verified_dispatch_persists_exact_delivery_evidence_when_available(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"

    verified = _tool_call(
        "manager_verified_dispatch",
        {
            "profile": "conan",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "projectRoot": "C:/work/conan",
            "managerThreadId": "manager-1",
            "workerId": "worker-a",
            "assignmentId": "A1",
            "assignmentPath": "docs/assignments/a1.md",
            "goal": "Implement the packet",
            "constraints": "Stay narrow",
            "definitionOfDone": "Tests pass",
            "dispatchSucceeded": True,
            "deliveryVerified": True,
            "observedThreadId": "thread-a",
            "visibleTurnAt": "2026-06-19T18:00:00Z",
            "observedTurnId": "turn-delivery-123",
            "observedMessageId": "msg-delivery-456",
            "deliveryVerificationEvidence": "verified visible worker dispatch turn via read_thread",
            "readbackSummary": "New worker prompt is visible in the thread.",
        },
    )

    registry = _tool_call("manager_read_worker_registry", {"registryFile": str(registry_file), "workerId": "worker-a"})
    ledger = _tool_call("manager_read_ledger", {"ledgerFile": str(ledger_file), "limit": 10})

    assert verified["status"] == "ok"
    assert verified["deliveryTurnId"] == "turn-delivery-123"
    assert verified["deliveryMessageId"] == "msg-delivery-456"
    assert registry["worker"]["deliveryTurnId"] == "turn-delivery-123"
    assert registry["worker"]["deliveryMessageId"] == "msg-delivery-456"
    assert registry["worker"]["deliveryVerificationEvidence"] == "verified visible worker dispatch turn via read_thread"
    assert registry["worker"]["lastReadbackSummary"] == "New worker prompt is visible in the thread."
    assert ledger["events"][0]["payload"]["deliveryTurnId"] == "turn-delivery-123"
    assert ledger["events"][0]["payload"]["deliveryMessageId"] == "msg-delivery-456"


def test_verified_dispatch_fails_closed_when_readback_is_not_visible(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"

    result = _tool_call(
        "manager_verified_dispatch",
        {
            "profile": "generic",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "projectRoot": "C:/work/example",
            "managerThreadId": "manager-1",
            "workerId": "worker-a",
            "assignmentId": "A1",
            "assignmentPath": "docs/assignments/a1.md",
            "goal": "Implement the packet",
            "constraints": "Stay narrow",
            "definitionOfDone": "Tests pass",
            "dispatchSucceeded": True,
            "deliveryVerified": False,
            "observedThreadId": "thread-a",
        },
    )

    assert result["status"] == "failed"
    assert "readback" in result["error"]
    assert registry_file.exists() is False
    assert ledger_file.exists() is False


def test_replace_dead_lane_registers_replacement_only_after_verification(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-old",
            "threadId": "thread-old",
            "assignmentId": "A0",
            "status": "historical",
        },
    )

    result = _tool_call(
        "manager_replace_dead_lane",
        {
            "profile": "minecraft",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "projectRoot": "C:/work/minecraft",
            "managerThreadId": "manager-1",
            "deadWorkerId": "worker-old",
            "deadThreadId": "thread-old",
            "deadReferenceReason": "read_thread could not load the historical lane",
            "workerId": "worker-new",
            "assignmentId": "A9",
            "assignmentPath": "docs/assignments/a9.md",
            "goal": "Continue the packet in a replacement lane",
            "constraints": "Stay narrow",
            "definitionOfDone": "Tests pass",
            "dispatchSucceeded": True,
            "deliveryVerified": True,
            "observedThreadId": "thread-new",
            "visibleTurnAt": "2026-06-19T18:05:00Z",
            "readbackSummary": "Replacement lane has the new assignment prompt.",
        },
    )

    registry = _tool_call("manager_read_worker_registry", {"registryFile": str(registry_file)})

    assert result["status"] == "ok"
    assert result["replacementOfThreadId"] == "thread-old"
    assert registry["registry"]["workers"]["worker-new"]["replacementOfThreadId"] == "thread-old"
    assert registry["registry"]["workers"]["worker-new"]["deadReferenceReason"] == "read_thread could not load the historical lane"
    assert registry["registry"]["workers"]["worker-old"]["status"] == "dead_reference"


def test_lane_health_from_readback_marks_silent_delivery_as_non_healthy(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "threadId": "thread-a",
            "assignmentId": "A1",
            "status": "active",
            "deliveryVisible": True,
            "deliveryVerified": True,
            "lastVisibleTurnAt": "2026-06-19T18:00:00Z",
            "evidenceSource": "verified_readback",
            "updatedAt": "2026-06-19T18:00:00Z",
        },
    )

    result = _tool_call(
        "manager_lane_health_from_readback",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "hasVisibleTurn": True,
            "assistantAuthored": False,
            "visibleTurnAt": "2026-06-19T18:05:00Z",
            "readbackSummary": "The manager delivery turn is visible but the worker has not replied yet.",
        },
    )

    assert result["status"] == "ok"
    assert result["laneHealth"] == "silent_after_delivery"
    assert result["quietHeartbeatAllowed"] is False
    assert result["recommendedAction"] == "recover_silent_lane:worker-a"


def test_lane_health_from_readback_upgrades_progressing_lane_and_writes_registry(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "threadId": "thread-a",
            "assignmentId": "A1",
            "status": "active",
            "deliveryVisible": True,
            "deliveryVerified": True,
            "lastVisibleTurnAt": "2026-06-19T18:00:00Z",
            "evidenceSource": "verified_readback",
            "updatedAt": "2026-06-19T18:00:00Z",
        },
    )

    result = _tool_call(
        "manager_lane_health_from_readback",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "hasVisibleTurn": True,
            "assistantAuthored": True,
            "visibleTurnAt": "2026-06-19T18:10:00Z",
            "deliveryTurnId": "turn-delivery-789",
            "deliveryMessageId": "msg-delivery-789",
            "acknowledgedTurnId": "turn-ack-789",
            "acknowledgedMessageId": "msg-ack-789",
            "deliveryVerificationEvidence": "assistant reply observed after verified delivery",
            "readbackSummary": "Implemented the patch and updated tests with progress details.",
            "writeRegistry": True,
        },
    )
    read = _tool_call("manager_read_worker_registry", {"registryFile": str(registry_file), "workerId": "worker-a"})

    assert result["status"] == "ok"
    assert result["laneHealth"] == "progressing"
    assert read["worker"]["workerAcknowledged"] is True
    assert read["worker"]["progressState"] == "progressing"
    assert read["worker"]["evidenceSource"] == "verified_readback"
    assert read["worker"]["deliveryTurnId"] == "turn-delivery-789"
    assert read["worker"]["deliveryMessageId"] == "msg-delivery-789"
    assert read["worker"]["acknowledgedTurnId"] == "turn-ack-789"
    assert read["worker"]["acknowledgedMessageId"] == "msg-ack-789"
    assert read["worker"]["deliveryVerificationEvidence"] == "assistant reply observed after verified delivery"
    assert read["worker"]["lastReadbackSummary"] == "Implemented the patch and updated tests with progress details."


def test_environment_health_reports_paths_and_heartbeat_readiness(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "docs").mkdir()
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text("[]", encoding="utf-8")
    mcp_log = tmp_path / "project-manager-mcp.log"
    mcp_log.write_text("", encoding="utf-8")

    result = _tool_call(
        "manager_environment_health",
        {
            "profile": "generic",
            "projectRoot": str(project_root),
            "ledgerFile": "docs/pm-ledger.jsonl",
            "registryFile": "docs/workers.json",
            "heartbeatIntervalMinutes": 5,
        },
        env={
            **os.environ,
            "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file),
            "PROJECT_MANAGER_CANONICAL_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PROJECT_MANAGER_AGENTS_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PROJECT_MANAGER_MCP_LOG": str(mcp_log),
        },
    )

    assert result["status"] == "ok"
    assert result["pluginVersion"]
    assert result["resolvedPluginRoot"] == str(PLUGIN_ROOT)
    assert result["expectedCanonicalRoot"] == str(PLUGIN_ROOT)
    assert result["sourceAlignmentStatus"] == "aligned"
    assert result["heartbeatReady"] is True
    assert result["ledger"]["parentExists"] is True
    assert result["registry"]["parentExists"] is True
    assert result["nativeThreadCreation"]["surface"] == "create_thread.model"
    assert result["orphanMcpDiagnostics"]["orphanCount"] == 0
    assert result["transportHealth"]["wrapperSmoke"]["status"] == "ok"
    assert result["transportHealth"]["recommendedOperatorAction"] == "continue"
    assert result["modelCatalogHealth"]["expectedModelCount"] >= 11
    assert result["providerUsage"]["usageVisibilityReady"] in {True, False}


def test_environment_health_reports_orphan_pythonw_processes_from_snapshot(tmp_path: Path) -> None:
    snapshot = [
        {
            "ProcessId": 100,
            "Name": "pythonw.exe",
            "CommandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\pythonw.exe\" C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.1+codex.20260619195222\\scripts\\project_manager_mcp_server.py",
        },
        {
            "ProcessId": 200,
            "Name": "python.exe",
            "CommandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" \"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.2+codex.20260619214130\\scripts\\project_manager_mcp_server.py\"",
        },
        {
            "ProcessId": 300,
            "Name": "pythonw.exe",
            "CommandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\pythonw.exe\" C:\\Users\\SlaVKs\\.codex\\codex-proxy.py",
        },
    ]
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text(json.dumps(snapshot), encoding="utf-8")

    result = _tool_call(
        "manager_environment_health",
        {"profile": "generic"},
        env={
            **os.environ,
            "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file),
            "PROJECT_MANAGER_CANONICAL_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PROJECT_MANAGER_AGENTS_PLUGIN_ROOT": str(PLUGIN_ROOT),
        },
    )

    assert result["status"] == "ok"
    assert result["orphanMcpDiagnostics"]["orphanCount"] == 1
    assert result["orphanMcpDiagnostics"]["orphanCandidates"][0]["pid"] == 100
    assert "pythonw" in result["issues"][0].lower()


def test_environment_health_reports_cache_bound_runtimes_after_source_rollout(tmp_path: Path) -> None:
    snapshot = [
        {
            "ProcessId": 200,
            "Name": "project-manager-mcp.exe",
            "CommandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.4+codex.20260620094353\\scripts\\project-manager-mcp.exe\"",
        },
        {
            "ProcessId": 201,
            "Name": "python.exe",
            "CommandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" \"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.4+codex.20260620094353\\scripts\\project_manager_mcp_server.py\"",
        },
    ]
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text(json.dumps(snapshot), encoding="utf-8")
    mcp_log = tmp_path / "project-manager-mcp.log"
    mcp_log.write_text("", encoding="utf-8")

    result = _tool_call(
        "manager_environment_health",
        {"profile": "generic"},
        env={
            **os.environ,
            "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file),
            "PROJECT_MANAGER_CANONICAL_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PROJECT_MANAGER_AGENTS_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PROJECT_MANAGER_MCP_LOG": str(mcp_log),
        },
    )

    assert result["status"] == "ok"
    assert result["transportHealth"]["recommendedOperatorAction"] == "reload session"
    assert result["orphanMcpDiagnostics"]["cacheBoundCount"] == 2
    assert any("cache-bound project-manager MCP runtimes detected" in issue for issue in result["issues"])


def test_environment_health_flags_same_version_wrapper_buildup_before_explosion(tmp_path: Path) -> None:
    snapshot = [
        {
            "ProcessId": 2000 + index,
            "Name": "project-manager-mcp.exe",
            "CommandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project-manager-mcp.exe\"",
        }
        for index in range(6)
    ]
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text(json.dumps(snapshot), encoding="utf-8")

    result = _tool_call(
        "manager_environment_health",
        {"profile": "generic"},
        env={
            **os.environ,
            "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file),
            "PROJECT_MANAGER_CANONICAL_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PROJECT_MANAGER_AGENTS_PLUGIN_ROOT": str(PLUGIN_ROOT),
        },
    )

    assert result["status"] == "ok"
    assert result["overallStatus"] in {"degraded", "reload_required"}
    assert result["transportHealth"]["recommendedOperatorAction"] == "run codex self repair"
    assert result["transportHealth"]["readThreadSafe"] is False
    assert result["orphanMcpDiagnostics"]["sameVersionWrapperCount"] == 6
    assert result["orphanMcpDiagnostics"]["sameVersionWrapperBuildup"] is True
    assert result["orphanMcpDiagnostics"]["sameVersionWrapperBuildupLimit"] == 5
    assert any(finding["code"] == "mcp_wrapper_buildup" for finding in result["healthFindings"])


def test_environment_health_reports_same_version_mcp_process_explosion(tmp_path: Path) -> None:
    snapshot = [
        {
            "ProcessId": 1000 + index,
            "Name": "project-manager-mcp.exe",
            "CommandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\local-marketplaces\\personal\\plugins\\project-manager\\scripts\\project-manager-mcp.exe\"",
        }
        for index in range(10)
    ]
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text(json.dumps(snapshot), encoding="utf-8")

    result = _tool_call(
        "manager_environment_health",
        {"profile": "generic"},
        env={**os.environ, "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file)},
    )

    assert result["status"] == "ok"
    assert result["overallStatus"] in {"degraded", "reload_required"}
    assert result["orphanMcpDiagnostics"]["sameVersionWrapperCount"] == 10
    assert result["orphanMcpDiagnostics"]["sameVersionProcessLimitExceeded"] is True
    assert result["transportHealth"]["recommendedOperatorAction"] == "run codex self repair"
    assert any(finding["code"] == "mcp_process_explosion" for finding in result["healthFindings"])


def test_codex_desktop_log_summary_detects_null_byte_warning_and_huge_git(monkeypatch, tmp_path: Path) -> None:
    log_root = tmp_path / "Codex" / "Logs" / "2026" / "06" / "20"
    log_root.mkdir(parents=True)
    log_file = log_root / "codex-desktop-test.log"
    log_file.write_text(
        "\n".join(
            [
                'warning [electron-fetch-handler] Failed to register chat process notification errorMessage="Unexpected token \'\\u0000\', ... is not valid JSON"',
                "warning [git] git.command.complete argsCount=1026 command='git add -- lots-of-files'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(SERVER_MODULE, "CODEX_DESKTOP_LOG_ROOT", tmp_path / "Codex" / "Logs")

    summary = SERVER_MODULE._codex_desktop_log_summary(limit_files=3, tail_chars=10000)

    assert summary["status"] == "ok"
    assert summary["filesScanned"] == 1
    assert summary["nullByteJsonWarningCount"] == 1
    assert summary["hugeGitCommandCount"] == 1
    assert summary["maxGitArgsCount"] == 1026


def test_mcp_log_summary_detects_startup_storm(monkeypatch, tmp_path: Path) -> None:
    log_file = tmp_path / "project-manager-mcp.log"
    log_file.write_text(
        "\n".join(
            [
                json.dumps({"time": "2026-06-21T10:00:00Z", "event": "server_start"}),
                json.dumps({"time": "2026-06-21T10:00:05Z", "event": "server_start_suppressed"}),
                json.dumps({"time": "2026-06-21T10:00:08Z", "event": "server_start"}),
                json.dumps({"time": "2026-06-21T10:00:11Z", "event": "server_start"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(SERVER_MODULE, "MCP_LOG_PATH", log_file)

    summary = SERVER_MODULE._mcp_log_summary(limit=20)

    assert summary["status"] == "ok"
    assert summary["serverStartCount"] == 3
    assert summary["startupStormSuspected"] is True
    assert summary["startupStormWindowSeconds"] == 11.0


def test_codex_host_health_reports_armed_bootstrap(monkeypatch, tmp_path: Path) -> None:
    startup_vbs = tmp_path / "Startup" / "CodexHybridProxy-Startup.vbs"
    startup_vbs.parent.mkdir(parents=True)
    startup_vbs.write_text("codex-health-guardian.ps1", encoding="utf-8")
    bootstrap_script = tmp_path / "codex-logon-bootstrap.ps1"
    bootstrap_script.write_text("Write-Output 'ok'", encoding="utf-8")
    guardian_script = tmp_path / "codex-health-guardian.ps1"
    guardian_script.write_text("Write-Output 'guardian'", encoding="utf-8")
    launch_log = tmp_path / "launch-codex.log"
    launch_log.write_text("2026-06-21 10:05:37 bootstrap-armed\n", encoding="utf-8")
    watchdog_state = tmp_path / "codex-watchdog-state.json"
    watchdog_state.write_text(
        json.dumps(
            {
                "managed_launch": True,
                "keepalive_until_utc": "2099-06-22T01:05:36.9027243Z",
                "last_bootstrap_utc": "2099-06-21T13:05:36.9027243Z",
                "max_restarts": 12,
                "restart_count": 0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(SERVER_MODULE, "CODEX_STARTUP_VBS_PATH", startup_vbs)
    monkeypatch.setattr(SERVER_MODULE, "CODEX_LOGON_BOOTSTRAP_PATH", bootstrap_script)
    monkeypatch.setattr(SERVER_MODULE, "CODEX_HEALTH_GUARDIAN_PATH", guardian_script)
    monkeypatch.setattr(SERVER_MODULE, "CODEX_WATCHDOG_STATE_PATH", watchdog_state)
    monkeypatch.setattr(SERVER_MODULE, "CODEX_LAUNCH_LOG_PATH", launch_log)
    monkeypatch.setattr(
        SERVER_MODULE,
        "_codex_host_scheduled_task",
        lambda task_name, scan_live=False: {"status": "ok", "taskName": task_name, "state": "Ready"},
    )
    monkeypatch.setattr(
        SERVER_MODULE,
        "_codex_host_process_counts",
        lambda scan_live=False: {"status": "ok", "watchdogCount": 1, "bootstrapCount": 0, "guardianCount": 1, "sample": []},
    )

    health = SERVER_MODULE._codex_host_health(scan_live=True)

    assert health["status"] == "healthy"
    assert health["recommendedAction"] == "continue"
    assert health["guardianScript"]["exists"] is True
    assert health["guardianScript"]["startupTargetsGuardian"] is True
    assert health["guardianScript"]["running"] is True
    assert health["recoveryLoopReady"] is True
    assert health["watchdogState"]["armed"] is True
    assert health["scheduledTask"]["state"] == "Ready"
    assert health["processes"]["watchdogCount"] == 1
    assert health["processes"]["guardianCount"] == 1
    assert health["launchLog"]["tail"][-1].endswith("bootstrap-armed")


def test_codex_host_health_healthy_without_scheduled_task_when_guardian_is_running(monkeypatch, tmp_path: Path) -> None:
    startup_vbs = tmp_path / "Startup" / "CodexHybridProxy-Startup.vbs"
    startup_vbs.parent.mkdir(parents=True)
    startup_vbs.write_text("powershell codex-health-guardian.ps1", encoding="utf-8")
    bootstrap_script = tmp_path / "codex-logon-bootstrap.ps1"
    bootstrap_script.write_text("Write-Output 'ok'", encoding="utf-8")
    guardian_script = tmp_path / "codex-health-guardian.ps1"
    guardian_script.write_text("Write-Output 'guardian'", encoding="utf-8")
    launch_log = tmp_path / "launch-codex.log"
    launch_log.write_text("2026-06-21 10:05:37 guardian-start\n", encoding="utf-8")
    watchdog_state = tmp_path / "codex-watchdog-state.json"
    watchdog_state.write_text(
        json.dumps(
            {
                "managed_launch": True,
                "keepalive_until_utc": "2099-06-22T01:05:36.9027243Z",
                "last_bootstrap_utc": "2099-06-21T13:05:36.9027243Z",
                "max_restarts": 12,
                "restart_count": 0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(SERVER_MODULE, "CODEX_STARTUP_VBS_PATH", startup_vbs)
    monkeypatch.setattr(SERVER_MODULE, "CODEX_LOGON_BOOTSTRAP_PATH", bootstrap_script)
    monkeypatch.setattr(SERVER_MODULE, "CODEX_HEALTH_GUARDIAN_PATH", guardian_script)
    monkeypatch.setattr(SERVER_MODULE, "CODEX_WATCHDOG_STATE_PATH", watchdog_state)
    monkeypatch.setattr(SERVER_MODULE, "CODEX_LAUNCH_LOG_PATH", launch_log)
    monkeypatch.setattr(
        SERVER_MODULE,
        "_codex_host_scheduled_task",
        lambda task_name, scan_live=False: {"status": "missing", "taskName": task_name},
    )
    monkeypatch.setattr(
        SERVER_MODULE,
        "_codex_host_process_counts",
        lambda scan_live=False: {"status": "ok", "watchdogCount": 1, "bootstrapCount": 0, "guardianCount": 1, "sample": []},
    )

    health = SERVER_MODULE._codex_host_health(scan_live=True)

    assert health["status"] == "healthy"
    assert health["recommendedAction"] == "continue"
    assert health["scheduledTask"]["status"] == "missing"
    assert health["guardianScript"]["running"] is True
    assert health["recoveryLoopReady"] is True


def test_chat_process_registry_health_detects_all_null_bytes(tmp_path: Path) -> None:
    registry_file = tmp_path / "chat_processes.json"
    registry_file.write_bytes(b"\x00" * 64)

    result = SERVER_MODULE._chat_process_registry_health(registry_file)

    assert result["status"] == "corrupt"
    assert result["corruptionKind"] == "all_null_bytes"
    assert result["readThreadSafe"] is False
    assert result["repairSuggested"] is True
    assert result["leadingNullBytes"] == 64


def test_environment_health_flags_corrupt_chat_process_registry(monkeypatch, tmp_path: Path) -> None:
    registry_file = tmp_path / "chat_processes.json"
    registry_file.write_bytes(b"\x00" * 128)
    monkeypatch.setattr(SERVER_MODULE, "CHAT_PROCESS_REGISTRY_PATH", registry_file)
    monkeypatch.setattr(
        SERVER_MODULE,
        "_run_wrapper_smoke",
        lambda timeout_seconds=10, plugin_root=None: {"status": "ok", "toolCount": 27},
    )
    monkeypatch.setattr(
        SERVER_MODULE,
        "_project_manager_mcp_diagnostics",
        lambda scan_live=False, cleanup=False: {
            "activeCacheVersion": "0.3.6+codex.20260620162000",
            "scanPerformed": True,
            "scanSource": "env_snapshot",
            "cleanupRequested": cleanup,
            "recommendedIntervalMinutes": 15,
            "processCount": 0,
            "orphanCount": 0,
            "cacheBoundCount": 0,
            "sameVersionProcessLimitExceeded": False,
            "issues": [],
            "processes": [],
            "orphanCandidates": [],
            "cleanedPids": [],
            "failedCleanupPids": [],
        },
    )
    monkeypatch.setattr(
        SERVER_MODULE,
        "_plugin_install_state",
        lambda: {
            "currentRoot": "C:/pm/source",
            "currentKind": "source",
            "currentVersion": "0.3.6+codex.20260620162000",
            "sourceVersion": "0.3.6+codex.20260620162000",
            "activeCacheVersion": "0.3.6+codex.20260620162000",
            "cacheVersionMatchesSource": True,
            "staleLoadedSessionSuspicion": False,
            "issues": [],
        },
    )

    result = SERVER_MODULE.tool_manager_environment_health({"profile": "generic"})
    repair = SERVER_MODULE.tool_manager_repair_plan({"profile": "generic"})

    assert result["status"] == "ok"
    assert result["chatProcessRegistry"]["status"] == "corrupt"
    assert result["transportHealth"]["readThreadSafe"] is False
    assert result["transportHealth"]["recommendedOperatorAction"] == "run codex self repair"
    assert any(finding["code"] == "codex_chat_process_registry_corruption" for finding in result["healthFindings"])
    assert repair["steps"][0]["action"] == "run codex self repair"


def test_prepare_thread_action_rejects_read_thread_when_chat_process_registry_is_corrupt(tmp_path: Path) -> None:
    registry_file = tmp_path / "chat_processes.json"
    registry_file.write_bytes(b"\x00" * 32)

    result = _tool_call(
        "manager_prepare_thread_action",
        {"actionType": "read_thread", "threadId": "thread-1"},
        env={**os.environ, "CODEX_CHAT_PROCESS_REGISTRY_PATH": str(registry_file)},
    )

    assert result["status"] == "failed"
    assert result["recommendedAction"] == "run codex self repair"
    assert result["chatProcessRegistry"]["status"] == "corrupt"


def test_prepare_thread_action_rejects_read_thread_when_same_version_wrapper_buildup_detected(tmp_path: Path) -> None:
    snapshot = [
        {
            "ProcessId": 3000 + index,
            "Name": "project-manager-mcp.exe",
            "CommandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project-manager-mcp.exe\"",
        }
        for index in range(6)
    ]
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text(json.dumps(snapshot), encoding="utf-8")

    result = _tool_call(
        "manager_prepare_thread_action",
        {"actionType": "read_thread", "threadId": "thread-1"},
        env={**os.environ, "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file)},
    )

    assert result["status"] == "failed"
    assert result["recommendedAction"] == "run codex self repair"
    assert result["orphanMcpDiagnostics"]["sameVersionWrapperBuildup"] is True


def test_manager_self_repair_cleans_runtime_and_rechecks_health(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_health(args: dict[str, object]) -> dict[str, object]:
        calls.append(dict(args))
        if len(calls) == 1:
            return {
                "status": "ok",
                "overallStatus": "degraded",
                "transportHealth": {"recommendedOperatorAction": "run codex self repair"},
                "healthFindings": [{"code": "mcp_wrapper_buildup", "message": "wrapper buildup"}],
            }
        return {
            "status": "ok",
            "overallStatus": "healthy",
            "transportHealth": {"recommendedOperatorAction": "continue"},
            "healthFindings": [],
        }

    monkeypatch.setattr(SERVER_MODULE, "tool_manager_environment_health", fake_health)
    monkeypatch.setattr(
        SERVER_MODULE,
        "_project_manager_mcp_diagnostics",
        lambda scan_live=False, cleanup=False: {
            "scanPerformed": True,
            "cleanupRequested": cleanup,
            "sameVersionWrapperCleanupCandidates": [{"pid": 101}],
            "sameVersionScriptCleanupCandidates": [{"pid": 201}],
            "cleanedPids": [201, 101] if cleanup else [],
            "failedCleanupPids": [],
            "sameVersionWrapperBuildup": False,
            "sameVersionProcessLimitExceeded": False,
            "orphanCount": 0,
            "cacheBoundCount": 0,
            "issues": [],
        },
    )
    monkeypatch.setattr(
        SERVER_MODULE,
        "_run_local_install_repair",
        lambda: {"status": "ok", "cacheWrapper": {"wrapperCopied": False}, "cacheMcp": {"changed": False}},
    )

    result = SERVER_MODULE.tool_manager_self_repair({"profile": "generic"})

    assert result["status"] == "ok"
    assert result["repairStatus"] == "repaired"
    assert result["recommendedNextAction"] == "continue"
    assert result["cleanupDiagnostics"]["cleanedPids"] == [201, 101]
    assert result["installRepair"]["status"] == "ok"
    assert result["preRepairHealth"]["overallStatus"] == "degraded"
    assert result["postRepairHealth"]["overallStatus"] == "healthy"


def test_atomic_dispatch_prepare_fails_closed_when_read_thread_is_unsafe(tmp_path: Path) -> None:
    registry_file = tmp_path / "chat_processes.json"
    registry_file.write_bytes(b"\x00" * 32)

    result = _tool_call(
        "manager_atomic_dispatch_prepare",
        {
            "assignmentId": "A1",
            "assignmentPath": "docs/assignments/a1.md",
            "goal": "Implement the bounded worker task",
            "constraints": "Stay in repo scope",
            "definitionOfDone": "Tests pass",
        },
        env={**os.environ, "CODEX_CHAT_PROCESS_REGISTRY_PATH": str(registry_file)},
    )

    assert result["status"] == "failed"
    assert result["recommendedAction"] == "run codex self repair"
    assert result["chatProcessRegistry"]["status"] == "corrupt"


def test_environment_health_reports_transport_mismatch_and_reload_action(monkeypatch, tmp_path: Path) -> None:
    log_file = tmp_path / "project-manager-mcp.log"
    log_file.write_text(
        "\n".join(
            [
                json.dumps({"time": "2026-06-19T18:00:00Z", "event": "server_start"}),
                json.dumps({"time": "2026-06-19T18:01:00Z", "event": "request_exception", "error": "boom"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(SERVER_MODULE, "MCP_LOG_PATH", log_file)
    monkeypatch.setattr(SERVER_MODULE, "LIVE_MODELS_PATH", tmp_path / "models.json")
    (tmp_path / "models.json").write_text(json.dumps({"models": [{"slug": "gpt-5.5"}]}), encoding="utf-8")
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    (export_dir / "proxy-model-list.json").write_text(json.dumps({"models": [{"slug": "deepseek-v4-flash"}]}), encoding="utf-8")
    (export_dir / "proxy-runtime-instructions.json").write_text(json.dumps({"models": {"deepseek-v4-flash": {"transportRoute": "messages"}}}), encoding="utf-8")
    monkeypatch.setattr(SERVER_MODULE, "PROXY_MODEL_LIST_EXPORT_PATH", export_dir / "proxy-model-list.json")
    monkeypatch.setattr(SERVER_MODULE, "PROXY_RUNTIME_EXPORT_PATH", export_dir / "proxy-runtime-instructions.json")
    monkeypatch.setattr(SERVER_MODULE, "_run_wrapper_smoke", lambda timeout_seconds=10, plugin_root=None: {"status": "ok", "toolCount": 27})
    monkeypatch.setattr(
        SERVER_MODULE,
        "_plugin_install_state",
        lambda: {
            "currentRoot": "C:/pm/source",
            "currentKind": "source",
            "currentVersion": "0.4.0",
            "sourceVersion": "0.4.0",
            "activeCacheVersion": "0.3.2+codex.old",
            "cacheVersionMatchesSource": False,
            "staleLoadedSessionSuspicion": True,
            "issues": ["source and cached plugin versions differ"],
        },
    )
    monkeypatch.setattr(
        SERVER_MODULE,
        "_project_manager_mcp_diagnostics",
        lambda scan_live=False, cleanup=False: {
            "activeCacheVersion": "0.3.2+codex.old",
            "scanPerformed": True,
            "scanSource": "env_snapshot",
            "cleanupRequested": cleanup,
            "recommendedIntervalMinutes": 15,
            "processCount": 1,
            "orphanCount": 0,
            "processes": [],
            "orphanCandidates": [],
            "cleanedPids": [],
            "failedCleanupPids": [],
            "issues": [],
        },
    )

    result = SERVER_MODULE.tool_manager_environment_health({"profile": "generic"})

    assert result["status"] == "ok"
    assert result["transportHealth"]["sourceCache"]["cacheVersionMatchesSource"] is False
    assert result["transportHealth"]["staleLoadedSessionSuspicion"] is True
    assert result["transportHealth"]["recentLogSummary"]["errorCount"] == 1
    assert result["transportHealth"]["recommendedOperatorAction"] == "reload session"
    assert result["modelCatalogHealth"]["driftDetected"] is True
    assert result["modelCatalogHealth"]["routeMismatchCount"] >= 1
    assert result["overallStatus"] == "reload_required"
    assert any(finding["code"] == "source_cache_mismatch" for finding in result["healthFindings"])


def test_repair_plan_and_health_snapshot_summarize_degraded_health(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        SERVER_MODULE,
        "tool_manager_environment_health",
        lambda args: {
            "status": "ok",
            "pluginVersion": "0.3.2-test",
            "overallStatus": "reload_required",
            "transportHealth": {"recommendedOperatorAction": "reload session"},
            "healthFindings": [
                {
                    "severity": "error",
                    "code": "source_cache_mismatch",
                    "message": "source and cache differ",
                    "recommendedAction": "reload session",
                }
            ],
            "modelTransportHealth": {"defaultWorkerModel": "deepseek-v4-flash"},
        },
    )

    repair = SERVER_MODULE.tool_manager_repair_plan({"profile": "generic"})
    snapshot = SERVER_MODULE.tool_manager_health_snapshot({"profile": "generic"})

    assert repair["status"] == "ok"
    assert repair["overallStatus"] == "reload_required"
    assert repair["steps"][0]["action"] == "reload session"
    assert snapshot["status"] == "ok"
    assert snapshot["snapshot"]["overallStatus"] == "reload_required"
    assert snapshot["snapshot"]["findingCodes"] == ["source_cache_mismatch"]
    assert snapshot["snapshot"]["loadedTurnRecovery"]["requiresFreshTurnIfMcpMissing"] is True
    assert "fresh turn" in snapshot["snapshot"]["loadedTurnRecovery"]["prompt"].lower()


def test_dispatch_transaction_plan_fails_closed_until_readback_visible(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"

    prepared = _tool_call(
        "manager_dispatch_transaction_plan",
        {
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "workerId": "worker-a",
            "assignmentId": "A1",
            "assignmentPath": "docs/a1.md",
            "goal": "Do one narrow thing",
            "constraints": "Stay bounded",
            "definitionOfDone": "Report artifacts",
        },
    )
    failed = _tool_call(
        "manager_dispatch_transaction_plan",
        {
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "workerId": "worker-a",
            "assignmentId": "A1",
            "assignmentPath": "docs/a1.md",
            "goal": "Do one narrow thing",
            "constraints": "Stay bounded",
            "definitionOfDone": "Report artifacts",
            "dispatchSucceeded": True,
            "deliveryVerified": False,
        },
    )

    assert prepared["status"] == "ok"
    assert prepared["phase"] == "prepare"
    assert prepared["transactionState"] == "prepared_not_mutated"
    assert failed["status"] == "failed"
    assert failed["transactionState"] == "failed_closed_no_state_written"
    assert not ledger_file.exists()
    assert not registry_file.exists()


def test_atomic_dispatch_prepare_returns_host_actions_without_writes(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text("[]", encoding="utf-8")

    result = _tool_call(
        "manager_atomic_dispatch_prepare",
        {
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "workerId": "worker-a",
            "assignmentId": "A1",
            "assignmentPath": "docs/a1.md",
            "goal": "Do one narrow thing",
            "constraints": "Stay bounded",
            "definitionOfDone": "Report artifacts",
            "projectId": "proj-1",
            "targetType": "project",
            "environment": "local",
            "recordedAt": "2026-06-20T12:00:00Z",
        },
        env={**os.environ, "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file)},
    )

    assert result["status"] == "ok"
    assert result["transactionType"] == "dispatch"
    assert result["transactionId"].startswith("dispatch-A1-")
    assert [action["tool"] for action in result["hostActions"]] == ["create_thread", "read_thread"]
    assert result["hostActions"][0]["resultKey"] == "dispatch"
    assert result["hostActions"][1]["threadIdFrom"] == "dispatch.threadId"
    assert result["pendingWrites"]["forbiddenUntilFinalize"] is True
    assert not ledger_file.exists()
    assert not registry_file.exists()


def test_atomic_dispatch_finalize_visible_delivery_without_worker_ack(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"
    host_results = {
        "dispatch": {"success": True, "threadId": "thread-a"},
        "readback": {
            "success": True,
            "observedThreadId": "thread-a",
            "observedTurnId": "turn-1",
            "visibleTurnAt": "2026-06-20T12:01:00Z",
            "assistantAuthored": False,
            "readbackSummary": "manager delivery visible",
        },
    }

    result = _tool_call(
        "manager_atomic_dispatch_finalize",
        {
            "transactionId": "dispatch-A1-test",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "workerId": "worker-a",
            "assignmentId": "A1",
            "assignmentPath": "docs/a1.md",
            "workerModel": "deepseek-v4-flash",
            "hostResults": host_results,
        },
    )

    assert result["status"] == "ok"
    assert result["deliveryVisible"] is True
    assert result["workerAcknowledged"] is False
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    worker = registry["workers"]["worker-a"]
    assert worker["activeTransactionId"] == "dispatch-A1-test"
    assert worker["lastTransactionStatus"] == "finalized"
    assert worker["workerAcknowledged"] is False
    events = [json.loads(line) for line in ledger_file.read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events] == ["dispatch_sent", "transaction_finalized"]


def test_atomic_dispatch_finalize_failed_host_action_writes_transaction_failed_only(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"

    result = _tool_call(
        "manager_atomic_dispatch_finalize",
        {
            "transactionId": "dispatch-A1-failed",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "workerId": "worker-a",
            "assignmentId": "A1",
            "hostResults": {"dispatch": {"success": False, "error": "host rejected model"}},
        },
    )

    assert result["status"] == "failed"
    assert result["failClosedReason"] == "host_action_failed"
    assert not registry_file.exists()
    events = [json.loads(line) for line in ledger_file.read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events] == ["transaction_failed", "host_action_failed"]


def test_atomic_dispatch_finalize_worker_ack_requires_assistant_or_final(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"

    result = _tool_call(
        "manager_atomic_dispatch_finalize",
        {
            "transactionId": "dispatch-A2-test",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "workerId": "worker-b",
            "assignmentId": "A2",
            "hostResults": {
                "dispatch": {"success": True, "threadId": "thread-b"},
                "readback": {
                    "success": True,
                    "observedThreadId": "thread-b",
                    "observedTurnId": "turn-2",
                    "visibleTurnAt": "2026-06-20T12:03:00Z",
                    "assistantAuthored": True,
                    "readbackSummary": "assistant acknowledged",
                },
            },
        },
    )

    assert result["status"] == "ok"
    assert result["workerAcknowledged"] is True
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    assert registry["workers"]["worker-b"]["progressState"] == "acknowledged"


def test_transaction_journal_record_read_and_incomplete_sorting(tmp_path: Path) -> None:
    journal_file = tmp_path / "transaction-journal.jsonl"
    ledger_file = tmp_path / "pm-ledger.jsonl"
    registry_file = tmp_path / "workers.json"

    prepared = _tool_call(
        "manager_transaction_journal_record",
        {
            "journalFile": str(journal_file),
            "transactionId": "dispatch-A1-test",
            "transactionType": "dispatch",
            "phase": "prepared",
            "hostActions": [{"tool": "create_thread", "resultKey": "dispatch", "required": True}],
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "recordedAt": "2026-06-20T12:00:00Z",
        },
    )
    _tool_call(
        "manager_transaction_journal_record",
        {
            "journalFile": str(journal_file),
            "transactionId": "heartbeat-ok",
            "transactionType": "heartbeat_automation",
            "phase": "finalized",
            "hostResults": {"automation": {"success": True, "automationId": "heartbeat-ok"}},
            "finalizedState": "finalized",
            "recordedAt": "2026-06-20T12:01:00Z",
        },
    )
    _tool_call(
        "manager_transaction_journal_record",
        {
            "journalFile": str(journal_file),
            "transactionId": "dispatch-A1-test",
            "transactionType": "dispatch",
            "phase": "host_action_started",
            "hostResults": {"dispatch": {"success": True, "threadId": "thread-a"}},
            "recordedAt": "2026-06-20T12:02:00Z",
        },
    )

    read = _tool_call("manager_transaction_journal_read", {"journalFile": str(journal_file)})

    assert prepared["status"] == "ok"
    assert not ledger_file.exists()
    assert not registry_file.exists()
    assert read["status"] == "ok"
    assert read["openTransactionCount"] == 1
    assert read["transactions"][0]["transactionId"] == "dispatch-A1-test"
    assert read["transactions"][0]["phase"] == "host_action_started"
    assert read["transactions"][0]["hostResults"]["dispatch"]["threadId"] == "thread-a"
    assert read["transactions"][0]["incomplete"] is True
    assert read["transactions"][1]["transactionId"] == "heartbeat-ok"


def test_transaction_resume_plan_reads_created_thread_before_finalize(tmp_path: Path) -> None:
    journal_file = tmp_path / "transaction-journal.jsonl"
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text("[]", encoding="utf-8")
    _tool_call(
        "manager_transaction_journal_record",
        {
            "journalFile": str(journal_file),
            "transactionId": "dispatch-A1-test",
            "transactionType": "dispatch",
            "phase": "host_action_started",
            "hostResults": {"dispatch": {"success": True, "threadId": "thread-a"}},
        },
    )

    result = _tool_call(
        "manager_transaction_resume_plan",
        {"journalFile": str(journal_file), "transactionId": "dispatch-A1-test"},
        env={**os.environ, "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file)},
    )

    assert result["status"] == "ok"
    assert result["nextAction"] == "read_thread"
    assert result["quietHeartbeatAllowed"] is False
    assert result["hostAction"]["tool"] == "read_thread"
    assert result["hostAction"]["arguments"]["threadId"] == "thread-a"
    assert result["phaseToRecord"] == "readback_pending"


def test_transaction_resume_plan_finalizes_after_readback(tmp_path: Path) -> None:
    journal_file = tmp_path / "transaction-journal.jsonl"
    _tool_call(
        "manager_transaction_journal_record",
        {
            "journalFile": str(journal_file),
            "transactionId": "dispatch-A1-test",
            "transactionType": "dispatch",
            "phase": "readback_pending",
            "hostResults": {
                "dispatch": {"success": True, "threadId": "thread-a"},
                "readback": {
                    "success": True,
                    "observedThreadId": "thread-a",
                    "visibleTurnAt": "2026-06-20T12:03:00Z",
                    "assistantAuthored": False,
                },
            },
        },
    )

    result = _tool_call(
        "manager_transaction_resume_plan",
        {"journalFile": str(journal_file), "transactionId": "dispatch-A1-test"},
    )

    assert result["status"] == "ok"
    assert result["nextAction"] == "finalize_transaction"
    assert result["finalizeTool"] == "manager_atomic_dispatch_finalize"
    assert result["quietHeartbeatAllowed"] is False


def test_transaction_resume_plan_model_route_failure_fails_closed(tmp_path: Path) -> None:
    journal_file = tmp_path / "transaction-journal.jsonl"
    _tool_call(
        "manager_transaction_journal_record",
        {
            "journalFile": str(journal_file),
            "transactionId": "dispatch-A1-test",
            "transactionType": "dispatch",
            "phase": "host_action_started",
            "hostResults": {"dispatch": {"success": False, "error": "unsupported model deepseek-v4-flash"}},
            "workerModel": "deepseek-v4-flash",
            "nativeFallbackAllowed": False,
        },
    )

    result = _tool_call(
        "manager_transaction_resume_plan",
        {"journalFile": str(journal_file), "transactionId": "dispatch-A1-test"},
    )

    assert result["status"] == "ok"
    assert result["nextAction"] == "fail_closed_model_route_unavailable"
    assert result["modelRoutingUnavailable"] is True
    assert result["nativeFallbackAllowed"] is False
    assert result["quietHeartbeatAllowed"] is False


def test_transaction_close_requires_evidence_or_failure_reason(tmp_path: Path) -> None:
    journal_file = tmp_path / "transaction-journal.jsonl"

    invalid = _tool_call(
        "manager_transaction_close",
        {"journalFile": str(journal_file), "transactionId": "dispatch-A1-test", "closeStatus": "finalized"},
    )
    failed = _tool_call(
        "manager_transaction_close",
        {
            "journalFile": str(journal_file),
            "transactionId": "dispatch-A1-test",
            "closeStatus": "failed",
            "failureReason": "readback did not show visible delivery",
        },
    )
    read = _tool_call(
        "manager_transaction_journal_read",
        {"journalFile": str(journal_file), "transactionId": "dispatch-A1-test"},
    )

    assert invalid["status"] == "failed"
    assert "finalizeEvidence" in invalid["error"]
    assert failed["status"] == "ok"
    assert read["transactions"][0]["phase"] == "failed"
    assert read["transactions"][0]["finalizedState"] == "failed"


def test_dispatcher_runbook_maps_host_actions_and_blocks_quiet_heartbeat() -> None:
    result = _tool_call(
        "manager_dispatcher_runbook",
        {
            "transactionType": "dispatch",
            "hostActions": [
                {"tool": "create_thread", "resultKey": "dispatch", "required": True},
                {"tool": "read_thread", "resultKey": "readback", "required": True},
            ],
        },
    )

    assert result["status"] == "ok"
    assert result["hostToolMap"]["create_thread"]["codexHostTool"] == "create_thread"
    assert result["hostToolMap"]["read_thread"]["codexHostTool"] == "read_thread"
    assert result["finalizeTool"] == "manager_atomic_dispatch_finalize"
    assert result["quietHeartbeatBlockedPhases"] == ["prepared", "host_action_started", "readback_pending"]
    assert "manager_transaction_journal_record" in result["markdown"]


def test_atomic_lane_recovery_prepare_and_finalize_replaces_dead_lane(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    ledger_file = tmp_path / "pm-ledger.jsonl"
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text("[]", encoding="utf-8")
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "old-worker",
            "threadId": "old-thread",
            "assignmentId": "A1",
            "status": "dead_reference",
            "deadReferenceReason": "unreadable",
        },
    )

    prepared = _tool_call(
        "manager_atomic_lane_recovery_prepare",
        {
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "deadWorkerId": "old-worker",
            "deadThreadId": "old-thread",
            "deadReferenceReason": "unreadable",
            "workerId": "replacement-worker",
            "assignmentId": "A1R",
            "assignmentPath": "docs/a1r.md",
            "goal": "Replace dead lane",
            "constraints": "Stay bounded",
            "definitionOfDone": "Report final",
            "recordedAt": "2026-06-20T12:05:00Z",
        },
        env={**os.environ, "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file)},
    )
    finalized = _tool_call(
        "manager_atomic_lane_recovery_finalize",
        {
            "transactionId": prepared["transactionId"],
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "deadWorkerId": "old-worker",
            "deadThreadId": "old-thread",
            "deadReferenceReason": "unreadable",
            "workerId": "replacement-worker",
            "assignmentId": "A1R",
            "hostResults": {
                "dispatch": {"success": True, "threadId": "new-thread"},
                "readback": {
                    "success": True,
                    "observedThreadId": "new-thread",
                    "observedTurnId": "turn-new",
                    "visibleTurnAt": "2026-06-20T12:06:00Z",
                    "assistantAuthored": True,
                    "readbackSummary": "replacement acknowledged",
                },
            },
        },
    )

    assert prepared["status"] == "ok"
    assert prepared["transactionType"] == "lane_recovery"
    assert finalized["status"] == "ok"
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    assert registry["workers"]["replacement-worker"]["replacementOfThreadId"] == "old-thread"
    assert registry["workers"]["old-worker"]["status"] == "dead_reference"
    assert registry["workers"]["old-worker"]["replacementOfThreadId"] == "new-thread"


def test_host_action_result_validate_requires_successful_readback() -> None:
    result = _tool_call(
        "manager_host_action_result_validate",
        {
            "transactionId": "dispatch-A1-test",
            "hostResults": {
                "dispatch": {"success": True, "threadId": "thread-a"},
                "readback": {"success": False, "error": "thread not readable"},
            },
        },
    )

    assert result["status"] == "failed"
    assert result["failClosedReason"] == "readback_missing_or_failed"


def test_successor_packet_plan_routes_implementer_final_to_spec_reviewer() -> None:
    result = _tool_call(
        "manager_successor_packet_plan",
        {
            "packetRole": "implementer",
            "workerFinalJson": json.dumps(
                {
                    "assignment_id": "A1",
                    "status": "completed",
                    "summary": "Done",
                    "artifacts": ["src/file.py"],
                    "verification": ["pytest"],
                    "blockers": [],
                    "next_recommended_action": "review",
                }
            ),
        },
    )

    assert result["status"] == "ok"
    assert result["nextAction"] == "dispatch_successor"
    assert result["successorPacketRole"] == "spec_reviewer"


def test_model_transport_health_reports_per_model_viability(monkeypatch) -> None:
    monkeypatch.setattr(SERVER_MODULE, "_run_wrapper_smoke", lambda timeout_seconds=10, plugin_root=None: {"status": "ok", "toolCount": 35})
    monkeypatch.setattr(
        SERVER_MODULE,
        "_plugin_install_state",
        lambda: {
            "currentRoot": "C:/pm/source",
            "currentKind": "source",
            "currentVersion": "0.4.0",
            "sourceVersion": "0.4.0",
            "activeCacheVersion": "0.4.0",
            "cacheVersionMatchesSource": True,
            "staleLoadedSessionSuspicion": True,
            "issues": [],
        },
    )
    monkeypatch.setattr(SERVER_MODULE, "_mcp_log_summary", lambda limit=30: {"errorCount": 0, "warnCount": 0, "events": []})
    monkeypatch.setattr(
        SERVER_MODULE,
        "_project_manager_mcp_diagnostics",
        lambda scan_live=False, cleanup=False: {
            "orphanCount": 0,
            "issues": [],
        },
    )

    result = SERVER_MODULE.tool_manager_model_transport_health({"profile": "generic"})
    flash = next(model for model in result["modelTransportHealth"]["models"] if model["model"] == "deepseek-v4-flash")

    assert result["status"] == "ok"
    assert result["recommendedOperatorAction"] == "reload session"
    assert flash["recommendedUsageTier"] == "degraded_default"
    assert flash["followUpTurnViability"] == "risky"


def test_model_pressure_summary_records_failures_and_transport_health_uses_evidence(monkeypatch, tmp_path: Path) -> None:
    evidence_file = tmp_path / "model-evidence.json"
    result = _tool_call(
        "manager_model_pressure_summary",
        {
            "evidenceFile": str(evidence_file),
            "writeEvidence": True,
            "observations": [
                {
                    "model": "deepseek-v4-flash",
                    "eventType": "follow_up_tool_loop",
                    "status": "failed",
                    "recordedAt": "2026-06-20T00:00:00Z",
                },
                {
                    "model": "deepseek-v4-flash",
                    "eventType": "follow_up_tool_loop",
                    "status": "failed",
                    "recordedAt": "2026-06-20T00:05:00Z",
                },
            ],
        },
    )

    monkeypatch.setattr(SERVER_MODULE, "_run_wrapper_smoke", lambda timeout_seconds=10, plugin_root=None: {"status": "ok", "toolCount": 35})
    monkeypatch.setattr(
        SERVER_MODULE,
        "_plugin_install_state",
        lambda: {
            "currentRoot": "C:/pm/source",
            "currentKind": "source",
            "currentVersion": "0.4.0",
            "sourceVersion": "0.4.0",
            "activeCacheVersion": "0.4.0",
            "cacheVersionMatchesSource": True,
            "staleLoadedSessionSuspicion": False,
            "issues": [],
        },
    )
    monkeypatch.setattr(SERVER_MODULE, "_mcp_log_summary", lambda limit=30: {"errorCount": 0, "warnCount": 0, "events": []})
    monkeypatch.setattr(SERVER_MODULE, "_project_manager_mcp_diagnostics", lambda scan_live=False, cleanup=False: {"orphanCount": 0, "issues": []})

    health = SERVER_MODULE.tool_manager_model_transport_health({"profile": "generic", "evidenceFile": str(evidence_file)})
    flash = next(model for model in health["modelTransportHealth"]["models"] if model["model"] == "deepseek-v4-flash")

    assert result["status"] == "ok"
    assert result["models"]["deepseek-v4-flash"]["followUpFailures"] == 2
    assert flash["toolLoopReliability"] == "degraded"
    assert flash["followUpTurnViability"] == "risky"
    assert flash["fallbackModel"] == "deepseek-v4-pro"
    assert flash["operatorActionIfDegraded"] == "route_to_fallback_or_run_fresh_canary"


def test_thread_supervisor_plan_and_finalize_detects_stuck_thinking(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    ledger_file = tmp_path / "pm-ledger.jsonl"
    snapshot_file = tmp_path / "process-snapshot.json"
    snapshot_file.write_text("[]", encoding="utf-8")
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "threadId": "thread-a",
            "assignmentId": "A1",
            "status": "active",
            "deliveryVisible": True,
            "workerAcknowledged": False,
            "lastVisibleTurnAt": "2026-06-20T11:00:00Z",
            "evidenceSource": "verified_readback",
        },
    )

    plan = _tool_call(
        "manager_thread_supervisor_plan",
        {
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "maxWorkers": 5,
            "recordedAt": "2026-06-20T12:00:00Z",
        },
        env={**os.environ, "PROJECT_MANAGER_PROCESS_SNAPSHOT": str(snapshot_file)},
    )
    finalized = _tool_call(
        "manager_thread_supervisor_finalize",
        {
            "transactionId": plan["transactionId"],
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "hostResults": {
                "read_worker-a": {
                    "success": True,
                    "threadId": "thread-a",
                    "assistantAuthored": False,
                    "thinking": True,
                    "readbackSummary": "Thinking with no assistant response",
                    "visibleTurnAt": "2026-06-20T12:01:00Z",
                }
            },
        },
    )

    assert plan["status"] == "ok"
    assert [action["tool"] for action in plan["hostActions"]] == ["read_thread"]
    assert finalized["status"] == "ok"
    assert finalized["laneFindings"][0]["laneClass"] in {"silent_after_delivery", "stale"}
    assert finalized["quietHeartbeatAllowed"] is False
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    assert registry["workers"]["worker-a"]["lastTransactionStatus"] == "supervisor_attention"
    assert registry["workers"]["worker-a"]["lastSupervisorCheckAt"] == "2026-06-20T12:01:00Z"


def test_heartbeat_automation_plan_and_finalize_records_success_only_after_host_success(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"

    plan = _tool_call(
        "manager_heartbeat_automation_plan",
        {
            "ledgerFile": str(ledger_file),
            "automationId": "pm-heartbeat",
            "managerThreadId": "manager-thread",
            "projectRoot": "C:/work/example",
            "heartbeatIntervalMinutes": 5,
            "prompt": "Run atomic manager heartbeat.",
            "recordedAt": "2026-06-20T12:10:00Z",
        },
    )
    failed = _tool_call(
        "manager_heartbeat_automation_finalize",
        {
            "transactionId": plan["transactionId"],
            "ledgerFile": str(ledger_file),
            "automationId": "pm-heartbeat",
            "hostResults": {"automation": {"success": False, "error": "host rejected update"}},
        },
    )
    succeeded = _tool_call(
        "manager_heartbeat_automation_finalize",
        {
            "transactionId": plan["transactionId"],
            "ledgerFile": str(ledger_file),
            "automationId": "pm-heartbeat",
            "hostResults": {"automation": {"success": True, "automationId": "pm-heartbeat"}},
        },
    )

    assert plan["status"] == "ok"
    assert plan["hostActions"][0]["tool"] == "automation_update"
    assert plan["hostActions"][0]["arguments"]["rrule"] == "FREQ=MINUTELY;INTERVAL=5"
    assert failed["status"] == "failed"
    assert failed["failClosedReason"] == "host_action_failed"
    assert succeeded["status"] == "ok"
    events = [json.loads(line) for line in ledger_file.read_text(encoding="utf-8").splitlines()]
    assert "automation_updated" in [event["event_type"] for event in events]


def test_recent_events_and_crash_forensics_pack_include_export_hashes(monkeypatch, tmp_path: Path) -> None:
    log_file = tmp_path / "project-manager-mcp.log"
    proxy_log = tmp_path / "proxy.log"
    evidence_file = tmp_path / "model-evidence.json"
    log_file.write_text(json.dumps({"time": "2026-06-20T10:00:00Z", "event": "tool_call_error", "tool": "x"}) + "\n", encoding="utf-8")
    proxy_log.write_text("2026-06-20 parse failure model=deepseek-v4-flash\n", encoding="utf-8")
    evidence_file.write_text(json.dumps({"models": {"deepseek-v4-flash": {"followUpFailures": 1}}}), encoding="utf-8")
    monkeypatch.setattr(SERVER_MODULE, "MCP_LOG_PATH", log_file)
    monkeypatch.setattr(SERVER_MODULE, "PROXY_LOG_PATH", proxy_log)

    recent = SERVER_MODULE.tool_manager_recent_events({"evidenceFile": str(evidence_file), "logTailLines": 20})
    pack = SERVER_MODULE.tool_manager_crash_forensics_pack({"evidenceFile": str(evidence_file)})

    assert recent["status"] == "ok"
    assert recent["mcp"]["errorCount"] >= 1
    assert recent["modelPressure"]["models"]["deepseek-v4-flash"]["followUpFailures"] == 1
    assert pack["status"] == "ok"
    assert "proxyModelList" in pack["exportHashes"]
    assert pack["activeModelPolicy"]["defaultWorkerModel"] == "deepseek-v4-flash"


def test_manager_tick_recommends_replacing_dead_reference_worker() -> None:
    result = _tool_call(
        "manager_tick",
        {
            "stateJson": json.dumps(
                {
                    "workers": [
                        {
                            "label": "worker-z",
                            "threadId": "thread-z",
                            "status": "historical",
                            "deadReferenceReason": "read_thread no longer resolves the lane",
                            "staleConfidence": 1.0,
                        }
                    ]
                }
            ),
            "now": "2026-06-19T18:19:00Z",
            "staleAfterMinutes": 60,
        },
    )

    assert result["status"] == "ok"
    assert result["attentionRequired"] is True
    assert result["heartbeatDecisionHint"] == "NOTIFY"
    assert result["nextRecommendedAction"] == "replace_dead_reference_worker:worker-z"
    assert result["workers"][0]["attention"] == "dead_reference"


def test_manager_tick_requires_follow_up_for_unverified_in_flight_worker() -> None:
    result = _tool_call(
        "manager_tick",
        {
            "stateJson": json.dumps(
                {
                    "workers": [
                        {
                            "label": "worker-u",
                            "threadId": "thread-u",
                            "status": "active",
                            "deliveryVerified": False,
                            "lastProgressAt": "2026-06-19T18:15:00Z",
                        }
                    ]
                }
            ),
            "now": "2026-06-19T18:19:00Z",
            "staleAfterMinutes": 60,
        },
    )

    assert result["status"] == "ok"
    assert result["attentionRequired"] is True
    assert result["quietHeartbeatAllowed"] is False
    assert result["nextRecommendedAction"] == "verify_dispatch_delivery:worker-u"
    assert result["workers"][0]["attention"] == "unverified_dispatch"


def test_manager_tick_allows_quiet_heartbeat_for_verified_healthy_worker() -> None:
    result = _tool_call(
        "manager_tick",
        {
            "stateJson": json.dumps(
                {
                    "workers": [
                        {
                            "label": "worker-h",
                            "threadId": "thread-h",
                            "status": "active",
                            "deliveryVerified": True,
                            "lastVisibleTurnAt": "2026-06-19T18:16:00Z",
                            "lastVerifiedHealthyAt": "2026-06-19T18:16:00Z",
                        }
                    ]
                }
            ),
            "now": "2026-06-19T18:19:00Z",
            "staleAfterMinutes": 60,
        },
    )

    assert result["status"] == "ok"
    assert result["attentionRequired"] is False
    assert result["quietHeartbeatAllowed"] is True
    assert result["heartbeatDecisionHint"] == "DONT_NOTIFY"
    assert result["workers"][0]["attention"] == "healthy"


def test_orphan_cleanup_terminates_only_safe_orphan_candidates(monkeypatch) -> None:
    seen: list[int] = []
    monkeypatch.setattr(
        SERVER_MODULE,
        "_load_project_manager_process_snapshot",
        lambda scan_live=False: [
            {
                "pid": 100,
                "name": "pythonw.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\pythonw.exe\" C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.1+codex.20260619195222\\scripts\\project_manager_mcp_server.py",
            },
            {
                "pid": 200,
                "name": "python.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" \"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.2+codex.20260619214130\\scripts\\project_manager_mcp_server.py\"",
            },
        ],
    )
    monkeypatch.setattr(SERVER_MODULE, "_terminate_process", lambda pid: seen.append(pid) or True)

    diagnostics = SERVER_MODULE._project_manager_mcp_diagnostics(cleanup=True)

    assert diagnostics["orphanCount"] == 1
    assert diagnostics["cleanedPids"] == [100]
    assert seen == [100]


def test_wrapper_buildup_cleanup_terminates_only_overflow_same_version_groups(monkeypatch) -> None:
    seen: list[int] = []
    monkeypatch.setattr(
        SERVER_MODULE,
        "_load_project_manager_process_snapshot",
        lambda scan_live=False: [
            {
                "pid": 10,
                "name": "project-manager-mcp.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project-manager-mcp.exe\"",
                "parentProcessId": 500,
                "startedAt": "2026-06-20T20:00:00Z",
            },
            {
                "pid": 11,
                "name": "project-manager-mcp.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project-manager-mcp.exe\"",
                "parentProcessId": 500,
                "startedAt": "2026-06-20T20:01:00Z",
            },
            {
                "pid": 12,
                "name": "project-manager-mcp.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project-manager-mcp.exe\"",
                "parentProcessId": 500,
                "startedAt": "2026-06-20T20:02:00Z",
            },
            {
                "pid": 13,
                "name": "project-manager-mcp.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project-manager-mcp.exe\"",
                "parentProcessId": 500,
                "startedAt": "2026-06-20T20:03:00Z",
            },
            {
                "pid": 14,
                "name": "project-manager-mcp.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project-manager-mcp.exe\"",
                "parentProcessId": 500,
                "startedAt": "2026-06-20T20:04:00Z",
            },
            {
                "pid": 15,
                "name": "project-manager-mcp.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project-manager-mcp.exe\"",
                "parentProcessId": 500,
                "startedAt": "2026-06-20T20:05:00Z",
            },
            {
                "pid": 110,
                "name": "python.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" \"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project_manager_mcp_server.py\"",
                "parentProcessId": 10,
                "startedAt": "2026-06-20T20:00:01Z",
            },
            {
                "pid": 111,
                "name": "python.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" \"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project_manager_mcp_server.py\"",
                "parentProcessId": 11,
                "startedAt": "2026-06-20T20:01:01Z",
            },
            {
                "pid": 112,
                "name": "python.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" \"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project_manager_mcp_server.py\"",
                "parentProcessId": 12,
                "startedAt": "2026-06-20T20:02:01Z",
            },
            {
                "pid": 113,
                "name": "python.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" \"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project_manager_mcp_server.py\"",
                "parentProcessId": 13,
                "startedAt": "2026-06-20T20:03:01Z",
            },
            {
                "pid": 114,
                "name": "python.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" \"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project_manager_mcp_server.py\"",
                "parentProcessId": 14,
                "startedAt": "2026-06-20T20:04:01Z",
            },
            {
                "pid": 115,
                "name": "python.exe",
                "commandLine": "\"C:\\Users\\SlaVKs\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" \"C:\\Users\\SlaVKs\\.codex\\plugins\\cache\\personal\\project-manager\\0.3.7+codex.20260620164500\\scripts\\project_manager_mcp_server.py\"",
                "parentProcessId": 15,
                "startedAt": "2026-06-20T20:05:01Z",
            },
        ],
    )
    monkeypatch.setattr(SERVER_MODULE, "_terminate_process", lambda pid: seen.append(pid) or True)

    diagnostics = SERVER_MODULE._project_manager_mcp_diagnostics(cleanup=True)

    assert diagnostics["sameVersionWrapperBuildup"] is True
    assert [entry["pid"] for entry in diagnostics["sameVersionWrapperCleanupCandidates"]] == [10]
    assert [entry["pid"] for entry in diagnostics["sameVersionScriptCleanupCandidates"]] == [110]
    assert diagnostics["cleanedPids"] == [110, 10]
    assert seen == [110, 10]


def test_cross_project_summary_combines_ledgers_and_registries(tmp_path: Path) -> None:
    ledger_file = tmp_path / "a" / "ledger.jsonl"
    registry_file = tmp_path / "a" / "workers.json"
    _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(ledger_file),
            "eventType": "blocker",
            "eventId": "evt-blocked",
            "assignmentId": "A1",
            "payload": {"reason": "blocked"},
        },
    )
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "threadId": "thread-a",
            "assignmentId": "A1",
            "status": "active",
            "evidenceSource": "verified_readback",
        },
    )

    result = _tool_call(
        "manager_cross_project_summary",
        {"projects": [{"name": "project-a", "ledgerFile": str(ledger_file), "registryFile": str(registry_file)}]},
    )

    assert result["status"] == "ok"
    assert result["totals"]["projects"] == 1
    assert result["totals"]["workers"] == 1
    assert result["totals"]["ledgerEvents"] == 1
    assert result["totals"]["blockers"] == 1


def test_cross_project_summary_emits_ranked_dashboard_and_operator_queue(tmp_path: Path) -> None:
    critical_registry = tmp_path / "critical-workers.json"
    healthy_registry = tmp_path / "healthy-workers.json"
    critical_ledger = tmp_path / "critical-ledger.jsonl"
    healthy_ledger = tmp_path / "healthy-ledger.jsonl"
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(critical_registry),
            "workerId": "worker-critical",
            "threadId": "thread-critical",
            "assignmentId": "A1",
            "status": "active",
            "deliveryVisible": True,
            "deliveryVerified": True,
            "lastVisibleTurnAt": "2026-06-19T18:00:00Z",
            "evidenceSource": "verified_readback",
            "updatedAt": "2026-06-19T18:00:00Z",
        },
    )
    _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(critical_ledger),
            "eventType": "dispatch_failed",
            "eventId": "evt-critical",
            "assignmentId": "A1",
            "payload": {"reason": "send failed"},
        },
    )
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(healthy_registry),
            "workerId": "worker-healthy",
            "threadId": "thread-healthy",
            "assignmentId": "A2",
            "status": "active",
            "deliveryVisible": True,
            "deliveryVerified": True,
            "workerAcknowledged": True,
            "progressState": "progressing",
            "lastVisibleTurnAt": "2026-06-19T18:15:00Z",
            "lastProgressAt": "2026-06-19T18:15:00Z",
            "lastVerifiedHealthyAt": "2026-06-19T18:15:00Z",
            "evidenceSource": "verified_readback",
            "updatedAt": "2026-06-19T18:15:00Z",
        },
    )

    result = _tool_call(
        "manager_cross_project_summary",
        {
            "now": "2026-06-19T18:20:00Z",
            "projects": [
                {
                    "name": "critical-project",
                    "profile": "generic",
                    "projectRoot": "C:/work/critical",
                    "registryFile": str(critical_registry),
                    "ledgerFile": str(critical_ledger),
                },
                {
                    "name": "healthy-project",
                    "profile": "generic",
                    "projectRoot": "C:/work/healthy",
                    "registryFile": str(healthy_registry),
                    "ledgerFile": str(healthy_ledger),
                },
            ],
        },
    )

    assert result["status"] == "ok"
    assert result["rankedProjects"] == ["critical-project", "healthy-project"]
    assert result["totals"]["criticalProjects"] == 1
    assert result["totals"]["healthyProjects"] == 1
    assert result["totals"]["deliveryFailures"] == 1
    assert result["operatorQueue"][0]["project"] == "critical-project"
    assert result["projects"][0]["status"] == "critical"
    assert result["projects"][0]["topAction"]["recommendedAction"] == "recover_silent_lane:worker-critical"


def test_cross_project_dashboard_renders_cards_markdown_and_queue(tmp_path: Path) -> None:
    critical_registry = tmp_path / "critical-workers.json"
    critical_ledger = tmp_path / "critical-ledger.jsonl"
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(critical_registry),
            "workerId": "worker-critical",
            "threadId": "thread-critical",
            "assignmentId": "A1",
            "status": "active",
            "deliveryVisible": True,
            "deliveryVerified": True,
            "lastVisibleTurnAt": "2026-06-19T18:00:00Z",
            "evidenceSource": "verified_readback",
            "updatedAt": "2026-06-19T18:00:00Z",
        },
    )
    _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(critical_ledger),
            "eventType": "dispatch_failed",
            "eventId": "evt-critical",
            "assignmentId": "A1",
            "payload": {"reason": "send failed"},
        },
    )

    result = _tool_call(
        "manager_cross_project_dashboard",
        {
            "title": "PM Dashboard",
            "now": "2026-06-19T18:20:00Z",
            "projects": [
                {
                    "name": "critical-project",
                    "profile": "generic",
                    "projectRoot": "C:/work/critical",
                    "registryFile": str(critical_registry),
                    "ledgerFile": str(critical_ledger),
                }
            ],
        },
    )

    assert result["status"] == "ok"
    assert result["title"] == "PM Dashboard"
    assert result["rankedProjects"] == ["critical-project"]
    assert result["summaryCards"][0]["label"] == "Projects"
    assert result["topPriority"]["project"] == "critical-project"
    assert result["projectRows"][0]["status"] == "critical"
    assert result["operatorRows"][0]["action"] == "recover_silent_lane:worker-critical"
    assert "# PM Dashboard" in result["markdown"]
    assert "## Projects" in result["markdown"]
    assert "## Operator Queue" in result["markdown"]


def test_project_readiness_next_best_action_and_operator_digest(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    ledger_file = tmp_path / "pm-ledger.jsonl"
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "threadId": "thread-a",
            "assignmentId": "A1",
            "status": "dead_reference",
            "deadReferenceReason": "unreadable",
            "updatedAt": "2026-06-20T10:00:00Z",
        },
    )
    _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(ledger_file),
            "eventType": "dispatch_failed",
            "assignmentId": "A1",
        },
    )
    project = {
        "name": "example",
        "profile": "generic",
        "registryFile": str(registry_file),
        "ledgerFile": str(ledger_file),
    }

    readiness = _tool_call("manager_project_readiness_score", project)
    next_action = _tool_call("manager_next_best_action", {"projects": [project]})
    digest = _tool_call("manager_operator_digest", {"projects": [project]})

    assert readiness["status"] == "ok"
    assert readiness["overallReadiness"] < 100
    assert readiness["dimensions"]["workerProgress"] < 100
    assert next_action["status"] == "ok"
    assert next_action["nextBestAction"]["project"] == "example"
    assert digest["status"] == "ok"
    assert "example" in digest["markdown"]


def test_registry_reconcile_marks_contradicted_lane_and_repairs_evidence_source(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    registry_file.write_text(
        json.dumps(
            {
                "updated_at": "2026-06-20T00:00:00Z",
                "workers": {
                    "worker-a": {
                        "thread_id": "thread-a",
                        "assignment_id": "A1",
                        "status": "active",
                        "deliveryVisible": True,
                        "lastVisibleTurnAt": "2026-06-20T00:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call(
        "manager_registry_reconcile",
        {
            "registryFile": str(registry_file),
            "recordedAt": "2026-06-20T00:30:00Z",
            "writeChanges": True,
        },
    )
    read = _tool_call("manager_read_worker_registry", {"registryFile": str(registry_file), "workerId": "worker-a"})

    assert result["status"] == "ok"
    assert result["contradictionCount"] == 1
    assert read["worker"]["evidenceSource"] == "registry_reconcile"
    assert read["worker"]["progressState"] == "silent_after_delivery"


def test_registry_maintenance_archives_dead_and_replaced_workers(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    registry_file.write_text(
        json.dumps(
            {
                "updated_at": "2026-06-20T00:00:00Z",
                "workers": {
                    "worker-active": {
                        "thread_id": "thread-active",
                        "status": "active",
                    },
                    "worker-dead": {
                        "thread_id": "thread-dead",
                        "status": "dead_reference",
                        "deadReferenceReason": "thread unreadable",
                    },
                    "worker-replaced": {
                        "thread_id": "thread-old",
                        "status": "idle_completed_needs_next_dispatch",
                        "replacementOfThreadId": "thread-old",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call(
        "manager_registry_maintenance",
        {
            "registryFile": str(registry_file),
            "archiveDeadReferences": True,
            "archiveReplacedWorkers": True,
            "recordedAt": "2026-06-20T00:30:00Z",
        },
    )
    read = _tool_call("manager_read_worker_registry", {"registryFile": str(registry_file)})

    assert result["status"] == "ok"
    assert result["archivedCount"] == 2
    assert result["activeWorkerCount"] == 1
    assert "worker-active" in read["registry"]["workers"]
    assert "worker-dead" not in read["registry"]["workers"]
    assert "worker-replaced" not in read["registry"]["workers"]
    assert read["registry"]["archivedWorkers"]["worker-dead"]["archivedReason"] == "dead_reference"
    assert read["registry"]["archivedWorkers"]["worker-replaced"]["archivedReason"] == "replaced_or_superseded"


def test_operational_audit_scores_project_and_emits_action_queue(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    ledger_file = tmp_path / "pm-ledger.jsonl"
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "threadId": "thread-a",
            "assignmentId": "A1",
            "status": "active",
            "deliveryVerified": False,
            "evidenceSource": "verified_readback",
            "updatedAt": "2026-06-20T00:00:00Z",
        },
    )
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-b",
            "threadId": "thread-b",
            "assignmentId": "B1",
            "status": "dead_reference",
            "deadReferenceReason": "thread no longer loads",
            "updatedAt": "2026-06-20T00:00:00Z",
        },
    )
    _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(ledger_file),
            "eventType": "dispatch_failed",
            "eventId": "evt-1",
            "assignmentId": "A1",
            "payload": {"reason": "send failed"},
        },
    )

    result = _tool_call(
        "manager_operational_audit",
        {
            "profile": "generic",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "now": "2026-06-20T00:30:00Z",
        },
    )

    assert result["status"] == "ok"
    assert result["projectHealthScore"] < 70
    assert result["workerAttentionCounts"]["dead_reference"] == 1
    assert result["workerAttentionCounts"]["unverified_dispatch"] == 1
    assert result["actionQueue"][0]["recommendedAction"].startswith("replace_dead_reference_worker:")
    assert any(item["recommendedAction"].startswith("verify_dispatch_delivery:") for item in result["actionQueue"])
    assert result["deliveryFailureCount"] == 1


def test_accept_worker_final_and_plan_next_routes_implementer_to_spec_review(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    ledger_file = tmp_path / "pm-ledger.jsonl"
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-a",
            "threadId": "thread-a",
            "assignmentId": "A1",
            "model": "deepseek-v4-flash",
            "status": "active",
            "packetRole": "implementer",
            "deliveryVisible": True,
            "deliveryVerified": True,
            "workerAcknowledged": True,
            "lastVisibleTurnAt": "2026-06-20T00:00:00Z",
            "lastVerifiedHealthyAt": "2026-06-20T00:00:00Z",
            "evidenceSource": "verified_readback",
            "updatedAt": "2026-06-20T00:00:00Z",
        },
    )

    result = _tool_call(
        "manager_accept_worker_final_and_plan_next",
        {
            "profile": "generic",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "workerId": "worker-a",
            "packetRole": "implementer",
            "recordedAt": "2026-06-20T00:20:00Z",
            "workerFinalJson": json.dumps(
                {
                    "assignment_id": "A1",
                    "status": "completed",
                    "summary": "Finished the implementation packet.",
                    "artifacts": ["src/example.py"],
                    "verification": ["pytest tests/example.py"],
                    "blockers": [],
                    "next_recommended_action": "dispatch spec review",
                }
            ),
        },
    )
    read = _tool_call("manager_read_worker_registry", {"registryFile": str(registry_file), "workerId": "worker-a"})

    assert result["status"] == "ok"
    assert result["nextPhase"] == "spec_review"
    assert result["dispatchRecommendation"]["packetRole"] == "spec_reviewer"
    assert read["worker"]["status"] == "idle_completed_needs_next_dispatch"
    assert read["worker"]["progressState"] == "finaled"
    assert read["worker"]["evidenceSource"] == "worker_final"


def test_accept_worker_final_and_plan_next_accepts_worker_final_path(tmp_path: Path) -> None:
    registry_file = tmp_path / "workers.json"
    ledger_file = tmp_path / "pm-ledger.jsonl"
    worker_final_path = tmp_path / "worker-final.json"
    worker_final_path.write_text(
        json.dumps(
            {
                "assignment_id": "A4",
                "status": "completed",
                "summary": "Completed the implementation packet from file input.",
                "artifacts": ["src/from_path.py"],
                "verification": ["pytest tests/test_from_path.py"],
                "blockers": [],
                "next_recommended_action": "dispatch spec review",
            }
        ),
        encoding="utf-8",
    )
    _tool_call(
        "manager_update_worker_registry",
        {
            "registryFile": str(registry_file),
            "workerId": "worker-path",
            "threadId": "thread-path",
            "assignmentId": "A4",
            "model": "deepseek-v4-flash",
            "status": "active",
            "packetRole": "implementer",
            "deliveryVisible": True,
            "deliveryVerified": True,
            "workerAcknowledged": True,
            "lastVisibleTurnAt": "2026-06-20T00:00:00Z",
            "lastVerifiedHealthyAt": "2026-06-20T00:00:00Z",
            "evidenceSource": "verified_readback",
            "updatedAt": "2026-06-20T00:00:00Z",
        },
    )

    result = _tool_call(
        "manager_accept_worker_final_and_plan_next",
        {
            "profile": "generic",
            "registryFile": str(registry_file),
            "ledgerFile": str(ledger_file),
            "workerId": "worker-path",
            "packetRole": "implementer",
            "recordedAt": "2026-06-20T00:20:00Z",
            "workerFinalPath": str(worker_final_path),
        },
    )

    assert result["status"] == "ok"
    assert result["nextPhase"] == "spec_review"
    assert result["workerFinalInput"]["source"] == "path"
    assert result["workerFinalInput"]["workerFinalPath"] == str(worker_final_path)


def test_operator_runbook_maps_reload_and_continue_actions() -> None:
    reload_result = _tool_call("manager_operator_runbook", {"recommendedOperatorAction": "reload session"})
    continue_result = _tool_call("manager_operator_runbook", {"recommendedOperatorAction": "continue"})

    assert reload_result["status"] == "ok"
    assert reload_result["recommendedOperatorAction"] == "reload session"
    assert any("fresh Codex thread" in step for step in reload_result["steps"])
    assert continue_result["recommendedOperatorAction"] == "continue"
    assert any("manager_environment_health" in step for step in continue_result["steps"])


def test_heartbeat_bootstrap_generates_prompt_and_paths(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = _tool_call(
        "manager_heartbeat_bootstrap",
        {
            "profile": "minecraft",
            "projectRoot": str(project_root),
            "managerThreadId": "manager-thread",
            "automationId": "pm-heartbeat",
        },
    )

    assert result["status"] == "ok"
    assert result["heartbeatIntervalMinutes"] == 5
    assert "pm-heartbeat" in result["prompt"]
    assert "manager-thread" in result["prompt"]
    assert "manager_verified_dispatch" in result["prompt"]
    assert "manager_replace_dead_lane" in result["prompt"]
    assert "manager_registry_reconcile and manager_registry_maintenance" in result["prompt"]
    assert result["maintenancePolicy"]["everyHeartbeats"] == 3
    assert result["maintenancePolicy"]["requiredTools"] == [
        "manager_registry_reconcile",
        "manager_registry_maintenance",
    ]
    assert result["automationId"] == "pm-heartbeat"
    assert result["ledgerFile"].endswith("project-manager-ledger.jsonl")


def test_automation_rollout_helper_builds_packets_for_live_manager_threads(tmp_path: Path) -> None:
    result = _tool_call(
        "manager_automation_rollout_helper",
        {
            "pluginVersion": "project-manager@personal 0.3.2-test",
            "releaseNotes": "Switch to verified dispatch and maintenance-aware heartbeats.",
            "targets": [
                {
                    "name": "Conan PM",
                    "profile": "conan",
                    "projectRoot": str(tmp_path / "conan"),
                    "managerThreadId": "thread-conan",
                    "ledgerFile": str(tmp_path / "conan-ledger.jsonl"),
                    "registryFile": str(tmp_path / "conan-workers.json"),
                    "heartbeatIntervalMinutes": 5,
                    "automationId": "conan-pm-heartbeat",
                }
            ],
        },
    )

    assert result["status"] == "ok"
    assert result["targetCount"] == 1
    packet = result["rolloutPackets"][0]
    assert packet["managerThreadId"] == "thread-conan"
    assert packet["heartbeat"]["automationId"] == "conan-pm-heartbeat"
    assert packet["heartbeat"]["maintenancePolicy"]["everyHeartbeats"] == 3
    assert packet["threadAction"]["actionPlan"]["threadId"] == "thread-conan"
    assert "Release notes:" in packet["threadAction"]["actionPlan"]["prompt"]
    assert packet["ledgerEventPlan"]["eventType"] == "decision"
    assert packet["ledgerEventPlan"]["payload"]["kind"] == "plugin_rollout"


def test_rollout_execution_bundle_builds_exact_host_action_plans(tmp_path: Path) -> None:
    result = _tool_call(
        "manager_rollout_execution_bundle",
        {
            "pluginVersion": "project-manager@personal 0.3.2-test",
            "releaseNotes": "Roll out execution bundles for live manager updates.",
            "targets": [
                {
                    "name": "Minecraft PM",
                    "profile": "minecraft",
                    "projectRoot": str(tmp_path / "minecraft"),
                    "managerThreadId": "thread-minecraft",
                    "ledgerFile": str(tmp_path / "minecraft-ledger.jsonl"),
                    "registryFile": str(tmp_path / "minecraft-workers.json"),
                    "heartbeatIntervalMinutes": 10,
                    "automationId": "minecraft-pm-heartbeat",
                }
            ],
        },
    )

    assert result["status"] == "ok"
    assert result["targetCount"] == 1
    bundle = result["executionBundles"][0]
    assert bundle["automationId"] == "minecraft-pm-heartbeat"
    assert bundle["failClosedPolicy"]["deliveryAndAutomationMustSucceedBeforeLedgerWrite"] is True
    notify_step = bundle["steps"][0]
    assert notify_step["tool"] == "send_message_to_thread"
    assert notify_step["params"]["threadId"] == "thread-minecraft"
    automation_step = bundle["steps"][1]
    assert automation_step["tool"] == "automation_update"
    assert automation_step["updateParams"]["mode"] == "update"
    assert automation_step["updateParams"]["id"] == "minecraft-pm-heartbeat"
    assert automation_step["updateParams"]["rrule"] == "FREQ=MINUTELY;INTERVAL=10"
    assert automation_step["createParams"]["mode"] == "create"
    ledger_step = bundle["steps"][2]
    assert ledger_step["tool"] == "manager_append_ledger_event"
    assert ledger_step["dependsOn"] == ["notify_manager_thread", "configure_heartbeat_automation"]
    assert ledger_step["params"]["eventType"] == "decision"
    assert ledger_step["params"]["payload"]["kind"] == "plugin_rollout"
    assert ledger_step["params"]["payload"]["automation_id"] == "minecraft-pm-heartbeat"
    assert "sourceRollout" in result


def test_model_policy_packet_and_notification_surface_current_defaults() -> None:
    packet = _tool_call(
        "manager_model_policy_packet",
        {
            "audience": "manager lanes",
            "degradedModels": ["deepseek-v4-flash"],
        },
    )
    notification = _tool_call(
        "manager_notification_packet",
        {
            "audience": "manager lanes",
            "degradedModels": ["deepseek-v4-flash"],
        },
    )

    assert packet["status"] == "ok"
    assert packet["defaultWorkerModel"] == "deepseek-v4-flash"
    assert packet["escalationWorkerModel"] == "deepseek-v4-pro"
    assert "deepseek-v4-flash" in packet["prompt"]
    assert "degraded" in packet["prompt"].lower()
    assert notification["status"] == "ok"
    assert "deepseek-v4-pro" in notification["prompt"]
    assert "fresh turn" in notification["prompt"].lower()


def test_release_checklist_and_release_scripts_exist() -> None:
    result = _tool_call("manager_release_checklist", {"profile": "generic"})

    assert result["status"] == "ok"
    assert result["gates"]["sourcePytest"]["command"]
    assert result["gates"]["cachedPytest"]["command"]
    assert result["gates"]["proxyExportValidation"]["command"]
    assert result["gates"]["transactionJournalSmoke"]["command"]
    assert (PLUGIN_ROOT / "scripts" / "Sync-ProjectManagerPlugin.ps1").exists()
    assert (PLUGIN_ROOT / "scripts" / "Test-ProjectManagerProxyExports.ps1").exists()


def test_notification_packet_mentions_models_and_discipline() -> None:
    result = _tool_call(
        "manager_notification_packet",
        {
            "audience": "worker threads",
            "pluginVersion": "project-manager@personal",
            "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        },
    )

    assert result["status"] == "ok"
    assert "worker threads" in result["prompt"]
    assert "deepseek-v4-flash" in result["prompt"]
    assert "manager_verified_dispatch" in result["prompt"]
    assert "heartbeat" in result["prompt"].lower()


def test_loaded_turn_recovery_packet_mentions_rebind_contract() -> None:
    result = _tool_call(
        "manager_loaded_turn_recovery_packet",
        {
            "audience": "manager threads",
            "pluginVersion": "project-manager@personal 0.3.7-test",
            "trigger": "post-crash repair",
        },
    )

    assert result["status"] == "ok"
    assert result["requiresFreshTurnIfMcpMissing"] is True
    assert "project-manager@personal 0.3.7-test" in result["prompt"]
    assert "next fresh turn" in result["prompt"].lower()
    assert "do not relay" in result["prompt"].lower()
    assert "manager_environment_health" in result["prompt"]


def test_loaded_turn_rescue_plan_emits_same_thread_send_and_readback() -> None:
    result = _tool_call(
        "manager_loaded_turn_rescue_plan",
        {
            "managerThreadId": "manager-thread-123",
            "reason": "project-manager MCP transport closed",
            "resumeInstruction": "Resume the prior manager task from durable registry and ledger state only.",
        },
    )

    assert result["status"] == "ok"
    assert result["transactionType"] == "loaded_turn_rescue"
    assert [action["tool"] for action in result["hostActions"]] == ["send_message_to_thread", "read_thread"]
    assert result["hostActions"][0]["arguments"]["threadId"] == "manager-thread-123"
    assert "do not forward" in result["hostActions"][0]["arguments"]["prompt"].lower()
    assert "manager_environment_health" in result["hostActions"][0]["arguments"]["prompt"]
    assert result["hostActions"][1]["arguments"]["threadId"] == "manager-thread-123"
    assert result["verificationRules"]["freshTurnVisibleRequired"] is True


def test_loaded_turn_rescue_finalize_records_success_after_visible_followup(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"

    result = _tool_call(
        "manager_loaded_turn_rescue_finalize",
        {
            "transactionId": "loaded-turn-rescue-1",
            "managerThreadId": "manager-thread-123",
            "ledgerFile": str(ledger_file),
            "hostResults": {
                "rescue_send": {"success": True, "threadId": "manager-thread-123"},
                "readback": {
                    "success": True,
                    "observedThreadId": "manager-thread-123",
                    "visibleTurnAt": "2026-06-20T21:30:00Z",
                    "readbackSummary": "fresh follow-up turn visible in the rescued manager thread",
                },
            },
        },
    )

    assert result["status"] == "ok"
    assert result["freshTurnVisible"] is True
    assert result["managerThreadId"] == "manager-thread-123"
    assert result["nextAction"] == "run_manager_environment_health_in_rescued_thread"
    events = [json.loads(line) for line in ledger_file.read_text(encoding="utf-8").splitlines()]
    assert "decision" in [event["event_type"] for event in events]


def test_loaded_turn_rescue_finalize_fails_closed_without_readback(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"

    result = _tool_call(
        "manager_loaded_turn_rescue_finalize",
        {
            "transactionId": "loaded-turn-rescue-2",
            "managerThreadId": "manager-thread-123",
            "ledgerFile": str(ledger_file),
            "hostResults": {
                "rescue_send": {"success": True, "threadId": "manager-thread-123"},
            },
        },
    )

    assert result["status"] == "failed"
    assert result["failClosedReason"] == "readback_missing_or_failed"


def test_ledger_append_read_and_summary(tmp_path: Path) -> None:
    ledger_file = tmp_path / "pm-ledger.jsonl"

    first = _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(ledger_file),
            "eventType": "dispatch_sent",
            "eventId": "evt-1",
            "recordedAt": "2026-06-19T16:45:00Z",
            "projectRoot": "C:/work/example",
            "managerThreadId": "manager-1",
            "assignmentId": "A1",
            "threadId": "thread-a",
            "model": "deepseek-v4-flash",
            "payload": {"assignment_id": "A1", "target": "thread-a"},
        },
    )
    second = _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(ledger_file),
            "eventType": "worker_final",
            "eventId": "evt-2",
            "recordedAt": "2026-06-19T16:50:00Z",
            "assignmentId": "A1",
            "payload": {
                "assignment_id": "A1",
                "status": "blocked",
                "blockers": ["missing fixture"],
            },
        },
    )

    assert first["status"] == "ok"
    assert first["eventCount"] == 1
    assert second["status"] == "ok"
    assert second["eventCount"] == 2

    read_result = _tool_call(
        "manager_read_ledger",
        {
            "ledgerFile": str(ledger_file),
            "assignmentId": "A1",
            "limit": 1,
        },
    )
    assert read_result["status"] == "ok"
    assert read_result["eventCount"] == 2
    assert read_result["truncated"] is True
    assert [event["event_id"] for event in read_result["events"]] == ["evt-2"]

    summary = _tool_call("manager_ledger_summary", {"ledgerFile": str(ledger_file)})
    assert summary["status"] == "ok"
    assert summary["eventCount"] == 2
    assert summary["countsByType"] == {"dispatch_sent": 1, "worker_final": 1}
    assert summary["activeAssignments"] == ["A1"]
    assert summary["latestEvent"]["event_id"] == "evt-2"
    assert summary["latestBlockers"][0]["event_id"] == "evt-2"


def test_ledger_rejects_unknown_event_type(tmp_path: Path) -> None:
    result = _tool_call(
        "manager_append_ledger_event",
        {
            "ledgerFile": str(tmp_path / "pm-ledger.jsonl"),
            "eventType": "surprise",
        },
    )

    assert result["status"] == "failed"
    assert result["error"] == "unknown ledger event type"
    assert "dispatch_sent" in result["knownEventTypes"]


def test_register_worker_final_reports_missing_required_fields() -> None:
    result = _tool_call(
        "manager_register_worker_final",
        {
            "workerFinalJson": json.dumps(
                {
                    "assignment_id": "assign-123",
                    "status": "blocked",
                }
            )
        },
    )

    assert result["status"] == "failed"
    assert result["error"] == "missing required worker-final fields"
    assert result["missing"] == [
        "summary",
        "artifacts",
        "verification",
        "blockers",
        "next_recommended_action",
    ]


def test_register_worker_final_accepts_worker_final_path(tmp_path: Path) -> None:
    worker_final_path = tmp_path / "worker-final.json"
    worker_final_path.write_text(
        json.dumps(
            {
                "assignment_id": "A3",
                "status": "completed",
                "summary": "Registered a real worker final.",
                "artifacts": ["docs/report.md"],
                "verification": ["python -m pytest tests/test_report.py"],
                "blockers": [],
                "next_recommended_action": "manager review",
            }
        ),
        encoding="utf-8",
    )

    result = _tool_call("manager_register_worker_final", {"workerFinalPath": str(worker_final_path)})

    assert result["status"] == "completed"
    assert result["assignmentId"] == "A3"
    assert result["workerFinalInput"]["source"] == "path"
    assert result["workerFinalInput"]["workerFinalPath"] == str(worker_final_path)


def test_non_object_json_request_returns_invalid_request() -> None:
    proc, responses = _run_server([])

    assert proc.returncode == 0, proc.stderr
    assert responses == [
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    ]


def test_tools_call_with_non_mapping_params_returns_invalid_params() -> None:
    proc, responses = _run_server(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": "oops"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "manager_tick", "arguments": "oops"}},
    )

    assert proc.returncode == 0, proc.stderr
    assert responses[1] == {
        "jsonrpc": "2.0",
        "id": 2,
        "error": {"code": -32602, "message": "Invalid params"},
    }
    assert responses[2] == {
        "jsonrpc": "2.0",
        "id": 3,
        "error": {"code": -32602, "message": "Invalid params"},
    }
