import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "project_manager_public_health.py"
SPEC = importlib.util.spec_from_file_location("project_manager_public_health", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
PUBLIC_HEALTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLIC_HEALTH)


def _health() -> dict:
    return {
        "status": "ok",
        "overallStatus": "healthy",
        "pluginPackageHealth": {
            "status": "healthy",
            "debugPath": r"C:\Users\Fixture\private.log",
        },
        "cacheMirrorHealth": {
            "resolvedPluginVersion": "0.4.7+codex.20260807151702",
            "privateUrl": "http://127.0.0.1:7778/health",
        },
        "coordinationGate": "allow",
        "heartbeatReady": True,
        "freshThreadLikelyCallable": True,
        "sameLoadedTurnLikelyCallable": True,
        "healthFindingCodes": ["live_model_catalog_advisory"],
        "blockingFindingCodes": [],
        "nonBlockingFindingCodes": ["live_model_catalog_advisory"],
        "requestTag": "thread-identifier",
        "wrapperCommand": "powershell -File private.ps1",
    }


def _stability() -> dict:
    return {
        "status": "ok",
        "auditStatus": "healthy",
        "safeForManagerAutomation": True,
        "pluginVersion": "0.4.7+codex.20260807151702",
        "checkedAt": "2026-08-07T19:59:58Z",
        "invariantCount": 10,
        "failedInvariantCount": 0,
        "failedInvariantCodes": [],
        "private": {"email": "operator@example.test"},
    }


def _build(*, generated_at: str = "2026-08-07T20:00:00Z") -> dict:
    return PUBLIC_HEALTH.build_public_health_snapshot(
        _health(),
        _stability(),
        generated_at=generated_at,
        max_age_minutes=30,
        source_revision="a" * 40,
        source_dirty=True,
    )


def test_build_public_health_snapshot_projects_only_safe_fields() -> None:
    snapshot = _build()

    assert snapshot["schemaVersion"] == 1
    assert snapshot["environment"] == {
        "pluginVersion": "0.4.7+codex.20260807151702",
        "overallStatus": "healthy",
        "coordinationGate": "allow",
        "heartbeatReady": True,
        "freshThreadCallability": "callable",
        "sameLoadedTurnCallability": "callable",
        "blockingFindingCodes": [],
        "advisoryFindingCodes": [],
        "nonBlockingFindingCodes": ["live_model_catalog_advisory"],
    }
    assert snapshot["stability"] == {
        "status": "healthy",
        "safeForManagerAutomation": True,
        "invariantCount": 10,
        "failedInvariantCount": 0,
        "failedInvariantCodes": [],
    }
    assert snapshot["source"] == {"revision": "a" * 40, "dirty": True}
    assert len(snapshot["contentDigest"]) == 64
    serialized = json.dumps(snapshot)
    assert r"C:\Users" not in serialized
    assert "thread-identifier" not in serialized
    assert "operator@example.test" not in serialized


def test_content_digest_excludes_generation_timestamp() -> None:
    assert _build(generated_at="2026-08-07T20:00:00Z")["contentDigest"] == _build(
        generated_at="2026-08-07T20:15:00Z"
    )["contentDigest"]


def test_operational_block_states_are_normalized_fail_closed() -> None:
    health = _health()
    stability = _stability()
    health.update(
        overallStatus="reload_required",
        coordinationGate="block_live_session",
        heartbeatReady=False,
        freshThreadLikelyCallable=False,
        sameLoadedTurnLikelyCallable=False,
    )
    stability.update(auditStatus="unstable", safeForManagerAutomation=False)

    snapshot = PUBLIC_HEALTH.build_public_health_snapshot(
        health,
        stability,
        generated_at="2026-08-07T20:00:00Z",
        max_age_minutes=30,
        source_revision="unknown",
        source_dirty=False,
    )

    assert snapshot["environment"]["overallStatus"] == "unhealthy"
    assert snapshot["environment"]["coordinationGate"] == "block"
    assert snapshot["environment"]["heartbeatReady"] is False
    assert snapshot["stability"]["status"] == "unhealthy"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("health", None),
        ("stability", []),
        ("generated_at", "not-a-timestamp"),
        ("max_age_minutes", 0),
        ("source_revision", "ABC123"),
        ("source_dirty", "yes"),
    ],
)
def test_malformed_inputs_are_rejected(field: str, value: object) -> None:
    arguments = {
        "health": _health(),
        "stability": _stability(),
        "generated_at": "2026-08-07T20:00:00Z",
        "max_age_minutes": 30,
        "source_revision": "a" * 40,
        "source_dirty": False,
    }
    arguments[field] = value

    with pytest.raises((TypeError, ValueError)):
        PUBLIC_HEALTH.build_public_health_snapshot(**arguments)


@pytest.mark.parametrize(
    ("value", "category"),
    [
        (r"C:\Users\Fixture\secret.txt", "absolute path"),
        (r"\\server\share\secret.txt", "UNC path"),
        ("operator@example.test", "email address"),
        ("019fdc00-0ddc-7472-bdbd-55c6d5daa983", "identifier"),
        ("Bearer very-private-value", "credential word"),
        ("http://127.0.0.1:7778/health", "private network URL"),
        ("line\u0000break", "control character"),
    ],
)
def test_recursive_privacy_guard_names_category_without_echoing_value(
    value: str, category: str
) -> None:
    with pytest.raises(ValueError) as error:
        PUBLIC_HEALTH.assert_public_snapshot_safe({"nested": [{"value": value}]})

    assert category in str(error.value)
    assert value not in str(error.value)


def test_cli_writes_snapshot_atomically(tmp_path: Path) -> None:
    health_path = tmp_path / "health.json"
    stability_path = tmp_path / "stability.json"
    output_path = tmp_path / "nested" / "project-manager-health.json"
    health_path.write_text(json.dumps(_health()), encoding="utf-8")
    stability_path.write_text(json.dumps(_stability()), encoding="utf-8")

    result = PUBLIC_HEALTH.main(
        [
            "--health-input",
            str(health_path),
            "--stability-input",
            str(stability_path),
            "--output",
            str(output_path),
            "--generated-at",
            "2026-08-07T20:00:00Z",
            "--max-age-minutes",
            "30",
            "--source-revision",
            "a" * 40,
            "--source-dirty",
        ]
    )

    assert result == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["schemaVersion"] == 1
    assert list(output_path.parent.glob("*.tmp")) == []
