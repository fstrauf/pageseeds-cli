"""
Main implementation task dispatcher
"""
import time
from datetime import datetime
from rich.console import Console

from ..config import EXECUTION_MODE_MAP, AUTONOMY_MODE_MAP
from ..models import Task
from ..storage import TaskList
from ..ui import console
from .base import TaskRunner

console = Console()


class ImplementationRunner(TaskRunner):
    """Dispatches implementation tasks to appropriate handlers."""
    
    def __init__(self, task_list, project, session, runners: dict):
        super().__init__(task_list, project, session)
        self.runners = runners
    
    def _get_execution_mode(self, task_type: str) -> str:
        """Get execution mode based on task type."""
        return EXECUTION_MODE_MAP.get(task_type, "auto")
    
    def _get_agent_decision(self, task: Task) -> tuple[str, str]:
        """Ask agent to decide implementation approach for unknown task types."""
        prompt = f"""You are analyzing an implementation task for {self.project.website_id}.

TASK: {task.title}
TYPE: {task.type}
CATEGORY: {task.category or 'none'}

Your job is to DECIDE how to implement this task. Choose ONE:

A) DIRECT - Simple content changes (write markdown, edit text, add images, write articles)
B) SPECIFICATION - Code/structural changes (Vue components, build config, routes, DB)
C) INVESTIGATION - Not enough info, need to analyze codebase first

GUIDELINES:
- DIRECT for: Writing articles/blog posts, editing markdown files, updating text content, adding images
- SPECIFICATION for: Code changes, config changes, structural modifications, anything requiring dev environment
- INVESTIGATION for: Unclear what files to modify, need to explore codebase first

CONTENT EXAMPLES (use DIRECT):
- "Write article about Kenya coffee"
- "Create blog post for..."
- "Optimize content for page..."

TECHNICAL EXAMPLES (use SPECIFICATION):
- "Fix robots meta tags"
- "Update sitemap generation"
- "Add canonical URLs"

RESPOND WITH EXACTLY ONE WORD: DIRECT, SPECIFICATION, or INVESTIGATION

Then on the next line, briefly explain why (1-2 sentences).

Example response:
SPECIFICATION
This requires modifying Vue components and build configuration, which needs testing in a dev environment."""
        
        console.print("[dim]Agent analyzing task...[/dim]")
        
        try:
            success, output = self.run_kimi_agent(prompt, timeout=60)
            
            if output:
                lines = output.strip().split('\n')
                decision = lines[0].strip().upper()
                reasoning = lines[1].strip() if len(lines) > 1 else "Agent decision"
                
                if "DIRECT" in decision:
                    return ("direct", reasoning)
                elif "INVESTIGATION" in decision:
                    return ("investigation", reasoning)
                else:
                    return ("specification", reasoning)
            else:
                return ("specification", "No response from agent, defaulting to specification")
                
        except Exception as e:
            console.print(f"[red]Error during analysis: {e}[/red]")
            return ("specification", f"Error: {e}")
    
    def _write_specification(self, task: Task) -> bool:
        """Let agent write the specification markdown directly."""
        import threading
        from rich.status import Status
        
        # Create specs directory
        specs_dir = self.task_list.automation_dir / "specs"
        specs_dir.mkdir(exist_ok=True)
        
        spec_file = specs_dir / f"{task.id}_spec.md"
        
        # Build context file paths
        context_files = []
        
        # Primary context: task's input_artifact (investigation result)
        if task.input_artifact:
            context_path = self.task_list.automation_dir / task.input_artifact
            if context_path.exists():
                context_files.append(("Investigation Result", str(context_path.absolute())))
        
        # Trace back to original source data through parent task
        source_artifact = None
        if task.parent_task:
            parent = next((t for t in self.task_list.tasks if t.id == task.parent_task), None)
            if parent and parent.input_artifact:
                source_path = self.task_list.automation_dir / parent.input_artifact
                if source_path.exists():
                    source_artifact = str(source_path.absolute())
                    context_files.append(("Original Source Data", source_artifact))
        
        spec_file_abs = str(spec_file.absolute())
        
        # Build context file section for prompt
        context_section = ""
        for label, path in context_files:
            context_section += f"\n{label}: {path}"
        
        prompt = f"""Write a technical specification for an SEO fix.

PROJECT: {self.project.website_id}
TASK: {task.title}
OUTPUT_FILE: {spec_file_abs}
{context_section}

INSTRUCTIONS:
1. Read the CONTEXT_FILE(s) above
2. Write a complete specification to OUTPUT_FILE using WriteFile tool
3. The specification should be markdown format with these sections:
   - # Specification: [title]
   - ## Problem
   - ## Root Cause
   - ## Solution
   - ## Implementation Steps
   - ## Files to Modify
   - ## Acceptance Criteria

REQUIREMENTS:
- Be SPECIFIC with file paths
- Include code examples where helpful
- Make it actionable for a developer
- Include a "## Data Sources" section listing the full paths to all referenced files
- Use WriteFile tool to save directly to OUTPUT_FILE

Write the specification now."""
        
        console.print("[dim]Agent writing specification...[/dim]")
        console.print("[dim]This may take 2-3 minutes. Press Ctrl+C to cancel.[/dim]\n")
        
        try:
            start_time = time.time()
            
            # Run with progress spinner
            result = [None]
            exception = [None]
            done = threading.Event()
            
            def worker():
                try:
                    result[0] = self.run_kimi_agent(prompt, timeout=180)
                except Exception as e:
                    exception[0] = e
                finally:
                    done.set()
            
            thread = threading.Thread(target=worker)
            thread.start()
            
            with Status("[dim]Writing specification...[/dim]", console=console, spinner="dots") as status:
                while not done.wait(timeout=0.1):
                    elapsed = time.time() - start_time
                    status.update(f"[dim]Writing specification... ({elapsed:.0f}s elapsed)[/dim]")
            
            if exception[0]:
                raise exception[0]
            
            success, output = result[0]
            
            # Check if file was created
            if spec_file.exists() and spec_file.stat().st_mtime > start_time:
                content = spec_file.read_text()
                
                task.spec_file = str(spec_file.relative_to(self.task_list.automation_dir))
                task.implementation_mode = "spec"
                task.status = "done"
                task.completed_at = datetime.now().isoformat()
                self.task_list.save()
                
                console.print(f"[green]✓ Specification written to: {spec_file}[/green]")
                
                # Show preview
                console.print("\n[dim]Preview:[/dim]")
                preview_lines = content.split('\n')[:25]
                for line in preview_lines:
                    console.print(f"  {line[:80]}")
                if len(content.split('\n')) > 25:
                    console.print("  ...")
                
                return True
            else:
                # File wasn't created - fallback to stdout parsing
                if output and "#" in output:
                    # Extract markdown content
                    for marker in ["# Specification:", "# Spec:", "## Problem", "## Solution"]:
                        idx = output.find(marker)
                        if idx != -1:
                            line_start = output.rfind('\n', 0, idx) + 1
                            content = output[line_start if line_start > 0 else idx:]
                            
                            # Clean up
                            if content.startswith("```markdown"):
                                content = content[11:]
                            elif content.startswith("```"):
                                content = content[3:]
                            if content.endswith("```"):
                                content = content[:-3]
                            content = content.strip()
                            
                            if content and len(content) > 100:
                                spec_file.write_text(content)
                                
                                task.spec_file = str(spec_file.relative_to(self.task_list.automation_dir))
                                task.implementation_mode = "spec"
                                task.status = "done"
                                task.completed_at = datetime.now().isoformat()
                                self.task_list.save()
                                
                                console.print(f"[green]✓ Specification saved from output[/green]")
                                return True
                
                console.print("[red]✗ No specification content generated[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
    
    def _write_landing_page_specification(self, task: Task) -> bool:
        """Write a detailed landing page specification."""
        # Create specs directory
        specs_dir = self.task_list.automation_dir / "specs"
        specs_dir.mkdir(exist_ok=True)
        
        # Generate slug from task title/keyword
        keyword = task.title.replace("Landing page: ", "").strip()
        slug = keyword.lower().replace(" ", "_").replace("-", "_")[:40]
        spec_file = specs_dir / f"landing_page_{slug}.md"
        
        # Read research context if available
        research_context = ""
        if task.input_artifact:
            try:
                import json
                context_path = self.task_list.automation_dir / task.input_artifact
                if context_path.exists():
                    with open(context_path) as f:
                        research_data = json.load(f)
                        # Find the specific candidate for this keyword
                        candidates = research_data.get("landing_page_candidates", [])
                        for c in candidates:
                            if c.get("keyword") == keyword:
                                research_context = json.dumps(c, indent=2)
                                break
            except:
                pass
        
        # Get metadata
        metadata = getattr(task, 'metadata', {}) or {}
        landing_page_type = metadata.get('landing_page_type', 'use_case')
        value_prop = metadata.get('value_prop', '')
        target_audience = metadata.get('target_audience', '')
        volume = metadata.get('volume', '')
        kd = metadata.get('kd', '')
        
        spec_file_abs = str(spec_file.absolute())
        
        prompt = f"""Write a comprehensive landing page specification for {self.project.website_id}.

TASK: {task.title}
KEYWORD: {keyword}
LANDING PAGE TYPE: {landing_page_type}
SEARCH VOLUME: {volume}
KEYWORD DIFFICULTY: {kd}

RESEARCH DATA:
{research_context}

OUTPUT_FILE: {spec_file_abs}

## SPECIFICATION TEMPLATE

Write a complete landing page specification using this structure:

```markdown
# Landing Page Specification: [Descriptive Page Title]

## Target Keyword
{keyword}

## Search Intent
- **Type**: [transactional/commercial/comparison - choose one]
- **User Goal**: [What the user is trying to achieve when searching this keyword]
- **Conversion Goal**: [What we want them to do - sign up, request demo, etc.]

## Page Strategy

### Positioning
[How this page positions the product relative to the keyword intent]

### Key Value Propositions
1. [Primary value prop - why choose this solution]
2. [Secondary value prop]
3. [Tertiary value prop]

### Target Audience
{target_audience or "[Define the specific audience segment]"}

## Page Structure

### 1. Hero Section
- **Headline (H1)**: [Must include exact keyword naturally]
- **Subheadline**: [Supporting value proposition]
- **Primary CTA**: [Button text, e.g., "Start Free Trial", "Get Started"]
- **Secondary CTA** (optional): [e.g., "View Demo", "Learn More"]
- **Visual**: [Recommended hero image/illustration description]

### 2. Problem/Solution Section
- **Problem Statement**: [The pain point this keyword represents]
- **Solution Intro**: [How the product solves it]
- **Transition**: [Bridge to features]

### 3. Key Features (3-4 features)
For each feature:
- **Name**: [Feature name]
- **Benefit**: [What it does for the user]
- **Description**: [1-2 sentences explaining the feature]

### 4. Social Proof Section
- **Type**: [testimonials/logos/stats/case studies - choose best fit]
- **Content**: [Specific social proof to include]
- **Placement**: [How to present it]

### 5. Differentiation/Comparison Section (if applicable)
- **Comparison Points**: [What to highlight vs alternatives]
- **Our Advantage**: [Why we're better]
- **Visual**: [Table, checklist, or feature comparison]

### 6. FAQ Section (2-3 questions)
Include questions that:
- Address common objections
- Include keyword variants naturally
- Lead toward conversion

Example:
- **Q**: [Question including keyword]
- **A**: [Helpful answer that positions product]

### 7. Final CTA Section
- **Headline**: [Urgency or benefit-focused headline]
- **Supporting text**: [Remove friction/address hesitation]
- **CTA Button**: [Action-oriented, e.g., "Get Started Free"]

## SEO Requirements

### Title Tag
[50-60 characters, include keyword near beginning]

### Meta Description
[150-160 characters, include keyword + compelling CTA]

### URL Slug
/[recommended-slug-with-keyword]

### Header Structure
- H1: [Primary headline with keyword]
- H2s: [Section headings]

### Internal Linking
- **Link to**: [Related pages on the site to link to]
- **Link from**: [Existing pages that should link to this landing page]

## Content Guidelines

### Tone and Voice
[Professional/friendly/technical/approachable - match brand]

### Messaging Do's
- [What messaging approaches to use]
- [Benefit-focused language]

### Messaging Don'ts
- [What to avoid]
- [Overpromising, jargon, etc.]

## Design and Technical Notes

### Layout Recommendations
- [Single column vs multi-column suggestions]
- [Mobile considerations]

### Visual Elements Needed
- [Icons, illustrations, screenshots, etc.]

### Interactive Elements
- [Forms, calculators, demos, etc.]

## Conversion Optimization

### Primary Conversion Action
[What counts as a conversion on this page]

### Conversion Support Elements
- [Trust signals to include]
- [Objection handlers]
- [Urgency/scarcity (if appropriate)]

### Tracking Requirements
- [Events to track]
- [Goals to set up]

## Acceptance Criteria
- [ ] All sections have complete content guidance
- [ ] Keyword appears in H1, title tag, meta description, and first paragraph
- [ ] At least 2 CTAs present (primary + secondary or repeated)
- [ ] Mobile-responsive design specified
- [ ] Page speed considerations noted
- [ ] Conversion tracking requirements defined
- [ ] Internal linking strategy defined

## Implementation Notes
[Any special considerations for the dev team implementing this page]
```

## REQUIREMENTS

1. Use the WriteFile tool to save the specification to OUTPUT_FILE
2. Be SPECIFIC with all recommendations - this is a blueprint for implementation
3. Tailor the specification to the LANDING PAGE TYPE:
   - **alternative**: Focus on comparison, migration path, why switch
   - **use_case**: Focus on specific workflow/job-to-be-done
   - **category**: Focus on feature comparison, best-of positioning
   - **comparison**: Focus on head-to-head feature/benefit comparison
   - **feature**: Focus on capability demonstration, technical details
4. Include REALISTIC examples, not placeholders
5. Consider the target keyword's search intent throughout

Write the complete specification now."""
        
        console.print("\n[dim]Agent writing landing page specification...[/dim]")
        console.print("[dim]This may take 3-5 minutes. Press Ctrl+C to cancel.[/dim]\n")
        
        try:
            import threading
            from rich.status import Status
            
            start_time = time.time()
            
            # Run with progress spinner
            result = [None]
            exception = [None]
            done = threading.Event()
            
            def worker():
                try:
                    result[0] = self.run_kimi_agent(prompt, timeout=300)
                except Exception as e:
                    exception[0] = e
                finally:
                    done.set()
            
            thread = threading.Thread(target=worker)
            thread.start()
            
            with Status("[dim]Writing specification...[/dim]", console=console, spinner="dots") as status:
                while not done.wait(timeout=0.1):
                    elapsed = time.time() - start_time
                    status.update(f"[dim]Writing specification... ({elapsed:.0f}s elapsed)[/dim]")
            
            if exception[0]:
                raise exception[0]
            
            success, output = result[0]
            
            # Check if file was created
            if spec_file.exists() and spec_file.stat().st_mtime > start_time:
                content = spec_file.read_text()
                
                task.spec_file = str(spec_file.relative_to(self.task_list.automation_dir))
                task.implementation_mode = "spec"
                task.status = "done"
                task.completed_at = datetime.now().isoformat()
                self.task_list.save()
                
                console.print(f"[green]✓ Landing page specification written to: {spec_file}[/green]")
                
                # Show preview
                console.print("\n[dim]Preview:[/dim]")
                preview_lines = content.split('\n')[:25]
                for line in preview_lines:
                    console.print(f"  {line[:80]}")
                if len(content.split('\n')) > 25:
                    console.print("  ...")
                
                console.print(f"\n[bold cyan]Next Steps:[/bold cyan]")
                console.print(f"  1. Review specification (press 'v' to view specs)")
                console.print(f"  2. Open project in dev context")
                console.print(f"  3. Implement landing page from specification")
                console.print(f"  4. Mark task as done when complete")
                
                return True
            else:
                # File wasn't created - try to extract from output
                if output and "#" in output:
                    for marker in ["# Landing Page Specification:", "# Specification:", "## Target Keyword"]:
                        idx = output.find(marker)
                        if idx != -1:
                            line_start = output.rfind('\n', 0, idx) + 1
                            content = output[line_start if line_start > 0 else idx:]
                            
                            if content.startswith("```markdown"):
                                content = content[11:]
                            elif content.startswith("```"):
                                content = content[3:]
                            if content.endswith("```"):
                                content = content[:-3]
                            content = content.strip()
                            
                            if content and len(content) > 100:
                                spec_file.write_text(content)
                                
                                task.spec_file = str(spec_file.relative_to(self.task_list.automation_dir))
                                task.implementation_mode = "spec"
                                task.status = "done"
                                task.completed_at = datetime.now().isoformat()
                                self.task_list.save()
                                
                                console.print(f"[green]✓ Specification saved from output[/green]")
                                console.print(f"[dim]Location: {spec_file}[/dim]")
                                return True
                
                console.print("[red]✗ No specification content generated[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
    
    def run(self, task: Task) -> bool:
        """Execute an implementation task via appropriate handler."""
        execution_mode = self._get_execution_mode(task.type)
        
        # Show execution mode
        mode_labels = {
            "direct": ("[green]Direct[/green]", "Agent will write content directly"),
            "spec": ("[yellow]Specification[/yellow]", "Agent will create a specification"),
            "workflow": ("[blue]Workflow[/blue]", "Running specialized workflow"),
            "auto": ("[dim]Auto-detect[/dim]", "Agent will determine best approach"),
        }
        mode_label, mode_desc = mode_labels.get(execution_mode, ("[dim]Unknown[/dim]", ""))
        
        console.print(f"\n[bold]Task:[/bold] {task.title}")
        console.print(f"[dim]Type:[/dim] {task.type}")
        console.print(f"[dim]Mode:[/dim] {mode_label} - {mode_desc}")
        
        # If already determined to be spec-based
        if execution_mode == "spec" and task.spec_file:
            console.print(f"\n[bold]Specification Task: {task.title}[/bold]")
            console.print("[yellow]This task requires structural changes.[/yellow]")
            console.print(f"[dim]Specification: {task.spec_file}[/dim]")
            console.print("\n[dim]Open in dev context to implement.[/dim]")
            return True
        
        # DIRECT CONTENT TASKS
        if execution_mode == "direct":
            return self.runners["content"].run(task)
        
        # SPEC TASKS
        if execution_mode == "spec":
            if task.type == "landing_page_spec":
                return self._write_landing_page_specification(task)
            return self._write_specification(task)
        
        # WORKFLOW TASKS
        workflow_handlers = {
            "cluster_and_link": self.runners["linking"],
            "content_cleanup": self.runners["cleanup"],
            "publish_content": self.runners["publishing"],
            "indexing_diagnostics": self.runners["indexing"],
        }
        
        if task.type in workflow_handlers:
            return workflow_handlers[task.type].run(task)
        
        # AUTO - Agent decides
        console.print(f"\n[bold]Analyzing: {task.title}[/bold]")
        console.print("[dim]Agent determining best implementation approach...[/dim]\n")
        
        decision, reasoning = self._get_agent_decision(task)
        
        console.print(f"[bold]Decision:[/bold] {decision.upper()}")
        console.print(f"[dim]{reasoning}[/dim]\n")
        
        if decision == "specification":
            success = self._write_specification(task)
            if success:
                console.print(f"\n[bold cyan]Next Steps:[/bold cyan]")
                console.print(f"  1. Review specification (press 'v' to view)")
                console.print(f"  2. Open project in dev context")
                console.print(f"  3. Implement from specification")
                console.print(f"  4. Mark task as done when complete")
            return success
        
        elif decision == "investigation":
            console.print("[yellow]Agent needs more information to decide.[/yellow]")
            console.print("[dim]Consider running an investigation task first.[/dim]")
            return False
        
        # Direct implementation fallback
        console.print(f"[green]✓ Direct implementation appropriate[/green]")
        console.print(f"\n[bold]Implementing: {task.title}[/bold]")
        
        # Read context if available
        context = ""
        if task.input_artifact:
            try:
                import json
                context_path = self.task_list.automation_dir / task.input_artifact
                if context_path.exists():
                    with open(context_path) as f:
                        context_data = json.load(f)
                        context = f"\nCONTEXT:\n{json.dumps(context_data, indent=2)[:800]}"
            except:
                pass
        
        prompt = f"""You are implementing a fix for {self.project.website_id}.

TASK: {task.title}
{context}

Your job:
1. Read relevant files
2. Implement the fix
3. Test changes
4. Document what you did

Be specific. Actually make changes.
"""
        
        console.print("\n[dim]Running Kimi agent...[/dim]\n")
        
        try:
            success, output = self.run_kimi_agent(prompt, timeout=300)
            
            if output:
                console.print(output[-2000:] if len(output) > 2000 else output)
            
            task.status = "done"
            task.completed_at = datetime.now().isoformat()
            self.task_list.save()
            console.print(f"\n[green]✓ Task completed[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
