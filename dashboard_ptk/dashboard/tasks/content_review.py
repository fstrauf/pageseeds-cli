"""Content review task runner.

Steps:
    1. Run gsc-sync-articles  — hydrates articles.json with live GSC data.
    2. Run content-audit       — deterministic health checks → content_audit.json.
    3. Build compact context deterministically, ask agent for JSON-only suggestions,
         then persist recommendations + state changes in Python.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

from ..engine.content_locator import resolve_content_dir
from ..models import Task
from .base import TaskRunner

console = Console()


class ContentReviewRunner(TaskRunner):
    """Runs the content review workflow: GSC sync → audit → agent recommendations."""

    def run(self, task: Task) -> bool:
        if task.type == "content_review":
            return self._run_content_review(task)
        if task.type == "content_review_apply":
            return self._run_apply(task)
        return False

    # ------------------------------------------------------------------

    def _find_workspace_dir(self) -> str:
        repo_root = Path(self.project.repo_root)
        for candidate in ("automation", ".github/automation"):
            if (repo_root / candidate / "articles.json").exists():
                return candidate
        return "automation"

    def _load_manifest(self) -> dict:
        repo_root = Path(self.project.repo_root)
        website_id = (
            getattr(self.project, "website_id", "")
            or getattr(self.project, "site_id", "")
        )
        candidates = [
            repo_root / ".github" / "automation" / "manifest.json",
            repo_root / "automation" / "manifest.json",
            repo_root / "manifest.json",
        ]
        if website_id:
            candidates.insert(0, repo_root / "general" / website_id / "manifest.json")
        for candidate in candidates:
            if candidate.exists():
                try:
                    return json.loads(candidate.read_text())
                except Exception:
                    pass
        return {}

    def _run_content_review(self, task: Task) -> bool:
        console.print("\n[bold]Content Review[/bold]\n")
        repo_root = Path(self.project.repo_root)
        workspace_dir = self._find_workspace_dir()

        # Step 1 — GSC sync: hydrate articles.json with live performance data
        console.print("[dim]Step 1/3 — Syncing GSC data into articles.json...[/dim]")
        manifest = self._load_manifest()
        site = manifest.get("gsc_site") or manifest.get("url") or ""
        gsc_cmd = [
            "seo", "gsc-sync-articles",
            "--repo-root", str(repo_root),
            "--workspace-dir", workspace_dir,
            "--days", "90",
        ]
        if site:
            gsc_cmd.extend(["--site", site])
        success, stdout, stderr = self.run_cli_command(gsc_cmd, timeout=300)
        if not success:
            console.print("[red]✗ GSC sync failed — aborting[/red]")
            if stderr:
                console.print(f"[dim]{stderr[:2000]}[/dim]")
            return False
        try:
            summary = json.loads(stdout)
            matched = summary.get("matched", "?")
            total = summary.get("total_articles", "?")
            console.print(f"[green]✓ GSC sync[/green] [dim]({matched}/{total} articles matched)[/dim]")
        except Exception:
            console.print("[green]✓ GSC sync complete[/green]")

        # Step 2 — Deterministic audit: objective health checks for every article
        console.print("[dim]Step 2/3 — Running content audit...[/dim]")
        audit_cmd = [
            "seo", "content-audit",
            "--repo-root", str(repo_root),
            "--workspace-dir", workspace_dir,
        ]
        success, stdout, stderr = self.run_cli_command(audit_cmd, timeout=120)
        if not success:
            console.print("[red]✗ Content audit failed — aborting[/red]")
            if stderr:
                console.print(f"[dim]{stderr[:2000]}[/dim]")
            return False
        try:
            audit = json.loads(stdout)
            total_a = audit.get("total_audited", "?")
            health = audit.get("health_summary", {})
            poor = health.get("poor", 0)
            needs_work = health.get("needs_improvement", 0)
            console.print(
                f"[green]✓ Audit[/green] [dim]({total_a} articles: "
                f"{poor} poor, {needs_work} need work)[/dim]"
            )
        except Exception:
            console.print("[green]✓ Audit complete[/green]")

        # Step 3 — Deterministic candidate selection + JSON-only recommendations
        console.print("[dim]Step 3/3 — Generating recommendations...[/dim]")
        articles_path = repo_root / workspace_dir / "articles.json"
        audit_path = repo_root / workspace_dir / "content_audit.json"
        results_dir = Path(self.task_list.task_results_dir) / task.id
        results_dir.mkdir(parents=True, exist_ok=True)

        rec_output_path = results_dir / "recommendations.json"

        try:
            articles_data = json.loads(articles_path.read_text())
            audit_data = json.loads(audit_path.read_text())
        except Exception as exc:
            console.print(f"[red]✗ Could not load review inputs: {exc}[/red]")
            return False

        raw_articles = articles_data if isinstance(articles_data, list) else articles_data.get("articles", [])
        audit_articles = audit_data.get("articles", []) if isinstance(audit_data, dict) else []

        selected = self._select_priority_articles(raw_articles, audit_articles, max_items=10)
        if not selected:
            console.print("[yellow]⚠ No eligible articles found for review[/yellow]")
            task.status = "done"
            task.completed_at = datetime.now().isoformat()
            self.task_list.save()
            return True

        context_articles = self._build_context_articles(repo_root, selected, max_chars=2600)
        if not context_articles:
            console.print("[red]✗ Could not build article context for recommendations[/red]")
            return False

        prompt = self._build_recommendations_prompt(context_articles)
        success, output = self.run_kimi_agent(prompt, cwd=repo_root, timeout=360, mode="text")

        if not success and self._is_timeout_error(output):
            console.print("[yellow]⚠ Step 3 timed out; retrying with fewer articles...[/yellow]")
            retry_context = context_articles[:5]
            retry_prompt = self._build_recommendations_prompt(retry_context)
            success, output = self.run_kimi_agent(retry_prompt, cwd=repo_root, timeout=240, mode="text")

        if not success:
            console.print("[red]✗ Agent failed to generate recommendations[/red]")
            if output:
                console.print(f"[dim]{output[:500]}[/dim]")
            return False

        rec = self._extract_recommendations_from_output(output)
        if not rec:
            console.print("[yellow]⚠ Could not recover valid recommendations JSON from agent output[/yellow]")
            return False

        rec = self._normalize_recommendations_payload(rec, context_articles)
        rec_output_path.write_text(json.dumps(rec, indent=2))

        self._mark_articles_in_review(articles_path, rec)

        try:
            self._print_action_plan(rec, rec_output_path)
        except Exception as exc:
            console.print(f"[yellow]⚠ Could not read recommendations: {exc}[/yellow]")
            console.print(f"[dim]File: {rec_output_path}[/dim]")
            return False

        # Create an implementation task so the agent applies the changes
        n_articles = len(rec.get("articles") or [])
        task_title = f"Apply review fixes: {n_articles} articles" if n_articles > 1 else (
            f"Apply review fixes: {rec.get('articles', [{}])[0].get('article_title', 'article')}"
            if rec.get("articles") else f"Apply review fixes: {rec.get('article_title', 'article')}"
        )
        artifact_path = str(rec_output_path.relative_to(Path(self.project.repo_root)))
        impl_task = self.task_list.create_task(
            task_type="content_review_apply",
            title=task_title,
            phase="implementation",
            priority="high",
            execution_mode="auto",
            input_artifact=artifact_path,
        )
        self.task_list.save()

        task.status = "done"
        task.completed_at = datetime.now().isoformat()
        self.task_list.save()

        console.print(
            f"\n[green]✓ Implementation task created:[/green] [bold]{impl_task.id}[/bold]"
        )
        console.print(
            "[dim]  Run this task to apply the changes to the article.[/dim]"
        )
        console.print("\n[bold green]✓ Content review complete[/bold green]")
        return True

    def _is_timeout_error(self, output: str) -> bool:
        text = (output or "").lower()
        return "timeout" in text or "timed out" in text

    def _build_context_articles(
        self,
        repo_root: Path,
        selected: list[dict],
        max_chars: int,
    ) -> list[dict]:
        content_dir = None
        try:
            resolution = resolve_content_dir(
                repo_root=repo_root,
                website_id=getattr(self.project, "website_id", None),
                include_empty_auto_fallback=True,
            )
            content_dir = resolution.selected
        except Exception:
            content_dir = None

        context_articles: list[dict] = []
        for article in selected:
            file_rel = str(article.get("file") or "")
            if not file_rel:
                continue

            file_abs, normalized_rel = self._resolve_article_file(repo_root, file_rel, content_dir)
            if not file_abs.exists() or not file_abs.is_file():
                continue

            try:
                source_text = file_abs.read_text(errors="ignore")
            except Exception:
                source_text = ""

            context_articles.append(
                {
                    "article_id": article.get("id"),
                    "article_title": article.get("title"),
                    "article_file": normalized_rel,
                    "url_slug": article.get("url_slug"),
                    "target_keyword": article.get("target_keyword"),
                    "gsc_snapshot": article.get("gsc") or {},
                    "failed_checks": article.get("_failed_checks") or [],
                    "source_excerpt": source_text[:max_chars],
                }
            )
        return context_articles

    def _resolve_article_file(
        self,
        repo_root: Path,
        file_ref: str,
        content_dir: Path | None,
    ) -> tuple[Path, str]:
        """Resolve article file references to an absolute path + repo-relative display path."""
        raw = str(file_ref or "").strip()
        ref_path = Path(raw)

        candidates: list[Path] = []
        if ref_path.is_absolute():
            candidates.append(ref_path)
        else:
            candidates.append(repo_root / raw)
            trimmed = raw[2:] if raw.startswith("./") else raw
            if trimmed != raw:
                candidates.append(repo_root / trimmed)

            if content_dir:
                # Some projects persist only basename in articles.json.
                candidates.append(content_dir / ref_path.name)

                # If file_ref is rooted at content/, remap inside the resolved content_dir.
                normalized = trimmed.replace("\\", "/")
                if normalized.startswith("content/"):
                    suffix = normalized.split("/", 1)[1]
                    candidates.append(content_dir / suffix)

        # Deduplicate while preserving order.
        deduped: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)

        chosen = next((c for c in deduped if c.exists() and c.is_file()), deduped[0])
        try:
            rel = chosen.resolve().relative_to(repo_root.resolve())
            normalized_rel = rel.as_posix()
        except Exception:
            normalized_rel = raw

        return chosen, normalized_rel

    def _build_recommendations_prompt(self, context_articles: list[dict]) -> str:
        payload = {
            "generated_at": datetime.now().isoformat(),
            "articles": context_articles,
        }

        return f"""Generate SEO recommendations JSON from provided context.

