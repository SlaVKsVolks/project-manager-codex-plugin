[CmdletBinding()]
param(
  [string]$SourceRoot = "$HOME\.codex\plugins\local-marketplaces\personal\plugins\project-manager",
  [string]$CacheRoot = "",
  [string]$PythonExe = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$processSnapshotFile = Join-Path ([System.IO.Path]::GetTempPath()) ('project-manager-empty-snapshot-' + [guid]::NewGuid().ToString() + '.json')
$mcpLogFile = Join-Path ([System.IO.Path]::GetTempPath()) ('project-manager-mcp-' + [guid]::NewGuid().ToString() + '.jsonl')
$wrapperLogFile = Join-Path ([System.IO.Path]::GetTempPath()) ('project-manager-wrapper-' + [guid]::NewGuid().ToString() + '.log')
Set-Content -LiteralPath $processSnapshotFile -Value "[]" -Encoding UTF8
$previousProcessSnapshot = $env:PROJECT_MANAGER_PROCESS_SNAPSHOT
$previousMcpLog = $env:PROJECT_MANAGER_MCP_LOG
$previousWrapperLog = $env:PROJECT_MANAGER_WRAPPER_LOG
$env:PROJECT_MANAGER_PROCESS_SNAPSHOT = $processSnapshotFile
$env:PROJECT_MANAGER_MCP_LOG = $mcpLogFile
$env:PROJECT_MANAGER_WRAPPER_LOG = $wrapperLogFile

try {

if (-not $CacheRoot) {
  $cacheBase = Join-Path $HOME '.codex\plugins\cache\personal\project-manager'
  $latest = Get-ChildItem -LiteralPath $cacheBase -Directory | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
  if (-not $latest) {
    throw "No cached project-manager install found under $cacheBase"
  }
  $CacheRoot = $latest.FullName
}

Write-Host '[1/10] Building source wrapper'
& (Join-Path $scriptRoot 'Build-ProjectManagerWrapper.ps1') -PluginRoot $SourceRoot
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host '[2/10] Checking source/cache consistency'
& (Join-Path $scriptRoot 'Check-ProjectManagerCacheConsistency.ps1') -SourceRoot $SourceRoot -CacheRoot $CacheRoot
if (-not $?) {
  exit 1
}

Write-Host '[3/10] Running source plugin pytest suite'
& $PythonExe -m pytest (Join-Path $SourceRoot 'tests\test_project_manager_mcp_server.py')
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host '[4/10] Running cached plugin pytest suite'
& $PythonExe -m pytest (Join-Path $CacheRoot 'tests\test_project_manager_mcp_server.py')
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host '[5/10] Running proxy export validation'
& (Join-Path $scriptRoot 'Test-ProjectManagerProxyExports.ps1') -PluginRoot $SourceRoot
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host '[6/10] Running export health JSON-RPC smoke'
$exportHealthCode = @'
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import uuid

root = pathlib.Path(sys.argv[1])
server = root / "scripts" / "project_manager_mcp_server.py"
snapshot = pathlib.Path(tempfile.gettempdir()) / f"project-manager-export-health-snapshot-{uuid.uuid4()}.json"
snapshot.write_text("[]", encoding="utf-8")
env = dict(os.environ)
env["PROJECT_MANAGER_PROCESS_SNAPSHOT"] = str(snapshot)
payload = "\n".join(
    json.dumps(message)
    for message in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "manager_model_export_health", "arguments": {}}},
    )
) + "\n"
try:
    proc = subprocess.run([sys.executable, str(server)], input=payload, text=True, capture_output=True, cwd=root, check=False, timeout=20, env=env)
finally:
    snapshot.unlink(missing_ok=True)
if proc.returncode != 0:
    raise SystemExit(proc.stderr or f"server exited {proc.returncode}")
responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
result = responses[-1].get("result", {})
content_items = result.get("content")
if not content_items:
    raise SystemExit(json.dumps({"status": "failed", "response": responses[-1]}))
