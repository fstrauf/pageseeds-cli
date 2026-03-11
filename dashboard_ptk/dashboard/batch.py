"""
Batch processing for autonomous task execution
"""
from datetime import datetime
from typing import List

from rich.console import Console

from .config import AUTONOMY_MODE_MAP
from .models import Task, BatchConfig


class BatchProcessor:
    """Handles autonomous batch processing of tasks."""
    
    def __init__(self, task_list, dashboard, config: BatchConfig = None):
        self.task_list = task_list
        self.dashboard = dashboard
        self.config = config or BatchConfig()
        self.running = False
        self.processed_count = 0
        self.errors: list[dict] = []
        self.start_time: datetime | None = None
    
    def _get_autonomy_mode(self, task_type: str) -> str:
        """Get autonomy mode for a task type."""
        if hasattr(self.dashboard, "workflow_bundle"):
            return self.dashboard.workflow_bundle.autonomy_mode_map.get(task_type, "manual")
        return AUTONOMY_MODE_MAP.get(task_type, "manual")
    
    def get_ready_autonomous_tasks(self) -> List[Task]:
        """Get all tasks that can run autonomously (sorted by priority)."""
        completed = self.task_list.get_completed_ids()
        ready = []
        
        for task in self.task_list.tasks:
            if task.status != "todo":
                continue
            if not task.is_unlocked(completed):
                continue
            
            autonomy = self._get_autonomy_mode(task.type)
            if autonomy in ("automatic", "batchable"):
                ready.append(task)
        
        # Sort by priority: high > medium > low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        ready.sort(key=lambda t: priority_order.get(t.priority, 1))
        
        return ready
    
    def get_batch_summary(self) -> dict:
        """Get summary of tasks ready for batch processing."""
        ready = self.get_ready_autonomous_tasks()
        
        by_autonomy = {"automatic": [], "batchable": []}
        for task in ready:
            autonomy = self._get_autonomy_mode(task.type)
            by_autonomy[autonomy].append(task)
        
        return {
            "total_ready": len(ready),
            "automatic": len(by_autonomy["automatic"]),
            "batchable": len(by_autonomy["batchable"]),
            "tasks": ready[:self.config.max_tasks]
        }
    
    def run_batch(self, console: Console) -> dict:
        """Run batch processing of autonomous tasks."""
        import time
        
        self.running = True
        self.processed_count = 0
        self.errors = []
        self.start_time = datetime.now()
        
        console.print(f"\n[bold cyan]🚀 Starting Batch Mode[/bold cyan]")
        console.print(f"[dim]Max tasks: {self.config.max_tasks}[/dim]")
        console.print(f"[dim]Pause on error: {self.config.pause_on_error}[/dim]")
        console.print(f"[dim]Pause on spec: {self.config.pause_on_spec}[/dim]")
        console.print()
        
        while self.running and self.processed_count < self.config.max_tasks:
            # Refresh task list
            self.task_list.load()
            
            # Get next ready task
            ready = self.get_ready_autonomous_tasks()
            
            if not ready:
                console.print("[green]✓ No more autonomous tasks available[/green]")
                break
            
            task = ready[0]
            autonomy = self._get_autonomy_mode(task.type)
            
            # Check if we should pause for batchable tasks
            if autonomy == "batchable" and not self.config.auto_approve_batchable:
                console.print(f"\n[yellow]⏸ Paused for batchable task review[/yellow]")
                return {
                    "status": "paused",
                    "reason": "batchable_review",
                    "processed": self.processed_count,
                    "next_task": task,
                    "errors": self.errors
                }
            
            # Process the task
            console.print(f"\n[bold]▶ Task {self.processed_count + 1}: {task.id} - {task.title[:50]}...[/bold]")
            console.print(f"[dim]   Type: {task.type} | Autonomy: {autonomy}[/dim]")
            
            success = self._execute_task(task, console)
            
            if success:
                self.processed_count += 1
                console.print(f"[green]   ✓ Completed ({self.processed_count}/{self.config.max_tasks})[/green]")
                
                if self.processed_count % self.config.show_progress_every == 0:
                    self._show_progress(console)
            else:
                self.errors.append({
                    "task_id": task.id,
                    "task_title": task.title,
                    "task_type": task.type
                })
                console.print(f"[red]   ✗ Failed[/red]")
                
                if self.config.pause_on_error:
                    console.print(f"\n[yellow]⏸ Batch paused due to error[/yellow]")
                    return {
                        "status": "error",
                        "reason": "task_failed",
                        "processed": self.processed_count,
                        "failed_task": task,
                        "errors": self.errors
                    }
            
            # Rate limiting delay
            if self.config.rate_limit_delay > 0 and self.running:
                time.sleep(self.config.rate_limit_delay)
        
        # Batch complete
        duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        console.print(f"\n[bold cyan]✓ Batch Complete[/bold cyan]")
        console.print(f"[dim]Processed: {self.processed_count} tasks in {duration:.1f}s[/dim]")
        
        if self.errors:
            console.print(f"[yellow]Errors: {len(self.errors)}[/yellow]")
        
        return {
            "status": "complete",
            "processed": self.processed_count,
            "duration_seconds": duration,
            "errors": self.errors
        }
    
    def _execute_task(self, task: Task, console: Console) -> bool:
        """Execute a single task and return success status."""
        from datetime import datetime
        
        task.started_at = datetime.now().isoformat()
        if task.status == "todo":
            task.status = "in_progress"
        self.task_list.save()
        
        try:
            if not self.dashboard.executor:
                console.print("[red]Execution engine is not initialized[/red]")
                success = False
            else:
                # Pass execution context to runners for batch-specific defaults
                if self.config.task_type_defaults:
                    for runner in self.dashboard.runners.values():
                        if hasattr(runner, 'set_execution_context'):
                            runner.set_execution_context(self.config.task_type_defaults)
                
                result = self.dashboard.executor.execute_task(task)
                # Handle both old bool return and new tuple return
                if isinstance(result, tuple):
                    success, _ = result
                else:
                    success = result
                
                # Clear execution context after task completion
                if self.config.task_type_defaults:
                    for runner in self.dashboard.runners.values():
                        if hasattr(runner, 'set_execution_context'):
                            runner.set_execution_context({})
        except Exception as e:
            console.print(f"[red]Error executing task: {e}[/red]")
            success = False
        
        self.task_list.save()
        return success
    
    def _show_progress(self, console: Console):
        """Show current batch progress."""
        progress = self.task_list.get_progress()
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        
        console.print(f"\n[dim]Progress: {progress['done']}/{progress['total']} total | "
                      f"Batch: {self.processed_count} | "
                      f"Elapsed: {elapsed/60:.1f}m[/dim]")
    
    def stop(self):
        """Stop batch processing gracefully."""
        self.running = False
