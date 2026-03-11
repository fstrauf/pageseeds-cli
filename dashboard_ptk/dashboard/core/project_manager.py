"""
Project management - add, edit, delete projects via UI
"""
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from prompt_toolkit import PromptSession

from ..config import PROJECTS_CONFIG, USER_CONFIG_DIR

console = Console()


@dataclass
class Project:
    """A project (website) being worked on."""
    name: str
    website_id: str
    repo_root: str
    content_dir: str = ""  # Optional override for content directory
    
    def __post_init__(self):
        # Ensure repo_root is expanded
        self.repo_root = str(Path(self.repo_root).expanduser().resolve())
        # Ensure content_dir is expanded if provided
        if self.content_dir:
            self.content_dir = str(Path(self.content_dir).expanduser().resolve())
    
    @property
    def repo_path(self) -> Path:
        return Path(self.repo_root)
    
    @property
    def automation_dir(self) -> Path:
        return self.repo_path / ".github" / "automation"
    
    def is_valid(self) -> tuple[bool, List[str]]:
        """Check if project configuration is valid."""
        issues = []
        
        # Check repo exists
        if not self.repo_path.exists():
            issues.append(f"Repository path does not exist: {self.repo_root}")
        
        # Check for automation directory
        if not self.automation_dir.exists():
            issues.append(f"No .github/automation/ directory found")
        
        # Check for articles.json
        articles_json = self.automation_dir / "articles.json"
        if not articles_json.exists():
            issues.append(f"No articles.json found")
        
        return len(issues) == 0, issues


