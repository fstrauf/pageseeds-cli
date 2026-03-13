"""Unified PageSeeds CLI - Single entrypoint for all commands.

This module consolidates all functionality from:
- automation-cli (repo, reddit, geo, campaign, seo/gsc, posthog, skills)
- seo-cli (keyword research, backlinks, traffic)
- seo-content-cli (content validation, cleaning, date management, linking, ops)

Usage:
    pageseeds                    # Launch interactive dashboard (default)
    pageseeds seo keywords ...   # SEO keyword research
    pageseeds content validate ... # Content validation
    pageseeds automation repo ...  # Repo management
    pageseeds reddit pending ...   # Reddit opportunities
    pageseeds geo maps-lookup ...  # Geo lookup
    pageseeds version            # Check versions
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _print_json(data: object) -> None:
    import json
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")


# =============================================================================
# Version Check (built-in, no external deps)
# =============================================================================

def _cmd_version(args: argparse.Namespace) -> None:
    """Check version and update status."""
    from .version_check import check_all_packages, format_version_output, VersionInfo
    
    if args.all:
        results = check_all_packages()
        any_outdated = False
        any_errors = False
        
        for info in results:
            print(format_version_output(info))
            print()
            if info.is_outdated:
                any_outdated = True
            if info.error:
                any_errors = True
        
        if any_outdated:
            print("📦 To update:")
            print("   cd ~/automation && git pull")
        elif not any_errors:
            print("✅ All packages are up to date!")
    else:
        # Just show pageseeds-cli version
        from . import __version__
        print(f"pageseeds-cli: {__version__}")
        
        # Also check if outdated
        info = check_all_packages()[0]  # First one is automation-cli
        if info.is_outdated:
            print(f"  ⚠️  Update available: {info.local_version} → {info.remote_version}")
            print(f"     Run: cd ~/automation && git pull")


# =============================================================================
# SEO Commands (delegates to seo-cli)
# =============================================================================

def _cmd_seo_keywords(args: argparse.Namespace) -> None:
    """Generate keyword ideas."""
    try:
        from seo_mcp.server import _keyword_generator
        result = _keyword_generator(keyword=args.keyword, country=args.country, search_engine=args.search_engine)
        if args.format == "flat":
            # Extract just keyword strings
            seen: set[str] = set()
            for key in ("all", "ideas", "questionIdeas"):
                for item in result.get(key, []):
                    kw = item.get("keyword", "") if isinstance(item, dict) else str(item)
                    if kw and kw not in seen:
                        seen.add(kw)
                        print(kw)
        else:
            _print_json(result)
    except ImportError:
        print("Error: seo-mcp not installed. Run: uv tool install -e packages/seo-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_seo_difficulty(args: argparse.Namespace) -> None:
    """Analyze keyword difficulty."""
    try:
        from seo_mcp.server import _keyword_difficulty
        result = _keyword_difficulty(keyword=args.keyword, country=args.country)
        _print_json(result)
    except ImportError:
        print("Error: seo-mcp not installed. Run: uv tool install -e packages/seo-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_seo_backlinks(args: argparse.Namespace) -> None:
    """Get backlinks for a domain."""
    try:
        from seo_mcp.server import _get_backlinks_list
        result = _get_backlinks_list(domain=args.domain)
        _print_json(result)
    except ImportError:
        print("Error: seo-mcp not installed. Run: uv tool install -e packages/seo-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_seo_traffic(args: argparse.Namespace) -> None:
    """Get traffic estimates."""
    try:
        from seo_mcp.server import _get_traffic
        result = _get_traffic(domain_or_url=args.domain_or_url, country=args.country, mode=args.mode)
        _print_json(result)
    except ImportError:
        print("Error: seo-mcp not installed. Run: uv tool install -e packages/seo-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_seo_batch_keywords(args: argparse.Namespace) -> None:
    """Batch keyword generator."""
    try:
        from seo_mcp.server import _keyword_generator
        
        themes: list[str] = list(args.themes) if args.themes else []
        if args.themes_file:
            path = args.themes_file
            if path == "-":
                text = sys.stdin.read()
            else:
                text = Path(path).read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    themes.append(line)
        
        if not themes:
            print("Error: no themes provided. Use --themes or --themes-file.", file=sys.stderr)
            sys.exit(1)
        
        all_keywords: list[str] = []
        seen: set[str] = set()
        per_theme: list[dict] = []
        
        for theme in themes:
            print(f"[keyword-generator] theme: {theme}", file=sys.stderr)
            result = _keyword_generator(keyword=theme, country=args.country, search_engine=args.search_engine)
            kws = []
            for key in ("all", "ideas", "questionIdeas"):
                for item in result.get(key, []):
                    kw = item.get("keyword", "") if isinstance(item, dict) else str(item)
                    if kw and kw not in seen:
                        seen.add(kw)
                        kws.append(kw)
            all_keywords.extend(kws)
            per_theme.append({"theme": theme, "keywords_found": len(kws), "error": result.get("error")})
        
        if args.format == "flat":
            for kw in all_keywords:
                print(kw)
        else:
            _print_json({
                "themes_processed": len(themes),
                "total_unique_keywords": len(all_keywords),
                "per_theme": per_theme,
                "keywords": all_keywords,
            })
    except ImportError:
        print("Error: seo-mcp not installed. Run: uv tool install -e packages/seo-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_seo_batch_difficulty(args: argparse.Namespace) -> None:
    """Batch keyword difficulty."""
    try:
        from seo_mcp.server import _batch_keyword_difficulty
        
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
        
        if not keywords:
            print("Error: no keywords provided. Use --keywords or --keywords-file.", file=sys.stderr)
            sys.exit(1)
            
        result = _batch_keyword_difficulty(keywords=keywords, country=args.country)
        _print_json(result)
    except ImportError:
        print("Error: seo-mcp not installed. Run: uv tool install -e packages/seo-cli", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# Content Commands (delegates to seo-content-cli)
# =============================================================================

def _workspace_root(explicit: str | None) -> str:
    """Resolve workspace root, reusing detection logic from seo-content-cli."""
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    from seo_content_mcp.server import detect_workspace_root
    return str(Path(detect_workspace_root()).resolve())


def _cmd_content_validate(args: argparse.Namespace) -> None:
    """Validate content files."""
    try:
        from seo_content_mcp.content_cleaner import ContentCleaner
        
        root = _workspace_root(args.workspace_root)
        cleaner = ContentCleaner(root)
        res = cleaner.clean_website(args.website_path, dry_run=True)
        _print_json(res.get_summary() | {"issues": [i.__dict__ for i in res.issues_found]})
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_clean(args: argparse.Namespace) -> None:
    """Clean content files."""
    try:
        from seo_content_mcp.content_cleaner import ContentCleaner
        
        root = _workspace_root(args.workspace_root)
        cleaner = ContentCleaner(root)
        res = cleaner.clean_website(args.website_path, dry_run=bool(args.dry_run))
        _print_json(res.get_summary() | {"issues": [i.__dict__ for i in res.issues_found], "dry_run": bool(args.dry_run)})
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_analyze_dates(args: argparse.Namespace) -> None:
    """Analyze content dates."""
    try:
        from seo_content_mcp.date_distributor import DateDistributor
        
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
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_fix_dates(args: argparse.Namespace) -> None:
    """Fix content dates."""
    try:
        from seo_content_mcp.date_distributor import DateDistributor
        
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
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_articles_summary(args: argparse.Namespace) -> None:
    """Get articles summary."""
    try:
        from seo_content_mcp.server import _articles_summary
        
        root = _workspace_root(args.workspace_root)
        res = _articles_summary(workspace_root=root, website_path=args.website_path)
        _print_json(res.model_dump())
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_articles_index(args: argparse.Namespace) -> None:
    """List articles by status."""
    try:
        from seo_content_mcp.server import _get_articles_index
        
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
            values = list(dict.fromkeys(values))
        
        if bool(getattr(args, "sort", False)):
            values = sorted(values, key=str.casefold)
        
        limit = int(getattr(args, "limit", 0) or 0)
        if limit > 0:
            values = values[:limit]
        
        if values:
            sys.stdout.write("\n".join(values) + "\n")
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_sync_and_validate(args: argparse.Namespace) -> None:
    """Sync and validate content."""
    try:
        from seo_content_mcp.cli import _cmd_sync_and_validate_local
        _cmd_sync_and_validate_local(args)
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_get_next_task(args: argparse.Namespace) -> None:
    """Get next content task."""
    try:
        from seo_content_mcp.server import _get_next_content_task
        
        root = _workspace_root(args.workspace_root)
        brief_file, task = _get_next_content_task(
            workspace_root=root,
            website_path=args.website_path,
            brief_path=args.brief_path,
            priority=args.priority,
        )
        _print_json({"website_path": args.website_path, "brief_path": str(brief_file), "task": task.model_dump()})
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_plan_article(args: argparse.Namespace) -> None:
    """Plan content article."""
    try:
        from seo_content_mcp.server import _plan_content_article
        
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
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_publish_article(args: argparse.Namespace) -> None:
    """Publish article and complete task."""
    try:
        from seo_content_mcp.cli import _cmd_publish_article_and_complete_task
        _cmd_publish_article_and_complete_task(args)
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_get_articles_by_keyword(args: argparse.Namespace) -> None:
    """Get articles by keyword."""
    try:
        from seo_content_mcp.server import _get_articles_by_keyword
        
        root = _workspace_root(args.workspace_root)
        res = _get_articles_by_keyword(
            workspace_root=root,
            website_path=args.website_path,
            keyword=args.keyword,
            enable_fuzzy=not bool(args.disable_fuzzy),
            fuzzy_threshold=float(args.fuzzy_threshold),
        )
        _print_json(res.model_dump())
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_get_article_content(args: argparse.Namespace) -> None:
    """Get article content."""
    try:
        from seo_content_mcp.clustering_linking import get_article_content
        
        root = _workspace_root(args.workspace_root)
        res = get_article_content(root, args.website_path, article_id=int(args.article_id))
        if args.metadata_only:
            res.pop("content", None)
        _print_json(res)
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_scan_internal_links(args: argparse.Namespace) -> None:
    """Scan internal links."""
    try:
        from seo_content_mcp.clustering_linking import scan_internal_links
        
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
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_generate_linking_plan(args: argparse.Namespace) -> None:
    """Generate linking plan."""
    try:
        from seo_content_mcp.clustering_linking import generate_linking_plan
        import json as json_mod
        
        root = _workspace_root(args.workspace_root)
        clusters_json = None
        if args.clusters_json:
            if args.clusters_json == "-":
                raw = sys.stdin.read()
            else:
                raw = Path(args.clusters_json).read_text(encoding="utf-8")
            clusters_json = json_mod.loads(raw)
        
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
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_add_article_links(args: argparse.Namespace) -> None:
    """Add article links."""
    try:
        from seo_content_mcp.clustering_linking import add_article_links
        
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
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_batch_add_links(args: argparse.Namespace) -> None:
    """Batch add links."""
    try:
        from seo_content_mcp.cli import _cmd_batch_add_links
        _cmd_batch_add_links(args)
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_update_brief_linking_status(args: argparse.Namespace) -> None:
    """Update brief linking status."""
    try:
        from seo_content_mcp.clustering_linking import update_brief_linking_status
        
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
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_research_keywords(args: argparse.Namespace) -> None:
    """Research keywords."""
    try:
        from seo_content_mcp.cli import _cmd_research_keywords
        _cmd_research_keywords(args)
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_filter_new_keywords(args: argparse.Namespace) -> None:
    """Filter new keywords."""
    try:
        from seo_content_mcp.cli import _cmd_filter_new_keywords
        _cmd_filter_new_keywords(args)
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_append_draft_articles(args: argparse.Namespace) -> None:
    """Append draft articles."""
    try:
        from seo_content_mcp.cli import _cmd_append_draft_articles
        _cmd_append_draft_articles(args)
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_content_test_distribution(args: argparse.Namespace) -> None:
    """Test distribution."""
    try:
        from seo_content_mcp.server import SEOContentServer
        
        root = _workspace_root(args.workspace_root)
        server = SEOContentServer(root)
        res = server.test_distribution(args.project_name, args.article_count, args.earliest_date)
        _print_json(res.model_dump())
    except ImportError:
        print("Error: seo-content-mcp not installed. Run: uv tool install -e packages/seo-content-cli", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# Automation Commands (delegates to automation-cli)
# =============================================================================

def _cmd_automation_repo_init(args: argparse.Namespace) -> None:
    """Initialize repo with workflow payload."""
    try:
        from automation_mcp.cli import _repo_init_or_update
        _repo_init_or_update(args, mode="init")
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_repo_update(args: argparse.Namespace) -> None:
    """Update repo workflow payload."""
    try:
        from automation_mcp.cli import _repo_init_or_update
        _repo_init_or_update(args, mode="update")
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_repo_status(args: argparse.Namespace) -> None:
    """Check repo status."""
    try:
        from automation_mcp.cli import _repo_status
        _repo_status(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_seo_init(args: argparse.Namespace) -> None:
    """Initialize SEO workspace."""
    try:
        from automation_mcp.cli import _seo_init
        _seo_init(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_seo_status(args: argparse.Namespace) -> None:
    """Check SEO status."""
    try:
        from automation_mcp.cli import _seo_status
        _seo_status(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_skills_sync(args: argparse.Namespace) -> None:
    """Sync skills to target repo."""
    try:
        from automation_mcp.cli import _skills_sync
        _skills_sync(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_seo_gsc_indexing_report(args: argparse.Namespace) -> None:
    """Run GSC indexing report."""
    try:
        from automation_mcp.cli import _seo_gsc_indexing_report
        _seo_gsc_indexing_report(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_seo_gsc_page_context(args: argparse.Namespace) -> None:
    """Run GSC page context."""
    try:
        from automation_mcp.cli import _seo_gsc_page_context
        _seo_gsc_page_context(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_seo_gsc_site_scan(args: argparse.Namespace) -> None:
    """Run GSC site scan."""
    try:
        from automation_mcp.cli import _seo_gsc_site_scan
        _seo_gsc_site_scan(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_seo_gsc_watch(args: argparse.Namespace) -> None:
    """Run GSC watch."""
    try:
        from automation_mcp.cli import _seo_gsc_watch
        _seo_gsc_watch(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_seo_gsc_action_queue(args: argparse.Namespace) -> None:
    """Run GSC action queue."""
    try:
        from automation_mcp.cli import _seo_gsc_action_queue
        _seo_gsc_action_queue(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_seo_gsc_remediation_inputs(args: argparse.Namespace) -> None:
    """Get GSC remediation inputs."""
    try:
        from automation_mcp.cli import _seo_gsc_remediation_inputs
        _seo_gsc_remediation_inputs(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_seo_gsc_remediation_targets(args: argparse.Namespace) -> None:
    """Get GSC remediation targets."""
    try:
        from automation_mcp.cli import _seo_gsc_remediation_targets
        _seo_gsc_remediation_targets(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_posthog_report(args: argparse.Namespace) -> None:
    """Run PostHog report."""
    try:
        from automation_mcp.cli import _posthog_report
        _posthog_report(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_posthog_list_projects(args: argparse.Namespace) -> None:
    """List PostHog projects."""
    try:
        from automation_mcp.cli import _posthog_list_projects
        _posthog_list_projects(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_posthog_list_dashboards(args: argparse.Namespace) -> None:
    """List PostHog dashboards."""
    try:
        from automation_mcp.cli import _posthog_list_dashboards
        _posthog_list_dashboards(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_posthog_view(args: argparse.Namespace) -> None:
    """View PostHog insights."""
    try:
        from automation_mcp.cli import _posthog_view
        _posthog_view(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_automation_posthog_action_queue(args: argparse.Namespace) -> None:
    """Build PostHog action queue."""
    try:
        from automation_mcp.cli import _posthog_action_queue
        _posthog_action_queue(args)
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# Reddit Commands (delegates to automation-cli)
# =============================================================================

def _cmd_reddit_pending(args: argparse.Namespace) -> None:
    """List pending Reddit opportunities."""
    try:
        from automation_mcp.reddit.database import ensure_reddit_table, get_pending_opportunities
        ensure_reddit_table()
        opportunities = get_pending_opportunities(project_name=args.project, severity=args.severity or "")
        if args.limit:
            opportunities = opportunities[:args.limit]
        _print_json({
            "project_name": args.project,
            "severity": args.severity or "",
            "count": len(opportunities),
            "opportunities": opportunities,
        })
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_reddit_posted(args: argparse.Namespace) -> None:
    """List posted Reddit opportunities."""
    try:
        from automation_mcp.reddit.database import ensure_reddit_table, get_posted_opportunities
        ensure_reddit_table()
        opportunities = get_posted_opportunities(project_name=args.project, days=args.days)
        if args.limit:
            opportunities = opportunities[:args.limit]
        _print_json({
            "project_name": args.project,
            "days": args.days,
            "count": len(opportunities),
            "opportunities": opportunities,
        })
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


def _cmd_reddit_stats(args: argparse.Namespace) -> None:
    """Show Reddit project stats."""
    try:
        from automation_mcp.reddit.database import ensure_reddit_table, get_reddit_statistics
        ensure_reddit_table()
        _print_json(get_reddit_statistics(project_name=args.project))
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# Geo Commands (delegates to automation-cli)
# =============================================================================

def _cmd_geo_maps_lookup(args: argparse.Namespace) -> None:
    """Lookup place on Google Maps."""
    try:
        from automation_mcp.geo.google_maps import GoogleMapsClient
        with GoogleMapsClient(
            headless=args.headless,
            slow_mo_ms=args.slow_mo_ms,
            timeout_ms=args.timeout_ms,
            cdp_url=args.cdp_url or None,
        ) as client:
            _print_json(client.lookup(args.query))
    except ImportError:
        print("Error: automation-mcp not installed. Run: uv tool install -e packages/automation-cli", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# Dashboard Command (original behavior)
# =============================================================================

def _cmd_dashboard(args: argparse.Namespace) -> None:
    """Launch interactive dashboard (default behavior)."""
    from .cli import Dashboard
    from .engine.runtime_config import RuntimeConfig
    from .workflow_bundle import legacy_seo_reddit_bundle

    bundle = legacy_seo_reddit_bundle()
    app = Dashboard(
        workflow_bundle=bundle,
        runtime_config=RuntimeConfig(required_clis=bundle.required_clis),
    )
    if not app.project_manager.current:
        app._clear_screen()
        selected = app.project_manager.select_project_interactive(app.session)
        if selected:
            app._activate_project(selected, show_report=True)
    else:
        app._activate_project(app.project_manager.current, show_report=False)
    app.main_menu()


# =============================================================================
# Argument Parser Builder
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pageseeds",
        description="PageSeeds CLI - Unified tool for SEO automation workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pageseeds                              # Launch interactive dashboard
  pageseeds version                      # Check version
  pageseeds version --all                # Check all package versions
  pageseeds seo keywords --keyword "coffee" --country us
  pageseeds content validate --website-path general/my-site
  pageseeds reddit pending --project my-project
  pageseeds automation seo init --content-dir ./content
  pageseeds automation posthog report
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Version command
    version_parser = subparsers.add_parser("version", help="Check CLI version and updates")
    version_parser.add_argument("--all", action="store_true", help="Check all packages")
    version_parser.set_defaults(func=_cmd_version)
    
    # Dashboard command (explicit)
    dashboard_parser = subparsers.add_parser("dashboard", help="Launch interactive dashboard (default)")
    dashboard_parser.set_defaults(func=_cmd_dashboard)
    
    # =========================================================================
    # SEO commands
    # =========================================================================
    seo = subparsers.add_parser("seo", help="SEO research tools")
    seo_sub = seo.add_subparsers(dest="seo_command", required=True)
    
    # seo keywords
    seo_keywords = seo_sub.add_parser("keywords", help="Generate keyword ideas")
    seo_keywords.add_argument("--keyword", required=True, help="Seed keyword")
    seo_keywords.add_argument("--country", default="us", help="Country code (default: us)")
    seo_keywords.add_argument("--search-engine", default="Google", help="Search engine")
    seo_keywords.add_argument("--format", choices=["json", "flat"], default="json", help="Output format")
    seo_keywords.set_defaults(func=_cmd_seo_keywords)
    
    # seo batch-keywords
    seo_batch = seo_sub.add_parser("batch-keywords", help="Batch keyword generator")
    seo_batch.add_argument("--themes", nargs="*", help="Theme keywords")
    seo_batch.add_argument("--themes-file", help="File with one theme per line")
    seo_batch.add_argument("--country", default="us")
    seo_batch.add_argument("--search-engine", default="Google")
    seo_batch.add_argument("--format", choices=["json", "flat"], default="json")
    seo_batch.set_defaults(func=_cmd_seo_batch_keywords)
    
    # seo difficulty
    seo_diff = seo_sub.add_parser("difficulty", help="Analyze keyword difficulty")
    seo_diff.add_argument("--keyword", required=True)
    seo_diff.add_argument("--country", default="us")
    seo_diff.set_defaults(func=_cmd_seo_difficulty)
    
    # seo batch-difficulty
    seo_batch_diff = seo_sub.add_parser("batch-difficulty", help="Batch keyword difficulty")
    seo_batch_diff.add_argument("--country", default="us")
    seo_batch_diff.add_argument("--keywords", nargs="*", default=[])
    seo_batch_diff.add_argument("--keywords-file", default=None, help="One keyword per line (use '-' for stdin)")
    seo_batch_diff.set_defaults(func=_cmd_seo_batch_difficulty)
    
    # seo backlinks
    seo_bl = seo_sub.add_parser("backlinks", help="Get backlinks for domain")
    seo_bl.add_argument("--domain", required=True)
    seo_bl.set_defaults(func=_cmd_seo_backlinks)
    
    # seo traffic
    seo_tr = seo_sub.add_parser("traffic", help="Get traffic estimates")
    seo_tr.add_argument("--domain-or-url", required=True)
    seo_tr.add_argument("--country", default="None")
    seo_tr.add_argument("--mode", choices=["subdomains", "exact"], default="subdomains")
    seo_tr.set_defaults(func=_cmd_seo_traffic)
    
    # =========================================================================
    # Content commands
    # =========================================================================
    content = subparsers.add_parser("content", help="Content lifecycle management")
    content_sub = content.add_subparsers(dest="content_command", required=True)
    
    # content validate
    content_val = content_sub.add_parser("validate", help="Validate content files")
    content_val.add_argument("--website-path", required=True)
    content_val.add_argument("--workspace-root", default=None, help="Override workspace root auto-detection")
    content_val.set_defaults(func=_cmd_content_validate)
    
    # content clean
    content_clean = content_sub.add_parser("clean", help="Clean content files")
    content_clean.add_argument("--website-path", required=True)
    content_clean.add_argument("--workspace-root", default=None)
    content_clean.add_argument("--dry-run", action="store_true")
    content_clean.set_defaults(func=_cmd_content_clean)
    
    # content analyze-dates
    content_dates = content_sub.add_parser("analyze-dates", help="Analyze content dates")
    content_dates.add_argument("--website-path", required=True)
    content_dates.add_argument("--workspace-root", default=None)
    content_dates.set_defaults(func=_cmd_content_analyze_dates)
    
    # content fix-dates
    content_fix = content_sub.add_parser("fix-dates", help="Fix content dates")
    content_fix.add_argument("--website-path", required=True)
    content_fix.add_argument("--workspace-root", default=None)
    content_fix.add_argument("--dry-run", action="store_true")
    content_fix.set_defaults(func=_cmd_content_fix_dates)
    
    # content articles-summary
    content_sum = content_sub.add_parser("articles-summary", help="Get articles summary")
    content_sum.add_argument("--website-path", required=True)
    content_sum.add_argument("--workspace-root", default=None)
    content_sum.set_defaults(func=_cmd_content_articles_summary)
    
    # content articles-index
    content_idx = content_sub.add_parser("articles-index", help="List articles by status")
    content_idx.add_argument("--website-path", required=True)
    content_idx.add_argument("--workspace-root", default=None)
    content_idx.add_argument("--status", default=None, help="Optional status filter")
    content_idx.add_argument("--format", default="json", choices=["json", "lines"], help="Output format")
    content_idx.add_argument("--field", default="", help="With --format lines: which item field to print")
    content_idx.add_argument("--unique", action="store_true", help="Deduplicate values in lines mode")
    content_idx.add_argument("--sort", action="store_true", help="Sort values in lines mode")
    content_idx.add_argument("--limit", type=int, default=0, help="Max lines in lines mode (0=all)")
    content_idx.set_defaults(func=_cmd_content_articles_index)
    
    # content sync-and-validate
    content_sync = content_sub.add_parser("sync-and-validate", help="Validate index/content gaps and optionally sync frontmatter dates")
    content_sync.add_argument("--website-path", required=True)
    content_sync.add_argument("--workspace-root", default=None)
    content_sync.add_argument("--apply-sync", action="store_true", help="Apply frontmatter date sync from articles.json")
    content_sync.add_argument("--dry-run", action="store_true", help="Preview only")
    content_sync.add_argument("--compact", action="store_true", help="Output only summary fields")
    content_sync.set_defaults(func=_cmd_content_sync_and_validate)
    
    # content get-next-content-task
    content_next = content_sub.add_parser("get-next-content-task", help="Pick next task from brief or drafts")
    content_next.add_argument("--website-path", required=True)
    content_next.add_argument("--workspace-root", default=None)
    content_next.add_argument("--brief-path", default=None)
    content_next.add_argument("--priority", default="HIGH PRIORITY")
    content_next.set_defaults(func=_cmd_content_get_next_task)
    
    # content plan-content-article
    content_plan = content_sub.add_parser("plan-content-article", help="Plan metadata + filename + frontmatter")
    content_plan.add_argument("--website-path", required=True)
    content_plan.add_argument("--workspace-root", default=None)
    content_plan.add_argument("--brief-path", default=None)
    content_plan.add_argument("--task-id", default=None)
    content_plan.add_argument("--priority", default="HIGH PRIORITY")
    content_plan.add_argument("--extension", default="mdx")
    content_plan.set_defaults(func=_cmd_content_plan_article)
    
    # content publish-article-and-complete-task
    content_pub = content_sub.add_parser("publish-article-and-complete-task", help="Upsert articles.json + mark brief task completed")
    content_pub.add_argument("--website-path", required=True)
    content_pub.add_argument("--workspace-root", default=None)
    content_pub.add_argument("--task-id", required=True)
    content_pub.add_argument("--from-plan", action="store_true", help="Auto-populate metadata from plan-content-article")
    content_pub.add_argument("--article-json", default=None, help="Path to JSON object (use '-' for stdin). Not needed with --from-plan")
    content_pub.add_argument("--title", default=None, help="Override article title (only with --from-plan)")
    content_pub.add_argument("--word-count", type=int, default=None, help="Override auto-detected word count")
    content_pub.add_argument("--brief-path", default=None)
    content_pub.add_argument("--status", default="ready_to_publish")
    content_pub.set_defaults(func=_cmd_content_publish_article)
    
    # content get-articles-by-keyword
    content_gabk = content_sub.add_parser("get-articles-by-keyword", help="Find existing articles matching keyword")
    content_gabk.add_argument("--website-path", required=True)
    content_gabk.add_argument("--workspace-root", default=None)
    content_gabk.add_argument("--keyword", required=True)
    content_gabk.add_argument("--disable-fuzzy", action="store_true")
    content_gabk.add_argument("--fuzzy-threshold", type=float, default=0.92)
    content_gabk.set_defaults(func=_cmd_content_get_articles_by_keyword)
    
    # content get-article-content
    content_gac = content_sub.add_parser("get-article-content", help="Get article metadata + MDX content by article ID")
    content_gac.add_argument("--website-path", required=True)
    content_gac.add_argument("--workspace-root", default=None)
    content_gac.add_argument("--article-id", required=True, type=int)
    content_gac.add_argument("--metadata-only", action="store_true", help="Return metadata without MDX content body")
    content_gac.set_defaults(func=_cmd_content_get_article_content)
    
    # content scan-internal-links
    content_sil = content_sub.add_parser("scan-internal-links", help="Scan all content files and build the internal link graph")
    content_sil.add_argument("--website-path", required=True)
    content_sil.add_argument("--workspace-root", default=None)
    content_sil.add_argument("--verbose", action="store_true", help="Include per-article link profiles")
    content_sil.add_argument("--show-all", action="store_true", help="With --verbose, show profiles even for articles with no links")
    content_sil.set_defaults(func=_cmd_content_scan_internal_links)
    
    # content generate-linking-plan
    content_glp = content_sub.add_parser("generate-linking-plan", help="Generate hub-spoke linking plan from clusters")
    content_glp.add_argument("--website-path", required=True)
    content_glp.add_argument("--workspace-root", default=None)
    content_glp.add_argument("--brief-path", default=None, help="Path to content brief (auto-detected if omitted)")
    content_glp.add_argument("--clusters-json", default=None, help="JSON file with cluster definitions (use '-' for stdin)")
    content_glp.add_argument("--missing-only", action="store_true", help="Only show links that are missing")
    content_glp.set_defaults(func=_cmd_content_generate_linking_plan)
    
    # content add-article-links
    content_aal = content_sub.add_parser("add-article-links", help="Add internal links from one article to target articles")
    content_aal.add_argument("--website-path", required=True)
    content_aal.add_argument("--workspace-root", default=None)
    content_aal.add_argument("--source-id", required=True, type=int, help="Article ID to add links into")
    content_aal.add_argument("--target-ids", required=True, nargs="+", type=int, help="Target article IDs to link to")
    content_aal.add_argument("--mode", choices=["related-section", "inline"], default="related-section")
    content_aal.add_argument("--dry-run", action="store_true")
    content_aal.set_defaults(func=_cmd_content_add_article_links)
    
    # content batch-add-links
    content_bal = content_sub.add_parser("batch-add-links", help="Add ALL missing links from the linking plan at once")
    content_bal.add_argument("--website-path", required=True)
    content_bal.add_argument("--workspace-root", default=None)
    content_bal.add_argument("--brief-path", default=None)
    content_bal.add_argument("--clusters-json", default=None, help="JSON file with cluster definitions (use '-' for stdin)")
    content_bal.add_argument("--mode", choices=["related-section", "inline"], default="related-section")
    content_bal.add_argument("--dry-run", action="store_true")
    content_bal.set_defaults(func=_cmd_content_batch_add_links)
    
    # content update-brief-linking-status
    content_ubls = content_sub.add_parser("update-brief-linking-status", help="Scan actual links and update brief checklist")
    content_ubls.add_argument("--website-path", required=True)
    content_ubls.add_argument("--workspace-root", default=None)
    content_ubls.add_argument("--brief-path", default=None)
    content_ubls.add_argument("--dry-run", action="store_true")
    content_ubls.set_defaults(func=_cmd_content_update_brief_linking_status)
    
    # content research-keywords
    content_rk = content_sub.add_parser("research-keywords", help="End-to-end: generate keywords from themes → dedupe → optionally analyze difficulty")
    content_rk.add_argument("--website-path", required=True)
    content_rk.add_argument("--workspace-root", default=None)
    content_rk.add_argument("--themes", nargs="*", default=[], help="Theme keywords (seed phrases)")
    content_rk.add_argument("--themes-file", default=None, help="File with one theme per line (use '-' for stdin)")
    content_rk.add_argument("--country", default="us")
    content_rk.add_argument("--analyze-difficulty", action="store_true", help="Also run batch keyword difficulty analysis")
    content_rk.add_argument("--top-n", type=int, default=None, help="Only analyze difficulty for first N new keywords")
    content_rk.add_argument("--auto-append", action="store_true", help="Auto-append viable keywords as draft articles")
    content_rk.add_argument("--min-volume", type=int, default=500, help="Minimum monthly search volume for auto-append")
    content_rk.add_argument("--max-kd", type=int, default=30, help="Maximum keyword difficulty for auto-append")
    content_rk.add_argument("--disable-fuzzy", action="store_true")
    content_rk.add_argument("--fuzzy-threshold", type=float, default=0.92)
    content_rk.set_defaults(func=_cmd_content_research_keywords)
    
    # content filter-new-keywords
    content_fnk = content_sub.add_parser("filter-new-keywords", help="Filter candidates against existing target_keyword")
    content_fnk.add_argument("--website-path", required=True)
    content_fnk.add_argument("--workspace-root", default=None)
    content_fnk.add_argument("--keywords", nargs="*", default=[])
    content_fnk.add_argument("--keywords-file", default=None, help="One keyword per line (use '-' for stdin)")
    content_fnk.add_argument("--disable-fuzzy", action="store_true")
    content_fnk.add_argument("--fuzzy-threshold", type=float, default=0.92)
    content_fnk.set_defaults(func=_cmd_content_filter_new_keywords)
    
    # content append-draft-articles
    content_ada = content_sub.add_parser("append-draft-articles", help="Append drafts to articles.json")
    content_ada.add_argument("--website-path", required=True)
    content_ada.add_argument("--workspace-root", default=None)
    content_ada.add_argument("--drafts-json", required=True, help="JSON list or {drafts:[...]} file path (use '-' for stdin)")
    content_ada.add_argument("--disable-dedupe", action="store_true")
    content_ada.add_argument("--fuzzy-threshold", type=float, default=0.92)
    content_ada.set_defaults(func=_cmd_content_append_draft_articles)
    
    # content test-distribution
    content_td = content_sub.add_parser("test-distribution", help="Preview distribution")
    content_td.add_argument("--workspace-root", default=None)
    content_td.add_argument("--project-name", required=True)
    content_td.add_argument("--article-count", type=int, required=True)
    content_td.add_argument("--earliest-date", required=True, help="YYYY-MM-DD")
    content_td.set_defaults(func=_cmd_content_test_distribution)
    
    # =========================================================================
    # Automation commands
    # =========================================================================
    automation = subparsers.add_parser("automation", help="Automation and repo management")
    automation_sub = automation.add_subparsers(dest="automation_command", required=True)
    
    # automation repo
    auto_repo = automation_sub.add_parser("repo", help="Repo workflow management")
    auto_repo_sub = auto_repo.add_subparsers(dest="repo_command", required=True)
    
    auto_repo_init = auto_repo_sub.add_parser("init", help="Initialize repo with workflow payload")
    auto_repo_init.add_argument("--to", default="", help="Target repo root")
    auto_repo_init.add_argument("--from-root", default=None)
    auto_repo_init.add_argument("--bundle", action="append", default=[])
    auto_repo_init.add_argument("--dry-run", action="store_true")
    auto_repo_init.add_argument("--force", action="store_true")
    auto_repo_init.set_defaults(func=_cmd_automation_repo_init)
    
    auto_repo_update = auto_repo_sub.add_parser("update", help="Update repo workflow payload")
    auto_repo_update.add_argument("--to", default="")
    auto_repo_update.add_argument("--from-root", default=None)
    auto_repo_update.add_argument("--bundle", action="append", default=[])
    auto_repo_update.add_argument("--prune", action="store_true")
    auto_repo_update.add_argument("--dry-run", action="store_true")
    auto_repo_update.add_argument("--no-overwrite", action="store_true")
    auto_repo_update.add_argument("--force", action="store_true")
    auto_repo_update.set_defaults(func=_cmd_automation_repo_update)
    
    auto_repo_status = auto_repo_sub.add_parser("status", help="Check repo status")
    auto_repo_status.add_argument("--to", default="")
    auto_repo_status.add_argument("--from-root", default=None)
    auto_repo_status.set_defaults(func=_cmd_automation_repo_status)
    
    # automation seo
    auto_seo = automation_sub.add_parser("seo", help="Repo-local SEO workspace helpers")
    auto_seo_sub = auto_seo.add_subparsers(dest="seo_subcommand", required=True)
    
    # automation seo init
    auto_seo_init = auto_seo_sub.add_parser("init", help="Initialize/update repo-local SEO workspace")
    auto_seo_init.add_argument("--site-id", default="", help="Optional site identifier")
    auto_seo_init.add_argument("--website-id", default="", help="Deprecated alias for --site-id")
    auto_seo_init.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    auto_seo_init.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root")
    auto_seo_init.add_argument("--source-repo", default="", help="Absolute path to content repo root")
    auto_seo_init.add_argument("--content-dir", default="", help="Canonical content dir")
    auto_seo_init.add_argument("--source-content-dir", default="", help="Deprecated alias for --content-dir")
    auto_seo_init.add_argument("--articles-json", default="", help="Optional seed file for workspace articles.json")
    auto_seo_init.add_argument("--link-mode", default="symlink", choices=["symlink", "copy"])
    auto_seo_init.add_argument("--dry-run", action="store_true")
    auto_seo_init.add_argument("--force", action="store_true")
    auto_seo_init.add_argument("--reset-articles", action="store_true", help="Reset articles.json to empty template")
    auto_seo_init.set_defaults(func=_cmd_automation_seo_init)
    
    # automation seo status
    auto_seo_status = auto_seo_sub.add_parser("status", help="Show repo-local SEO workspace status")
    auto_seo_status.add_argument("--website-id", default="", help="Deprecated (ignored)")
    auto_seo_status.add_argument("--repo-root", default="")
    auto_seo_status.add_argument("--workspace-dir", default="automation")
    auto_seo_status.set_defaults(func=_cmd_automation_seo_status)
    
    # automation seo gsc-* commands
    auto_seo_gsc = auto_seo_sub.add_parser("gsc-indexing-report", help="Run GSC URL Inspection indexing diagnostics")
    auto_seo_gsc.add_argument("--repo-root", default="")
    auto_seo_gsc.add_argument("--workspace-dir", default="automation")
    auto_seo_gsc.add_argument("--out-dir", default="")
    auto_seo_gsc.add_argument("--manifest", default="")
    auto_seo_gsc.add_argument("--site", default="", help="Search Console property, e.g. sc-domain:example.com")
    auto_seo_gsc.add_argument("--sitemap-url", default="")
    auto_seo_gsc.add_argument("--urls-file", default="")
    auto_seo_gsc.add_argument("--limit", type=int, default=500)
    auto_seo_gsc.add_argument("--workers", type=int, default=2)
    auto_seo_gsc.add_argument("--language", default="en-US")
    auto_seo_gsc.add_argument("--service-account-path", default="")
    auto_seo_gsc.add_argument("--delegated-user", default="")
    auto_seo_gsc.add_argument("--oauth-client-secrets", default="")
    auto_seo_gsc.add_argument("--list-sites", action="store_true")
    auto_seo_gsc.add_argument("--include-raw", action="store_true")
    auto_seo_gsc.add_argument("--samples-per-bucket", type=int, default=10)
    auto_seo_gsc.set_defaults(func=_cmd_automation_seo_gsc_indexing_report)
    
    auto_seo_page = auto_seo_sub.add_parser("gsc-page-context", help="Pull deterministic context for one URL")
    auto_seo_page.add_argument("--repo-root", default="")
    auto_seo_page.add_argument("--workspace-dir", default="automation")
    auto_seo_page.add_argument("--out-dir", default="")
    auto_seo_page.add_argument("--manifest", default="")
    auto_seo_page.add_argument("--site", default="")
    auto_seo_page.add_argument("--url", required=True)
    auto_seo_page.add_argument("--compare-days", type=int, default=7)
    auto_seo_page.add_argument("--long-compare-days", type=int, default=28)
    auto_seo_page.add_argument("--queries-limit", type=int, default=15)
    auto_seo_page.add_argument("--queries-fetch-limit", type=int, default=100)
    auto_seo_page.add_argument("--language", default="en-US")
    auto_seo_page.add_argument("--service-account-path", default="")
    auto_seo_page.add_argument("--delegated-user", default="")
    auto_seo_page.add_argument("--oauth-client-secrets", default="")
    auto_seo_page.add_argument("--action-queue", default="")
    auto_seo_page.set_defaults(func=_cmd_automation_seo_gsc_page_context)
    
    auto_seo_scan = auto_seo_sub.add_parser("gsc-site-scan", help="Run mixed-candidate page scan")
    auto_seo_scan.add_argument("--repo-root", default="")
    auto_seo_scan.add_argument("--workspace-dir", default="automation")
    auto_seo_scan.add_argument("--out-dir", default="")
    auto_seo_scan.add_argument("--manifest", default="")
    auto_seo_scan.add_argument("--site", default="")
    auto_seo_scan.add_argument("--compare-days", type=int, default=7)
    auto_seo_scan.add_argument("--long-compare-days", type=int, default=28)
    auto_seo_scan.add_argument("--top-pages", type=int, default=5)
    auto_seo_scan.add_argument("--decliners", type=int, default=5)
    auto_seo_scan.add_argument("--max-pages", type=int, default=20)
    auto_seo_scan.add_argument("--fetch-pages-limit", type=int, default=200)
    auto_seo_scan.add_argument("--non-pass-pool", type=int, default=20)
    auto_seo_scan.add_argument("--queries-limit", type=int, default=10)
    auto_seo_scan.add_argument("--queries-fetch-limit", type=int, default=100)
    auto_seo_scan.add_argument("--language", default="en-US")
    auto_seo_scan.add_argument("--service-account-path", default="")
    auto_seo_scan.add_argument("--delegated-user", default="")
    auto_seo_scan.add_argument("--oauth-client-secrets", default="")
    auto_seo_scan.add_argument("--action-queue", default="")
    auto_seo_scan.set_defaults(func=_cmd_automation_seo_gsc_site_scan)
    
    auto_seo_watch = auto_seo_sub.add_parser("gsc-watch", help="Build ongoing GSC watch feed")
    auto_seo_watch.add_argument("--repo-root", default="")
    auto_seo_watch.add_argument("--workspace-dir", default="automation")
    auto_seo_watch.add_argument("--out-dir", default="")
    auto_seo_watch.add_argument("--manifest", default="")
    auto_seo_watch.add_argument("--site", default="")
    auto_seo_watch.add_argument("--compare-days", type=int, default=7)
    auto_seo_watch.add_argument("--long-compare-days", type=int, default=28)
    auto_seo_watch.add_argument("--fetch-pages-limit", type=int, default=250)
    auto_seo_watch.add_argument("--alerts-limit", type=int, default=30)
    auto_seo_watch.add_argument("--opps-limit", type=int, default=30)
    auto_seo_watch.add_argument("--inspect-top-drops", type=int, default=8)
    auto_seo_watch.add_argument("--drift-limit", type=int, default=12)
    auto_seo_watch.add_argument("--language", default="en-US")
    auto_seo_watch.add_argument("--service-account-path", default="")
    auto_seo_watch.add_argument("--delegated-user", default="")
    auto_seo_watch.add_argument("--oauth-client-secrets", default="")
    auto_seo_watch.add_argument("--action-queue", default="")
    auto_seo_watch.set_defaults(func=_cmd_automation_seo_gsc_watch)
    
    auto_seo_queue = auto_seo_sub.add_parser("gsc-action-queue", help="Select remediation targets from action queue")
    auto_seo_queue.add_argument("--repo-root", default="")
    auto_seo_queue.add_argument("--workspace-dir", default="automation")
    auto_seo_queue.add_argument("--action-queue", default="")
    auto_seo_queue.add_argument("--reason-code", action="append", default=[])
    auto_seo_queue.add_argument("--coverage-contains", action="append", default=[])
    auto_seo_queue.add_argument("--verdict", default="")
    auto_seo_queue.add_argument("--mapped-only", action="store_true")
    auto_seo_queue.add_argument("--unmapped-only", action="store_true")
    auto_seo_queue.add_argument("--include-indexed-pass", action="store_true")
    auto_seo_queue.add_argument("--limit", type=int, default=100)
    auto_seo_queue.add_argument("--format", choices=["json", "lines"], default="json")
    auto_seo_queue.add_argument("--field", choices=["url", "path", "reason_code", "basename", "file", "title", "url_slug", "id"], default="basename")
    auto_seo_queue.add_argument("--unique", action="store_true")
    auto_seo_queue.set_defaults(func=_cmd_automation_seo_gsc_action_queue)
    
    auto_seo_inputs = auto_seo_sub.add_parser("gsc-remediation-inputs", help="Get Step 7 starter inputs")
    auto_seo_inputs.add_argument("--repo-root", default="")
    auto_seo_inputs.add_argument("--workspace-dir", default="automation")
    auto_seo_inputs.add_argument("--action-queue", default="")
    auto_seo_inputs.add_argument("--mapped-only", action="store_true")
    auto_seo_inputs.add_argument("--limit", type=int, default=20)
    auto_seo_inputs.add_argument("--format", choices=["json", "lines"], default="lines")
    auto_seo_inputs.add_argument("--field", choices=["url", "path", "reason_code", "basename", "file", "title", "url_slug", "id", "url_to_file"], default="url")
    auto_seo_inputs.add_argument("--unique", action="store_true")
    auto_seo_inputs.set_defaults(func=_cmd_automation_seo_gsc_remediation_inputs)
    
    auto_seo_targets = auto_seo_sub.add_parser("gsc-remediation-targets", help="Get Step 7 edit-ready mapped targets")
    auto_seo_targets.add_argument("--repo-root", default="")
    auto_seo_targets.add_argument("--workspace-dir", default="automation")
    auto_seo_targets.add_argument("--action-queue", default="")
    auto_seo_targets.add_argument("--limit", type=int, default=12)
    auto_seo_targets.add_argument("--format", choices=["json", "lines"], default="lines")
    auto_seo_targets.add_argument("--field", choices=["url", "file", "basename", "reason_code", "coverageState", "title", "url_to_file"], default="basename")
    auto_seo_targets.add_argument("--unique", action="store_true")
    auto_seo_targets.set_defaults(func=_cmd_automation_seo_gsc_remediation_targets)
    
    # automation skills
    auto_skills = automation_sub.add_parser("skills", help="Sync workflow skills")
    auto_skills_sub = auto_skills.add_subparsers(dest="skills_command", required=True)
    
    auto_skills_sync = auto_skills_sub.add_parser("sync", help="Copy .github/skills to target repo")
    auto_skills_sync.add_argument("--to", required=True, help="Target repo root")
    auto_skills_sync.add_argument("--from-root", default=None)
    auto_skills_sync.add_argument("--include", action="append", default=[])
    auto_skills_sync.add_argument("--include-prompts", action="store_true")
    auto_skills_sync.add_argument("--dry-run", action="store_true")
    auto_skills_sync.add_argument("--force", action="store_true")
    auto_skills_sync.set_defaults(func=_cmd_automation_skills_sync)
    
    # automation posthog
    auto_posthog = automation_sub.add_parser("posthog", help="PostHog analytics")
    auto_posthog_sub = auto_posthog.add_subparsers(dest="posthog_command", required=True)
    
    auto_posthog_report = auto_posthog_sub.add_parser("report", help="Run PostHog multi-site pull and summary")
    auto_posthog_report.add_argument("--repo-root", default="")
    auto_posthog_report.add_argument("--registry", default="")
    auto_posthog_report.add_argument("--manifests-dir", default="")
    auto_posthog_report.add_argument("--project-id", type=int, default=None)
    auto_posthog_report.add_argument("--api-key-env", default="")
    auto_posthog_report.add_argument("--base-url", default="")
    auto_posthog_report.add_argument("--dashboard-name", action="append", default=[])
    auto_posthog_report.add_argument("--insight-id", action="append", default=[], type=int)
    auto_posthog_report.add_argument("--site", action="append", default=[])
    auto_posthog_report.add_argument("--out-dir", default="")
    auto_posthog_report.add_argument("--refresh", action="store_true")
    auto_posthog_report.add_argument("--list-dashboards", action="store_true")
    auto_posthog_report.add_argument("--timeout", type=int, default=30)
    auto_posthog_report.add_argument("--max-insights", type=int, default=30)
    auto_posthog_report.add_argument("--extra-insights", type=int, default=0)
    auto_posthog_report.add_argument("--env-file", action="append", default=[])
    auto_posthog_report.set_defaults(func=_cmd_automation_posthog_report)
    
    auto_posthog_projects = auto_posthog_sub.add_parser("list-projects", help="List PostHog projects")
    auto_posthog_projects.add_argument("--repo-root", default="")
    auto_posthog_projects.add_argument("--api-key-env", required=True)
    auto_posthog_projects.add_argument("--base-url", default="")
    auto_posthog_projects.add_argument("--out-dir", default="")
    auto_posthog_projects.add_argument("--env-file", action="append", default=[])
    auto_posthog_projects.set_defaults(func=_cmd_automation_posthog_list_projects)
    
    auto_posthog_dashboards = auto_posthog_sub.add_parser("list-dashboards", help="List PostHog dashboards")
    auto_posthog_dashboards.add_argument("--repo-root", default="")
    auto_posthog_dashboards.add_argument("--project-id", required=True, type=int)
    auto_posthog_dashboards.add_argument("--api-key-env", required=True)
    auto_posthog_dashboards.add_argument("--base-url", default="")
    auto_posthog_dashboards.add_argument("--out-dir", default="")
    auto_posthog_dashboards.add_argument("--env-file", action="append", default=[])
    auto_posthog_dashboards.set_defaults(func=_cmd_automation_posthog_list_dashboards)
    
    auto_posthog_view = auto_posthog_sub.add_parser("view", help="View extracted fields from latest PostHog insights")
    auto_posthog_view.add_argument("--repo-root", default="")
    auto_posthog_view.add_argument("--out-dir", default="")
    auto_posthog_view.add_argument("--field", required=True, choices=["situations", "action_candidates", "insights", "page_traffic", "breakdowns"])
    auto_posthog_view.add_argument("--format", choices=["json", "lines"], default="lines")
    auto_posthog_view.set_defaults(func=_cmd_automation_posthog_view)
    
    auto_posthog_queue = auto_posthog_sub.add_parser("action-queue", help="Build cross-site PostHog action queue")
    auto_posthog_queue.add_argument("--repo-root", default="")
    auto_posthog_queue.add_argument("--out-dir", default="")
    auto_posthog_queue.add_argument("--date", default="")
    auto_posthog_queue.add_argument("--max-actions", type=int, default=15)
    auto_posthog_queue.add_argument("--max-per-site", type=int, default=5)
    auto_posthog_queue.add_argument("--write-md", action="store_true")
    auto_posthog_queue.set_defaults(func=_cmd_automation_posthog_action_queue)
    
    # =========================================================================
    # Reddit commands
    # =========================================================================
    reddit = subparsers.add_parser("reddit", help="Reddit engagement tools")
    reddit_sub = reddit.add_subparsers(dest="reddit_command", required=True)
    
    reddit_pending = reddit_sub.add_parser("pending", help="List pending opportunities")
    reddit_pending.add_argument("--project", required=True)
    reddit_pending.add_argument("--severity", default="")
    reddit_pending.add_argument("--limit", type=int)
    reddit_pending.set_defaults(func=_cmd_reddit_pending)
    
    reddit_posted = reddit_sub.add_parser("posted", help="List posted opportunities")
    reddit_posted.add_argument("--project", required=True)
    reddit_posted.add_argument("--days", type=int, default=30)
    reddit_posted.add_argument("--limit", type=int)
    reddit_posted.set_defaults(func=_cmd_reddit_posted)
    
    reddit_stats = reddit_sub.add_parser("stats", help="Show project stats")
    reddit_stats.add_argument("--project", required=True)
    reddit_stats.set_defaults(func=_cmd_reddit_stats)
    
    # =========================================================================
    # Geo commands
    # =========================================================================
    geo = subparsers.add_parser("geo", help="Geo/place enrichment")
    geo_sub = geo.add_subparsers(dest="geo_command", required=True)
    
    geo_lookup = geo_sub.add_parser("maps-lookup", help="Lookup place on Google Maps")
    geo_lookup.add_argument("--query", required=True)
    geo_lookup.add_argument("--headless", action="store_true")
    geo_lookup.add_argument("--slow-mo-ms", type=int, default=0)
    geo_lookup.add_argument("--timeout-ms", type=int, default=30000)
    geo_lookup.add_argument("--cdp-url", default="")
    geo_lookup.set_defaults(func=_cmd_geo_maps_lookup)
    
    return parser


def main(argv: list[str] | None = None) -> None:
    """Main entrypoint for unified CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    
    # If no command specified, launch dashboard (backward compatible)
    if not args.command:
        _cmd_dashboard(args)
        return
    
    # Dispatch to handler
    if hasattr(args, "func"):
        try:
            args.func(args)
        except KeyboardInterrupt:
            sys.stderr.write("Interrupted by user.\n")
            sys.exit(130)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
