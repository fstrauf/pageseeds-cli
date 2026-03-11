"""Regression tests for safe temporary-file handling in Kimi adapter."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.agent_runtime import KimiAdapter
from dashboard.engine.types import PromptSpec


def test_kimi_adapter_captures_output_without_mktemp_usage() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "dashboard"
        / "engine"
        / "agent_runtime.py"
    ).read_text()
    assert "tempfile.mktemp(" not in source

    def fake_run(_cmd, stdout=None, **_kwargs):
        if stdout is not None:
            stdout.write("hello from kimi\n")
        return SimpleNamespace(returncode=0, stderr="")

    with patch("dashboard.engine.agent_runtime.shutil.which", return_value="/usr/bin/kimi"), patch(
        "dashboard.engine.agent_runtime.subprocess.run", side_effect=fake_run
    ):
        result = KimiAdapter().run(PromptSpec(text="test"), cwd=Path.cwd())

    assert result.success is True
    assert "hello from kimi" in result.output_text


if __name__ == "__main__":
    test_kimi_adapter_captures_output_without_mktemp_usage()
    print("ok")

