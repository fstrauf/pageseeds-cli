"""
Clustering and internal linking tasks
"""
import threading
import time
from pathlib import Path

from rich.console import Console

from ..config import get_repo_root
from ..models import Task
from .base import TaskRunner

console = Console()


class LinkingRunner(TaskRunner):
    """Runs clustering and internal linking tasks."""
    
    def _run_with_progress(self, func, *args, **kwargs):
        """Run a function with a progress spinner using Rich's status."""
        from rich.status import Status
        
        result = [None]
        exception = [None]
        done = threading.Event()
        
        def worker():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e
            finally:
                done.set()
        
        # Start worker thread
        thread = threading.Thread(target=worker)
        thread.start()
        
        # Show Rich status spinner while waiting
        start_time = time.time()
        with Status("[dim]Working...[/dim]", console=console, spinner="dots") as status:
            while not done.wait(timeout=0.1):
                elapsed = time.time() - start_time
                status.update(f"[dim]Working... ({elapsed:.0f}s elapsed)[/dim]")
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    def run(self, task: Task) -> bool:
        """Execute SEO Step 3: Clustering and Internal Linking."""
        console.print(f"\n[bold]Cluster & Link Task: {task.title}[/bold]")
        console.print("[cyan]Running SEO Step 3: Clustering and Internal Linking[/cyan]\n")
        
        # Extract article ID from category if stored there
        article_id = None
        if task.category and task.category.startswith("linking:article_id="):
            try:
                article_id = int(task.category.split("=")[1])
            except:
                pass
        
        # Find the content brief path
        repo_root = Path(self.project.repo_root)
        automation_dir = repo_root / ".github" / "automation"
        brief_path = automation_dir / "seo_content_brief.md"
        
        # Build the prompt
        prompt_parts = [
            f"Run SEO Step 3 (Clustering & Linking) for article in {self.project.website_id}.",
            "",
            f"WORKSPACE: .github/automation",
        ]
        
        if article_id:
            prompt_parts.extend([
                f"TARGET ARTICLE ID: {article_id}",
                "",
                "STEPS:",
                f"1. Load article {article_id} content: seo-content-cli --workspace-root .github/automation get-article-content --website-path . --article-id {article_id}",
                f"2. Scan existing internal links: seo-content-cli --workspace-root .github/automation scan-internal-links --website-path .",
                f"3. Generate linking plan: seo-content-cli --workspace-root .github/automation generate-linking-plan --website-path . --missing-only",
                "4. Identify which cluster this article belongs to",
                "5. Add links TO this article from relevant existing articles",
                "6. Add links FROM this article to relevant existing articles",
                f"7. Use: seo-content-cli --workspace-root .github/automation add-article-links --website-path . --source-id <ID> --target-ids <ID1> <ID2>",
                f"8. Update brief linking status: seo-content-cli --workspace-root .github/automation update-brief-linking-status --website-path .",
            ])
        else:
            prompt_parts.extend([
                "STEPS (Full Site):",
                f"1. Load all articles: seo-content-cli --workspace-root .github/automation articles-summary --website-path .",
                f"2. Scan existing internal links: seo-content-cli --workspace-root .github/automation scan-internal-links --website-path .",
                f"3. Generate linking plan: seo-content-cli --workspace-root .github/automation generate-linking-plan --website-path . --missing-only",
                "4. Group articles by intent into clusters",
                "5. Pick/update pillar articles for each cluster",
                "6. Add missing hub-spoke and cross-cluster links",
                f"7. Batch add links: seo-content-cli --workspace-root .github/automation batch-add-links --website-path .",
                "8. Update content brief with cluster mapping",
            ])
        
        prompt_parts.extend([
            "",
            "REQUIREMENTS:",
            "- Every article should link to its pillar (if support) or to supports (if pillar)",
            "- Add 2-4 cross-cluster links where topically relevant",
            "- Update the content brief linking checklist",
            "- Use the seo-content-cli commands",
        ])
        
        if brief_path.exists():
            prompt_parts.extend([
                "",
                f"CONTENT BRIEF: {brief_path}",
                "Update the brief with cluster mapping and mark linking tasks complete.",
            ])
        
        prompt = "\n".join(prompt_parts)
        
        console.print("[dim]Running clustering and linking workflow...[/dim]")
        console.print("[dim]This may take 3-5 minutes. Press Ctrl+C to cancel.[/dim]\n")
        
        try:
            # Run agent with progress indicator
            success, output = self._run_with_progress(
                self.run_kimi_agent, prompt, cwd=repo_root, timeout=600
            )
            
            if output:
                lines = output.split('\n')
                filtered = []
                skip_patterns = ['ToolCall', 'ToolResult', 'StepBegin', 'ThinkPart', 'StatusUpdate', 'TurnBegin', 'TurnEnd']
                for line in lines:
                    if line.strip() and not any(p in line for p in skip_patterns):
                        filtered.append(line)
                if filtered:
                    console.print('\n'.join(filtered[-30:]))
            
            console.print(f"\n[green]✓ Clustering and linking complete[/green]")
            console.print("[dim]Internal links have been added and brief updated.[/dim]")
            
            task.status = "done"
            task.completed_at = __import__('datetime').datetime.now().isoformat()
            self.task_list.save()
            return True
            
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            return False
