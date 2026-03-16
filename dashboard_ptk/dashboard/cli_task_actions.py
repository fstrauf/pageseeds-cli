"""Task action menu handlers for Dashboard CLI."""
from __future__ import annotations

import re
from pathlib import Path

from .ui import console


class DashboardTaskActionsMixin:
    """Task work, review, and creation/deletion flows."""

    def work_on_task(self, task):
        """Execute a task based on its phase."""
        from datetime import datetime

        task.started_at = datetime.now().isoformat()
        if task.status == "todo":
            task.status = "in_progress"
            self.task_list.save()

        if not self.executor:
            console.print("[red]Execution engine is not initialized[/red]")
            self.task_list.save()
            self.session.prompt("\nPress Enter to continue...")
            return

        console.print(f"[dim]DEBUG: Engine executing task phase='{task.phase}', type='{task.type}'[/dim]")
        result = self.executor.execute_task(task)
        # Handle both old bool return and new tuple return
        if isinstance(result, tuple):
            success, message = result
        else:
            success, message = result, ""

        self.task_list.save()

        if success:
            console.print(f"\n[green]✓ Task {task.status}[/green]")
        else:
            console.print(f"\n[red]✗ Task failed: {message}[/red]")

        self.session.prompt("\nPress Enter to continue...")

    def select_and_work_on_task(self):
        """Show available tasks and let user select.

        Supports single selection (e.g., '1') or multiple comma-separated (e.g., '1,3,5').
        """
        ready = self.task_list.get_ready()
        in_progress = self.task_list.get_by_status("in_progress")
        review_tasks = self.task_list.get_by_status("review")
        available = in_progress + ready + review_tasks

        if not available:
            console.print("\n[yellow]No tasks available. Create some first![/yellow]")
            self.session.prompt("\nPress Enter...")
            return

        console.print("\n[bold]Available Tasks:[/bold]\n")

        for i, task in enumerate(available[:10], 1):
            if task.status == "in_progress":
                status_icon = "◐"
            elif task.status == "review":
                status_icon = "👁"
            else:
                status_icon = "○"

            phase_color = {
                "collection": "blue",
                "investigation": "yellow",
                "research": "cyan",
                "implementation": "green",
            }.get(task.phase, "white")

            status_label = f" [{task.status}]" if task.status in ("review",) else ""
            console.print(f"  {i}. {status_icon} [{phase_color}]{task.phase}[/{phase_color}] {task.title[:45]}{status_label}")

        if len(available) > 10:
            console.print(f"\n  [dim]... and {len(available) - 10} more[/dim]")

        console.print("\n  [dim]Enter number(s): 1 or 1,3,5[/dim]")
        console.print("  c. Cancel")

        choice = self.session.prompt("\nSelect task(s): ")

        if choice.lower() == "c":
            return

        # Parse comma-separated selections
        selections = [s.strip() for s in choice.split(",") if s.strip()]
        selected_tasks = []
        invalid = []

        for sel in selections:
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(available):
                    selected_tasks.append(available[idx])
                else:
                    invalid.append(sel)
            except ValueError:
                invalid.append(sel)

        if invalid:
            console.print(f"\n[yellow]Invalid selection(s): {', '.join(invalid)}[/yellow]")

        if not selected_tasks:
            return

        # Work on selected tasks
        if len(selected_tasks) == 1:
            # Single task - normal flow
            task = selected_tasks[0]
            if task.status == "review":
                self._handle_review_task_selection(task)
            else:
                self.work_on_task(task)
        else:
            # Multiple tasks - show what we'll process
            console.print(f"\n[bold]Processing {len(selected_tasks)} tasks:[/bold]")
            for task in selected_tasks:
                console.print(f"  • {task.title[:50]}")
            console.print()

            # Process each task
            for i, task in enumerate(selected_tasks, 1):
                console.print(f"\n[bold cyan]Task {i}/{len(selected_tasks)}[/bold cyan]")
                console.print("=" * 60)

                if task.status == "review":
                    # For review tasks, just ask to mark as done
                    console.print(f"[bold]{task.title}[/bold] (in review)")
                    mark_done = self.session.prompt("Mark as done? (y/n): ")
                    if mark_done.lower() == "y":
                        from datetime import datetime

                        task.status = "done"
                        task.completed_at = datetime.now().isoformat()
                        self.task_list.save()
                        console.print("[green]✓ Marked as done[/green]")
                else:
                    self.work_on_task(task)

                if i < len(selected_tasks):
                    console.print(f"\n[dim]Moving to next task ({i + 1}/{len(selected_tasks)})...[/dim]")

            console.print(f"\n[green]✓ Completed batch processing of {len(selected_tasks)} tasks[/green]")

    def _handle_review_task_selection(self, task):
        """Handle selection of a task that's in review status."""
        console.print(f"\n[bold cyan]Task is in review:[/bold cyan] {task.title}")
        console.print("\nOptions:")
        console.print("  1. Continue working on this task")
        console.print("  2. Mark as done (review complete)")
        console.print("  c. Cancel")

        choice = self.session.prompt("\nChoice: ")

        if choice == "1":
            self.work_on_task(task)
        elif choice == "2":
            from datetime import datetime

            task.status = "done"
            task.completed_at = datetime.now().isoformat()
            self.task_list.save()
            console.print(f"\n[green]✓ Task {task.id} marked as done[/green]")
            self.session.prompt("\nPress Enter...")

    def mark_task_reviewed(self):
        """Mark reviewed tasks as done. Supports multi-select."""
        from datetime import datetime

        review_tasks = self.task_list.get_by_status("review")

        if not review_tasks:
            console.print("\n[yellow]No tasks in review[/yellow]")
            self.session.prompt("\nPress Enter...")
            return

        # Reddit tasks are auto-processed, no special handling needed
        # (reddit_opportunity_search creates reply tasks automatically)

        console.print("\n[bold]Tasks in Review:[/bold]\n")
        for i, task in enumerate(review_tasks, 1):
            console.print(f"  {i}. {task.title}")
        console.print("  a. Mark all done")
        console.print("  c. Cancel")
        console.print("\n[dim]Enter: 1 or 1,3,5 or 'a' for all[/dim]")

        choice = self.session.prompt("\nChoice: ").strip()

        if choice.lower() == "c":
            return

        if choice.lower() == "a":
            # Mark all done
            for task in review_tasks:
                task.status = "done"
                task.completed_at = datetime.now().isoformat()
            console.print(f"[green]✓ Marked {len(review_tasks)} done[/green]")
        elif "," in choice:
            # Multi-select: parse comma-separated numbers
            selected_indices = []
            invalid = []
            for part in choice.split(","):
                part = part.strip()
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(review_tasks):
                        selected_indices.append(idx)
                    else:
                        invalid.append(part)
                except ValueError:
                    invalid.append(part)

            if invalid:
                console.print(f"[yellow]Invalid selection(s): {', '.join(invalid)}[/yellow]")

            # Mark selected tasks as done
            marked_count = 0
            for idx in selected_indices:
                review_tasks[idx].status = "done"
                review_tasks[idx].completed_at = datetime.now().isoformat()
                marked_count += 1

            if marked_count > 0:
                console.print(f"[green]✓ Marked {marked_count} done[/green]")
        else:
            # Single selection
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(review_tasks):
                    review_tasks[idx].status = "done"
                    review_tasks[idx].completed_at = datetime.now().isoformat()
                    console.print("[green]✓ Task done[/green]")
            except ValueError:
                pass

        self.task_list.save()
        self.session.prompt("\nPress Enter...")

    def view_specifications(self):
        """View available specifications."""
        specs = [t for t in self.task_list.tasks if t.spec_file]

        if not specs:
            console.print("\n[yellow]No specifications available[/yellow]")
            self.session.prompt("\nPress Enter...")
            return

        console.print("\n[bold]Available Specifications:[/bold]\n")

        for i, task in enumerate(specs[:10], 1):
            status_icon = "✓" if task.status == "done" else "◑"
            console.print(f"  {i}. {status_icon} {task.title}")
            console.print(f"     [dim]{task.spec_file}[/dim]")

        console.print("\n  c. Cancel")

        choice = self.session.prompt("\nView spec #: ")

        if choice.lower() == "c":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(specs):
                task = specs[idx]
                spec_path = self.task_list.automation_dir / task.spec_file
                if spec_path.exists():
                    content = spec_path.read_text()
                    console.print(f"\n[bold]{task.title}[/bold]")
                    console.print("=" * 60)
                    console.print(content[:3000])
                    if len(content) > 3000:
                        console.print("\n[dim]... (truncated)[/dim]")
                else:
                    console.print("[red]Spec file not found[/red]")
        except ValueError:
            pass

        self.session.prompt("\nPress Enter...")

    def _quick_create_task(self, task_type: str):
        """Quickly create a common task type without prompts.

        Args:
            task_type: One of 'gsc', 'posthog', 'keywords', 'reddit', 'landing_pages', 'performance'
        """
        if not self.task_list:
            console.print("[red]No task list loaded[/red]")
            input("\nPress Enter...")
            return

        created = []

        if task_type in ["gsc", "posthog"]:
            # Check for existing tasks
            existing_collect = any(t.type == f"collect_{task_type}" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)

            if existing_collect:
                console.print(f"[yellow]Active {task_type.upper()} collection task already exists[/yellow]")
            else:
                col_task = self.task_list.create_collection_task(task_type)
                created.append(col_task.title)
                # Note: Investigation task will be created by the collection task on success
                # This prevents orphaned investigation tasks when collection fails

        elif task_type == "keywords":
            existing = any(t.type == "research_keywords" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)
            if existing:
                console.print("[yellow]Active keyword research task already exists[/yellow]")
            else:
                res_task = self.task_list.create_research_task("keywords")
                created.append(res_task.title)

        elif task_type == "reddit":
            existing = any(t.type == "reddit_opportunity_search" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)
            if existing:
                console.print("[yellow]Active Reddit search task already exists[/yellow]")
            else:
                reddit_task = self.task_list.create_reddit_opportunity_search()
                created.append(reddit_task.title)

        elif task_type == "landing_pages":
            existing = any(t.type == "research_landing_pages" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)
            if existing:
                console.print("[yellow]Active landing page research task already exists[/yellow]")
            else:
                lp_task = self.task_list.create_research_task("landing_pages")
                created.append(lp_task.title)

        elif task_type == "performance":
            existing = any(t.type == "analyze_gsc_performance" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)
            if existing:
                console.print("[yellow]Active GSC performance analysis task already exists[/yellow]")
            else:
                perf_task = self.task_list.create_task(
                    task_type="analyze_gsc_performance",
                    title="Analyze GSC performance for optimization opportunities",
                    phase="research",
                    priority="high",
                )
                created.append(perf_task.title)

        if created:
            console.print(f"[green]✓ Created {len(created)} task(s):[/green]")
            for title in created:
                console.print(f"  [dim]• {title}[/dim]")

        input("\nPress Enter...")

    def _quick_create_custom_keywords(self):
        """Quickly create a custom keyword research task with minimal prompts."""
        if not self.task_list:
            console.print("[red]No task list loaded[/red]")
            input("\nPress Enter...")
            return

        existing = any(t.type == "custom_keyword_research" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)
        if existing:
            console.print("[yellow]Active custom keyword research task already exists[/yellow]")
            input("\nPress Enter...")
            return

        console.print("\n[bold cyan]Custom Keyword Research[/bold cyan]")
        console.print("[dim]Enter keyword themes (comma-separated, e.g., 'options trading, wheel strategy')[/dim]")

        themes_input = self.session.prompt("Themes: ").strip()
        themes = [t.strip() for t in re.split(r'[,,\n]', themes_input) if t.strip()]

        # Validate themes aren't too long
        valid_themes = []
        for t in themes:
            word_count = len(t.split())
            if word_count > 10:
                t = ' '.join(t.split()[:4])
            valid_themes.append(t)
        themes = valid_themes

        if not themes:
            console.print("[yellow]No themes provided, cancelled[/yellow]")
            input("\nPress Enter...")
            return

        # Optional: quick criteria
        criteria = self.session.prompt("Focus/criteria (optional, Enter to skip): ").strip()

        # Create with defaults
        custom_task = self.task_list.create_custom_keyword_research_task(
            themes=themes,
            criteria=criteria,
            min_volume=100,
            max_kd=40,
        )

        console.print(f"[green]✓ Created: {custom_task.title}[/green]")
        console.print(f"[dim]  → {len(themes)} theme(s), using defaults (vol≥100, kd≤40)[/dim]")

        input("\nPress Enter...")

    def create_initial_tasks(self):
        """Create initial tasks for a new project."""
        console.print("\n[bold]Create Initial Tasks[/bold]\n")
        console.print("What do you want to do?\n")

        sources = []

        if self.session.prompt("  Collect GSC data? (y/n): ").lower() == "y":
            sources.append("gsc")
        if self.session.prompt("  Collect PostHog data? (y/n): ").lower() == "y":
            sources.append("posthog")
        if self.session.prompt("  Research keywords? (y/n): ").lower() == "y":
            sources.append("keywords")
        if self.session.prompt("  Reddit opportunity search? (y/n): ").lower() == "y":
            sources.append("reddit")
        if self.session.prompt("  Research landing pages? (y/n): ").lower() == "y":
            sources.append("landing_pages")

        for source in sources:
            if source in ["gsc", "posthog"]:
                existing_collect = any(t.type == f"collect_{source}" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)

                if existing_collect:
                    console.print("[dim]Active collection task already exists[/dim]")
                else:
                    col_task = self.task_list.create_collection_task(source)
                    console.print(f"[dim]Created: {col_task.title}[/dim]")
                    # Note: Investigation task will be created by the collection task on success
                    # This prevents orphaned investigation tasks when collection fails

            elif source == "keywords":
                existing = any(t.type == "research_keywords" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)
                if existing:
                    console.print("[dim]Active keyword research task already exists[/dim]")
                else:
                    res_task = self.task_list.create_research_task("keywords")
                    console.print(f"[dim]Created: {res_task.title}[/dim]")

            elif source == "reddit":
                # Only check for non-completed tasks (allow new search if previous is done)
                existing = any(t.type == "reddit_opportunity_search" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)
                if existing:
                    console.print("[dim]Active Reddit search task already exists (wait for it to complete)[/dim]")
                else:
                    reddit_task = self.task_list.create_reddit_opportunity_search()
                    console.print(f"[dim]Created: {reddit_task.title}[/dim]")

            elif source == "landing_pages":
                existing = any(t.type == "research_landing_pages" and t.status not in ["done", "cancelled", "failed"] for t in self.task_list.tasks)
                if existing:
                    console.print("[dim]Active landing page research task already exists[/dim]")
                else:
                    lp_task = self.task_list.create_research_task("landing_pages")
                    console.print(f"[dim]Created: {lp_task.title}[/dim]")

        console.print("\n[green]✓ Tasks created[/green]")
        self.session.prompt("\nPress Enter...")

    def reset_project(self):
        """Reset the entire project with confirmation."""
        console.print("\n[bold red]⚠️  RESET PROJECT[/bold red]")
        console.print("\n[yellow]This will delete:[/yellow]")
        console.print("  • All tasks")
        console.print("  • All collected data (artifacts)")
        console.print("  • All research results")
        console.print("  • All specifications")
        console.print("\n[green]This will NOT delete:[/green]")
        console.print("  • Your articles (articles.json)")
        console.print("  • Your content files (.mdx)")
        console.print("  • Project configuration")
        console.print("  • Reddit POSTED history (prevents duplicate posting)")
        console.print("\n[red]Deleted items cannot be undone![/red]")

        # Ask about clearing skipped Reddit history
        clear_skipped = self.session.prompt(
            "\nClear skipped Reddit posts for rediscovery? (y/n): "
        ).lower() == "y"

        confirm = self.session.prompt("\nType 'reset' to confirm: ")

        if confirm != "reset":
            console.print("\n[yellow]Reset cancelled.[/yellow]")
            self.session.prompt("\nPress Enter...")
            return

        # Double confirm if there are tasks
        if self.task_list.tasks:
            progress = self.task_list.get_progress()
            console.print(f"\n[red]You have {progress['done']}/{progress['total']} completed tasks.[/red]")
            confirm2 = self.session.prompt("Are you sure? Type 'DELETE' to confirm: ")
            if confirm2 != "DELETE":
                console.print("\n[yellow]Reset cancelled.[/yellow]")
                self.session.prompt("\nPress Enter...")
                return

        # Clear skipped Reddit history if requested (after confirmation)
        if clear_skipped:
            from .tasks.reddit import RedditHistoryManager

            history = RedditHistoryManager(Path(self.project_manager.current.repo_root))
            cleared = history.clear_skipped()
            console.print(f"[dim]Cleared {cleared} skipped Reddit posts (will be rediscovered)[/dim]")

        # Perform reset (preserves Reddit tasks by default)
        console.print("\n[dim]Resetting project...[/dim]")
        counts = self.task_list.reset_all(preserve_reddit=True)

        console.print("\n[green]✓ Project reset complete[/green]")
        console.print(f"  Deleted {counts['tasks']} tasks")
        console.print(f"  Deleted {counts['artifacts']} artifacts")
        console.print(f"  Deleted {counts['results']} result directories")
        console.print(f"  Deleted {counts['specs']} specifications")
        if counts.get('ghost_articles_cleaned', 0) > 0:
            console.print(f"  [green]Cleaned {counts['ghost_articles_cleaned']} ghost articles[/green]")
            console.print("  [dim](Draft entries with no content files)[/dim]")
        if counts.get('reddit_preserved', 0) > 0:
            console.print(f"  [cyan]Preserved {counts['reddit_preserved']} posted Reddit tasks[/cyan]")
            console.print("  [dim](Prevents duplicate posting to same thread)[/dim]")
        if clear_skipped:
            console.print("  [green]Cleared skipped Reddit history[/green]")
            console.print("  [dim](Skipped posts will be rediscovered in new searches)[/dim]")
        console.print("\n[dim]You can now start fresh with 'Add more tasks'[/dim]")

        self.session.prompt("\nPress Enter...")

    def delete_task(self):
        """Delete one or more tasks with confirmation."""
        # Get all non-completed tasks (can't delete done tasks)
        deletable = [t for t in self.task_list.tasks if t.status != "done"]

        if not deletable:
            console.print("\n[yellow]No deletable tasks available.[/yellow]")
            console.print("[dim]Completed tasks cannot be deleted.[/dim]")
            self.session.prompt("\nPress Enter...")
            return

        console.print("\n[bold]Delete Task(s)[/bold]")
        console.print("[dim]Enter task numbers (comma-separated) or task IDs[/dim]\n")

        # Show tasks grouped by status
        todo_tasks = [t for t in deletable if t.status == "todo"]
        in_progress = [t for t in deletable if t.status == "in_progress"]
        review_tasks = [t for t in deletable if t.status == "review"]

        all_shown = []

        if todo_tasks:
            console.print("[dim]To Do:[/dim]")
            for i, task in enumerate(todo_tasks, len(all_shown) + 1):
                console.print(f"  {i}. {task.id} - {task.title[:40]}...")
            all_shown.extend(todo_tasks)

        if in_progress:
            console.print("\n[dim]In Progress:[/dim]")
            for i, task in enumerate(in_progress, len(all_shown) + 1):
                console.print(f"  {i}. {task.id} - {task.title[:40]}... [yellow](in progress)[/yellow]")
            all_shown.extend(in_progress)

        if review_tasks:
            console.print("\n[dim]In Review:[/dim]")
            for i, task in enumerate(review_tasks, len(all_shown) + 1):
                console.print(f"  {i}. {task.id} - {task.title[:40]}... [cyan](review)[/cyan]")
            all_shown.extend(review_tasks)

        console.print("\n  c. Cancel")

        choice = self.session.prompt("\nSelect task(s) to delete: ")

        if not choice or choice.lower() == "c":
            return

        # Parse input - can be comma-separated numbers or task IDs
        selections = [s.strip() for s in choice.split(",") if s.strip()]
        tasks_to_delete = []
        invalid_selections = []

        for sel in selections:
            # Try as number first
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(all_shown):
                    tasks_to_delete.append(all_shown[idx])
                else:
                    invalid_selections.append(sel)
            except ValueError:
                # Try as task ID
                matching = [t for t in all_shown if t.id == sel]
                if matching:
                    tasks_to_delete.append(matching[0])
                else:
                    invalid_selections.append(sel)

        if invalid_selections:
            console.print(f"\n[yellow]Invalid selection(s): {', '.join(invalid_selections)}[/yellow]")

        if not tasks_to_delete:
            console.print("\n[yellow]No valid tasks selected.[/yellow]")
            self.session.prompt("\nPress Enter...")
            return

        # Show summary and confirm
        console.print(f"\n[bold red]⚠️  DELETE {len(tasks_to_delete)} TASK(S)[/bold red]\n")
        for task in tasks_to_delete:
            status_note = " [yellow](in progress)[/yellow]" if task.status == "in_progress" else ""
            console.print(f"  • [cyan]{task.id}[/cyan] - {task.title[:50]}{status_note}")

        in_progress_count = sum(1 for t in tasks_to_delete if t.status == "in_progress")
        if in_progress_count > 0:
            console.print(f"\n[yellow]Warning: {in_progress_count} task(s) are in progress![/yellow]")

        confirm = self.session.prompt("\nType 'delete' to confirm: ")

        if confirm == "delete":
            task_ids = [t.id for t in tasks_to_delete]
            result = self.task_list.delete_tasks(task_ids)

            if result["deleted"]:
                console.print(f"\n[green]✓ Deleted {len(result['deleted'])} task(s)[/green]")
            if result["skipped_done"]:
                console.print(f"[yellow]⚠ Skipped {len(result['skipped_done'])} completed task(s)[/yellow]")
            if result["not_found"]:
                console.print(f"[red]✗ {len(result['not_found'])} task(s) not found[/red]")
        else:
            console.print("\n[dim]Deletion cancelled.[/dim]")

        self.session.prompt("\nPress Enter...")