Return ONLY one valid JSON object. No markdown fences, no commentary.

Input context JSON:
{json.dumps(payload, ensure_ascii=False)}

Output schema:
{{
  "generated_at": "<ISO timestamp>",
  "total_articles": <N>,
  "articles": [
    {{
      "article_id": <id>,
      "article_title": "<title>",
      "article_file": "<relative path>",
      "url_slug": "<slug>",
      "target_keyword": "<keyword>",
      "gsc_snapshot": {{...}},
      "failed_checks": [...],
      "suggestions": [
        {{
          "category": "title|meta_description|intro|h1|internal_links|faq|eeat|cta",
          "current": "<current text or situation>",
          "proposed": "<specific replacement/action>",
          "reason": "<one sentence impact>"
        }}
      ]
    }}
  ]
}}

Requirements:
- Use only the provided context.
- Provide 4-8 actionable suggestions per article.
- Preserve article metadata fields exactly from input where present.
"""

    def _normalize_recommendations_payload(self, rec: dict, context_articles: list[dict]) -> dict:
        """Guarantee stable schema and deterministic metadata from local context."""
        context_map = {
            str(item.get("article_id")): item
            for item in context_articles
            if item.get("article_id") is not None
        }

        normalized_articles: list[dict] = []
        rec_articles = rec.get("articles") if isinstance(rec, dict) else None
        if not isinstance(rec_articles, list):
            rec_articles = []

        for item in rec_articles:
            if not isinstance(item, dict):
                continue

            article_id = item.get("article_id")
            key = str(article_id)
            fallback = context_map.get(key)
            if fallback is None:
                continue

            suggestions = item.get("suggestions")
            if not isinstance(suggestions, list):
                suggestions = []

            normalized_suggestions = []
            for suggestion in suggestions:
                if not isinstance(suggestion, dict):
                    continue
                normalized_suggestions.append(
                    {
                        "category": str(suggestion.get("category") or ""),
                        "current": str(suggestion.get("current") or ""),
                        "proposed": str(suggestion.get("proposed") or ""),
                        "reason": str(suggestion.get("reason") or ""),
                    }
                )

            normalized_articles.append(
                {
                    "article_id": fallback.get("article_id"),
                    "article_title": fallback.get("article_title") or item.get("article_title"),
                    "article_file": fallback.get("article_file") or item.get("article_file"),
                    "url_slug": fallback.get("url_slug") or item.get("url_slug"),
                    "target_keyword": fallback.get("target_keyword") or item.get("target_keyword"),
                    "gsc_snapshot": fallback.get("gsc_snapshot") or item.get("gsc_snapshot") or {},
                    "failed_checks": fallback.get("failed_checks") or item.get("failed_checks") or [],
                    "suggestions": normalized_suggestions,
                }
            )

        if not normalized_articles:
            for fallback in context_articles:
                normalized_articles.append(
                    {
                        "article_id": fallback.get("article_id"),
                        "article_title": fallback.get("article_title"),
                        "article_file": fallback.get("article_file"),
                        "url_slug": fallback.get("url_slug"),
                        "target_keyword": fallback.get("target_keyword"),
                        "gsc_snapshot": fallback.get("gsc_snapshot") or {},
                        "failed_checks": fallback.get("failed_checks") or [],
                        "suggestions": [],
                    }
                )

        return {
            "generated_at": datetime.now().isoformat(),
            "total_articles": len(normalized_articles),
            "articles": normalized_articles,
        }

    def _mark_articles_in_review(self, articles_path: Path, rec: dict) -> None:
        """Update selected articles to in_review deterministically."""
        try:
            payload = json.loads(articles_path.read_text())
        except Exception:
            return

        if isinstance(payload, dict):
            articles = payload.get("articles")
            is_wrapped = True
        else:
            articles = payload
            is_wrapped = False

        if not isinstance(articles, list):
            return

        ids = {
            str(item.get("article_id"))
            for item in (rec.get("articles") or [])
            if isinstance(item, dict) and item.get("article_id") is not None
        }
        if not ids:
            return

        changed = False
        for article in articles:
            if not isinstance(article, dict):
                continue
            if str(article.get("id")) in ids:
                if article.get("review_status") != "in_review":
                    article["review_status"] = "in_review"
                    changed = True

        if not changed:
            return

        out_payload = payload if is_wrapped else articles
        if is_wrapped:
            out_payload["articles"] = articles
        articles_path.write_text(json.dumps(out_payload, indent=2))

    def _select_priority_articles(
        self,
        raw_articles: list,
        audit_articles: list,
        max_items: int = 5,
    ) -> list[dict]:
        """Deterministically rank likely high-impact articles for review recommendations."""
        articles = [a for a in raw_articles if isinstance(a, dict)]
        audit = [a for a in audit_articles if isinstance(a, dict)]

        audit_by_file = {str(a.get("file") or ""): a for a in audit if a.get("file")}
        audit_by_slug = {str(a.get("url_slug") or ""): a for a in audit if a.get("url_slug")}

        candidates: list[tuple[int, dict]] = []
        for article in articles:
            status = str(article.get("status") or "").lower()
            review_status = str(article.get("review_status") or "").lower()
            file_rel = str(article.get("file") or "")
            if status == "draft" or review_status == "in_review" or not file_rel:
                continue

            gsc = article.get("gsc") or {}
            pos = self._to_float(gsc.get("avg_position"))
            impressions = self._to_float(gsc.get("impressions"))
            ctr = self._to_float(gsc.get("ctr"))

            audit_row = audit_by_file.get(file_rel) or audit_by_slug.get(str(article.get("url_slug") or "")) or {}
            health = str(audit_row.get("health") or "").lower()
            checks_failed = int(audit_row.get("checks_failed") or 0)
            health_score = int(audit_row.get("health_score") or 0)

            failed_checks = []
            checks = audit_row.get("checks") or {}
            if isinstance(checks, dict):
                for key, check in checks.items():
                    if isinstance(check, dict) and check.get("pass") is False:
                        failed_checks.append(
                            {
                                "check_id": key,
                                "label": check.get("label", key),
                            }
                        )
            article["_failed_checks"] = failed_checks

            score = 0
            # Tier 1 quick CTR wins.
            if 5 <= pos <= 20 and impressions > 200 and ctr < 0.03:
                score += 1000
            # Tier 2 stale + poor.
            if health == "poor" and self._is_stale_review(article.get("last_reviewed_at")):
                score += 700
            # Tier 3 weak content quality / no GSC.
            score += checks_failed * 15
            score += max(0, 100 - health_score)

            # Avoid already-strong performers.
            if 1 <= pos <= 4 and ctr >= 0.05:
                score -= 600

            candidates.append((score, article))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [a for score, a in candidates if score > 0][:max_items]

    def _to_float(self, value: object) -> float:
        try:
            if value is None or value == "":
                return 0.0
            return float(value)
        except Exception:
            return 0.0

    def _is_stale_review(self, value: object) -> bool:
        if not value:
            return True
        try:
            raw = str(value).replace("Z", "+00:00")
            reviewed_at = datetime.fromisoformat(raw)
            delta_days = (datetime.now(reviewed_at.tzinfo) - reviewed_at).days
            return delta_days >= 365
        except Exception:
            return True

    def _extract_recommendations_from_output(self, output: str) -> dict | None:
        """Best-effort recovery for recommendations JSON from agent text output."""
        text = (output or "").strip()
        if not text:
            return None

        parsed = self._parse_json_candidate(text)
        if isinstance(parsed, dict):
            return parsed

        # Prefer explicit JSON code blocks if present.
        code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
        for block in code_blocks:
            parsed = self._parse_json_candidate(block.strip())
            if isinstance(parsed, dict):
                return parsed

        # Final fallback: scan for the first balanced JSON object in free text.
        extracted = self._extract_first_balanced_object(text)
        if extracted:
            parsed = self._parse_json_candidate(extracted)
            if isinstance(parsed, dict):
                return parsed

        return None

    def _parse_json_candidate(self, candidate: str) -> dict | None:
        try:
            parsed = json.loads(candidate)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        # Minimal shape check for review recommendations payloads.
        if "articles" in parsed and isinstance(parsed.get("articles"), list):
            return parsed
        if "article_file" in parsed or "suggestions" in parsed:
            return parsed
        return parsed

    def _extract_first_balanced_object(self, text: str) -> str | None:
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escaped = False

        for i in range(start, len(text)):
            ch = text[i]

            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None

    def _print_action_plan(self, rec: dict, rec_path: Path) -> None:
        """Print the full action plan from a recommendations.json file."""
        articles = rec.get("articles")
        if articles:
            # Multi-article format
            total = rec.get("total_articles", len(articles))
            console.print(f"\n[bold]Action plan[/bold] — {total} articles\n")
            for art in articles:
                self._print_single_article(art)
                console.print()
        else:
            # Legacy single-article format
            self._print_single_article(rec)
        console.print(f"[dim]Full recommendations: {rec_path}[/dim]")

    def _print_single_article(self, rec: dict) -> None:
        """Print the action plan for one article."""
        title = rec.get("article_title") or rec.get("url_slug") or "(unknown)"
        article_file = rec.get("article_file", "")
        keyword = rec.get("target_keyword", "")
        gsc = rec.get("gsc_snapshot") or {}
        failed = rec.get("failed_checks") or []
        suggestions = rec.get("suggestions") or []

        console.print(f"[bold]Article:[/bold] {title}")
        if article_file:
            console.print(f"[dim]File:    {article_file}[/dim]")
        if keyword:
            console.print(f"[dim]Keyword: {keyword}[/dim]")

        if gsc:
            pos = gsc.get("avg_position", "?")
            impr = gsc.get("impressions", "?")
            ctr = gsc.get("ctr", "?")
            clicks = gsc.get("clicks", "?")
            console.print(
                f"[dim]GSC:     pos {pos} · {impr} impressions · "
                f"{clicks} clicks · CTR {ctr}[/dim]"
            )

        if failed:
            failed_labels = [
                f.get("label", f.get("check_id", "")) if isinstance(f, dict) else str(f)
                for f in failed
            ]
            console.print(f"[dim]Failed:  {', '.join(failed_labels)}[/dim]")

        if not suggestions:
            console.print("[yellow]  No suggestions.[/yellow]")
            return

        console.print(f"[dim]{len(suggestions)} suggestions:[/dim]")
        for i, s in enumerate(suggestions, 1):
            cat = s.get("category", "").upper()
            proposed = s.get("proposed", "")
            reason = s.get("reason", "")
            console.print(f"  [bold]{i}. {cat}[/bold]  {proposed[:100]}")
            if reason:
                console.print(f"     [dim]{reason[:120]}[/dim]")

    def _run_apply(self, task: Task) -> bool:
        """Apply recommendations from a previous content review to the article file."""
        repo_root = Path(self.project.repo_root)

        artifact_path = getattr(task, "input_artifact", "") or ""
        if not artifact_path:
            console.print("[red]✗ No recommendations file linked to this task[/red]")
            return False

        rec_path = repo_root / artifact_path
        if not rec_path.exists():
            console.print(f"[red]✗ Recommendations file not found: {rec_path}[/red]")
            return False

        try:
            rec = json.loads(rec_path.read_text())
        except Exception as exc:
            console.print(f"[red]✗ Could not read recommendations: {exc}[/red]")
            return False

        workspace_dir = self._find_workspace_dir()
        articles_json = repo_root / workspace_dir / "articles.json"

        self._print_action_plan(rec, rec_path)
        articles = rec.get("articles") or []
        if not articles and rec.get("article_file"):
            # Backward compatibility: legacy single-article recommendations format.
            articles = [rec]
        n = len(articles)
        console.print(f"\n[dim]Applying changes to {n} article(s)...[/dim]")

        today = datetime.now().date().isoformat()
        prompt = f"""Apply content improvements across multiple article files.

