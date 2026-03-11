"""Validate dashboard launcher bootstraps local CLI packages."""
from __future__ import annotations

from pathlib import Path


def test_run_sh_bootstraps_local_cli_packages() -> None:
    run_sh = Path(__file__).resolve().parents[1] / "run.sh"
    content = run_sh.read_text()

    assert "packages/automation-cli" in content
    assert "packages/seo-cli" in content
    assert "packages/seo-content-cli" in content
    assert "pip install -q -e" in content
    assert "dashboard_oss" not in content
    assert "export PYTHONPATH=" in content
    assert ".venv/bin/automation-cli" in content
    assert ".venv/bin/seo-cli" in content
    assert ".venv/bin/seo-content-cli" in content
    assert ".venv/bin/pageseeds" in content
    assert ".venv/bin/task-dashboard" in content


if __name__ == "__main__":
    test_run_sh_bootstraps_local_cli_packages()
    print("ok")
