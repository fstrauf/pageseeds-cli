"""
Content creation and optimization tasks
"""
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console

from ..config import AUTOMATION_ROOT
from ..models import Task
from ..utils import ArticleManager
from .base import TaskRunner

console = Console()


class ContentRunner(TaskRunner):
    """Runs content creation and optimization tasks."""
    
    def __init__(self, task_list, project, session):
        super().__init__(task_list, project, session)
        self.article_manager = ArticleManager(project.website_id)
    
    def _run_with_progress(self, func, *args, **kwargs):
        """Run a function with a progress spinner using Rich's status."""
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
        
        # Start worker thread
        thread = threading.Thread(target=worker)
        thread.start()
        
        # Show Rich status spinner while waiting
        start_time = time.time()
        with Status("[dim]Writing...[/dim]", console=console, spinner="dots") as status:
            while not done.wait(timeout=0.1):
                elapsed = time.time() - start_time
                status.update(f"[dim]Writing... ({elapsed:.0f}s elapsed)[/dim]")
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    def run(self, task: Task) -> bool:
        """Execute a content creation or optimization task."""
        is_optimization = task.type == "optimize_article"
        
        # For new content, validate articles.json alignment first
        if not is_optimization:
            is_valid, _ = self.validate_articles_json()
            if not is_valid:
                console.print(f"\n[yellow]Content creation aborted due to articles.json misalignment.[/yellow]")
                console.print(f"[dim]Fix the mismatches first to ensure proper article ID sequencing.[/dim]")
                return False
        
        console.print(f"\n[bold]Content Task: {task.title}[/bold]")
        if is_optimization:
            console.print("[green]This is a content optimization task - improving existing content.[/green]\n")
        else:
            console.print("[green]This is a content creation task - writing directly.[/green]\n")
        
        # Phase 1: Setup
        console.print("[bold cyan]Phase 1: Setup[/bold cyan]")
        
        # Use project's repo_root to find content directory
        repo_root = Path(self.project.repo_root)
        articles_dir = self.article_manager.get_content_dir(repo_root)
        if not articles_dir:
            console.print("[red]✗ Content directory not found[/red]")
            console.print(f"[dim]Looked in: {repo_root}/content/, src/content/, src/blog/posts/, etc.[/dim]")
            return False
        
        if not articles_dir.exists():
            console.print(f"[red]✗ Content directory does not exist: {articles_dir}[/red]")
            return False
        
        console.print(f"[dim]  Content directory: {articles_dir}[/dim]")
        
        # Get target keyword from task category
        target_keyword = ""
        if task.category and task.category.startswith("content:"):
            target_keyword = task.category.replace("content:", "")
        
        # Extract article topic from title
        article_topic = task.title
        if ":" in article_topic:
            article_topic = article_topic.split(":", 1)[1].strip()
        
        if is_optimization:
            return self._run_optimization(task, articles_dir, article_topic, target_keyword, repo_root)
        else:
            return self._run_creation(task, articles_dir, article_topic, target_keyword, repo_root)
    
    def _run_optimization(self, task: Task, articles_dir: Path, article_topic: str, 
                          target_keyword: str, repo_root: Path) -> bool:
        """Run article optimization workflow."""
        # Try to find by task.url first (for performance optimization tasks)
        existing_article = None
        if task.url:
            # Extract slug from URL like https://example.com/blog-post-slug
            url_slug = task.url.rstrip('/').split('/')[-1] if '/' in task.url else task.url
            # Try finding by URL slug
            existing_article = self.article_manager.find_existing(url_slug, repo_root)
        
        # Fall back to searching by article_topic (task title)
        if not existing_article:
            existing_article = self.article_manager.find_existing(article_topic, repo_root)
        
        if not existing_article:
            console.print(f"[yellow]⚠ Could not find existing article for: {article_topic}[/yellow]")
            if task.url:
                console.print(f"[dim]  URL: {task.url}[/dim]")
            console.print("[dim]  Falling back to creating new article...[/dim]\n")
            return self._run_creation(task, articles_dir, article_topic, target_keyword, repo_root)
        
        # Found existing article
        existing_id = existing_article.get("id")
        existing_title = existing_article.get("title")
        existing_file = existing_article.get("file", "")
        existing_date = existing_article.get("published_date", "")
        
        # Convert relative file path to absolute
        if existing_file.startswith("./content/"):
            filename = existing_file.replace("./content/", "")
        else:
            filename = Path(existing_file).name
        
        output_file = articles_dir / filename
        
        console.print(f"[green]✓ Found existing article to optimize:[/green]")
        console.print(f"[dim]  ID: {existing_id}[/dim]")
        console.print(f"[dim]  Title: {existing_title}[/dim]")
        console.print(f"[dim]  File: {filename}[/dim]")
        console.print(f"[dim]  Published: {existing_date}[/dim]")
        
        # Read existing content
        existing_content = ""
        if output_file.exists():
            try:
                existing_content = output_file.read_text()[:5000]
            except Exception as e:
                console.print(f"[dim]  Could not read existing content: {e}[/dim]")
        
        if self.auto_confirm_enabled():
            console.print("[dim]Auto-confirm enabled: proceeding with article optimization.[/dim]")
        else:
            # Confirm with user
            confirm = self.session.prompt("\nProceed with article optimization? (y/n): ")
            if confirm.lower() != "y":
                console.print("[yellow]Cancelled.[/yellow]")
                return False
        
        # Phase 2: Optimization
        console.print("\n[bold cyan]Phase 2: Optimizing Article (Agent)[/bold cyan]")
        
        context = self._get_research_context(task)
        
        prompt = f"""Optimize and improve an existing article.

PROJECT: {self.project.website_id}
TOPIC: {article_topic}
OUTPUT_FILE: {output_file}
PRESERVE_DATE: {existing_date}
{f'TARGET_KEYWORD: {target_keyword}' if target_keyword else ''}
{f'RESEARCH_CONTEXT: {context}' if context else ''}

EXISTING CONTENT (current article):
```
{existing_content}
```

INSTRUCTIONS:
1. READ the existing content above carefully
2. IMPROVE the article while keeping its core message
3. USE WriteFile tool to save to OUTPUT_FILE (overwrite existing)
4. PRESERVE the original publish date in frontmatter (use PRESERVE_DATE)
5. ENHANCE with better structure, more detail, improved SEO
6. KEEP the same URL/title concept but improve execution

OPTIMIZATION GUIDELINES:
- Add more depth and detail where thin
- Improve headings and structure
- Enhance introduction and conclusion
- Add internal link placeholders like [related article](TODO: link)
- Fix any SEO issues
- Maintain the same writing style/tone
- Do NOT change the fundamental topic

REQUIREMENTS:
- Use proper markdown (no HTML)
- Preserve the original publish date exactly
- Improve word count and depth
- Write naturally - don't keyword stuff
- Use the exact OUTPUT_FILE path when saving

Write the optimized article now."""
        
        return self._execute_write(task, prompt, output_file, existing_id, existing_date, 
                                   is_optimization=True, repo_root=repo_root)
    
    def _run_creation(self, task: Task, articles_dir: Path, article_topic: str, 
                      target_keyword: str, repo_root: Path) -> bool:
        """Run new article creation workflow."""
        # Check date gap - maintain 2-day spacing from ALL articles (published + drafts)
        suggested_date = self.article_manager.get_next_available_date(repo_root)
        latest_date, _ = self.article_manager.get_latest_date(repo_root, include_drafts=True)
        
        if latest_date:
            days_since_latest = (datetime.now() - latest_date).days
            console.print(f"[dim]  Latest article: {latest_date.strftime('%Y-%m-%d')} ({days_since_latest} days ago)[/dim]")
            console.print(f"[dim]  Suggested publish date: {suggested_date.strftime('%Y-%m-%d')}[/dim]")
            
            # Warn if building up a backlog (suggested date is far in future)
            days_ahead = (suggested_date.date() - datetime.now().date()).days
            if days_ahead > 7:
                console.print(f"[yellow]  ⚠ Note: You have content scheduled through {latest_date.strftime('%Y-%m-%d')}[/yellow]")
        else:
            suggested_date = datetime.now()
        
        # Get next ID and build filename
        next_id = self.article_manager.get_next_id(repo_root)
        console.print(f"[dim]  Next article ID: {next_id}[/dim]")
        
        filename = self.article_manager.build_filename(next_id, article_topic)
        output_file = articles_dir / filename
        
        publish_date_str = suggested_date.strftime("%Y-%m-%d")
        
        console.print(f"[dim]  Filename: {filename}[/dim]")
        console.print(f"[dim]  Publish date: {publish_date_str}[/dim]")
        
        # PRE-FLIGHT VALIDATION - catch issues before creating anything
        console.print("\n[bold cyan]Phase 1b: Pre-flight Validation[/bold cyan]")
        is_valid, error_msg = self.article_manager.validate_new_article(
            article_topic, publish_date_str, repo_root
        )
        
        if not is_valid:
            console.print(f"\n[bold red]✗ VALIDATION FAILED[/bold red]")
            console.print(f"[red]Cannot create article:[/red]")
            console.print(f"[red]  {error_msg}[/red]")
            console.print(f"\n[yellow]Fix the issue before proceeding.[/yellow]")
            return False
        
        console.print("[green]✓ All validation checks passed[/green]")
        
        if self.auto_confirm_enabled():
            console.print("[dim]Auto-confirm enabled: proceeding with article creation.[/dim]")
        else:
            # Confirm with user
            confirm = self.session.prompt("\nProceed with article creation? (y/n): ")
            if confirm.lower() != "y":
                console.print("[yellow]Cancelled.[/yellow]")
                return False
        
        # Phase 2: Writing
        console.print("\n[bold cyan]Phase 2: Writing Article (Agent)[/bold cyan]")
        
        context = self._get_research_context(task)
        
        prompt = f"""Write a complete, publish-ready article.

PROJECT: {self.project.website_id}
TOPIC: {article_topic}
OUTPUT_FILE: {output_file}
PUBLISH_DATE: {publish_date_str}
{f'TARGET_KEYWORD: {target_keyword}' if target_keyword else ''}
{f'RESEARCH_CONTEXT: {context}' if context else ''}

INSTRUCTIONS:
1. Write a comprehensive, well-researched article
2. Use WriteFile tool to save directly to OUTPUT_FILE
3. Include frontmatter with title, description, date (use PUBLISH_DATE)
4. Write 800-1500 words with proper markdown formatting
5. Include H2 and H3 headings for structure
6. Make it SEO-friendly but natural-reading

ARTICLE STRUCTURE:
```yaml
---
title: "Article Title Here"
description: "Brief meta description for SEO (150-160 chars)"
date: "{publish_date_str}"
tags: ["tag1", "tag2"]
---

# Article Title (H1)

Introduction paragraph that hooks the reader...

## Section 1 (H2)

Content with **bold** and *italic* text.

### Subsection (H3)

More detailed content.

## Section 2 (H2)

- Bullet point 1
- Bullet point 2

## Conclusion

Wrap up with key takeaways.
```

REQUIREMENTS:
- Use proper markdown (no HTML)
- Include internal link placeholders like [related article](TODO: link)
- Frontmatter must use PUBLISH_DATE exactly as provided
- Write naturally - don't keyword stuff
- Use the exact OUTPUT_FILE path when saving

Write the complete article now."""
        
        return self._execute_write(task, prompt, output_file, next_id, publish_date_str,
                                   target_keyword=target_keyword, is_optimization=False,
                                   repo_root=repo_root)
    
    def _get_research_context(self, task: Task) -> str:
        """Extract research context if available."""
        if not task.input_artifact:
            return ""
        
        try:
            context_path = self.task_list.automation_dir / task.input_artifact
            if context_path.exists():
                with open(context_path) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return json.dumps(data, indent=2)[:3000]
        except:
            pass
        return ""
    
    def _execute_write(self, task: Task, prompt: str, output_file: Path, article_id: int,
                       publish_date: str, target_keyword: str = "", is_optimization: bool = False,
                       repo_root: Path | None = None) -> bool:
        """Execute the writing phase via agent."""
        console.print(f"[dim]Writing article to: {output_file}[/dim]")
        console.print("[dim]This may take 2-5 minutes. Press Ctrl+C to cancel.[/dim]\n")
        
        try:
            start_time = time.time()
            success, output = self._run_with_progress(
                self.run_kimi_agent, prompt, timeout=300
            )
            
            # Check if file was created
            if not (output_file.exists() and output_file.stat().st_mtime > start_time):
                # Debug: Show why file wasn't created
                console.print("[red]✗ Article not created[/red]")
                if not output_file.exists():
                    console.print(f"[dim]  File does not exist: {output_file}[/dim]")
                else:
                    mtime = output_file.stat().st_mtime
                    console.print(f"[dim]  File exists but mtime ({mtime}) <= start_time ({start_time})[/dim]")
                if not success:
                    console.print(f"[yellow]  Agent failed: {output[:500]}[/yellow]")
                return False
            
            # SUCCESS PATH - File was created
            content = output_file.read_text()
            word_count = len(content.split())
            
            console.print(f"[green]✓ Article written: {output_file.name}[/green]")
            console.print(f"[dim]  Words: {word_count}[/dim]")
            
            # Show preview
            console.print("\n[dim]Preview:[/dim]")
            lines = content.split('\n')
            for line in lines[:15]:
                if line.strip():
                    console.print(f"  {line[:80]}")
            if len(lines) > 15:
                console.print("  ...")
            
            # Phase 3: Finalize
            console.print(f"\n[bold cyan]Phase 3: Finalizing[/bold cyan]")
            
            if is_optimization:
                repo_root = Path(self.project.repo_root)
                self.article_manager.update_word_count(article_id, word_count, repo_root)
                console.print(f"\n[green]✓ Article {article_id} optimized![/green]")
                console.print(f"[dim]  Date preserved: {publish_date}[/dim]")
            else:
                filename = output_file.name
                title = task.title
                if ":" in title:
                    title = title.split(":", 1)[1].strip()
                
                repo_root = Path(self.project.repo_root)
                self.article_manager.add_article(
                    article_id=article_id,
                    title=title,
                    filename=filename,
                    publish_date=publish_date,
                    word_count=word_count,
                    target_keyword=target_keyword,
                    repo_root=repo_root
                )
                
                console.print(f"\n[green]✓ Article {article_id} created![/green]")
                
                # Create follow-up linking task
                self._create_linking_task(task, title, article_id)
            
            task.status = "done"
            task.completed_at = datetime.now().isoformat()
            self.task_list.save()
            console.print(f"[dim]Task completed[/dim]")
            return True
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            return False
    
    def _create_linking_task(self, parent_task: Task, article_title: str, article_id: int):
        """Create a follow-up task for clustering and linking."""
        try:
            linking_task = self.task_list.create_task(
                task_type="cluster_and_link",
                title=f"Cluster and link article: {article_title}",
                phase="implementation",
                priority="medium",
                depends_on=parent_task.id,
                parent_task=parent_task.id,
                category="content",
                input_artifact=parent_task.input_artifact
            )
            
            linking_task.category = f"linking:article_id={article_id}"
            self.task_list.save()
            
            console.print(f"\n[dim]Created follow-up task: {linking_task.title}[/dim]")
            console.print(f"[dim]  ID: {linking_task.id}[/dim]")
            
        except Exception as e:
            console.print(f"[yellow]⚠ Could not create linking task: {e}[/yellow]")
    
    def create_multiple_articles(self, count: int, repo_root: Path) -> list[dict]:
        """
        Simplified batch article creation.
        
        Creates multiple articles in sequence with automatic ID/date assignment.
        No complex task workflow - just prompt for titles and create.
        
        Args:
            count: Number of articles to create (1-4)
            repo_root: Path to repository root
            
        Returns:
            List of created article metadata dicts
        """
        from datetime import datetime, timedelta
        
        created_articles = []
        content_dir = self.article_manager.get_content_dir(repo_root)
        
        if not content_dir:
            console.print("[red]✗ Content directory not found[/red]")
            return created_articles
        
        console.print(f"\n[bold cyan]Creating {count} Article(s)[/bold cyan]")
        console.print("[dim]Each article will get the next available ID and date.[/dim]\n")
        
        for i in range(count):
            console.print(f"\n[bold]Article {i+1} of {count}[/bold]")
            console.print("-" * 50)
            
            # Get next available date and ID
            next_date = self.article_manager.get_next_available_date(repo_root)
            next_id = self.article_manager.get_next_id(repo_root)
            
            console.print(f"[dim]Next ID: {next_id}[/dim]")
            console.print(f"[dim]Next date: {next_date.strftime('%Y-%m-%d')}[/dim]")
            
            # Prompt for title
            title = self.session.prompt("Article title: ").strip()
            if not title:
                console.print("[yellow]Skipping (no title provided)[/yellow]")
                continue
            
            # Build filename
            filename = self.article_manager.build_filename(next_id, title)
            console.print(f"[dim]Filename: {filename}[/dim]")
            
            # Pre-flight validation
            date_str = next_date.strftime("%Y-%m-%d")
            is_valid, error_msg = self.article_manager.validate_new_article(
                title, date_str, repo_root
            )
            
            if not is_valid:
                console.print(f"[red]✗ Validation failed: {error_msg}[/red]")
                console.print("[yellow]Skipping this article.[/yellow]")
                continue
            
            # Confirm
            confirm = self.session.prompt(f"Create article {next_id}? (y/n): ")
            if confirm.lower() != "y":
                console.print("[yellow]Cancelled.[/yellow]")
                continue
            
            # Write article via agent
            output_file = content_dir / filename
            
            console.print(f"\n[bold cyan]Writing Article {next_id}...[/bold cyan]")
            
            prompt = f"""Write a complete, publish-ready article.

PROJECT: {self.project.website_id}
TOPIC: {title}
OUTPUT_FILE: {output_file}
PUBLISH_DATE: {date_str}

INSTRUCTIONS:
1. Write a comprehensive article (800-1500 words)
2. Use WriteFile tool to save to OUTPUT_FILE
3. Include frontmatter with title, description, date (use PUBLISH_DATE)
4. Include H2 and H3 headings
5. Make it SEO-friendly

ARTICLE STRUCTURE:
```yaml
---
title: "{title}"
description: "Brief meta description for SEO (150-160 chars)"
date: "{date_str}"
tags: ["tag1", "tag2"]
---

# {title}

Introduction paragraph...

## Section 1

Content...

## Conclusion

Wrap up with key takeaways.
```

Write the article now."""

            try:
                start_time = datetime.now().timestamp()
                success, output = self._run_with_progress(
                    self.run_kimi_agent, prompt, timeout=300
                )
                
                # Check if file was created
                if not (output_file.exists() and output_file.stat().st_mtime > start_time):
                    console.print(f"[red]✗ Article {next_id} not created (file not found)[/red]")
                    continue
                
                # Read content and get word count
                content = output_file.read_text()
                word_count = len(content.split())
                
                # Add to articles.json
                self.article_manager.add_article(
                    article_id=next_id,
                    title=title,
                    filename=filename,
                    publish_date=date_str,
                    word_count=word_count,
                    target_keyword="",
                    repo_root=repo_root
                )
                
                console.print(f"[green]✓ Article {next_id} created: {word_count} words[/green]")
                
                created_articles.append({
                    "id": next_id,
                    "title": title,
                    "filename": filename,
                    "date": date_str,
                    "word_count": word_count
                })
                
                # Mark any matching "Write article" task as done
                self._mark_write_task_done(title)
                
                # Small delay between articles
                if i < count - 1:
                    console.print("[dim]Moving to next article...[/dim]")
                    
            except Exception as e:
                console.print(f"[red]✗ Error creating article {next_id}: {e}[/red]")
                continue
        
        # Summary
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"Created {len(created_articles)} of {count} articles:")
        for article in created_articles:
            console.print(f"  [green]✓ ID {article['id']}: {article['title'][:40]}...[/green]")
        
        # Offer to create linking tasks for the new articles
        if created_articles:
            console.print(f"\n[cyan]Linking:[/cyan] Create internal linking tasks for the new articles?")
            console.print("[dim]This will create tasks to add links between articles.[/dim]")
            linking_confirm = self.session.prompt("Create linking tasks? (y/n): ")
            
            if linking_confirm.lower() == "y":
                for article in created_articles:
                    self._create_linking_task_simple(article["title"], article["id"])
                console.print(f"[green]✓ Created {len(created_articles)} linking task(s)[/green]")
        
        return created_articles
    
    def _create_linking_task_simple(self, article_title: str, article_id: int):
        """Create a simple linking task for a newly created article."""
        try:
            if self.task_list:
                linking_task = self.task_list.create_task(
                    task_type="cluster_and_link",
                    title=f"Link article: {article_title}",
                    phase="implementation",
                    priority="medium",
                    category="linking"
                )
                linking_task.category = f"linking:article_id={article_id}"
                self.task_list.save()
        except Exception:
            pass  # Silently fail - linking is optional
    
    def _mark_write_task_done(self, article_title: str):
        """Mark any matching 'Write article' task as done."""
        if not self.task_list:
            return
        
        try:
            for task in self.task_list.tasks:
                if task.type == "write_article" and task.status != "done":
                    # Check if task title matches article title
                    task_title = task.title.replace("Write article: ", "").strip().lower()
                    if task_title == article_title.lower() or article_title.lower() in task_title:
                        task.status = "done"
                        from datetime import datetime
                        task.completed_at = datetime.now().isoformat()
                        console.print(f"[dim]  Marked task '{task.title}' as done[/dim]")
                        self.task_list.save()
                        break
        except Exception:
            pass  # Silently fail - task marking is optional
