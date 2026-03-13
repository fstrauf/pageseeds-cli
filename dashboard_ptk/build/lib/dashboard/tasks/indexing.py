"""
Indexing diagnostics tasks
"""
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

from ..models import Task
from .base import TaskRunner

console = Console()


class IndexingRunner(TaskRunner):
    """Runs indexing diagnostics tasks."""
    
    def run(self, task: Task = None) -> bool:
        """Execute SEO Step 6: Indexing Diagnostics."""
        console.print(f"\n[bold]Indexing Diagnostics (Step 6)[/bold]")
        console.print("[cyan]Checking Google Search Console indexing status...[/cyan]\n")
        
        # Get site info from manifest
        site = None
        sitemap_url = None
        
        try:
            repo_root = Path(self.project.repo_root)
            automation_dir = repo_root / ".github" / "automation"
            manifest_path = automation_dir / "manifest.json"
            if not manifest_path.exists():
                # Fallback to legacy location
                manifest_path = repo_root / "automation" / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text())
                site = manifest.get("gsc_site") or f"sc-domain:{manifest.get('url', '').replace('https://', '').replace('http://', '').rstrip('/')}"  
                sitemap_url = manifest.get("sitemap") or f"{manifest.get('url', '').rstrip('/')}/sitemap.xml"
        except:
            pass
        
        if not site:
            console.print("[yellow]Could not auto-detect GSC site.[/yellow]")
            site = self.session.prompt("Enter GSC site (e.g., sc-domain:example.com): ")
        
        if not sitemap_url:
            sitemap_url = self.session.prompt("Enter sitemap URL: ")
        
        console.print(f"\n[dim]Site: {site}[/dim]")
        console.print(f"[dim]Sitemap: {sitemap_url}[/dim]")
        
        confirm = self.session.prompt("\nProceed with indexing check? (y/n): ")
        if confirm.lower() != "y":
            console.print("[yellow]Cancelled.[/yellow]")
            return False
        
        # Run the indexing report via CLI
        # Use smaller limit for faster completion - can run multiple times if needed
        limit = 100  # Reduced from 200 to avoid timeouts
        cmd = [
            "seo",
            "gsc-indexing-report",
            "--site", site,
            "--sitemap-url", sitemap_url,
            "--limit", str(limit),
            "--workers", "3"  # Increased from 2 for faster processing
        ]
        
        console.print(f"\n[dim]Running GSC indexing report (limit: {limit} URLs, 3 workers)...[/dim]")
        console.print("[dim]This may take 3-8 minutes depending on GSC API response times.[/dim]")
        console.print("[dim]Press Ctrl+C to cancel if needed.[/dim]\n")
        
        try:
            success, stdout, stderr = self.run_cli_command(
                cmd,
                timeout=600  # Increased from 300 to 10 minutes
            )
            
            if stdout:
                lines = stdout.split('\n')
                filtered = []
                skip_patterns = ['ToolCall', 'ToolResult', 'StepBegin', 'ThinkPart', 'StatusUpdate', 'TurnBegin', 'TurnEnd']
                for line in lines:
                    if line.strip() and not any(p in line for p in skip_patterns):
                        filtered.append(line)
                if filtered:
                    console.print('\n'.join(filtered[-40:]))
            
            if success:
                console.print(f"\n[green]✓ Indexing diagnostics complete[/green]")
                console.print("[dim]Check .github/automation/output/gsc_indexing/ for results[/dim]")
                
                # Auto-create fix tasks
                self._create_fix_tasks()
                
                if task:
                    task.status = "done"
                    task.completed_at = datetime.now().isoformat()
                    self.task_list.save()
                return True
            else:
                console.print(f"[red]✗ Command failed[/red]")
                if stderr:
                    console.print(f"[dim]{stderr[-1200:]}[/dim]")
                return False
                
        except Exception as e:
            error_msg = str(e)
            console.print(f"[red]Error: {error_msg}[/red]")
            
            # Check for partial output even on failure
            output_dir = repo_root / ".github" / "automation" / "output" / "gsc_indexing"
            if output_dir.exists():
                json_files = list(output_dir.glob("*.json"))
                if json_files:
                    latest = max(json_files, key=lambda p: p.stat().st_mtime)
                    console.print(f"\n[yellow]Partial output may be available:[/yellow]")
                    console.print(f"[dim]  {latest}[/dim]")
                    console.print(f"[dim]Check this file for any results before the timeout.[/dim]")
            
            # Check if it's a timeout specifically
            if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                console.print(f"\n[yellow]The GSC API call timed out.[/yellow]")
                console.print(f"[dim]Suggestions:[/dim]")
                console.print(f"[dim]  1. Try again with a smaller URL limit (50-100 instead of 200)[/dim]")
                console.print(f"[dim]  2. Check GSC API access and service account permissions[/dim]")
                console.print(f"[dim]  3. Run the command manually to see detailed progress:[/dim]")
                console.print(f"[dim]     pageseeds automation seo gsc-indexing-report --site {site} --sitemap-url {sitemap_url} --limit 50[/dim]")
            
            return False
    
    def _create_fix_tasks(self):
        """Create fix tasks from indexing diagnostics results."""
        try:
            repo_root = Path(self.project.repo_root)
            output_dir = repo_root / ".github" / "automation" / "output" / "gsc_indexing"
            if not output_dir.exists():
                return
            
            queue_files = list(output_dir.glob("*_action_queue.json"))
            if queue_files:
                latest = max(queue_files, key=lambda p: p.stat().st_mtime)
                data = json.loads(latest.read_text())
                
                fixes = data.get("fixes", [])
                created = 0
                
                for fix in fixes[:5]:
                    issue = fix.get("issue", "Indexing issue")
                    
                    existing = any(
                        t.title == issue and t.type == "fix_indexing"
                        for t in self.task_list.tasks
                    )
                    if existing:
                        continue
                    
                    fix_task = self.task_list.create_task(
                        task_type="fix_indexing",
                        title=issue,
                        phase="implementation",
                        priority="high" if fix.get("count", 0) > 10 else "medium",
                        category="technical_seo"
                    )
                    created += 1
                
                if created > 0:
                    console.print(f"\n[green]✓ Created {created} indexing fix task(s)[/green]")
                    
        except Exception as e:
            console.print(f"[dim]Could not create fix tasks: {e}[/dim]")
