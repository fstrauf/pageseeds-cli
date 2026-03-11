#!/usr/bin/env python3
"""
Task Dashboard - Entry Point

A task-centered workflow for SEO automation. No campaigns, just tasks.

Usage:
    ./run.sh              # Run with venv setup
    python main.py        # Run directly (requires dependencies)
    python main.py --scheduled-cycle              # Run scheduled cycle for all projects
    python main.py --scheduled-cycle --project <id>  # Run scheduled cycle for one project

For full documentation, see README.md and GUIDE.md
"""

import argparse
import sys
from pathlib import Path


def run_interactive():
    """Run interactive dashboard."""
    from dashboard import Dashboard
    from dashboard.ui import console
    from dashboard.workflow_bundle import legacy_seo_reddit_bundle
    from dashboard.engine.runtime_config import RuntimeConfig
    
    bundle = legacy_seo_reddit_bundle()
    dashboard = Dashboard(
        workflow_bundle=bundle,
        runtime_config=RuntimeConfig(required_clis=bundle.required_clis),
    )
    
    # Select project if none current
    if not dashboard.project_manager.current:
        dashboard._clear_screen()
        selected = dashboard.project_manager.select_project_interactive(dashboard.session)
        if not selected:
            console.print("\n[yellow]No project selected. Exiting dashboard.[/yellow]")
            return
    
    # Run main menu
    dashboard.main_menu()


def run_scheduled_cycle(project_id: str | None = None) -> int:
    """Run scheduled cycle non-interactively.
    
    Returns:
        Exit code (0 for success, 1 for errors)
    """
    from dashboard.engine.scheduler_service import SchedulerService
    from dashboard.workflow_bundle import legacy_seo_reddit_bundle
    from dashboard.engine.runtime_config import RuntimeConfig
    
    # Determine paths
    config_dir = Path.home() / ".config" / "automation"
    projects_config = config_dir / "projects.json"
    output_dir = Path(__file__).parent.parent / "output"
    
    # Run the scheduled cycle
    bundle = legacy_seo_reddit_bundle()
    service = SchedulerService(
        projects_config_path=projects_config,
        output_dir=output_dir,
        workflow_bundle=bundle,
        runtime_config=RuntimeConfig(required_clis=bundle.required_clis),
    )
    
    result = service.run_cycle(project_id=project_id)
    
    # Output summary
    print(f"Scheduled cycle completed: {result.result}")
    print(f"Projects processed: {len(result.project_results)}")
    print(f"Tasks created: {result.total_tasks_created}")
    print(f"Orchestrator runs: {result.total_orchestrator_runs}")
    
    if result.errors:
        print(f"Errors: {len(result.errors)}")
        for error in result.errors:
            print(f"  - {error}")
    
    # Return appropriate exit code
    # ok = success, warn = success with attention items, error = failure
    return 0 if result.result in ("ok", "warn") else 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Task Dashboard - SEO Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Run interactive mode
  %(prog)s --scheduled-cycle         # Run scheduled cycle for all projects
  %(prog)s --scheduled-cycle -p abc  # Run scheduled cycle for project 'abc'
        """,
    )
    
    parser.add_argument(
        "--scheduled-cycle",
        action="store_true",
        help="Run non-interactive scheduled cycle",
    )
    parser.add_argument(
        "--project", "-p",
        metavar="ID",
        help="Specific project ID to process (with --scheduled-cycle)",
    )
    
    args = parser.parse_args()
    
    if args.scheduled_cycle:
        exit_code = run_scheduled_cycle(project_id=args.project)
        sys.exit(exit_code)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
