"""
Research tasks - find content opportunities
"""
import json
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..models import Task
from .base import TaskRunner

console = Console()


class ResearchRunner(TaskRunner):
    """Runs research tasks."""
    
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
        with Status("[dim]Researching...[/dim]", console=console, spinner="dots") as status:
            while not done.wait(timeout=0.1):
                elapsed = time.time() - start_time
                status.update(f"[dim]Researching... ({elapsed:.0f}s elapsed)[/dim]")
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    def run(self, task: Task) -> bool:
        """Execute a research task via agent."""
        # Skip Reddit tasks - handled by RedditRunner
        if task.type.startswith("reddit_"):
            return False
        
        # Handle custom keyword research with agentic tool calling
        if task.type == "custom_keyword_research":
            return self._run_agentic_keyword_research(task)
        
        # Handle landing page keyword research
        if task.type == "research_landing_pages":
            return self._run_landing_page_research(task)
        
        console.print(f"\n[bold]Researching: {task.title}[/bold]")
        
        result_dir = self.task_list.task_results_dir / task.id
        result_dir.mkdir(parents=True, exist_ok=True)
        
        prompt = f"""You are researching for {self.project.website_id}.

TASK: {task.title}

READ: Existing content in {self.project.repo_root}/.github/automation/
RESEARCH: Find long-tail keyword opportunities, content gaps, analyze competitors

## LONG-TAIL KEYWORD CRITERIA (Prioritize these):
- **Keyword Difficulty (KD)**: Target LOW (ideally <30, max 40)
- **Search Volume**: Minimum 100-500 monthly searches (indicates real demand)
- **Specificity**: 3-5 word phrases (e.g., "best options strategy for beginners" not just "options strategy")
- **Search Intent**: Clear problem/question being asked
- **Competition Gap**: Weak existing content OR your site can rank better

## RESEARCH PROCESS:
1. Analyze existing content - what do you already cover?
2. Identify content gaps - what are you missing?
3. Use tools/search to find long-tail keywords matching criteria above
4. **RANK keywords by opportunity score** (volume/KD ratio)
5. **SELECT TOP 8-10** - present variety for user selection

## OUTPUT STRUCTURE:
{{
  "summary": "Key findings - existing content analysis, gap analysis, competitor landscape",
  
  "keyword_candidates": [
    {{
      "keyword": "exact long-tail keyword phrase",
      "estimated_volume": "monthly searches (number or 'low/medium/high')",
      "estimated_kd": "keyword difficulty 0-100 (number or 'low/medium/high')",
      "intent": "informational|transactional|navigational",
      "opportunity_score": "high|medium|low",
      "opportunity_reason": "Brief explanation of why this is a good opportunity",
      "competition": "who ranks now and their content quality",
      "proposed_title": "Suggested article title based on keyword"
    }}
  ],
  
  "optimize_candidates": [
    {{
      "page": "path/to/existing/page",
      "target_keyword": "keyword to optimize for",
      "improvements": ["specific improvement 1", "specific improvement 2"],
      "potential_impact": "high|medium|low"
    }}
  ],
  
  "strategy_notes": "Any complex planning recommendations"
}}

## IMPORTANT RULES:
1. **Find 8-10 keyword candidates** - give the user options to choose from
2. **Each candidate MUST have a clear, specific long-tail keyword**
3. **Prioritize keywords with LOW difficulty + REAL search volume**
4. **Include opportunity_reason** - why this keyword is worth pursuing
5. **Suggest a title** for each candidate article
6. Present variety - don't make all candidates too similar
7. Be realistic about KD estimates - better to under-promise

WRITE: Save to {result_dir}/research.json
"""
        
        console.print("\n[dim]Running research agent...[/dim]")
        console.print("[dim]This may take 3-5 minutes. Press Ctrl+C to cancel.[/dim]\n")
        
        try:
            success, output = self._run_with_progress(
                self.run_kimi_agent, prompt, timeout=600
            )
            
            if output:
                console.print(output[-2000:] if len(output) > 2000 else output)
            
            research_file = result_dir / "research.json"
            if research_file.exists():
                console.print(f"\n[green]✓ Research saved[/green]")
                
                # Parse research results and let user select keywords
                try:
                    research_data = json.loads(research_file.read_text())
                    
                    keyword_candidates = research_data.get("keyword_candidates", [])
                    optimize_candidates = research_data.get("optimize_candidates", [])
                    
                    if not keyword_candidates:
                        console.print("[yellow]No keyword candidates found in research[/yellow]")
                        task.status = "done"
                        task.result_path = str(result_dir.relative_to(self.task_list.automation_dir))
                        return True
                    
                    # Display keyword candidates table
                    console.print("\n")
                    table = Table(title=f"📊 Keyword Opportunities for {self.project.website_id}", show_header=True)
                    table.add_column("#", style="cyan", justify="center", width=3)
                    table.add_column("Keyword", style="bright_white", min_width=30)
                    table.add_column("Volume", justify="right", width=8)
                    table.add_column("KD", justify="right", width=6)
                    table.add_column("Opp", justify="center", width=5)
                    table.add_column("Intent", width=12)
                    
                    for i, kw in enumerate(keyword_candidates[:10], 1):
                        vol = str(kw.get('estimated_volume', '-'))[:7]
                        kd = str(kw.get('estimated_kd', '-'))[:5]
                        opp = kw.get('opportunity_score', '-')
                        opp_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(opp.lower(), "⚪")
                        intent = kw.get('intent', '-')
                        table.add_row(
                            str(i),
                            kw.get('keyword', 'N/A'),
                            vol,
                            kd,
                            opp_emoji,
                            intent
                        )
                    
                    console.print(table)
                    
                    # Show detailed view for each candidate
                    console.print("\n[bold]Candidate Details:[/bold]")
                    for i, kw in enumerate(keyword_candidates[:10], 1):
                        title = kw.get('proposed_title', f"Article about {kw.get('keyword', 'topic')}")
                        reason = kw.get('opportunity_reason', 'Good opportunity')
                        panel = Panel(
                            f"[dim]{title}[/dim]\n[italic]{reason}[/italic]",
                            title=f"[{i}] {kw.get('keyword', 'N/A')}",
                            border_style="green" if kw.get('opportunity_score', '').lower() == 'high' else "yellow"
                        )
                        console.print(panel)
                    
                    # Interactive selection
                    console.print("\n[bold cyan]Select keywords to create article tasks:[/bold cyan]")
                    console.print("Enter numbers (1-10) separated by commas, or 'all' for all, or 'none' to skip")
                    console.print("Examples: '1,3,5' or '2,4' or 'all'")
                    
                    selection = console.input("\n[bold]Your selection:[/bold] ").strip().lower()
                    
                    selected_indices = []
                    if selection == 'all':
                        selected_indices = list(range(len(keyword_candidates[:10])))
                    elif selection == 'none' or selection == '':
                        selected_indices = []
                    else:
                        try:
                            for part in selection.split(','):
                                idx = int(part.strip()) - 1
                                if 0 <= idx < len(keyword_candidates[:10]):
                                    selected_indices.append(idx)
                        except ValueError:
                            console.print("[yellow]Invalid input, creating no tasks[/yellow]")
                    
                    # Create tasks for selected keywords
                    created_count = 0
                    created_tasks = []
                    
                    for idx in selected_indices:
                        kw = keyword_candidates[idx]
                        keyword = kw.get('keyword', f"article-{idx+1}")
                        title = kw.get('proposed_title', f"Write article: {keyword}")
                        
                        # Ensure title starts with "Write article:"
                        if not title.lower().startswith("write article"):
                            title = f"Write article: {title}"
                        
                        # Check for duplicates
                        if any(t.title == title and t.parent_task == task.id for t in self.task_list.tasks):
                            console.print(f"[dim]Skipping duplicate: {title}[/dim]")
                            continue
                        
                        new_task = self.task_list.create_task(
                            task_type="write_article",
                            title=title,
                            phase="implementation",
                            priority="high" if kw.get('opportunity_score', '').lower() == 'high' else "medium",
                            depends_on=task.id,
                            parent_task=task.id,
                            category=f"content:{keyword}",
                            input_artifact=str(research_file.relative_to(self.task_list.automation_dir)),
                            implementation_mode="direct"
                        )
                        self.task_list.save()
                        task.spawns_tasks.append(new_task.id)
                        created_count += 1
                        created_tasks.append((title, keyword))
                    
                    # Also offer to create optimization tasks
                    if optimize_candidates:
                        console.print(f"\n[bold cyan]Found {len(optimize_candidates)} optimization opportunities[/bold cyan]")
                        for i, opt in enumerate(optimize_candidates[:3], 1):
                            console.print(f"  {i}. {opt.get('page', 'N/A')} → {opt.get('target_keyword', 'N/A')}")
                        
                        opt_selection = console.input("\nSelect optimizations (1-3, comma-separated, or 'none'): ").strip().lower()
                        
                        if opt_selection != 'none' and opt_selection != '':
                            try:
                                for part in opt_selection.split(','):
                                    idx = int(part.strip()) - 1
                                    if 0 <= idx < len(optimize_candidates[:3]):
                                        opt = optimize_candidates[idx]
                                        title = f"Optimize: {opt.get('page', 'page')}"
                                        
                                        if any(t.title == title and t.parent_task == task.id for t in self.task_list.tasks):
                                            continue
                                        
                                        new_task = self.task_list.create_task(
                                            task_type="optimize_article",
                                            title=title,
                                            phase="implementation",
                                            priority=opt.get('potential_impact', 'medium'),
                                            depends_on=task.id,
                                            parent_task=task.id,
                                            category="optimization",
                                            input_artifact=str(research_file.relative_to(self.task_list.automation_dir)),
                                            implementation_mode="direct"
                                        )
                                        self.task_list.save()
                                        task.spawns_tasks.append(new_task.id)
                                        created_count += 1
                            except ValueError:
                                pass
                    
                    # Summary
                    if created_count > 0:
                        console.print(f"\n[green]✓ Created {created_count} tasks[/green]")
                        for title, keyword in created_tasks:
                            console.print(f"  [dim]• {title} ({keyword})[/dim]")
                    else:
                        console.print("\n[dim]No tasks created - research complete but no articles selected[/dim]")
                    
                except Exception as e:
                    console.print(f"[yellow]Could not process research results: {e}[/yellow]")
                
                task.status = "done"
                task.completed_at = datetime.now().isoformat()
                task.result_path = str(result_dir.relative_to(self.task_list.automation_dir))
                self.task_list.save()
                return True
            else:
                return False
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return False


    def _run_agentic_keyword_research(self, task: Task) -> bool:
        """Agentic keyword research where AI runs CLI tools directly."""
        import tempfile
        
        # Extract parameters
        metadata = getattr(task, 'metadata', {}) or {}
        raw_themes = metadata.get('custom_themes', [])
        criteria = metadata.get('custom_criteria', '')
        exclude_terms = metadata.get('exclude_terms', '')
        min_volume = metadata.get('min_volume', 100)
        max_kd = metadata.get('max_kd', 40)
        is_legacy_task = metadata.get('_migrated_legacy_task', False)
        
        full_context = "\n".join(raw_themes)
        if criteria:
            full_context += f"\n\nFocus: {criteria}"
        
        # Validate we have product context to research
        if not full_context.strip():
            # Check if this is a legacy migrated task
            if is_legacy_task:
                console.print("\n[yellow]⚠ This is a legacy task from before the schema update.[/yellow]")
                console.print("[dim]Custom keyword research tasks now require themes to be configured.[/dim]\n")
            
            error_msg = "Task has no product/context configured. Add themes/criteria to task metadata."
            console.print(f"\n[red]✗ {error_msg}[/red]")
            console.print("\n[bold cyan]To fix this task:[/bold cyan]")
            console.print("  1. Delete this task (option 'd' from task menu)")
            console.print("  2. Create a new custom keyword research task (option 'x' from task menu)")
            console.print("  3. Enter your research themes when prompted")
            console.print("\n[dim]Or: Manually edit task_list.json to add custom_themes to this task's metadata[/dim]")
            self._set_error(error_msg)
            return False
        
        console.print(f"\n[bold]Agentic Keyword Research[/bold]")
        console.print("[dim]AI will run pageseeds seo commands for real Ahrefs data...[/dim]\n")
        
        # Read the instructions file
        instructions_path = Path(__file__).parent / "keyword_research_instructions.md"
        instructions = instructions_path.read_text() if instructions_path.exists() else ""
        
        result_dir = self.task_list.task_results_dir / task.id
        result_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = tempfile.mktemp(suffix='.json')
        
        prompt = f"""{instructions}

---

PRODUCT TO RESEARCH:
{full_context[:1500]}

CRITERIA:
- Minimum volume: {min_volume}
- Maximum keyword difficulty: {max_kd}
- Exclusions: {exclude_terms or "None"}

YOUR TASK:
Run CLI commands to research keywords efficiently.

EFFICIENCY GUIDELINES:
- Use ONLY 3 seeds max (pick the most relevant ones)
- After each keyword-generator call, immediately analyze and move to next
- Select only 6-8 final candidates for difficulty analysis
- Write the file as soon as you have results

STEPS:
1. Identify 3 best seed keywords from the product
2. Run: pageseeds seo keywords --keyword "SEED" --country us
3. Collect unique keywords (check 'all' array in JSON)
4. Select 6-8 most promising (good volume + relevance)
5. Run: pageseeds seo batch-difficulty --keywords-file /tmp/kw.txt --country us
6. Write final JSON to: {output_file}

⚠️ CRITICAL: Use this exact Python code to write results:
```python
import json
result = {{"seed_keywords": [...], "total_discovered": N, "keyword_candidates": [...]}}
with open('{output_file}', 'w') as f:
    json.dump(result, f, indent=2)
```

Speed is important - don't over-analyze, just get good keywords and write the file."""
        
        console.print("[bold cyan]Running AI agent with CLI tools...[/bold cyan]")
        console.print("[dim]AI will run pageseeds seo commands directly (timeout: 10 min)[/dim]")
        console.print("[dim]This may take 3-8 minutes depending on keyword volume...[/dim]\n")
        
        try:
            # Run kimi agent - AI will execute CLI commands
            start_time = datetime.now()
            success, output = self._run_with_progress(
                self.run_kimi_agent,
                prompt,
                timeout=600,
                cwd=Path(self.project.repo_root),
            )
            elapsed = (datetime.now() - start_time).total_seconds()
            console.print(f"[dim]AI completed in {elapsed:.1f}s[/dim]")
            if not success and not output:
                error_msg = "Agent execution failed with no output"
                console.print(f"[red]✗ {error_msg}[/red]")
                self._set_error(error_msg)
                return False

            # Check if AI wrote the output file
            if not Path(output_file).exists():
                console.print("[yellow]AI did not write output file. Checking for inline results...[/yellow]")
                # Show last bit of output for debugging
                if len(output) > 500:
                    console.print("[dim]Last 500 chars of output:[/dim]")
                    console.print(output[-500:])
                json_data = self._extract_json_from_output(output)
                if json_data:
                    Path(output_file).write_text(json.dumps(json_data, indent=2))
                    console.print("[green]✓ Extracted JSON from output[/green]")
                else:
                    error_msg = "Could not find results in AI output"
                    console.print(f"[red]✗ {error_msg}[/red]")
                    self._set_error(error_msg)
                    return False
            
            # Read and process results
            research_data = json.loads(Path(output_file).read_text())
            Path(output_file).unlink(missing_ok=True)
            
            keyword_candidates = research_data.get('keyword_candidates', [])
            if not keyword_candidates:
                error_msg = "No keyword candidates found in research results"
                console.print(f"[red]✗ {error_msg}[/red]")
                self._set_error(error_msg)
                return False
            
            # Normalize KD values and opportunity scores
            for kw in keyword_candidates:
                kd = kw.get('estimated_kd', 0)
                if isinstance(kd, str):
                    try:
                        kw['estimated_kd'] = int(kd)
                    except ValueError:
                        kw['estimated_kd'] = 0
                
                if not kw.get('opportunity_score'):
                    kd = kw.get('estimated_kd', 99)
                    vol = str(kw.get('estimated_volume', ''))
                    if kd <= 10 and '1000' in vol:
                        kw['opportunity_score'] = 'high'
                    elif kd <= max_kd and ('100' in vol or '1000' in vol):
                        kw['opportunity_score'] = 'medium'
                    else:
                        kw['opportunity_score'] = 'low'
            
            # Save to standard location
            research_file = result_dir / "research.json"
            research_file.write_text(json.dumps({
                "summary": f"Agentic research found {len(keyword_candidates)} keywords",
                "seed_keywords": research_data.get('seed_keywords', []),
                "criteria_applied": criteria,
                "exclusions_applied": exclude_terms,
                "thresholds": {"min_volume": min_volume, "max_kd": max_kd},
                "keyword_candidates": keyword_candidates,
                "optimize_candidates": []
            }, indent=2))
            
            console.print(f"[green]✓ Found {len(keyword_candidates)} keyword candidates[/green]\n")
            
            # Display and prompt for selection
            self._display_keyword_results(keyword_candidates)
            self._prompt_for_selection(keyword_candidates, task, research_file)
            
            task.status = "done"
            task.completed_at = datetime.now().isoformat()
            task.result_path = str(result_dir.relative_to(self.task_list.automation_dir))
            self.task_list.save()
            return True
        except Exception as e:
            error_msg = f"Error in agentic research: {e}"
            console.print(f"[red]✗ {error_msg}[/red]")
            self._set_error(error_msg)
            return False

    def _run_landing_page_research(self, task: Task) -> bool:
        """Run landing page keyword research and create spec tasks."""
        console.print(f"\n[bold]Landing Page Keyword Research: {task.title}[/bold]")
        console.print("[dim]Finding high-intent keywords for dedicated landing pages...[/dim]\n")
        
        result_dir = self.task_list.task_results_dir / task.id
        result_dir.mkdir(parents=True, exist_ok=True)
        
        # Create specs directory for landing page specs
        specs_dir = self.task_list.automation_dir / "specs"
        specs_dir.mkdir(exist_ok=True)
        
        prompt = f"""You are researching LANDING PAGE opportunities for {self.project.website_id}.

TASK: {task.title}

READ: Existing content in {self.project.repo_root}/.github/automation/
RESEARCH: Find keywords with COMMERCIAL/TRANSACTIONAL intent suitable for dedicated landing pages

## LANDING PAGE vs BLOG ARTICLE
Landing pages are for CONVERSION, not just traffic:
- Focus: Product/solution positioning
- Intent: Transactional/commercial (user wants to buy, compare, or take action)
- Structure: Hero, value props, features, social proof, CTAs
- Goal: Convert visitors to customers

## LANDING PAGE KEYWORD CRITERIA (Prioritize these):
- **Intent**: Transactional/Commercial (NOT informational)
- **Keyword Difficulty (KD)**: Target LOW (ideally <30, max 40)
- **Search Volume**: Minimum 200 monthly searches
- **Patterns to prioritize**:
  * "best [product] for [use case]"
  * "[product] alternative" or "[competitor] alternative"
  * "[product] vs [competitor]"
  * "[category] software/tool/platform"
  * "[solution] for [audience]"
  * "compare [products]"
  * "top [category] tools"

## SKIP (Better as blog articles):
- "how to [do something]" → informational
- "what is [concept]" → informational  
- "guide to [topic]" → informational
- "tips for [activity]" → informational

## RESEARCH PROCESS (Complete in under 3 minutes):
1. **QUICK** read of existing content (30s) - just note product name, competitors, key use cases
2. **Run MAX 3 keyword research queries** using seo-cli:
   - Query 1: "[product] alternative" OR competitor alternatives
   - Query 2: "best [category] tool" OR category keywords  
   - Query 3: "[use case] software" OR use case keywords
3. **Get KD for top 5-7 keywords only** (not all results)
4. **QUICK SELECT**: Pick 8-10 with best volume/KD ratio + clear commercial intent
5. **STOP** - don't over-research, just need good candidates

## OUTPUT STRUCTURE:
{{
  "summary": "Key findings - existing content analysis, gap analysis, competitor landscape",
  
  "landing_page_candidates": [
    {{
      "keyword": "exact keyword phrase",
      "estimated_volume": "monthly searches",
      "estimated_kd": "keyword difficulty 0-100",
      "intent": "transactional|commercial|comparison",
      "landing_page_type": "alternative|use_case|category|comparison|feature",
      "opportunity_score": "high|medium|low",
      "opportunity_reason": "Why this keyword deserves a landing page",
      "competition": "Who ranks now and their landing page quality",
      "proposed_title": "Landing page title (not article)",
      "target_audience": "Specific audience segment",
      "key_value_prop": "Primary value proposition for this page"
    }}
  ],
  
  "strategy_notes": "Recommendations for landing page prioritization"
}}

## IMPORTANT RULES:
1. **Find 8-10 landing page candidates** - give the user options
2. **Each MUST have clear commercial/transactional intent**
3. **Prioritize LOW difficulty + REAL search volume + HIGH intent**
4. **Include landing_page_type** - categorize the opportunity
5. **Suggest landing page titles** (not article titles)
6. **Focus on conversion potential**, not just traffic
7. Be realistic about KD estimates

WRITE: Save to {result_dir}/research.json

## SPEED CONSTRAINTS (MANDATORY):
- MAX 3 pageseeds seo keyword research calls
- MAX 7 keyword-difficulty checks
- Total research time: under 3 minutes
- Don't analyze every competitor deeply - just note who's ranking
- Good enough > Perfect - we need candidates, not a dissertation
"""
        
        console.print("[dim]Running landing page research agent...[/dim]")
        console.print("[dim]This should take 2-3 minutes. Press Ctrl+C to cancel.[/dim]\n")
        
        try:
            success, output = self._run_with_progress(
                self.run_kimi_agent, prompt, timeout=300
            )
            
            if output:
                console.print(output[-2000:] if len(output) > 2000 else output)
            
            research_file = result_dir / "research.json"
            if not research_file.exists():
                console.print("[yellow]Research file not created[/yellow]")
                return False
            
            console.print(f"\n[green]✓ Research saved[/green]")
            
            # Parse research results and let user select keywords
            try:
                research_data = json.loads(research_file.read_text())
                candidates = research_data.get("landing_page_candidates", [])
                
                if not candidates:
                    console.print("[yellow]No landing page candidates found[/yellow]")
                    task.status = "done"
                    task.result_path = str(result_dir.relative_to(self.task_list.automation_dir))
                    return True
                
                # Display candidates table
                console.print("\n")
                table = Table(title=f"📊 Landing Page Opportunities for {self.project.website_id}", show_header=True)
                table.add_column("#", style="cyan", justify="center", width=3)
                table.add_column("Keyword", style="bright_white", min_width=25)
                table.add_column("Type", width=12)
                table.add_column("Vol", justify="right", width=8)
                table.add_column("KD", justify="right", width=5)
                table.add_column("Opp", justify="center", width=4)
                
                for i, lp in enumerate(candidates[:10], 1):
                    vol = str(lp.get('estimated_volume', '-'))[:7]
                    kd = str(lp.get('estimated_kd', '-'))[:4]
                    opp = lp.get('opportunity_score', '-')
                    opp_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(opp.lower(), "⚪")
                    lp_type = lp.get('landing_page_type', '-')[:11]
                    table.add_row(str(i), lp.get('keyword', 'N/A'), lp_type, vol, kd, opp_emoji)
                
                console.print(table)
                
                # Show detailed view for each candidate
                console.print("\n[bold]Candidate Details:[/bold]")
                for i, lp in enumerate(candidates[:10], 1):
                    title = lp.get('proposed_title', f"Landing page: {lp.get('keyword', 'topic')}")
                    reason = lp.get('opportunity_reason', 'Good opportunity')
                    value_prop = lp.get('key_value_prop', '')
                    panel_content = f"[dim]{title}[/dim]\n[italic]{reason}[/italic]"
                    if value_prop:
                        panel_content += f"\n\n[cyan]Value Prop:[/cyan] {value_prop}"
                    panel = Panel(
                        panel_content,
                        title=f"[{i}] {lp.get('keyword', 'N/A')}",
                        border_style="green" if lp.get('opportunity_score', '').lower() == 'high' else "yellow"
                    )
                    console.print(panel)
                
                # Interactive selection
                console.print("\n[bold cyan]Select landing pages to create specifications:[/bold cyan]")
                console.print("Enter numbers (1-10) separated by commas, or 'all' for all, or 'none' to skip")
                console.print("Examples: '1,3,5' or '2,4' or 'all'")
                
                selection = console.input("\n[bold]Your selection:[/bold] ").strip().lower()
                
                selected_indices = []
                if selection == 'all':
                    selected_indices = list(range(len(candidates[:10])))
                elif selection == 'none' or selection == '':
                    selected_indices = []
                else:
                    try:
                        for part in selection.split(','):
                            idx = int(part.strip()) - 1
                            if 0 <= idx < len(candidates[:10]):
                                selected_indices.append(idx)
                    except ValueError:
                        console.print("[yellow]Invalid input, creating no specs[/yellow]")
                
                # Create spec tasks for selected keywords
                created_count = 0
                created_tasks = []
                
                for idx in selected_indices:
                    lp = candidates[idx]
                    keyword = lp.get('keyword', f"lp-{idx+1}")
                    title = f"Landing page: {keyword}"
                    
                    # Check for duplicates
                    if any(t.title == title and t.parent_task == task.id for t in self.task_list.tasks):
                        console.print(f"[dim]Skipping duplicate: {title}[/dim]")
                        continue
                    
                    new_task = self.task_list.create_task(
                        task_type="landing_page_spec",
                        title=title,
                        phase="implementation",
                        priority="high" if lp.get('opportunity_score', '').lower() == 'high' else "medium",
                        depends_on=task.id,
                        parent_task=task.id,
                        category=f"landing_page:{keyword}",
                        input_artifact=str(research_file.relative_to(self.task_list.automation_dir)),
                        implementation_mode="spec",
                        metadata={
                            "keyword": keyword,
                            "landing_page_type": lp.get('landing_page_type', ''),
                            "value_prop": lp.get('key_value_prop', ''),
                            "target_audience": lp.get('target_audience', ''),
                            "volume": lp.get('estimated_volume', ''),
                            "kd": lp.get('estimated_kd', '')
                        }
                    )
                    self.task_list.save()
                    task.spawns_tasks.append(new_task.id)
                    created_count += 1
                    created_tasks.append((title, keyword))
                
                # Summary
                if created_count > 0:
                    console.print(f"\n[green]✓ Created {created_count} landing page spec tasks[/green]")
                    for title, keyword in created_tasks:
                        console.print(f"  [dim]• {title} ({keyword})[/dim]")
                else:
                    console.print("\n[dim]No landing page specs created[/dim]")
                
                task.status = "done"
                task.completed_at = datetime.now().isoformat()
                task.result_path = str(result_dir.relative_to(self.task_list.automation_dir))
                self.task_list.save()
                return True
                
            except Exception as e:
                console.print(f"[yellow]Could not process research results: {e}[/yellow]")
                return False
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return False

    def _extract_json_from_output(self, output: str) -> dict | None:
        """Extract JSON from kimi output."""
        import re
        
        # Debug: Show what we're searching
        console.print(f"[dim]Searching for JSON in {len(output)} chars of output...[/dim]")
        
        # Try code blocks with json tag
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', output, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                console.print("[dim]✓ Found JSON in ```json block[/dim]")
                return data
            except Exception as e:
                console.print(f"[dim]JSON parse error in code block: {e}[/dim]")
        
        # Try any code block containing JSON-like structure
        code_blocks = re.findall(r'```\s*(\{[\s\S]*?\})\s*```', output)
        for block in code_blocks:
            if '"keyword_candidates"' in block or '"seed_keywords"' in block:
                try:
                    data = json.loads(block)
                    console.print("[dim]✓ Found JSON in generic code block[/dim]")
                    return data
                except:
                    continue
        
        # Try to find JSON object directly (look for balanced braces)
        # Search for patterns that look like our expected JSON
        patterns = [
            r'(\{\s*"seed_keywords"\s*:\s*\[[^\]]*\][\s\S]*?"keyword_candidates"[\s\S]*?\}\s*\])',
            r'(\{[\s\S]*?"keyword_candidates"[\s\S]*?\}(?=\s*$|\s*\n\s*\n))',
            r'(\{[\s\S]*?"seed_keywords"[\s\S]*?"keyword_candidates"[\s\S]*?\})',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, output, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    if 'keyword_candidates' in data:
                        console.print("[dim]✓ Found JSON via pattern matching[/dim]")
                        return data
                except:
                    continue
        
        # Last resort: try to find any JSON object with keyword_candidates
        brace_count = 0
        start_idx = -1
        for i, char in enumerate(output):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx >= 0:
                    json_str = output[start_idx:i+1]
                    if '"keyword_candidates"' in json_str:
                        try:
                            data = json.loads(json_str)
                            console.print("[dim]✓ Found JSON by brace counting[/dim]")
                            return data
                        except:
                            pass
                    start_idx = -1
        
        console.print("[yellow]Could not extract JSON from output[/yellow]")
        
        # Debug: Save output for inspection
        debug_file = Path(f"/tmp/kimi_debug_{datetime.now().strftime('%H%M%S')}.txt")
        debug_file.write_text(output[-5000:])  # Last 5000 chars
        console.print(f"[dim]Debug output saved to: {debug_file}[/dim]")
        
        return None



    def _display_keyword_results(self, candidates: list[dict]):
        """Display keyword results in a table."""
        from rich.table import Table
        
        console.print("\n")
        table = Table(title="📊 Keyword Research Results", show_header=True)
        table.add_column("#", style="cyan", justify="center", width=3)
        table.add_column("Keyword", style="bright_white", min_width=30)
        table.add_column("Volume", justify="right", width=10)
        table.add_column("KD", justify="right", width=6)
        table.add_column("Opp", justify="center", width=5)
        
        for i, kw in enumerate(candidates[:12], 1):
            vol = str(kw.get('estimated_volume', '-'))
            kd = str(kw.get('estimated_kd', '-'))
            opp = kw.get('opportunity_score', '-')
            opp_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(opp.lower(), "⚪")
            table.add_row(str(i), kw.get('keyword', 'N/A'), vol, kd, opp_emoji)
        
        console.print(table)

    def _prompt_for_selection(self, candidates: list[dict], task: Task, research_file: Path):
        """Prompt user to select keywords and create tasks."""
        from rich.panel import Panel
        
        console.print("\n[bold]Candidate Details:[/bold]")
        for i, kw in enumerate(candidates[:12], 1):
            title = kw.get('proposed_title', '')
            reason = kw.get('opportunity_reason', '')
            panel = Panel(
                f"[dim]{title}[/dim]\n[italic]{reason}[/italic]",
                title=f"[{i}] {kw.get('keyword', 'N/A')}",
                border_style="green" if kw.get('opportunity_score', '').lower() == 'high' else "yellow"
            )
            console.print(panel)
        
        console.print("\n[bold cyan]Select keywords to create article tasks:[/bold cyan]")
        console.print("Enter numbers (1-12) separated by commas, or 'all' for all, or 'none' to skip")
        
        selection = console.input("\n[bold]Your selection:[/bold] ").strip().lower()
        
        selected_indices = []
        if selection == 'all':
            selected_indices = list(range(len(candidates[:12])))
        elif selection not in ('none', ''):
            try:
                selected_indices = [int(x.strip()) - 1 for x in selection.split(',') 
                                  if 0 <= int(x.strip()) - 1 < len(candidates[:12])]
            except ValueError:
                console.print("[yellow]Invalid input, creating no tasks[/yellow]")
        
        created_count = 0
        for idx in selected_indices:
            kw = candidates[idx]
            keyword = kw.get('keyword', f"article-{idx+1}")
            title = f"Write article: {keyword}"
            
            if any(t.title == title and t.parent_task == task.id for t in self.task_list.tasks):
                continue
            
            new_task = self.task_list.create_task(
                task_type="write_article",
                title=title,
                phase="implementation",
                priority="high" if kw.get('opportunity_score', '').lower() == 'high' else "medium",
                depends_on=task.id,
                parent_task=task.id,
                category=f"content:{keyword}",
                input_artifact=str(research_file.relative_to(self.task_list.automation_dir)),
                implementation_mode="direct"
            )
            self.task_list.save()
            task.spawns_tasks.append(new_task.id)
            created_count += 1
        
        if created_count > 0:
            console.print(f"\n[green]✓ Created {created_count} tasks[/green]")
        else:
            console.print("\n[dim]No tasks created[/dim]")
