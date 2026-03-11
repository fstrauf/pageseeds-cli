"""
Content cleanup and QA tasks
"""
from pathlib import Path

from rich.console import Console

from ..config import get_repo_root
from ..models import Task
from .base import TaskRunner

console = Console()


class CleanupRunner(TaskRunner):
    """Runs content cleanup and QA tasks."""
    
    def run(self, task: Task = None) -> bool:
        """Execute SEO Step 5: Content Cleanup & QA."""
        console.print(f"\n[bold]Content Cleanup & QA (Step 5)[/bold]")
        console.print("[cyan]Validating content and fixing issues...[/cyan]\n")
        
        repo_root = Path(self.project.repo_root)
        workspace = ".github/automation"
        
        prompt = f"""Run SEO Step 5 (Content Cleanup & QA) for {self.project.website_id}.

WORKSPACE: {workspace}

STEPS:
1. Validate content (read-only check):
   seo-content-cli --workspace-root {workspace} validate-content --website-path .

2. Review validation results for:
   - Duplicate title headings
   - Frontmatter/date mismatches
   - Missing fields
   - articles.json out of sync with actual .mdx files

3. Clean content (fix structural issues only):
   seo-content-cli --workspace-root {workspace} clean-content --website-path .
   (This fixes duplicate headings, frontmatter format - NOT dates)

4. Analyze dates (report only, DO NOT FIX):
   seo-content-cli --workspace-root {workspace} analyze-dates --website-path .
   
   Report any issues found:
   - Date overlaps between articles
   - Dates in the future
   - Missing dates
   BUT DO NOT run fix-dates - that is handled by Publish step

5. Final validation to confirm structural issues resolved.

REQUIREMENTS:
- Report what was checked and what was fixed (structural issues only)
- Ensure articles.json accurately reflects actual content files
- REPORT date issues but do NOT fix them (publish step handles this)
- Verify frontmatter correctness on sample files
- Use seo-content-cli commands only
- NEVER change dates of published articles
"""
        
        console.print("[dim]Running content cleanup workflow...[/dim]\n")
        
        try:
            success, output = self.run_kimi_agent(prompt, cwd=repo_root, timeout=600)
            
            if output:
                # Extract just the useful summary
                summary_start = -1
                for marker in ["## ✅ SEO Step 5 Complete", "## Content Cleanup", "---", "## Summary"]:
                    idx = output.find(marker)
                    if idx != -1:
                        summary_start = idx
                        break
                
                if summary_start != -1:
                    summary = output[summary_start:]
                    for end_marker in ["TurnEnd", "StatusUpdate", "StepBegin(n=", "TextPart("]:
                        end_idx = summary.find(end_marker)
                        if end_idx != -1:
                            summary = summary[:end_idx].strip()
                            break
                    console.print(summary)
                else:
                    lines = output.split('\n')
                    filtered = []
                    skip_patterns = ['ToolCall', 'ToolResult', 'StepBegin', 'ThinkPart', 'StatusUpdate', 'TurnBegin', 'TurnEnd']
                    for line in lines[-50:]:
                        if not any(p in line for p in skip_patterns):
                            filtered.append(line)
                    if filtered:
                        console.print('\n'.join(filtered[-30:]))
            
            console.print(f"\n[green]✓ Content cleanup complete[/green]")
            
            if task:
                task.status = "done"
                task.completed_at = __import__('datetime').datetime.now().isoformat()
                self.task_list.save()
            return True
            
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
