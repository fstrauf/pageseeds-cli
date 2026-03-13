"""Project menu handlers for Dashboard CLI."""
from __future__ import annotations

import json

from .ui import console


class DashboardProjectsMixin:
    """Project management menus and detail views."""

    def _projects_menu(self):
        """Projects submenu - Switch, Add, or Manage projects."""
        while True:
            self._clear_screen()

            console.print("[bold]Projects[/bold]\n")

            # Show current project
            if self.project_manager.current:
                p = self.project_manager.current
                console.print(f"[dim]Current:[/dim] [cyan]{p.name}[/cyan] ({p.website_id})")
                console.print()

            console.print("1. Switch Project")
            console.print("2. Add New Project")
            console.print("3. Manage Projects (Edit/Delete/Validate)")
            console.print("q. Back to Main Menu")

            choice = self.session.prompt("\nChoice: ")

            if choice == "1":
                selected = self.project_manager.select_project_interactive(self.session)
                if selected:
                    self._activate_project(selected, show_report=True)
                self.session.prompt("\nPress Enter...")
                break  # Return to main menu after selection

            elif choice == "2":
                new_project = self.project_manager.add_project_interactive(self.session)
                if new_project:
                    self._activate_project(new_project, show_report=True)
                    console.print(f"\n[green]✓ Project '{new_project.name}' is now active[/green]")
                self.session.prompt("\nPress Enter...")
                break  # Return to main menu after adding

            elif choice == "3":
                self._manage_projects_menu()
                # Don't break - stay in projects menu after managing

            elif choice.lower() == "q":
                break

    def _manage_projects_menu(self):
        """Project management submenu."""
        while True:
            self._clear_screen()

            console.print("[bold]Manage Projects[/bold]\n")

            # Show project list with status
            self.project_manager.show_project_status()

            console.print("\n[b]Options:[/b]")
            console.print("1. Edit Project")
            console.print("2. Delete Project")
            console.print("3. Validate All Projects")
            console.print("4. Show Project Details")
            console.print("q. Back to Main Menu")

            choice = self.session.prompt("\nChoice: ")

            if choice == "1":
                self.project_manager.edit_project_interactive(self.session)
                self.session.prompt("\nPress Enter...")

            elif choice == "2":
                deleted = self.project_manager.delete_project_interactive(self.session)
                if deleted and not self.project_manager.current:
                    self.task_list = None
                    self.runners = {}
                self.session.prompt("\nPress Enter...")

            elif choice == "3":
                self._validate_all_projects()
                self.session.prompt("\nPress Enter...")

            elif choice == "4":
                self._show_project_details()
                self.session.prompt("\nPress Enter...")

            elif choice.lower() == "q":
                break

    def _validate_all_projects(self):
        """Validate all configured projects."""
        console.print("\n[bold]Validating All Projects[/bold]\n")

        issues = self.project_manager.validate_all()

        if not issues:
            console.print("[green]✓ All projects are valid[/green]")
            return

        console.print(f"[yellow]Found issues in {len(issues)} project(s):[/yellow]\n")

        for project, project_issues in issues:
            console.print(f"[red]{project.name} ({project.website_id}):[/red]")
            for issue in project_issues:
                console.print(f"  - {issue}")
            console.print()

    def _show_project_details(self):
        """Show detailed information about a project."""
        if not self.project_manager.projects:
            console.print("[yellow]No projects configured[/yellow]")
            return

        console.print("\n[bold]Select Project:[/bold]\n")
        for i, p in enumerate(self.project_manager.projects, 1):
            console.print(f"  {i}. {p.name}")
        console.print("  c. Cancel")

        choice = self.session.prompt("\nChoice: ")

        if choice.lower() == 'c':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(self.project_manager.projects):
                project = self.project_manager.projects[idx]
                self._display_project_details(project)
        except ValueError:
            pass

    def _display_project_details(self, project):
        """Display detailed project information."""
        from rich.panel import Panel
        from rich.table import Table

        is_valid, issues = project.is_valid()

        # Main info
        console.print(
            Panel(
                f"[bold]{project.name}[/bold]\n"
                f"ID: {project.website_id}\n"
                f"Path: {project.repo_root}",
                title="Project Details",
                border_style="green" if is_valid else "red",
            )
        )

        # Validation status
        if is_valid:
            console.print("[green]✓ Configuration valid[/green]\n")
        else:
            console.print("[red]✗ Configuration issues:[/red]")
            for issue in issues:
                console.print(f"  - {issue}")
            console.print()

        # Check for files
        files_table = Table(show_header=True)
        files_table.add_column("File")
        files_table.add_column("Status")

        auto_dir = project.automation_dir

        # Check articles.json
        articles_json = auto_dir / "articles.json"
        if articles_json.exists():
            try:
                data = json.loads(articles_json.read_text())
                count = len(data.get("articles", []))
                files_table.add_row("articles.json", f"[green]✓ {count} articles[/green]")
            except Exception:
                files_table.add_row("articles.json", "[red]✗ Invalid JSON[/red]")
        else:
            files_table.add_row("articles.json", "[red]✗ Missing[/red]")

        # Check manifest.json
        manifest_json = auto_dir / "manifest.json"
        if manifest_json.exists():
            files_table.add_row("manifest.json", "[green]✓ Present[/green]")
        else:
            files_table.add_row("manifest.json", "[red]✗ Missing[/red]")

        # Check content directory
        content_dir = project.repo_path / "content"
        if content_dir.exists():
            mdx_count = len(list(content_dir.glob("*.mdx")))
            files_table.add_row("content/", f"[green]✓ {mdx_count} .mdx files[/green]")
        else:
            files_table.add_row("content/", "[yellow]⚠ Not found[/yellow]")

        console.print(files_table)
