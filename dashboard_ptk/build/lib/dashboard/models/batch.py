"""
Batch processing configuration
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BatchConfig:
    """Configuration for batch processing."""
    max_tasks: int = 10  # Max tasks to process in one batch
    auto_approve_batchable: bool = False  # Require confirmation for batchable tasks (safer)
    pause_on_error: bool = True  # Stop batch if a task fails
    pause_on_spec: bool = True  # Stop when encountering a spec task
    rate_limit_delay: int = 5  # Seconds between tasks (to avoid rate limits)
    show_progress_every: int = 1  # Show progress every N tasks
    
    # Task-type specific defaults for automated batch processing
    # Example: {"reddit_reply": {"action": "copy_and_mark"}}
    task_type_defaults: dict = field(default_factory=dict)
