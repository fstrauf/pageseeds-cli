"""Verification and setup flows for Dashboard CLI."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .engine import ProjectPreflight
from .ui import console


class DashboardVerificationMixin:
    """Setup verification and repair helpers used by Dashboard."""

    def _check_article_dates(self, repo_root: Path, articles_data: dict, article_mgr) -> list:
        """Check for date mismatches between articles.json and content files.

        Args:
            repo_root: Repository root path
            articles_data: Parsed articles.json data
            article_mgr: ArticleManager instance

        Returns:
            List of date mismatch dictionaries
        """
        mismatches = []
        articles = articles_data.get("articles", [])

        for article in articles:
            article_id = article.get("id")
            json_date = article.get("published_date", "")
            url_slug = article.get("url_slug", "")

            if not url_slug or not json_date:
                continue

            # Find the content file
            content_dir = article_mgr.get_content_dir(repo_root)
            if not content_dir:
                continue

            # Try multiple filename patterns (with and without ID prefix)
            content_file = None
            patterns = [
                f"{url_slug}.mdx",
                f"{url_slug}.md",
                f"{article_id:03d}_{url_slug}.mdx",
                f"{article_id:03d}_{url_slug}.md",
                f"{article_id}_{url_slug}.mdx",
                f"{article_id}_{url_slug}.md",
            ]

            for pattern in patterns:
                candidate = content_dir / pattern
                if candidate.exists():
                    content_file = candidate
                    break

            if not content_file:
                continue

            # Extract date from frontmatter
            try:
                content = content_file.read_text()

                # Look for date in frontmatter
                date_match = re.search(r'^date:\s*"?(\d{4}-\d{2}-\d{2})"?', content, re.MULTILINE)
                if not date_match:
                    date_match = re.search(r'^publishedDate:\s*"?(\d{4}-\d{2}-\d{2})"?', content, re.MULTILINE)
                if not date_match:
                    date_match = re.search(r'^pubDate:\s*"?(\d{4}-\d{2}-\d{2})"?', content, re.MULTILINE)

                if date_match:
                    file_date = date_match.group(1)
                    # Normalize JSON date (handle timezone)
                    json_date_normalized = json_date.split('T')[0] if 'T' in json_date else json_date[:10]

                    if json_date_normalized != file_date:
                        mismatches.append({
                            "id": article_id,
                            "url_slug": url_slug,
                            "json_date": json_date_normalized,
                            "file_date": file_date,
                            "file": content_file.name,
                        })
            except Exception:
                continue

        return mismatches

    def _fix_date_mismatches(self, repo_root: Path, date_mismatches: list) -> int:
        """Fix date mismatches by updating articles.json to match content files.

        Args:
            repo_root: Repository root path
            date_mismatches: List of date mismatch dictionaries

        Returns:
            Number of dates fixed
        """
        from .utils import ArticleManager

        article_mgr = ArticleManager(self.project_manager.current.website_id)
        articles_json_path = article_mgr.get_articles_json_path(repo_root)

        if not articles_json_path or not articles_json_path.exists():
            return 0

        try:
            data = json.loads(articles_json_path.read_text())
            articles = data.get("articles", [])

            # Build lookup by ID
            article_by_id = {a.get("id"): a for a in articles if a.get("id")}

            fixed_count = 0
            for mismatch in date_mismatches:
                article_id = mismatch["id"]
                file_date = mismatch["file_date"]

                if article_id in article_by_id:
                    article = article_by_id[article_id]
                    old_date = article.get("published_date", "")
                    article["published_date"] = file_date
                    fixed_count += 1
                    console.print(f"[dim]  ID {article_id}: {old_date} → {file_date}[/dim]")

            # Save if changes were made
            if fixed_count > 0:
                articles_json_path.write_text(json.dumps(data, indent=2))

            return fixed_count

        except Exception as e:
            console.print(f"[red]Error fixing dates: {e}[/red]")
            return 0

    def _repair_templates(self, auto_dir: Path, website_id: str, missing_templates: list) -> int:
        """Create missing template files.

        Args:
            auto_dir: Automation directory path
            website_id: Website ID for the project
            missing_templates: List of (name, path) tuples for missing templates

        Returns:
            Number of templates created
        """
        from .core.project_manager import ProjectManager
        
        # Create a temporary ProjectManager just to use its template creation method
        pm = ProjectManager()
        
        created = 0
        try:
            for name, path in missing_templates:
                if name == "brandvoice.md":
                    content = self._get_brandvoice_template()
                elif name == "project_summary.md":
                    content = self._get_project_summary_template(website_id)
                elif name == "seo_content_brief.md":
                    content = self._get_seo_brief_template(website_id)
                elif name == "reddit_config.md":
                    content = self._get_reddit_config_template(website_id)
                else:
                    continue
                
                path.write_text(content)
                console.print(f"[dim]  Created: {name}[/dim]")
                created += 1
            
            # Also create orchestrator_policy.json if missing
            policy_path = auto_dir / "orchestrator_policy.json"
            if not policy_path.exists():
                policy = {"version": "1.0", "website_id": website_id, "rules": [], "schedules": []}
                policy_path.write_text(json.dumps(policy, indent=2))
                console.print(f"[dim]  Created: orchestrator_policy.json[/dim]")
                created += 1
                
        except Exception as e:
            console.print(f"[red]Error creating templates: {e}[/red]")
        
        return created

    def _get_brandvoice_template(self) -> str:
        return """# Brand Voice Guidelines

