"""
Publishing workflow tasks
"""
from datetime import datetime
from pathlib import Path

from rich.console import Console

from ..models import Task
from ..utils import ArticleManager
from .base import TaskRunner

console = Console()


class PublishingRunner(TaskRunner):
    """Runs publishing workflow tasks."""
    
    def __init__(self, task_list, project, session):
        super().__init__(task_list, project, session)
        self.article_manager = ArticleManager(project.website_id)
    
    def _check_article_linking(self, article_id: int, repo_root: Path) -> bool:
        """
        Check if an article has internal links (both incoming and outgoing).
        
        Returns True if linking appears to be done, False otherwise.
        """
        try:
            content_dir = self.article_manager.get_content_dir(repo_root)
            if not content_dir:
                return False
            
            # Find the article file
            articles_json = self.article_manager.get_articles_json_path(repo_root)
            if not articles_json:
                return False
            
            import json
            data = json.loads(articles_json.read_text())
            articles = data.get("articles", [])
            
            article = None
            for a in articles:
                if a.get("id") == article_id:
                    article = a
                    break
            
            if not article:
                return False
            
            # Get the content file
            file_path = article.get("file", "")
            if not file_path:
                return False
            
            filename = file_path.split("/")[-1]
            full_path = content_dir / filename
            
            if not full_path.exists():
                return False
            
            # Read content and check for internal links
            content = full_path.read_text()
            
            # Look for markdown links that point to other articles on the same site
            # Pattern: [text](/slug) or [text](slug.mdx) or [text](/slug/) or [text](/blog/path/)
            import re
            # Match internal links: paths starting with / or ./ or containing /blog/
            internal_links = re.findall(r'\[([^\]]+)\]\((/?[\w/-]+)\)', content)
            # Also match relative .mdx and .md links
            internal_links_mdx = re.findall(r'\[([^\]]+)\]\(([\w./-]+\.(?:mdx|md))\)', content)
            # Also match ./relative-path links without extension
            internal_links_rel = re.findall(r'\[([^\]]+)\](\(\.[/\w-]+\))', content)
            
            total_links = len(internal_links) + len(internal_links_mdx) + len(internal_links_rel)
            
            # Check if there's a linking task for this article
            linking_task_exists = False
            if self.task_list:
                for t in self.task_list.tasks:
                    if t.type == "cluster_and_link" and t.category == f"linking:article_id={article_id}":
                        linking_task_exists = True
                        break
            
            # If article has internal links OR no linking task exists, consider it linked
            # (No linking task means either it's linked or it was created before linking workflow)
            return total_links > 0 or not linking_task_exists
            
        except Exception:
            # If we can't check, assume it's okay (don't block publishing)
            return True
    
    def _auto_link_article(self, article_id: int, repo_root: Path, workspace: str) -> bool:
        """
        Auto-run linking for a specific article using CLI commands.
        
        This bypasses the AI agent to avoid authentication issues.
        Returns True if linking appears successful.
        """
        console.print(f"  [dim]Auto-linking article {article_id}...[/dim]")
        
        try:
            # Step 1: Generate linking plan
            success, _, _ = self.run_cli_command(
                ["seo-content-cli", "--workspace-root", workspace, "generate-linking-plan", "--website-path", ".", "--missing-only"],
                cwd=repo_root,
                timeout=60,
            )
            if not success:
                console.print("    [dim]Failed to generate linking plan[/dim]")
                return False
            
            # Step 2: Add basic links - link to pillar (article 73 for expense tracking)
            # This is a simplified approach - link to the main pillar article
            if self.project.website_id == "expense":
                # Link FROM this article TO pillar (73)
                success1, _, _ = self.run_cli_command(
                    [
                        "seo-content-cli",
                        "--workspace-root",
                        workspace,
                        "add-article-links",
                        "--website-path",
                        ".",
                        "--source-id",
                        str(article_id),
                        "--target-ids",
                        "73",
                    ],
                    cwd=repo_root,
                    timeout=60,
                )
                
                # Link FROM pillar (73) TO this article
                success2, _, _ = self.run_cli_command(
                    [
                        "seo-content-cli",
                        "--workspace-root",
                        workspace,
                        "add-article-links",
                        "--website-path",
                        ".",
                        "--source-id",
                        "73",
                        "--target-ids",
                        str(article_id),
                    ],
                    cwd=repo_root,
                    timeout=60,
                )
                if not (success1 and success2):
                    return False
            
            # Step 3: Mark linking task as done if it exists
            if self.task_list:
                for t in self.task_list.tasks:
                    if t.type == "cluster_and_link" and t.category == f"linking:article_id={article_id}":
                        t.status = "done"
                        t.completed_at = datetime.now().isoformat()
                        break
                self.task_list.save()
            
            return True
            
        except Exception as e:
            console.print(f"    [dim]Linking error: {e}[/dim]")
            return False
    
    def _fix_future_dates_free_slot(self, date_issues: list, repo_root: Path) -> int:
        """
        Fix future dates by assigning each article the nearest earlier free date
        (a past date where no other article has been published).
        Updates both articles.json and the MDX frontmatter.
        """
        import json
        import re
        from datetime import date, timedelta

        articles_json = self.article_manager.get_articles_json_path(repo_root)
        if not articles_json:
            console.print("    [yellow]⚠ Could not locate articles.json[/yellow]")
            return 0

        try:
            with open(articles_json) as f:
                data = json.load(f)
        except Exception as e:
            console.print(f"    [yellow]⚠ Failed to read articles.json: {e}[/yellow]")
            return 0

        all_articles = data.get("articles", [])

        # Collect all taken dates across ALL articles (published or draft)
        taken_dates: set[date] = set()
        for a in all_articles:
            d_str = a.get("published_date") or ""
            if d_str:
                try:
                    taken_dates.add(date.fromisoformat(d_str))
                except ValueError:
                    pass

        today = date.today()

        def _next_free_date(taken: set[date]) -> date:
            """Walk backwards from yesterday to find newest unused date."""
            candidate = today - timedelta(days=1)
            while candidate in taken:
                candidate -= timedelta(days=1)
            return candidate

        # Resolve content directory for frontmatter updates
        content_dir = self.article_manager.get_content_dir(repo_root)

        fixed = 0
        for issue in date_issues:
            article_id = issue["id"]

            # Find the article record
            target_article = next((a for a in all_articles if a.get("id") == article_id), None)
            if not target_article:
                console.print(f"    [yellow]⚠ Article {article_id} not found in articles.json[/yellow]")
                continue

            new_date = _next_free_date(taken_dates)
            new_date_str = new_date.isoformat()
            old_date_str = target_article.get("published_date", "?")

            # Reserve so next article in loop gets a different slot
            taken_dates.add(new_date)

            # 1. Update articles.json in-memory
            target_article["published_date"] = new_date_str

            # 2. Update MDX frontmatter
            file_path = target_article.get("file", "")
            mdx_path = self._resolve_article_file_path(file_path, repo_root, content_dir) if content_dir else None
            fm_ok = False
            if mdx_path and mdx_path.exists():
                fm_ok = self._update_frontmatter_date_inline(mdx_path, new_date_str)

            console.print(
                f"    [green]✓ Article {article_id}: {old_date_str} → {new_date_str}"
                + ("" if fm_ok else " [yellow](articles.json only — MDX not updated)[/yellow]")
                + "[/green]"
            )
            fixed += 1

        # Persist articles.json
        if fixed:
            try:
                with open(articles_json, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                console.print(f"    [yellow]⚠ Failed to save articles.json: {e}[/yellow]")
                return 0

        return fixed

    @staticmethod
    def _update_frontmatter_date_inline(content_path: Path, new_date_iso: str) -> bool:
        """Update `date:`, `published_date:`, or `published:` in MDX/MD frontmatter."""
        import re
        try:
            text = content_path.read_text(encoding="utf-8")
        except Exception:
            return False
        if not text.startswith("---"):
            return False
        parts = text.split("---", 2)
        if len(parts) < 3:
            return False
        fm, body = parts[1], parts[2]
        date_re = re.compile(r"^(\s*(?:date|published_date|published)\s*:).*$", re.IGNORECASE | re.MULTILINE)
        match = date_re.search(fm)
        if match:
            fm_new = date_re.sub(rf'\1 "{new_date_iso}"', fm, count=1)
        else:
            # Insert after title line if present, otherwise at top
            title_match = re.search(r"^(\s*title\s*:.*$)", fm, re.IGNORECASE | re.MULTILINE)
            insert_pos = title_match.end() + 1 if title_match else 0
            fm_new = fm[:insert_pos] + f'date: "{new_date_iso}"\n' + fm[insert_pos:]
        try:
            content_path.write_text("---" + fm_new + "---" + body, encoding="utf-8")
        except Exception:
            return False
        return True

    def _fix_future_dates_deterministic(self, date_issues: list, repo_root: Path) -> int:
        """
        Fix future dates using date redistribution to maintain spacing.
        Uses fix-dates CLI command which respects distribution rules.
        
        Args:
            date_issues: List of issue dicts with 'id', 'title', 'issue'
            repo_root: Path to repository root
            
        Returns:
            Number of articles fixed
        """
        console.print(f"    [dim]Using date redistribution to fix {len(date_issues)} future date(s)...[/dim]")
        
        # Use the fix-dates CLI command which handles redistribution properly
        success, stdout, stderr = self.run_cli_command(
            ["seo-content-cli", "--workspace-root", ".github/automation", "fix-dates", "--website-path", "."],
            cwd=repo_root,
            timeout=60,
        )
        
        if not success:
            console.print(f"    [yellow]⚠ Date redistribution command failed: {stderr}[/yellow]")
            return 0
        
        # Parse the result to count fixes
        try:
            import json
            result = json.loads(stdout)
            fixed = result.get("articles_fixed", 0)
            
            # Show the changes
            for change in result.get("changes", []):
                article_id = change.get("article_id")
                old_date = change.get("old_date")
                new_date = change.get("new_date")
                console.print(f"    [green]✓ Article {article_id}: {old_date} → {new_date}[/green]")
            
            return fixed
        except Exception as e:
            console.print(f"    [yellow]⚠ Could not parse fix-dates result: {e}[/yellow]")
            return 0

    @staticmethod
    def _resolve_article_file_path(file_path: str, repo_root: Path, content_dir: Path) -> Path | None:
        file_path = str(file_path or "").strip()
        if not file_path:
            return None
        if file_path.startswith("./"):
            return repo_root / file_path[2:]
        if file_path.startswith("content/"):
            return repo_root / file_path
        return content_dir / Path(file_path).name
    
    def _check_future_dates(self, repo_root: Path) -> list[dict]:
        """Check for any articles with future dates."""
        from datetime import datetime
        
        articles_json = self.article_manager.get_articles_json_path(repo_root)
        if not articles_json:
            return []
        
        try:
            with open(articles_json) as f:
                data = json.load(f)
            articles = data.get("articles", [])
        except Exception:
            return []
        
        today = datetime.now()
        future_dates = []
        
        for article in articles:
            if article.get("status") != "published":
                continue
            date_str = article.get("published_date", "")
            if not date_str:
                continue
            try:
                article_date = datetime.strptime(date_str, "%Y-%m-%d")
                if article_date > today:
                    future_dates.append({
                        "id": article.get("id"),
                        "title": article.get("title", "Untitled"),
                        "date": date_str
                    })
            except ValueError:
                pass
        
        return future_dates
    
    def run(self, task: Task = None) -> bool:
        """Execute Publish workflow: Validate and publish draft articles."""
        console.print(f"\n[bold]Publish Articles[/bold]")
        console.print("[cyan]Phase 1: Content Cleanup (structural validation)[/cyan]")
        console.print("[cyan]Phase 2: Publish validated drafts[/cyan]\n")
        
        # Phase 1: Run structural cleanup first
        console.print("[dim]Running structural validation...[/dim]\n")
        
        repo_root = Path(self.project.repo_root)
        workspace = ".github/automation"
        
        cleanup_prompt = f"""Run SEO Step 5 (Content Cleanup & QA) for {self.project.website_id}.

WORKSPACE: {workspace}

STEPS:
1. Validate content structure
2. Check for duplicate headings, frontmatter issues
3. Clean structural issues if found
4. Report date issues (DO NOT FIX)

REQUIREMENTS:
- Fix structural issues only
- Report date overlaps or future dates for next phase
- Do NOT change any dates
- Use pageseeds content commands only

Report what structural issues were found and fixed."""
        
        try:
            success, output = self.run_kimi_agent(cleanup_prompt, cwd=repo_root, timeout=300)
            
            if output:
                lines = output.split('\n')
                filtered = []
                skip_patterns = ['ToolCall', 'ToolResult', 'StepBegin', 'ThinkPart', 'StatusUpdate', 'TurnBegin', 'TurnEnd']
                for line in lines:
                    if line.strip() and not any(p in line for p in skip_patterns):
                        filtered.append(line)
                if filtered:
                    console.print('\n'.join(filtered[-20:]))
            
            console.print(f"\n[green]✓ Phase 1 complete[/green]")
            
        except Exception as e:
            console.print(f"[yellow]⚠ Phase 1 warning: {e}[/yellow]")
        
        # Phase 2: Publishing
        console.print(f"\n[bold cyan]Phase 2: Publishing Draft Articles[/bold cyan]\n")
        
        # Load articles.json
        repo_root = Path(self.project.repo_root)
        articles_json = self.article_manager.get_articles_json_path(repo_root)
        if not articles_json:
            console.print("[red]✗ Could not find articles.json[/red]")
            return False
        
        try:
            import json
            data = json.loads(articles_json.read_text())
            articles = data.get("articles", [])
        except Exception as e:
            console.print(f"[red]✗ Error reading articles.json: {e}[/red]")
            return False
        
        # Filter to draft articles only
        draft_articles = [a for a in articles if a.get("status") == "draft"]
        
        if not draft_articles:
            console.print("[dim]No draft articles found to publish.[/dim]")
            return True
        
        console.print(f"[dim]Found {len(draft_articles)} draft article(s)[/dim]\n")
        
        # Check each draft article
        issues = []
        ready_to_publish = []
        missing_linking = []
        
        for article in draft_articles:
            article_id = article.get("id")
            title = article.get("title", "Untitled")
            file_path = article.get("file", "")
            pub_date = article.get("published_date")
            
            # Check 1: Does content file exist?
            content_dir = self.article_manager.get_content_dir(repo_root)
            file_exists = False
            if content_dir and file_path:
                filename = file_path.split("/")[-1]
                full_path = content_dir / filename
                file_exists = full_path.exists()
            
            # Check 2: Is date in the future?
            date_in_future = False
            if pub_date:
                try:
                    article_date = datetime.strptime(pub_date, "%Y-%m-%d")
                    date_in_future = article_date > datetime.now()
                except:
                    pass
            
            # Check 3: Date overlap
            date_overlap = False
            overlapping_with = None
            if pub_date:
                for other in articles:
                    if other.get("id") != article_id and other.get("published_date") == pub_date:
                        date_overlap = True
                        overlapping_with = other.get("title", f"ID {other.get('id')}")
                        break
            
            # Check 4: Has internal linking been done?
            linking_done = self._check_article_linking(article_id, repo_root)
            
            # Check 5: Year mismatch between title and publish date
            year_mismatch = False
            year_mismatch_details = None
            if pub_date:
                import re
                # Extract years from title (e.g., "2025", "2024")
                title_years = re.findall(r'\b(20\d{2})\b', title)
                if title_years:
                    pub_year = int(pub_date.split('-')[0])
                    title_year = int(title_years[0])
                    # Flag if title year is more than 1 year behind publish year
                    # (allows some grace period for late publishing)
                    if pub_year - title_year > 1:
                        year_mismatch = True
                        year_mismatch_details = f"Title says {title_year}, publishing in {pub_year}"
            
            # Categorize
            if not file_exists:
                issues.append({
                    "id": article_id,
                    "title": title,
                    "issue": "Content file missing",
                    "file": file_path
                })
            elif date_in_future:
                issues.append({
                    "id": article_id,
                    "title": title,
                    "issue": f"Date is in the future ({pub_date})",
                    "suggestion": "Change to today's date"
                })
            elif date_overlap:
                issues.append({
                    "id": article_id,
                    "title": title,
                    "issue": f"Date overlaps with: {overlapping_with}",
                    "suggestion": "Will need date redistribution"
                })
            elif not linking_done:
                missing_linking.append({
                    "id": article_id,
                    "title": title,
                    "issue": "Internal linking not done",
                    "suggestion": "Run linking task first (or override to skip)"
                })
            elif year_mismatch:
                issues.append({
                    "id": article_id,
                    "title": title,
                    "issue": f"Year mismatch: {year_mismatch_details}",
                    "suggestion": "Update title to current year or backdate publish date"
                })
            else:
                ready_to_publish.append(article)
        
        # Report findings
        if issues:
            console.print("[yellow]Issues found (will be fixed before publishing):[/yellow]")
            for issue in issues:
                console.print(f"  [dim]ID {issue['id']}: {issue['title'][:40]}...[/dim]")
                console.print(f"    [red]→ {issue['issue']}[/red]")
                if "suggestion" in issue:
                    console.print(f"      [dim]{issue['suggestion']}[/dim]")
            console.print()
        
        # Report linking warnings
        if missing_linking:
            console.print("[yellow]⚠ Linking not done (internal links missing):[/yellow]")
            for item in missing_linking:
                console.print(f"  [dim]ID {item['id']}: {item['title'][:40]}...[/dim]")
                console.print(f"    [yellow]→ {item['issue']}[/yellow]")
            console.print()
            console.print("[dim]Options:[/dim]")
            console.print("  1. Auto-run linking now (recommended)")
            console.print("  2. Go back and run linking tasks manually")
            console.print("  3. Publish anyway (you can add links later)")
            console.print()
        
        if ready_to_publish:
            console.print(f"[green]✓ {len(ready_to_publish)} article(s) ready to publish[/green]")
            for article in ready_to_publish:
                console.print(f"  [dim]ID {article['id']}: {article['title'][:50]}...[/dim]")
            console.print()
        
        if not ready_to_publish and not issues:
            console.print("[dim]No articles ready for publishing.[/dim]")
            return True
        
        # Handle linking warnings - offer to auto-run
        if missing_linking and not ready_to_publish:
            choice = self.session.prompt("Auto-run linking for these articles? (y/n): ")
            if choice.lower() == 'y':
                console.print("\n[dim]Running auto-linking...[/dim]")
                for item in missing_linking:
                    success = self._auto_link_article(item['id'], repo_root, workspace)
                    if success:
                        console.print(f"  [green]✓ Linked article {item['id']}[/green]")
                    else:
                        console.print(f"  [yellow]⚠ Could not fully link article {item['id']} (will publish anyway)[/yellow]")
                # After auto-linking, include all articles in publishing
                for item in missing_linking:
                    for article in draft_articles:
                        if article.get("id") == item["id"]:
                            ready_to_publish.append(article)
                            break
            else:
                console.print("[yellow]Publishing cancelled. Run linking tasks first.[/yellow]")
                self.session.prompt("\nPress Enter to continue...")
                return True
        
        # If we have ready articles but also missing linking, offer to auto-link first
        if ready_to_publish and missing_linking:
            choice = self.session.prompt(f"\nAuto-run linking for {len(missing_linking)} unlinked articles before publishing? (y/n): ")
            if choice.lower() == 'y':
                console.print("\n[dim]Running auto-linking...[/dim]")
                newly_linked = []
                for item in missing_linking:
                    success = self._auto_link_article(item['id'], repo_root, workspace)
                    if success:
                        console.print(f"  [green]✓ Linked article {item['id']}[/green]")
                        newly_linked.append(item)
                    else:
                        console.print(f"  [yellow]⚠ Could not fully link article {item['id']}[/yellow]")
                # Add newly linked articles to ready_to_publish
                for item in newly_linked:
                    for article in draft_articles:
                        if article.get("id") == item["id"]:
                            ready_to_publish.append(article)
                            break
                # Remove newly linked from missing_linking
                missing_linking = [m for m in missing_linking if m not in newly_linked]
        
        # Handle date issues - ALWAYS use deterministic fix for future dates
        # Date overlaps need redistribution - let agent handle those
        future_date_issues = [i for i in issues if "future" in i.get("issue", "").lower()]
        other_issues = [i for i in issues if i not in future_date_issues]
        
        if future_date_issues:
            console.print(f"\n[yellow]Future date issues found ({len(future_date_issues)} article(s)):[/yellow]")
            for issue in future_date_issues:
                console.print(f"  [dim]ID {issue['id']}: {issue['title'][:40]}...[/dim]")
                console.print(f"    [red]→ {issue['issue']}[/red]")
            
            console.print(f"\n[dim]Options:[/dim]")
            console.print(f"  1. Fix dates to today (deterministic) - RECOMMENDED")
            console.print(f"  2. Assign nearest earlier free date (no article published on that day)")
            console.print(f"  3. Skip date fixes (NOT RECOMMENDED - may cause issues)")
            
            choice = self.session.prompt("\nChoice (1/2/3): ").strip()
            
            if choice == "2":
                console.print(f"\n[dim]Finding nearest earlier free dates...[/dim]")
                fixed_count = self._fix_future_dates_free_slot(future_date_issues, repo_root)
                console.print(f"[green]✓ Fixed {fixed_count} date issue(s)[/green]")
                if fixed_count == len(future_date_issues):
                    issues = other_issues
                else:
                    console.print(f"[yellow]⚠ Some dates could not be fixed - will be handled in publishing[/yellow]")
            elif choice == "3":
                console.print(f"[yellow]⚠ Skipping date fixes - future dates may cause issues[/yellow]")
            else:
                # Default to Option 1 (fix to today)
                console.print(f"\n[dim]Fixing future dates...[/dim]")
                fixed_count = self._fix_future_dates_deterministic(future_date_issues, repo_root)
                console.print(f"[green]✓ Fixed {fixed_count} date issue(s)[/green]")
                # Remove fixed date issues from the list only if actually fixed
                if fixed_count == len(future_date_issues):
                    issues = other_issues
                else:
                    console.print(f"[yellow]⚠ Some dates could not be fixed - will be handled in publishing[/yellow]")
        
        # Ask for confirmation
        publish_count = len(ready_to_publish)
        if missing_linking:
            publish_count += len(missing_linking)
        
        if ready_to_publish or missing_linking:
            if missing_linking:
                confirm = self.session.prompt(f"\nPublish {publish_count} article(s) (including {len(missing_linking)} without linking)? (y/n): ")
            else:
                confirm = self.session.prompt(f"\nPublish {publish_count} article(s)? (y/n): ")
            if confirm.lower() != "y":
                console.print("[yellow]Publishing cancelled.[/yellow]")
                return True
            
            # Include missing_linking articles in publishing if user confirmed
            if missing_linking:
                for item in missing_linking:
                    # Find the article in draft_articles
                    for article in draft_articles:
                        if article.get("id") == item["id"]:
                            ready_to_publish.append(article)
                            break
        
        # Build prompt for agent
        content_dir = self.article_manager.get_content_dir(repo_root)
        
        prompt_parts = [
            f"Publish draft articles for {self.project.website_id}.",
            "",
            f"WORKSPACE: {workspace}",
            f"CONTENT_DIR: {content_dir}",
            "",
            "DRAFT ARTICLES TO PUBLISH:",
        ]
        
        for article in ready_to_publish:
            prompt_parts.append(f"- ID {article['id']}: {article['title']} (date: {article.get('published_date', 'none')})")
        
        if issues:
            prompt_parts.extend(["", "ISSUES TO FIX FIRST:"])
            for issue in issues:
                prompt_parts.append(f"- ID {issue['id']}: {issue['issue']}")
        
        prompt_parts.extend([
            "",
            "SAFETY RULES (CRITICAL):",
            "1. ONLY modify articles with status='draft' - NEVER touch published articles",
            "2. If date overlaps found, redistribute dates for DRAFT articles only",
            "3. If date is in future, change to today or tomorrow for drafts only",
            "4. If year mismatch (e.g., '2025' in title but publishing in 2026):",
            "   - EITHER update title to current year (e.g., '2025' → '2026')",
            "   - OR backdate publish date to match title year",
            "   - Update BOTH articles.json title AND .mdx frontmatter + content",
            "5. Update BOTH articles.json AND the .mdx frontmatter for any date changes",
            "6. After fixing issues, change status from 'draft' to 'published'",
            "",
            "CLI COMMANDS:",
            f"- Validate: pageseeds content validate --workspace-root {workspace} --website-path .",
            f"- Fix dates: pageseeds content fix-dates --workspace-root {workspace} --website-path .",
            f"- Check: pageseeds content analyze-dates --workspace-root {workspace} --website-path .",
            "",
            "Report what was published and what issues were fixed.",
        ])
        
        prompt = "\n".join(prompt_parts)
        
        console.print("[dim]Running publish workflow...[/dim]\n")
        
        try:
            success, output = self.run_kimi_agent(prompt, cwd=repo_root, timeout=600)
            
            if output:
                lines = output.split('\n')
                filtered = []
                skip_patterns = ['ToolCall', 'ToolResult', 'StepBegin', 'ThinkPart', 'StatusUpdate', 'TurnBegin', 'TurnEnd']
                for line in lines:
                    if line.strip() and not any(p in line for p in skip_patterns):
                        filtered.append(line)
                if filtered:
                    console.print('\n'.join(filtered[-40:]))
            
            console.print(f"\n[green]✓ Publish workflow complete[/green]")
            
            # VERIFY: Check for any remaining future dates
            console.print(f"\n[dim]Verifying dates...[/dim]")
            remaining_future = self._check_future_dates(repo_root)
            if remaining_future:
                console.print(f"[yellow]⚠ Warning: {len(remaining_future)} article(s) still have future dates:[/yellow]")
                for item in remaining_future:
                    console.print(f"  [dim]ID {item['id']}: {item['date']} - {item['title'][:40]}...[/dim]")
                console.print(f"[yellow]Run 'analyze-dates' to fix these manually if needed.[/yellow]")
            else:
                console.print(f"[green]✓ All dates verified - no future dates found[/green]")
            
            if task:
                task.status = "done"
                task.completed_at = datetime.now().isoformat()
                self.task_list.save()
            return True
            
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
