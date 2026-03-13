"""Scheduler CLI integration for the dashboard."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.console import Console

console = Console()


class SchedulerCLI:
    """Scheduler management CLI integration."""

    def __init__(self, dashboard):
        self.dashboard = dashboard
        self.session = dashboard.session
        self.project_manager = dashboard.project_manager

    def show_menu(self):
        """Show scheduler management menu."""
        while True:
            self.dashboard._clear_screen()
            console.print("[bold]Scheduler Management[/bold]\n")

            # Show current project context
            p = self.project_manager.current
            if p:
                console.print(f"[dim]Current project:[/dim] [cyan]{p.name}[/cyan] ({p.website_id})")
                # Load and display scheduler status for current project
                self._display_scheduler_status(p)
            else:
                console.print("[yellow]No project selected - some options require a project[/yellow]")

            console.print("\n[bold]Options:[/bold]")
            console.print("1. View Scheduler Configuration")
            console.print("2. Edit Scheduler Settings")
            console.print("3. View Scheduler Rules")
            console.print("4. Run Scheduler Now (current project)")
            console.print("5. Run Scheduler Now (all projects)")
            console.print("6. View Global Scheduler Status")
            console.print("7. Configure Reddit Automation (current project)")
            console.print("8. Setup / Verify macOS Scheduler Daemon")
            console.print("q. Back to Main Menu")

            choice = self.session.prompt("\nChoice: ")

            if choice == "1":
                self._view_scheduler_config()
            elif choice == "2":
                self._edit_scheduler_settings()
            elif choice == "3":
                self._view_scheduler_rules()
            elif choice == "4":
                if p:
                    self._run_scheduler_now(project_id=p.website_id)
                else:
                    console.print("[red]No project selected[/red]")
                    self.session.prompt("\nPress Enter...")
            elif choice == "5":
                self._run_scheduler_now(project_id=None)
            elif choice == "6":
                self._view_global_scheduler_status()
            elif choice == "7":
                self._configure_reddit_automation()
            elif choice == "8":
                self._setup_scheduler_daemon()
            elif choice.lower() == "q":
                break

    def _display_scheduler_status(self, project):
        """Display current scheduler status for a project."""
        from .engine.policy import PolicyEngine
        from .engine.scheduler_service import SchedulerService

        try:
            policy_engine = PolicyEngine(Path(project.repo_root))
            policy = policy_engine.load_or_create()
            scheduler_config = policy.scheduler

            status_color = "green" if scheduler_config.enabled else "red"
            console.print(f"[dim]Scheduler:[/dim] [{status_color}]{'enabled' if scheduler_config.enabled else 'disabled'}[/{status_color}]")

            if scheduler_config.timezone:
                console.print(f"[dim]Timezone:[/dim] {scheduler_config.timezone}")
            console.print(f"[dim]Quiet hours:[/dim] {scheduler_config.quiet_hours_start} - {scheduler_config.quiet_hours_end}")
            console.print(f"[dim]Max tasks/cycle:[/dim] {scheduler_config.max_task_creations_per_cycle}")

            # Load scheduler state
            service = SchedulerService(
                projects_config_path=Path.home() / ".config" / "automation" / "projects.json",
                output_dir=Path(__file__).parent.parent.parent / "output",
                workflow_bundle=self.dashboard.workflow_bundle,
                runtime_config=self.dashboard.runtime_config,
            )
            state = service._load_scheduler_state(Path(project.repo_root))

            if state.last_cycle_finished_at:
                console.print(f"[dim]Last cycle:[/dim] {state.last_cycle_finished_at}")
            if state.stats.cycles > 0:
                console.print(f"[dim]Total cycles:[/dim] {state.stats.cycles} | [dim]Tasks created:[/dim] {state.stats.tasks_created}")

        except Exception as e:
            console.print(f"[dim]Could not load scheduler status: {e}[/dim]")

    def _view_scheduler_config(self):
        """View scheduler configuration for current project."""
        p = self.project_manager.current
        if not p:
            console.print("[red]No project selected[/red]")
            self.session.prompt("\nPress Enter...")
            return

        from .engine.policy import PolicyEngine

        try:
            policy_engine = PolicyEngine(Path(p.repo_root))
            policy = policy_engine.load_or_create()
            config = policy.scheduler

            console.print(f"\n[bold]Scheduler Configuration for {p.name}[/bold]\n")

            status_color = "green" if config.enabled else "red"
            console.print(f"Enabled: [{status_color}]{config.enabled}[/{status_color}]")
            console.print(f"Timezone: {config.timezone or '(system default)'}")
            console.print(f"Max task creations per cycle: {config.max_task_creations_per_cycle}")
            console.print(f"Quiet hours: {config.quiet_hours_start} - {config.quiet_hours_end}")
            console.print(f"Overdue warn threshold: {config.overdue_warn_after_hours} hours")
            console.print(f"Overdue error threshold: {config.overdue_error_after_hours} hours")

            console.print(f"\n[bold]Configured Rules ({len(config.rules)}):[/bold]")
            for rule in config.rules:
                status_icon = "✓" if rule.enabled else "✗"
                console.print(f"  {status_icon} {rule.id}: {rule.task_type} ({rule.mode}, every {rule.cadence_hours}h)")

        except Exception as e:
            console.print(f"[red]Error loading configuration: {e}[/red]")

        self.session.prompt("\nPress Enter...")

    def _edit_scheduler_settings(self):
        """Edit scheduler settings for current project."""
        p = self.project_manager.current
        if not p:
            console.print("[red]No project selected[/red]")
            self.session.prompt("\nPress Enter...")
            return

        from .engine.policy import PolicyEngine

        try:
            policy_engine = PolicyEngine(Path(p.repo_root))
            policy = policy_engine.load_or_create()
            config = policy.scheduler

            console.print(f"\n[bold]Edit Scheduler Settings for {p.name}[/bold]")
            console.print("[dim]Press Enter to keep current value[/dim]\n")

            # Edit enabled status
            current = "y" if config.enabled else "n"
            new_val = self.session.prompt(f"Enabled? (y/n) [{current}]: ").strip().lower()
            if new_val in ("y", "n"):
                config.enabled = new_val == "y"

            # Edit timezone
            new_val = self.session.prompt(f"Timezone [{config.timezone or ''}]: ").strip()
            if new_val:
                config.timezone = new_val

            # Edit quiet hours
            new_val = self.session.prompt(f"Quiet hours start [{config.quiet_hours_start}]: ").strip()
            if new_val:
                config.quiet_hours_start = new_val
            new_val = self.session.prompt(f"Quiet hours end [{config.quiet_hours_end}]: ").strip()
            if new_val:
                config.quiet_hours_end = new_val

            # Edit max creations
            new_val = self.session.prompt(f"Max task creations per cycle [{config.max_task_creations_per_cycle}]: ").strip()
            if new_val:
                try:
                    config.max_task_creations_per_cycle = max(1, int(new_val))
                except ValueError:
                    console.print("[yellow]Invalid number, keeping current value[/yellow]")

            # Save policy
            policy.scheduler = config
            policy_engine.save(policy)
            console.print("\n[green]✓ Scheduler settings saved[/green]")

        except Exception as e:
            console.print(f"[red]Error saving configuration: {e}[/red]")

        self.session.prompt("\nPress Enter...")

    def _view_scheduler_rules(self):
        """View detailed scheduler rules and their state."""
        p = self.project_manager.current
        if not p:
            console.print("[red]No project selected[/red]")
            self.session.prompt("\nPress Enter...")
            return

        from .engine.policy import PolicyEngine
        from .engine.scheduler_service import SchedulerService

        try:
            policy_engine = PolicyEngine(Path(p.repo_root))
            policy = policy_engine.load_or_create()
            config = policy.scheduler

            service = SchedulerService(
                projects_config_path=Path.home() / ".config" / "automation" / "projects.json",
                output_dir=Path(__file__).parent.parent.parent / "output",
                workflow_bundle=self.dashboard.workflow_bundle,
                runtime_config=self.dashboard.runtime_config,
            )
            state = service._load_scheduler_state(Path(p.repo_root))

            console.print(f"\n[bold]Scheduler Rules for {p.name}[/bold]\n")

            for rule in config.rules:
                status_color = "green" if rule.enabled else "red"
                status_text = "enabled" if rule.enabled else "disabled"
                console.print(f"[bold]{rule.id}[/bold] [{status_color}]{status_text}[/{status_color}]")
                console.print(f"  Task type: {rule.task_type}")
                console.print(f"  Mode: {rule.mode}")
                console.print(f"  Cadence: every {rule.cadence_hours} hours")
                console.print(f"  Priority: {rule.priority}")
                console.print(f"  Phase: {rule.phase}")

                # Show rule state
                rule_state = state.rules.get(rule.id)
                if rule_state:
                    if rule_state.last_task_created_at:
                        console.print(f"  Last created: {rule_state.last_task_created_at}")
                    if rule_state.last_status:
                        console.print(f"  Last status: {rule_state.last_status}")
                else:
                    console.print("  [dim]Never run[/dim]")
                console.print()

        except Exception as e:
            console.print(f"[red]Error loading rules: {e}[/red]")

        self.session.prompt("Press Enter...")

    def _find_or_create_reddit_rule(self, config):
        """Find the Reddit opportunity rule or create it with defaults."""
        from .engine.types import SchedulerRule

        for rule in config.rules:
            if rule.id == "reddit_opportunity_search" or rule.task_type == "reddit_opportunity_search":
                return rule

        rule = SchedulerRule(
            id="reddit_opportunity_search",
            task_type="reddit_opportunity_search",
            mode="create_task",
            cadence_hours=48,
            priority="medium",
            phase="research",
            enabled=True,
        )
        config.rules.append(rule)
        return rule

    def _configure_reddit_automation(self):
        """Configure Reddit opportunity automation cadence for current project."""
        p = self.project_manager.current
        if not p:
            console.print("[red]No project selected[/red]")
            self.session.prompt("\nPress Enter...")
            return

        from .engine.policy import PolicyEngine

        try:
            policy_engine = PolicyEngine(Path(p.repo_root))
            policy = policy_engine.load_or_create()
            config = policy.scheduler
            reddit_rule = self._find_or_create_reddit_rule(config)

            console.print(f"\n[bold]Reddit Automation: {p.name}[/bold]\n")
            console.print("[dim]This creates reddit_opportunity_search on a cadence and notifies on macOS when new opportunities are generated.[/dim]\n")
            console.print(f"Current status: {'enabled' if reddit_rule.enabled else 'disabled'}")
            console.print(f"Current cadence: every {reddit_rule.cadence_hours} hours")

            enable_default = "y" if reddit_rule.enabled else "n"
            enable_raw = self.session.prompt(f"Enable Reddit automation? (y/n) [{enable_default}]: ").strip().lower()
            if enable_raw in ("y", "n"):
                reddit_rule.enabled = enable_raw == "y"

            cadence_raw = self.session.prompt(
                f"Cadence hours (48 = every 2 days) [{reddit_rule.cadence_hours or 48}]: "
            ).strip()
            if cadence_raw:
                try:
                    reddit_rule.cadence_hours = max(6, int(cadence_raw))
                except ValueError:
                    console.print("[yellow]Invalid cadence, keeping current value[/yellow]")

            reddit_rule.mode = "create_task"
            reddit_rule.phase = "research"
            reddit_rule.priority = "medium"

            if reddit_rule.enabled and not config.enabled:
                config.enabled = True
                console.print("[dim]Scheduler enabled for this project[/dim]")

            policy.scheduler = config
            policy_engine.save(policy)

            console.print("\n[green]✓ Reddit automation updated[/green]")
            console.print(f"[dim]Rule enabled: {reddit_rule.enabled} | cadence: {reddit_rule.cadence_hours}h[/dim]")
            console.print("[dim]When new opportunities are generated, you'll receive a macOS notification to review in bulk.[/dim]")
        except Exception as e:
            console.print(f"[red]Error configuring Reddit automation: {e}[/red]")

        self.session.prompt("\nPress Enter...")

    def _run_scheduler_now(self, project_id: str | None = None):
        """Run the scheduler cycle manually."""
        from .engine.scheduler_service import SchedulerService

        console.print(f"\n[bold]Running Scheduler Cycle[/bold]")
        if project_id:
            console.print(f"[dim]Project: {project_id}[/dim]")
        else:
            console.print("[dim]Project: all configured projects[/dim]")

        try:
            service = SchedulerService(
                projects_config_path=Path.home() / ".config" / "automation" / "projects.json",
                output_dir=Path(__file__).parent.parent.parent / "output",
                workflow_bundle=self.dashboard.workflow_bundle,
                runtime_config=self.dashboard.runtime_config,
            )

            result = service.run_cycle(project_id=project_id)

            result_color = "green" if result.result == "ok" else "red"
            console.print(f"\n[bold]Result:[/bold] [{result_color}]{result.result}[/{result_color}]")
            console.print(f"[dim]Projects processed:[/dim] {len(result.project_results)}")
            console.print(f"[dim]Tasks created:[/dim] {result.total_tasks_created}")
            console.print(f"[dim]Orchestrator runs:[/dim] {result.total_orchestrator_runs}")

            if result.errors:
                console.print(f"\n[yellow]Errors ({len(result.errors)}):[/yellow]")
                for error in result.errors:
                    console.print(f"  - {error}")

            # Show per-project summary
            for proj_result in result.project_results:
                if proj_result.tasks_created:
                    created = [t.task_id for t in proj_result.tasks_created if t.success]
                    if created:
                        console.print(f"\n[green]✓ {proj_result.website_id}:[/green] Created {len(created)} task(s)")

        except Exception as e:
            console.print(f"[red]Error running scheduler: {e}[/red]")

        self.session.prompt("\nPress Enter...")

    def _setup_scheduler_daemon(self):
        """Install/repair and verify macOS launchd scheduler jobs."""
        from .engine.scheduler_system_service import SchedulerSystemService

        service = SchedulerSystemService()

        while True:
            self.dashboard._clear_screen()
            console.print("[bold]Scheduler Daemon Setup[/bold]\n")

            status = service.get_status()
            console.print(f"Platform: {status.platform}")
            if not status.supported:
                console.print("[yellow]macOS-only feature. Launchd setup is unavailable on this platform.[/yellow]")
                self.session.prompt("\nPress Enter...")
                return

            launchctl_state = "yes" if status.launchctl_available else "no"
            console.print(f"launchctl available: [cyan]{launchctl_state}[/cyan]")
            console.print(f"Cycle plist: [{'green' if status.cycle_plist_exists else 'red'}]{status.cycle_plist_exists}[/{'green' if status.cycle_plist_exists else 'red'}]")
            console.print(f"Health plist: [{'green' if status.health_plist_exists else 'red'}]{status.health_plist_exists}[/{'green' if status.health_plist_exists else 'red'}]")
            console.print(f"Cycle job loaded: [{'green' if status.cycle_loaded else 'yellow'}]{status.cycle_loaded}[/{'green' if status.cycle_loaded else 'yellow'}]")
            console.print(f"Health job loaded: [{'green' if status.health_loaded else 'yellow'}]{status.health_loaded}[/{'green' if status.health_loaded else 'yellow'}]")

            if status.status_file_exists:
                result_color = {"ok": "green", "warn": "yellow", "error": "red"}.get(status.last_result or "", "white")
                console.print(f"Last scheduler result: [{result_color}]{status.last_result or 'unknown'}[/{result_color}]")
                if status.last_finished_at:
                    console.print(f"Last finished at: {status.last_finished_at}")
                if status.last_error:
                    console.print(f"[yellow]Last error: {status.last_error}[/yellow]")
            else:
                console.print("[dim]No scheduler status file yet (run cycle once to initialize).[/dim]")

            console.print("\n[bold]Actions:[/bold]")
            console.print("1. Install / Repair launchd scheduler jobs")
            console.print("2. Refresh status")
            console.print("q. Back")

            choice = self.session.prompt("\nChoice: ").strip().lower()
            if choice == "1":
                success, messages = service.install_or_repair()
                if success:
                    console.print("\n[green]✓ Scheduler daemon installed/repaired[/green]")
                else:
                    console.print("\n[red]✗ Scheduler daemon setup had errors[/red]")
                for msg in messages[:12]:
                    color = "green" if msg.startswith("ok:") else "red"
                    console.print(f"[{color}]  {msg}[/{color}]")
                self.session.prompt("\nPress Enter...")
            elif choice == "2":
                continue
            elif choice == "q":
                return

    def _view_global_scheduler_status(self):
        """View global scheduler status from monitoring files."""
        console.print("\n[bold]Global Scheduler Status[/bold]\n")

        try:
            output_dir = Path(__file__).parent.parent.parent / "output"
            status_file = output_dir / "monitoring" / "seo_scheduler" / "status.json"

            if not status_file.exists():
                console.print("[yellow]No scheduler status file found[/yellow]")
                console.print("[dim]The scheduler may not have run yet[/dim]")
                self.session.prompt("\nPress Enter...")
                return

            import json
            status = json.loads(status_file.read_text())

            result = status.get("last_result", "unknown")
            result_color = {"ok": "green", "warn": "yellow", "error": "red"}.get(result, "white")

            console.print(f"Last result: [{result_color}]{result}[/{result_color}]")
            console.print(f"Last run: {status.get('last_finished_at', 'never')}")
            console.print(f"Duration: {status.get('last_duration_sec', 0)} seconds")
            console.print(f"Projects: {status.get('project_count', 0)}")
            console.print(f"Due rules: {status.get('due_count', 0)}")
            console.print(f"Overdue: {status.get('overdue_count', 0)}")
            console.print(f"Needs attention: {status.get('manual_attention_count', 0)}")

            if status.get("last_top_alert"):
                console.print(f"\n[yellow]Alert: {status['last_top_alert']}[/yellow]")
            if status.get("last_error"):
                console.print(f"\n[red]Error: {status['last_error']}[/red]")

            runs = status.get("runs", {})
            if runs:
                console.print(f"\n[dim]Total runs:[/dim] {runs.get('total', 0)}")
                console.print(f"[dim]Successes:[/dim] {runs.get('successes', 0)}")
                console.print(f"[dim]Failures:[/dim] {runs.get('failures', 0)}")

        except Exception as e:
            console.print(f"[red]Error reading status: {e}[/red]")

        self.session.prompt("\nPress Enter...")
