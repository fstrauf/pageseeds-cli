"""
Investigation tasks - analyze collected data
"""
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

from ..models import Task
from .base import TaskRunner

console = Console()


class InvestigationRunner(TaskRunner):
    """Runs investigation tasks."""
    
    def run(self, task: Task) -> bool:
        """Execute an investigation task via agent."""
        # Validate articles.json alignment first - affects GSC data interpretation
        is_valid, _ = self.validate_articles_json()
        if not is_valid:
            console.print(f"\n[yellow]Investigation aborted due to articles.json misalignment.[/yellow]")
            console.print(f"[dim]Fix the mismatches, then retry this task.[/dim]")
            return False
        
        console.print(f"\n[bold]Investigating: {task.title}[/bold]")
        
        source = task.type.replace("investigate_", "").upper()
        
        # Ensure result directory exists
        result_dir = self.task_list.task_results_dir / task.id
        result_dir.mkdir(parents=True, exist_ok=True)
        
        prompt = f"""You are investigating {source} data for {self.project.website_id}.

TASK: {task.title}

READ: {self.project.repo_root}/.github/automation/{task.input_artifact}

Your job:
1. Analyze the data thoroughly
2. Identify specific issues that need fixing
3. Create actionable tasks

OUTPUT STRUCTURE:
{{
  "investigation_summary": "Brief overview",
  "issues_found": [
    {{
      "title": "Specific fix title",
      "description": "What needs to be done",
      "priority": "high|medium|low",
      "category": "technical_seo|content|conversion"
    }}
  ]
}}

WRITE: Save your analysis to {result_dir}/investigation.json

After saving, report what issues you found.
"""
        
        console.print("\n[dim]Running Kimi agent...[/dim]\n")
        
        inv_file = result_dir / "investigation.json"
        
        try:
            success, output = self.run_kimi_agent(prompt, timeout=600)
            
            if output:
                console.print(output[-2000:] if len(output) > 2000 else output)
            
            # Check if investigation was saved (even if agent reported error)
            if inv_file.exists():
                # Validate it's readable JSON
                try:
                    inv_data = json.loads(inv_file.read_text())
                    issues = inv_data.get("issues_found", [])
                    console.print(f"\n[green]✓ Investigation saved ({len(issues)} issues found)[/green]")
                except json.JSONDecodeError:
                    console.print("\n[yellow]⚠ Investigation file exists but has invalid JSON[/yellow]")
                    console.print("[dim]The agent may have been interrupted while writing.[/dim]")
                    return False
                
                # Create fix tasks from the investigation
                try:
                    created_count = 0
                    for issue in issues:
                        issue_title = issue.get("title", "Fix issue")
                        
                        # Check if fix task already exists
                        existing_fix = any(
                            t.title == issue_title and t.parent_task == task.id
                            for t in self.task_list.tasks
                        )
                        
                        if existing_fix:
                            continue
                        
                        fix_task = self.task_list.create_task(
                            task_type="fix_technical" if issue.get("category") == "technical_seo" else "fix_content",
                            title=issue_title,
                            phase="implementation",
                            priority=issue.get("priority", "medium"),
                            depends_on=task.id,
                            parent_task=task.id,
                            category=issue.get("category"),
                            input_artifact=str(inv_file.relative_to(self.task_list.automation_dir))
                        )
                        task.spawns_tasks.append(fix_task.id)
                        created_count += 1
                    
                    if created_count > 0:
                        console.print(f"[green]✓ Created {created_count} fix tasks[/green]")
                    else:
                        console.print(f"[dim]All fix tasks already exist[/dim]")
                    
                except Exception as e:
                    console.print(f"[yellow]Could not auto-create tasks: {e}[/yellow]")
                
                # Mark task done even if agent had warnings - we got the data
                task.status = "done"
                task.completed_at = datetime.now().isoformat()
                task.result_path = str(result_dir.relative_to(self.task_list.automation_dir))
                self.task_list.save()
                return True
            else:
                console.print("[yellow]Investigation file not found[/yellow]")
                console.print("[dim]The agent may have failed before writing output.[/dim]")
                if not success:
                    console.print(f"[dim]Agent error: {output[:500]}[/dim]")
                return False
                
        except Exception as e:
            # Even on exception, check if we got partial results
            if inv_file.exists():
                try:
                    inv_data = json.loads(inv_file.read_text())
                    issues = inv_data.get("issues_found", [])
                    console.print(f"\n[yellow]Agent crashed, but investigation was saved ({len(issues)} issues)[/yellow]")
                    console.print("[dim]You may want to review the output file manually.[/dim]")
                    task.status = "done"
                    task.completed_at = datetime.now().isoformat()
                    task.result_path = str(result_dir.relative_to(self.task_list.automation_dir))
                    self.task_list.save()
                    return True
                except:
                    pass
            console.print(f"[red]Error: {e}[/red]")
            return False
