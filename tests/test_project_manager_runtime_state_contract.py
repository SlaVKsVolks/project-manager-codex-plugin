import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = (
    "docs/project-manager/worker-registry.json",
    "docs/project-manager/manager-ledger.jsonl",
    "docs/project-manager/transaction-journal.jsonl",
)


def test_runtime_state_paths_are_ignored_by_git() -> None:
    for runtime_path in RUNTIME_PATHS:
        completed = subprocess.run(
            ["git", "check-ignore", "--no-index", runtime_path],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == runtime_path