Repo root: {repo_root}
Recommendations file: {rec_path}
Articles registry: {articles_json}

## Your job

1. Read the full recommendations file at {rec_path}.
   It contains a list of articles under the "articles" key
   (or a single article if the top-level has "article_file" — legacy format).

2. For each article:
   a. Read the source file (article_file field, relative to {repo_root})
   b. Apply every suggestion in that article's suggestions list:
      - title/meta_description/h1: update frontmatter
      - intro: rewrite opening paragraph(s) as specified
      - internal_links: add links at the specified places in the body
      - faq: add or expand the FAQ section with the suggested Q&As
      - eeat: add the credibility signal described
      - cta: add or strengthen the call-to-action as described
   c. Save the updated file
   d. In {articles_json}, find the article by id and update:
      - review_status → "reviewed"
      - last_reviewed_at → {today}

3. Report one line per article summarising what was changed.

Work through all articles. Make all changes directly. Do not ask questions."""

        success, output = self.run_kimi_agent(prompt, cwd=repo_root, timeout=600)

        task.status = "done"
        task.completed_at = datetime.now().isoformat()
        self.task_list.save()

        if not success:
            console.print("[red]✗ Agent failed to apply changes[/red]")
            if output:
                console.print(f"[dim]{output[:500]}[/dim]")
            return False

        console.print("\n[bold green]✓ Changes applied[/bold green]")
        if output:
            # Print a short summary from the agent
            lines = [l for l in output.strip().splitlines() if l.strip()][:8]
            for line in lines:
                console.print(f"[dim]  {line[:120]}[/dim]")
        return True

