"""
Reddit tasks - opportunity search and engagement
"""
import json
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..engine import EnvResolver
from ..models import Task
from .base import TaskRunner

console = Console()


class RedditHistoryManager:
    """Manages posted/skipped Reddit post history to prevent duplicates."""
    
    def __init__(self, repo_root: Path):
        # History is now stored in .github/automation/reddit/ within the repo
        self.history_file = repo_root / ".github" / "automation" / "reddit" / "_posted_history.json"
        self._data = None
    
    def _load(self) -> dict:
        """Load history from JSON file."""
        if self._data is not None:
            return self._data
        
        if self.history_file.exists():
            try:
                loaded = json.loads(self.history_file.read_text())
                # Ensure all required keys exist
                if isinstance(loaded, dict):
                    self._data = {
                        "version": loaded.get("version", "1.0"),
                        "posted": loaded.get("posted", []),
                        "skipped": loaded.get("skipped", []),
                        "metadata": loaded.get("metadata", {"last_updated": datetime.now().isoformat()})
                    }
                    return self._data
            except (json.JSONDecodeError, IOError) as e:
                console.print(f"[yellow]Warning: Could not load history file: {e}[/yellow]")
        
        # Return empty history if file doesn't exist or is corrupted
        self._data = {"version": "1.0", "posted": [], "skipped": [], "metadata": {"last_updated": datetime.now().isoformat()}}
        return self._data
    
    def _save(self):
        """Save history back to JSON file."""
        try:
            self._data["metadata"]["last_updated"] = datetime.now().isoformat()
            self.history_file.write_text(json.dumps(self._data, indent=2))
        except IOError as e:
            console.print(f"[yellow]Warning: Could not save history file: {e}[/yellow]")
    
    def has_been_posted(self, post_id: str) -> bool:
        """Check if a post ID has already been posted to."""
        data = self._load()
        return post_id in data.get("posted", [])
    
    def has_been_skipped(self, post_id: str) -> bool:
        """Check if a post ID has been skipped (don't show again)."""
        data = self._load()
        return post_id in data.get("skipped", [])
    
    def record_posted(self, post_id: str, post_title: str = ""):
        """Record that we successfully posted to this post."""
        data = self._load()
        if post_id not in data["posted"]:
            data["posted"].append({
                "post_id": post_id,
                "title": post_title[:100],  # Truncate for storage
                "posted_at": datetime.now().isoformat()
            })
            self._save()
    
    def record_skipped(self, post_id: str, reason: str = ""):
        """Record that we skipped this post (don't suggest again)."""
        data = self._load()
        if post_id not in [p.get("post_id") if isinstance(p, dict) else p for p in data["skipped"]]:
            data["skipped"].append({
                "post_id": post_id,
                "reason": reason,
                "skipped_at": datetime.now().isoformat()
            })
            self._save()
    
    def get_stats(self) -> dict:
        """Get statistics about posted/skipped posts."""
        data = self._load()
        return {
            "total_posted": len(data.get("posted", [])),
            "total_skipped": len(data.get("skipped", []))
        }
    
    def clear_skipped(self) -> int:
        """Clear all skipped entries (allow rediscovery), keep posted.
        
        Returns:
            Number of skipped entries cleared
        """
        data = self._load()
        count = len(data.get("skipped", []))
        data["skipped"] = []
        self._save()
        return count


