"""Tests for macOS scheduler daemon setup/verification service."""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.scheduler_system_service import SchedulerSystemService


class TestSchedulerSystemService:
    def test_get_status_non_macos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            service = SchedulerSystemService(
                automation_root=root,
                launch_agents_dir=root / "LaunchAgents",
            )

            with patch("dashboard.engine.scheduler_system_service.sys.platform", "linux"):
                status = service.get_status()

            assert status.platform == "linux"
            assert status.supported is False

    def test_get_status_parses_launchd_and_status_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            launch_agents = root / "LaunchAgents"
            launch_agents.mkdir(parents=True, exist_ok=True)
            service = SchedulerSystemService(
                automation_root=root,
                launch_agents_dir=launch_agents,
            )

            service.cycle_plist.write_text("cycle")
            service.health_plist.write_text("health")
            status_file = root / "output" / "monitoring" / "seo_scheduler" / "status.json"
            status_file.parent.mkdir(parents=True, exist_ok=True)
            status_file.write_text(
                '{"last_result":"ok","last_finished_at":"2026-03-10T12:00:00","last_error":null}'
            )

            with patch("dashboard.engine.scheduler_system_service.sys.platform", "darwin"), \
                 patch("dashboard.engine.scheduler_system_service.shutil.which", return_value="/bin/launchctl"), \
                 patch.object(
                     service,
                     "_run_command",
                     return_value=(
                         True,
                         "com.pageseeds.scheduler.cycle\ncom.pageseeds.scheduler.health\n",
                         "",
                     ),
                 ):
                status = service.get_status()

            assert status.supported is True
            assert status.launchctl_available is True
            assert status.cycle_plist_exists is True
            assert status.health_plist_exists is True
            assert status.cycle_loaded is True
            assert status.health_loaded is True
            assert status.status_file_exists is True
            assert status.last_result == "ok"
            assert status.last_finished_at == "2026-03-10T12:00:00"

    def test_install_or_repair_non_macos_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            service = SchedulerSystemService(
                automation_root=root,
                launch_agents_dir=root / "LaunchAgents",
            )

            with patch("dashboard.engine.scheduler_system_service.sys.platform", "linux"):
                success, messages = service.install_or_repair()

            assert success is False
            assert messages

    def test_install_or_repair_writes_plists_and_runs_launchctl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            launch_agents = root / "LaunchAgents"
            service = SchedulerSystemService(
                automation_root=root,
                launch_agents_dir=launch_agents,
            )

            calls = []

            def _fake_run(cmd, timeout=30):
                calls.append(cmd)
                return True, "", ""

            with patch("dashboard.engine.scheduler_system_service.sys.platform", "darwin"), \
                 patch("dashboard.engine.scheduler_system_service.shutil.which", return_value="/bin/launchctl"), \
                 patch.object(service, "_run_command", side_effect=_fake_run):
                success, messages = service.install_or_repair()

            assert success is True
            assert service.cycle_plist.exists()
            assert service.health_plist.exists()
            assert "com.pageseeds.scheduler.cycle" in service.cycle_plist.read_text()
            assert "com.pageseeds.scheduler.health" in service.health_plist.read_text()
            assert any("bootstrap" in " ".join(c) for c in calls)
            assert any("kickstart" in " ".join(c) for c in calls)
            assert messages


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
