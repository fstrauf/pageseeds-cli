"""System-level scheduler setup and verification for macOS launchd."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SchedulerDaemonStatus:
    """Current system daemon status for scheduler launch agents."""

    platform: str
    supported: bool
    launchctl_available: bool
    cycle_plist_exists: bool
    health_plist_exists: bool
    cycle_loaded: bool
    health_loaded: bool
    status_file_exists: bool
    last_result: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None


class SchedulerSystemService:
    """Installs and verifies the recurring scheduler daemon jobs on macOS."""

    CYCLE_LABEL = "com.pageseeds.scheduler.cycle"
    HEALTH_LABEL = "com.pageseeds.scheduler.health"

    def __init__(
        self,
        automation_root: Path | None = None,
        launch_agents_dir: Path | None = None,
    ):
        if automation_root is None:
            automation_root = Path(__file__).resolve().parents[3]

        self.automation_root = Path(automation_root).expanduser().resolve()
        self.launch_agents_dir = (
            Path(launch_agents_dir).expanduser().resolve()
            if launch_agents_dir is not None
            else (Path.home() / "Library" / "LaunchAgents")
        )

        self.output_dir = self.automation_root / "output"
        self.monitoring_dir = self.output_dir / "monitoring" / "seo_scheduler"
        self.dashboard_dir = self.automation_root / "dashboard_ptk"

        self.cycle_plist = self.launch_agents_dir / f"{self.CYCLE_LABEL}.plist"
        self.health_plist = self.launch_agents_dir / f"{self.HEALTH_LABEL}.plist"

    def get_status(self) -> SchedulerDaemonStatus:
        """Read current scheduler daemon status from launchd + monitoring files."""
        supported = sys.platform == "darwin"
        launchctl_available = shutil.which("launchctl") is not None

        status = SchedulerDaemonStatus(
            platform=sys.platform,
            supported=supported,
            launchctl_available=launchctl_available,
            cycle_plist_exists=self.cycle_plist.exists(),
            health_plist_exists=self.health_plist.exists(),
            cycle_loaded=False,
            health_loaded=False,
            status_file_exists=False,
        )

        if supported and launchctl_available:
            ok, stdout, _stderr = self._run_command(["launchctl", "list"], timeout=20)
            if ok:
                status.cycle_loaded = self.CYCLE_LABEL in stdout
                status.health_loaded = self.HEALTH_LABEL in stdout

        status_file = self.monitoring_dir / "status.json"
        if status_file.exists():
            status.status_file_exists = True
            try:
                payload = json.loads(status_file.read_text())
                status.last_result = payload.get("last_result")
                status.last_finished_at = payload.get("last_finished_at")
                status.last_error = payload.get("last_error")
            except Exception:
                pass

        return status

    def install_or_repair(
        self,
        cycle_interval_seconds: int = 1800,
        health_interval_seconds: int = 900,
    ) -> tuple[bool, list[str]]:
        """Install or repair launchd agents for scheduler cycle + health jobs."""
        messages: list[str] = []

        if sys.platform != "darwin":
            return False, ["Scheduler daemon setup is only supported on macOS."]

        if not shutil.which("launchctl"):
            return False, ["launchctl not found on this system."]

        self.launch_agents_dir.mkdir(parents=True, exist_ok=True)
        self.monitoring_dir.mkdir(parents=True, exist_ok=True)

        cycle_cmd = (
            f'cd "{self.automation_root}" && '
            "cd dashboard_ptk && python3 main.py --scheduled-cycle"
        )
        health_cmd = (
            f'cd "{self.automation_root}" && '
            "python3 scripts/scheduler_status.py"
        )

        self.cycle_plist.write_text(
            self._render_launchd_plist(
                label=self.CYCLE_LABEL,
                shell_command=cycle_cmd,
                start_interval=max(60, int(cycle_interval_seconds)),
                stdout_path="/tmp/com.pageseeds.scheduler.cycle.out.log",
                stderr_path="/tmp/com.pageseeds.scheduler.cycle.err.log",
            )
        )
        self.health_plist.write_text(
            self._render_launchd_plist(
                label=self.HEALTH_LABEL,
                shell_command=health_cmd,
                start_interval=max(60, int(health_interval_seconds)),
                stdout_path="/tmp/com.pageseeds.scheduler.health.out.log",
                stderr_path="/tmp/com.pageseeds.scheduler.health.err.log",
            )
        )

        uid = str(Path.home().stat().st_uid)
        domain = f"gui/{uid}"

        # Best effort unload any existing jobs.
        self._run_command(["launchctl", "bootout", f"{domain}/{self.CYCLE_LABEL}"], timeout=20)
        self._run_command(["launchctl", "bootout", f"{domain}/{self.HEALTH_LABEL}"], timeout=20)

        commands = [
            (["launchctl", "bootstrap", domain, str(self.cycle_plist)], "cycle bootstrap"),
            (["launchctl", "bootstrap", domain, str(self.health_plist)], "health bootstrap"),
            (["launchctl", "enable", f"{domain}/{self.CYCLE_LABEL}"], "cycle enable"),
            (["launchctl", "enable", f"{domain}/{self.HEALTH_LABEL}"], "health enable"),
            (["launchctl", "kickstart", "-k", f"{domain}/{self.CYCLE_LABEL}"], "cycle kickstart"),
            (["launchctl", "kickstart", "-k", f"{domain}/{self.HEALTH_LABEL}"], "health kickstart"),
        ]

        success = True
        for cmd, label in commands:
            ok, _stdout, stderr = self._run_command(cmd, timeout=30)
            if ok:
                messages.append(f"ok: {label}")
            else:
                success = False
                err = stderr.strip() or "unknown error"
                messages.append(f"error: {label}: {err}")

        return success, messages

    def _run_command(self, cmd: list[str], timeout: int = 30) -> tuple[bool, str, str]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout or "", result.stderr or ""
        except Exception as exc:
            return False, "", str(exc)

    def _render_launchd_plist(
        self,
        label: str,
        shell_command: str,
        start_interval: int,
        stdout_path: str,
        stderr_path: str,
    ) -> str:
        cmd = self._xml_escape(shell_command)
        return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
  <dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/zsh</string>
      <string>-lc</string>
      <string>{cmd}</string>
    </array>
    <key>StartInterval</key>
    <integer>{int(start_interval)}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{stdout_path}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_path}</string>
  </dict>
</plist>
"""

    @staticmethod
    def _xml_escape(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