## Tone
- Professional but approachable
- Clear and concise
- Helpful and educational

## Voice Characteristics
- **Knowledgeable**: Demonstrate expertise in your domain
- **Practical**: Focus on actionable insights
- **Transparent**: Be honest about limitations and trade-offs
- **Conversational**: Write like you're talking to a colleague

## Language Style
- Use industry terminology correctly
- Avoid hype or promotional language
- Keep sentences clear and concise
- Use first person when sharing experience

## What to Avoid
- Overpromising results
- Aggressive self-promotion
- Jargon without context
- Being dismissive of alternatives
"""

    def _get_project_summary_template(self, website_id: str) -> str:
        return f"""# Project Summary: {website_id}

## Platform Overview

Brief description of what this project does and who it serves.

---

## Core Features

### Feature 1: [Name]
Description of the feature and its value proposition.

**Search Keywords:**
- "keyword 1"
- "keyword 2"

---

### Feature 2: [Name]
Description of the feature and its value proposition.

---

## Content Pillars for SEO

### Pillar 1: [Topic Area]
- Subtopic 1
- Subtopic 2

### Pillar 2: [Topic Area]
- Subtopic 1
- Subtopic 2

---

## Target Audience

- **Primary audience**: Description
- **Secondary audience**: Description

---

## Key Differentiators

1. **Differentiator 1**: Description
2. **Differentiator 2**: Description

---

## User Workflows

### Workflow 1: [Name]
1. Step 1
2. Step 2
3. Step 3

---

## Data & Integrations

### Data Sources
- Source 1
- Source 2

---

## Target Communities (for Reddit)
- r/example1
- r/example2

---

## TODO: Fill in this template

Replace the placeholder sections above with actual project details.
This file is used by SEO workflows and content generation agents.
"""

    def _get_seo_brief_template(self, website_id: str) -> str:
        return f"""# {website_id} - SEO Content Brief

## Project Overview

**Site:** {website_id}  
**Domain:** [your domain focus]  
**Current Coverage:** [X published articles covering ...]

## Content Clusters & Status

### Cluster 1: [Topic Area] (STATUS)
**Pillar Content:** [Main topic description]
- Subtopic 1 ✅
- Subtopic 2 ✅
- Subtopic 3 🎯 (planned)

### Cluster 2: [Topic Area] (STATUS)
**Pillar Content:** [Main topic description]
- Subtopic 1 ✅
- Subtopic 2 🎯 (planned)

## Target Keywords

### High Priority
- [keyword 1]
- [keyword 2]

### Medium Priority
- [keyword 3]
- [keyword 4]

## Content Gaps

- Gap 1: Description
- Gap 2: Description

## TODO: Fill in this template

Update this brief as your content strategy evolves.
"""

    def _get_reddit_config_template(self, website_id: str) -> str:
        return f"""# Reddit Config: {website_id}

> **Generic reply standards:** See `_reply_guardrails.md` in the reddit/ directory

## Product Information
- **Product Name**: [Your Product Name]
- **Description**: [Brief description]

