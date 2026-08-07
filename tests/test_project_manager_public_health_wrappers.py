import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_WRAPPER = ROOT / "scripts" / "Sync-ProjectManagerPublicHealth.ps1"
RELEASE_WRAPPER = ROOT / "scripts" / "Prepare-ProjectManagerRoadmapRelease.ps1"
PWSH = shutil.which("pwsh") or shutil.which("powershell")


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    assert PWSH is not None, "PowerShell is required for wrapper tests"
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", *command],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_fake_compact_wrappers(plugin_root: Path) -> None:
    scripts = plugin_root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "Invoke-ProjectManagerEnvironmentHealth.ps1").write_text(
        r'''[CmdletBinding()]
param(
  [string]$PluginRoot,
  [string]$ProjectRoot,
  [string]$RegistryFile,
  [string]$LedgerFile,
  [int]$HeartbeatIntervalMinutes,
  [switch]$ScanHostHealth,
  [switch]$Compact
)
@{
  status = 'ok'
  overallStatus = 'healthy'
  cacheMirrorHealth = @{ resolvedPluginVersion = '0.4.7+codex.20260807151702' }
  coordinationGate = 'allow'
  heartbeatReady = $true
  freshThreadLikelyCallable = $true
  sameLoadedTurnLikelyCallable = $true
  healthFindingCodes = @('live_model_catalog_advisory')
  blockingFindingCodes = @()
  nonBlockingFindingCodes = @('live_model_catalog_advisory')
  rawPath = 'C:\Users\Fixture\must-not-leak.log'
} | ConvertTo-Json -Depth 8
''',
        encoding="utf-8",
    )
    (scripts / "Get-ProjectManagerStabilityAudit.ps1").write_text(
        r'''[CmdletBinding()]
param(
  [string]$PluginRoot,
  [string]$ProjectRoot,
  [string]$RegistryFile,
  [string]$LedgerFile,
  [switch]$Compact
)
@{
  status = 'ok'
  auditStatus = 'healthy'
  safeForManagerAutomation = $true
  pluginVersion = '0.4.7+codex.20260807151702'
  checkedAt = '2026-08-07T20:00:00Z'
  invariantCount = 10
  failedInvariantCount = 0
  failedInvariantCodes = @()
  rawEmail = 'operator@example.test'
} | ConvertTo-Json -Depth 8
''',
        encoding="utf-8",
    )


def _health_snapshot(*, digest: str = "b" * 64) -> dict:
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-08-07T20:00:00Z",
        "maxAgeMinutes": 30,
        "contentDigest": digest,
        "source": {"revision": "a" * 40, "dirty": True},
        "environment": {
            "pluginVersion": "0.4.7+codex.20260807151702",
            "overallStatus": "healthy",
            "coordinationGate": "allow",
            "heartbeatReady": True,
            "freshThreadCallability": "callable",
            "sameLoadedTurnCallability": "callable",
            "blockingFindingCodes": [],
            "advisoryFindingCodes": [],
            "nonBlockingFindingCodes": [],
        },
        "stability": {
            "status": "healthy",
            "safeForManagerAutomation": True,
            "invariantCount": 10,
            "failedInvariantCount": 0,
            "failedInvariantCodes": [],
        },
        "evidenceBoundary": "Snapshot evidence is not proof of this viewer's current loaded-turn binding.",
    }


