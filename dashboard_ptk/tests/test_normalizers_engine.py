"""Tests for deterministic agent output normalizers."""
from __future__ import annotations

import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.normalizers import NormalizerRegistry
from dashboard.engine.types import AgentRawResult


def test_keyword_research_normalizer_success() -> None:
    registry = NormalizerRegistry()
    raw = AgentRawResult(
        success=True,
        provider="kimi",
        output_text='''```json\n{"summary":"x","keyword_candidates":[{"keyword":"best coffee grinder","estimated_volume":500,"estimated_kd":22,"intent":"informational","opportunity_score":"high"}]}\n```''',
    )

    with tempfile.TemporaryDirectory() as tmp:
        result = registry.normalize(
            "keyword_research",
            raw,
            {"task_results_dir": tmp, "task_id": "COF-001", "artifact_name": "keywords"},
        )

        assert result.success
        assert result.payload is not None
        assert result.payload["keyword_candidates"][0]["keyword"] == "best coffee grinder"
        assert result.output_path is not None
        assert Path(result.output_path).exists()


def test_keyword_research_normalizer_failure() -> None:
    registry = NormalizerRegistry()
    raw = AgentRawResult(success=True, provider="kimi", output_text="not json")
    result = registry.normalize("keyword_research", raw, {})
    assert not result.success
    assert "parse" in (result.error or "").lower() or "missing" in (result.error or "").lower()


if __name__ == "__main__":
    test_keyword_research_normalizer_success()
    test_keyword_research_normalizer_failure()
    print("ok")
