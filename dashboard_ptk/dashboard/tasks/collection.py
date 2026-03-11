"""
Data collection tasks (GSC, PostHog)
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from rich.console import Console

from ..engine.env_resolver import EnvResolver
from ..models import Task
from .base import TaskRunner

console = Console()


class CollectionRunner(TaskRunner):
    """Runs data collection tasks."""
    
    def _load_manifest(self) -> dict:
        """Load project manifest if it exists.
        
        Checks in order:
        1. Project repo root (for standalone projects)
        2. Automation repo's general/{website_id}/manifest.json
        """
        repo_root = Path(self.project.repo_root)
        automation_dir = repo_root / ".github" / "automation"
        manifest_candidates = [
            automation_dir / "manifest.json",
            repo_root / "automation" / "manifest.json",
            repo_root / "manifest.json",
        ]
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
    
    def _validate_collection_domain(self, collection_file: Path, expected_domain: str) -> bool:
        """Verify collected data matches expected project domain."""
        try:
            data = json.loads(collection_file.read_text())
            meta = data.get("meta", {})
            actual_site = meta.get("site_url", "")
            
            # Normalize domains for comparison
            expected_clean = expected_domain.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
            actual_clean = actual_site.replace("sc-domain:", "").replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
            
            if expected_clean and actual_clean and expected_clean not in actual_clean:
                console.print(f"\n[red]ERROR: Domain mismatch![/red]")
                console.print(f"  Expected: {expected_domain}")
                console.print(f"  Got: {actual_site}")
                console.print(f"\n[yellow]This usually means:[/yellow]")
                console.print(f"  1. Wrong GSC site selected")
                console.print(f"  2. Project manifest URL is incorrect")
                console.print(f"  3. Explicit 'gsc_site' config needed in manifest")
                return False
            return True
        except Exception:
            return True  # Allow on validation error (defensive)
    
    def _site_matches_project(self, site: str, project) -> bool:
        """Check if GSC site string matches the project."""
        site_lower = site.lower()
        website_id = project.website_id.lower()
        
        # Check website_id is in site
        if website_id in site_lower:
            return True
        
        # Also check common variations
        manifest = self._load_manifest()
        url = manifest.get("url", "")
        if url:
            domain = urlparse(url).netloc.replace("www.", "")
            if domain and domain in site_lower:
                return True
        
        return False
    
    def _detect_gsc_site(self) -> tuple[str | None, str | None, dict]:
        """Detect GSC site and sitemap URL for a project.
        
        Priority:
        1. Explicit 'gsc_site' in manifest.json
        2. Derive from project's manifest.json URL
        3. Fallback: list GSC sites and find matching one
        
        Returns:
            (site, sitemap_url, manifest_data)
        """
        manifest = self._load_manifest()
        
        # Priority 1: Explicit gsc_site in manifest
        if manifest.get("gsc_site"):
            gsc_site = manifest["gsc_site"]
            # Derive sitemap from gsc_site or explicit sitemap config
            if manifest.get("sitemap"):
                sitemap = manifest["sitemap"]
            elif gsc_site.startswith("sc-domain:"):
                domain = gsc_site.replace("sc-domain:", "")
                sitemap = f"https://{domain}/sitemap.xml"
            else:
                sitemap = f"{gsc_site.rstrip('/')}/sitemap.xml"
            return gsc_site, sitemap, manifest
        
        # Priority 2: Derive from URL in manifest
        project_url = manifest.get("url", "")
        
        # If we have a URL, derive GSC site from it
        if project_url:
            domain = project_url.replace("https://", "").replace("http://", "").rstrip("/")
            if domain.startswith("www."):
                gsc_site = f"sc-domain:{domain[4:]}"
            else:
                gsc_site = f"sc-domain:{domain}"
            sitemap = manifest.get("sitemap") or f"{project_url.rstrip('/')}/sitemap.xml"
            return gsc_site, sitemap, manifest
        
        # Priority 4: Fallback - list GSC sites and find matching one
        try:
            success, stdout, _ = self.run_cli_command(
                [
                    "seo",
                    "gsc-indexing-report",
                    "--repo-root",
                    str(self.project.repo_root),
                    "--list-sites",
                ],
                timeout=30,
            )
            if success:
                website_id = self.project.website_id.lower()
                matching_site = None
                first_site = None
                
                for line in stdout.split('\n'):
                    line = line.strip()
                    if 'sc-domain:' in line or line.startswith('http'):
                        site = line
                        if first_site is None:
                            first_site = site
                        if website_id in site.lower():
                            matching_site = site
                            break
                
                site = matching_site if matching_site else first_site
                
                if site:
                    if site.startswith('sc-domain:'):
                        domain = site.replace('sc-domain:', "")
                        sitemap = f"https://{domain}/sitemap.xml"
                    else:
                        sitemap = f"{site.rstrip('/')}/sitemap.xml"
                    return site, sitemap, manifest
        except Exception:
            pass
        
        # Ultimate fallback
        if self.project.website_id:
            domain = self.project.website_id
            return f"sc-domain:{domain}", f"https://{domain}/sitemap.xml", manifest
        
        return None, None, manifest
    
    def run(self, task: Task) -> bool:
        """Execute a collection task."""
        console.print(f"\n[bold]Running: {task.title}[/bold]\n")
        
        # Parse source from task type (collect_gsc -> gsc)
        source = task.type.replace("collect_", "")
        
        # Determine output path
        output_path = self.task_list.artifacts_dir / f"{source}_collection.json"
        
        # Build command based on source
        if source == "gsc":
            return self._collect_gsc(task, output_path)
        elif source == "posthog":
            if self.auto_confirm_enabled():
                console.print("[dim]Non-interactive mode: running PostHog config check + collection.[/dim]")
                config_ok = self._collect_posthog(task, output_path, dry_run=True)
                if not config_ok:
                    console.print("[yellow]PostHog config check failed in non-interactive mode.[/yellow]")
                    return False
                return self._collect_posthog(task, output_path)

            # Offer dry-run config check first
            console.print("[cyan]PostHog Collection Setup[/cyan]")
            console.print("Before collecting, let's verify your configuration.\n")
            
            check_first = self.session.prompt(
                "Run config check first? (recommended) (y/n): "
            ).lower() == "y"
            
            if check_first:
                console.print()
                config_ok = self._collect_posthog(task, output_path, dry_run=True)
                if not config_ok:
                    console.print("\n[yellow]Configuration check failed.[/yellow]")
                    fix_now = self.session.prompt(
                        "I can create a task to track this fix. Create task? (y/n): "
                    ).lower() == "y"
                    if fix_now:
                        fix_task = self.task_list.create_task(
                            task_type="fix_posthog_config",
                            title=f"Configure PostHog API key for {self.project.website_id}",
                            phase="implementation",
                            priority="high",
                            notes="Add POSTHOG_PERSONAL_API_KEY to .env.local\n\nSteps:\n1. Go to PostHog → Project Settings → Personal API Keys\n2. Create a new key\n3. Add to .env.local: POSTHOG_PERSONAL_API_KEY=your_key_here",
                            category="technical_seo"
                        )
                        console.print(f"[green]✓ Created task: {fix_task.title}[/green]")
                    return False
                
                console.print()
                proceed = self.session.prompt(
                    "Config check passed. Proceed with collection? (y/n): "
                ).lower() == "y"
                if not proceed:
                    return False
                console.print()
            
            return self._collect_posthog(task, output_path)
        else:
            console.print(f"[red]Unknown collection source: {source}[/red]")
            return False
    
    def _collect_gsc(self, task: Task, output_path: Path) -> bool:
        """Collect Google Search Console data."""
        repo_root = Path(self.project.repo_root)
        
        # Validate articles.json alignment first - critical for GSC mapping
        is_valid, mismatches = self.validate_articles_json()
        if not is_valid:
            console.print(f"\n[yellow]Collection aborted due to articles.json misalignment.[/yellow]")
            console.print(f"[dim]Fix the mismatches above, then retry this task.[/dim]")
            return False
        
        # Find manifest
        manifest_path = None
        manifest_candidates = [
            repo_root / ".github" / "automation" / "manifest.json",
            repo_root / "automation" / "manifest.json",
            repo_root / "manifest.json",
        ]
        for candidate in manifest_candidates:
            if candidate.exists():
                manifest_path = candidate
                break
        
        # Detect site and sitemap
        site, sitemap_url, manifest = self._detect_gsc_site()
        
        # Early validation: Check if we have proper configuration
        if not manifest_path and not manifest.get("url") and not manifest.get("gsc_site"):
            console.print(f"[red]✗ Missing configuration[/red]")
            console.print(f"\n[yellow]Create a manifest.json file:[/yellow]")
            console.print(f"  Location: {self.project.repo_root}/.github/automation/manifest.json")
            console.print(f"\n[dim]Example content:[/dim]")
            console.print('  {"url": "https://www.example.com", "gsc_site": "sc-domain:example.com"}')
            return False
        
        if not site:
            console.print("[red]✗ Could not detect GSC site.[/red]")
            console.print("[dim]Add to automation/manifest.json:[/dim]")
            console.print('  "gsc_site": "sc-domain:example.com"')
            return False
        
        # Interactive confirmation preview
        console.print(f"\n[bold]Collection Preview:[/bold]")
        console.print(f"  Project: [cyan]{self.project.name}[/cyan]")
        console.print(f"  Website ID: {self.project.website_id}")
        console.print(f"  GSC Site: [cyan]{site}[/cyan]")
        console.print(f"  Sitemap: [dim]{sitemap_url}[/dim]")
        
        # Warning if site doesn't match project
        if not self._site_matches_project(site, self.project):
            console.print(f"\n[yellow]⚠️  Warning: GSC site doesn't appear to match this project[/yellow]")
            console.print(f"   Expected something containing: '{self.project.website_id}'")
            console.print(f"   This may indicate wrong site selection.")
        
        # Require explicit confirmation for mismatched sites or fallback sources
        is_explicit_config = bool(manifest.get("gsc_site") or manifest.get("url"))
        if not is_explicit_config or not self._site_matches_project(site, self.project):
            if self.auto_confirm_enabled():
                console.print(
                    "[yellow]Non-interactive mode: blocking GSC collection due to ambiguous/mismatched site configuration.[/yellow]"
                )
                console.print(
                    "[dim]Set explicit manifest gsc_site/url matching project, then retry orchestration.[/dim]"
                )
                return False
            confirm = self.session.prompt("\nProceed with collection? (yes/no): ")
            if confirm.lower() != "yes":
                console.print("[dim]Collection cancelled.[/dim]")
                return False
        
        # Get service account path from secrets or environment
        service_account_path = self._get_service_account_path()
        
        cmd = [
            "seo", "gsc-indexing-report",
            "--repo-root", str(self.project.repo_root),
            "--site", site,
            "--sitemap-url", sitemap_url,
            "--limit", "200",
            "--workers", "8",
            "--include-raw",
            "--out-dir", str(self.task_list.artifacts_dir)
        ]
        
        if service_account_path:
            cmd.extend(["--service-account-path", str(service_account_path)])
        
        if manifest_path:
            cmd.extend(["--manifest", str(manifest_path)])
        
        try:
            start_time = time.time()
            console.print(f"\n[dim]Running collection (limit: 200, workers: 8)...[/dim]\n")
            
            success, stdout, stderr = self.run_cli_command(cmd, timeout=300)
            duration = time.time() - start_time
            
            # Show stdout if any
            if stdout:
                lines = stdout.strip().split('\n')[-5:]
                for line in lines:
                    if line.strip():
                        console.print(f"  {line}")
            
            # Check for actual success - file should exist
            artifact_files = list(self.task_list.artifacts_dir.glob("*.json"))
            new_files = [f for f in artifact_files if f.stat().st_mtime > (datetime.now().timestamp() - 60)]
            
            if success or new_files:
                if new_files:
                    # Rename most recent to standard name
                    newest = max(new_files, key=lambda p: p.stat().st_mtime)
                    standard_name = "gsc_collection.json"
                    standard_path = self.task_list.artifacts_dir / standard_name
                    
                    if standard_path.exists():
                        standard_path.unlink()
                    newest.rename(standard_path)
                    
                    # VALIDATION: Verify domain matches before accepting
                    expected_url = manifest.get("url", "")
                    if not self._validate_collection_domain(standard_path, expected_url):
                        console.print(f"\n[red]✗ Collection rejected: domain mismatch[/red]")
                        standard_path.unlink()  # Delete bad data
                        console.print(f"[dim]Deleted invalid collection file[/dim]")
                        return False
                    
                    console.print(f"[green]✓ Collection complete in {duration:.1f}s[/green]")
                    console.print(f"[dim]Saved: {standard_path.name}[/dim]")
                    task.output_artifact = f"artifacts/{standard_name}"
                    
                    # Parse collection results and create specific tasks
                    tasks_created = self._create_tasks_from_collection(standard_path)
                    if tasks_created > 0:
                        console.print(f"[green]✓ Created {tasks_created} specific fix tasks from GSC findings[/green]")
                    
                    # Check if all items are api_errors (indicates access issue)
                    api_error_count = self._count_api_errors(standard_path)
                    if api_error_count > 0 and tasks_created == 0:
                        # Create a task to fix GSC access
                        existing_access_task = any(
                            t.type == "fix_gsc_access" and t.status in ("todo", "in_progress")
                            for t in self.task_list.tasks
                        )
                        if not existing_access_task:
                            access_task = self.task_list.create_task(
                                task_type="fix_gsc_access",
                                title=f"Fix GSC access: {self.project.website_id} ({api_error_count} URLs blocked)",
                                phase="implementation",
                                priority="high",
                                notes=f"The GSC service account cannot access this property.\n\nAdd your service account email to Google Search Console.\nThe email is found in your service account JSON file (client_email field).\n\nSteps:\n1. Go to https://search.google.com/search-console\n2. Select the {self.project.website_id} property\n3. Settings → Users and Permissions\n4. Add your service account email\n5. Grant 'Full' or 'Restricted' permission\n\nAfter fixing, re-run the Collect GSC data task.",
                            )
                            console.print(f"[yellow]⚠ Created task: {access_task.title}[/yellow]")
                            console.print(f"[dim]  The service account needs GSC access to collect data[/dim]")
                            tasks_created += 1
                    
                    task.status = "done"
                    task.completed_at = datetime.now().isoformat()
                    self.task_list.save()
                    
                    # Only create generic investigation task if no specific tasks were created
                    if tasks_created == 0:
                        existing_investigation = any(
                            t.type == "investigate_gsc" and t.status == "todo" 
                            for t in self.task_list.tasks
                        )
                        if not existing_investigation:
                            inv_task = self.task_list.create_investigation_task("gsc", task)
                            task.spawns_tasks.append(inv_task.id)
                            console.print(f"[dim]Created: {inv_task.title}[/dim]")
                        else:
                            console.print(f"[dim]Investigation task already exists[/dim]")
                    
                    return True
            
            # Show detailed error info
            console.print(f"[red]✗ Collection failed[/red]")
            
            if stderr:
                console.print(f"\n[dim]Error details:[/dim]")
                # Show last few lines of stderr
                stderr_lines = stderr.strip().split('\n')[-10:]
                for line in stderr_lines:
                    if line.strip():
                        console.print(f"  [red]{line}[/red]")
            
            # Show troubleshooting hints
            console.print(f"\n[yellow]Troubleshooting:[/yellow]")
            console.print(f"  1. Check GSC credentials are configured")
            console.print(f"  2. Verify site '{site}' exists in GSC")
            console.print(f"  3. Check sitemap URL is accessible: {sitemap_url}")
            console.print(f"  4. Try running manually:")
            console.print(f"[dim]     automation-cli seo gsc-indexing-report --site {site} --sitemap-url {sitemap_url} --limit 10[/dim]")
            
            return False
            
        except Exception as e:
            from rich.markup import escape
            console.print(f"[red]Error: {escape(str(e))}[/red]")
            import traceback
            console.print(f"[dim]{escape(traceback.format_exc())}[/dim]")
            return False
    
    def _count_api_errors(self, collection_file: Path) -> int:
        """Count items with api_error reason code."""
        try:
            data = json.loads(collection_file.read_text())
            items = data.get("items", [])
            return sum(1 for item in items if item.get("reason_code") == "api_error")
        except Exception:
            return 0
    
    def _create_tasks_from_collection(self, collection_file: Path) -> int:
        """Parse GSC collection results and create specific fix tasks.
        
        Returns:
            Number of tasks created
        """
        try:
            import json
            data = json.loads(collection_file.read_text())
            items = data.get("items", [])
            
            tasks_created = 0
            seen_issues = set()  # Track unique issues to avoid duplicates
            
            for item in items[:20]:  # Limit to top 20 issues
                url = item.get("url", "")
                reason = item.get("reason_code", "unknown")
                action = item.get("action", "")
                verdict = item.get("verdict", "")
                
                # Skip API errors and duplicates
                if reason in ("api_error", "ok", "indexed"):
                    continue
                
                # Create unique key for deduplication
                issue_key = f"{reason}:{url}"
                if issue_key in seen_issues:
                    continue
                seen_issues.add(issue_key)
                
                # Map reasons to task types
                task_type_map = {
                    "not_indexed": "fix_indexing",
                    "crawl_anomaly": "fix_technical",
                    "redirect_error": "fix_technical",
                    "soft_404": "fix_content",
                    "duplicate_content": "fix_content",
                    "canonical_mismatch": "fix_technical",
                    "robots_blocked": "fix_technical",
                }
                
                task_type = task_type_map.get(reason, "fix_indexing")
                
                # Create descriptive title
                url_slug = url.replace(f"https://www.{self.project.website_id}.com/", "").replace(f"https://{self.project.website_id}.com/", "")
                title = f"Fix {reason.replace('_', ' ')}: {url_slug}"
                
                # Check if similar task already exists
                existing = any(
                    t.type == task_type and url in (t.title or "")
                    for t in self.task_list.tasks
                    if t.status in ("todo", "in_progress")
                )
                if existing:
                    continue
                
                # Create the task
                fix_task = self.task_list.create_task(
                    task_type=task_type,
                    title=title,
                    phase="implementation",
                    priority="high" if item.get("priority", 0) > 50 else "medium",
                    notes=f"URL: {url}\nIssue: {reason}\nAction: {action}\nVerdict: {verdict}",
                    url=url
                )
                tasks_created += 1
            
            return tasks_created
            
        except Exception as e:
            console.print(f"[dim]Warning: Could not parse collection results: {e}[/dim]")
            return 0
    
    @staticmethod
    def verify_posthog_configs() -> list[dict]:
        """Verify PostHog configuration for all projects.
        
        Returns list of projects with config status:
        - ok: Config exists and is valid
        - missing: Config file doesn't exist
        - invalid: Config exists but is invalid JSON
        
        This is a static method so it can be called from main menu
        without instantiating CollectionRunner.
        """
        from ..core.project_manager import ProjectManager
        
        pm = ProjectManager()
        results = []
        
        for project in pm.projects:
            config_path = Path(project.repo_root) / ".github" / "automation" / "posthog_config.json"
            
            status = {"project": project.name, "website_id": project.website_id, "status": "unknown"}
            
            if not config_path.exists():
                status["status"] = "missing"
                status["message"] = "posthog_config.json not found"
            else:
                try:
                    import json
                    config = json.loads(config_path.read_text())
                    
                    # Check required fields
                    required = ["project_id", "api_key_env", "base_url"]
                    missing_fields = [f for f in required if f not in config]
                    
                    if missing_fields:
                        status["status"] = "invalid"
                        status["message"] = f"Missing fields: {', '.join(missing_fields)}"
                    else:
                        status["status"] = "ok"
                        status["message"] = f"Project ID: {config.get('project_id')}"
                        status["config"] = config
                        
                except json.JSONDecodeError as e:
                    status["status"] = "invalid"
                    status["message"] = f"Invalid JSON: {e}"
                except Exception as e:
                    status["status"] = "error"
                    status["message"] = str(e)
            
            results.append(status)
        
        return results
    
    def _check_posthog_config(self) -> tuple[bool, str]:
        """Check if PostHog API key is configured.
        
        The key can be in:
        - Environment variables
        - Machine secrets (~/.config/automation/secrets.env)
        - Automation repo .env file (shared across projects)
        
        Also checks if posthog_config.json exists for this project.
        
        Returns:
            (is_configured, message) tuple
        """
        resolver = EnvResolver(repo_root=Path(self.project.repo_root))

        # Check common env var names (POSTHOG is the shared key name)
        key_names = ["POSTHOG", "POSTHOG_PERSONAL_API_KEY", "POSTHOG_API_KEY"]

        for name in key_names:
            api_key, source, _ = resolver.resolve_key(name)
            if api_key:
                source_label = "environment" if source and source.startswith("env:") else source
                return True, f"Found {name} in {source_label}"
        
        # Also check if posthog_config.json exists
        posthog_config = Path(self.project.repo_root) / ".github" / "automation" / "posthog_config.json"
        if not posthog_config.exists():
            return False, f"posthog_config.json not found in {self.project.repo_root}/.github/automation/"
        
        return False, "POSTHOG API key not found. Add POSTHOG to ~/.config/automation/secrets.env or automation/.env"
    
    def _collect_posthog(self, task: Task, output_path: Path, dry_run: bool = False) -> bool:
        """Collect PostHog analytics data."""
        # Pre-flight check
        is_configured, config_msg = self._check_posthog_config()
        
        if dry_run:
            if is_configured:
                console.print(f"[green]✓ PostHog config check passed:[/green] {config_msg}")
                return True
            else:
                console.print(f"[red]✗ PostHog config check failed:[/red] {config_msg}")
                console.print("\n[yellow]To fix:[/yellow]")
                console.print("1. Go to PostHog → Project Settings → Personal API Keys")
                console.print("2. Create a new key")
                console.print("3. Add to .env.local in your project root:")
                console.print(f"   POSTHOG_PERSONAL_API_KEY=your_key_here")
                return False
        
        if not is_configured:
            console.print(f"[red]✗ PostHog collection cannot run:[/red] {config_msg}")
            console.print("\n[yellow]Run with dry-run first to see setup instructions.[/yellow]")
            return False
        
        env_file_args = []
        resolver = EnvResolver(repo_root=Path(self.project.repo_root))
        for name in ["POSTHOG", "POSTHOG_PERSONAL_API_KEY", "POSTHOG_API_KEY"]:
            _, source, _ = resolver.resolve_key(name)
            if source and not source.startswith("env:"):
                env_file_args = ["--env-file", source]
                break
        
        cmd = [
            "posthog", "report",
            "--repo-root", str(self.project.repo_root),
            "--out-dir", str(self.task_list.artifacts_dir),
            "--manifests-dir", str(Path(self.project.repo_root) / ".github" / "automation")
        ] + env_file_args
        
        try:
            console.print(f"[dim]DEBUG: Running command: {' '.join(cmd)}[/dim]")
            success, stdout, stderr = self.run_cli_command(cmd, timeout=300)
            console.print(f"[dim]DEBUG: success={success}, stdout={stdout[:200] if stdout else 'None'}, stderr={stderr[:200] if stderr else 'None'}[/dim]")
            
            if success:
                console.print("[green]✓ PostHog collection complete[/green]")
                task.status = "done"
                task.completed_at = datetime.now().isoformat()
                self.task_list.save()
                
                # Spawn investigation task (if not already exists)
                existing_investigation = any(
                    t.type == "investigate_posthog" and t.status == "todo"
                    for t in self.task_list.tasks
                )
                if not existing_investigation:
                    inv_task = self.task_list.create_investigation_task("posthog", task)
                    task.spawns_tasks.append(inv_task.id)
                    console.print(f"[dim]Created: {inv_task.title}[/dim]")
                else:
                    console.print(f"[dim]Investigation task already exists[/dim]")
                
                return True
            else:
                error_msg = "PostHog collection failed"
                if stderr:
                    error_msg += f": {stderr[:200]}"
                elif stdout:
                    error_msg += f": {stdout[:200]}"
                console.print(f"[red]✗ {error_msg}[/red]")
                self._set_error(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"PostHog collection error: {e}"
            console.print(f"[red]✗ {error_msg}[/red]")
            self._set_error(error_msg)
            return False
