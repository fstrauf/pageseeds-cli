"""Article submenu flows for Dashboard CLI."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .ui import console


class DashboardArticlesMixin:
    """Article maintenance menu and handlers."""

    def _articles_menu(self):
        """Articles submenu - Sync, Repair, and Validate articles."""
        from .utils import ArticleStore

        p = self.project_manager.current
        if not p:
            console.print("[red]No project selected[/red]")
            self.session.prompt("\nPress Enter...")
            return

        # Initialize ArticleStore
        try:
            store = ArticleStore(Path(p.repo_root), p.website_id)
        except Exception as e:
            console.print(f"[red]Error initializing article store: {e}[/red]")
            self.session.prompt("\nPress Enter...")
            return

        while True:
            self._clear_screen()

            console.print(f"[bold]Articles: {p.name}[/bold]\n")

            # Show quick stats
            json_articles = store.load_json()
            file_articles = store.scan()

            console.print(f"[dim]Content files:[/dim] {len(file_articles)}")
            console.print(f"[dim]articles.json entries:[/dim] {len(json_articles)}")

            if len(file_articles) != len(json_articles):
                console.print("[yellow]⚠ Mismatch detected[/yellow]")
            else:
                console.print("[green]✓ Counts match[/green]")
            console.print()

            console.print("1. Check / Validate (dry-run)")
            console.print("2. Sync (files → JSON)")
            console.print("3. Repair All Issues")
            console.print("4. Redistribute Future Dates")
            console.print("5. Show Date Mismatches")
            console.print("q. Back to Main Menu")

            choice = self.session.prompt("\nChoice: ")

            if choice == "1":
                self._articles_check(store)
                self.session.prompt("\nPress Enter...")

            elif choice == "2":
                self._articles_sync(store)
                self.session.prompt("\nPress Enter...")

            elif choice == "3":
                self._articles_repair(store)
                self.session.prompt("\nPress Enter...")

            elif choice == "4":
                self._articles_redistribute_dates(store)
                self.session.prompt("\nPress Enter...")

            elif choice == "5":
                self._articles_show_date_mismatches(store)
                self.session.prompt("\nPress Enter...")

            elif choice.lower() == "q":
                break

    def _articles_check(self, store):
        """Run validation check (dry-run)."""
        console.print("\n[bold]Checking Articles...[/bold]\n")

        # Run sync in dry-run mode
        result = store.sync(dry_run=True, prefer="files")

        # Show what would be added
        if result.added:
            console.print(f"[yellow]Would add {len(result.added)} new article(s):[/yellow]")
            for art in result.added[:5]:
                console.print(f"  [dim]ID {art.id}: {art.filename}[/dim]")
            if len(result.added) > 5:
                console.print(f"  [dim]... and {len(result.added) - 5} more[/dim]")
            console.print()

        # Show what would be removed
        if result.removed:
            console.print(f"[yellow]Would remove {len(result.removed)} orphaned entry(s):[/yellow]")
            for art in result.removed[:5]:
                console.print(f"  [dim]ID {art.id}: {art.filename}[/dim]")
            if len(result.removed) > 5:
                console.print(f"  [dim]... and {len(result.removed) - 5} more[/dim]")
            console.print()

        # Show date fixes
        if result.date_fixed:
            console.print(f"[yellow]Would fix {len(result.date_fixed)} date(s):[/yellow]")
            for fix in result.date_fixed[:5]:
                art = fix["article"]
                console.print(f"  [dim]ID {art.id}: {fix['old_date']} → {fix['new_date']}[/dim]")
            if len(result.date_fixed) > 5:
                console.print(f"  [dim]... and {len(result.date_fixed) - 5} more[/dim]")
            console.print()

        # Show issues
        if result.duplicates_found:
            console.print(f"[red]Found {len(result.duplicates_found)} duplicate ID group(s):[/red]")
            for group in result.duplicates_found[:3]:
                ids = [a.id for a in group]
                console.print(f"  IDs: {ids}")
            console.print()

        if result.collisions_found:
            console.print(f"[red]Found {len(result.collisions_found)} date collision(s):[/red]")
            for coll in result.collisions_found[:3]:
                date = coll["date"]
                ids = [a.id for a in coll["articles"]]
                console.print(f"  {date}: IDs {ids}")
            console.print()

        if result.errors:
            console.print(f"[red]Errors ({len(result.errors)}):[/red]")
            for err in result.errors[:5]:
                console.print(f"  [dim]{err}[/dim]")
            console.print()

        if not result.has_changes and not result.has_issues:
            console.print("[green]✓ No issues found - everything looks good![/green]")
        elif not result.has_changes and result.has_issues:
            console.print("[yellow]⚠ Issues found but no automatic fixes available[/yellow]")
        else:
            console.print("[cyan]Run 'Sync' or 'Repair' to apply fixes[/cyan]")

    def _articles_sync(self, store):
        """Sync articles (files are source of truth)."""
        console.print("\n[bold]Syncing Articles (files → JSON)...[/bold]\n")

        # First show dry-run
        result = store.sync(dry_run=True, prefer="files")

        if not result.has_changes:
            console.print("[green]✓ Already in sync - no changes needed[/green]")
            return

        # Show changes
        if result.added:
            console.print(f"[green]Will add {len(result.added)} article(s)[/green]")
        if result.removed:
            console.print(f"[yellow]Will remove {len(result.removed)} orphaned entry(s)[/yellow]")
        if result.date_fixed:
            console.print(f"[yellow]Will fix {len(result.date_fixed)} date(s)[/yellow]")
        if result.slug_fixed:
            console.print(f"[yellow]Will fix {len(result.slug_fixed)} slug(s)[/yellow]")

        # Confirm
        confirm = self.session.prompt("\nApply changes? (yes/no): ")
        if confirm.lower() not in ("yes", "y"):
            console.print("[dim]Cancelled[/dim]")
            return

        # Apply
        result = store.sync(dry_run=False, prefer="files")
        console.print("\n[green]✓ Sync complete![/green]")
        console.print(f"[dim]Added: {len(result.added)}, Removed: {len(result.removed)}[/dim]")

    def _articles_repair(self, store):
        """Repair all fixable issues."""
        console.print("\n[bold]Repairing Articles...[/bold]\n")

        result = store.repair(dry_run=True)

        if not result.has_changes and not result.has_issues:
            console.print("[green]✓ Nothing to repair[/green]")
            return

        if result.has_changes:
            console.print(f"[cyan]Will apply {len(result.added) + len(result.removed) + len(result.date_fixed)} fix(es)[/cyan]")

        if result.has_issues and not result.has_changes:
            console.print(f"[yellow]Found {len(result.duplicates_found)} duplicate(s) and {len(result.collisions_found)} collision(s)[/yellow]")
            console.print("[dim]These require manual intervention[/dim]")

        confirm = self.session.prompt("\nApply repairs? (yes/no): ")
        if confirm.lower() not in ("yes", "y"):
            console.print("[dim]Cancelled[/dim]")
            return

        result = store.repair(dry_run=False)
        console.print("\n[green]✓ Repair complete![/green]")

    def _articles_redistribute_dates(self, store):
        """Redistribute dates for articles with 2-day gaps."""
        console.print("\n[bold]Redistribute Article Dates[/bold]\n")

        # Get current articles
        articles = store.load_json()
        if not articles:
            console.print("[yellow]No articles found[/yellow]")
            return

        # Find articles with future dates
        future_articles = [a for a in articles if a.status == "draft"]
        if not future_articles:
            console.print("[yellow]No draft (future) articles found[/yellow]")
            return

        console.print(f"Found {len(future_articles)} draft article(s)\n")

        # Show current dates
        console.print("[dim]Current future dates:[/dim]")
        for art in sorted(future_articles, key=lambda a: a.date_obj)[:5]:
            console.print(f"  ID {art.id}: {art.published_date}")
        if len(future_articles) > 5:
            console.print(f"  ... and {len(future_articles) - 5} more")
        console.print()

        # Ask for start date
        start_default = datetime.now().strftime("%Y-%m-%d")
        start_input = self.session.prompt(f"Start date from [{start_default}]: ")
        start_date = start_input.strip() if start_input.strip() else start_default

        # Show preview
        console.print(f"\n[dim]Will redistribute with 2-day gaps from {start_date}[/dim]\n")

        confirm = self.session.prompt("Apply redistribution? (yes/no): ")
        if confirm.lower() not in ("yes", "y"):
            console.print("[dim]Cancelled[/dim]")
            return

        # Apply
        redistributed = store.redistribute_dates(articles, start_date, dry_run=False)
        store.save_json(redistributed)
        console.print("\n[green]✓ Dates redistributed![/green]")

    def _articles_show_date_mismatches(self, store):
        """Show date mismatches between files and JSON."""
        console.print("\n[bold]Date Mismatches[/bold]\n")

        file_articles = {a.filename: a for a in store.scan()}
        json_articles = {a.filename: a for a in store.load_json()}

        mismatches = []
        for filename, file_art in file_articles.items():
            if filename in json_articles:
                json_art = json_articles[filename]
                if file_art.published_date != json_art.published_date:
                    mismatches.append(
                        {
                            "id": file_art.id,
                            "filename": filename,
                            "file_date": file_art.published_date,
                            "json_date": json_art.published_date,
                        }
                    )

        if not mismatches:
            console.print("[green]✓ No date mismatches found[/green]")
            return

        console.print(f"[yellow]Found {len(mismatches)} date mismatch(es):[/yellow]\n")
        for m in mismatches[:10]:
            console.print(f"  ID {m['id']}: {m['filename'][:40]}...")
            console.print(f"    File: {m['file_date']} | JSON: {m['json_date']}")
        if len(mismatches) > 10:
            console.print(f"\n  ... and {len(mismatches) - 10} more")

        console.print("\n[dim]Run 'Sync' to fix (files are source of truth)[/dim]")