## Mention Stance
**RECOMMENDED** - Include product name when it adds value naturally

## Trigger Topics
- Topic 1
- Topic 2
- Topic 3

## Target Subreddits
- r/example1
- r/example2
- r/example3

## Query Keywords
- "keyword 1"
- "keyword 2"

## TODO: Fill in this template

Define your product details and target communities here.
"""

    def _run_setup_gitignore(self) -> bool:
        """Update project .gitignore to exclude automation data.

        Returns:
            True if successful, False otherwise.
        """
        if not self.project_manager.current:
            return False

        preflight = ProjectPreflight(
            repo_root=Path(self.project_manager.current.repo_root),
            website_id=self.project_manager.current.website_id,
            check_cli=False,
            check_reddit_auth=False,
        )
        success, message = preflight.fix_gitignore_exclusions()
        if success:
            console.print("[green]✓ .gitignore updated successfully[/green]")
            console.print(f"[dim]{message}[/dim]")
            return True

        console.print("[red]✗ Failed to update .gitignore[/red]")
        console.print(f"[dim]{message}[/dim]")
        return False

    def verify_setup(self):
        """Verify project setup for content tasks."""
        p = self.project_manager.current
        if not p:
            console.print("[red]No project selected[/red]")
            self.session.prompt("\nPress Enter...")
            return

        console.print(f"\n[bold]Setup Verification: {p.name}[/bold]\n")

        checks = []
        # Use the project's repo_root from configuration
        repo_root = Path(p.repo_root)
        automation_dir = repo_root / ".github" / "automation"

        # Initialize ArticleManager early
        from .utils import ArticleManager

        article_mgr = ArticleManager(p.website_id)

        # Initialize mismatch trackers (always defined for repair prompts)
        slug_mismatches: list = []
        date_mismatches: list = []

        # Check automation directory exists
        if automation_dir.exists():
            checks.append(("✓", "green", f"Automation directory exists: {automation_dir}"))
        else:
            checks.append(("✗", "red", f"Automation directory NOT FOUND: {automation_dir}"))

        # Check .gitignore excludes automation data
        gitignore_path = repo_root / ".gitignore"
        gitignore_needs_fix = False
        content_dir_needs_setup = False
        if gitignore_path.exists():
            try:
                gitignore_content = gitignore_path.read_text()
                if ".github/automation/" in gitignore_content:
                    checks.append(("✓", "green", ".gitignore excludes automation data"))
                else:
                    checks.append(("⚠", "yellow", ".gitignore does NOT exclude automation data"))
                    checks.append((" ", "dim", "  Type 'fix' below to auto-fix"))
                    gitignore_needs_fix = True
            except IOError:
                checks.append(("?", "dim", "Could not read .gitignore"))
        else:
            checks.append(("?", "dim", "No .gitignore found (may not be a git repo)"))

        # Check articles.json
        articles_json = automation_dir / "articles.json"
        if articles_json.exists():
            try:
                data = json.loads(articles_json.read_text())
                article_count = len(data.get("articles", []))
                max_id = max((a.get("id", 0) for a in data.get("articles", [])), default=0)
                checks.append(("✓", "green", f"articles.json exists ({article_count} articles, next ID: {max_id + 1})"))

                # Check articles.json alignment with post files
                mismatches = article_mgr.check_slug_alignment(repo_root)

                if mismatches:
                    checks.append(("⚠", "yellow", f"articles.json has {len(mismatches)} slug/filename mismatches:"))
                    for m in mismatches[:5]:
                        checks.append((" ", "yellow", f"  ID {m['id']}: url_slug='{m['url_slug']}' vs file='{m['filename']}'"))
                    if len(mismatches) > 5:
                        checks.append((" ", "yellow", f"  ... and {len(mismatches) - 5} more"))
                    checks.append((" ", "dim", "  This causes 0% GSC article mapping. Fix url_slug to match filename."))

                    # Store mismatches for potential auto-repair
                    slug_mismatches = mismatches
                else:
                    checks.append(("✓", "green", "articles.json slugs align with filenames"))

                # Check date alignment between articles.json and content files
                date_mismatches = self._check_article_dates(repo_root, data, article_mgr)
                if date_mismatches:
                    checks.append(("⚠", "yellow", f"Date mismatches found ({len(date_mismatches)} articles):"))
                    for dm in date_mismatches[:5]:
                        checks.append((" ", "yellow", f"  ID {dm['id']}: articles.json={dm['json_date']} vs file={dm['file_date']} ({dm['file']})"))
                    if len(date_mismatches) > 5:
                        checks.append((" ", "yellow", f"  ... and {len(date_mismatches) - 5} more"))
                    checks.append((" ", "dim", "  Content file dates will be used as source of truth"))
                else:
                    checks.append(("✓", "green", "Article dates align between articles.json and content files"))

            except Exception:
                checks.append(("✗", "red", "articles.json exists but is invalid"))
        else:
            checks.append(("✗", "red", f"articles.json NOT FOUND: {articles_json}"))

        # Check manifest.json
        manifest_json = automation_dir / "manifest.json"
        if manifest_json.exists():
            try:
                data = json.loads(manifest_json.read_text())
                url = data.get("url", "N/A")
                checks.append(("✓", "green", f"manifest.json exists (URL: {url})"))
            except Exception:
                checks.append(("⚠", "yellow", "manifest.json exists but is invalid"))
        else:
            checks.append(("⚠", "yellow", f"manifest.json NOT FOUND (optional but recommended)"))

        # Check content directory using ArticleManager
        content_dir = article_mgr.get_content_dir(repo_root)

        # Check if using configured content_dir
        configured_content_dir = None
        if p.content_dir:
            configured_content_dir = Path(p.content_dir).expanduser().resolve()

        if content_dir and content_dir.exists():
            # Show if it's a symlink
            if content_dir.is_symlink():
                target = content_dir.readlink()
                checks.append(("✓", "green", f"Content directory exists: {content_dir} -> {target}"))
            else:
                checks.append(("✓", "green", f"Content directory exists: {content_dir}"))

            # Show if this is from project config
            if configured_content_dir and content_dir.resolve() == configured_content_dir.resolve():
                checks.append(("ℹ", "blue", "  (Using configured path from project settings)"))

            # Count files
            mdx_files = list(content_dir.glob("*.mdx"))
            md_files = list(content_dir.glob("*.md"))
            total = len(mdx_files) + len(md_files)
            checks.append(("ℹ", "blue", f"  Found {total} content files ({len(mdx_files)} .mdx, {len(md_files)} .md)"))

            # Check for mismatch between articles.json and content files
            articles_json_path = article_mgr.get_articles_json_path(repo_root)
            if articles_json_path:
                try:
                    data = json.loads(articles_json_path.read_text())
                    articles_count = len(data.get("articles", []))
                    if articles_count != total:
                        checks.append(("⚠", "yellow", f"  Mismatch: articles.json has {articles_count} entries, but content dir has {total} files"))
                except Exception:
                    pass
        else:
            checks.append(("⚠", "yellow", "Content directory not found"))
            if configured_content_dir:
                checks.append((" ", "dim", f"  Configured path not found: {configured_content_dir}"))
            checks.append((" ", "dim", "  Looked for: webapp/content/blog/, content/blog/, content/, src/content/, src/blog/posts/, posts/, blog/"))
            content_dir_needs_setup = True

        # Check task health - what will actually run?
        checks.append(("", "white", ""))  # Blank line separator
        checks.append(("━", "dim", " Task Health Check "))

        task_list_path = automation_dir / "task_list.json"
        policy_path = automation_dir / "orchestrator_policy.json"

        if task_list_path.exists() and policy_path.exists():
            try:
                task_data = json.loads(task_list_path.read_text())
                policy_data = json.loads(policy_path.read_text())

                tasks = task_data.get("tasks", [])
                allowed_modes = set(policy_data.get("allow_modes", []))
                blocked_types = set(policy_data.get("blocked_task_types", []))

                # Import autonomy map
                from .config import AUTONOMY_MODE_MAP

                pending = [t for t in tasks if t.get("status") in ("todo", "ready")]
                blocked = []

                for task in pending:
                    task_type = task.get("type", "unknown")
                    autonomy = AUTONOMY_MODE_MAP.get(task_type, "manual")

                    reasons = []
                    if autonomy not in allowed_modes:
                        reasons.append(f"mode '{autonomy}' blocked by policy")
                    if task_type in blocked_types:
                        reasons.append("task type blocked")

                    if reasons:
                        blocked.append({
                            "id": task.get("id", "?"),
                            "type": task_type,
                            "reasons": reasons,
                        })

                if pending:
                    checks.append(("ℹ", "blue", f"{len(pending)} task(s) waiting to run"))

                    if blocked:
                        checks.append(("⚠", "yellow", f"{len(blocked)} task(s) WILL BE BLOCKED by policy:"))
                        for b in blocked[:5]:
                            checks.append((" ", "yellow", f"  {b['id']}: {b['type']} - {b['reasons'][0]}"))
                        if len(blocked) > 5:
                            checks.append((" ", "yellow", f"  ... and {len(blocked) - 5} more"))
                        checks.append((" ", "dim", "  Update orchestrator_policy.json to allow these tasks"))
                    else:
                        checks.append(("✓", "green", "All pending tasks are eligible to run"))
                else:
                    checks.append(("✓", "green", "No pending tasks"))

            except Exception as e:
                checks.append(("?", "dim", f"Could not check task health: {e}"))
        else:
            if not task_list_path.exists():
                checks.append(("?", "dim", "No task_list.json found"))
            if not policy_path.exists():
                checks.append(("?", "dim", "No orchestrator_policy.json found"))

        # Check for template/config files (new projects have these, old ones may not)
        missing_templates = []
        template_files = [
            (automation_dir / "brandvoice.md", "brandvoice.md"),
            (automation_dir / "project_summary.md", "project_summary.md"),
            (automation_dir / "seo_content_brief.md", "seo_content_brief.md"),
            (automation_dir / "reddit_config.md", "reddit_config.md"),
        ]
        for path, name in template_files:
            if not path.exists():
                missing_templates.append((name, path))
        
        if missing_templates:
            checks.append(("", "white", ""))  # Blank line separator
            checks.append(("━", "dim", " Template Files "))
            for name, path in missing_templates:
                checks.append(("⚠", "yellow", f"Missing: {name}"))
            checks.append((" ", "dim", "  Type 'repair' to create missing templates"))

        # Display results
        for icon, color, message in checks:
            console.print(f"[{color}]{icon} {message}[/{color}]")

        # Summary
        errors = sum(1 for icon, _, _ in checks if icon == "✗")
        warnings = sum(1 for icon, _, _ in checks if icon == "⚠")
        blocked_tasks = sum(1 for icon, _, msg in checks if icon == "⚠" and "WILL BE BLOCKED" in msg)

        if errors == 0 and warnings == 0:
            console.print("\n[green]✓ All checks passed! Ready to create content.[/green]")
        elif errors == 0 and blocked_tasks > 0:
            console.print(f"\n[yellow]⚠ {blocked_tasks} task(s) blocked by policy. Update orchestrator_policy.json to run them.[/yellow]")
        elif errors == 0:
            console.print(f"\n[yellow]⚠ {warnings} warning(s) found.[/yellow]")
        else:
            console.print(f"\n[red]✗ {errors} error(s) found.[/red]")

        # Offer gitignore fix
        if gitignore_needs_fix:
            console.print("\n[cyan]Auto-fix available:[/cyan] Add .github/automation/ to .gitignore")
            confirm = self.session.prompt("Type 'fix' to update .gitignore, or press Enter to skip: ")
            if confirm.lower() == "fix":
                success = self._run_setup_gitignore()
                if success:
                    console.print("[green]✓ .gitignore updated successfully[/green]")
                else:
                    console.print("[red]✗ Failed to update .gitignore[/red]")

        # Offer auto-repair for slug mismatches
        if slug_mismatches:
            console.print(f"\n[cyan]Auto-repair available:[/cyan] Fix {len(slug_mismatches)} slug mismatch(es)?")
            confirm = self.session.prompt("Type 'fix' to repair, or press Enter to skip: ")
            if confirm.lower() == "fix":
                result = article_mgr.repair_slugs(repo_root, dry_run=False)
                if result.get("error"):
                    console.print(f"[red]✗ {result['error']}[/red]")
                else:
                    console.print(f"[green]✓ Fixed {len(result['fixed'])} slug(s)[/green]")
                    console.print(f"[dim]  {result['unchanged']} article(s) unchanged[/dim]")

        # Offer auto-repair for date mismatches
        if date_mismatches:
            console.print(f"\n[cyan]Auto-repair available:[/cyan] Sync {len(date_mismatches)} date mismatch(es) from content files?")
            confirm = self.session.prompt("Type 'fix' to update articles.json dates, or press Enter to skip: ")
            if confirm.lower() == "fix":
                fixed_count = self._fix_date_mismatches(repo_root, date_mismatches)
                if fixed_count > 0:
                    console.print(f"[green]✓ Fixed {fixed_count} date mismatch(es)[/green]")
                    console.print("[dim]  articles.json dates now match content file frontmatter[/dim]")
                else:
                    console.print("[yellow]⚠ No dates were fixed[/yellow]")

        # Offer content directory sync
        content_dir = article_mgr.get_content_dir(repo_root)
        if content_dir:
            content_files = list(content_dir.glob("*.mdx")) + list(content_dir.glob("*.md"))
            articles_count = len(data.get("articles", [])) if 'data' in locals() else 0

            if len(content_files) != articles_count:
                console.print(f"\n[cyan]Sync available:[/cyan] Content dir has {len(content_files)} files, articles.json has {articles_count} entries")
                confirm = self.session.prompt("Type 'sync' to synchronize, or press Enter to skip: ")
                if confirm.lower() == "sync":
                    result = article_mgr.sync_with_content_dir(repo_root, dry_run=False)
                    if result.get("error"):
                        console.print(f"[red]✗ {result['error']}[/red]")
                    else:
                        if result.get("added"):
                            console.print(f"[green]✓ Added {len(result['added'])} article(s)[/green]")
                        if result.get("removed"):
                            console.print(f"[yellow]✓ Removed {len(result['removed'])} orphaned entry(s)[/yellow]")
                        if result.get("duplicate_ids"):
                            console.print(f"[red]⚠ {len(result['duplicate_ids'])} duplicate ID issue(s) need manual resolution[/red]")
                        if result.get("next_id_updated"):
                            console.print("[dim]✓ Updated nextArticleId[/dim]")

        # Offer content directory setup if not found
        if content_dir_needs_setup:
            console.print("\n[cyan]Setup required:[/cyan] Content directory not found")
            console.print("[dim]Content tasks need a directory with markdown files.[/dim]")

            user_path = self.session.prompt("\nEnter content directory path (or press Enter to skip): ").strip()

            if user_path:
                user_path_expanded = Path(user_path).expanduser().resolve()

                if not user_path_expanded.exists():
                    console.print(f"[red]✗ Path does not exist: {user_path_expanded}[/red]")
                elif not user_path_expanded.is_dir():
                    console.print(f"[red]✗ Not a directory: {user_path_expanded}[/red]")
                else:
                    # Check for markdown files
                    md_files = list(user_path_expanded.glob("*.md*"))

                    if not md_files:
                        console.print(f"[yellow]⚠ Warning: No markdown files found in {user_path_expanded}[/yellow]")
                        confirm = self.session.prompt("Save anyway? (y/n): ").lower()
                    else:
                        console.print(f"[green]✓ Found {len(md_files)} markdown file(s)[/green]")
                        confirm = "y"

                    if confirm == "y":
                        # Save to project config
                        success, msg = self.project_manager.edit_project(
                            p.website_id,
                            content_dir=str(user_path_expanded),
                        )
                        if success:
                            console.print(f"[green]✓ Content directory saved: {user_path_expanded}[/green]")
                            console.print("[dim]  Project config updated.[/dim]")
                        else:
                            console.print(f"[red]✗ Failed to save: {msg}[/red]")

        # Offer to repair missing templates
        if missing_templates:
            console.print(f"\n[cyan]Template repair available:[/cyan] Create {len(missing_templates)} missing template file(s)?")
            confirm = self.session.prompt("Type 'repair' to create templates, or press Enter to skip: ")
            if confirm.lower() == "repair":
                created = self._repair_templates(automation_dir, p.website_id, missing_templates)
                if created > 0:
                    console.print(f"[green]✓ Created {created} template file(s)[/green]")
                    console.print("[dim]  Edit these files to customize for your project.[/dim]")
                else:
                    console.print("[yellow]⚠ No templates were created[/yellow]")

        self.session.prompt("\nPress Enter...")
