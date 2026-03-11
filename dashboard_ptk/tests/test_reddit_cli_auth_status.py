"""Regression checks for Reddit auth-status CLI support."""
from __future__ import annotations

from pathlib import Path


def test_automation_cli_has_reddit_auth_status_command() -> None:
    cli_py = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "automation-cli"
        / "src"
        / "automation_mcp"
        / "cli.py"
    )
    content = cli_py.read_text()
    assert "def _reddit_auth_status(" in content
    assert 'reddit_sub.add_parser("auth-status"' in content


if __name__ == "__main__":
    test_automation_cli_has_reddit_auth_status_command()
    print("ok")
