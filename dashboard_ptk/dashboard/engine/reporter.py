"""Summary builders for orchestration runs."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def build_run_summary(
    *,
    run_id: str,
    project_id: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    reason: str,
    processed: int,
    succeeded: int,
    failed: int,
    blocked: int,
    events: list[dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Build machine + markdown summaries for a run."""
    duration_seconds = max(0.0, (finished_at - started_at).total_seconds())
    task_type_counter = Counter()
    for event in events:
        if event.get("event_type") != "task_result":
            continue
        task_type = str(event.get("payload", {}).get("task_type", "unknown"))
        task_type_counter[task_type] += 1

    summary = {
        "run_id": run_id,
        "project_id": project_id,
        "status": status,
        "reason": reason,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "blocked": blocked,
        "task_type_counts": dict(task_type_counter),
        "policy": policy,
        "events_count": len(events),
    }

    lines = [
        f"# Orchestration Run {run_id}",
        "",
        f"- Project: `{project_id}`",
        f"- Status: `{status}` ({reason})",
        f"- Started: `{started_at.isoformat()}`",
        f"- Finished: `{finished_at.isoformat()}`",
        f"- Duration seconds: `{duration_seconds:.1f}`",
        "",
        "## Totals",
        f"- Processed: `{processed}`",
        f"- Succeeded: `{succeeded}`",
        f"- Failed: `{failed}`",
        f"- Policy-blocked: `{blocked}`",
        "",
        "## Task Types",
    ]
    if task_type_counter:
        for task_type, count in sorted(task_type_counter.items()):
            lines.append(f"- `{task_type}`: {count}")
    else:
        lines.append("- None")

    return summary, "\n".join(lines) + "\n"
