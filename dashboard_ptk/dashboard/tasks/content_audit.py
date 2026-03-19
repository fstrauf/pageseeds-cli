"""
Content audit task runner.

Runs a fully deterministic batch audit of all published articles:
no LLM, no external API — just file parsing and check scoring.
Writes content_audit.json and prints a ranked summary table.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.status import Status

from ..models import Task
from .base import TaskRunner

console = Console()


class ContentAuditRunner(TaskRunner):
    """Runs the deterministic batch content audit workflow."""

    def run(self, task: Task) -> bool:
        if task.type == "content_audit":
            return self._run_content_audit(task)
        return False

    def _find_workspace_dir(self) -> str:
        repo_root = Path(self.project.repo_root)
        for candidate in ("automation", ".github/automation"):
            if (repo_root / candidate / "articles.json").exists():
                return candidate
        return "automation"

    def _run_content_audit(self, task: Task) -> bool:
        console.print("\n[bold]Content Audit[/bold]")
        console.print(
            "[dim]Runs deterministic checks on every published article — "
            "no LLM required. Writes a ranked content_audit.json.[/dim]\n"
        )

        repo_root = Path(self.project.repo_root)
        workspace_dir = self._find_workspace_dir()

        cmd = [
            "seo",
            "content-audit",
            "--repo-root", str(repo_root),
            "--workspace-dir", workspace_dir,
        ]

        console.print("[dim]Auditing all published articles...[/dim]")

        result: list = [None]
        done = threading.Event()

        def _worker():
            result[0] = self.run_cli_command(cmd, timeout=120)
            done.set()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        start = time.time()
        with Status(
            "[dim]Checking articles...[/dim]", console=console, spinner="dots"
        ) as status:
            while not done.wait(timeout=0.1):
                elapsed = time.time() - start
                status.update(f"[dim]Checking articles... ({elapsed:.0f}s)[/dim]")

        success, stdout, stderr = result[0]

        if not success:
            console.print("[red]✗ Content audit failed[/red]")
            if stderr:
                console.print(f"[dim]{stderr[:3000]}[/dim]")
            return False

        # Parse and display result summary
        data: dict = {}
        try:
            data = json.loads(stdout)
            total = data.get("total_audited", "?")
            health = data.get("health_summary", {})
            good = health.get("good", 0)
            needs_work = health.get("needs_improvement", 0)
            poor = health.get("poor", 0)
            console.print(
                f"[green]✓ Audit complete[/green] "
                f"[dim]({total} articles: {good} good, {needs_work} needs work, {poor} poor)[/dim]"
            )
            # Show top 5 priority articles
            articles = data.get("articles", [])
            if articles:
                console.print("\n[bold dim]Top priority articles:[/bold dim]")
                for i, a in enumerate(articles[:5], 1):
                    health_icon = {"good": "✓", "needs_improvement": "⚠", "poor": "✗"}.get(
                        a.get("health", ""), "?"
                    )
                    title = (a.get("title") or a.get("url_slug") or "")[:55]
                    failed = a.get("checks_failed", 0)
                    score = a.get("health_score", 0)
                    console.print(
                        f"  {i}. {health_icon} [dim]{title}[/dim]  "
                        f"[dim]score={score} failed={failed}[/dim]"
                    )
            out_path = (
                Path(self.project.repo_root) / workspace_dir / "content_audit.json"
            )
            console.print(f"\n[dim]Full report: {out_path}[/dim]")
        except Exception:
            console.print("[green]✓ Audit complete[/green]")

        task.status = "done"
        task.completed_at = datetime.now().isoformat()
        self.task_list.save()

        # Generate consolidated spec file + spec task
        try:
            self._generate_spec(data, workspace_dir)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow]⚠ Spec generation failed: {exc}[/yellow]")

        return True

    # ------------------------------------------------------------------ #
    # Spec generation                                                      #
    # ------------------------------------------------------------------ #

    _PRIORITY_LABEL = {
        "poor": "🔴 CRITICAL",
        "needs_improvement": "🟠 HIGH",
    }

    def _generate_spec(self, data: dict, workspace_dir: str) -> None:
        """Write a spec markdown file and a spec task for every article that
        needs work.  Pure-Python — no LLM required."""
        articles = data.get("articles", [])
        actionable = [
            a for a in articles
            if a.get("health") != "good" and a.get("checks_failed", 0) > 0
        ]

        if not actionable:
            console.print("[dim]All articles healthy — no spec generated.[/dim]")
            return

        date_str = datetime.now().strftime("%Y-%m-%d")
        total = data.get("total_audited", len(articles))
        health_summary = data.get("health_summary", {})
        good = health_summary.get("good", 0)
        needs_work = health_summary.get("needs_improvement", 0)
        poor = health_summary.get("poor", 0)

        critical_total = sum(a.get("critical_issues", 0) for a in actionable)
        high_total = sum(a.get("high_issues", 0) for a in actionable)

        lines: list[str] = [
            f"# Content Audit Fixes — {date_str} ({len(actionable)} articles)",
            "",
            "## Summary",
            "",
            f"- **{total} articles audited** — {good} good, {needs_work} needs improvement, {poor} poor",
            f"- **Actionable articles:** {len(actionable)}",
            f"- **Critical check failures:** {critical_total}",
            f"- **High check failures:** {high_total}",
            "",
            "## Priority Fixes",
            "",
        ]

        for article in actionable:
            hlabel = self._PRIORITY_LABEL.get(article.get("health", ""), "⚪ MEDIUM")
            title = article.get("title") or article.get("url_slug") or "(untitled)"
            file_ref = article.get("file") or "(file unknown)"
            keyword = article.get("target_keyword") or "(no keyword set)"
            score = article.get("health_score", "?")

            lines += [
                f"### {hlabel} — {title}",
                "",
                f"**File:** `{file_ref}`  ",
                f"**Keyword:** `{keyword}`  ",
                f"**Health score:** {score}/100",
                "",
                "#### Fixes required",
                "",
            ]

            checks = article.get("checks", {})
            for check_key, check in checks.items():
                if check.get("pass") is not False:
                    continue
                label = check.get("label", check_key)
                value = check.get("value")
                issues = check.get("issues", [])

                line = f"- [ ] **{label}**"
                if value is not None and check_key != "broken_links":
                    line += f" (current: {value})"
                lines.append(line)

                if issues:
                    for issue in issues[:5]:
                        href = issue.get("href", "")
                        text = issue.get("text", "")
                        lines.append(f"  - `{href}` — {text}")
                    if len(issues) > 5:
                        lines.append(f"  - …and {len(issues) - 5} more")

            lines.append("")

        lines += [
            "## Acceptance Criteria",
            "",
            "- [ ] All 🔴 CRITICAL articles resolve their highest-weight failures.",
            "- [ ] No broken/placeholder TODO links remain in published articles.",
            "- [ ] Re-run `automation-cli seo content-audit` — no articles in **poor** health.",
            "",
        ]

        spec_content = "\n".join(lines)

        # Create the spec task to get its auto-generated ID
        new_task = self.task_list.create_task(
            task_type="technical_fix",
            title=f"Content Audit Fixes — {date_str}",
            phase="implementation",
            priority="high",
            execution_mode="manual",
            implementation_mode="spec",
        )

        # Write spec file using the task ID
        specs_dir = Path(self.project.repo_root) / workspace_dir / "specs"
        specs_dir.mkdir(exist_ok=True)
        spec_filename = f"{new_task.id}_spec.md"
        spec_path = specs_dir / spec_filename
        spec_path.write_text(spec_content)

        # Point task at spec file and set to review
        new_task.spec_file = f"specs/{spec_filename}"
        new_task.status = "review"
        self.task_list.save()

        console.print(
            f"\n[green]✓ Spec task created:[/green] [bold]{new_task.id}[/bold] — {new_task.title}"
        )
        console.print(f"[dim]  {spec_path}[/dim]")
        console.print("[dim]  Press 'v' from dashboard to view, then implement fixes.[/dim]")