class RedditRunner(TaskRunner):
    """Handles Reddit opportunity search (Stage 1) and reply tasks."""
    
    def __init__(self, task_list, project, session):
        super().__init__(task_list, project, session)
        # Use the project's repo_root for history storage
        self.history = RedditHistoryManager(Path(project.repo_root))
    
    def run(self, task: Task) -> bool:
        """Dispatch to appropriate handler based on task type."""
        if task.type in ("reddit_opportunity_search", "reddit_search"):
            return self._run_opportunity_search(task)
        elif task.type == "reddit_reply":
            return self._run_reply_task(task)
        console.print(f"[red]✗ Unknown Reddit task type: {task.type}[/red]")
        return False
    
    def _run_opportunity_search(self, task: Task) -> bool:
        """Execute Reddit Stage 1: search, score, draft replies, create tasks."""
        console.print(f"\n[bold]Reddit Opportunity Search: {self.project.website_id}[/bold]\n")
        
        # Check required config files exist (in repo's .github/automation/ directory)
        repo_root = Path(self.project.repo_root)
        automation_dir = repo_root / ".github" / "automation"
        config_files = [
            automation_dir / "project_summary.md",
            automation_dir / "reddit_config.md",
            automation_dir / "brandvoice.md",
            automation_dir / "reddit" / "_reply_guardrails.md",
        ]
        
        missing = [f for f in config_files if not f.exists()]
        if missing:
            console.print("[red]✗ Missing required config files:[/red]")
            for f in missing:
                console.print(f"  - {f.name}")
            return False
        
        # Create output directory
        reddit_dir = self.task_list.artifacts_dir / "reddit"
        reddit_dir.mkdir(exist_ok=True)
        
        # Load posted history for deduplication
        history_stats = self.history.get_stats()
        console.print(f"[dim]Posted history: {history_stats['total_posted']} posted, {history_stats['total_skipped']} skipped[/dim]")
        console.print("[dim]Checking history to avoid duplicates...[/dim]\n")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = reddit_dir / f"search_{self.project.website_id}_{timestamp}.md"
        
        console.print("[dim]Running Reddit opportunity search...[/dim]\n")
        
        MAX_POST_AGE_DAYS = 14
        
        prompt = f"""You are a Reddit marketing researcher. Find opportunities for {self.project.website_id} and save results to a markdown file.

CONFIG FILES TO READ (from repo's .github/automation/ directory):
1. project_summary.md - Website/product description
2. reddit_config.md - Project-specific: product name, mention stance, trigger topics, excluded subreddits
3. brandvoice.md - Tone and voice guidelines

YOUR TASK:
1. Read project_summary.md to understand the product/website
2. Read reddit_config.md to get product name, mention stance, and excluded subreddits
3. Read brandvoice.md for tone guidelines
4. EXTRACT AND STATE: Before searching, write down:
   - Product name: [from reddit_config.md]
   - Mention stance: [REQUIRED/RECOMMENDED/OPTIONAL/OMIT]
   - Trigger topics: [list from reddit_config.md]
   - EXCLUDED subreddits: [list from reddit_config.md - NEVER search these]
5. Search Reddit using the CLI for each subreddit + query combination (use --time week)
   - SKIP any subreddit in the EXCLUDED list
6. Filter out posts older than {MAX_POST_AGE_DAYS} days - HARD RULE: only posts from last {MAX_POST_AGE_DAYS} days
   - The CLI returns `created_utc` as Unix timestamp - convert to YYYY-MM-DD
   - Calculate days_old = (today - posted_date).days
   - If days_old > {MAX_POST_AGE_DAYS}: SKIP IMMEDIATELY, do not score, do not draft reply
7. For each relevant post (max {MAX_POST_AGE_DAYS} days old), extract:
   - Post title, URL, subreddit
   - created_utc → convert to **Posted:** YYYY-MM-DD
   - Calculate and include **Age:** X days ago
   - Score and draft a reply following standards
8. For EACH reply, validate product mention before saving
9. Save results to: {output_file}

HARD DATE RULE (ENFORCED):
- Posts older than {MAX_POST_AGE_DAYS} days are NEVER included
- Calculate age: days_old = (today - posted_date).days
- If days_old > {MAX_POST_AGE_DAYS}: SKIP - do not include in results
- This is a HARD FILTER applied before scoring

DEDUPLICATION RULE:
Before including any post, check its post_id against the posted history file.
- Read: .github/automation/reddit/_posted_history.json
- If post_id is in "posted" array → SKIP (already replied)
- If post_id is in "skipped" array → SKIP (user chose to skip)
- Only include NEW posts that haven't been seen before

SUBREDDIT EXCLUSION RULE:
- Read the EXCLUDED section from reddit_config.md
- NEVER search subreddits in the excluded list
- For expense: personalfinance is EXCLUDED

CRITICAL: If you see a post about a topic you've seen before, DO NOT include it again even if it seems like a good fit.

SCORING (0-10 each):
- Relevance: How well it matches the project
- Engagement: min(10, upvotes / days_old / 10)  
- Accessibility: <10 comments=10, 10-30=8, 30-100=6, 100+=2
- Final Score = average of three

SEVERITY:
- CRITICAL: 8.5+, HIGH: 7.0-8.4, MEDIUM: 5.0-6.9

REPLY RULES (from _reply_standards.md):
- 3-5 sentences, plain text, no links
- Formula: Acknowledge → Educate → Product mention (per config stance) → Engage
- Product mention rules come from reddit_config.md (check REQUIRED/RECOMMENDED/OPTIONAL/OMIT)
- Vary product mention phrasing (see _reply_standards.md for patterns)

CRITIQUE WORKFLOW (Mandatory - Every Reply):
After drafting EACH reply, you MUST run this critique pass:

> Act as an old man copy editor at a respected newspaper who believes deeply in respecting your reader's time. Review your drafted reply and ask:
> 1. Is every sentence earning its place?
> 2. Can any words be cut without losing meaning?
> 3. Is the tone conversational, not corporate?
> 4. Does it sound like something you'd say to a friend over coffee?
> 5. Does it respect the reader's intelligence and time?

**Revise the reply based on this critique before finalizing.**

This critique pass is NON-NEGOTIABLE and applies to ALL replies regardless of project or stance.

CRITICAL - PRODUCT MENTION VALIDATION:
After drafting EACH reply, you MUST check:
1. What is the product name from reddit_config.md?
2. What is the stance (REQUIRED/RECOMMENDED/OPTIONAL/OMIT)?
3. Does this post match any trigger topics?
4. If stance is REQUIRED: DOES THE REPLY CONTAIN THE EXACT PRODUCT NAME?

**If stance is REQUIRED and the reply does NOT contain the product name, REWRITE IT to include the product mention.**

Examples of REQUIRED mentions:
- "I use Days to Expiry to track my DTE ranges."
- "Before picking a strike, I sanity-check in Days to Expiry."
- "I started tracking my option data in Days to Expiry to catch these anomalies."

**FORBIDDEN VAGUE PHRASES (NEVER USE THESE):**
- ❌ "a dedicated tool" → Use "Days to Expiry"
- ❌ "a platform" → Use "Days to Expiry"  
- ❌ "the app" → Use "Days to Expiry"
- ❌ "a tool I built" → Use "Days to Expiry" (unless you literally built it yourself)
- ❌ "my tool" → Use "Days to Expiry"
- ❌ "a tracker" → Use "Days to Expiry"

**RULE: Use the EXACT product name from reddit_config.md. No substitutions. No vague references.**

**DO NOT SKIP THE PRODUCT MENTION WHEN STANCE IS REQUIRED.**

OUTPUT FORMAT (Markdown):
Save to {output_file} using this exact structure:

# Reddit Opportunities: {self.project.website_id}

Search Date: YYYY-MM-DD
Total Found: X

## Summary
- CRITICAL: X
- HIGH: X  
- MEDIUM: X

---

## Opportunity 1

**Post:** [actual post title]
**Subreddit:** r/[name]
**Posted:** YYYY-MM-DD (extract from Reddit post created_utc)
**Age:** X days ago (calculated from posted date)
**Severity:** [CRITICAL|HIGH|MEDIUM]
**Score:** X.X/10
**URL:** [full permalink]
**Why Relevant:** [one sentence]
**Product Mention Stance:** [REQUIRED/RECOMMENDED/OPTIONAL/OMIT - from config]

**Drafted Reply:**
[the actual reply text - 3-5 sentences]
[Reply MUST include product name if stance is REQUIRED]

---

[repeat for each opportunity]

IMPORTANT:
- Only include MEDIUM+ opportunities (score 5.0+)
- Write actual replies, not placeholders
- Use WriteFile to save to the exact path: {output_file}

FINAL VALIDATION - BEFORE SAVING:
Go through EVERY opportunity and verify:

1. **Posted Date Check:**
   - Does each opportunity have **Posted:** YYYY-MM-DD? 
   - Extract from Reddit's created_utc field
   - If missing → add it now

2. **Product Name Check:**
   - If stance is REQUIRED: Does reply contain EXACT product name? If NO → rewrite now.
   - If stance is RECOMMENDED: Should mention product for this topic? If YES but missing → add it.

3. **Vague Phrase Check (REJECT THESE):**
   - Search for: "a dedicated tool", "a platform", "the app", "a tracker", "my tool"
   - If found → REPLACE with exact product name from config
   - Example: "I use a dedicated tool" → "I use Days to Expiry"

DO NOT save the file until ALL opportunities have:
- **Posted:** YYYY-MM-DD date (extracted from Reddit)
- Exact product name in replies (not vague substitutes)
- Follow the stance rules from reddit_config.md
"""
        
        success, output = self.run_kimi_agent(prompt, timeout=600)
        
        # Check if file was created
        if not output_file.exists():
            console.print("[red]✗ Output file not created[/red]")
            console.print("[dim]Agent output:[/dim]")
            console.print(output[-500:] if output else "No output")
            return False
        
        # Parse the markdown file
        content = output_file.read_text()
        opportunities = self._parse_opportunities_from_markdown(content)
        
        if not opportunities:
            console.print("[yellow]No valid opportunities found in output[/yellow]")
            console.print("[dim]File content preview:[/dim]")
            console.print(content[:500])
            return False
        
        # Create reply tasks for each opportunity
        created_count = 0
        for opp in opportunities:
            reply_task = self.task_list.create_reddit_reply_task(
                post_title=opp.get("title", ""),
                post_id=opp.get("post_id", ""),
                reply_text=opp.get("reply", ""),
                parent_artifact=str(output_file.relative_to(self.task_list.automation_dir)),
                severity=opp.get("severity", "MEDIUM"),
                url=opp.get("url", ""),
                subreddit=opp.get("subreddit", ""),
                post_date=opp.get("post_date", "")
            )
            created_count += 1
        
        # Mark search task as done
        task.status = "done"
        task.completed_at = datetime.now().isoformat()
        task.output_artifact = str(output_file.relative_to(self.task_list.automation_dir))
        task.notes = f"Created {created_count} reply tasks"
        self.task_list.save()
        
        # Show summary
        console.print(f"\n[green]✓ Found {len(opportunities)} opportunities[/green]")
        
        # Count by severity
        severity_counts = {}
        for opp in opportunities:
            sev = opp.get("severity", "MEDIUM")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        if severity_counts:
            table = Table(title="By Severity")
            table.add_column("Severity", style="cyan")
            table.add_column("Count", style="magenta")
            for sev, count in sorted(severity_counts.items(), 
                                     key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x[0], 4)):
                color = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "green", "LOW": "dim"}.get(sev, "white")
                table.add_row(f"[{color}]{sev}[/{color}]", str(count))
            console.print(table)
        
        console.print(f"\n[green]✓ Created {created_count} reply tasks[/green]")
        console.print("[dim]Use 'Bulk by Type' or 'Batch Mode' to process replies[/dim]")
        return True
    
    def _parse_opportunities_from_markdown(self, content: str) -> list:
        """Parse opportunity data from markdown."""
        opportunities = []
        duplicates_skipped = 0
        too_old_skipped = 0
        MAX_POST_AGE_DAYS = 14
        
        # Split by opportunity headers
        sections = re.split(r'\n## Opportunity \d+\s*\n', content)
        
        for section in sections[1:]:  # Skip header section
            opp = {}
            
            # Extract title
            title_match = re.search(r'\*\*Post:\*\*\s*(.+?)\s*\n', section)
            if title_match:
                opp['title'] = title_match.group(1).strip()
            
            # Extract subreddit
            sub_match = re.search(r'\*\*Subreddit:\*\*\s*r/(\w+)', section)
            if sub_match:
                opp['subreddit'] = sub_match.group(1)
            
            # Extract post date (YYYY-MM-DD format)
            date_match = re.search(r'\*\*Posted:\*\*\s*(\d{4}-\d{2}-\d{2})', section)
            if date_match:
                opp['post_date'] = date_match.group(1)
            else:
                # Try alternative format with potential time component
                date_match = re.search(r'\*\*Posted:\*\*\s*(\d{4}-\d{2}-\d{2})', section)
                if date_match:
                    opp['post_date'] = date_match.group(1)
            
            # CODE-LEVEL VALIDATION: Skip posts older than MAX_POST_AGE_DAYS
            if opp.get('post_date'):
                try:
                    post_dt = datetime.strptime(opp['post_date'], "%Y-%m-%d")
                    days_old = (datetime.now() - post_dt).days
                    if days_old > MAX_POST_AGE_DAYS:
                        too_old_skipped += 1
                        console.print(f"[dim]Skipping '{opp.get('title', 'Unknown')[:40]}...' - {days_old} days old (max {MAX_POST_AGE_DAYS})[/dim]")
                        continue
                except ValueError:
                    # Invalid date format, skip this opportunity
                    continue
            
            # Extract severity
            sev_match = re.search(r'\*\*Severity:\*\*\s*(\w+)', section, re.IGNORECASE)
            if sev_match:
                opp['severity'] = sev_match.group(1).upper()
            
            # Extract URL for post_id
            url_match = re.search(r'\*\*URL:\*\*\s*(https://[^\s]+)', section)
            if url_match:
                url = url_match.group(1)
                post_id_match = re.search(r'/comments/(\w+)', url)
                opp['post_id'] = post_id_match.group(1) if post_id_match else url.split('/')[-1]
            else:
                opp['post_id'] = f"opp_{len(opportunities)}"
            
            # Check if already posted/skipped (client-side dedup)
            if self.history.has_been_posted(opp['post_id']) or self.history.has_been_skipped(opp['post_id']):
                duplicates_skipped += 1
                continue
            
            # Extract reply text
            reply_match = re.search(r'\*\*Drafted Reply:\*\*\s*\n(.+?)(?:\n---|\n## |\Z)', section, re.DOTALL)
            if reply_match:
                opp['reply'] = reply_match.group(1).strip()
            else:
                opp['reply'] = ""
            
            # Only include if we have both title and reply, and reply isn't a placeholder
            if (opp.get('title') and opp.get('reply') and 
                opp['reply'] and 
                '[actual' not in opp['reply'].lower() and
                '[placeholder' not in opp['reply'].lower() and
                len(opp['reply']) > 50):  # Must be substantial
                opportunities.append(opp)
        
        if duplicates_skipped > 0:
            console.print(f"[dim]Skipped {duplicates_skipped} duplicate posts (already in history)[/dim]")
        
        if too_old_skipped > 0:
            console.print(f"[yellow]Skipped {too_old_skipped} posts older than {MAX_POST_AGE_DAYS} days[/yellow]")
        
        return opportunities
    
    def _run_reply_task(self, task: Task) -> bool:
        """Display a Reddit reply for human review and posting."""
        console.print(f"\n[bold]Review Reddit Reply[/bold]\n")
        console.print(f"Task: {task.title}")
        
        # Show drafted reply from notes - FULL TEXT
        if task.notes:
            console.print(f"\n[bold]Drafted Reply:[/bold]")
            console.print("─" * 60)
            console.print(task.notes)
            console.print("─" * 60)
        else:
            console.print("[red]No reply text found in task notes.[/red]")
            return False
        
        # Extract post_id and subreddit
        post_id = self._extract_post_id(task)
        subreddit = task.subreddit or self._extract_subreddit(task)
        
        # Show subreddit if available
        if subreddit:
            console.print(f"Subreddit: [cyan]r/{subreddit}[/cyan]")
        
        # Show post date with age indicator (ALWAYS show this)
        post_date = task.post_date
        if not post_date and task.input_artifact:
            # Try to extract date from parent artifact
            post_date = self._extract_date_from_artifact(task)
        
        if post_date:
            try:
                post_dt = datetime.strptime(post_date, "%Y-%m-%d")
                days_old = (datetime.now() - post_dt).days
                
                if days_old == 0:
                    age_color = "green"
                    age_text = "today"
                elif days_old == 1:
                    age_color = "green"
                    age_text = "yesterday"
                elif days_old <= 3:
                    age_color = "green"
                    age_text = f"{days_old} days ago"
                elif days_old <= 7:
                    age_color = "yellow"
                    age_text = f"{days_old} days ago"
                elif days_old <= 14:
                    age_color = "yellow"
                    age_text = f"{days_old} days ago"
                else:
                    age_color = "red"
                    age_text = f"{days_old} days ago"
                
                console.print(f"Posted: [cyan]{post_date}[/cyan] ([{age_color}]{age_text}[/{age_color}])")
                
                # HARD BLOCK: Prevent posting to posts older than 14 days
                MAX_POST_AGE_DAYS = 14
                if days_old > MAX_POST_AGE_DAYS:
                    console.print(f"[red]✗ CANNOT POST: Post is {days_old} days old (max {MAX_POST_AGE_DAYS})[/red]")
                    console.print(f"[dim]This post is too old to reply to. Please skip or keep for review.[/dim]")
            except ValueError:
                console.print(f"Posted: [cyan]{post_date}[/cyan]")
        else:
            console.print(f"Posted: [yellow]Unknown date[/yellow]")
        
        # Check if auto-post is available (requires non-empty REDDIT_REFRESH_TOKEN)
        auth_ready, auth_hint, _token = self._reddit_auth_status()
        can_auto_post = auth_ready
        
        # Check if post is too old to disable auto-post
        post_too_old = False
        check_date = task.post_date or post_date  # Use post_date which may have been extracted from artifact
        if check_date:
            try:
                post_dt = datetime.strptime(check_date, "%Y-%m-%d")
                days_old = (datetime.now() - post_dt).days
                if days_old > 14:
                    post_too_old = True
                    can_auto_post = False
            except ValueError:
                pass
        
        # Check for batch default action
        default_action = self._execution_context.get("reddit_reply", {}).get("action")
        choice = None
        
        if default_action:
            # Map default action to choice number
            action_map = {
                "copy_and_mark": "1",
                "auto_post": "2",
                "skip": "3",
                "keep": "4",
            }
            mapped_choice = action_map.get(default_action)
            
            # Validate the default action is applicable
            if mapped_choice == "2" and post_too_old:
                console.print(f"[yellow]⚠ Default action 'auto_post' disabled - post >14 days old[/yellow]")
            elif mapped_choice == "2" and not can_auto_post:
                console.print(f"[yellow]⚠ Default action 'auto_post' not available - {auth_hint}[/yellow]")
            else:
                choice = mapped_choice
                console.print(f"[dim]Using batch default action: {default_action}[/dim]")
        
        # Human decision (if no valid default action)
        if not choice:
            console.print("\n[bold]Actions:[/bold]")
            console.print("  1. Copy reply and mark posted (I will post manually)")
            if post_too_old:
                console.print("  2. [dim]Post automatically (disabled - post >14 days old)[/dim]")
            elif post_id and can_auto_post:
                console.print("  2. [cyan]Post automatically to Reddit[/cyan]")
            elif post_id:
                console.print(f"  2. [dim]Post automatically ({auth_hint})[/dim]")
            else:
                console.print("  2. [dim]Post automatically (no post_id found)[/dim]")
            if post_too_old:
                console.print("  3. [yellow]Skip this opportunity (recommended - post too old)[/yellow]")
            else:
                console.print("  3. Skip this opportunity")
            console.print("  4. Keep for later review")
            
            choice = self.session.prompt("\nChoice (1/2/3/4): ")
        
        if choice == "1":
            # Copy to clipboard
            try:
                import pyperclip
                pyperclip.copy(task.notes)
                console.print("[green]✓ Reply copied to clipboard[/green]")
            except ImportError:
                console.print("[dim]Install pyperclip to enable auto-copy[/dim]")
            
            # Record in history to prevent duplicates
            if post_id:
                self.history.record_posted(post_id, task.title.replace("Reply: ", ""))
                console.print("[dim]Recorded in history (won't suggest again)[/dim]")
            
            task.status = "done"
            task.completed_at = datetime.now().isoformat()
            self.task_list.save()
            console.print("[green]✓ Marked as posted[/green]")
            return True
            
        elif choice == "2":
            # HARD BLOCK: Never post to posts older than 14 days
            if post_too_old:
                console.print("[red]Cannot auto-post: Post is too old (>14 days)[/red]")
                console.print("[dim]Reddit API will reject posts to archived threads.[/dim]")
                console.print("[dim]Use option 1 to copy and post manually, or option 3 to skip.[/dim]")
                return False
            
            if not post_id:
                console.print("[red]Cannot auto-post: no post_id found[/red]")
                return False
            
            auth_ready, auth_hint, token = self._reddit_auth_status()
            if not auth_ready:
                console.print("[yellow]Auto-posting not available.[/yellow]")
                console.print(f"[dim]{auth_hint}[/dim]")
                console.print("[dim]To enable auto-posting:[/dim]")
                console.print("  1. Get a Reddit refresh token (see REDDIT_POSTING_SETUP.md)")
                console.print("  2. Set REDDIT_REFRESH_TOKEN in env, ~/.config/automation/secrets.env, repo .env/.env.local, or automation/.env")
                console.print("\n[dim]For now, use option 1 to copy the reply and post manually.[/dim]")
                return False

            # Get all Reddit credentials (token + client_id + client_secret)
            reddit_creds = self._get_reddit_credentials()
            
            auth_ok, auth_error = self._verify_reddit_auth_via_cli(reddit_creds)
            if not auth_ok:
                console.print("[red]Cannot auto-post: Reddit auth validation failed.[/red]")
                if auth_error:
                    console.print(f"[dim]{auth_error}[/dim]")
                console.print("[dim]Refresh or replace REDDIT_REFRESH_TOKEN, then try again.[/dim]")
                return False
            
            # Confirm before posting unless explicitly pre-confirmed in execution context
            skip_confirm = bool(self._execution_context.get("reddit_reply", {}).get("skip_confirm"))
            if not skip_confirm and not self.auto_confirm_enabled():
                confirm = self.session.prompt(f"\nPost to Reddit post {post_id}? (yes/no): ")
                if confirm.lower().strip() != "yes":
                    console.print("[dim]Cancelled[/dim]")
                    return False
            else:
                console.print("[dim]Auto-confirm enabled; posting without per-task prompt.[/dim]")
            
            # Submit comment via CLI
            console.print("[dim]Posting to Reddit...[/dim]")
            cmd = ["reddit", "submit-comment", "--post-id", post_id, "--text", task.notes]
            
            console.print(f"[dim]DEBUG: post_id={post_id}, text_length={len(task.notes)}[/dim]")
            
            success, stdout, stderr = self.run_cli_command(
                cmd,
                env_overrides=reddit_creds if reddit_creds else None,
            )
            
            if stdout:
                console.print(f"[dim]DEBUG: stdout={stdout[:500]}[/dim]")
            if stderr:
                console.print(f"[dim]DEBUG: stderr={stderr[:500]}[/dim]")
            
            if success:
                # Parse and show full response (strip debug lines before parsing)
                if stdout:
                    try:
                        # Remove DEBUG: lines and extract only the JSON part
                        import re
                        json_match = re.search(r'\{[\s\S]*\}', stdout)
                        if json_match:
                            json_str = json_match.group(0)
                            result = __import__('json').loads(json_str)
                        else:
                            raise ValueError("No JSON found in output")
                        
                        if result.get("success"):
                            permalink = result.get("permalink", "")
                            comment_id = result.get("comment_id", "")
                            
                            if permalink:
                                full_url = f"https://reddit.com{permalink}"
                                console.print(f"\n[cyan]Comment URL:[/cyan]")
                                console.print(f"[blue underline]{full_url}[/blue underline]")
                            elif comment_id:
                                # Build URL from comment_id
                                full_url = f"https://reddit.com/r/{subreddit}/comments/{post_id}/_/{comment_id}/"
                                console.print(f"\n[cyan]Comment URL:[/cyan]")
                                console.print(f"[blue underline]{full_url}[/blue underline]")
                            else:
                                # Fallback to post URL
                                post_url = f"https://reddit.com/r/{subreddit}/comments/{post_id}/"
                                console.print(f"\n[yellow]Post URL (comment ID not returned):[/yellow]")
                                console.print(f"[blue underline]{post_url}[/blue underline]")
                        else:
                            error_msg = result.get('error', 'Unknown error')
                            console.print(f"[red]✗ Reddit API error: {error_msg}[/red]")
                            # Provide helpful guidance based on error
                            if 'archived' in error_msg.lower():
                                console.print("[yellow]→ Post is too old (>6 months) and cannot be replied to[/yellow]")
                            elif 'forbidden' in error_msg.lower() or 'locked' in error_msg.lower():
                                console.print("[yellow]→ Post may be locked or subreddit has karma/account age requirements[/yellow]")
                                console.print("[dim]  Try posting manually to verify access[/dim]")
                            elif 'rate limited' in error_msg.lower():
                                console.print("[yellow]→ You're posting too fast. Wait a few minutes.[/yellow]")
                            return False
                    except Exception as e:
                        console.print(f"[red]✗ Failed to parse response: {e}[/red]")
                        console.print(f"[dim]Raw stdout: {stdout}[/dim]")
                        return False
                else:
                    console.print("[yellow]⚠ No output from CLI[/yellow]")
                
                # Record in history to prevent duplicates
                if post_id:
                    self.history.record_posted(post_id, task.title.replace("Reply: ", ""))
                    console.print("[dim]Recorded in history (won't suggest again)[/dim]")
                
                task.status = "done"
                task.completed_at = datetime.now().isoformat()
                self.task_list.save()
                return True
            else:
                console.print(f"[red]✗ CLI failed: {stderr}[/red]")
                return False
            
        elif choice == "3":
            # Record in history so we don't suggest again
            if post_id:
                self.history.record_skipped(post_id, "User chose to skip")
                console.print("[dim]Recorded as skipped (won't suggest again)[/dim]")
            
            task.status = "cancelled"
            task.notes = f"Skipped: {task.notes}"
            console.print("[dim]Opportunity skipped[/dim]")
            return True
            
        else:  # choice == "4"
            console.print("[dim]Kept for later review[/dim]")
            return True

    def run_reply_task_autonomous(self, task: Task) -> tuple[bool, str]:
        """Execute reddit_reply without prompts (for orchestration runs)."""
        if not task.notes:
            return False, "No reply text found in task notes."

        post_id = self._extract_post_id(task)
        subreddit = task.subreddit or self._extract_subreddit(task)
        if not post_id:
            return False, "Cannot auto-post: no post_id found."

        post_date = task.post_date or self._extract_date_from_artifact(task)
        if post_date:
            try:
                post_dt = datetime.strptime(post_date, "%Y-%m-%d")
                days_old = (datetime.now() - post_dt).days
                if days_old > 14:
                    return False, f"Cannot auto-post: post is {days_old} days old (>14)."
            except ValueError:
                pass

        auth_ready, _auth_hint, token = self._reddit_auth_status()
        if not auth_ready:
            return False, "Auto-posting not available: REDDIT_REFRESH_TOKEN missing/empty."

        # Get all Reddit credentials (token + client_id + client_secret)
        reddit_creds = self._get_reddit_credentials()
        
        auth_ok, auth_error = self._verify_reddit_auth_via_cli(reddit_creds)
        if not auth_ok:
            return False, f"Reddit auth validation failed: {auth_error}"

        submit_ok, result, error = self._submit_reddit_comment_cli(
            post_id=post_id,
            subreddit=subreddit,
            text=task.notes,
            creds=reddit_creds,
        )
        if not submit_ok:
            return False, error or "Reddit API submission failed."

        self.history.record_posted(post_id, task.title.replace("Reply: ", ""))
        task.status = "done"
        task.completed_at = datetime.now().isoformat()
        self.task_list.save()

        permalink = result.get("permalink", "") if isinstance(result, dict) else ""
        comment_id = result.get("comment_id", "") if isinstance(result, dict) else ""
        if permalink:
            return True, f"https://reddit.com{permalink}"
        if comment_id and subreddit:
            return True, f"https://reddit.com/r/{subreddit}/comments/{post_id}/_/{comment_id}/"
        return True, "posted"
    
    def _extract_post_id(self, task: Task) -> str:
        """Extract Reddit post_id from task data or markdown file."""
        # First check task.post_id
        if task.post_id:
            if '/comments/' in task.post_id:
                match = re.search(r'/comments/(\w+)', task.post_id)
                if match:
                    return match.group(1)
            return task.post_id
        
        # Check task.url
        if task.url:
            match = re.search(r'/comments/(\w+)', task.url)
            if match:
                return match.group(1)
        
        # Fallback: extract from markdown file
        return self._extract_from_markdown(task, "post_id")
    
    def _extract_subreddit(self, task: Task) -> str:
        """Extract subreddit from task data or markdown file."""
        if task.subreddit:
            return task.subreddit
        
        # Fallback: extract from markdown file
        return self._extract_from_markdown(task, "subreddit")
    
    def _extract_date_from_artifact(self, task: Task) -> str:
        """Extract post date from the parent markdown artifact."""
        if not task.input_artifact:
            return ""
        
        try:
            artifact_path = self.task_list.automation_dir / task.input_artifact
            if not artifact_path.exists():
                return ""
            
            content = artifact_path.read_text()
            title = task.title.replace("Reply: ", "").strip()
            
            # Split by opportunity sections
            sections = re.split(r'\n## Opportunity \d+\s*\n', content)
            
            for section in sections:
                if title[:40].lower() in section.lower():
                    # Extract date
                    date_match = re.search(r'\*\*Posted:\*\*\s*(\d{4}-\d{2}-\d{2})', section)
                    if date_match:
                        return date_match.group(1)
        except Exception:
            pass
        
        return ""
    
    def _can_auto_post(self) -> bool:
        """Check if auto-posting is available (requires non-empty REDDIT_REFRESH_TOKEN)."""
        auth_ready, _, _ = self._reddit_auth_status()
        return auth_ready

    def _reddit_auth_status(self) -> tuple[bool, str, str | None]:
        """Return auth readiness, UI hint, and resolved token (if any)."""
        token, source, saw_empty = self._resolve_reddit_refresh_token()
        if token:
            source_hint = source if source else "resolved source"
            return True, f"auth ready ({source_hint})", token
        if saw_empty:
            return False, "REDDIT_REFRESH_TOKEN is empty", None
        return False, "set REDDIT_REFRESH_TOKEN (env, secrets.env, repo .env/.env.local, or automation/.env)", None

    def _env_resolver(self) -> EnvResolver:
        return EnvResolver(
            repo_root=Path(self.project.repo_root),
        )

    def _resolve_reddit_refresh_token(self) -> tuple[str | None, str | None, bool]:
        """Resolve token from env + standard env files without mutating process environment."""
        return self._env_resolver().resolve_key("REDDIT_REFRESH_TOKEN")
    
    def _get_reddit_credentials(self) -> dict[str, str]:
        """Get all Reddit credentials (token, client_id, client_secret) for CLI calls."""
        resolver = self._env_resolver()
        creds: dict[str, str] = {}
        
        # Get refresh token
        token, _, _ = resolver.resolve_key("REDDIT_REFRESH_TOKEN")
        if token:
            creds["REDDIT_REFRESH_TOKEN"] = token
        
        # Get client ID (required for posting)
        client_id, _, _ = resolver.resolve_key("REDDIT_CLIENT_ID")
        if client_id:
            creds["REDDIT_CLIENT_ID"] = client_id
        
        # Get client secret (required for posting)
        client_secret, _, _ = resolver.resolve_key("REDDIT_CLIENT_SECRET")
        if client_secret:
            creds["REDDIT_CLIENT_SECRET"] = client_secret
        
        return creds

    def _verify_reddit_auth_via_cli(self, creds: dict[str, str] | None) -> tuple[bool, str | None]:
        """Run CLI auth-status to validate credentials before attempting to post."""
        if not creds or not creds.get("REDDIT_REFRESH_TOKEN"):
            return False, "Missing REDDIT_REFRESH_TOKEN."

        success, stdout, stderr = self.run_cli_command(
            ["reddit", "auth-status"],
            timeout=45,
            env_overrides=creds,
        )
        if not success:
            return False, (stderr or stdout or "Failed to run reddit auth-status").strip()

        if not stdout:
            return False, "reddit auth-status returned no output."

        try:
            json_match = re.search(r"\{[\s\S]*\}", stdout)
            if not json_match:
                return False, f"Unexpected auth-status output: {stdout[:240]}"
            payload = json.loads(json_match.group(0))
        except Exception as exc:
            return False, f"Could not parse auth-status JSON: {exc}"

        if payload.get("authenticated") is True:
            return True, None
        return False, payload.get("error") or "Reddit auth not ready."

    def _submit_reddit_comment_cli(
        self,
        *,
        post_id: str,
        subreddit: str,
        text: str,
        creds: dict[str, str] | None,
    ) -> tuple[bool, dict, str | None]:
        """Submit reddit comment via CLI and parse JSON result."""
        success, stdout, stderr = self.run_cli_command(
            ["reddit", "submit-comment", "--post-id", post_id, "--text", text],
            env_overrides=creds if creds else None,
        )
        if not success:
            return False, {}, (stderr or stdout or "CLI command failed").strip()
        if not stdout:
            return False, {}, "CLI returned no output."

        try:
            json_match = re.search(r"\{[\s\S]*\}", stdout)
            if not json_match:
                return False, {}, f"Unexpected submit-comment output: {stdout[:240]}"
            result = json.loads(json_match.group(0))
        except Exception as exc:
            return False, {}, f"Failed to parse submit-comment JSON: {exc}"

        if result.get("success"):
            return True, result, None

        error_msg = result.get("error") or "Unknown Reddit API error."
        if "archived" in error_msg.lower():
            return False, result, "Post is archived and cannot be replied to."
        if "forbidden" in error_msg.lower() or "locked" in error_msg.lower():
            return False, result, "Post locked or subreddit/account restrictions prevent posting."
        if "rate limited" in error_msg.lower():
            return False, result, "Rate limited by Reddit; wait and retry later."
        return False, result, error_msg

    @staticmethod
    def _automation_workspace_env_path() -> Path:
        """Return workspace-level automation .env path."""
        return EnvResolver.default_automation_root() / ".env"
    
    def _extract_from_markdown(self, task: Task, field: str) -> str:
        """Extract data from markdown file by matching title."""
        if not task.input_artifact:
            return ""
        
        try:
            artifact_path = self.task_list.automation_dir / task.input_artifact
            if not artifact_path.exists():
                return ""
            
            content = artifact_path.read_text()
            title = task.title.replace("Reply: ", "").strip()
            
            # Split by opportunity sections
            sections = re.split(r'\n## Opportunity \d+\s*\n', content)
            
            for section in sections:
                if title[:40].lower() in section.lower():
                    if field == "post_id":
                        url_match = re.search(r'\*\*URL:\*\*\s*(https://[^\s\n]+)', section)
                        if url_match:
                            url = url_match.group(1)
                            post_match = re.search(r'/comments/(\w+)', url)
                            if post_match:
                                return post_match.group(1)
                    elif field == "subreddit":
                        sub_match = re.search(r'\*\*Subreddit:\*\*\s*r/(\w+)', section)
                        if sub_match:
                            return sub_match.group(1)
        except Exception as e:
            console.print(f"[dim]Debug: Error extracting {field}: {e}[/dim]")
        
        return ""
