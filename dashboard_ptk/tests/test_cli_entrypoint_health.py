"""Smoke checks for dashboard CLI module bootstrap behavior."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_dashboard_python_can_import_local_cli_modules_via_pythonpath() -> None:
    root = Path(__file__).resolve().parents[1]
    repo_root = root.parent
    python_bin = root / ".venv" / "bin" / "python3"
    assert python_bin.exists(), f"Expected dashboard venv python: {python_bin}"

    pythonpath = os.pathsep.join(
        [
            str(repo_root / "packages" / "automation-cli" / "src"),
            str(repo_root / "packages" / "seo-cli" / "src"),
            str(repo_root / "packages" / "seo-content-cli" / "src"),
        ]
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = pythonpath + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [
            str(python_bin),
            "-c",
            "import automation_mcp.cli, seo_mcp.cli, seo_content_mcp.cli; print('ok')",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )

    assert result.returncode == 0, f"CLI module import failed: {result.stderr or result.stdout}"


if __name__ == "__main__":
    test_dashboard_python_can_import_local_cli_modules_via_pythonpath()
    print("ok")
