"""Tests for orchestration policy loading and decisions."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.policy import OrchestrationPolicy, PolicyContext, PolicyEngine


class _Task:
    def __init__(self, task_type: str):
        self.type = task_type


def test_policy_load_or_create_persists_default_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)

        engine = PolicyEngine(repo_root)
        policy = engine.load_or_create()

        assert isinstance(policy, OrchestrationPolicy)
        assert engine.policy_path.exists()
        payload = engine.policy_path.read_text()
        assert "max_steps_per_run" in payload


def test_policy_blocks_reddit_when_auth_not_ready() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        engine = PolicyEngine(repo_root)

        policy = OrchestrationPolicy(reddit_autopost_enabled=True)
        context = PolicyContext(
            reddit_posts_last_day=0,
            reddit_posts_last_week=0,
            reddit_auth_ready=False,
            reddit_auth_error="invalid_grant",
        )
        decision = engine.evaluate(_Task("reddit_reply"), "batchable", policy, context)
        assert not decision.allowed
        assert "auth not ready" in decision.reason


def test_policy_blocks_daily_limit() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        engine = PolicyEngine(repo_root)

        policy = OrchestrationPolicy(
            reddit_autopost_enabled=True,
            reddit_max_posts_per_day=2,
            reddit_max_posts_per_week=10,
        )
        context = PolicyContext(
            reddit_posts_last_day=2,
            reddit_posts_last_week=2,
            reddit_auth_ready=True,
        )
        decision = engine.evaluate(_Task("reddit_reply"), "batchable", policy, context)
        assert not decision.allowed
        assert "daily limit" in decision.reason


if __name__ == "__main__":
    test_policy_load_or_create_persists_default_file()
    test_policy_blocks_reddit_when_auth_not_ready()
    test_policy_blocks_daily_limit()
    print("ok")
