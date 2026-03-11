"""Tests for scheduler policy loading with defaults."""
from __future__ import annotations

import json
import inspect
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine import SchedulerConfig, SchedulerRule, OrchestrationPolicy, PolicyEngine


class TestSchedulerPolicyDefaults:
    """Test scheduler section in policy loads with correct defaults."""

    def test_scheduler_config_default_creation(self):
        """SchedulerConfig.default() returns config with default rules."""
        config = SchedulerConfig.default()
        
        assert config.enabled is True
        assert config.timezone == ""
        assert config.max_task_creations_per_cycle == 3
        assert config.quiet_hours_start == "22:00"
        assert config.quiet_hours_end == "07:00"
        assert config.overdue_warn_after_hours == 48
        assert config.overdue_error_after_hours == 168
        
        # Check default rules
        rule_ids = {r.id for r in config.rules}
        expected_rules = {
            "collect_gsc_weekly",
            "collect_posthog_weekly",
            "reddit_opportunity_search",
            "research_keywords",
            "indexing_diagnostics",
        }
        assert rule_ids == expected_rules
        reddit_rule = next(r for r in config.rules if r.id == "reddit_opportunity_search")
        assert reddit_rule.mode == "create_task"
        assert reddit_rule.cadence_hours == 48

    def test_scheduler_config_from_dict_with_none(self):
        """SchedulerConfig.from_dict(None) returns default config."""
        config = SchedulerConfig.from_dict(None)
        
        assert config.enabled is True
        assert len(config.rules) == 5  # Default rules

    def test_scheduler_config_from_dict_with_empty(self):
        """SchedulerConfig.from_dict({}) returns config with defaults."""
        config = SchedulerConfig.from_dict({})
        
        assert config.enabled is True
        assert config.max_task_creations_per_cycle == 3

    def test_scheduler_config_from_dict_partial(self):
        """SchedulerConfig.from_dict loads partial config with defaults for missing fields."""
        data = {
            "enabled": False,
            "timezone": "Pacific/Auckland",
            "rules": [
                {"id": "custom_rule", "task_type": "custom_task", "mode": "create_task", "cadence_hours": 24}
            ]
        }
        config = SchedulerConfig.from_dict(data)
        
        assert config.enabled is False
        assert config.timezone == "Pacific/Auckland"
        # Missing fields use defaults
        assert config.max_task_creations_per_cycle == 3
        assert config.quiet_hours_start == "22:00"
        # Rules are loaded from data, not defaults
        assert len(config.rules) == 1
        assert config.rules[0].id == "custom_rule"

    def test_scheduler_config_roundtrip(self):
        """SchedulerConfig can be serialized and deserialized."""
        original = SchedulerConfig.default()
        data = original.to_dict()
        restored = SchedulerConfig.from_dict(data)
        
        assert restored.enabled == original.enabled
        assert restored.timezone == original.timezone
        assert restored.max_task_creations_per_cycle == original.max_task_creations_per_cycle
        assert len(restored.rules) == len(original.rules)

    def test_orchestration_policy_with_scheduler(self):
        """OrchestrationPolicy includes scheduler config."""
        policy = OrchestrationPolicy()
        
        assert policy.scheduler is not None
        assert policy.scheduler.enabled is True
        assert len(policy.scheduler.rules) == 5

    def test_orchestration_policy_to_dict_includes_scheduler(self):
        """OrchestrationPolicy.to_dict() includes scheduler section."""
        policy = OrchestrationPolicy()
        data = policy.to_dict()
        
        assert "scheduler" in data
        assert data["scheduler"]["enabled"] is True
        assert "rules" in data["scheduler"]

    def test_policy_engine_loads_scheduler_section(self):
        """PolicyEngine loads scheduler section from policy file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            policy_path = repo_root / ".github" / "automation" / "orchestrator_policy.json"
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write policy with custom scheduler config
            custom_policy = {
                "schema_version": 1,
                "max_steps_per_run": 10,
                "scheduler": {
                    "enabled": True,
                    "timezone": "America/New_York",
                    "max_task_creations_per_cycle": 5,
                    "rules": [
                        {"id": "test_rule", "task_type": "test_task", "mode": "create_task", "cadence_hours": 24}
                    ]
                }
            }
            policy_path.write_text(json.dumps(custom_policy, indent=2))
            
            engine = PolicyEngine(repo_root)
            policy = engine.load_or_create()
            
            assert policy.scheduler.enabled is True
            assert policy.scheduler.timezone == "America/New_York"
            assert policy.scheduler.max_task_creations_per_cycle == 5
            assert len(policy.scheduler.rules) == 1
            assert policy.scheduler.rules[0].id == "test_rule"

    def test_policy_engine_backward_compatibility_no_scheduler(self):
        """PolicyEngine works with policy files that don't have scheduler section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            policy_path = repo_root / ".github" / "automation" / "orchestrator_policy.json"
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write policy WITHOUT scheduler section
            old_policy = {
                "schema_version": 1,
                "max_steps_per_run": 8,
                "blocked_task_types": ["research_keywords"]
            }
            policy_path.write_text(json.dumps(old_policy, indent=2))
            
            engine = PolicyEngine(repo_root)
            policy = engine.load_or_create()
            
            # Should use default scheduler config
            assert policy.scheduler is not None
            assert policy.scheduler.enabled is True
            assert len(policy.scheduler.rules) == 5  # Default rules

    def test_scheduler_rule_from_dict(self):
        """SchedulerRule.from_dict correctly parses rule data."""
        data = {
            "id": "test_rule",
            "task_type": "collect_gsc",
            "mode": "create_task",
            "cadence_hours": 168,
            "priority": "high",
            "phase": "collection",
            "enabled": False
        }
        rule = SchedulerRule.from_dict(data)
        
        assert rule.id == "test_rule"
        assert rule.task_type == "collect_gsc"
        assert rule.mode == "create_task"
        assert rule.cadence_hours == 168
        assert rule.priority == "high"
        assert rule.phase == "collection"
        assert rule.enabled is False

    def test_scheduler_rule_defaults(self):
        """SchedulerRule.from_dict uses defaults for missing fields."""
        data = {"id": "minimal_rule", "task_type": "test_task", "mode": "reminder_only", "cadence_hours": 72}
        rule = SchedulerRule.from_dict(data)
        
        assert rule.id == "minimal_rule"
        assert rule.task_type == "test_task"
        assert rule.mode == "reminder_only"
        assert rule.cadence_hours == 72
        # Defaults
        assert rule.priority == "medium"
        assert rule.phase == "collection"
        assert rule.enabled is True


def _run_all_tests() -> None:
    module = sys.modules[__name__]
    ran = 0
    for _, cls in inspect.getmembers(module, inspect.isclass):
        if not cls.__name__.startswith("Test"):
            continue
        instance = cls()
        for name, _ in inspect.getmembers(cls, inspect.isfunction):
            if not name.startswith("test_"):
                continue
            getattr(instance, name)()
            ran += 1
    print(f"ok ({ran} tests)")


if __name__ == "__main__":
    _run_all_tests()
