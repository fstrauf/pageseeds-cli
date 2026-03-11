"""Tests for centralized ToolRegistry behavior."""
from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.tool_registry import ToolRegistry
from dashboard.engine.types import ExecutionContext


def test_run_command_success() -> None:
    registry = ToolRegistry()
    ctx = ExecutionContext(repo_root=Path.cwd())
    result = registry.run_command([sys.executable, "-c", "print('ok')"], context=ctx, timeout=10)
    assert result.success
    assert "ok" in result.stdout


def test_run_command_missing_executable() -> None:
    registry = ToolRegistry()
    ctx = ExecutionContext(repo_root=Path.cwd())
    result = registry.run_command(["definitely-not-a-real-tool-xyz"], context=ctx, timeout=5)
    assert not result.success
    assert result.error_type == "not_found"


def test_legacy_namespace_normalization() -> None:
    registry = ToolRegistry()
    normalized = registry._normalize_legacy_command(["seo", "gsc-indexing-report", "--help"])
    assert normalized[0] == "automation-cli"


if __name__ == "__main__":
    test_run_command_success()
    test_run_command_missing_executable()
    test_legacy_namespace_normalization()
    print("ok")