class ProjectManager:
    """Manages the list of configured projects with UI support."""
    
    def __init__(self, projects_config_path: Path | None = None):
        self.projects: List[Project] = []
        self.current: Optional[Project] = None
        self.projects_config_path = (
            Path(projects_config_path).expanduser().resolve()
            if projects_config_path is not None
            else PROJECTS_CONFIG
        )
        self._load()
    
    def _load(self):
        """Load projects from config file."""
        if self.projects_config_path.exists():
            try:
                data = json.loads(self.projects_config_path.read_text())
                for p in data.get("projects", []):
                    self.projects.append(Project(
                        name=p.get("name", p["website_id"]),
                        website_id=p["website_id"],
                        repo_root=p["repo_root"],
                        content_dir=p.get("content_dir", "")
                    ))
            except Exception as e:
                console.print(f"[red]Error loading projects: {e}[/red]")
    
    def _save(self):
        """Save projects to config file."""
        try:
            self.projects_config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "projects": [
                    {
                        "name": p.name,
                        "website_id": p.website_id,
                        "repo_root": str(p.repo_root),
                        "content_dir": str(p.content_dir) if p.content_dir else ""
                    }
                    for p in self.projects
                ]
            }
            self.projects_config_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            console.print(f"[red]Error saving projects: {e}[/red]")
    
    def add_project(self, name: str, website_id: str, repo_root: str) -> tuple[bool, str]:
        """
        Add a new project.
        
        Returns:
            (success, message)
        """
        # Validate inputs
        if not name.strip():
            return False, "Project name cannot be empty"
        
        if not website_id.strip():
            return False, "Website ID cannot be empty"
        
        # Check for duplicates
        if any(p.website_id == website_id for p in self.projects):
            return False, f"Project with website_id '{website_id}' already exists"
        
        # Create project
        project = Project(name=name, website_id=website_id, repo_root=repo_root)
        
        # Validate
        is_valid, issues = project.is_valid()
        if not is_valid:
            return False, "\n".join(issues)
        
        # Add and save
        self.projects.append(project)
        self._save()
        
        return True, f"Project '{name}' added successfully"
    
    def edit_project(self, website_id: str, **kwargs) -> tuple[bool, str]:
        """
        Edit an existing project.
        
        Args:
            website_id: ID of project to edit
            **kwargs: Fields to update (name, repo_root, content_dir)
        
        Returns:
            (success, message)
        """
        project = self.get_by_id(website_id)
        if not project:
            return False, f"Project '{website_id}' not found"
        
        # Update fields
        if "name" in kwargs:
            project.name = kwargs["name"]
        if "repo_root" in kwargs:
            project.repo_root = str(Path(kwargs["repo_root"]).expanduser().resolve())
        if "content_dir" in kwargs:
            content_dir = str(kwargs["content_dir"]).strip()
            project.content_dir = str(Path(content_dir).expanduser().resolve()) if content_dir else ""
        
        # Re-validate
        is_valid, issues = project.is_valid()
        if not is_valid:
            return False, "\n".join(issues)
        
        self._save()
        return True, f"Project '{website_id}' updated"
    
    def delete_project(self, website_id: str) -> tuple[bool, str]:
        """
        Delete a project.
        
        Returns:
            (success, message)
        """
        project = self.get_by_id(website_id)
        if not project:
            return False, f"Project '{website_id}' not found"
        
        # Remove from list
        self.projects = [p for p in self.projects if p.website_id != website_id]
        
        # Clear current if it was deleted
        if self.current and self.current.website_id == website_id:
            self.current = None
        
        self._save()
        return True, f"Project '{project.name}' deleted"
    
    def get_by_id(self, website_id: str) -> Optional[Project]:
        """Get project by website_id."""
        for p in self.projects:
            if p.website_id == website_id:
                return p
        return None
    
    def validate_all(self) -> List[tuple[Project, List[str]]]:
        """Validate all projects and return issues."""
        results = []
        for project in self.projects:
            is_valid, issues = project.is_valid()
            if not is_valid:
                results.append((project, issues))
        return results
    
    # =========================================================================
    # UI Methods
    # =========================================================================
    
    def select_project_interactive(self, session: PromptSession) -> Optional[Project]:
        """Interactive project selection."""
        if not self.projects:
            console.print("\n[yellow]No projects configured.[/yellow]")
            console.print("Add a project first.\n")
            return None
        
        console.print("\n[bold]Select Project:[/bold]\n")
        
        for i, p in enumerate(self.projects, 1):
            # Show validation status
            is_valid, issues = p.is_valid()
            status = "[green]✓[/green]" if is_valid else "[red]✗[/red]"
            console.print(f"  {i}. {status} {p.name}")
            console.print(f"     [dim]{p.repo_root}[/dim]")
            if not is_valid:
                console.print(f"     [red]{len(issues)} issue(s)[/red]")
        
        console.print("\n  n. Add new project")
        console.print("  q. Quit")
        
        choice = session.prompt("\nChoice: ")
        
        if choice.lower() == 'q':
            return None
        
        if choice.lower() == 'n':
            return self.add_project_interactive(session)
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(self.projects):
                self.current = self.projects[idx]
                console.print(f"\n[green]✓ {self.current.name}[/green]")
                return self.current
        except ValueError:
            pass
        
        console.print("[red]Invalid choice[/red]")
        return None
    
    def add_project_interactive(self, session: PromptSession) -> Optional[Project]:
        """Interactive project creation."""
        console.print("\n[bold]Add New Project[/bold]\n")
        
        # Get project name
        name = session.prompt("Project name (e.g., 'Coffee Site'): ").strip()
        if not name:
            console.print("[red]Name cannot be empty[/red]")
            return None
        
        # Get website ID
        website_id = session.prompt("Website ID (e.g., 'coffee'): ").strip().lower()
        if not website_id:
            console.print("[red]Website ID cannot be empty[/red]")
            return None
        
        # Check for duplicate
        if any(p.website_id == website_id for p in self.projects):
            console.print(f"[red]Project '{website_id}' already exists[/red]")
            return None
        
        # Get repo path
        repo_path = session.prompt("Repository path: ").strip()
        repo_path = str(Path(repo_path).expanduser())
        
        if not Path(repo_path).exists():
            console.print(f"[red]Path does not exist: {repo_path}[/red]")
            create = session.prompt("Create directory? (y/n): ").lower()
            if create == 'y':
                Path(repo_path).mkdir(parents=True, exist_ok=True)
            else:
                return None
        
        # Check/initialize automation directory
        auto_dir = Path(repo_path) / ".github" / "automation"
        if not auto_dir.exists():
            console.print(f"\n[yellow]No .github/automation/ found[/yellow]")
            init = session.prompt("Initialize project structure? (y/n): ").lower()
            
            if init == 'y':
                success, msg = self._init_project_structure(repo_path, website_id)
                if not success:
                    console.print(f"[red]{msg}[/red]")
                    return None
                console.print(f"[green]{msg}[/green]")
        
        # Add project
        success, msg = self.add_project(name, website_id, repo_path)
        
        if success:
            console.print(f"\n[green]✓ {msg}[/green]")
            return self.get_by_id(website_id)
        else:
            console.print(f"\n[red]✗ {msg}[/red]")
            return None
    
    def edit_project_interactive(self, session: PromptSession) -> bool:
        """Interactive project editing."""
        if not self.projects:
            console.print("[yellow]No projects to edit[/yellow]")
            return False
        
        console.print("\n[bold]Edit Project[/bold]\n")
        
        for i, p in enumerate(self.projects, 1):
            console.print(f"  {i}. {p.name} ({p.website_id})")
        
        console.print("  c. Cancel")
        
        choice = session.prompt("\nSelect project: ")
        
        if choice.lower() == 'c':
            return False
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(self.projects):
                project = self.projects[idx]
                return self._edit_project_fields(session, project)
        except ValueError:
            pass
        
        return False
    
    def delete_project_interactive(self, session: PromptSession) -> bool:
        """Interactive project deletion."""
        if not self.projects:
            console.print("[yellow]No projects to delete[/yellow]")
            return False
        
        console.print("\n[bold red]Delete Project[/bold red]\n")
        
        for i, p in enumerate(self.projects, 1):
            console.print(f"  {i}. {p.name}")
        
        console.print("  c. Cancel")
        
        choice = session.prompt("\nSelect project to delete: ")
        
        if choice.lower() == 'c':
            return False
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(self.projects):
                project = self.projects[idx]
                
                # Confirm
                console.print(f"\n[red]Delete '{project.name}'?[/red]")
                console.print("[dim]This only removes the project from the dashboard.[/dim]")
                console.print("[dim]Your files and content will NOT be deleted.[/dim]")
                
                confirm = session.prompt("\nType 'delete' to confirm: ")
                
                if confirm == 'delete':
                    success, msg = self.delete_project(project.website_id)
                    if success:
                        console.print(f"\n[green]✓ {msg}[/green]")
                    else:
                        console.print(f"\n[red]✗ {msg}[/red]")
                    return success
        except ValueError:
            pass
        
        return False
    
    def show_project_status(self):
        """Show status of all projects."""
        console.print("\n[bold]Project Status[/bold]\n")
        
        if not self.projects:
            console.print("[yellow]No projects configured[/yellow]")
            return
        
        table = Table(show_header=True)
        table.add_column("Name")
        table.add_column("ID")
        table.add_column("Path")
        table.add_column("Status")
        
        for project in self.projects:
            is_valid, issues = project.is_valid()
            status = "[green]✓ OK[/green]" if is_valid else f"[red]✗ {len(issues)} issues[/red]"
            
            # Truncate path if too long
            path_str = str(project.repo_root)
            if len(path_str) > 40:
                path_str = "..." + path_str[-37:]
            
            table.add_row(
                project.name,
                project.website_id,
                path_str,
                status
            )
        
        console.print(table)
        
        # Show current
        if self.current:
            console.print(f"\n[green]Current:[/green] {self.current.name}")
    
    def _edit_project_fields(self, session: PromptSession, project: Project) -> bool:
        """Edit fields of a specific project."""
        console.print(f"\n[bold]Editing: {project.name}[/bold]\n")
        
        # Edit name
        new_name = session.prompt(f"Name [{project.name}]: ").strip()
        if new_name:
            project.name = new_name
        
        # Edit repo path
        new_path = session.prompt(f"Path [{project.repo_root}]: ").strip()
        if new_path:
            project.repo_root = str(Path(new_path).expanduser())
        
        # Validate and save
        is_valid, issues = project.is_valid()
        if not is_valid:
            console.print("\n[yellow]Warning:[/yellow]")
            for issue in issues:
                console.print(f"  - {issue}")
        
        self._save()
        console.print(f"\n[green]✓ Project updated[/green]")
        return True
    
    def _init_project_structure(self, repo_path: str, website_id: str) -> tuple[bool, str]:
        """Initialize automation directory structure with templates."""
        try:
            repo = Path(repo_path)
            auto_dir = repo / ".github" / "automation"
            auto_dir.mkdir(parents=True, exist_ok=True)
            
            # Create content directory
            content_dir = repo / "content"
            content_dir.mkdir(exist_ok=True)
            
            # Create subdirectories
            (auto_dir / "artifacts").mkdir(exist_ok=True)
            (auto_dir / "task_results").mkdir(exist_ok=True)
            (auto_dir / "reddit").mkdir(exist_ok=True)
            (auto_dir / "specs").mkdir(exist_ok=True)
            
            # Create manifest.json
            manifest = {
                "website": website_id,
                "url": f"https://{website_id}.example.com",
                "gsc_site": f"sc-domain:{website_id}.example.com"
            }
            (auto_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2)
            )
            
            # Create articles.json
            articles = {
                "nextArticleId": 1,
                "articles": []
            }
            (auto_dir / "articles.json").write_text(
                json.dumps(articles, indent=2)
            )
            
            # Create template files
            self._create_template_files(auto_dir, website_id)
            
            return True, "Project structure initialized with templates"
            
        except Exception as e:
            return False, str(e)
    
    def _create_template_files(self, auto_dir: Path, website_id: str) -> None:
        """Create template files for the project."""
        
        # brandvoice.md
        brandvoice_content = """# Brand Voice Guidelines

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
        (auto_dir / "brandvoice.md").write_text(brandvoice_content)
        
        # project_summary.md (generalized from days_to_expiry.md pattern)
        project_summary_content = f"""# Project Summary: {website_id}

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
        (auto_dir / "project_summary.md").write_text(project_summary_content)
        
        # seo_content_brief.md
        seo_brief_content = f"""# {website_id} - SEO Content Brief

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
        (auto_dir / "seo_content_brief.md").write_text(seo_brief_content)
        
        # reddit_config.md
        reddit_config_content = f"""# Reddit Config: {website_id}

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
        (auto_dir / "reddit_config.md").write_text(reddit_config_content)
        
        # reddit/_reply_guardrails.md
        reply_guardrails_content = """# Reply Guardrails & Quality Checklist

> Source of truth for all Reddit reply drafting.

## The Critique Workflow (Mandatory)

After drafting your reply, run this critique pass:

> Act as an old copy editor who believes deeply in respecting reader's time.
> Review your drafted reply and ask:
> 1. Is every sentence earning its place?
> 2. Can any words be cut without losing meaning?
> 3. Is the tone conversational, not corporate?
> 4. Does it sound like something you'd say to a friend?
> 5. Does it respect the reader's intelligence and time?

Then: Revise ruthlessly based on this critique.

## Core Rules (Non-Negotiable)

1. **No Links** – No `http://`, `https://`, or `[text](url)`
2. **No Markdown Formatting** – Plain text only
3. **Non-Promotional Tone** – Lead with education, not product features
4. **3–5 Sentences** – No longer
5. **Mention Product by Name (if relevant)** – Use simple, casual language

## The Formula

[Acknowledge] → [Educate] → [Tool (optional)] → [Engage]

## Quality Checklist

- [ ] Length: Exactly 3-5 sentences
- [ ] No Links: Zero URLs
- [ ] Tone: Sounds like advice from a knowledgeable friend
- [ ] Product Mention: Per project config stance
- [ ] Engaging Question: Ends with genuine question
- [ ] Specific Examples: Contains numbers or concrete details

## Product Mention Rules

- **REQUIRED**: Reply MUST contain exact product name
- **RECOMMENDED**: Include when natural
- **OPTIONAL**: Mention only if adds value
- **OMIT**: Do not mention product

## Forbidden Phrases

- ❌ "a dedicated tool" → Use exact product name
- ❌ "a platform" → Use exact product name
- ❌ "the app" → Use exact product name
- ❌ "a tracker" → Use exact product name
"""
        (auto_dir / "reddit" / "_reply_guardrails.md").write_text(reply_guardrails_content)
        
        # orchestrator_policy.json (minimal default)
        orchestrator_policy = {
            "version": "1.0",
            "website_id": website_id,
            "rules": [],
            "schedules": []
        }
        (auto_dir / "orchestrator_policy.json").write_text(
            json.dumps(orchestrator_policy, indent=2)
        )