content = json.loads(content_items[0]["text"])
if content.get("status") != "ok":
    raise SystemExit(json.dumps(content))
print(json.dumps({"status": "ok", "overallStatus": content.get("overallStatus"), "disabledModelRouteLeak": content.get("disabledModelRouteLeak")}))
'@
$tempExportHealth = Join-Path ([System.IO.Path]::GetTempPath()) ('project-manager-export-health-' + [guid]::NewGuid().ToString() + '.py')
Set-Content -LiteralPath $tempExportHealth -Value $exportHealthCode -Encoding UTF8
try {
  & $PythonExe $tempExportHealth $SourceRoot
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  if (Test-Path -LiteralPath $tempExportHealth) {
    Remove-Item -LiteralPath $tempExportHealth -Force
  }
}

Write-Host '[7/10] Running atomic host-action JSON-RPC smoke'
$atomicSmokeCode = @'
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import uuid

root = pathlib.Path(sys.argv[1])
server = root / "scripts" / "project_manager_mcp_server.py"
snapshot = pathlib.Path(tempfile.gettempdir()) / f"project-manager-atomic-snapshot-{uuid.uuid4()}.json"
snapshot.write_text("[]", encoding="utf-8")
env = dict(os.environ)
env["PROJECT_MANAGER_PROCESS_SNAPSHOT"] = str(snapshot)
payload = "\n".join(
    json.dumps(message)
    for message in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "manager_atomic_dispatch_prepare",
                "arguments": {
                    "assignmentId": "smoke",
                    "assignmentPath": "docs/smoke.md",
                    "goal": "Smoke test atomic host-action preparation.",
                    "constraints": "No mutation outside this JSON-RPC smoke.",
                    "definitionOfDone": "Return host actions.",
                },
            },
        },
    )
) + "\n"
try:
    proc = subprocess.run([sys.executable, str(server)], input=payload, text=True, capture_output=True, cwd=root, check=False, timeout=20, env=env)
finally:
    snapshot.unlink(missing_ok=True)
if proc.returncode != 0:
    raise SystemExit(proc.stderr or f"server exited {proc.returncode}")
responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
result = responses[-1].get("result", {})
content_items = result.get("content")
if not content_items:
    raise SystemExit(json.dumps({"status": "failed", "response": responses[-1]}))
content = json.loads(content_items[0]["text"])
if content.get("status") != "ok":
    raise SystemExit(json.dumps(content))
tools = [action.get("tool") for action in content.get("hostActions", [])]
if tools != ["create_thread", "read_thread"]:
    raise SystemExit(json.dumps({"status": "failed", "hostActions": content.get("hostActions")}))
print(json.dumps({"status": "ok", "transactionType": content.get("transactionType"), "hostActions": tools}))
'@
$tempAtomicSmoke = Join-Path ([System.IO.Path]::GetTempPath()) ('project-manager-atomic-smoke-' + [guid]::NewGuid().ToString() + '.py')
Set-Content -LiteralPath $tempAtomicSmoke -Value $atomicSmokeCode -Encoding UTF8
try {
  & $PythonExe $tempAtomicSmoke $SourceRoot
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  if (Test-Path -LiteralPath $tempAtomicSmoke) {
    Remove-Item -LiteralPath $tempAtomicSmoke -Force
  }
}

Write-Host '[8/10] Running transaction journal/resume JSON-RPC smoke'
$journalSmokeCode = @'
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import uuid

root = pathlib.Path(sys.argv[1])
server = root / "scripts" / "project_manager_mcp_server.py"
journal_file = pathlib.Path(tempfile.gettempdir()) / "project-manager-transaction-journal-smoke.jsonl"
snapshot = pathlib.Path(tempfile.gettempdir()) / f"project-manager-journal-snapshot-{uuid.uuid4()}.json"
snapshot.write_text("[]", encoding="utf-8")
env = dict(os.environ)
env["PROJECT_MANAGER_PROCESS_SNAPSHOT"] = str(snapshot)
try:
    journal_file.unlink()
