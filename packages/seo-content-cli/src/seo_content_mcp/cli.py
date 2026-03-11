"""Plain Python CLI for seo-content-mcp.

Runs the same underlying logic as the MCP tools, but without starting an MCP server.

Examples:
  uv run --directory packages/seo-content-cli seo-content-cli validate-content --website-path general/expense
  uv run --directory packages/seo-content-cli seo-content-cli clean-content --website-path general/expense
  uv run --directory packages/seo-content-cli seo-content-cli analyze-dates --website-path general/expense
  uv run --directory packages/seo-content-cli seo-content-cli fix-dates --website-path general/expense --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _print_json(data: object) -> None:
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Compact output helpers for ops commands (Step 4)
# ---------------------------------------------------------------------------

def _compact_pull_from_repo(data: dict) -> dict:
    """Strip verbose fields from pull-from-repo output."""
    return {
        "ok": data.get("ok"),
        "dry_run": data.get("dry_run"),
        "website_id": data.get("site_id"),
        "files_to_pull": data.get("files_to_pull", 0),
        "files_skipped": data.get("files_skipped", 0),
        "files_pulled": data.get("files_pulled", 0),
        "production_in_sync": data.get("files_to_pull", 0) == 0,
    }


def _compact_schedule_apply(data: dict) -> dict:
    """Strip verbose fields from schedule-apply output."""
    schedule = data.get("schedule", []) or []
    fm_synced = data.get("frontmatter_synced", []) or []
    date_range = None
    if schedule:
        dates = [item.get("to") for item in schedule if item.get("to")]
        if dates:
            date_range = {"start": min(dates), "end": max(dates)}
    return {
        "ok": data.get("ok"),
        "website_id": data.get("site_id"),
        "articles_scheduled": len(schedule),
        "date_range": date_range,
        "spacing_days": data.get("spacing_days"),
        "frontmatter_synced": len(fm_synced),
        "applied": data.get("applied", False),
    }


def _compact_sync_and_optimize(data: dict) -> dict:
    """Strip phases detail, keep only the summary block."""
    summary = data.get("summary", {})
    deploy = (data.get("phases") or {}).get("deployment", {})
    result = {
        "ok": data.get("ok"),
        "mode": data.get("mode"),
        "website_id": data.get("website_id"),
        "files_ready_to_push": summary.get("files_ready_to_push", 0),
        "date_issues_found": summary.get("date_issues_found", 0),
        "validation_errors": summary.get("validation_errors", 0),
        "missing_in_repo": summary.get("missing_in_repo_total", 0),
        "files_mismatched": summary.get("files_mismatched", 0),
        "next_action": summary.get("next_action", ""),
    }
    if deploy.get("status") == "completed":
        result["files_deployed"] = deploy.get("files_copied", 0)
    if data.get("recommended_actions"):
        result["recommended_actions"] = data["recommended_actions"]
    return result


def _compact_sync_and_validate(data: dict) -> dict:
    """Strip phases detail, keep only sync/validation summary."""
    summary = data.get("summary", {})
    result = {
        "ok": data.get("ok"),
        "mode": data.get("mode"),
        "website_id": data.get("website_id"),
        "articles_imported": summary.get("articles_imported", 0),
        "new_articles": summary.get("new_articles", 0),
        "updated_articles": summary.get("updated_articles", 0),
        "checked_entries": summary.get("checked_entries", 0),
        "missing_everywhere": summary.get("missing_everywhere", 0),
        "missing_in_repo": summary.get("missing_in_repo", 0),
        "missing_in_automation": summary.get("missing_in_automation", 0),
        "mismatched_files": summary.get("mismatched_files", 0),
        "next_action": summary.get("next_action", ""),
    }
    if data.get("recommended_actions"):
        result["recommended_actions"] = data["recommended_actions"]
    return result


def _compact_deploy_files(data: dict) -> dict:
    """Strip verbose fields from deploy-files output."""
    return {
        "ok": data.get("ok"),
        "dry_run": data.get("dry_run"),
        "website_id": data.get("site_id"),
        "allow_overwrite": data.get("allow_overwrite"),
        "files_requested": len(data.get("files_requested") or []),
        "files_copied": data.get("files_copied", 0),
        "files_skipped": data.get("files_skipped", 0),
        "files_failed": data.get("files_failed", 0),
        "copied": data.get("copied", []),
    }


def _workspace_root(explicit: str | None) -> str:
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    # Reuse the same detection logic used by the MCP server.
    from .server import detect_workspace_root

    return str(Path(detect_workspace_root()).resolve())


def _cmd_validate_content(args: argparse.Namespace) -> None:
    from .content_cleaner import ContentCleaner

    root = _workspace_root(args.workspace_root)
    cleaner = ContentCleaner(root)
    res = cleaner.clean_website(args.website_path, dry_run=True)
    _print_json(res.get_summary() | {"issues": [i.__dict__ for i in res.issues_found]})


def _cmd_clean_content(args: argparse.Namespace) -> None:
    from .content_cleaner import ContentCleaner

    root = _workspace_root(args.workspace_root)
    cleaner = ContentCleaner(root)
    res = cleaner.clean_website(args.website_path, dry_run=bool(args.dry_run))
    _print_json(res.get_summary() | {"issues": [i.__dict__ for i in res.issues_found], "dry_run": bool(args.dry_run)})


def _cmd_analyze_dates(args: argparse.Namespace) -> None:
    from .date_distributor import DateDistributor

    root = _workspace_root(args.workspace_root)
    distributor = DateDistributor(root)
    res = distributor.analyze_dates(args.website_path)
    _print_json(
        {
            "project_name": res.project_name,
            "today": res.today.strftime("%Y-%m-%d"),
            "seven_days_ago": res.seven_days_ago.strftime("%Y-%m-%d"),
            "total_articles": res.total_articles,
            "past_articles": res.past_articles,
            "recent_articles": res.recent_articles,
            "issues": [i.__dict__ for i in res.issues],
            "overlapping_dates": [{"date": d, "article_ids": ids} for d, ids in res.overlapping_dates],
        }
    )


def _cmd_fix_dates(args: argparse.Namespace) -> None:
    from .date_distributor import DateDistributor

    root = _workspace_root(args.workspace_root)
    distributor = DateDistributor(root)
    res = distributor.fix_dates(args.website_path, dry_run=bool(args.dry_run))
    _print_json(
        {
            "project_name": res.project_name,
            "articles_fixed": res.articles_fixed,
            "changes": res.changes,
            "distribution_info": res.distribution_info,
            "dry_run": bool(args.dry_run),
        }
    )


def _cmd_test_distribution(args: argparse.Namespace) -> None:
    from .server import SEOContentServer

    root = _workspace_root(args.workspace_root)
    server = SEOContentServer(root)
    res = server.test_distribution(args.project_name, args.article_count, args.earliest_date)
    _print_json(res.model_dump())


def _cmd_articles_summary(args: argparse.Namespace) -> None:
    from .server import _articles_summary

    root = _workspace_root(args.workspace_root)
    res = _articles_summary(workspace_root=root, website_path=args.website_path)
    _print_json(res.model_dump())


def _cmd_articles_index(args: argparse.Namespace) -> None:
    from .server import _get_articles_index

    root = _workspace_root(args.workspace_root)
    res = _get_articles_index(workspace_root=root, website_path=args.website_path, status=args.status)
    data = res.model_dump()

    out_format = (getattr(args, "format", "") or "json").strip().lower()
    if out_format == "json":
        _print_json(data)
        return

    if out_format != "lines":
        raise SystemExit(f"Unsupported --format: {out_format}")

    field = (getattr(args, "field", "") or "").strip()
    if not field:
        raise SystemExit("--field is required when using --format lines")

    items = data.get("items") or []
    if not isinstance(items, list):
        raise SystemExit("Unexpected articles-index payload (items is not a list)")

    values: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        v = item.get(field)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        values.append(s)

    if bool(getattr(args, "unique", False)):
        # Preserve first-seen order by default.
        values = list(dict.fromkeys(values))

    if bool(getattr(args, "sort", False)):
        values = sorted(values, key=str.casefold)

    limit = int(getattr(args, "limit", 0) or 0)
    if limit > 0:
        values = values[:limit]

    if values:
        sys.stdout.write("\n".join(values) + "\n")


def _cmd_filter_new_keywords(args: argparse.Namespace) -> None:
    from .server import _filter_new_keywords

    root = _workspace_root(args.workspace_root)
    keywords = []
    if args.keywords:
        keywords.extend(args.keywords)
    if args.keywords_file:
        if args.keywords_file == "-":
            text = sys.stdin.read()
        else:
            text = Path(args.keywords_file).read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line:
                keywords.append(line)

    res = _filter_new_keywords(
        workspace_root=root,
        website_path=args.website_path,
        keywords=keywords,
        enable_fuzzy=not bool(args.disable_fuzzy),
        fuzzy_threshold=float(args.fuzzy_threshold),
    )
    _print_json(res.model_dump())


def _cmd_append_draft_articles(args: argparse.Namespace) -> None:
    from .server import DraftArticleInput, _append_draft_articles

    root = _workspace_root(args.workspace_root)
    if args.drafts_json == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.drafts_json).read_text(encoding="utf-8")
    payload = json.loads(raw)
    drafts_raw = payload.get("drafts") if isinstance(payload, dict) else payload
    if not isinstance(drafts_raw, list):
        raise SystemExit("drafts_json must be a JSON list or an object with a 'drafts' list")

    drafts = [DraftArticleInput(**d) for d in drafts_raw]
    res = _append_draft_articles(
        workspace_root=root,
        website_path=args.website_path,
        drafts=drafts,
        enable_dedupe=not bool(args.disable_dedupe),
        fuzzy_threshold=float(args.fuzzy_threshold),
    )
    _print_json(res.model_dump())


def _cmd_get_articles_by_keyword(args: argparse.Namespace) -> None:
    from .server import _get_articles_by_keyword

    root = _workspace_root(args.workspace_root)
    res = _get_articles_by_keyword(
        workspace_root=root,
        website_path=args.website_path,
        keyword=args.keyword,
        enable_fuzzy=not bool(args.disable_fuzzy),
        fuzzy_threshold=float(args.fuzzy_threshold),
    )
    _print_json(res.model_dump())


def _cmd_get_next_content_task(args: argparse.Namespace) -> None:
    from .server import _get_next_content_task

    root = _workspace_root(args.workspace_root)
    brief_file, task = _get_next_content_task(
        workspace_root=root,
        website_path=args.website_path,
        brief_path=args.brief_path,
        priority=args.priority,
    )
    _print_json({"website_path": args.website_path, "brief_path": str(brief_file), "task": task.model_dump()})


def _cmd_plan_content_article(args: argparse.Namespace) -> None:
    from .server import _plan_content_article

    root = _workspace_root(args.workspace_root)
    res = _plan_content_article(
        workspace_root=root,
        website_path=args.website_path,
        brief_path=args.brief_path,
        task_id=args.task_id,
        priority=args.priority,
        extension=args.extension,
    )
    _print_json(res.model_dump())


def _cmd_publish_article_and_complete_task(args: argparse.Namespace) -> None:
    from .server import (
        _complete_task_in_brief,
        _plan_content_article,
        _resolve_brief_path,
        _upsert_article_entry,
    )
    import re as _re

    root = _workspace_root(args.workspace_root)
    brief_file = _resolve_brief_path(workspace_root=root, website_path=args.website_path, brief_path=args.brief_path)

    if args.from_plan:
        # Auto-populate article metadata from plan-content-article
        sys.stderr.write(f"[publish] Running plan-content-article for task '{args.task_id}'...\n")
        plan = _plan_content_article(
            workspace_root=root,
            website_path=args.website_path,
            brief_path=args.brief_path,
            task_id=args.task_id,
            priority="HIGH PRIORITY",
            extension="mdx",
        )

        # Auto-detect word count from the content file
        content_dir = Path(root) / args.website_path
        file_ref = plan.file  # e.g., "./content/91_some_slug.mdx"
        content_path = content_dir / file_ref.lstrip("./")
        word_count = 0
        if content_path.exists():
            text = content_path.read_text(encoding="utf-8")
            # Strip frontmatter
            fm_match = _re.match(r"^---\s*\n.*?\n---\s*\n", text, _re.DOTALL)
            body = text[fm_match.end():] if fm_match else text
            word_count = len(body.split())
            sys.stderr.write(f"[publish] Auto-detected word count: {word_count} from {content_path.name}\n")
        else:
            sys.stderr.write(f"[publish] Warning: content file not found at {content_path}, word_count=0\n")

        # Extract difficulty as a number
        difficulty = ""
        if plan.task.est_kd:
            difficulty = _re.sub(r"[^0-9.]", "", plan.task.est_kd) or plan.task.est_kd

        # Extract volume
        volume = 0
        if plan.task.est_volume:
            vol_str = _re.sub(r"[^0-9]", "", plan.task.est_volume)
            volume = int(vol_str) if vol_str else 0

        # Extract traffic estimate
        traffic = ""
        if plan.task.est_traffic:
            traffic = plan.task.est_traffic.strip()

        # Build content_gaps from task
        gaps = []
        if plan.task.fills_gap:
            gaps.append(plan.task.fills_gap)

        # Allow CLI overrides
        override_word_count = getattr(args, "word_count", None)
        override_title = getattr(args, "title", None)

        article = {
            "id": plan.article_id,
            "title": override_title or (plan.task.article_title or plan.url_slug.replace("-", " ").title()),
            "url_slug": plan.url_slug,
            "file": plan.file,
            "target_keyword": plan.task.target_keyword or "",
            "keyword_difficulty": difficulty,
            "target_volume": volume,
            "published_date": plan.published_date,
            "word_count": override_word_count if override_word_count is not None else word_count,
            "status": args.status,
            "content_gaps_addressed": gaps,
            "estimated_traffic_monthly": traffic,
        }
        sys.stderr.write(f"[publish] Article {article['id']}: \"{article['title']}\" -> {article['file']}\n")

    elif args.article_json:
        if args.article_json == "-":
            article_raw = sys.stdin.read()
        else:
            article_raw = Path(args.article_json).read_text(encoding="utf-8")
        article = json.loads(article_raw)
        if not isinstance(article, dict):
            raise SystemExit("--article-json must contain a JSON object")
    else:
        raise SystemExit("Either --from-plan or --article-json must be provided")

    article_id = int(article.get("id") or 0)
    if article_id <= 0:
        raise SystemExit("article.id must be provided and > 0")

    article.setdefault("status", args.status)
    article.setdefault("published_date", "")
    article.setdefault("word_count", 0)
    article.setdefault("content_gaps_addressed", [])
    article.setdefault("target_volume", 0)
    article.setdefault("keyword_difficulty", "")
    article.setdefault("estimated_traffic_monthly", "")

    _upsert_article_entry(workspace_root=root, website_path=args.website_path, entry=article)
    updated_brief = _complete_task_in_brief(brief_path=brief_file, task_id=args.task_id, article_id=article_id)
    _print_json(
        {
            "website_path": args.website_path,
            "brief_path": str(brief_file),
            "task_id": args.task_id,
            "article_id": article_id,
            "article": article,
            "updated_articles_json": True,
            "updated_brief": bool(updated_brief),
        }
    )


def _cmd_diagnose(args: argparse.Namespace) -> None:
    """Comprehensive diagnostic of articles.json vs content files."""
    import re
    from collections import defaultdict
    
    root = _workspace_root(args.workspace_root)
    website_root = (Path(root) / args.website_path).resolve()
    
    # Support both old structure (articles.json in website root) and new structure (.github/automation/)
    articles_paths = [
        website_root / "articles.json",
        website_root / ".github" / "automation" / "articles.json",
    ]
    articles_path = None
    for p in articles_paths:
        if p.exists():
            articles_path = p
            break
    
    if not articles_path:
        raise SystemExit(f"articles.json not found in {website_root} or {website_root}/.github/automation/")
    
    # Find content directory
    content_dirs = [
        website_root / "content",
        website_root / "src" / "blog" / "posts",
        website_root / "src" / "content",
        website_root / "posts",
        website_root / "blog",
    ]
    content_dir = None
    for d in content_dirs:
        if d.exists() and d.is_dir():
            content_dir = d
            break
    
    if not content_dir:
        raise SystemExit(f"Content directory not found in {website_root}")
    
    # Load articles.json
    try:
        with open(articles_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        raise SystemExit(f"Failed to read {articles_path}: {e}")
    
    articles = data.get('articles', [])
    if not isinstance(articles, list):
        raise SystemExit("articles.json must contain an 'articles' list")
    
    # Helper to extract date from frontmatter
    def extract_frontmatter_date(filepath: Path) -> str | None:
        try:
            text = filepath.read_text(encoding='utf-8')
            match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
            if not match:
                return None
            fm = match.group(1)
            date_match = re.search(r'^date:\s*["\']?([^"\'\n]+)["\']?$', fm, re.MULTILINE)
            return date_match.group(1).strip() if date_match else None
        except Exception:
            return None
    
    # Run diagnostics
    results = {
        "website_path": str(website_root),
        "articles_json": str(articles_path),
        "content_dir": str(content_dir),
        "total_articles_in_json": len(articles),
    }
    
    # Check nextArticleId
    max_id = max((a.get('id', 0) for a in articles if isinstance(a, dict)), default=0)
    next_id = data.get('nextArticleId')
    expected_next = max_id + 1
    results["id_management"] = {
        "nextArticleId": next_id,
        "max_article_id": max_id,
        "expected_next": expected_next,
        "correct": next_id == expected_next,
    }
    
    # Check ID gaps
    ids = sorted([a.get('id') for a in articles if isinstance(a, dict) and a.get('id')])
    gaps = [(ids[i], ids[i+1]) for i in range(len(ids) - 1) if ids[i+1] - ids[i] > 1]
    results["id_gaps"] = {"count": len(gaps), "gaps": gaps[:10]}  # Limit to first 10
    
    # Check for duplicate JSON dates
    json_dates = defaultdict(list)
    for a in articles:
        if isinstance(a, dict):
            d = a.get('published_date', '')
            if d:
                json_dates[d].append(a.get('id'))
    dup_json_dates = {d: ids for d, ids in json_dates.items() if len(ids) > 1}
    results["json_dates"] = {
        "total_unique": len(json_dates),
        "duplicates": dup_json_dates,
        "has_duplicates": bool(dup_json_dates),
    }
    
    # Check content files
    content_files = {f.name: f for f in content_dir.glob('*') if f.suffix in {'.md', '.mdx'} and f.is_file()}
    results["content_files"] = {"count": len(content_files)}
    
    # Check frontmatter dates and mismatches
    fm_dates = defaultdict(list)
    date_mismatches = []
    missing_files = []
    orphaned_files = set(content_files.keys())
    
    for article in articles:
        if not isinstance(article, dict):
            continue
        article_id = article.get('id')
        file_ref = article.get('file', '')
        json_date = article.get('published_date', '')
        
        if not file_ref:
            continue
        
        basename = Path(file_ref).name
        filepath = content_dir / basename
        
        if basename in orphaned_files:
            orphaned_files.discard(basename)
        
        if not filepath.exists():
            missing_files.append({"id": article_id, "file": basename})
            continue
        
        fm_date = extract_frontmatter_date(filepath)
        if fm_date:
            fm_dates[fm_date].append((article_id, basename))
            if json_date and fm_date != json_date:
                date_mismatches.append({
                    "id": article_id,
                    "file": basename,
                    "json_date": json_date,
                    "frontmatter_date": fm_date,
                })
    
    dup_fm_dates = {d: items for d, items in fm_dates.items() if len(items) > 1}
    results["frontmatter_dates"] = {
        "total_unique": len(fm_dates),
        "duplicates": {d: [i[0] for i in items] for d, items in dup_fm_dates.items()},
        "has_duplicates": bool(dup_fm_dates),
    }
    results["date_mismatches"] = {
        "count": len(date_mismatches),
        "mismatches": date_mismatches[:20] if args.verbose else [],  # Limit unless verbose
    }
    results["missing_files"] = {
        "count": len(missing_files),
        "files": missing_files[:20] if args.verbose else [],
    }
    results["orphaned_files"] = {
        "count": len(orphaned_files),
        "files": sorted(orphaned_files)[:20] if args.verbose else [],
    }
    
    # Overall health
    issues = []
    if not results["id_management"]["correct"]:
        issues.append(f"nextArticleId should be {expected_next}")
    if dup_json_dates:
        issues.append(f"{len(dup_json_dates)} duplicate JSON dates")
    if dup_fm_dates:
        issues.append(f"{len(dup_fm_dates)} duplicate frontmatter dates")
    if date_mismatches:
        issues.append(f"{len(date_mismatches)} date mismatches")
    if missing_files:
        issues.append(f"{len(missing_files)} missing content files")
    if orphaned_files:
        issues.append(f"{len(orphaned_files)} orphaned content files")
    
    results["health"] = {
        "status": "healthy" if not issues else "issues_found",
        "issues": issues,
    }
    
    _print_json(results)


def _cmd_fix_next_id(args: argparse.Namespace) -> None:
    """Fix nextArticleId to be max(article_ids) + 1."""
    root = _workspace_root(args.workspace_root)
    website_root = (Path(root) / args.website_path).resolve()
    
    # Support both old structure and new structure (.github/automation/)
    articles_paths = [
        website_root / "articles.json",
        website_root / ".github" / "automation" / "articles.json",
    ]
    articles_path = None
    for p in articles_paths:
        if p.exists():
            articles_path = p
            break
    
    if not articles_path:
        raise SystemExit(f"articles.json not found in {website_root} or {website_root}/.github/automation/")
    
    try:
        with open(articles_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        raise SystemExit(f"Failed to read {articles_path}: {e}")
    
    articles = data.get('articles', [])
    max_id = max((a.get('id', 0) for a in articles if isinstance(a, dict)), default=0)
    expected_next = max_id + 1
    current_next = data.get('nextArticleId')
    
    result = {
        "articles_json": str(articles_path),
        "current_nextArticleId": current_next,
        "max_article_id": max_id,
        "expected_nextArticleId": expected_next,
        "already_correct": current_next == expected_next,
    }
    
    if current_next == expected_next:
        result["action"] = "none_needed"
        _print_json(result)
        return
    
    if args.dry_run:
        result["action"] = "would_fix"
        result["note"] = "Run without --dry-run to apply fix"
        _print_json(result)
        return
    
    # Apply fix
    data['nextArticleId'] = expected_next
    try:
        with open(articles_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        result["action"] = "fixed"
        result["success"] = True
    except Exception as e:
        result["action"] = "failed"
        result["error"] = str(e)
        result["success"] = False
    
    _print_json(result)


def _cmd_sync_and_validate_local(args: argparse.Namespace) -> None:
    """Repo-local sync + validation without registry-based ops."""
    root = _workspace_root(args.workspace_root)
    website_root = (Path(root) / args.website_path).resolve()
    articles_path = website_root / "articles.json"
    content_dir = website_root / "content"

    if not articles_path.exists():
        raise SystemExit(f"articles.json not found: {articles_path}")
    if not content_dir.exists():
        workspace_cfg_path = Path(root) / "seo_workspace.json"
        if workspace_cfg_path.exists():
            try:
                cfg = json.loads(workspace_cfg_path.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
            cfg_content_dir = str((cfg or {}).get("content_dir") or "").strip()
            if cfg_content_dir:
                candidate = Path(cfg_content_dir).expanduser()
                if not candidate.is_absolute():
                    candidate = (Path(root).parent / candidate).resolve()
                else:
                    candidate = candidate.resolve()
                if candidate.exists():
                    content_dir = candidate

    if not content_dir.exists():
        raise SystemExit(f"content directory not found: {content_dir}")

    try:
        doc = json.loads(articles_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Failed to read articles.json: {exc}") from exc

    articles = doc.get("articles", []) if isinstance(doc, dict) else []
    if not isinstance(articles, list):
        raise SystemExit("articles.json must contain an object with an 'articles' list")

    content_files = {
        p.name: p
        for p in content_dir.glob("*")
        if p.is_file() and p.suffix.lower() in {".md", ".mdx"}
    }

    referenced: list[str] = []
    seen_references: set[str] = set()
    duplicate_references: list[dict[str, object]] = []
    missing_files: list[dict[str, object]] = []
    malformed_file_refs: list[dict[str, object]] = []
    date_mismatches: list[dict[str, object]] = []
    sync_changes: list[dict[str, object]] = []

    apply_sync = bool(args.apply_sync) and not bool(args.dry_run)

    for article in articles:
        article_id = article.get("id")
        title = article.get("title")
        file_ref = str(article.get("file") or "").strip()
        basename = Path(file_ref).name if file_ref else ""

        if not basename:
            malformed_file_refs.append(
                {"id": article_id, "title": title, "file": file_ref or None, "reason": "missing_file_field"}
            )
            continue

        if basename in seen_references:
            duplicate_references.append({"id": article_id, "title": title, "basename": basename})
        else:
            seen_references.add(basename)
            referenced.append(basename)

        file_path = content_files.get(basename)
        if not file_path:
            missing_files.append({"id": article_id, "title": title, "file": file_ref, "basename": basename})
            continue

        expected_date = str(article.get("published_date") or "").strip()
        if not expected_date:
            continue

        text = file_path.read_text(encoding="utf-8")
        fm_match = re.match(r"^---\n([\s\S]*?)\n---\n?", text)
        if not fm_match:
            continue

        fm_block = fm_match.group(1)
        current_match = re.search(r'^date:\s*"([^"]+)"\s*$', fm_block, re.MULTILINE)
        if not current_match:
            current_match = re.search(r"^date:\s*([^\n]+?)\s*$", fm_block, re.MULTILINE)
        current_date = current_match.group(1).strip().strip('"').strip("'") if current_match else ""

        if current_date == expected_date:
            continue

        date_mismatches.append(
            {
                "id": article_id,
                "title": title,
                "basename": basename,
                "current_date": current_date or None,
                "expected_date": expected_date,
            }
        )

        if not apply_sync:
            continue

        old_frontmatter = fm_match.group(0)
        if current_match:
            new_fm_block = re.sub(
                r'^date:\s*([^\n]+?)\s*$',
                f'date: "{expected_date}"',
                fm_block,
                count=1,
                flags=re.MULTILINE,
            )
        elif re.search(r'^title:\s*([^\n]+?)\s*$', fm_block, re.MULTILINE):
            new_fm_block = re.sub(
                r'^title:\s*([^\n]+?)\s*$',
                r'\g<0>' + f'\ndate: "{expected_date}"',
                fm_block,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            new_fm_block = fm_block + f'\ndate: "{expected_date}"'

        new_frontmatter = f"---\n{new_fm_block}\n---\n"
        new_text = text.replace(old_frontmatter, new_frontmatter, 1)
        file_path.write_text(new_text, encoding="utf-8")
        sync_changes.append({"id": article_id, "basename": basename, "new_date": expected_date})

    orphan_files = sorted([name for name in content_files.keys() if name not in seen_references])

    summary = {
        "checked_entries": len(articles),
        "content_files": len(content_files),
        "missing_files": len(missing_files),
        "orphan_files": len(orphan_files),
        "malformed_file_refs": len(malformed_file_refs),
        "duplicate_file_refs": len(duplicate_references),
        "date_mismatches": len(date_mismatches),
        "dates_synced": len(sync_changes),
        "next_action": "",
    }

    if summary["missing_files"] > 0:
        summary["next_action"] = "Fix missing content files referenced by articles.json"
    elif summary["malformed_file_refs"] > 0:
        summary["next_action"] = "Fix malformed file references in articles.json"
    elif summary["date_mismatches"] > 0 and not apply_sync:
        summary["next_action"] = "Run with --apply-sync --dry-run false to sync frontmatter dates"
    elif summary["orphan_files"] > 0:
        summary["next_action"] = "Review orphan content files not referenced in articles.json"
    else:
        summary["next_action"] = "Index and content are in sync"

    result = {
        "ok": True,
        "mode": "apply" if apply_sync else "preview",
        "workspace_root": root,
        "website_path": args.website_path,
        "summary": summary,
        "issues": {
            "missing_files": missing_files,
            "orphan_files": orphan_files,
            "malformed_file_refs": malformed_file_refs,
            "duplicate_file_refs": duplicate_references,
            "date_mismatches": date_mismatches,
        },
        "sync_changes": sync_changes,
    }

    if getattr(args, "compact", False):
        result = {
            "ok": result.get("ok"),
            "mode": result.get("mode"),
            "website_path": result.get("website_path"),
            "checked_entries": summary.get("checked_entries", 0),
            "missing_files": summary.get("missing_files", 0),
            "orphan_files": summary.get("orphan_files", 0),
            "date_mismatches": summary.get("date_mismatches", 0),
            "dates_synced": summary.get("dates_synced", 0),
            "next_action": summary.get("next_action", ""),
        }

    _print_json(result)


def _cmd_ops_sync_and_optimize(args: argparse.Namespace) -> None:
    from .seo_ops import SEOOps

    root = _workspace_root(args.workspace_root)
    ops = SEOOps(root)
    site = ops.get_site_by_id(args.website_id)
    if not site:
        raise SystemExit(f"Unknown website_id: {args.website_id}")
    statuses = [s.strip() for s in (args.statuses or []) if s.strip()]
    res = ops.sync_and_optimize(
        site,
        auto_fix=bool(args.auto_fix),
        spacing_days=int(args.spacing_days),
        max_recent_days=int(args.max_recent_days),
        dry_run=bool(args.dry_run),
        auto_deploy=bool(args.auto_deploy),
        target_statuses=statuses or None,
    )
    if getattr(args, "compact", False):
        res = _compact_sync_and_optimize(res)
    _print_json(res)


def _cmd_ops_sync_and_validate(args: argparse.Namespace) -> None:
    from .seo_ops import SEOOps

    root = _workspace_root(args.workspace_root)
    ops = SEOOps(root)
    site = ops.get_site_by_id(args.website_id)
    if not site:
        raise SystemExit(f"Unknown website_id: {args.website_id}")
    res = ops.sync_and_validate(
        site,
        apply_sync=bool(args.apply_sync),
        dry_run=bool(args.dry_run),
    )
    if getattr(args, "compact", False):
        res = _compact_sync_and_validate(res)
    _print_json(res)


def _cmd_research_keywords(args: argparse.Namespace) -> None:
    """End-to-end keyword research: generate → dedupe → optionally analyze difficulty."""
    import subprocess

    from .server import _filter_new_keywords

    root = _workspace_root(args.workspace_root)

    # Step 1: Collect themes
    themes: list[str] = []
    if args.themes:
        themes.extend(args.themes)
    if args.themes_file:
        if args.themes_file == "-":
            text = sys.stdin.read()
        else:
            text = Path(args.themes_file).read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                themes.append(line)
    if not themes:
        sys.stderr.write("Error: no themes provided. Use --themes or --themes-file.\n")
        raise SystemExit(1)

    # Step 2: Generate keywords via seo-cli batch-keyword-generator
    # Stream stderr so the agent sees per-theme progress in real-time
    sys.stderr.write(f"[research-keywords] Generating keywords for {len(themes)} themes (expect ~15s per theme)...\n")
    sys.stderr.flush()
    gen_cmd = [
        "seo-cli", "batch-keyword-generator",
        "--themes", *themes,
        "--output-format", "flat",
        "--country", args.country,
    ]
    try:
        gen_result = subprocess.run(gen_cmd, stdout=subprocess.PIPE, stderr=None, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        _print_json({"error": "keyword generation timed out after 180s", "themes": themes})
        raise SystemExit(1)
    if gen_result.returncode != 0:
        _print_json({"error": "keyword generation failed", "returncode": gen_result.returncode})
        raise SystemExit(1)

    candidates = [line.strip() for line in gen_result.stdout.splitlines() if line.strip()]
    sys.stderr.write(f"[research-keywords] Generated {len(candidates)} unique candidate keywords\n")

    if not candidates:
        _print_json({
            "themes": themes,
            "total_candidates": 0,
            "new_keywords": [],
            "filtered_out": 0,
            "difficulty": None,
        })
        return

    # Step 3: Dedupe against existing articles
    sys.stderr.write(f"[research-keywords] Filtering against existing articles in {args.website_path}...\n")
    filter_res = _filter_new_keywords(
        workspace_root=root,
        website_path=args.website_path,
        keywords=candidates,
        enable_fuzzy=not bool(args.disable_fuzzy),
        fuzzy_threshold=float(args.fuzzy_threshold),
    )
    new_keywords = filter_res.new_keywords
    sys.stderr.write(f"[research-keywords] {len(new_keywords)} new keywords (filtered out {len(filter_res.matches)})\n")

    # Step 4: Optionally analyze difficulty
    difficulty = None
    if args.analyze_difficulty and new_keywords:
        kw_to_analyze = new_keywords
        if args.top_n and args.top_n > 0:
            kw_to_analyze = new_keywords[:args.top_n]
            if len(new_keywords) > args.top_n:
                sys.stderr.write(f"[research-keywords] --top-n {args.top_n}: analyzing {len(kw_to_analyze)} of {len(new_keywords)} new keywords\n")
        est_time = len(kw_to_analyze) * 15
        timeout_secs = max(300, len(kw_to_analyze) * 20 + 60)
        sys.stderr.write(f"[research-keywords] Analyzing difficulty for {len(kw_to_analyze)} keywords (~{est_time}s estimated, timeout {timeout_secs}s)...\n")
        sys.stderr.flush()
        diff_cmd = [
            "seo-cli", "batch-keyword-difficulty",
            "--keywords-file", "-",
            "--country", args.country,
        ]
        try:
            diff_result = subprocess.run(
                diff_cmd, input="\n".join(kw_to_analyze),
                stdout=subprocess.PIPE, stderr=None, text=True, timeout=timeout_secs,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write("[research-keywords] Warning: difficulty analysis timed out after 300s\n")
            diff_result = None
        if diff_result and diff_result.returncode == 0:
            try:
                difficulty = json.loads(diff_result.stdout)
            except json.JSONDecodeError:
                sys.stderr.write("[research-keywords] Warning: could not parse difficulty output\n")
        else:
            sys.stderr.write(f"[research-keywords] Warning: difficulty analysis failed\n")

    # Step 5: Optionally auto-append viable keywords as drafts
    appended = None
    if args.auto_append:
        from .server import DraftArticleInput, _append_draft_articles

        viable = []

        if difficulty is not None and isinstance(difficulty, list):
            # We have difficulty data — filter by min-volume / max-kd
            for entry in difficulty:
                kd_val = entry.get("difficulty", 999)
                vol_val = entry.get("volume", 0)
                try:
                    kd_val = int(kd_val) if kd_val is not None else 999
                except (ValueError, TypeError):
                    kd_val = 999
                try:
                    vol_val = int(vol_val) if vol_val is not None else 0
                except (ValueError, TypeError):
                    vol_val = 0
                if kd_val <= args.max_kd and vol_val >= args.min_volume:
                    kw = entry.get("keyword", "")
                    title = kw.strip().title() if kw else "Untitled"
                    viable.append(DraftArticleInput(
                        title=title,
                        target_keyword=kw,
                        keyword_difficulty=kd_val,
                        target_volume=vol_val,
                        estimated_traffic_monthly="",
                    ))
        elif new_keywords:
            # No difficulty data available — append all new keywords as drafts
            # (difficulty analysis was skipped or failed)
            kw_to_append = new_keywords
            if args.top_n and args.top_n > 0:
                kw_to_append = new_keywords[:args.top_n]
            sys.stderr.write(f"[research-keywords] No difficulty data available — appending {len(kw_to_append)} new keywords as drafts (KD/volume unknown)\n")
            for kw in kw_to_append:
                title = kw.strip().title() if kw else "Untitled"
                viable.append(DraftArticleInput(
                    title=title,
                    target_keyword=kw,
                    keyword_difficulty="",
                    target_volume=0,
                    estimated_traffic_monthly="",
                ))

        if viable:
            sys.stderr.write(f"[research-keywords] Auto-appending {len(viable)} drafts...\n")
            append_res = _append_draft_articles(
                workspace_root=root,
                website_path=args.website_path,
                drafts=viable,
                enable_dedupe=not bool(args.disable_fuzzy),
                fuzzy_threshold=float(args.fuzzy_threshold),
            )
            appended = append_res.model_dump()
            sys.stderr.write(f"[research-keywords] Appended {len(append_res.added_ids)} draft articles (IDs: {append_res.added_ids})\n")
        else:
            sys.stderr.write(f"[research-keywords] No keywords to auto-append\n")

    # Output combined result
    output: dict = {
        "themes": themes,
        "total_candidates": len(candidates),
        "new_keywords": new_keywords,
        "filtered_out": len(filter_res.matches),
        "filter_details": filter_res.model_dump(),
    }
    if difficulty is not None:
        output["difficulty"] = difficulty
        if args.top_n and args.top_n > 0 and len(new_keywords) > args.top_n:
            output["difficulty_analyzed_count"] = args.top_n
            output["difficulty_skipped_keywords"] = new_keywords[args.top_n:]
    if appended is not None:
        output["appended"] = appended
    _print_json(output)


# ---------------------------------------------------------------------------
# Clustering & Linking commands (Step 3)
# ---------------------------------------------------------------------------

def _cmd_scan_internal_links(args: argparse.Namespace) -> None:
    from .clustering_linking import scan_internal_links

    root = _workspace_root(args.workspace_root)
    res = scan_internal_links(root, args.website_path)
    output: dict = {
        "website_path": res.website_path,
        "total_articles": res.total_articles,
        "total_internal_links": res.total_internal_links,
        "articles_with_outgoing": res.articles_with_outgoing,
        "articles_with_incoming": res.articles_with_incoming,
        "orphan_articles": res.orphan_articles,
    }
    if args.verbose:
        output["profiles"] = [
            {
                "id": p.id,
                "title": p.title,
                "file": p.file,
                "outgoing_ids": p.outgoing_ids,
                "incoming_ids": p.incoming_ids,
                "outgoing_links": p.outgoing_links,
                "unresolved_links": p.unresolved_links,
            }
            for p in res.profiles
            if p.outgoing_ids or p.incoming_ids or p.unresolved_links or args.show_all
        ]
    _print_json(output)


def _cmd_generate_linking_plan(args: argparse.Namespace) -> None:
    from .clustering_linking import generate_linking_plan

    root = _workspace_root(args.workspace_root)
    clusters_json = None
    if args.clusters_json:
        if args.clusters_json == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(args.clusters_json).read_text(encoding="utf-8")
        clusters_json = json.loads(raw)

    res = generate_linking_plan(
        root,
        args.website_path,
        brief_path=args.brief_path,
        clusters_json=clusters_json,
    )
    output: dict = {
        "website_path": res.website_path,
        "total_planned": res.total_planned,
        "already_linked": res.already_linked,
        "missing_links": res.missing_links,
    }
    if args.missing_only:
        output["items"] = [
            {
                "source_id": it.source_id,
                "source_title": it.source_title,
                "target_id": it.target_id,
                "target_title": it.target_title,
                "link_type": it.link_type,
            }
            for it in res.items if not it.already_exists
        ]
    else:
        output["items"] = [
            {
                "source_id": it.source_id,
                "source_title": it.source_title,
                "source_file": it.source_file,
                "target_id": it.target_id,
                "target_title": it.target_title,
                "target_file": it.target_file,
                "link_type": it.link_type,
                "already_exists": it.already_exists,
            }
            for it in res.items
        ]
    _print_json(output)


def _cmd_add_article_links(args: argparse.Namespace) -> None:
    from .clustering_linking import add_article_links

    root = _workspace_root(args.workspace_root)
    target_ids = [int(t) for t in args.target_ids]
    res = add_article_links(
        root,
        args.website_path,
        source_id=int(args.source_id),
        target_ids=target_ids,
        mode=args.mode,
        dry_run=bool(args.dry_run),
    )
    _print_json({
        "source_id": res.source_id,
        "source_file": res.source_file,
        "mode": res.mode,
        "links_added": res.links_added,
        "links_skipped": res.links_skipped,
        "dry_run": bool(args.dry_run),
    })


def _cmd_get_article_content(args: argparse.Namespace) -> None:
    from .clustering_linking import get_article_content

    root = _workspace_root(args.workspace_root)
    res = get_article_content(root, args.website_path, article_id=int(args.article_id))
    if args.metadata_only:
        res.pop("content", None)
    _print_json(res)


def _cmd_update_brief_linking_status(args: argparse.Namespace) -> None:
    from .clustering_linking import update_brief_linking_status

    root = _workspace_root(args.workspace_root)
    res = update_brief_linking_status(
        root,
        args.website_path,
        brief_path=args.brief_path,
        dry_run=bool(args.dry_run),
    )
    _print_json({
        "brief_path": res.brief_path,
        "items_checked": res.items_checked,
        "items_already_done": res.items_already_done,
        "items_still_pending": res.items_still_pending,
        "dry_run": bool(args.dry_run),
    })


def _cmd_batch_add_links(args: argparse.Namespace) -> None:
    """Batch: add all missing links from the linking plan at once."""
    from .clustering_linking import add_article_links, generate_linking_plan

    root = _workspace_root(args.workspace_root)
    clusters_json = None
    if args.clusters_json:
        if args.clusters_json == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(args.clusters_json).read_text(encoding="utf-8")
        clusters_json = json.loads(raw)

    plan = generate_linking_plan(
        root,
        args.website_path,
        brief_path=args.brief_path,
        clusters_json=clusters_json,
    )

    # Group missing links by source
    missing_by_source: dict[int, list[int]] = {}
    for it in plan.items:
        if not it.already_exists:
            missing_by_source.setdefault(it.source_id, []).append(it.target_id)

    total_added = 0
    total_skipped = 0
    results: list[dict] = []
    for source_id, target_ids in sorted(missing_by_source.items()):
        try:
            res = add_article_links(
                root,
                args.website_path,
                source_id=source_id,
                target_ids=target_ids,
                mode=args.mode,
                dry_run=bool(args.dry_run),
            )
            total_added += len(res.links_added)
            total_skipped += len(res.links_skipped)
            results.append({
                "source_id": source_id,
                "links_added": len(res.links_added),
                "links_skipped": len(res.links_skipped),
            })
        except Exception as e:
            results.append({
                "source_id": source_id,
                "error": str(e),
            })
            sys.stderr.write(f"[batch-add-links] Error on article {source_id}: {e}\n")

    _print_json({
        "website_path": args.website_path,
        "mode": args.mode,
        "dry_run": bool(args.dry_run),
        "total_sources": len(missing_by_source),
        "total_links_added": total_added,
        "total_links_skipped": total_skipped,
        "results": results,
    })


def _cmd_ops_schedule_preview(args: argparse.Namespace) -> None:
    from .seo_ops import SEOOps

    root = _workspace_root(args.workspace_root)
    ops = SEOOps(root)
    site = ops.get_site_by_id(args.website_id)
    if not site:
        raise SystemExit(f"Unknown website_id: {args.website_id}")
    statuses = [s.strip() for s in (args.statuses or []) if s.strip()]
    res = ops.preview_date_schedule(site, spacing_days=int(args.spacing_days), statuses=statuses or None)
    if getattr(args, "compact", False):
        res = _compact_schedule_apply(res)
    _print_json(res)


def _cmd_ops_schedule_apply(args: argparse.Namespace) -> None:
    from .seo_ops import SEOOps

    root = _workspace_root(args.workspace_root)
    ops = SEOOps(root)
    site = ops.get_site_by_id(args.website_id)
    if not site:
        raise SystemExit(f"Unknown website_id: {args.website_id}")
    statuses = [s.strip() for s in (args.statuses or []) if s.strip()]
    res = ops.apply_date_schedule(site, spacing_days=int(args.spacing_days), statuses=statuses or None)
    if getattr(args, "compact", False):
        res = _compact_schedule_apply(res)
    _print_json(res)


def _cmd_ops_pull_from_repo(args: argparse.Namespace) -> None:
    from .seo_ops import SEOOps

    root = _workspace_root(args.workspace_root)
    ops = SEOOps(root)
    site = ops.get_site_by_id(args.website_id)
    if not site:
        raise SystemExit(f"Unknown website_id: {args.website_id}")
    res = ops.pull_content_from_repo(site, dry_run=bool(args.dry_run))
    if getattr(args, "compact", False):
        res = _compact_pull_from_repo(res)
    _print_json(res)


def _cmd_ops_deploy_files(args: argparse.Namespace) -> None:
    from .seo_ops import SEOOps

    root = _workspace_root(args.workspace_root)
    ops = SEOOps(root)
    site = ops.get_site_by_id(args.website_id)
    if not site:
        raise SystemExit(f"Unknown website_id: {args.website_id}")
    files = [str(f) for f in (args.files or []) if str(f).strip()]
    if not files:
        raise SystemExit("--files must be provided (one or more basenames)")
    res = ops.deploy_files_to_repo(
        site,
        files=files,
        dry_run=bool(args.dry_run),
        allow_overwrite=bool(args.allow_overwrite),
    )
    if getattr(args, "compact", False):
        res = _compact_deploy_files(res)
    _print_json(res)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="seo-content-cli", description="SEO content operations without MCP")
    p.add_argument("--workspace-root", default=None, help="Override workspace root auto-detection")
    sp = p.add_subparsers(dest="cmd", required=True)

    vc = sp.add_parser("validate-content", help="Validate content (read-only)")
    vc.add_argument("--website-path", required=True, help="e.g. general/expense")
    vc.set_defaults(func=_cmd_validate_content)

    cc = sp.add_parser("clean-content", help="Clean content (writes unless --dry-run)")
    cc.add_argument("--website-path", required=True)
    cc.add_argument("--dry-run", action="store_true")
    cc.set_defaults(func=_cmd_clean_content)

    ad = sp.add_parser("analyze-dates", help="Analyze dates (read-only)")
    ad.add_argument("--website-path", required=True)
    ad.set_defaults(func=_cmd_analyze_dates)

    fd = sp.add_parser("fix-dates", help="Fix recent date issues (writes unless --dry-run)")
    fd.add_argument("--website-path", required=True)
    fd.add_argument("--dry-run", action="store_true")
    fd.set_defaults(func=_cmd_fix_dates)

    td = sp.add_parser("test-distribution", help="Preview distribution")
    td.add_argument("--project-name", required=True)
    td.add_argument("--article-count", type=int, required=True)
    td.add_argument("--earliest-date", required=True, help="YYYY-MM-DD")
    td.set_defaults(func=_cmd_test_distribution)

    summ = sp.add_parser("articles-summary", help="Summarize articles.json")
    summ.add_argument("--website-path", required=True)
    summ.set_defaults(func=_cmd_articles_summary)

    idx = sp.add_parser("articles-index", help="List articles from articles.json")
    idx.add_argument("--website-path", required=True)
    idx.add_argument("--status", default=None, help="Optional status filter")
    idx.add_argument(
        "--format",
        default="json",
        choices=["json", "lines"],
        help="Output format. Use 'lines' with --field to avoid jq/pipes.",
    )
    idx.add_argument("--field", default="", help="With --format lines: which item field to print (e.g. target_keyword)")
    idx.add_argument("--unique", action="store_true", help="With --format lines: dedupe values")
    idx.add_argument("--sort", action="store_true", help="With --format lines: sort values lexicographically")
    idx.add_argument("--limit", type=int, default=0, help="With --format lines: max number of lines to print (0=all)")
    idx.set_defaults(func=_cmd_articles_index)

    fnk = sp.add_parser("filter-new-keywords", help="Filter candidates against existing target_keyword")
    fnk.add_argument("--website-path", required=True)
    fnk.add_argument("--keywords", nargs="*", default=[])
    fnk.add_argument("--keywords-file", default=None, help="One keyword per line (use '-' for stdin)")
    fnk.add_argument("--disable-fuzzy", action="store_true")
    fnk.add_argument("--fuzzy-threshold", type=float, default=0.92)
    fnk.set_defaults(func=_cmd_filter_new_keywords)

    ada = sp.add_parser("append-draft-articles", help="Append drafts to articles.json")
    ada.add_argument("--website-path", required=True)
    ada.add_argument("--drafts-json", required=True, help="JSON list or {drafts:[...]} file path (use '-' for stdin)")
    ada.add_argument("--disable-dedupe", action="store_true")
    ada.add_argument("--fuzzy-threshold", type=float, default=0.92)
    ada.set_defaults(func=_cmd_append_draft_articles)

    rk = sp.add_parser("research-keywords",
                        help="End-to-end: generate keywords from themes → dedupe vs articles.json → optionally analyze difficulty")
    rk.add_argument("--website-path", required=True, help="e.g. general/expense")
    rk.add_argument("--themes", nargs="*", default=[], help="Theme keywords (seed phrases)")
    rk.add_argument("--themes-file", default=None,
                    help="File with one theme per line (use '-' for stdin)")
    rk.add_argument("--country", default="us")
    rk.add_argument("--analyze-difficulty", action="store_true",
                    help="Also run batch keyword difficulty analysis on new keywords")
    rk.add_argument("--top-n", type=int, default=None,
                    help="Only analyze difficulty for the first N new keywords (use with --analyze-difficulty to bound runtime)")
    rk.add_argument("--auto-append", action="store_true",
                    help="Automatically append viable keywords as draft articles to articles.json. With difficulty data: filters by --min-volume/--max-kd. Without: appends all new keywords.")
    rk.add_argument("--min-volume", type=int, default=500,
                    help="Minimum monthly search volume for auto-append (default: 500)")
    rk.add_argument("--max-kd", type=int, default=30,
                    help="Maximum keyword difficulty for auto-append (default: 30)")
    rk.add_argument("--disable-fuzzy", action="store_true")
    rk.add_argument("--fuzzy-threshold", type=float, default=0.92)
    rk.set_defaults(func=_cmd_research_keywords)

    gabk = sp.add_parser("get-articles-by-keyword", help="Find existing articles matching keyword")
    gabk.add_argument("--website-path", required=True)
    gabk.add_argument("--keyword", required=True)
    gabk.add_argument("--disable-fuzzy", action="store_true")
    gabk.add_argument("--fuzzy-threshold", type=float, default=0.92)
    gabk.set_defaults(func=_cmd_get_articles_by_keyword)

    nxt = sp.add_parser("get-next-content-task", help="Pick next task from brief or drafts")
    nxt.add_argument("--website-path", required=True)
    nxt.add_argument("--brief-path", default=None)
    nxt.add_argument("--priority", default="HIGH PRIORITY")
    nxt.set_defaults(func=_cmd_get_next_content_task)

    plan = sp.add_parser("plan-content-article", help="Plan metadata + filename + frontmatter")
    plan.add_argument("--website-path", required=True)
    plan.add_argument("--brief-path", default=None)
    plan.add_argument("--task-id", default=None)
    plan.add_argument("--priority", default="HIGH PRIORITY")
    plan.add_argument("--extension", default="mdx")
    plan.set_defaults(func=_cmd_plan_content_article)

    pub = sp.add_parser("publish-article-and-complete-task", help="Upsert articles.json + mark brief task completed")
    pub.add_argument("--website-path", required=True)
    pub.add_argument("--task-id", required=True)
    pub.add_argument("--from-plan", action="store_true",
                     help="Auto-populate all metadata from plan-content-article (no JSON needed). Auto-detects word count from MDX file.")
    pub.add_argument("--article-json", default=None, help="Path to JSON object for the article entry (use '-' for stdin). Not needed with --from-plan.")
    pub.add_argument("--title", default=None, help="Override article title (only with --from-plan)")
    pub.add_argument("--word-count", type=int, default=None, help="Override auto-detected word count (only with --from-plan)")
    pub.add_argument("--brief-path", default=None)
    pub.add_argument("--status", default="ready_to_publish")
    pub.set_defaults(func=_cmd_publish_article_and_complete_task)

    # -- Clustering & Linking (Step 3) ------------------------------------

    sil = sp.add_parser("scan-internal-links",
                         help="Scan all content files and build the internal link graph (read-only)")
    sil.add_argument("--website-path", required=True)
    sil.add_argument("--verbose", action="store_true",
                     help="Include per-article link profiles in output")
    sil.add_argument("--show-all", action="store_true",
                     help="With --verbose, show profiles even for articles with no links")
    sil.set_defaults(func=_cmd_scan_internal_links)

    glp = sp.add_parser("generate-linking-plan",
                         help="Generate hub-spoke linking plan from clusters in the brief (read-only)")
    glp.add_argument("--website-path", required=True)
    glp.add_argument("--brief-path", default=None,
                     help="Path to content brief (auto-detected if omitted)")
    glp.add_argument("--clusters-json", default=None,
                     help="JSON file with cluster definitions (use '-' for stdin). "
                          "Format: [{cluster_id, name, pillar_id, support_ids}]")
    glp.add_argument("--missing-only", action="store_true",
                     help="Only show links that are missing (not already present)")
    glp.set_defaults(func=_cmd_generate_linking_plan)

    aal = sp.add_parser("add-article-links",
                         help="Add internal links from one article to target articles")
    aal.add_argument("--website-path", required=True)
    aal.add_argument("--source-id", required=True, type=int,
                     help="Article ID to add links into")
    aal.add_argument("--target-ids", required=True, nargs="+", type=int,
                     help="Target article IDs to link to")
    aal.add_argument("--mode", choices=["related-section", "inline"], default="related-section",
                     help="How to add links (default: related-section)")
    aal.add_argument("--dry-run", action="store_true",
                     help="Preview what would be added without writing")
    aal.set_defaults(func=_cmd_add_article_links)

    gac = sp.add_parser("get-article-content",
                         help="Get article metadata + MDX content by article ID")
    gac.add_argument("--website-path", required=True)
    gac.add_argument("--article-id", required=True, type=int)
    gac.add_argument("--metadata-only", action="store_true",
                     help="Return metadata without MDX content body")
    gac.set_defaults(func=_cmd_get_article_content)

    ubls = sp.add_parser("update-brief-linking-status",
                          help="Scan actual links and update ☐ → ✅ in the brief checklist")
    ubls.add_argument("--website-path", required=True)
    ubls.add_argument("--brief-path", default=None)
    ubls.add_argument("--dry-run", action="store_true",
                      help="Preview changes without writing")
    ubls.set_defaults(func=_cmd_update_brief_linking_status)

    bal = sp.add_parser("batch-add-links",
                         help="Add ALL missing links from the linking plan at once")
    bal.add_argument("--website-path", required=True)
    bal.add_argument("--brief-path", default=None)
    bal.add_argument("--clusters-json", default=None,
                     help="JSON file with cluster definitions (use '-' for stdin)")
    bal.add_argument("--mode", choices=["related-section", "inline"], default="related-section",
                     help="How to add links (default: related-section)")
    bal.add_argument("--dry-run", action="store_true")
    bal.set_defaults(func=_cmd_batch_add_links)

    # Repo-local sync + validation (no registry required)
    diag = sp.add_parser("diagnose", help="Comprehensive diagnostic of articles.json vs content files")
    diag.add_argument("--website-path", required=True, help="Path to website folder (e.g. . or general/coffee)")
    diag.add_argument("--verbose", action="store_true", help="Include full lists of mismatches/orphans")
    diag.set_defaults(func=_cmd_diagnose)

    fni = sp.add_parser("fix-next-id", help="Fix nextArticleId to be max(article_ids) + 1")
    fni.add_argument("--website-path", required=True, help="Path to website folder")
    fni.add_argument("--dry-run", action="store_true", help="Preview only, don't modify")
    fni.set_defaults(func=_cmd_fix_next_id)

    sv_local = sp.add_parser("sync-and-validate", help="Validate index/content gaps and optionally sync frontmatter dates")
    sv_local.add_argument("--website-path", required=True, help="e.g. . or general/expense")
    sv_local.add_argument("--apply-sync", action="store_true", help="Apply frontmatter date sync from articles.json")
    sv_local.add_argument("--dry-run", action="store_true", help="Preview only (default behavior)")
    sv_local.add_argument("--compact", action="store_true", help="Output only summary fields")
    sv_local.set_defaults(func=_cmd_sync_and_validate_local)

    # -- Ops (registry-driven) --------------------------------------------

    ops = sp.add_parser("ops", help="Registry-driven SEO ops")
    ops_sp = ops.add_subparsers(dest="ops_cmd", required=True)

    pull = ops_sp.add_parser("pull-from-repo", help="Pull content files from production repo to automation (run FIRST in Step 4)")
    pull.add_argument("--website-id", required=True)
    pull.add_argument("--dry-run", action="store_true", help="Preview only, don't copy files")
    pull.add_argument("--compact", action="store_true", help="Output only decision-relevant fields (no protected_basenames or details)")
    pull.set_defaults(func=_cmd_ops_pull_from_repo)

    dep = ops_sp.add_parser("deploy-files", help="Deploy selected content basenames from automation to production repo (explicit, scoped)")
    dep.add_argument("--website-id", required=True)
    dep.add_argument("--files", nargs="+", required=True, help="One or more basenames, e.g. 40_foo.mdx 41_bar.md")
    dep.add_argument("--dry-run", action="store_true", help="Preview only, don't copy files")
    dep.add_argument("--allow-overwrite", action="store_true", help="Allow overwriting existing files in production")
    dep.add_argument("--compact", action="store_true", help="Output only decision-relevant fields")
    dep.set_defaults(func=_cmd_ops_deploy_files)

    schp = ops_sp.add_parser("schedule-preview", help="Preview date scheduling")
    schp.add_argument("--website-id", required=True)
    schp.add_argument("--spacing-days", type=int, default=2)
    schp.add_argument("--statuses", nargs="*", default=[])
    schp.add_argument("--compact", action="store_true", help="Output only summary (no full schedule list)")
    schp.set_defaults(func=_cmd_ops_schedule_preview)

    scha = ops_sp.add_parser("schedule-apply", help="Apply date scheduling")
    scha.add_argument("--website-id", required=True)
    scha.add_argument("--spacing-days", type=int, default=2)
    scha.add_argument("--statuses", nargs="*", default=[])
    scha.add_argument("--compact", action="store_true", help="Output only summary (no full schedule list)")
    scha.set_defaults(func=_cmd_ops_schedule_apply)

    sync = ops_sp.add_parser("sync-and-optimize", help="Unified sync/analyze/fix/validate/deploy")
    sync.add_argument("--website-id", required=True)
    sync.add_argument("--auto-fix", action="store_true")
    sync.add_argument("--spacing-days", type=int, default=2)
    sync.add_argument("--max-recent-days", type=int, default=14)
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--auto-deploy", action="store_true")
    sync.add_argument("--statuses", nargs="*", default=[])
    sync.add_argument("--compact", action="store_true", help="Output only summary (no phase details)")
    sync.set_defaults(func=_cmd_ops_sync_and_optimize)

    sv = ops_sp.add_parser("sync-and-validate", help="Focused sync + index/file validation (no scheduling/deploy)")
    sv.add_argument("--website-id", required=True)
    sv.add_argument("--apply-sync", action="store_true", help="Apply import sync to articles.json instead of preview")
    sv.add_argument("--dry-run", action="store_true", help="Preview only. Writes happen only with --apply-sync and --dry-run false")
    sv.add_argument("--compact", action="store_true", help="Output only summary (no phase details)")
    sv.set_defaults(func=_cmd_ops_sync_and_validate)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
