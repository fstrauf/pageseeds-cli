"""Run ledger persistence for orchestrator progress and summaries."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class OrchestrationLedger:
    """Persists orchestrator events and summaries under .github/automation."""

    def __init__(self, automation_dir: Path):
        self.automation_dir = Path(automation_dir).expanduser().resolve()
        self.runs_dir = self.automation_dir / "orchestrator_runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def start_run(self, project_id: str, policy: dict[str, Any]) -> tuple[str, Path]:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "run_id": run_id,
            "project_id": project_id,
            "started_at": datetime.now().isoformat(),
            "policy": policy,
        }
        (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
        return run_id, run_dir

    def append_event(self, run_dir: Path, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        events_path = run_dir / "events.jsonl"
        with events_path.open("a") as handle:
            handle.write(json.dumps(event) + "\n")
        return event

    def write_summary(self, run_dir: Path, summary: dict[str, Any], markdown: str) -> tuple[Path, Path]:
        summary_json = run_dir / "summary.json"
        summary_md = run_dir / "summary.md"
        summary_json.write_text(json.dumps(summary, indent=2))
        summary_md.write_text(markdown)
        return summary_json, summary_md

    def log_scheduler_cycle(
        self,
        run_id: str,
        project_id: str,
        due_rules: list[dict[str, Any]],
        tasks_created: list[dict[str, Any]],
        reminders: list[dict[str, Any]],
        orchestrator_run: bool,
    ) -> None:
        """Log a scheduler cycle event to the ledger."""
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "scheduler_cycle",
            "payload": {
                "project_id": project_id,
                "due_rules": due_rules,
                "tasks_created": tasks_created,
                "reminders": reminders,
                "orchestrator_run": orchestrator_run,
            },
        }
        events_path = run_dir / "events.jsonl"
        with events_path.open("a") as handle:
            handle.write(json.dumps(event) + "\n")