except FileNotFoundError:
    pass
messages = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "manager_transaction_journal_record",
            "arguments": {
                "journalFile": str(journal_file),
                "transactionId": "dispatch-smoke",
                "transactionType": "dispatch",
                "phase": "host_action_started",
                "hostResults": {"dispatch": {"success": True, "threadId": "thread-smoke"}},
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "manager_transaction_resume_plan",
            "arguments": {"journalFile": str(journal_file), "transactionId": "dispatch-smoke"},
        },
    },
]
payload = "\n".join(json.dumps(message) for message in messages) + "\n"
try:
    proc = subprocess.run([sys.executable, str(server)], input=payload, text=True, capture_output=True, cwd=root, check=False, timeout=20, env=env)
finally:
    snapshot.unlink(missing_ok=True)
if proc.returncode != 0:
    raise SystemExit(proc.stderr or f"server exited {proc.returncode}")
responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
record = json.loads(responses[1]["result"]["content"][0]["text"])
resume = json.loads(responses[2]["result"]["content"][0]["text"])
if record.get("status") != "ok":
    raise SystemExit(json.dumps(record))
if resume.get("status") != "ok" or resume.get("nextAction") != "read_thread":
    raise SystemExit(json.dumps(resume))
print(json.dumps({"status": "ok", "nextAction": resume.get("nextAction"), "threadId": resume.get("hostAction", {}).get("arguments", {}).get("threadId")}))
'@
$tempJournalSmoke = Join-Path ([System.IO.Path]::GetTempPath()) ('project-manager-journal-smoke-' + [guid]::NewGuid().ToString() + '.py')
Set-Content -LiteralPath $tempJournalSmoke -Value $journalSmokeCode -Encoding UTF8
try {
  & $PythonExe $tempJournalSmoke $SourceRoot
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  if (Test-Path -LiteralPath $tempJournalSmoke) {
    Remove-Item -LiteralPath $tempJournalSmoke -Force
  }
}

Write-Host '[9/10] Running environment-health alignment JSON-RPC smoke'
$healthSmokeCode = @'
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import uuid

root = pathlib.Path(sys.argv[1])
server = root / "scripts" / "project_manager_mcp_server.py"
snapshot = pathlib.Path(tempfile.gettempdir()) / f"project-manager-health-snapshot-{uuid.uuid4()}.json"
snapshot.write_text("[]", encoding="utf-8")
env = dict(os.environ)
env["PROJECT_MANAGER_PROCESS_SNAPSHOT"] = str(snapshot)
payload = "\n".join(
    json.dumps(message)
    for message in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "manager_environment_health", "arguments": {"profile": "generic", "scanOrphanProcesses": False, "scanHostHealth": False}}},
    )
) + "\n"
try:
    proc = subprocess.run([sys.executable, str(server)], input=payload, text=True, capture_output=True, cwd=root, check=False, timeout=20, env=env)
finally:
    snapshot.unlink(missing_ok=True)
if proc.returncode != 0:
    raise SystemExit(proc.stderr or f"server exited {proc.returncode}")
responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
tool_response = next((response for response in responses if response.get("id") == 2), None)
if not tool_response:
    raise SystemExit(json.dumps({"status": "failed", "reason": "missing tool response", "responses": responses}))
if "result" not in tool_response:
    raise SystemExit(json.dumps({"status": "failed", "reason": "tool response missing result", "response": tool_response}))
content_items = tool_response["result"].get("content")
if not content_items:
    raise SystemExit(json.dumps({"status": "failed", "reason": "tool response missing content", "response": tool_response}))
result = json.loads(content_items[0]["text"])
expected_root = str(root)
if result.get("resolvedPluginRoot") != expected_root:
    raise SystemExit(json.dumps({"status": "failed", "reason": "resolvedPluginRoot mismatch", "result": result}))
