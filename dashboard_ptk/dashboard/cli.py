"""
Main CLI - Menu system and work loop
"""
from datetime import datetime
from pathlib import Path

from prompt_toolkit import PromptSession
from rich.console import Console

from .config import PHASES
from .core.project_manager import ProjectManager
from .engine import (
    ExecutionEngine,
    OrchestratorService,
    ProjectPreflight,
    ProjectPreflightReport,
    RuntimeConfig,
    resolve_reddit_history_path,
)
from .cli_articles import DashboardArticlesMixin
from .cli_projects import DashboardProjectsMixin
from .cli_task_actions import DashboardTaskActionsMixin
from .cli_verification import DashboardVerificationMixin
from .models import BatchConfig
from .scheduler_cli import SchedulerCLI
from .storage import TaskList
from .ui import TaskRenderer, console, style
from .workflow_bundle import WorkflowBundle, legacy_seo_reddit_bundle

console = Console()


class Dashboard(
    DashboardVerificationMixin,
    DashboardArticlesMixin,
    DashboardTaskActionsMixin,
    DashboardProjectsMixin,
):
    """Main dashboard application."""
    
    def __init__(
        self,
        *,
        workflow_bundle: WorkflowBundle | None = None,
        runtime_config: RuntimeConfig | None = None,
    ):
        self.session = PromptSession(style=style)
        self.workflow_bundle = workflow_bundle or legacy_seo_reddit_bundle()
        self.runtime_config = runtime_config or RuntimeConfig(
            required_clis=tuple(self.workflow_bundle.required_clis)
        )
        self.project_manager = ProjectManager(
            projects_config_path=self.runtime_config.projects_config_path,
        )
        self.task_list: TaskList | None = None
        self.renderer: TaskRenderer | None = None
        self.runners: dict = {}
        self.executor: ExecutionEngine | None = None
        self.project_preflight: ProjectPreflightReport | None = None

    def _activate_project(self, project, show_report: bool = True) -> ProjectPreflightReport:
        """Activate project and run initialization/preflight checks."""
        self.project_manager.current = project
        self.task_list = TaskList(
            project,
            autonomy_mode_map=self.workflow_bundle.autonomy_mode_map,
        )
        self.renderer = TaskRenderer(self.task_list)
        self._init_runners()

        preflight = ProjectPreflight(
            repo_root=Path(project.repo_root),
            website_id=project.website_id,
            runtime_config=self.runtime_config,
            required_clis=self.workflow_bundle.required_clis,
            check_reddit_auth=self.workflow_bundle.check_reddit_auth,
        )
        report = preflight.run()
        self.project_preflight = report

        if show_report:
            self._render_project_preflight_report(project.name, report)
        return report

    def _render_project_preflight_report(self, project_name: str, report: ProjectPreflightReport) -> None:
        """Display concise project activation checks."""
        console.print(f"\n[bold]Project Initialization: {project_name}[/bold]")

        if report.created_paths:
            for path in report.created_paths:
                console.print(f"[dim]  • Created: {path}[/dim]")

        if not report.findings:
            console.print("[green]✓ No issues detected[/green]")
            return

        for finding in report.findings:
            if finding.severity == "error":
                color = "red"
                prefix = "✗"
            elif finding.severity == "warning":
                color = "yellow"
                prefix = "⚠"
            else:
                color = "green"
                prefix = "✓"
            console.print(f"[{color}]{prefix} {finding.message}[/{color}]")
            if finding.fix_hint:
                console.print(f"[dim]    Fix: {finding.fix_hint}[/dim]")

        if report.errors:
            console.print("[yellow]Project activated with blocking issues; some workflows will fail until fixed.[/yellow]")
        elif report.warnings:
            console.print("[dim]Project activated with warnings; non-critical workflows remain available.[/dim]")
        
        # Offer interactive fixes for actionable warnings
        self._offer_interactive_fixes(report)
    
    def _offer_interactive_fixes(self, report: ProjectPreflightReport) -> None:
        """Offer to auto-fix certain warnings interactively."""
        # Check for gitignore warning
        gitignore_finding = None
        for finding in report.findings:
            if finding.check == "gitignore" and finding.severity == "warning":
                gitignore_finding = finding
                break
        
        if gitignore_finding:
            console.print()
            fix = self.session.prompt("Fix gitignore now? (y/n): ")
            if fix.lower() == "y":
                success = self._run_setup_gitignore()
                if success:
                    # Remove the warning from findings
                    report.findings = [f for f in report.findings if f.check != "gitignore"]
    
    def _init_runners(self):
        """Initialize task runners for current project."""
        if not self.project_manager.current:
            return
        
        project = self.project_manager.current
        self.runners = self.workflow_bundle.build_runners(self.task_list, project, self.session)
        self.executor = ExecutionEngine(
            self.task_list,
            project,
            self.runners,
            handlers=self.workflow_bundle.build_handlers(),
        )
    
    def _clear_screen(self):
        """Clear screen and show header."""
        import os
        os.system('clear' if os.name != 'nt' else 'cls')
        
        console.print("=" * 70)
        console.print("[bold]Task Dashboard[/bold] - Just Tasks, No Campaigns")
        console.print("=" * 70)
        
        if self.project_manager.current:
            code = self.task_list._get_project_code() if self.task_list else ""
            code_str = f" [{code}]" if code else ""
            console.print(f"Project: [bold]{self.project_manager.current.name}[/bold]{code_str}")
        
        console.print()
    
    def _get_autonomy_mode(self, task_type: str) -> str:
        """Get autonomy mode for batch processing."""
        return self.workflow_bundle.autonomy_mode_map.get(task_type, "manual")
    
    def _get_execution_mode(self, task_type: str) -> str:
        """Get execution mode for display."""
        return self.workflow_bundle.execution_mode_map.get(task_type, "auto")
    
    def _get_last_published_info(self) -> tuple[str | None, int | None]:
        """Get the last published article date and days since published.
        
        Returns:
            Tuple of (date_string, days_ago) or (None, None) if no data
        """
        from datetime import datetime
        from .utils import ArticleManager
        
        if not self.project_manager.current:
            return None, None
        
        try:
            article_mgr = ArticleManager(self.project_manager.current.website_id)
            # Pass repo_root so it finds the correct articles.json
            # Only look at PUBLISHED articles, not drafts
            latest_date, _ = article_mgr.get_latest_date(
                repo_root=Path(self.project_manager.current.repo_root),
                include_drafts=False
            )
            
            if latest_date:
                days_ago = (datetime.now() - latest_date).days
                date_str = latest_date.strftime("%Y-%m-%d")
                return date_str, days_ago
        except Exception as e:
            # Debug: print error to help diagnose issues
            pass
        
        return None, None
    
    def _render_last_published_card(self):
        """Render an info card showing last published date."""
        date_str, days_ago = self._get_last_published_info()
        
        if date_str and days_ago is not None:
            if days_ago == 0:
                days_text = "[green]today[/green]"
            elif days_ago == 1:
                days_text = "[yellow]1 day ago[/yellow]"
            elif days_ago < 7:
                days_text = f"[yellow]{days_ago} days ago[/yellow]"
            else:
                days_text = f"[red]{days_ago} days ago[/red]"
            
            console.print(f"[dim]Last published:[/dim] [cyan]{date_str}[/cyan] ({days_text})")
            console.print()
    
    def _get_last_gsc_run_info(self) -> tuple[str | None, int | None]:
        """Get the last Google Search Console collection run date.
        
        Returns:
            Tuple of (date_string, days_ago) or (None, None) if no data
        """
        from datetime import datetime
        
        if not self.project_manager.current:
            return None, None
        
        try:
            # Look for gsc_collection.json in artifacts
            automation_dir = Path(self.project_manager.current.repo_root) / ".github" / "automation"
            gsc_file = automation_dir / "artifacts" / "gsc_collection.json"
            
            if gsc_file.exists():
                # Get file modification time
                mtime = gsc_file.stat().st_mtime
                run_date = datetime.fromtimestamp(mtime)
                days_ago = (datetime.now() - run_date).days
                date_str = run_date.strftime("%Y-%m-%d")
                return date_str, days_ago
                
            # Also check for any GSC collection task that was completed
            if self.task_list:
                gsc_tasks = [t for t in self.task_list.tasks 
                            if t.type == "collect_gsc" and t.status == "done" and t.completed_at]
                if gsc_tasks:
                    # Get the most recent one
                    latest_task = max(gsc_tasks, key=lambda t: t.completed_at or "")
                    if latest_task.completed_at:
                        # Parse ISO format date
                        run_date = datetime.fromisoformat(latest_task.completed_at.replace('Z', '+00:00').replace('+00:00', ''))
                        days_ago = (datetime.now() - run_date).days
                        date_str = run_date.strftime("%Y-%m-%d")
                        return date_str, days_ago
        except Exception:
            pass
        
        return None, None
    
    def _render_gsc_status_card(self):
        """Render an info card showing last GSC collection run."""
        date_str, days_ago = self._get_last_gsc_run_info()
        
        if date_str and days_ago is not None:
            if days_ago == 0:
                days_text = "[green]today[/green]"
            elif days_ago == 1:
                days_text = "[yellow]1 day ago[/yellow]"
            elif days_ago < 14:
                days_text = f"[yellow]{days_ago} days ago[/yellow]"
            elif days_ago < 30:
                days_text = f"[red]{days_ago} days ago[/red]"
            else:
                days_text = f"[red bold]{days_ago} days ago[/red bold]"
            
            console.print(f"[dim]Last GSC collection:[/dim] [cyan]{date_str}[/cyan] ({days_text})")
            console.print()
    
    def _check_system_integrity(self) -> list[str]:
        """
        Check for common system integrity issues.
        
        Returns list of issues found (empty if all good).
        Called once when dashboard loads.
        """
        import json
        from collections import Counter
        
        issues = []
        
        if not self.project_manager.current:
            return issues
        
        p = self.project_manager.current
        repo_root = p.repo_root
        
        from .utils import ArticleManager
        article_mgr = ArticleManager(p.website_id)
        
        # Check 1: articles.json exists and is valid
        articles_json = article_mgr.get_articles_json_path(repo_root)
        if not articles_json:
            issues.append("articles.json not found")
            return issues
        
        try:
            data = json.loads(articles_json.read_text())
            articles = data.get("articles", [])
        except Exception as e:
            issues.append(f"articles.json is invalid: {e}")
            return issues
        
        # Check 2: Duplicate IDs
        ids = [a.get("id") for a in articles if a.get("id")]
        id_counts = Counter(ids)
        duplicates = [id for id, count in id_counts.items() if count > 1]
        if duplicates:
            issues.append(f"Duplicate IDs found: {duplicates}")
        
        # Check 3: Duplicate dates
        dates = [a.get("published_date") for a in articles if a.get("published_date")]
        date_counts = Counter(dates)
        dup_dates = {d: c for d, c in date_counts.items() if c > 1}
        if dup_dates:
            for d, c in list(dup_dates.items())[:3]:
                issues.append(f"Date {d} has {c} articles")
        
        # Check 4: nextArticleId correctness
        if articles:
            max_id = max(ids) if ids else 0
            expected_next = max_id + 1
            actual_next = data.get("nextArticleId")
            if actual_next != expected_next:
                issues.append(f"nextArticleId should be {expected_next}, found {actual_next}")
        
        # Check 5: Content file existence
        content_dir = article_mgr.get_content_dir(repo_root)
        if content_dir:
            missing_files = []
            for article in articles[:20]:  # Check first 20 for performance
                file_path = article.get("file", "")
                if file_path:
                    # Handle both ./content/ and relative paths
                    if file_path.startswith("./content/"):
                        filename = file_path.replace("./content/", "")
                    else:
                        from pathlib import Path as P
                        filename = P(file_path).name
                    
                    full_path = content_dir / filename
                    if not full_path.exists():
                        missing_files.append(f"ID {article.get('id')}: {filename}")
            
            if missing_files:
                issues.append(f"{len(missing_files)} content files missing (showing first 3):")
                for m in missing_files[:3]:
                    issues.append(f"  {m}")
        
        # Check 6: Slug alignment
        mismatches = article_mgr.check_slug_alignment(repo_root)
        if mismatches:
            issues.append(f"{len(mismatches)} slug/filename mismatches detected")
        
        return issues
    
    def _sync_task_status_with_files(self):
        """
        Sync task status with actual file existence.
        
        Marks 'Write article' tasks as done if their files exist,
        and creates linking tasks for them.
        """
        from .utils import ArticleManager
        
        if not self.project_manager.current or not self.task_list:
            return
        
        try:
            article_mgr = ArticleManager(self.project_manager.current.website_id)
            repo_root = Path(self.project_manager.current.repo_root)
            content_dir = article_mgr.get_content_dir(repo_root)
            
            if not content_dir:
                return
            
            # Get all content files
            content_files = set(f.name for f in content_dir.glob("*.mdx"))
            
            # Check each write_article task
            for task in self.task_list.tasks:
                if task.type != "write_article":
                    continue
                
                # Skip if already done
                if task.status == "done":
                    continue
                
                # Extract article title from task
                task_title = task.title.replace("Write article: ", "").strip()
                
                # Build expected filename pattern
                import re
                slug = re.sub(r'[^\w\s-]', '', task_title).strip().lower()
                slug = re.sub(r'[-\s]+', '_', slug)
                
                # Check if any file matches this slug
                file_exists = any(slug in fname for fname in content_files)
                
                if file_exists:
                    # Mark task as done
                    console.print(f"[dim]Auto-completing: '{task_title}' (file exists)[/dim]")
                    task.status = "done"
                    task.completed_at = __import__('datetime').datetime.now().isoformat()
                    
                    # Create linking task if not exists
                    linking_exists = any(
                        t.type == "cluster_and_link" and t.category == f"linking:article_id={task.id}"
                        for t in self.task_list.tasks
                    )
                    
                    if not linking_exists:
                        try:
                            linking_task = self.task_list.create_task(
                                task_type="cluster_and_link",
                                title=f"Link article: {task_title}",
                                phase="implementation",
                                priority="medium",
                                depends_on=task.id,
                                parent_task=task.id,
                                category=f"linking:task_{task.id}"
                            )
                            console.print(f"[dim]  Created linking task: {linking_task.title}[/dim]")
                        except Exception:
                            pass
            
            self.task_list.save()
            
        except Exception as e:
            console.print(f"[dim]Task sync warning: {e}[/dim]")
    
    def _check_task_suggestions(self):
        """
        Check for task suggestions based on time since last run.
        
        This provides automation-assisted task creation - suggests tasks
        that haven't been run recently, but lets the user decide.
        """
        from .utils import TaskGenerator, format_time_since
        
        if not self.task_list:
            return
        
        try:
            generator = TaskGenerator(self.task_list)
            suggestions = generator.analyze()
            
            if not suggestions:
                return
            
            # Show suggestions header
            console.print(f"\n[bold cyan]📋 Task Suggestions[/bold cyan]")
            console.print(f"[dim]Based on when steps were last completed:[/dim]\n")
            
            # Show each suggestion
            for i, suggestion in enumerate(suggestions[:5], 1):
                icon = suggestion.icon
                priority_color = {"high": "red", "medium": "yellow", "low": "dim"}.get(suggestion.priority, "white")
                
                console.print(f"  {i}. {icon} [{priority_color}]{suggestion.title}[/{priority_color}]")
                if suggestion.days_since_last:
                    time_str = format_time_since(suggestion.days_since_last)
                    console.print(f"     [dim]Last run: {time_str} — {suggestion.reason}[/dim]")
                else:
                    console.print(f"     [dim]Never run — {suggestion.reason}[/dim]")
            
            if len(suggestions) > 5:
                console.print(f"  [dim]... and {len(suggestions) - 5} more[/dim]")
            
            console.print()
            
            # Ask if user wants to create suggested tasks
            choice = self.session.prompt("Create suggested tasks? (all/number/skip): ").strip().lower()
            
            if choice == "all":
                created = 0
                for suggestion in suggestions:
                    task = self.task_list.create_task(
                        task_type=suggestion.task_type,
                        title=suggestion.title,
                        phase=suggestion.phase,
                        priority=suggestion.priority,
                        category=suggestion.category,
                    )
                    if suggestion.depends_on:
                        task.depends_on = suggestion.depends_on
                    created += 1
                
                self.task_list.save()
                console.print(f"[green]✓ Created {created} task(s)[/green]\n")
                self.session.prompt("Press Enter to continue...")
                
            elif choice.isdigit():
                # Create specific suggestion by number
                idx = int(choice) - 1
                if 0 <= idx < len(suggestions):
                    suggestion = suggestions[idx]
                    task = self.task_list.create_task(
                        task_type=suggestion.task_type,
                        title=suggestion.title,
                        phase=suggestion.phase,
                        priority=suggestion.priority,
                        category=suggestion.category,
                    )
                    if suggestion.depends_on:
                        task.depends_on = suggestion.depends_on
                    
                    self.task_list.save()
                    console.print(f"[green]✓ Created: {suggestion.title}[/green]\n")
                    self.session.prompt("Press Enter to continue...")
                else:
                    console.print("[yellow]Invalid selection[/yellow]\n")
                    self.session.prompt("Press Enter to continue...")
            
            # If 'skip' or anything else, just continue without creating
            
        except Exception as e:
            # Silently fail - suggestions are optional
            console.print(f"[dim]Could not generate suggestions: {e}[/dim]")
    
    def _run_bulk_linking(self):
        """Run linking workflow for articles that need internal links."""
        from .tasks import LinkingRunner
        
        if not self.project_manager.current:
            console.print("[red]No project selected[/red]")
            self.session.prompt("\nPress Enter...")
            return
        
        p = self.project_manager.current
        repo_root = Path(p.repo_root)
        
        # Get articles that need linking
        from .utils import ArticleManager
        article_mgr = ArticleManager(p.website_id)
        
        articles_json = article_mgr.get_articles_json_path(repo_root)
        if not articles_json:
            console.print("[red]Could not find articles.json[/red]")
            self.session.prompt("\nPress Enter...")
            return
        
        try:
            import json
            data = json.loads(articles_json.read_text())
            articles = data.get("articles", [])
            
            # Find recent articles (last 10) without linking tasks
            recent_articles = sorted(articles, key=lambda a: a.get("id", 0), reverse=True)[:10]
            
            # Check which ones need linking
            needs_linking = []
            for article in recent_articles:
                article_id = article.get("id")
                title = article.get("title", "Untitled")
                
                # Check if linking task exists
                linking_exists = any(
                    t.type == "cluster_and_link" and 
                    (f"linking:article_id={article_id}" in t.category or title in t.title)
                    for t in self.task_list.tasks
                ) if self.task_list else False
                
                if not linking_exists:
                    needs_linking.append(article)
            
            if not needs_linking:
                console.print("[green]✓ All recent articles have linking tasks[/green]")
                self.session.prompt("\nPress Enter...")
                return
            
            console.print(f"\n[bold]Articles needing internal links:[/bold]")
            for i, article in enumerate(needs_linking, 1):
                console.print(f"  {i}. ID {article['id']}: {article['title'][:50]}...")
            
            # Option to run for all or select specific
            console.print(f"\n[dim]Options:[/dim]")
            console.print(f"  1. Create linking tasks for all {len(needs_linking)} articles")
            console.print(f"  2. Run linking now for all (auto-process)")
            console.print(f"  3. Select specific articles")
            console.print(f"  q. Cancel")
            
            choice = self.session.prompt("\nChoice: ")
            
            if choice == "1":
                # Create tasks only
                for article in needs_linking:
                    task = self.task_list.create_task(
                        task_type="cluster_and_link",
                        title=f"Link article: {article['title']}",
                        phase="implementation",
                        priority="medium",
                        category=f"linking:article_id={article['id']}"
                    )
                self.task_list.save()
                console.print(f"[green]✓ Created {len(needs_linking)} linking task(s)[/green]")
                
            elif choice == "2":
                # Run linking directly
                console.print(f"\n[cyan]Running bulk linking for {len(needs_linking)} articles...[/cyan]\n")
                
                # Create a temporary LinkingRunner
                linking_runner = LinkingRunner(self.task_list, p, self.session)
                
                # Run for each article
                for article in needs_linking:
                    console.print(f"[dim]Linking: {article['title'][:50]}...[/dim]")
                    # Create a temporary task for this article
                    temp_task = type('Task', (), {
                        'title': f"Link article: {article['title']}",
                        'category': f"linking:article_id={article['id']}"
                    })()
                    linking_runner.run(temp_task)
                
                # Mark all matching linking tasks as done
                from datetime import datetime
                marked_count = 0
                for article in needs_linking:
                    article_id = article.get("id")
                    article_title = article.get("title", "")
                    for task in self.task_list.tasks:
                        if task.type == "cluster_and_link" and task.status != "done":
                            # Match by category (article_id) or by title
                            if (task.category == f"linking:article_id={article_id}" or 
                                article_title in task.title):
                                task.status = "done"
                                task.completed_at = datetime.now().isoformat()
                                marked_count += 1
                                console.print(f"[dim]  Marked task '{task.title[:40]}...' as done[/dim]")
                
                if marked_count > 0:
                    self.task_list.save()
                    console.print(f"\n[green]✓ Marked {marked_count} linking task(s) as done[/green]")
                
                console.print(f"\n[green]✓ Bulk linking complete[/green]")
                
            elif choice == "3":
                # Select specific
                selected = self.session.prompt("Enter article numbers (comma-separated, e.g., 1,3): ")
                try:
                    indices = [int(x.strip()) - 1 for x in selected.split(",")]
                    for idx in indices:
                        if 0 <= idx < len(needs_linking):
                            article = needs_linking[idx]
                            task = self.task_list.create_task(
                                task_type="cluster_and_link",
                                title=f"Link article: {article['title']}",
                                phase="implementation",
                                priority="medium",
                                category=f"linking:article_id={article['id']}"
                            )
                    self.task_list.save()
                    console.print(f"[green]✓ Created linking task(s)[/green]")
                except ValueError:
                    console.print("[yellow]Invalid selection[/yellow]")
            
            else:
                console.print("[dim]Cancelled[/dim]")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        
        self.session.prompt("\nPress Enter...")
    
    def work_loop(self):
        """Main work loop - show tasks and work on them."""
        p = self.project_manager.current
        if not p:
            console.print("[yellow]No project selected. Choose one from Projects first.[/yellow]")
            self.session.prompt("\nPress Enter...")
            return
        
        # Load or create task list
        self.task_list = TaskList(
            p,
            autonomy_mode_map=self.workflow_bundle.autonomy_mode_map,
        )
        self.renderer = TaskRenderer(self.task_list)
        self._init_runners()
        
        # Sync task status with files (auto-complete existing articles)
        self._sync_task_status_with_files()
        
        # Run integrity check on first load (using same method as main menu)
        integrity_issues = self._auto_verify()
        
        while True:
            self._clear_screen()
            self.task_list.load()
            
            # Show integrity status (same format as main menu)
            self._render_integrity_status(integrity_issues)
            
            # Show last published info (same as main menu)
            self._render_last_published_card()
            self._render_gsc_status_card()
            
            # Clear issues after first display
            if integrity_issues:
                integrity_issues = []
            
            # Note: Task suggestions disabled - was showing after every task
            # self._check_task_suggestions()
            
            if not self.task_list.tasks:
                console.print("[yellow]No tasks yet. Let's create some.[/yellow]\n")
                self.create_initial_tasks()
                continue
            
            self.renderer.render_task_list()
            self.renderer.render_ready_tasks()
            
            # Check for batch-ready tasks
            from .batch import BatchProcessor
            temp_processor = BatchProcessor(self.task_list, self)
            batch_summary = temp_processor.get_batch_summary()
            
            console.print("\n[bold]Actions:[/bold]")
            console.print("  1. Work on a task")
            
            if self.task_list.get_by_status("review"):
                console.print("  2. Mark reviewed tasks done")
            
            has_specs = any(t.spec_file for t in self.task_list.tasks)
            if has_specs:
                console.print("  v. View specifications")
            
            if batch_summary and batch_summary["total_ready"] > 0:
                console.print(f"  [cyan]b. Batch Mode[/cyan] ([green]{batch_summary['total_ready']}[/green] ready)")
            
            type_counts = self.task_list.get_unique_task_types()
            if type_counts:
                console.print(f"  [cyan]t. Bulk by Type[/cyan] ([green]{len(type_counts)}[/green] types)")
            
            console.print("  c. Create articles (simple)")
            console.print("  l. Link existing articles (bulk)")
            console.print("  d. Delete task(s)")
            console.print("  q. Back")
            
            # Quick Task Creation Section
            console.print("\n[bold dim]Quick Add Tasks:[/bold dim]")
            console.print("  [dim]g.[/dim] Collect GSC       [dim]p.[/dim] Collect PostHog    [dim]k.[/dim] Research Keywords")
            console.print("  [dim]r.[/dim] Reddit Search     [dim]x.[/dim] Landing Pages      [dim]n.[/dim] GSC Performance Analysis")
            
            choice = self.session.prompt("\nChoice: ").strip()
            
            if choice == "1":
                self.select_and_work_on_task()
            elif choice == "2":
                self.mark_task_reviewed()
            elif choice.lower() == "l":
                self._run_bulk_linking()
            elif choice.lower() == "v" and has_specs:
                self.view_specifications()
            elif choice.lower() == "b" and batch_summary and batch_summary["total_ready"] > 0:
                self.run_batch_mode()
            elif choice.lower() == "t" and type_counts:
                self.run_bulk_by_type()
            elif choice.lower() == "g":
                self._quick_create_task("gsc")
            elif choice.lower() == "p":
                self._quick_create_task("posthog")
            elif choice.lower() == "k":
                self._quick_create_task("keywords")
            elif choice.lower() == "r":
                self._quick_create_task("reddit")
            elif choice.lower() == "x":
                self._quick_create_task("landing_pages")
            elif choice.lower() == "n":
                self._quick_create_task("performance")
            elif choice.lower() == "c":
                self._run_simple_article_creation()
            elif choice.lower() == "d":
                self.delete_task()
            elif choice == "q":
                break
    
    def _run_simple_article_creation(self):
        """Run simplified article creation workflow."""
        from pathlib import Path
        from .utils import ArticleManager
        from .tasks import ContentRunner
        
        if not self.project_manager.current:
            console.print("[red]No project selected[/red]")
            self.session.prompt("\nPress Enter...")
            return
        
        p = self.project_manager.current
        repo_root = Path(p.repo_root)
        
        # Check content directory exists
        article_mgr = ArticleManager(p.website_id)
        content_dir = article_mgr.get_content_dir(repo_root)
        
        if not content_dir:
            console.print("[red]✗ Content directory not found[/red]")
            self.session.prompt("\nPress Enter...")
            return
        
        # Show current status
        latest_date, _ = article_mgr.get_latest_date(repo_root, include_drafts=True)
        next_id = article_mgr.get_next_id(repo_root)
        
        console.print("\n[bold cyan]Simple Article Creation[/bold cyan]")
        console.print("[dim]Create multiple articles with automatic ID/date assignment.[/dim]\n")
        
        if latest_date:
            console.print(f"[dim]Latest article: {latest_date.strftime('%Y-%m-%d')}[/dim]")
        console.print(f"[dim]Next ID: {next_id}[/dim]")
        console.print()
        
        # Ask how many articles
        count_str = self.session.prompt("How many articles to create? (1-4): ")
        try:
            count = int(count_str)
            if count < 1 or count > 4:
                console.print("[yellow]Please enter a number between 1 and 4.[/yellow]")
                self.session.prompt("\nPress Enter...")
                return
        except ValueError:
            console.print("[yellow]Invalid number.[/yellow]")
            self.session.prompt("\nPress Enter...")
            return
        
        # Confirm
        confirm = self.session.prompt(f"\nCreate {count} article(s)? (y/n): ")
        if confirm.lower() != "y":
            console.print("[yellow]Cancelled.[/yellow]")
            self.session.prompt("\nPress Enter...")
            return
        
        # Run simplified creation
        content_runner = ContentRunner(self.task_list, p, self.session)
        created = content_runner.create_multiple_articles(count, repo_root)
        
        if created:
            console.print(f"\n[green]✓ Successfully created {len(created)} article(s)[/green]")
        else:
            console.print("\n[yellow]No articles were created.[/yellow]")
        
        self.session.prompt("\nPress Enter to continue...")
    
    def run_batch_mode(self):
        """Run batch processing mode."""
        from .batch import BatchProcessor, BatchConfig
        
        if not self.task_list:
            console.print("[red]No task list loaded[/red]")
            self.session.prompt("\nPress Enter...")
            return
        
        temp_processor = BatchProcessor(self.task_list, self)
        summary = temp_processor.get_batch_summary()
        
        if summary["total_ready"] == 0:
            console.print("[yellow]No autonomous tasks ready.[/yellow]")
            self.session.prompt("\nPress Enter...")
            return
        
        # Show preview
        console.print(f"\n[bold cyan]🚀 Batch Mode Preview[/bold cyan]\n")
        console.print(f"Ready tasks: [green]{summary['total_ready']}[/green]")
        console.print(f"  [dim]- Fully automatic: {summary['automatic']}[/dim]")
        console.print(f"  [dim]- Batchable: {summary['batchable']}[/dim]")
        console.print()
        
        console.print("[bold]Next tasks in queue:[/bold]")
        for i, task in enumerate(summary["tasks"][:5], 1):
            autonomy = self._get_autonomy_mode(task.type)
            icon = "⚡" if autonomy == "automatic" else "📝"
            console.print(f"  {i}. {icon} [{task.priority[0].upper()}] {task.title[:45]}...")
        
        if len(summary["tasks"]) > 5:
            console.print(f"  [dim]... and {len(summary['tasks']) - 5} more[/dim]")
        
        console.print()
        
        # Configure
        max_tasks = self.session.prompt("Max tasks to process (1-20, default 10): ")
        try:
            max_tasks = max(1, min(20, int(max_tasks)))
        except ValueError:
            max_tasks = 10
        
        auto_approve = True
        if summary["batchable"] > 0:
            confirm = self.session.prompt(
                f"Process {summary['batchable']} content tasks without confirmation? (y/n): "
            )
            auto_approve = confirm.lower() == "y"
        
        confirm = self.session.prompt(f"Start batch processing up to {max_tasks} tasks? (y/n): ")
        
        if confirm.lower() != "y":
            console.print("[dim]Batch cancelled.[/dim]")
            self.session.prompt("\nPress Enter...")
            return
        
        # Configure and run
        config = BatchConfig(
            max_tasks=max_tasks,
            auto_approve_batchable=auto_approve,
            pause_on_error=True,
            pause_on_spec=True,
            rate_limit_delay=5
        )
        
        processor = BatchProcessor(self.task_list, self, config)
        
        try:
            result = processor.run_batch(console)
            
            console.print()
            if result["status"] == "complete":
                console.print(f"[bold green]✓ Batch completed[/bold green]")
            elif result["status"] == "paused":
                console.print(f"[bold yellow]⏸ Batch paused[/bold yellow]")
            elif result["status"] == "error":
                console.print(f"[bold red]✗ Batch stopped[/bold red]")
            
            console.print(f"[dim]Processed: {result['processed']} tasks[/dim]")
            
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠ Batch interrupted[/yellow]")
            processor.stop()
        
        self.session.prompt("\nPress Enter to continue...")
    
    def run_bulk_by_type(self):
        """Run bulk processing filtered by specific task type."""
        from .batch import BatchProcessor, BatchConfig
        
        if not self.task_list:
            return
        
        type_counts = self.task_list.get_unique_task_types()
        
        if not type_counts:
            console.print("[yellow]No ready tasks available.[/yellow]")
            self.session.prompt("\nPress Enter...")
            return
        
        console.print("\n[bold cyan]📦 Bulk by Type[/bold cyan]\n")
        
        console.print("[bold]Available Task Types:[/bold]")
        for i, (task_type, count) in enumerate(type_counts[:15], 1):
            autonomy = self._get_autonomy_mode(task_type)
            icon = {"automatic": "⚡", "batchable": "📝", "spec": "📋", "manual": "👤"}.get(autonomy, "?")
            console.print(f"  {i}. {icon} {task_type} [green]({count} ready)[/green]")
        
        console.print("\n  c. Cancel")
        
        choice = self.session.prompt("\nSelect type #: ")
        
        if choice.lower() == "c":
            return
        
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(type_counts):
                raise ValueError()
            
            selected_type = type_counts[idx][0]
            ready_tasks = self.task_list.get_ready_by_type(selected_type)
            
            if not ready_tasks:
                console.print(f"[yellow]No ready tasks of type '{selected_type}' found.[/yellow]")
                self.session.prompt("\nPress Enter...")
                return
            
            autonomy = self._get_autonomy_mode(selected_type)
            console.print(f"\n[bold]Selected: {selected_type}[/bold]")
            console.print(f"[dim]Ready tasks: {len(ready_tasks)}[/dim]\n")
            selected_task_ids: set[str] | None = None
            task_type_defaults = {}

            if selected_type == "reddit_reply":
                (
                    selected_tasks,
                    task_type_defaults,
                    cancelled,
                ) = self._configure_reddit_bulk_selection(ready_tasks)
                if cancelled:
                    console.print("[dim]Cancelled.[/dim]")
                    self.session.prompt("\nPress Enter...")
                    return
                ready_tasks = selected_tasks
                selected_task_ids = {task.id for task in selected_tasks}
                max_tasks = len(selected_tasks)
            else:
                # Configure
                max_tasks = self.session.prompt(
                    f"Max tasks (1-{len(ready_tasks)}, default {min(5, len(ready_tasks))}): "
                )
                try:
                    max_tasks = max(1, min(len(ready_tasks), int(max_tasks)))
                except ValueError:
                    max_tasks = min(5, len(ready_tasks))
                
                confirm = self.session.prompt(f"\nProcess {max_tasks} '{selected_type}' tasks? (y/n): ")
                
                if confirm.lower() != "y":
                    console.print("[dim]Cancelled.[/dim]")
                    self.session.prompt("\nPress Enter...")
                    return
            
            # Create filtered processor
            config = BatchConfig(
                max_tasks=max_tasks,
                auto_approve_batchable=(autonomy in ("automatic", "batchable")),
                pause_on_error=True,
                rate_limit_delay=3 if selected_type == "write_article" else 5,
                task_type_defaults=task_type_defaults
            )

            selected_order: dict[str, int] = {}
            if selected_task_ids:
                selected_order = {
                    task.id: index
                    for index, task in enumerate(ready_tasks)
                }
            
            class FilteredBatchProcessor(BatchProcessor):
                def get_ready_autonomous_tasks(self):
                    tasks = self.task_list.get_ready_by_type(selected_type)
                    if selected_task_ids:
                        tasks = [task for task in tasks if task.id in selected_task_ids]
                        tasks.sort(key=lambda task: selected_order.get(task.id, 999999))
                    return tasks
            
            processor = FilteredBatchProcessor(self.task_list, self, config)
            
            try:
                result = processor.run_batch(console)
                
                console.print()
                if result["status"] == "complete":
                    console.print(f"[bold green]✓ Bulk processing complete[/bold green]")
                elif result["status"] == "paused":
                    console.print(f"[bold yellow]⏸ Bulk processing paused[/bold yellow]")
                elif result["status"] == "error":
                    console.print(f"[bold red]✗ Bulk processing stopped[/bold red]")
                
                console.print(f"[dim]Processed: {result['processed']} {selected_type} tasks[/dim]")
                
            except KeyboardInterrupt:
                console.print("\n[yellow]⚠ Bulk processing interrupted[/yellow]")
                processor.stop()
            
            self.session.prompt("\nPress Enter to continue...")
            
        except (ValueError, IndexError):
            console.print("[red]Invalid selection.[/red]")
            self.session.prompt("\nPress Enter...")

    def _configure_reddit_bulk_selection(self, ready_tasks):
        """Configure selected reddit_reply opportunities for batch execution."""
        from rich.table import Table

        console.print("[bold cyan]Reddit Opportunity Review[/bold cyan]")
        console.print("[dim]Select which opportunities to process in this batch.[/dim]\n")

        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="cyan", width=4)
        table.add_column("Subreddit", width=14)
        table.add_column("Posted", width=12)
        table.add_column("Age", width=12)
        table.add_column("Title", overflow="fold")

        for i, task in enumerate(ready_tasks, 1):
            subreddit = f"r/{task.subreddit}" if task.subreddit else "-"
            posted = task.post_date or "-"
            age_label, age_color = self._reddit_age_display(task.post_date)
            title = task.title.replace("Reply: ", "").strip()[:75]
            table.add_row(
                str(i),
                subreddit,
                posted,
                f"[{age_color}]{age_label}[/{age_color}]",
                title,
            )
        console.print(table)
        console.print()
        console.print("[dim]Enter numbers (e.g. 1,3,5), 'all', or 'c' to cancel.[/dim]")

        selection = self.session.prompt("\nSelect opportunities: ").strip()
        if not selection or selection.lower() in {"c", "cancel"}:
            return [], {}, True

        if selection.lower() in {"a", "all"}:
            selected_tasks = list(ready_tasks)
        else:
            selected_indices, invalid = self._parse_selection_indices(selection, len(ready_tasks))
            if invalid:
                console.print(f"[yellow]Ignored invalid selections: {', '.join(invalid)}[/yellow]")
            selected_tasks = [ready_tasks[idx] for idx in selected_indices]

        if not selected_tasks:
            console.print("[yellow]No valid opportunities selected.[/yellow]")
            return [], {}, True

        console.print(f"[green]Selected {len(selected_tasks)} opportunity(s).[/green]")

        adjust = self.session.prompt("Apply bulk find/replace to selected replies? (y/n): ").strip().lower()
        if adjust == "y":
            self._bulk_adjust_reddit_reply_text(selected_tasks)

        console.print("\n[bold cyan]Batch Action for Selected Opportunities:[/bold cyan]")
        console.print("  1. Auto-post selected replies (single confirmation)")
        console.print("  2. Copy + mark selected as posted (manual post)")
        console.print("  3. Skip selected opportunities")
        console.print("  4. Keep selected for later (cancel batch)")

        choice = self.session.prompt("\nAction (1/2/3/4): ").strip()
        action_map = {
            "1": "auto_post",
            "2": "copy_and_mark",
            "3": "skip",
            "4": "keep",
        }
        action = action_map.get(choice)
        if not action or action == "keep":
            return [], {}, True

        if action == "auto_post":
            auth_ready, auth_hint = self._reddit_bulk_auth_readiness()
            if not auth_ready:
                console.print(f"[red]Cannot auto-post: {auth_hint}[/red]")
                return [], {}, True

            eligible_tasks = [task for task in selected_tasks if not self._reddit_post_is_too_old(task.post_date)]
            stale_count = len(selected_tasks) - len(eligible_tasks)
            if stale_count:
                console.print(
                    f"[yellow]Excluded {stale_count} selected opportunity(s) older than 14 days (Reddit auto-post blocked).[/yellow]"
                )
            selected_tasks = eligible_tasks

            if not selected_tasks:
                console.print("[yellow]No eligible opportunities left to auto-post.[/yellow]")
                return [], {}, True

            final_confirm = self.session.prompt(
                f"Final confirmation: auto-post {len(selected_tasks)} selected replies now? Type 'yes': "
            ).strip().lower()
            if final_confirm != "yes":
                return [], {}, True

            return selected_tasks, {
                "auto_confirm": True,
                "reddit_reply": {"action": "auto_post", "skip_confirm": True},
            }, False

        confirm = self.session.prompt(
            f"Apply '{action}' to {len(selected_tasks)} selected opportunity(s)? (y/n): "
        ).strip().lower()
        if confirm != "y":
            return [], {}, True

        return selected_tasks, {"reddit_reply": {"action": action}}, False

    def _parse_selection_indices(self, selection: str, max_count: int) -> tuple[list[int], list[str]]:
        """Parse comma-separated 1-based indices from user input."""
        selected: list[int] = []
        invalid: list[str] = []
        seen: set[int] = set()

        for token in selection.split(","):
            item = token.strip()
            if not item:
                continue
            if not item.isdigit():
                invalid.append(item)
                continue
            idx = int(item) - 1
            if idx < 0 or idx >= max_count:
                invalid.append(item)
                continue
            if idx in seen:
                continue
            seen.add(idx)
            selected.append(idx)

        return selected, invalid

    def _reddit_age_display(self, post_date: str | None) -> tuple[str, str]:
        """Return display label and color for a Reddit post date."""
        if not post_date:
            return "unknown", "dim"

        try:
            post_dt = datetime.strptime(post_date, "%Y-%m-%d")
            days_old = (datetime.now() - post_dt).days
        except ValueError:
            return post_date, "dim"

        if days_old < 0:
            return f"in {abs(days_old)}d", "cyan"
        if days_old == 0:
            return "today", "green"
        if days_old == 1:
            return "1 day", "green"
        if days_old <= 3:
            return f"{days_old} days", "green"
        if days_old <= 14:
            return f"{days_old} days", "yellow"
        return f"{days_old} days (stale)", "red"

    def _reddit_post_is_too_old(self, post_date: str | None) -> bool:
        """Return True when Reddit post is older than auto-post policy."""
        if not post_date:
            return False
        try:
            post_dt = datetime.strptime(post_date, "%Y-%m-%d")
            return (datetime.now() - post_dt).days > 14
        except ValueError:
            return False

    def _reddit_bulk_auth_readiness(self) -> tuple[bool, str]:
        """Check Reddit auth readiness before bulk auto-post."""
        reddit_runner = self.runners.get("reddit")
        if not reddit_runner or not hasattr(reddit_runner, "_reddit_auth_status"):
            return False, "Reddit runner unavailable"

        auth_ready, auth_hint, _token = reddit_runner._reddit_auth_status()
        return auth_ready, auth_hint

    def _bulk_adjust_reddit_reply_text(self, selected_tasks) -> None:
        """Apply an optional bulk find/replace to selected Reddit replies."""
        find_text = self.session.prompt("Find text (blank to skip): ")
        if not find_text:
            console.print("[dim]No changes applied.[/dim]")
            return

        replace_text = self.session.prompt("Replace with: ")
        changed_tasks = 0

        for task in selected_tasks:
            if not task.notes or find_text not in task.notes:
                continue
            task.notes = task.notes.replace(find_text, replace_text)
            changed_tasks += 1

        if changed_tasks:
            self.task_list.save()
            console.print(f"[green]Updated {changed_tasks} selected reply draft(s).[/green]")
        else:
            console.print("[dim]No selected replies contained that text.[/dim]")
    
    def _show_reddit_history(self):
        """Show Reddit posting history for current project."""
        import json

        repo_root = None
        if self.project_manager.current:
            repo_root = self.project_manager.current.repo_root
        history_file = resolve_reddit_history_path(repo_root)
        
        if not history_file.exists():
            console.print("[yellow]No history file found.[/yellow]")
            return
        
        try:
            data = json.loads(history_file.read_text())
            posted = data.get("posted", [])
            skipped = data.get("skipped", [])
            
            console.print("\n[bold]Reddit Posting History[/bold]\n")
            console.print(f"Total Posted: [green]{len(posted)}[/green]")
            console.print(f"Total Skipped: [yellow]{len(skipped)}[/yellow]")
            
            if posted:
                console.print("\n[bold]Recently Posted:[/bold]")
                # Show last 10 posts
                for p in posted[-10:]:
                    if isinstance(p, dict):
                        title = p.get('title', 'Unknown')[:50]
                        post_id = p.get('post_id', 'unknown')
                        console.print(f"  • {title}... [dim]({post_id})[/dim]")
                    else:
                        console.print(f"  • {p}")
            
            if skipped:
                console.print("\n[bold]Recently Skipped:[/bold]")
                for s in skipped[-5:]:
                    if isinstance(s, dict):
                        reason = s.get('reason', 'No reason')
                        post_id = s.get('post_id', 'unknown')
                        console.print(f"  • {post_id} [dim]({reason})[/dim]")
                    else:
                        console.print(f"  • {s}")
                        
        except (json.JSONDecodeError, IOError) as e:
            console.print(f"[red]Error reading history: {e}[/red]")
    
    def _check_all_posthog_configs(self):
        """Check PostHog configuration for all projects."""
        from .tasks.collection import CollectionRunner
        from rich.table import Table
        
        console.print("\n[bold cyan]PostHog Configuration Check[/bold cyan]\n")
        
        results = CollectionRunner.verify_posthog_configs()
        
        if not results:
            console.print("[yellow]No projects configured.[/yellow]")
            return
        
        # Count statuses
        ok_count = sum(1 for r in results if r["status"] == "ok")
        missing_count = sum(1 for r in results if r["status"] == "missing")
        invalid_count = sum(1 for r in results if r["status"] == "invalid")
        
        # Summary
        console.print(f"[green]✓ Configured:[/green] {ok_count}")
        if missing_count:
            console.print(f"[red]✗ Missing:[/red] {missing_count}")
        if invalid_count:
            console.print(f"[yellow]⚠ Invalid:[/yellow] {invalid_count}")
        console.print()
        
        # Detailed table
        table = Table(show_header=True)
        table.add_column("Project")
        table.add_column("Status")
        table.add_column("Details")
        
        for r in results:
            status_color = {
                "ok": "green",
                "missing": "red",
                "invalid": "yellow",
                "error": "red"
            }.get(r["status"], "white")
            
            status_icon = {
                "ok": "✓",
                "missing": "✗",
                "invalid": "⚠",
                "error": "✗"
            }.get(r["status"], "?")
            
            table.add_row(
                r["project"],
                f"[{status_color}]{status_icon} {r['status']}[/{status_color}]",
                r.get("message", "")
            )
        
        console.print(table)
        
        # Action items
        if missing_count > 0:
            console.print("\n[yellow]Action Required:[/yellow]")
            console.print("Create posthog_config.json in each project's .github/automation/ folder:")
            console.print("""
{
  "project_id": <your_posthog_project_id>,
  "api_key_env": "POSTHOG",
  "dashboard_names": [],
  "base_url": "https://us.i.posthog.com"
}
""")
            console.print("[dim]Find your project ID in PostHog: Settings → Project ID[/dim]")
    
    def _auto_verify(self) -> list[str]:
        """Quick auto-verify on startup. Returns issues found."""
        issues = []
        
        if not self.project_manager.current:
            return issues
        
        # Run integrity check
        try:
            from .utils import ArticleManager
            article_mgr = ArticleManager(self.project_manager.current.website_id)
            issues = article_mgr.check_integrity(self.project_manager.current.repo_root)
        except Exception:
            pass
        
        return issues
    
    def _render_integrity_status(self, issues: list[str]):
        """Render integrity check status on menu."""
        if not issues:
            console.print("[dim]System check:[/dim] [green]✓ All good[/green]")
        else:
            console.print(f"[dim]System check:[/dim] [yellow]⚠ {len(issues)} issue(s) found[/yellow]")
            for issue in issues[:3]:
                console.print(f"  [yellow]• {issue}[/yellow]")
            if len(issues) > 3:
                console.print(f"  [dim]... and {len(issues) - 3} more (run 'v' for details)[/dim]")
        console.print()

    def _run_menu_workflow_task(self, task_type: str, title: str) -> bool:
        """Create/reuse a workflow task and execute it via the execution engine."""
        if not self.project_manager.current:
            console.print("[red]No project selected[/red]")
            return False

        if not self.task_list:
            self.task_list = TaskList(
                self.project_manager.current,
                autonomy_mode_map=self.workflow_bundle.autonomy_mode_map,
            )
            self._init_runners()

        if not self.executor:
            console.print("[red]Execution engine is not initialized[/red]")
            return False

        existing = next(
            (
                task
                for task in self.task_list.tasks
                if task.type == task_type and task.status in ("todo", "in_progress")
            ),
            None,
        )

        phase_by_type = {
            "publish_content": "implementation",
            "indexing_diagnostics": "verification",
            "analyze_gsc_performance": "research",
        }
        task = existing or self.task_list.create_task(
            task_type=task_type,
            title=title,
            phase=phase_by_type.get(task_type, "implementation"),
            priority="medium",
            execution_mode="manual",
        )

        result = self.executor.execute_task(task)
        # Handle both old bool return and new tuple return
        if isinstance(result, tuple):
            success, _ = result
        else:
            success = result
        self.task_list.save()
        return success

    def _run_orchestration_now(self):
        """Run bounded autonomous orchestration for the current project."""
        if not self.project_manager.current:
            console.print("[red]No project selected[/red]")
            return
        if not self.task_list:
            self.task_list = TaskList(
                self.project_manager.current,
                autonomy_mode_map=self.workflow_bundle.autonomy_mode_map,
            )
            self._init_runners()
        if not self.executor:
            console.print("[red]Execution engine is not initialized[/red]")
            return

        service = OrchestratorService(
            task_list=self.task_list,
            project=self.project_manager.current,
            executor=self.executor,
            runners=self.runners,
            autonomy_mode_map=self.workflow_bundle.autonomy_mode_map,
        )
        policy = service.policy_engine.load_or_create()

        console.print("\n[bold]Orchestration Run[/bold]")
        console.print("[dim]Runs ready tasks through policy-bounded autonomous execution.[/dim]")
        console.print(f"[dim]Safety limits: {policy.max_steps_per_run} steps, {policy.max_runtime_minutes}min max runtime[/dim]\n")

        steps_raw = self.session.prompt(f"Max steps [{policy.max_steps_per_run}]: ").strip()
        max_steps = None
        if steps_raw:
            try:
                max_steps = max(1, int(steps_raw))
            except ValueError:
                console.print("[yellow]Invalid step count; using policy default.[/yellow]")

        runtime_raw = self.session.prompt(f"Max runtime minutes [{policy.max_runtime_minutes}]: ").strip()
        max_runtime = None
        if runtime_raw:
            try:
                max_runtime = max(1, int(runtime_raw))
            except ValueError:
                console.print("[yellow]Invalid runtime; using policy default.[/yellow]")

        autopost_default = "yes" if policy.reddit_autopost_enabled else "no"
        autopost_raw = self.session.prompt(
            f"Enable Reddit auto-post this run? (yes/no/blank=policy) [{autopost_default}]: "
        ).strip().lower()
        reddit_autopost = None
        if autopost_raw in {"yes", "y"}:
            reddit_autopost = True
        elif autopost_raw in {"no", "n"}:
            reddit_autopost = False

        console.print("\n[cyan]Starting orchestration...[/cyan]")
        console.print("[dim]Press Ctrl+C to abort[/dim]\n")

        start_time = datetime.now()

        def _progress(event: dict):
            from datetime import datetime
            event_type = event.get("event_type", "")
            payload = event.get("payload", {})
            
            # Calculate elapsed time
            elapsed = datetime.now() - start_time
            elapsed_str = f"{int(elapsed.total_seconds() // 60)}m{int(elapsed.total_seconds() % 60)}s"
            
            if event_type == "task_selected":
                console.print(
                    f"[dim][{elapsed_str}] → {payload.get('task_id')} {payload.get('task_type')}[/dim]"
                )
            elif event_type == "task_result":
                icon = "✓" if payload.get("success") else "✗"
                color = "green" if payload.get("success") else "red"
                message = payload.get("message", "")
                elapsed_min = payload.get("elapsed_minutes", 0)
                console.print(
                    f"[dim][{elapsed_str}][/dim] [{color}]{icon} {payload.get('task_id')} {payload.get('task_type')}[/{color}] [dim]{message}[/dim]"
                )
            elif event_type == "policy_block":
                console.print(
                    f"[dim][{elapsed_str}][/dim] [yellow]⚠ Policy blocked {payload.get('task_id')} ({payload.get('reason')})[/yellow]"
                )
            elif event_type == "runtime_timeout":
                limit = payload.get("limit_minutes", 0)
                elapsed_min = payload.get("elapsed_minutes", 0)
                console.print(
                    f"\n[yellow]⏱ Runtime limit reached: {elapsed_min}m / {limit}m[/yellow]"
                )

        result = service.run(
            max_steps=max_steps,
            max_runtime_minutes=max_runtime,
            reddit_autopost=reddit_autopost,
            progress_callback=_progress,
        )

        console.print("\n[bold]Orchestration Summary[/bold]")
        console.print(
            f"Status: [cyan]{result.status}[/cyan] ({result.reason}) | "
            f"Processed: [green]{result.processed}[/green] | "
            f"Succeeded: [green]{result.succeeded}[/green] | "
            f"Failed: [red]{result.failed}[/red] | "
            f"Blocked: [yellow]{result.blocked}[/yellow]"
        )
        console.print(f"[dim]Summary JSON:[/dim] {result.summary_json}")
        console.print(f"[dim]Summary MD:[/dim] {result.summary_markdown}")
        console.print(f"[dim]Events:[/dim] {result.events_path}")
    
    def main_menu(self):
        """Main menu."""
        # Run auto-verify once on first load
        integrity_issues = self._auto_verify()
        
        while True:
            self._clear_screen()
            
            p = self.project_manager.current
            
            # Show integrity status
            self._render_integrity_status(integrity_issues)
            
            # Show last published info card
            self._render_last_published_card()
            self._render_gsc_status_card()
            
            console.print("[bold]MENU[/bold]\n")
            console.print("1. View/Work on Tasks")
            console.print("2. Projects (Switch / Add / Manage)")
            console.print("v. Verify Setup")
            console.print("a. Articles (Sync / Repair / Validate)")
            console.print("o. Orchestrate Now")
            console.print("p. Publish Articles (Step 5)")
            console.print("i. Indexing Diagnostics (Step 6)")
            console.print("g. GSC Performance Analysis")
            if p:
                console.print("h. Reddit History (view posted/skipped)")
            console.print("c. Check PostHog Configs (All Projects)")
            console.print("s. Scheduler (View / Configure / Run)")
            console.print("r. Reset Project")
            console.print("d. Delete Project")
            console.print("q. Quit")
            
            if p and self.task_list:
                pending_publish = len([t for t in self.task_list.tasks if t.type == "publish_content" and t.status == "todo"])
                if pending_publish > 0:
                    console.print(f"\n[green]📰 {pending_publish} publish task(s) ready[/green]")
            
            choice = self.session.prompt("\nChoice: ").strip()
            
            if choice == "1":
                if not self.project_manager.current:
                    console.print("[yellow]No project selected. Please choose a project first.[/yellow]\n")
                    selected = self.project_manager.select_project_interactive(self.session)
                    if not selected:
                        self.session.prompt("\nPress Enter...")
                        continue
                    self._activate_project(selected)
                self.work_loop()
            elif choice == "2":
                self._projects_menu()
                # Refresh integrity check after project operations
                integrity_issues = self._auto_verify()
            elif choice.lower() == "v":
                self.verify_setup()
                # Refresh integrity check after verify
                integrity_issues = self._auto_verify()
            elif choice.lower() == "a":
                self._articles_menu()
                # Refresh integrity check after articles menu
                integrity_issues = self._auto_verify()
            elif choice.lower() == "o":
                self._run_orchestration_now()
                self.session.prompt("\nPress Enter...")
            elif choice.lower() == "p":
                self._run_menu_workflow_task("publish_content", "Publish Content")
                self.session.prompt("\nPress Enter...")
            elif choice.lower() == "i":
                self._run_menu_workflow_task("indexing_diagnostics", "Indexing Diagnostics")
                self.session.prompt("\nPress Enter...")
            elif choice.lower() == "g":
                self._run_menu_workflow_task("analyze_gsc_performance", "GSC Performance Analysis")
                self.session.prompt("\nPress Enter...")
            elif choice.lower() == "h":
                if self.project_manager.current:
                    self._show_reddit_history()
                self.session.prompt("\nPress Enter...")
            elif choice.lower() == "c":
                self._check_all_posthog_configs()
                self.session.prompt("\nPress Enter...")
            elif choice.lower() == "r":
                if not self.task_list and self.project_manager.current:
                    self.task_list = TaskList(
                        self.project_manager.current,
                        autonomy_mode_map=self.workflow_bundle.autonomy_mode_map,
                    )
                if self.task_list:
                    self.reset_project()
                else:
                    console.print("[red]No project selected[/red]")
                    self.session.prompt("\nPress Enter...")
            elif choice.lower() == "s":
                scheduler_cli = SchedulerCLI(self)
                scheduler_cli.show_menu()
            elif choice.lower() == "d":
                deleted = self.project_manager.delete_project(self.session)
                if deleted and not self.project_manager.current:
                    # Current project was deleted, clear task list
                    self.task_list = None
                    self.runners = {}
                self.session.prompt("\nPress Enter...")
            elif choice == "q":
                break
