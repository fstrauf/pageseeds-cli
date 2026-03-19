"""
Clustering and internal linking tasks
"""
import json
from pathlib import Path

from rich.console import Console

from ..config import get_repo_root
from ..models import Task
from .base import TaskRunner

console = Console()


class LinkingRunner(TaskRunner):
    """Runs clustering and internal linking tasks."""
    WORKSPACE_ROOT = ".github/automation"
    WEBSITE_PATH = "."
    LINK_MODE = "related-section"

    def _run_json_command(self, cmd: list[str], cwd: Path, step: str, timeout: int = 300) -> dict:
        """Run a deterministic CLI command and parse JSON output."""
        success, stdout, stderr = self.run_cli_command(cmd, cwd=cwd, timeout=timeout)
        if not success:
            detail = (stderr or stdout or "unknown error").strip()
            raise RuntimeError(f"{step} failed: {detail[:500]}")
        try:
            return json.loads(stdout or "{}")
        except json.JSONDecodeError as exc:
            snippet = (stdout or "").strip()[:300]
            raise RuntimeError(f"{step} returned invalid JSON: {exc}. Output: {snippet}") from exc

    @staticmethod
    def _to_int(value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _build_link_map(self, items: list[dict], article_id: int | None) -> dict[int, list[int]]:
        """Group missing links by source article, optionally scoped to one article."""
        grouped: dict[int, set[int]] = {}
        for item in items:
            source_id = self._to_int(item.get("source_id"))
            target_id = self._to_int(item.get("target_id"))
            if source_id is None or target_id is None:
                continue
            if article_id is not None and source_id != article_id and target_id != article_id:
                continue
            grouped.setdefault(source_id, set()).add(target_id)
        return {source: sorted(targets) for source, targets in grouped.items()}

    def _count_scoped_missing(self, items: list[dict], article_id: int | None) -> int:
        if article_id is None:
            return len(items)
        count = 0
        for item in items:
            source_id = self._to_int(item.get("source_id"))
            target_id = self._to_int(item.get("target_id"))
            if source_id is None or target_id is None:
                continue
            if source_id == article_id or target_id == article_id:
                count += 1
        return count

    def _apply_links(self, repo_root: Path, link_map: dict[int, list[int]]) -> tuple[int, int]:
        """Apply link changes source-by-source using deterministic CLI calls."""
        total_added = 0
        total_skipped = 0
        for source_id, target_ids in sorted(link_map.items()):
            cmd = [
                "pageseeds",
                "content",
                "add-article-links",
                "--workspace-root",
                self.WORKSPACE_ROOT,
                "--website-path",
                self.WEBSITE_PATH,
                "--source-id",
                str(source_id),
                "--target-ids",
                *[str(tid) for tid in target_ids],
                "--mode",
                self.LINK_MODE,
            ]
            result = self._run_json_command(
                cmd,
                cwd=repo_root,
                step=f"add links for source {source_id}",
                timeout=300,
            )
            added = len(result.get("links_added") or [])
            skipped = len(result.get("links_skipped") or [])
            total_added += added
            total_skipped += skipped
            console.print(
                f"[dim]- Source {source_id}: +{added} added, {skipped} skipped[/dim]"
            )
        return total_added, total_skipped
    
    def run(self, task: Task) -> bool:
        """Execute SEO Step 3: Clustering and Internal Linking."""
        console.print(f"\n[bold]Cluster & Link Task: {task.title}[/bold]")
        console.print("[cyan]Running SEO Step 3: Clustering and Internal Linking (deterministic mode)[/cyan]\n")
        
        # Extract article ID from category if stored there
        article_id = None
        if task.category and task.category.startswith("linking:article_id="):
            try:
                article_id = int(task.category.split("=")[1])
            except:
                pass
        
        repo_root = Path(self.project.repo_root)
        console.print("[dim]Step 1/4: Scanning current internal links...[/dim]")

        try:
            base_cmd = [
                "pageseeds",
                "content",
            ]
            scan_before = self._run_json_command(
                [
                    *base_cmd,
                    "scan-internal-links",
                    "--workspace-root",
                    self.WORKSPACE_ROOT,
                    "--website-path",
                    self.WEBSITE_PATH,
                ],
                cwd=repo_root,
                step="scan internal links (before)",
            )

            console.print("[dim]Step 2/4: Building missing-link plan...[/dim]")
            plan_before = self._run_json_command(
                [
                    *base_cmd,
                    "generate-linking-plan",
                    "--workspace-root",
                    self.WORKSPACE_ROOT,
                    "--website-path",
                    self.WEBSITE_PATH,
                    "--missing-only",
                ],
                cwd=repo_root,
                step="generate linking plan (before)",
            )

            missing_items = plan_before.get("items") or []
            scoped_missing_before = self._count_scoped_missing(missing_items, article_id)
            link_map = self._build_link_map(missing_items, article_id)

            console.print(
                f"[dim]- Current links: {scan_before.get('total_internal_links', 0)} | "
                f"Missing (scoped): {scoped_missing_before}[/dim]"
            )

            console.print("[dim]Step 3/4: Applying missing links...[/dim]")
            if link_map:
                links_added, links_skipped = self._apply_links(repo_root, link_map)
            else:
                links_added, links_skipped = 0, 0
                console.print("[dim]- No missing links found for this scope[/dim]")

            console.print("[dim]Step 4/4: Updating brief checklist + verifying...[/dim]")
            brief_update = self._run_json_command(
                [
                    *base_cmd,
                    "update-brief-linking-status",
                    "--workspace-root",
                    self.WORKSPACE_ROOT,
                    "--website-path",
                    self.WEBSITE_PATH,
                ],
                cwd=repo_root,
                step="update brief linking status",
            )

            plan_after = self._run_json_command(
                [
                    *base_cmd,
                    "generate-linking-plan",
                    "--workspace-root",
                    self.WORKSPACE_ROOT,
                    "--website-path",
                    self.WEBSITE_PATH,
                    "--missing-only",
                ],
                cwd=repo_root,
                step="generate linking plan (after)",
            )
            scoped_missing_after = self._count_scoped_missing(plan_after.get("items") or [], article_id)

            console.print(f"\n[green]✓ Clustering and linking complete[/green]")
            console.print(
                f"[dim]Links added: {links_added}, skipped: {links_skipped}, "
                f"missing before/after (scoped): {scoped_missing_before}/{scoped_missing_after}[/dim]"
            )
            console.print(
                f"[dim]Brief checklist updated: {brief_update.get('items_checked', 0)} newly checked[/dim]"
            )
            
            task.status = "done"
            task.completed_at = __import__('datetime').datetime.now().isoformat()
            self.task_list.save()
            return True
            
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            return False