if result.get("expectedCanonicalRoot") != expected_root:
    raise SystemExit(json.dumps({"status": "failed", "reason": "expectedCanonicalRoot mismatch", "result": result}))
if result.get("sourceAlignmentStatus") != "aligned":
    raise SystemExit(json.dumps({"status": "failed", "reason": "sourceAlignmentStatus mismatch", "result": result}))
print(json.dumps({"status": "ok", "resolvedPluginRoot": result.get("resolvedPluginRoot"), "sourceAlignmentStatus": result.get("sourceAlignmentStatus")}))
'@
$tempHealthSmoke = Join-Path ([System.IO.Path]::GetTempPath()) ('project-manager-health-smoke-' + [guid]::NewGuid().ToString() + '.py')
Set-Content -LiteralPath $tempHealthSmoke -Value $healthSmokeCode -Encoding UTF8
try {
  & $PythonExe $tempHealthSmoke $SourceRoot
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  if (Test-Path -LiteralPath $tempHealthSmoke) {
    Remove-Item -LiteralPath $tempHealthSmoke -Force
  }
}

Write-Host '[10/10] Running fresh packaged wrapper JSON-RPC smoke'
$smokeCode = @'
import json
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
config = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
server = config["mcpServers"]["project-manager"]
command = pathlib.Path(server["command"])
if not command.is_absolute():
    command = (root / command).resolve()
payload = "\n".join(
    json.dumps(message)
    for message in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
) + "\n"
proc = subprocess.run(
    [str(command), *server.get("args", [])],
    input=payload,
    text=True,
    capture_output=True,
    cwd=root,
    check=False,
    timeout=20,
)
if proc.returncode != 0:
    raise SystemExit(proc.stderr or f"wrapper exited {proc.returncode}")
responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
tools = responses[-1]["result"]["tools"]
print(json.dumps({"status": "ok", "serverName": responses[0]["result"]["serverInfo"]["name"], "toolCount": len(tools)}))
'@
$tempSmoke = Join-Path ([System.IO.Path]::GetTempPath()) ('project-manager-smoke-' + [guid]::NewGuid().ToString() + '.py')
Set-Content -LiteralPath $tempSmoke -Value $smokeCode -Encoding UTF8
try {
  & $PythonExe $tempSmoke $SourceRoot
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  if (Test-Path -LiteralPath $tempSmoke) {
    Remove-Item -LiteralPath $tempSmoke -Force
  }
}

Write-Host '[done] Project-manager plugin verification completed successfully'
} finally {
  if ($null -ne $previousProcessSnapshot) {
    $env:PROJECT_MANAGER_PROCESS_SNAPSHOT = $previousProcessSnapshot
  } else {
    Remove-Item Env:PROJECT_MANAGER_PROCESS_SNAPSHOT -ErrorAction SilentlyContinue
  }
  if ($null -ne $previousMcpLog) {
    $env:PROJECT_MANAGER_MCP_LOG = $previousMcpLog
  } else {
    Remove-Item Env:PROJECT_MANAGER_MCP_LOG -ErrorAction SilentlyContinue
  }
  if ($null -ne $previousWrapperLog) {
    $env:PROJECT_MANAGER_WRAPPER_LOG = $previousWrapperLog
  } else {
    Remove-Item Env:PROJECT_MANAGER_WRAPPER_LOG -ErrorAction SilentlyContinue
  }
  if (Test-Path -LiteralPath $processSnapshotFile) {
    Remove-Item -LiteralPath $processSnapshotFile -Force -ErrorAction SilentlyContinue
  }
  if (Test-Path -LiteralPath $mcpLogFile) {
    Remove-Item -LiteralPath $mcpLogFile -Force -ErrorAction SilentlyContinue
  }
  if (Test-Path -LiteralPath $wrapperLogFile) {
    Remove-Item -LiteralPath $wrapperLogFile -Force -ErrorAction SilentlyContinue
  }
}
