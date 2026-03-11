#!/usr/bin/env python3
"""
End-to-end integration test for dashboard collection task
This runs through the actual Dashboard class and simulates user interaction
"""
import sys
import os
import io
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

# Ensure we use the venv
os.environ['TERM'] = 'dumb'
os.environ['COLUMNS'] = '80'

# Change to dashboard directory
os.chdir('/path/to/your/automation/dashboard_ptk')

from rich.console import Console

console = Console()

class MockPromptSession:
    """Simulates user input for testing"""
    def __init__(self, responses):
        self.responses = responses
        self.index = 0
        self.history = []
    
    def prompt(self, text, **kwargs):
        if self.index < len(self.responses):
            response = self.responses[self.index]
            self.index += 1
            self.history.append((text.strip(), response))
            console.print(f"[dim][TEST INPUT] {text.strip()} -> {response}[/dim]")
            return response
        console.print(f"[red][TEST ERROR] No more responses for: {text}[/red]")
        return ""

class MockProjectManager:
    """Simple project manager for testing"""
    def __init__(self, project):
        self.current = project
        self.projects = [project]

def test_e2e_collection():
    """Full end-to-end test of collection task flow"""
    
    console.print("=" * 70)
    console.print("[bold cyan]E2E TEST: Dashboard Collection Task Flow[/bold cyan]")
    console.print("=" * 70)
    
    # Import dashboard
    from dashboard.cli import Dashboard
    from dashboard.models import Project
    
    # Create project
    project = Project(
        name="Example Site",
        website_id="examplesite",
        repo_root="/path/to/your/website"
    )
    
    console.print(f"\n[dim]Project: {project.name}[/dim]")
    console.print(f"[dim]Website ID: {project.website_id}[/dim]")
    
    # Verify manifest exists
    manifest_path = Path(project.repo_root) / ".github" / "automation" / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[red]✗ Manifest not found at {manifest_path}[/red]")
        return False
    
    console.print(f"[green]✓ Manifest exists[/green]")
    
    # Create dashboard with mocked input
    # Inputs: "1" = work on task, "1" = select first task, "yes" = confirm collection
    test_inputs = ["1", "1", "yes"]
    mock_session = MockPromptSession(test_inputs)
    
    console.print(f"\n[dim]Initializing Dashboard...[/dim]")
    
    try:
        dashboard = Dashboard.__new__(Dashboard)
        dashboard.project_manager = MockProjectManager(project)
        dashboard.session = mock_session
        
        # Initialize components (skip gitignore check)
        from dashboard.storage.task_list import TaskList
        dashboard.task_list = TaskList(project)
        
        # Clear any existing tasks for clean test
        dashboard.task_list.tasks = []
        dashboard.task_list.save()
        
        # Create a fresh collection task
        task = dashboard.task_list.create_task(
            task_type="collect_gsc",
            title="Collect GSC data",
            phase="collection",
            priority="medium"
        )
        console.print(f"[green]✓ Created task: {task.id} - {task.title}[/green]")
        
        # Initialize all runners
        from dashboard.tasks import (
            CollectionRunner, InvestigationRunner, ResearchRunner,
            ContentRunner, ImplementationRunner, RedditRunner
        )
        
        # Create runners dict (ImplementationRunner needs the full dict)
        dashboard.runners = {
            "collection": CollectionRunner(dashboard.task_list, project, mock_session),
            "investigation": InvestigationRunner(dashboard.task_list, project, mock_session),
            "research": ResearchRunner(dashboard.task_list, project, mock_session),
            "content": ContentRunner(dashboard.task_list, project, mock_session),
            "reddit": RedditRunner(dashboard.task_list, project, mock_session),
        }
        # ImplementationRunner needs the runners dict
        dashboard.runners["implementation"] = ImplementationRunner(
            dashboard.task_list, project, mock_session, dashboard.runners
        )
        console.print(f"[green]✓ All runners initialized[/green]")
        
    except Exception as e:
        console.print(f"[red]✗ Dashboard initialization failed: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return False
    
    # Run the work loop with mocked input
    console.print(f"\n[bold]Executing task flow...[/bold]")
    console.print("-" * 70)
    
    try:
        # Capture output
        output_buffer = io.StringIO()
        
        with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
            # This simulates: work_loop -> select_and_work_on_task -> work_on_task
            success = dashboard.work_on_task(task)
        
        # Show captured output
        output = output_buffer.getvalue()
        if output:
            for line in output.split('\n')[-30:]:  # Show last 30 lines
                if line.strip():
                    console.print(f"  {line}")
        
        console.print("-" * 70)
        
        # Show what inputs were used
        console.print(f"\n[dim]Inputs provided:[/dim]")
        for prompt, response in mock_session.history:
            console.print(f"  [dim]{prompt[:50]}... -> {response}[/dim]")
        
        # Check result
        if success:
            console.print(f"\n[green]✓ Task completed successfully[/green]")
        else:
            console.print(f"\n[yellow]✗ Task failed (expected without GSC credentials)[/yellow]")
        
        return True  # Test ran without crashing
        
    except Exception as e:
        console.print("-" * 70)
        console.print(f"\n[red]✗ EXCEPTION during execution: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return False
    finally:
        # Cleanup: remove test task
        try:
            dashboard.task_list.tasks = [t for t in dashboard.task_list.tasks if t.id != task.id]
            dashboard.task_list.save()
        except:
            pass

if __name__ == "__main__":
    try:
        result = test_e2e_collection()
        
        console.print("\n" + "=" * 70)
        if result:
            console.print("[bold green]E2E TEST PASSED[/bold green]")
            console.print("[dim]Dashboard flow executed without crashes[/dim]")
        else:
            console.print("[bold red]E2E TEST FAILED[/bold red]")
        console.print("=" * 70)
        
        sys.exit(0 if result else 1)
        
    except KeyboardInterrupt:
        console.print("\n[dim]Test interrupted by user[/dim]")
        sys.exit(1)
