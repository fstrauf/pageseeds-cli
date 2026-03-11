"""Tests for internal workflow bundle/runtime contract wiring."""
from __future__ import annotations

import os
import sys
import importlib.util

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.workflow_bundle import legacy_seo_reddit_bundle
from dashboard.engine.runtime_config import RuntimeConfig


def test_legacy_bundle_exposes_expected_defaults() -> None:
    if importlib.util.find_spec("prompt_toolkit") is None:
        return
    bundle = legacy_seo_reddit_bundle()
    assert bundle.name == "seo_reddit"
    assert "automation-cli" in bundle.required_clis
    assert bundle.runner_builder is not None
    assert bundle.handler_builder is not None
    assert bundle.autonomy_mode_map.get("collect_gsc") == "automatic"


def test_runtime_config_accepts_required_clis() -> None:
    cfg = RuntimeConfig(required_clis=("cli-a", "cli-b"))
    assert cfg.required_clis == ("cli-a", "cli-b")


if __name__ == "__main__":
    test_legacy_bundle_exposes_expected_defaults()
    test_runtime_config_accepts_required_clis()
    print("ok")
