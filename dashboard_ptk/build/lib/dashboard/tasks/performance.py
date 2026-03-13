"""
Performance analysis tasks - analyze GSC ranking data for optimization opportunities
"""
import json
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..engine.env_resolver import EnvResolver
from ..models import Task
from .base import TaskRunner

console = Console()


class PerformanceRunner(TaskRunner):
    """Runs GSC performance analysis tasks."""
    
    def _run_with_progress(self, func, *args, **kwargs):
        """Run a function with a progress spinner."""
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
        
        thread = threading.Thread(target=worker)
        thread.start()
        
        start_time = time.time()
        with Status("[dim]Analyzing GSC data...[/dim]", console=console, spinner="dots") as status:
            while not done.wait(timeout=0.1):
                elapsed = time.time() - start_time
                status.update(f"[dim]Analyzing... ({elapsed:.0f}s elapsed)[/dim]")
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    def run(self, task: Task) -> bool:
        """Execute a performance analysis task."""
        if task.type == "analyze_gsc_performance":
            return self._run_gsc_performance_analysis(task)
        return False
    
    def _run_gsc_performance_analysis(self, task: Task) -> bool:
        """Run GSC site scan and analyze ranking opportunities."""
        console.print(f"\n[bold]GSC Performance Analysis: {task.title}[/bold]")
        console.print("[dim]Analyzing top pages, decliners, and ranking opportunities...[/dim]\n")
        
        # Validate articles.json alignment first
        is_valid, _ = self.validate_articles_json()
        if not is_valid:
            console.print(f"\n[yellow]Analysis aborted due to articles.json misalignment.[/yellow]")
            console.print(f"[dim]Fix the mismatches, then retry this task.[/dim]")
            return False
        
        # Load manifest for site configuration
        manifest = self._load_manifest()
        site_url = manifest.get("gsc_site") or manifest.get("url", "")
        
        if not site_url:
            console.print("[red]✗ No GSC site configured in manifest[/red]")
            console.print("[dim]Add gsc_site or url to your manifest.json[/dim]")
            return False
        
        # Run GSC site scan
        try:
            scan_result = self._run_gsc_site_scan(task, site_url)
            if not scan_result:
                return False
            
            # Process and display results
            return self._process_scan_results(task, scan_result)
            
        except Exception as e:
            console.print(f"[red]Error during GSC analysis: {e}[/red]")
            return False
    
    def _load_manifest(self) -> dict:
        """Load project manifest."""
        repo_root = Path(self.project.repo_root)
        website_id = getattr(self.project, 'website_id', '') or getattr(self.project, 'site_id', '')
        
        manifest_candidates = [
            repo_root / ".github" / "automation" / "manifest.json",
            repo_root / "automation" / "manifest.json",
            repo_root / "manifest.json",
        ]
        
        # Also check general/<website_id>/manifest.json
        if website_id:
            manifest_candidates.insert(0, repo_root / "general" / website_id / "manifest.json")
        
        for candidate in manifest_candidates:
            if candidate.exists():
                try:
                    return json.loads(candidate.read_text())
                except Exception:
                    pass
        return {}
    
    def _get_service_account_path(self) -> Path | None:
        """Get GSC service account path from environment or secrets."""
        resolver = EnvResolver(repo_root=Path(self.project.repo_root))
        for env_var in ["GSC_SERVICE_ACCOUNT_PATH", "GOOGLE_APPLICATION_CREDENTIALS"]:
            path, _, _ = resolver.resolve_key(env_var)
            if path and Path(path).expanduser().exists():
                return Path(path).expanduser().resolve()
        
        # Fallback: Check common locations
        common_paths = [
            Path.home() / ".config" / "automation" / "gsc-service-account.json",
            Path.home() / ".config" / "gcloud" / "application_default_credentials.json",
        ]
        
        for path in common_paths:
            if path.exists():
                return path
        
        return None
    
    def _run_gsc_site_scan(self, task: Task, site_url: str) -> dict | None:
        """Run the gsc-site-scan CLI command."""
        repo_root = Path(self.project.repo_root)
        out_dir = self.task_list.artifacts_dir / "gsc_performance"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Build command - use the tool registry via run_cli_command
        # Note: Use "seo" prefix (not "automation-cli") to match how collection.py calls it
        cmd = [
            "seo", "gsc-site-scan",
            "--repo-root", str(repo_root),
            "--out-dir", str(out_dir),
            "--top-pages", "10",
            "--decliners", "10",
            "--max-pages", "20",
            "--compare-days", "7",
            "--long-compare-days", "28",
            "--queries-limit", "10",
        ]
        
        # Add manifest for site auto-detection
        # The CLI will read the manifest and auto-select the correct GSC property
        website_id = getattr(self.project, 'website_id', '') or getattr(self.project, 'site_id', '')
        manifest_path = repo_root / ".github" / "automation" / "manifest.json"
        if not manifest_path.exists():
            manifest_path = repo_root / "automation" / "manifest.json"
        if not manifest_path.exists() and website_id:
            manifest_path = repo_root / "general" / website_id / "manifest.json"
        if not manifest_path.exists():
            manifest_path = repo_root / "manifest.json"
        
        if manifest_path.exists():
            cmd.extend(["--manifest", str(manifest_path)])
        else:
            # Fallback: pass site directly if no manifest
            cmd.extend(["--site", site_url])
        
        console.print("[dim]Running GSC site scan (this may take 3-5 minutes)...[/dim]")
        console.print("[dim]Service account: Will be auto-detected by CLI[/dim]\n")
        
        try:
            # Use the base class method that properly handles tool registry
            # Note: Don't pass cwd - let it use the context's repo_root
            # Timeout: 600s (10 min) - gsc-site-scan is heavy: fetches pages, queries, inspections
            success, stdout, stderr = self.run_cli_command(cmd, timeout=600)
            
            if not success:
                console.print(f"[red]✗ GSC scan failed[/red]")
                if stderr:
                    console.print(f"[dim]STDERR: {stderr[:2000]}[/dim]")
                if stdout:
                    console.print(f"[dim]STDOUT: {stdout[:2000]}[/dim]")
                return None
            
            # Find the output file
            json_files = list(out_dir.glob("gsc_site_scan_*.json"))
            if not json_files:
                console.print("[red]✗ No scan output file found[/red]")
                return None
            
            # Get most recent
            latest_file = max(json_files, key=lambda p: p.stat().st_mtime)
            scan_data = json.loads(latest_file.read_text())
            
            console.print(f"[green]✓ Scan complete[/green] [dim]({len(scan_data.get('pages', []))} pages analyzed)[/dim]\n")
            return scan_data
            
        except Exception as e:
            console.print(f"[red]✗ Error running scan: {e}[/red]")
            return None
    
    def _process_scan_results(self, task: Task, scan_data: dict) -> bool:
        """Process scan results and create optimization tasks."""
        pages = scan_data.get("pages", [])
        
        if not pages:
            console.print("[yellow]No pages found in scan results[/yellow]")
            task.status = "done"
            task.completed_at = datetime.now().isoformat()
            self.task_list.save()
            return True
        
        # Categorize pages by opportunity type
        quick_wins = []      # Positions 3-15
        decliners = []       # Impression drops
        stable_top = []      # Positions 1-3
        needs_work = []      # Position > 15
        
        for page in pages:
            url = page.get("url", "")
            
            # Support both old format (short_window.current) and new format (metrics)
            metrics = page.get("metrics", {})
            position = metrics.get("position", 0)
            impressions = metrics.get("impressions", 0)
            clicks = metrics.get("clicks", 0)
            ctr = metrics.get("ctr", 0)
            
            # For delta, we'll use 0 for now (new format doesn't have historical comparison yet)
            impression_delta = 0
            
            page_summary = {
                "url": url,
                "position": position,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "impression_delta": impression_delta,
                "queries": page.get("queries", []),
                "inspection": page.get("inspection", {}),
            }
            
            # Categorize by position (no selection_reason in new format)
            if 1 <= position <= 3:
                stable_top.append(page_summary)
            elif 3 < position <= 15:
                quick_wins.append(page_summary)
            elif position > 15:
                needs_work.append(page_summary)
            else:
                # Position 0 or unknown - include in needs_work
                needs_work.append(page_summary)
        
        # Sort by opportunity
        quick_wins.sort(key=lambda x: x["position"])
        decliners.sort(key=lambda x: x["impression_delta"])
        stable_top.sort(key=lambda x: x["impressions"], reverse=True)
        
        # Display results
        self._display_opportunities(quick_wins, decliners, stable_top, needs_work)
        
        # Interactive selection for optimization tasks
        all_opportunities = quick_wins + decliners + stable_top
        if all_opportunities:
            return self._create_optimization_tasks(task, all_opportunities)
        
        console.print("\n[dim]No optimization opportunities identified[/dim]")
        task.status = "done"
        task.completed_at = datetime.now().isoformat()
        self.task_list.save()
        return True
    
    def _display_opportunities(self, quick_wins: list, decliners: list, stable_top: list, needs_work: list):
        """Display categorized opportunities."""
        
        # Quick Wins (Positions 3-15)
        if quick_wins:
            console.print("\n[bold green]🚀 Quick Wins (Positions 3-15)[/bold green]")
            console.print("[dim]Small improvements can yield big gains - these are on page 1 or top of page 2[/dim]\n")
            
            table = Table(show_header=True, header_style="bold")
            table.add_column("Page", min_width=30, max_width=50)
            table.add_column("Position", justify="center", width=8)
            table.add_column("Impressions", justify="right", width=12)
            table.add_column("CTR", justify="right", width=8)
            
            for page in quick_wins[:5]:
                url = page["url"].replace(f"https://{self.project.website_id}.com/", "").replace(f"https://www.{self.project.website_id}.com/", "")[:45]
                pos = f"{page['position']:.1f}"
                imp = f"{page['impressions']:,.0f}"
                ctr = f"{page['ctr']*100:.1f}%"
                table.add_row(url, pos, imp, ctr)
            
            console.print(table)
        
        # Decliners
        if decliners:
            console.print("\n[bold yellow]📉 Decliners (Impression Drops)[/bold yellow]")
            console.print("[dim]Pages losing visibility - needs attention[/dim]\n")
            
            table = Table(show_header=True, header_style="bold")
            table.add_column("Page", min_width=30, max_width=50)
            table.add_column("Position", justify="center", width=8)
            table.add_column("Imp. Drop", justify="right", width=10)
            
            for page in decliners[:5]:
                url = page["url"].replace(f"https://{self.project.website_id}.com/", "").replace(f"https://www.{self.project.website_id}.com/", "")[:45]
                pos = f"{page['position']:.1f}" if page['position'] > 0 else "-"
                drop = f"{page['impression_delta']:,.0f}"
                table.add_row(url, pos, drop)
            
            console.print(table)
        
        # Stable Top Performers
        if stable_top:
            console.print("\n[bold cyan]👑 Top Performers (Positions 1-3)[/bold cyan]")
            console.print("[dim]Your best ranking pages - protect and expand these[/dim]\n")
            
            table = Table(show_header=True, header_style="bold")
            table.add_column("Page", min_width=30, max_width=50)
            table.add_column("Position", justify="center", width=8)
            table.add_column("Impressions", justify="right", width=12)
            table.add_column("Clicks", justify="right", width=10)
            
            for page in stable_top[:5]:
                url = page["url"].replace(f"https://{self.project.website_id}.com/", "").replace(f"https://www.{self.project.website_id}.com/", "")[:45]
                pos = f"{page['position']:.1f}"
                imp = f"{page['impressions']:,.0f}"
                clicks = f"{page['clicks']:,.0f}"
                table.add_row(url, pos, imp, clicks)
            
            console.print(table)
        
        # Needs Work
        if needs_work:
            console.print(f"\n[dim]{len(needs_work)} pages ranking > position 15 (not shown)[/dim]")
    
    def _create_optimization_tasks(self, task: Task, opportunities: list) -> bool:
        """Create optimization tasks based on user selection."""
        result_dir = self.task_list.task_results_dir / task.id
        result_dir.mkdir(parents=True, exist_ok=True)
        
        # Save analysis results
        analysis_file = result_dir / "performance_analysis.json"
        analysis_data = {
            "analysis_date": datetime.now().isoformat(),
            "website_id": self.project.website_id,
            "total_pages_analyzed": len(opportunities),
            "opportunities": opportunities,
        }
        analysis_file.write_text(json.dumps(analysis_data, indent=2))
        
        console.print("\n" + "=" * 70)
        console.print("[bold cyan]🎯 Create Optimization Tasks[/bold cyan]")
        console.print("[dim]Select pages to optimize based on GSC performance data[/dim]\n")
        
        # Display numbered list
        for i, opp in enumerate(opportunities[:15], 1):
            url = opp["url"].replace(f"https://{self.project.website_id}.com/", "").replace(f"https://www.{self.project.website_id}.com/", "")
            pos = opp["position"]
            imp = opp["impressions"]
            
            # Determine opportunity type and emoji
            if opp.get("impression_delta", 0) < -100:
                opp_type = "📉 Declining"
                style = "yellow"
            elif 3 < pos <= 10:
                opp_type = "🚀 Page 1 (low)"
                style = "green"
            elif 10 < pos <= 15:
                opp_type = "🎯 Page 2 (top)"
                style = "cyan"
            elif pos <= 3:
                opp_type = "👑 Top 3"
                style = "bright_white"
            else:
                opp_type = "📄 Other"
                style = "dim"
            
            panel = Panel(
                f"[dim]Position: {pos:.1f} | Impressions: {imp:,.0f}[/dim]",
                title=f"[{i}] [{style}]{opp_type}[/{style}] {url[:40]}",
                border_style=style
            )
            console.print(panel)
        
        # Get user selection
        console.print("\n[bold]Select pages to create optimization tasks:[/bold]")
        console.print("Enter numbers (1-15) separated by commas, or 'all' for all, or 'none' to skip")
        console.print("Examples: '1,3,5' or '2,4,6' or 'all'")
        
        selection = self.session.prompt("\nYour selection: ").strip().lower()
        
        selected_indices = []
        if selection == 'all':
            selected_indices = list(range(len(opportunities[:15])))
        elif selection in ('none', ''):
            selected_indices = []
        else:
            try:
                for part in selection.split(','):
                    idx = int(part.strip()) - 1
                    if 0 <= idx < len(opportunities[:15]):
                        selected_indices.append(idx)
            except ValueError:
                console.print("[yellow]Invalid input, creating no tasks[/yellow]")
        
        # Create tasks
        created_count = 0
        result_dir_relative = result_dir.relative_to(self.task_list.automation_dir)
        
        for idx in selected_indices:
            opp = opportunities[idx]
            url = opp["url"]
            position = opp["position"]
            
            # Extract slug from URL
            slug = url.rstrip('/').split('/')[-1] if '/' in url else url
            
            # Determine task type and priority based on position
            if position <= 3:
                task_type = "optimize_article"
                priority = "medium"  # Protect what's working
                title = f"Optimize top performer: {slug[:40]}"
            elif position <= 10:
                task_type = "optimize_article"
                priority = "high"  # Biggest opportunity
                title = f"Optimize for position boost: {slug[:40]}"
            elif position <= 15:
                task_type = "optimize_article"
                priority = "high"
                title = f"Push to page 1: {slug[:40]}"
            else:
                task_type = "optimize_article"
                priority = "medium"
                title = f"Improve rankings: {slug[:40]}"
            
            # Check for duplicates
            existing = any(
                t.title == title and t.parent_task == task.id
                for t in self.task_list.tasks
            )
            if existing:
                console.print(f"[dim]Skipping duplicate: {title[:50]}...[/dim]")
                continue
            
            new_task = self.task_list.create_task(
                task_type=task_type,
                title=title,
                phase="implementation",
                priority=priority,
                depends_on=task.id,
                parent_task=task.id,
                category="performance_optimization",
                url=url,
                notes=f"Current position: {position:.1f}\nImpressions: {opp['impressions']:,.0f}\nCTR: {opp['ctr']*100:.2f}%",
                input_artifact=str(result_dir_relative / "performance_analysis.json"),
                implementation_mode="direct"
            )
            self.task_list.save()
            task.spawns_tasks.append(new_task.id)
            created_count += 1
        
        # Summary
        if created_count > 0:
            console.print(f"\n[green]✓ Created {created_count} optimization tasks[/green]")
        else:
            console.print("\n[dim]No optimization tasks created[/dim]")
        
        # Mark analysis task complete
        task.status = "done"
        task.completed_at = datetime.now().isoformat()
        task.result_path = str(result_dir_relative)
        self.task_list.save()
        
        return True
