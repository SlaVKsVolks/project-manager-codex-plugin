#!/usr/bin/env python3
"""Project compact manager health into a privacy-safe site snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


HEALTH_STATUSES = {"healthy", "degraded", "unhealthy", "unknown"}
COORDINATION_GATES = {"allow", "block", "block_host_state", "unknown"}
STABILITY_STATUSES = {"healthy", "degraded", "unhealthy", "unknown"}
CALLABILITY_STATUSES = {"callable", "not_callable", "unknown"}
CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,79}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,95}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")

EVIDENCE_BOUNDARY = (
    "Snapshot evidence is not proof of this viewer's current loaded-turn binding."
)

_WINDOWS_PATH_RE = re.compile(r"(?i)(?:^|[\s\"'(=])[a-z]:[\\/]")
_HOME_FRAGMENT_RE = re.compile(r"(?i)(?:^|[\\/])(?:users|home)[\\/]")
_UNC_PATH_RE = re.compile(r"^\\\\[^\\]+\\[^\\]+")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_IDENTIFIER_RE = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)
_CREDENTIAL_WORD_RE = re.compile(
    r"(?i)\b(?:bearer|token|secret|password|passwd|api[_-]?key|credential)\b"
)
_PRIVATE_URL_RE = re.compile(
    r"(?i)https?://(?:localhost|127(?:\.\d{1,3}){3}|10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|"
    r"[^/\s]+\.(?:internal|local))(?:[:/]|$)"
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field} must be an object")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{field} must be a boolean")
    return value


def _require_non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _require_positive_int(value: Any, field: str) -> int:
    result = _require_non_negative_int(value, field)
    if result == 0:
        raise ValueError(f"{field} must be positive")
    return result


def _require_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an RFC3339 timestamp")
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return normalized


def _normalize_health_status(value: Any) -> str:
    if value in HEALTH_STATUSES:
        return str(value)
    if value in {"reload_required", "repair_required", "blocked", "failed", "error"}:
        return "unhealthy"
    raise ValueError("overallStatus is invalid")


def _normalize_coordination_gate(value: Any) -> str:
    if value in COORDINATION_GATES:
        return str(value)
    if isinstance(value, str) and value.startswith("block_"):
        return "block"
    raise ValueError("coordinationGate is invalid")


def _normalize_stability_status(value: Any) -> str:
    if value in STABILITY_STATUSES:
        return str(value)
    if value in {"stable", "ok", "passed", "pass"}:
        return "healthy"
    if value in {"warning", "warn"}:
        return "degraded"
    if value in {"unstable", "failed", "error", "blocked"}:
        return "unhealthy"
    raise ValueError("auditStatus is invalid")


def _callability(value: Any, field: str) -> str:
    if value is None:
        return "unknown"
    return "callable" if _require_bool(value, field) else "not_callable"


def _safe_version(health: dict[str, Any], stability: dict[str, Any]) -> str:
    cache = health.get("cacheMirrorHealth")
    if not isinstance(cache, dict):
        cache = {}
    value = stability.get("pluginVersion") or cache.get("resolvedPluginVersion") or "unknown"
    if not isinstance(value, str) or VERSION_RE.fullmatch(value) is None:
        raise ValueError("pluginVersion is invalid")
    return value


def _finding_codes(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"{field} must be an array")
    codes: set[str] = set()
    for item in value:
        if not isinstance(item, str) or CODE_RE.fullmatch(item) is None:
            raise ValueError(f"{field} contains an invalid finding code")
        codes.add(item)
    return sorted(codes)


def _privacy_category(value: str) -> str | None:
    if _CONTROL_RE.search(value):
        return "control character"
    if _UNC_PATH_RE.search(value):
        return "UNC path"
    if _WINDOWS_PATH_RE.search(value) or _HOME_FRAGMENT_RE.search(value):
        return "absolute path"
    if _EMAIL_RE.search(value):
        return "email address"
    if _IDENTIFIER_RE.search(value):
        return "identifier"
    if _CREDENTIAL_WORD_RE.search(value):
        return "credential word"
    if _PRIVATE_URL_RE.search(value):
        return "private network URL"
    return None


def assert_public_snapshot_safe(snapshot: dict[str, Any]) -> None:
    """Reject privacy-sensitive string values without echoing those values."""

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                visit(key)
                visit(nested)
            return
        if isinstance(value, list):
            for nested in value:
                visit(nested)
            return
        if isinstance(value, str):
            category = _privacy_category(value)
            if category is not None:
                raise ValueError(f"public snapshot contains forbidden {category}")

    _require_dict(snapshot, "snapshot")
    visit(snapshot)


def build_public_health_snapshot(
    health: dict[str, Any],
    stability: dict[str, Any],
    *,
    generated_at: str,
    max_age_minutes: int,
    source_revision: str,
    source_dirty: bool,
) -> dict[str, Any]:
    """Create an allowlist-only health snapshot from compact wrapper results."""

    health = _require_dict(health, "health")
    stability = _require_dict(stability, "stability")
    generated_at = _require_timestamp(generated_at, "generated_at")
    max_age_minutes = _require_positive_int(max_age_minutes, "max_age_minutes")
    if source_revision != "unknown" and (
        not isinstance(source_revision, str) or REVISION_RE.fullmatch(source_revision) is None
    ):
        raise ValueError("source_revision must be unknown or a lowercase forty-character revision")
    source_dirty = _require_bool(source_dirty, "source_dirty")

    blocking_codes = _finding_codes(health.get("blockingFindingCodes"), "blockingFindingCodes")
    non_blocking_codes = _finding_codes(
        health.get("nonBlockingFindingCodes"), "nonBlockingFindingCodes"
    )
    all_codes = _finding_codes(health.get("healthFindingCodes"), "healthFindingCodes")
    advisory_codes = sorted(set(all_codes) - set(blocking_codes) - set(non_blocking_codes))
    failed_codes = _finding_codes(
        stability.get("failedInvariantCodes"), "failedInvariantCodes"
    )

    snapshot: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "maxAgeMinutes": max_age_minutes,
        "source": {"revision": source_revision, "dirty": source_dirty},
        "environment": {
            "pluginVersion": _safe_version(health, stability),
            "overallStatus": _normalize_health_status(health.get("overallStatus")),
            "coordinationGate": _normalize_coordination_gate(health.get("coordinationGate")),
            "heartbeatReady": _require_bool(health.get("heartbeatReady"), "heartbeatReady"),
            "freshThreadCallability": _callability(
                health.get("freshThreadLikelyCallable"), "freshThreadLikelyCallable"
            ),
            "sameLoadedTurnCallability": _callability(
                health.get("sameLoadedTurnLikelyCallable"), "sameLoadedTurnLikelyCallable"
            ),
            "blockingFindingCodes": blocking_codes,
            "advisoryFindingCodes": advisory_codes,
            "nonBlockingFindingCodes": non_blocking_codes,
        },
        "stability": {
            "status": _normalize_stability_status(stability.get("auditStatus")),
            "safeForManagerAutomation": _require_bool(
                stability.get("safeForManagerAutomation"), "safeForManagerAutomation"
            ),
            "invariantCount": _require_non_negative_int(
                stability.get("invariantCount"), "invariantCount"
            ),
            "failedInvariantCount": _require_non_negative_int(
                stability.get("failedInvariantCount"), "failedInvariantCount"
            ),
            "failedInvariantCodes": failed_codes,
        },
        "evidenceBoundary": EVIDENCE_BOUNDARY,
    }
    if snapshot["stability"]["failedInvariantCount"] != len(failed_codes):
        raise ValueError("failedInvariantCount does not match failedInvariantCodes")

    digest_payload = {
        key: value for key, value in snapshot.items() if key not in {"generatedAt", "contentDigest"}
    }
    canonical = json.dumps(
        digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    snapshot["contentDigest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert_public_snapshot_safe(snapshot)
    return snapshot


def write_snapshot_atomic(snapshot: dict[str, Any], output_path: Path) -> None:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health-input", required=True, type=Path)
    parser.add_argument("--stability-input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--max-age-minutes", required=True, type=int)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--source-dirty", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    health = json.loads(args.health_input.read_text(encoding="utf-8-sig"))
    stability = json.loads(args.stability_input.read_text(encoding="utf-8-sig"))
    snapshot = build_public_health_snapshot(
        health,
        stability,
        generated_at=args.generated_at,
        max_age_minutes=args.max_age_minutes,
        source_revision=args.source_revision,
        source_dirty=args.source_dirty,
    )
    write_snapshot_atomic(snapshot, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