def _init_deployment_repo(path: Path) -> None:
    data = path / "site" / "src" / "data"
    data.mkdir(parents=True)
    (data / "project-manager.json").write_text(
        json.dumps({"schemaVersion": 1, "generated": {"documentCount": 0}, "documents": []}),
        encoding="utf-8",
    )
    baseline_health = _health_snapshot(digest="c" * 64)
    baseline_health["baselineOnly"] = True
    (data / "project-manager-health.json").write_text(json.dumps(baseline_health), encoding="utf-8")
    subprocess.run(
        ["git", "init", "-b", "codex/project-manager-rock-solid"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=path, check=True, capture_output=True)


def test_health_wrapper_executes_compact_sources_and_removes_raw_files(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    project_root = tmp_path / "source"
    temp_root = tmp_path / "temp"
    output_path = tmp_path / "output" / "project-manager-health.json"
    project_root.mkdir()
    temp_root.mkdir()
    _write_fake_compact_wrappers(plugin_root)
    before = set(temp_root.rglob("*"))
    env = os.environ.copy()
    env.update(TEMP=str(temp_root), TMP=str(temp_root))

    result = _run(
        [
            str(SYNC_WRAPPER),
            "-ProjectRoot",
            str(project_root),
            "-OutputPath",
            str(output_path),
            "-PluginRoot",
            str(plugin_root),
            "-PythonExe",
            sys.executable,
            "-MaxAgeMinutes",
            "30",
        ],
        cwd=ROOT,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    snapshot = json.loads(output_path.read_text(encoding="utf-8"))
    assert snapshot["environment"]["overallStatus"] == "healthy"
    assert snapshot["environment"]["coordinationGate"] == "allow"
    assert snapshot["stability"]["failedInvariantCount"] == 0
    assert len(snapshot["contentDigest"]) == 64
    assert set(temp_root.rglob("*")) == before
    assert r"C:\Users\Fixture" not in json.dumps(snapshot)


def test_release_wrapper_changes_only_generated_destinations_and_blocks_unrelated_dirt(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    deployment_root = tmp_path / "deployment"
    source_root.mkdir()
    deployment_root.mkdir()
    _init_deployment_repo(deployment_root)
    documentation_input = tmp_path / "project-manager.json"
    health_input = tmp_path / "project-manager-health.json"
    documentation_input.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "generated": {"documentCount": 2},
                "documents": [{"id": "one"}, {"id": "two"}],
            }
        ),
        encoding="utf-8",
    )
    health_input.write_text(json.dumps(_health_snapshot()), encoding="utf-8")

    result = _run(
        [
            str(RELEASE_WRAPPER),
            "-SourceRoot",
            str(source_root),
            "-DeploymentRoot",
            str(deployment_root),
            "-DocumentationInputPath",
            str(documentation_input),
            "-HealthInputPath",
            str(health_input),
            "-SkipBuild",
        ],
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout.splitlines()[-1])
    assert summary["status"] == "ok"
    assert summary["documentationChanged"] is True
    assert summary["healthChanged"] is True
    assert summary["changed"] is True
    assert summary["documentCount"] == 2
    assert summary["healthDigest"] == "b" * 64
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=deployment_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert sorted(line[3:].replace("\\", "/") for line in status) == [
        "site/src/data/project-manager-health.json",
        "site/src/data/project-manager.json",
    ]

    documentation_destination = deployment_root / "site" / "src" / "data" / "project-manager.json"
    health_destination = deployment_root / "site" / "src" / "data" / "project-manager-health.json"
    before_documents = documentation_destination.read_bytes()
    before_health = health_destination.read_bytes()
    (deployment_root / "unrelated.txt").write_text("do not touch\n", encoding="utf-8")
    documentation_input.write_text(
        json.dumps({"schemaVersion": 1, "generated": {"documentCount": 3}, "documents": []}),
        encoding="utf-8",
    )

    blocked = _run(
        [
            str(RELEASE_WRAPPER),
            "-SourceRoot",
            str(source_root),
            "-DeploymentRoot",
            str(deployment_root),
            "-DocumentationInputPath",
            str(documentation_input),
            "-HealthInputPath",
            str(health_input),
            "-SkipBuild",
        ],
        cwd=ROOT,
    )

    assert blocked.returncode != 0
    assert "unrelated changes" in blocked.stderr
    assert documentation_destination.read_bytes() == before_documents
    assert health_destination.read_bytes() == before_health
