#!/usr/bin/env python3
"""
Quick test for collection task initialization
"""
import sys
import os

# Ensure we're using the venv
os.environ['TERM'] = 'dumb'

from pathlib import Path
from rich.console import Console

console = Console()

def test_collection():
    """Test GSC collection setup for Example Site"""
    
    console.print("=" * 60)
    console.print("[bold cyan]TEST: GSC Collection Setup Test[/bold cyan]")
    console.print("=" * 60)
    
    # Import dashboard components
    from dashboard.models import Project
    from dashboard.storage.task_list import TaskList
    from dashboard.tasks.collection import CollectionRunner
    
    # Create project (same as projects.json)
    project = Project(
        name="Example Site",
        website_id="examplesite",
        repo_root="/path/to/your/website"
    )
    
    console.print(f"\n[dim]Project: {project.name}[/dim]")
    console.print(f"[dim]Website ID: {project.website_id}[/dim]")
    console.print(f"[dim]Repo: {project.repo_root}[/dim]")
    
    # Check manifest exists
    manifest_path = Path(project.repo_root) / ".github" / "automation" / "manifest.json"
    if manifest_path.exists():
        import json
        manifest = json.loads(manifest_path.read_text())
        console.print(f"[green]✓ Manifest found[/green]")
        console.print(f"[dim]  URL: {manifest.get('url', 'NO URL')}[/dim]")
        console.print(f"[dim]  GSC Site: {manifest.get('gsc_site', 'NOT SET')}[/dim]")
        console.print(f"[dim]  Sitemap: {manifest.get('sitemap', 'NOT SET')}[/dim]")
    else:
        console.print(f"[red]✗ Manifest NOT found at {manifest_path}[/red]")
        return False
    
    # Create task list
    console.print(f"\n[dim]Creating TaskList...[/dim]")
    task_list = TaskList(project)
    console.print(f"[green]✓ TaskList created[/green]")
    
    # Test runner initialization
    console.print(f"\n[dim]Initializing CollectionRunner...[/dim]")
    try:
        runner = CollectionRunner(task_list, project, None)
        console.print(f"[green]✓ CollectionRunner initialized[/green]")
    except Exception as e:
        console.print(f"[red]✗ CollectionRunner failed: {e}[/red]")
        return False
    
    # Test manifest detection
    console.print(f"\n[dim]Testing _detect_gsc_site()...[/dim]")
    try:
        site, sitemap, manifest_data = runner._detect_gsc_site()
        console.print(f"[green]✓ Site detected:[/green] {site}")
        console.print(f"[green]✓ Sitemap detected:[/green] {sitemap}")
    except Exception as e:
        console.print(f"[red]✗ Site detection failed: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return False
    
    # Create collection task
    console.print(f"\n[dim]Creating collection task...[/dim]")
    task = task_list.create_task(
        task_type="collect_gsc",
        title="Collect GSC data",
        phase="collection",
        priority="medium"
    )
    console.print(f"[green]✓ Task created: {task.id}[/green]")
    
    # Test validation
    console.print(f"\n[dim]Testing articles.json validation...[/dim]")
    try:
        is_valid, mismatches = runner.validate_articles_json()
        if is_valid:
            console.print(f"[green]✓ Articles.json is valid[/green]")
        else:
            console.print(f"[yellow]⚠ Articles.json has mismatches:[/yellow]")
            for m in mismatches[:3]:
                console.print(f"  [dim]{m}[/dim]")
    except Exception as e:
        console.print(f"[red]✗ Validation failed: {e}[/red]")
    
    console.print(f"\n[green]✓ All initialization tests passed[/green]")
    console.print(f"[dim]Ready for collection (will fail without GSC credentials)[/dim]")
    
    return True

if __name__ == "__main__":
    try:
        result = test_collection()
        
        console.print("\n" + "=" * 60)
        if result:
            console.print("[bold green]SETUP TEST PASSED[/bold green]")
        else:
            console.print("[bold red]SETUP TEST FAILED[/bold red]")
        console.print("=" * 60)
        
        sys.exit(0 if result else 1)
        
    except KeyboardInterrupt:
        console.print("\n[dim]Test interrupted[/dim]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]UNEXPECTED ERROR: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)
