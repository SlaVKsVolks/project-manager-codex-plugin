import importlib.util
import json
from pathlib import Path

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = PLUGIN_ROOT / "scripts" / "sync_project_manager_roadmap_site.py"
MANIFEST_PATH = PLUGIN_ROOT / "site" / "content" / "site-manifest.json"
SPEC = importlib.util.spec_from_file_location("project_manager_roadmap_site_sync", SYNC_PATH)
assert SPEC is not None
assert SPEC.loader is not None
SYNC_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC_MODULE)


def _fixture_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "skills" / "project-manager").mkdir(parents=True)
    (tmp_path / "README.md").write_text("# Fixture README\n\nLocal project overview.\n", encoding="utf-8")
    (tmp_path / "DEVELOPMENT_IMPROVEMENTS.md").write_text(
        "# Improvements\n\nA fixture improvement.\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "decision.md").write_text(
        "# Fixture decision\n\nA decision body at C:\\Users\\Fixture\\Secrets\\thing.ps1.\n", encoding="utf-8"
    )
    (tmp_path / "skills" / "project-manager" / "SKILL.md").write_text(
        "# Fixture skill\n\nA skill body.\n", encoding="utf-8"
    )
    (tmp_path / ".env").write_text("SECRET=do-not-export\n", encoding="utf-8")
    return tmp_path


def test_build_site_dataset_discovers_only_allowlisted_markdown(tmp_path: Path):
    repo = _fixture_repo(tmp_path)

    dataset = SYNC_MODULE.build_site_dataset(repo, MANIFEST_PATH, generated_at="2026-08-07T12:00:00Z")

    assert dataset["schemaVersion"] == 1
    assert dataset["generatedAt"] == "2026-08-07T12:00:00Z"
    assert dataset["source"]["kind"] == "local"
    assert dataset["source"]["repositoryPath"] == "project-manager"
    assert len(dataset["documents"]) == 4
    assert {document["sourcePath"] for document in dataset["documents"]} == {
        "README.md",
        "DEVELOPMENT_IMPROVEMENTS.md",
        "docs/decision.md",
        "skills/project-manager/SKILL.md",
    }
    assert all(document["body"].strip() for document in dataset["documents"])
    decision = next(document for document in dataset["documents"] if document["sourcePath"] == "docs/decision.md")
    assert "<LOCAL_PATH>" in decision["body"]
    assert "C:\\Users\\Fixture" not in decision["body"]
    serialized = json.dumps(dataset)
    assert ".env" not in serialized
    assert "do-not-export" not in serialized


def test_build_site_dataset_preserves_manifest_records_and_stable_document_ids(tmp_path: Path):
    repo = _fixture_repo(tmp_path)

    first = SYNC_MODULE.build_site_dataset(repo, MANIFEST_PATH, generated_at="2026-08-07T12:00:00Z")
    second = SYNC_MODULE.build_site_dataset(repo, MANIFEST_PATH, generated_at="2026-08-07T12:00:00Z")

    assert {item["id"] for item in first["capabilities"]} == {
        "health-gates",
        "lane-coordination",
        "recovery-rebind",
        "model-transport",
        "objective-runner",
        "release-install",
        "cross-project-audit",
    }
    assert {item["id"] for item in first["roadmap"]} == {
        "foundation-v03",
        "gates-july",
        "recovery-july",
        "objective-runner-august",
        "canonical-health-august",
        "hosted-roadmap-surface",
    }
    assert [document["id"] for document in first["documents"]] == [
        document["id"] for document in second["documents"]
    ]
    assert first["generated"]["documentCount"] == 4


def test_empty_allowlisted_markdown_fails_closed(tmp_path: Path):
    repo = _fixture_repo(tmp_path)
    (repo / "docs" / "empty.md").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty Markdown document"):
        SYNC_MODULE.build_site_dataset(repo, MANIFEST_PATH, generated_at="2026-08-07T12:00:00Z")


def test_write_site_dataset_creates_utf8_json(tmp_path: Path):
    output = tmp_path / "nested" / "project-manager.json"
    dataset = {"schemaVersion": 1, "documents": [], "roadmap": [], "capabilities": []}

    SYNC_MODULE.write_site_dataset(dataset, output)

    assert json.loads(output.read_text(encoding="utf-8")) == dataset
