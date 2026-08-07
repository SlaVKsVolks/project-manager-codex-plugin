#!/usr/bin/env python3
"""Generate the source-backed dataset consumed by the Project Manager roadmap site."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
ALLOWLIST_DESCRIPTION = [
    "README.md",
    "DEVELOPMENT_IMPROVEMENTS.md",
    "docs/**/*.md",
    "skills/project-manager/SKILL.md",
]
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
DATE_RE = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
LOCAL_PATH_RE = re.compile(r'''(?i)(?<![\w])(?:[A-Z]:[\\/][^\s`"'<>|]+|/(?:Users|home)/[^\s`"'<>|]+)''')


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"source path escapes repository root: {path}") from exc
    return relative.as_posix()


def _is_allowlisted(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    if normalized in {"README.md", "DEVELOPMENT_IMPROVEMENTS.md"}:
        return True
    if normalized == "skills/project-manager/SKILL.md":
        return True
    return normalized.startswith("docs/") and normalized.lower().endswith(".md")


def _document_category(relative_path: str) -> str:
    parts = relative_path.split("/")
    if parts[0] == "docs" and len(parts) > 1:
        if parts[1] in {"bugs", "decisions", "migration"}:
            return parts[1][:-1] if parts[1].endswith("s") else parts[1]
        if parts[1] == "superpowers" and len(parts) > 2:
            return parts[2][:-1] if parts[2].endswith("s") else parts[2]
        return "documentation"
    if relative_path == "skills/project-manager/SKILL.md":
        return "skill"
    return "project"


def _document_date(relative_path: str, text: str) -> str | None:
    match = DATE_RE.search(relative_path) or DATE_RE.search(text[:2000])
    return match.group(1) if match else None


def _document_id(relative_path: str) -> str:
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]
    return f"doc-{digest}"


def _sanitize_local_paths(text: str) -> str:
    """Redact machine-specific absolute paths while retaining document meaning."""

    return LOCAL_PATH_RE.sub("<LOCAL_PATH>", text)


def _read_document(path: Path, repo_root: Path) -> dict[str, Any]:
    relative_path = _relative_path(path, repo_root)
    if not _is_allowlisted(relative_path):
        raise ValueError(f"file is outside the roadmap site allowlist: {relative_path}")
    raw_text = path.read_text(encoding="utf-8-sig")
    if not raw_text.strip():
        raise ValueError(f"empty Markdown document: {relative_path}")
    text = _sanitize_local_paths(raw_text)

    headings = [
        {"level": len(match.group(1)), "text": match.group(2).strip()}
        for match in HEADING_RE.finditer(text)
    ]
    title = headings[0]["text"] if headings else Path(relative_path).stem.replace("-", " ").title()
    content_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "id": _document_id(relative_path),
        "title": title,
        "sourcePath": relative_path,
        "category": _document_category(relative_path),
        "date": _document_date(relative_path, text),
        "evidence": "repository",
        "headings": headings,
        "body": text,
        "wordCount": len(WORD_RE.findall(text)),
        "contentSha256": content_digest,
    }


def discover_documents(repo_root: Path) -> list[dict[str, Any]]:
    """Read the Markdown sources explicitly allowed by the site contract."""

    root = repo_root.resolve()
    candidates: set[Path] = set()
    for relative in ("README.md", "DEVELOPMENT_IMPROVEMENTS.md", "skills/project-manager/SKILL.md"):
        candidate = root / relative
        if candidate.is_file():
            candidates.add(candidate)
    docs_root = root / "docs"
    if docs_root.is_dir():
        candidates.update(path for path in docs_root.rglob("*.md") if path.is_file())

    documents = [_read_document(path, root) for path in sorted(candidates, key=lambda item: _relative_path(item, root))]
    return documents


def _git_value(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _resolve_manifest_sources(
    repo_root: Path,
    patterns: Iterable[str],
    documents_by_path: dict[str, dict[str, Any]],
) -> list[str]:
    root = repo_root.resolve()
    resolved_ids: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        if Path(pattern).is_absolute():
            raise ValueError(f"manifest source pattern must be relative: {pattern}")
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            relative_path = _relative_path(candidate, root)
            document = documents_by_path.get(relative_path)
            if document and document["id"] not in seen:
                resolved_ids.append(document["id"])
                seen.add(document["id"])
    return resolved_ids


def _attach_source_ids(
    records: Iterable[dict[str, Any]],
    repo_root: Path,
    documents_by_path: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    attached: list[dict[str, Any]] = []
    for record in records:
        copy = dict(record)
        copy["sourceIds"] = _resolve_manifest_sources(repo_root, record.get("sourcePatterns", []), documents_by_path)
        attached.append(copy)
    return attached


def _source_digest(documents: Iterable[dict[str, Any]]) -> str:
    digest_input = "\n".join(
        f"{document['sourcePath']}:{document['contentSha256']}" for document in documents
    ).encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()


def build_site_dataset(
    repo_root: Path,
    manifest_path: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the JSON-compatible dataset for the roadmap site."""

    root = repo_root.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = discover_documents(root)
    documents_by_path = {document["sourcePath"]: document for document in documents}
    capabilities = _attach_source_ids(manifest.get("capabilities", []), root, documents_by_path)
    roadmap = _attach_source_ids(manifest.get("roadmap", []), root, documents_by_path)
    revision = _git_value(root, "rev-parse", "HEAD") or "unknown"
    dirty = bool(_git_value(root, "status", "--porcelain"))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at or _utc_now(),
        "source": {
            "kind": "local",
            "repositoryPath": "project-manager",
            "revision": revision,
            "workingTreeDirty": dirty,
            "allowlist": ALLOWLIST_DESCRIPTION,
        },
        "generated": {
            "generator": "scripts/sync_project_manager_roadmap_site.py",
            "documentCount": len(documents),
            "sourceDigest": _source_digest(documents),
        },
        "documents": documents,
        "capabilities": capabilities,
        "roadmap": roadmap,
        "comparison": manifest.get("comparison", {}),
    }


def write_site_dataset(dataset: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _default_paths() -> tuple[Path, Path, Path]:
    repo_root = Path(__file__).resolve().parents[1]
    return (
        repo_root,
        repo_root / "site" / "content" / "site-manifest.json",
        repo_root / "site" / "src" / "data" / "project-manager.json",
    )


def main(argv: list[str] | None = None) -> int:
    default_root, default_manifest, default_output = _default_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=default_root)
    parser.add_argument("--manifest", type=Path, default=default_manifest)
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)

    try:
        dataset = build_site_dataset(args.repo_root, args.manifest, generated_at=args.generated_at)
        write_site_dataset(dataset, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"roadmap site sync failed: {exc}", file=sys.stderr)
        return 2

    print(f"synced {dataset['generated']['documentCount']} documents to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
