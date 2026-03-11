"""
Task list rendering and display
"""
from ..config import PHASES, EXECUTION_MODE_MAP
from ..storage import TaskList
from .console import console


class TaskRenderer:
    """Renders task lists and UI elements."""
    
    def __init__(self, task_list: TaskList):
        self.task_list = task_list
    
    def _get_execution_mode(self, task_type: str) -> str:
        """Get execution mode based on task type."""
        return EXECUTION_MODE_MAP.get(task_type, "auto")
    
    def render_task_list(self):
        """Display tasks organized by phase."""
        progress = self.task_list.get_progress()
        
        # Progress bar
        bar_width = 30
        filled = int((progress["pct"] / 100) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        console.print(f"Progress: {bar} {progress['pct']}% ({progress['done']}/{progress['total']})")
        console.print()
        
        completed = self.task_list.get_completed_ids()
        
        for phase in PHASES:
            phase_tasks = self.task_list.get_by_phase(phase)
            if not phase_tasks:
                continue
            
            todo = len([t for t in phase_tasks if t.status == "todo"])
            in_prog = len([t for t in phase_tasks if t.status == "in_progress"])
            done = len([t for t in phase_tasks if t.status == "done"])
            
            console.print(f"[bold]{phase.upper()}[/bold] [dim]todo:{todo} in-progress:{in_prog} done:{done}[/dim]")
            
            for task in phase_tasks[:5]:
                unlocked = task.is_unlocked(completed)
                locked_str = "[dim]🔒[/dim]" if not unlocked and task.status == "todo" else "  "
                
                priority_color = {"high": "red", "medium": "yellow", "low": "dim"}.get(task.priority, "white")
                # DEBUG
                console.print(f"[dim]DEBUG RENDER: {task.id} status={task.status}[/dim]")
                status_icon = {
                    "todo": "○",
                    "in_progress": "[yellow]◐[/yellow]",
                    "review": "[cyan]👁[/cyan]",
                    "done": "[green]✓[/green]",
                    "blocked": "[red]✗[/red]"
                }.get(task.status, "?")
                
                # Show spec indicator for structural tasks
                spec_indicator = ""
                if task.spec_file:
                    spec_indicator = "[dim][spec][/dim] "
                elif task.implementation_mode == "spec":
                    spec_indicator = "[yellow][spec][/yellow] "
                
                # Show short task ID
                task_id_short = task.id if '-' in task.id else task.id[:20]
                
                # Show task type indicator
                type_indicator = ""
                execution_mode = self._get_execution_mode(task.type)
                if execution_mode == "direct":
                    type_indicator = "[green][write][/green] "
                elif execution_mode == "spec":
                    type_indicator = "[yellow][spec][/yellow] "
                elif execution_mode == "workflow":
                    type_indicator = "[blue][flow][/blue] "
                elif execution_mode == "auto":
                    type_indicator = "[dim][auto][/dim] "
                
                console.print(f"  {locked_str} {status_icon} [{priority_color}]{task.priority[0].upper()}[/{priority_color}] [dim]{task_id_short}[/dim] {type_indicator}{spec_indicator}{task.title[:50]}")
            
            if len(phase_tasks) > 5:
                console.print(f"     [dim]... and {len(phase_tasks) - 5} more[/dim]")
            
            console.print()
    
    def render_ready_tasks(self):
        """Show tasks ready to start."""
        ready = self.task_list.get_ready()
        in_progress = self.task_list.get_by_status("in_progress")
        
        if in_progress:
            console.print("[bold cyan]→ In Progress:[/bold cyan]")
            for task in in_progress[:3]:
                console.print(f"  ◐ [{task.phase}] {task.title}")
            console.print()
        
        if ready:
            console.print("[bold cyan]→ Ready to Start:[/bold cyan]")
            for task in ready[:3]:
                console.print(f"  ○ [{task.phase}] {task.title}")
            console.print()
    
    def clear_screen(self, project_name: str = None, project_code: str = None):
        """Clear screen and show header."""
        import os
        os.system('clear' if os.name != 'nt' else 'cls')
        console.print("=" * 70)
        console.print("[bold]Task Dashboard[/bold] - Just Tasks, No Campaigns")
        console.print("=" * 70)
        if project_name:
            code_str = f" [{project_code}]" if project_code else ""
            console.print(f"Project: [bold]{project_name}[/bold]{code_str}")
        console.print()
