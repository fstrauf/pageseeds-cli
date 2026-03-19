"""GSC CLI commands using internal modules.

This module replaces the external script calls with proper Python module usage.
"""

from __future__ import annotations

import json
import sys
import threading
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from .seo.gsc import (
    get_search_console_service,
    list_sites,
    auto_select_site_property,
    fetch_page_rows,
    fetch_queries_for_page,
    compute_movers,
    inspect_url,
    classify_record,
    priority_for_record,
    generate_indexing_report,
    generate_site_scan_report,
    generate_coverage_404_report,
)


def _print_json(data: object) -> None:
    """Print JSON to stdout."""
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    """Load manifest.json if it exists."""
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_urls_from_sitemap(sitemap_url: str) -> list[str]:
    """Fetch URLs from sitemap."""
    import urllib.request
    import xml.etree.ElementTree as ET
    
    try:
        # Create request with proper headers to avoid 403 from Cloudflare/WAF
        req = urllib.request.Request(
            sitemap_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            
        # Handle gzip
        if sitemap_url.endswith('.gz') or data[:2] == b'\x1f\x8b':
            import gzip
            data = gzip.decompress(data)
            
        root = ET.fromstring(data)
        
        # Handle sitemapindex
        urls = []
        for elem in root.iter():
            if elem.tag.endswith('loc'):
                urls.append(elem.text.strip())
        return urls
    except Exception as e:
        print(f"Error fetching sitemap: {e}", file=sys.stderr)
        return []


def _load_urls_from_file(urls_file: Path) -> list[str]:
    """Load URLs from text file."""
    try:
        content = urls_file.read_text(encoding="utf-8")
        return [line.strip() for line in content.splitlines() if line.strip()]
    except Exception as e:
        print(f"Error reading URLs file: {e}", file=sys.stderr)
        return []


def cmd_gsc_list_sites(args: Namespace) -> int:
    """List accessible GSC sites."""
    try:
        service = get_search_console_service(
            service_account_path=args.service_account_path or None,
            repo_root=Path(args.repo_root) if args.repo_root else Path.cwd(),
        )
        sites = list_sites(service)
        
        _print_json({
            "sites": sites,
            "count": len(sites),
        })
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_gsc_indexing_report(args: Namespace) -> int:
    """Run GSC URL Inspection indexing report."""
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else (repo_root / ".github" / "automation" / "output" / "gsc_indexing")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()
    
    try:
        # Initialize service
        service = get_search_console_service(
            service_account_path=args.service_account_path or None,
            oauth_client_secrets=args.oauth_client_secrets or None,
            delegated_user=args.delegated_user or None,
            repo_root=repo_root,
        )
        
        # Handle list-sites flag
        if getattr(args, 'list_sites', False):
            sites = list_sites(service)
            _print_json({
                "sites": sites,
                "count": len(sites),
            })
            return 0
        
        # Determine site URL
        if args.site:
            site_url = args.site
        else:
            # Try to get from manifest
            manifest_path = Path(args.manifest) if args.manifest else repo_root / ".github" / "automation" / "manifest.json"
            manifest = _load_manifest(manifest_path)
            base_url = manifest.get("url") or manifest.get("gsc_site")
            if not base_url:
                print("Error: No site specified and no manifest found", file=sys.stderr)
                return 1
            site_url = auto_select_site_property(service, base_url)
        
        # Get URLs to inspect
        urls: list[str] = []
        if args.urls_file:
            urls = _load_urls_from_file(Path(args.urls_file))
        elif args.sitemap_url:
            urls = _load_urls_from_sitemap(args.sitemap_url)
        else:
            # Try to get sitemap from manifest
            manifest_path = Path(args.manifest) if args.manifest else repo_root / ".github" / "automation" / "manifest.json"
            manifest = _load_manifest(manifest_path)
            sitemap_url = manifest.get("sitemap")
            if sitemap_url:
                urls = _load_urls_from_sitemap(sitemap_url)
        
        if not urls:
            print("Error: No URLs to inspect. Provide --urls-file, --sitemap-url, or manifest with sitemap.", file=sys.stderr)
            return 1
        
        # Limit URLs
        urls = urls[:args.limit]
        
        print(f"Inspecting {len(urls)} URLs...", file=sys.stderr)
        
        # Inspect URLs with threading
        # NOTE: Each thread creates its own service because httplib2 is not thread-safe
        inspections: list[tuple[str, Any, str, str, int]] = []
        
        # Get credentials once (credentials object IS thread-safe)
        from .seo.gsc.client import build_credentials_from_service_account, resolve_service_account_path
        sa_path = args.service_account_path or None
        if not sa_path:
            # Try to resolve from env
            sa_path = resolve_service_account_path(None, repo_root)
        
        credentials = None
        if sa_path:
            credentials = build_credentials_from_service_account(sa_path)
        
        def inspect_worker(url: str) -> tuple[str, Any, str, str, int] | None:
            try:
                # Create service per-thread to avoid httplib2 thread-safety issues
                if credentials:
                    from googleapiclient.discovery import build
                    thread_service = build("searchconsole", "v1", credentials=credentials, cache_discovery=False, static_discovery=False)
                else:
                    thread_service = service
                record = inspect_url(thread_service, url, site_url=site_url, language=args.language)
                reason_code, action = classify_record(record)
                priority = priority_for_record(record, reason_code)
                return (url, record, reason_code, action, priority)
            except Exception as e:
                print(f"  Error inspecting {url}: {e}", file=sys.stderr)
                return None
        
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(inspect_worker, url): url for url in urls}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    inspections.append(result)
                    print(f"  Inspected: {result[0][:60]}...", file=sys.stderr)
        
        # Sort by priority
        inspections.sort(key=lambda x: x[4])
        
        # Generate report
        report_meta = generate_indexing_report(
            site_url=site_url,
            inspections=inspections,
            out_dir=out_dir,
            include_raw=args.include_raw,
        )
        
        print(f"\nReport generated:", file=sys.stderr)
        print(f"  Action queue: {report_meta['action_queue']}", file=sys.stderr)
        print(f"  Summary: {report_meta['summary']}", file=sys.stderr)
        
        _print_json(report_meta)
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_gsc_site_scan(args: Namespace) -> int:
    """Run multi-page GSC site scan."""
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else (repo_root / ".github" / "automation" / "output" / "gsc_site_scan")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()
    
    try:
        # Initialize service
        service = get_search_console_service(
            service_account_path=args.service_account_path or None,
            oauth_client_secrets=args.oauth_client_secrets or None,
            delegated_user=args.delegated_user or None,
            repo_root=repo_root,
        )
        
        # Determine site URL
        if args.site:
            site_url = args.site
        else:
            manifest_path = Path(args.manifest) if args.manifest else repo_root / ".github" / "automation" / "manifest.json"
            manifest = _load_manifest(manifest_path)
            base_url = manifest.get("url") or manifest.get("gsc_site")
            if not base_url:
                print("Error: No site specified and no manifest found", file=sys.stderr)
                return 1
            site_url = auto_select_site_property(service, base_url)
        
        print(f"Scanning site: {site_url}", file=sys.stderr)
        
        # Get top pages
        print(f"  Fetching top pages...", file=sys.stderr)
        import datetime as dt
        
        end_date = dt.date.today() - dt.timedelta(days=1)
        start_date = end_date - dt.timedelta(days=args.compare_days - 1)
        
        pages_data = fetch_page_rows(
            service, site_url,
            start_date.isoformat(),
            end_date.isoformat(),
            limit=args.fetch_pages_limit
        )
        
        # Sort by impressions and select top
        sorted_pages = sorted(pages_data.values(), key=lambda x: x.impressions, reverse=True)
        selected_pages = sorted_pages[:args.top_pages]
        
        print(f"  Analyzing {len(selected_pages)} pages...", file=sys.stderr)
        
        # Build page data with queries and inspection
        page_results: list[dict[str, Any]] = []
        
        for page in selected_pages[:args.max_pages]:
            print(f"  Processing: {page.page[:60]}...", file=sys.stderr)
            
            # Get queries
            queries = fetch_queries_for_page(
                service, site_url, page.page,
                start_date.isoformat(),
                end_date.isoformat(),
                limit=args.queries_limit
            )
            
            # Inspect URL
            try:
                inspection = inspect_url(service, page.page, site_url=site_url, language=args.language)
            except Exception as e:
                print(f"    Warning: Could not inspect {page.page}: {e}", file=sys.stderr)
                inspection = None
            
            page_data: dict[str, Any] = {
                "url": page.page,
                "metrics": {
                    "clicks": page.clicks,
                    "impressions": page.impressions,
                    "ctr": page.ctr,
                    "position": page.position,
                },
                "queries": [
                    {
                        "query": q.query,
                        "clicks": q.clicks,
                        "impressions": q.impressions,
                        "position": q.position,
                    }
                    for q in queries
                ],
            }
            
            if inspection:
                page_data["inspection"] = {
                    "verdict": inspection.verdict,
                    "coverage_state": inspection.coverage_state,
                    "indexing_state": inspection.indexing_state,
                }
            
            page_results.append(page_data)
        
        # Generate report
        report_meta = generate_site_scan_report(
            site_url=site_url,
            pages=page_results,
            out_dir=out_dir,
        )
        
        print(f"\nScan complete:", file=sys.stderr)
        print(f"  Output: {report_meta['output_path']}", file=sys.stderr)
        
        _print_json(report_meta)
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_gsc_page_context(args: Namespace) -> int:
    """Get GSC context for a single page."""
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else (repo_root / ".github" / "automation" / "output" / "gsc_page_context")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()
    
    try:
        service = get_search_console_service(
            service_account_path=args.service_account_path or None,
            repo_root=repo_root,
        )
        
        # Determine site URL
        if args.site:
            site_url = args.site
        else:
            manifest_path = Path(args.manifest) if args.manifest else repo_root / ".github" / "automation" / "manifest.json"
            manifest = _load_manifest(manifest_path)
            base_url = manifest.get("url") or manifest.get("gsc_site")
            if not base_url:
                print("Error: No site specified and no manifest found", file=sys.stderr)
                return 1
            site_url = auto_select_site_property(service, base_url)
        
        url = args.url
        
        # Get analytics
        import datetime as dt
        end_date = dt.date.today() - dt.timedelta(days=1)
        start_date = end_date - dt.timedelta(days=args.compare_days - 1)
        
        queries = fetch_queries_for_page(
            service, site_url, url,
            start_date.isoformat(),
            end_date.isoformat(),
            limit=args.queries_limit
        )
        
        # Get inspection
        inspection = inspect_url(service, url, site_url=site_url, language=args.language)
        
        result = {
            "url": url,
            "site_url": site_url,
            "queries": [
                {
                    "query": q.query,
                    "clicks": q.clicks,
                    "impressions": q.impressions,
                    "position": q.position,
                }
                for q in queries
            ],
            "inspection": {
                "verdict": inspection.verdict,
                "coverage_state": inspection.coverage_state,
                "indexing_state": inspection.indexing_state,
                "robots_txt_state": inspection.robots_txt_state,
                "crawl_allowed": inspection.crawl_allowed,
                "indexing_allowed": inspection.indexing_allowed,
            } if inspection else None,
        }
        
        # Write output
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"page_context_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_path.write_text(json.dumps(result, indent=2))
        
        _print_json(result)
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_gsc_coverage_404s(args: Namespace) -> int:
    """Process GSC Coverage Drilldown CSV for 404 errors.
    
    This command takes a CSV export from GSC Coverage > Drilldown (Not found)
    and generates an action queue with classified 404 errors.
    """
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else (repo_root / ".github" / "automation" / "output" / "gsc_coverage_404s")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()
    
    csv_path = Path(args.csv_file).expanduser().resolve()
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        return 1
    
    # Determine site URL
    site_url = args.site
    if not site_url:
        manifest_path = Path(args.manifest) if args.manifest else repo_root / ".github" / "automation" / "manifest.json"
        manifest = _load_manifest(manifest_path)
        site_url = manifest.get("url", "")
        if not site_url:
            print("Error: No site URL specified. Use --site or ensure manifest.json has 'url'", file=sys.stderr)
            return 1
    
    try:
        print(f"Processing Coverage 404 CSV: {csv_path}", file=sys.stderr)
        print(f"Site: {site_url}", file=sys.stderr)
        
        report_meta = generate_coverage_404_report(
            csv_path=csv_path,
            site_url=site_url,
            out_dir=out_dir,
        )
        
        print(f"\n✓ Report generated:", file=sys.stderr)
        print(f"  Total 404s: {report_meta['total_404s']}", file=sys.stderr)
        print(f"  Categories: {', '.join(report_meta['categories'])}", file=sys.stderr)
        print(f"  Action queue: {report_meta['action_queue']}", file=sys.stderr)
        print(f"  Fix plan: {report_meta['fix_plan']}", file=sys.stderr)
        
        _print_json(report_meta)
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_gsc_redirect_analysis(args: Namespace) -> int:
    """Process GSC "Page with redirect" CSV for redirect issues.
    
    Analyzes redirect issues and creates fix tasks.
    """
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else (repo_root / ".github" / "automation" / "output" / "gsc_redirects")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()
    
    csv_path = Path(args.csv_file).expanduser().resolve()
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        return 1
    
    # Determine site URL
    site_url = args.site
    if not site_url:
        manifest_path = Path(args.manifest) if args.manifest else repo_root / ".github" / "automation" / "manifest.json"
        manifest = _load_manifest(manifest_path)
        site_url = manifest.get("url", "")
        if not site_url:
            print("Error: No site URL specified. Use --site or ensure manifest.json has 'url'", file=sys.stderr)
            return 1
    
    # Load sitemap if available
    sitemap_urls: set[str] | None = None
    sitemap_path = repo_root / ".github" / "automation" / "sitemap.xml"
    if not sitemap_path.exists():
        sitemap_path = repo_root / "public" / "sitemap.xml"
    if sitemap_path.exists():
        try:
            urls = _load_urls_from_sitemap(f"file://{sitemap_path}")
            sitemap_urls = set(urls)
            print(f"Loaded {len(sitemap_urls)} URLs from sitemap", file=sys.stderr)
        except Exception:
            pass
    
    try:
        from .seo.gsc.redirects import generate_redirect_report
        
        print(f"Processing redirect CSV: {csv_path}", file=sys.stderr)
        print(f"Site: {site_url}", file=sys.stderr)
        
        report_meta = generate_redirect_report(
            csv_path=csv_path,
            site_url=site_url,
            out_dir=out_dir,
            sitemap_urls=sitemap_urls,
        )
        
        print(f"\n✓ Report generated:", file=sys.stderr)
        print(f"  Total redirects: {report_meta['total_redirects']}", file=sys.stderr)
        print(f"  In sitemap (CRITICAL): {report_meta['in_sitemap_count']}", file=sys.stderr)
        print(f"  Redirect types: {', '.join(report_meta['redirect_types'])}", file=sys.stderr)
        print(f"  Action queue: {report_meta['action_queue']}", file=sys.stderr)
        print(f"  Fix plan: {report_meta['fix_plan']}", file=sys.stderr)
        
        _print_json(report_meta)
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_gsc_sync_articles(args: Namespace) -> int:
    """Hydrate articles.json with live GSC performance data.

    Fetches page-level metrics (clicks, impressions, CTR, average position) from
    GSC and writes a ``gsc`` block into each matching article record in
    articles.json.  Articles with no GSC match have their ``gsc`` field set to
    null.  Existing fields (title, status, etc.) are never touched.
    """
    import datetime as dt
    import re

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    workspace_dir_name = str(getattr(args, "workspace_dir", "automation") or "automation")
    workspace_dir = (repo_root / workspace_dir_name).resolve()
    articles_path = workspace_dir / "articles.json"

    if not articles_path.exists():
        print(f"Error: articles.json not found at {articles_path}", file=sys.stderr)
        return 1

    try:
        raw_data = json.loads(articles_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading articles.json: {e}", file=sys.stderr)
        return 1

    # Support both plain list and {"articles": [...], "nextArticleId": ...} shapes
    articles_wrapper: dict[str, Any] | None = None
    if isinstance(raw_data, dict):
        if "articles" not in raw_data:
            print("Error: articles.json is a dict but has no 'articles' key", file=sys.stderr)
            return 1
        articles_wrapper = raw_data
        articles: list[dict[str, Any]] = raw_data["articles"]
    else:
        articles = raw_data

    if not isinstance(articles, list):
        print("Error: articles.json must contain a list of article objects", file=sys.stderr)
        return 1

    # Resolve site URL from flag or manifest
    site_url = getattr(args, "site", "") or ""
    if not site_url:
        manifest_path = (
            Path(args.manifest)
            if getattr(args, "manifest", "")
            else repo_root / ".github" / "automation" / "manifest.json"
        )
        manifest = _load_manifest(manifest_path)
        site_url = manifest.get("gsc_site") or manifest.get("url") or ""
    if not site_url:
        print(
            "Error: No site URL specified. Use --site or ensure manifest.json has 'url' or 'gsc_site'",
            file=sys.stderr,
        )
        return 1

    # Convert sc-domain: property to a usable base URL for slug matching
    base_url = site_url
    if base_url.startswith("sc-domain:"):
        base_url = "https://" + base_url[len("sc-domain:"):]
    base_url = base_url.rstrip("/")

    days = int(getattr(args, "days", 90) or 90)
    end_date = dt.date.today() - dt.timedelta(days=1)
    start_date = end_date - dt.timedelta(days=days - 1)
    dry_run = bool(getattr(args, "dry_run", False))
    verbose = bool(getattr(args, "verbose", False))
    service_account_path = getattr(args, "service_account_path", "") or ""

    try:
        service = get_search_console_service(service_account_path or None)
    except Exception as e:
        print(f"Error initializing GSC service: {e}", file=sys.stderr)
        return 1

    try:
        resolved_site = auto_select_site_property(service, base_url)
    except Exception as e:
        print(f"Error resolving GSC site property for {base_url}: {e}", file=sys.stderr)
        return 1

    print(
        f"Fetching GSC page metrics for {resolved_site} ({start_date} → {end_date})",
        file=sys.stderr,
    )

    try:
        page_metrics = fetch_page_rows(
            service,
            resolved_site,
            start_date.isoformat(),
            end_date.isoformat(),
        )
    except Exception as e:
        print(f"Error fetching GSC data: {e}", file=sys.stderr)
        return 1

    print(f"  Fetched metrics for {len(page_metrics)} pages from GSC", file=sys.stderr)

    # Build normalized-path → metrics lookup from GSC URLs
    def _normalize_path(url: str) -> str:
        for prefix in ("https://", "http://"):
            if url.startswith(prefix):
                url = url[len(prefix):]
                break
        url = url[url.index("/"):] if "/" in url else "/"
        return url.rstrip("/").lower().replace("_", "-") or "/"

    gsc_by_path: dict[str, Any] = {}
    for _raw_url, _metrics in page_metrics.items():
        _path = _normalize_path(_raw_url)
        if _path:
            gsc_by_path[_path] = _metrics

    # Secondary index: last path segment → metrics.  Allows bare-slug articles
    # to match GSC paths that include a directory prefix (e.g. /blog/my-slug).
    # Also index the de-numbered segment for paths like /blog/06-my-slug.
    gsc_by_last_segment: dict[str, Any] = {}
    for _gsc_path, _m in gsc_by_path.items():
        _last = _gsc_path.rstrip("/").rsplit("/", 1)[-1]
        if _last:
            gsc_by_last_segment[_last] = _m
            # Strip leading numeric prefix (e.g. "06-", "149-") so bare slugs match
            _stripped = re.sub(r"^\d+[_-]+", "", _last)
            if _stripped and _stripped != _last:
                gsc_by_last_segment.setdefault(_stripped, _m)

    def _article_path(article: dict[str, Any]) -> str:
        slug = str(article.get("url_slug") or "").strip()
        if not slug:
            file_ref = str(article.get("file") or "").strip()
            if file_ref:
                stem = Path(file_ref).stem
                slug = re.sub(r"^\d+[_-]+", "", stem)
        slug = slug.strip("/").replace("_", "-").lower()
        return ("/" + slug) if slug else ""

    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    matched = 0
    unmatched = 0
    matched_gsc_paths: set[str] = set()

    if verbose:
        print(f"  GSC paths returned ({len(gsc_by_path)}):", file=sys.stderr)
        for p in sorted(gsc_by_path.keys()):
            print(f"    {p}", file=sys.stderr)

    for article in articles:
        path = _article_path(article)
        if not path or path == "/":
            article["gsc"] = None
            unmatched += 1
            continue
        metrics = gsc_by_path.get(path) or gsc_by_last_segment.get(path.lstrip("/"))
        if metrics is None:
            if verbose:
                print(f"  no-match: article path {path!r}", file=sys.stderr)
            article["gsc"] = None
            unmatched += 1
        else:
            article["gsc"] = {
                "impressions": metrics.impressions,
                "clicks": metrics.clicks,
                "ctr": round(metrics.ctr, 4),
                "avg_position": round(metrics.position, 1),
                "last_synced": now_iso,
                "period_days": days,
            }
            matched_gsc_paths.add(path)
            matched += 1

    summary: dict[str, Any] = {
        "total_articles": len(articles),
        "matched": matched,
        "unmatched": unmatched,
        "site": resolved_site,
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "dry_run": dry_run,
        "articles_path": str(articles_path),
    }

    if not dry_run:
        if articles_wrapper is not None:
            articles_wrapper["articles"] = articles
            write_data: Any = articles_wrapper
        else:
            write_data = articles
        articles_path.write_text(
            json.dumps(write_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  Written: {articles_path}", file=sys.stderr)
    else:
        print("  Dry run — articles.json not modified", file=sys.stderr)

    print(f"  Matched: {matched}/{len(articles)} articles", file=sys.stderr)

    if verbose:
        # Show GSC URLs that had data but no matching article
        unmatched_gsc = [
            p for p in gsc_by_path
            if p not in matched_gsc_paths
            and gsc_by_last_segment.get(p.lstrip("/")) is None
            or p not in matched_gsc_paths
        ]
        # Simplified: just show all GSC paths not consumed
        consumed_last_segments = {path.lstrip("/") for path in matched_gsc_paths}
        unmatched_gsc_paths = [
            p for p in sorted(gsc_by_path.keys())
            if p not in matched_gsc_paths and p.rstrip("/").rsplit("/", 1)[-1] not in consumed_last_segments
        ]
        if unmatched_gsc_paths:
            print(f"  GSC URLs with no matching article ({len(unmatched_gsc_paths)}):", file=sys.stderr)
            for p in unmatched_gsc_paths:
                m = gsc_by_path[p]
                print(f"    {p}  (impr={m.impressions} clicks={m.clicks})", file=sys.stderr)
        else:
            print("  All GSC URLs matched an article.", file=sys.stderr)
    _print_json(summary)
    return 0


# ---------------------------------------------------------------------------
# content-audit: deterministic batch audit of all articles
# ---------------------------------------------------------------------------

import re as _re
import datetime as _dt


def _read_source_file(repo_root: Path, file_ref: str) -> str | None:
    """Read article source file, trying several resolution strategies."""
    if not file_ref:
        return None
    # Resolve relative paths against repo root
    p = Path(file_ref)
    if not p.is_absolute():
        p = repo_root / file_ref
    # Strip leading "./" so Path(repo_root / "./content/...") works
    p = p.resolve()
    if p.exists():
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None
    return None


def _parse_frontmatter(source: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_text). Handles YAML --- fences."""
    if not source.startswith("---"):
        return {}, source
    end = source.find("\n---", 3)
    if end == -1:
        return {}, source
    fm_text = source[3:end].strip()
    body = source[end + 4:].strip()
    fm: dict[str, Any] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body


def _audit_article(article: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Run all deterministic checks on one article. Returns audit record."""
    keyword = str(article.get("target_keyword") or "").strip().lower()
    title = str(article.get("title") or "").strip()
    file_ref = str(article.get("file") or "").strip()
    word_count = int(article.get("word_count") or 0)
    gsc = article.get("gsc")
    published_date = str(article.get("published_date") or "")
    status = str(article.get("status") or "").lower()

    source = _read_source_file(repo_root, file_ref)
    fm, body = _parse_frontmatter(source) if source else ({}, "")

    meta_description = str(fm.get("description") or "").strip()
    h1_match = _re.search(r"^#\s+(.+)$", body, _re.MULTILINE)
    h1 = h1_match.group(1).strip() if h1_match else ""
    h2s = _re.findall(r"^##\s+(.+)$", body, _re.MULTILINE)
    h3s = _re.findall(r"^###\s+(.+)$", body, _re.MULTILINE)

    # Count plain text words (strip markdown syntax)
    plain = _re.sub(r"```.*?```", " ", body, flags=_re.DOTALL)
    plain = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
    plain = _re.sub(r"[#*_`>|]", " ", plain)
    actual_word_count = len(plain.split())

    # Keyword occurrences in body
    kw_occurrences = len(_re.findall(_re.escape(keyword), body.lower())) if keyword else 0
    kw_density = round(kw_occurrences / max(actual_word_count, 1) * 100, 2)

    # First paragraph (first non-empty, non-heading line)
    first_para = ""
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            first_para = line.lower()
            break

    # Internal / external links
    all_links = _re.findall(r"\[([^\]]*)\]\(([^)]+)\)", body)
    internal_links = [l for l in all_links if not l[1].startswith("http") or "pageseeds" in l[1]]
    broken_placeholders = [l for l in all_links if "TODO" in l[1] or l[1].strip() in ("", "#")]

    checks: dict[str, Any] = {}

    # 1. Title contains keyword
    checks["title_keyword"] = {
        "pass": keyword in title.lower() if keyword else None,
        "label": "Title contains keyword",
    }

    # 2. H1 contains keyword
    checks["h1_keyword"] = {
        "pass": keyword in h1.lower() if (keyword and h1) else (None if not h1 else False),
        "label": "H1 contains keyword",
    }

    # 3. Meta description present
    checks["meta_desc_present"] = {
        "pass": bool(meta_description),
        "label": "Meta description present",
    }

    # 4. Meta description contains keyword
    checks["meta_desc_keyword"] = {
        "pass": keyword in meta_description.lower() if (keyword and meta_description) else False,
        "label": "Meta description contains keyword",
    }

    # 5. Meta description length (≤155 chars)
    checks["meta_desc_length"] = {
        "pass": 50 <= len(meta_description) <= 155 if meta_description else False,
        "value": len(meta_description),
        "label": "Meta description length 50–155 chars",
    }

    # 6. Keyword in first paragraph
    checks["keyword_first_para"] = {
        "pass": keyword in first_para if keyword else None,
        "label": "Keyword in first paragraph",
    }

    # 7. Word count ≥ 800
    checks["word_count"] = {
        "pass": actual_word_count >= 800,
        "value": actual_word_count,
        "label": "Word count ≥ 800",
    }

    # 8. Keyword density 0.2–0.8%
    checks["keyword_density"] = {
        "pass": 0.2 <= kw_density <= 0.8 if keyword else None,
        "value": f"{kw_density}%",
        "occurrences": kw_occurrences,
        "label": "Keyword density 0.2–0.8%",
    }

    # 9. H2 structure (≥2 H2s)
    checks["h2_structure"] = {
        "pass": len(h2s) >= 2,
        "value": len(h2s),
        "label": "Has ≥2 H2 headings",
    }

    # 10. Internal links (≥3)
    checks["internal_links"] = {
        "pass": len(internal_links) >= 3,
        "value": len(internal_links),
        "label": "Has ≥3 internal links",
    }

    # 11. Broken/placeholder links
    checks["broken_links"] = {
        "pass": len(broken_placeholders) == 0,
        "value": len(broken_placeholders),
        "issues": [{"text": l[0], "href": l[1]} for l in broken_placeholders],
        "label": "No broken/placeholder links",
    }

    # 12. GSC data present
    checks["gsc_data"] = {
        "pass": gsc is not None,
        "label": "GSC data synced",
        "value": gsc,
    }

    # 13. Source file found
    checks["source_file_found"] = {
        "pass": source is not None,
        "label": "Source file readable",
    }

    # Scoring: each failed check costs points; critical failures cost more
    WEIGHTS = {
        "broken_links": 30,
        "source_file_found": 20,
        "title_keyword": 10,
        "h1_keyword": 10,
        "meta_desc_keyword": 10,
        "keyword_first_para": 8,
        "keyword_density": 8,
        "meta_desc_present": 7,
        "meta_desc_length": 5,
        "word_count": 5,
        "h2_structure": 3,
        "internal_links": 3,
        "gsc_data": 1,
    }
    penalty = 0
    for key, weight in WEIGHTS.items():
        c = checks.get(key, {})
        if c.get("pass") is False:
            penalty += weight

    health_score = max(0, 100 - penalty)

    if health_score >= 85:
        health = "good"
    elif health_score >= 60:
        health = "needs_improvement"
    else:
        health = "poor"

    # Flags that drive review priority
    critical_issues = sum(
        1 for k in ("broken_links", "source_file_found", "title_keyword")
        if checks.get(k, {}).get("pass") is False
    )
    high_issues = sum(
        1 for k in ("meta_desc_keyword", "keyword_first_para", "keyword_density", "h1_keyword")
        if checks.get(k, {}).get("pass") is False
    )

    # GSC-based priority boost: low impressions on old articles
    gsc_priority_boost = 0
    if gsc is None and published_date:
        try:
            pub = _dt.date.fromisoformat(published_date)
            age_days = (_dt.date.today() - pub).days
            if age_days > 60:
                gsc_priority_boost = 15  # old article, no GSC signal
        except Exception:
            pass
    elif gsc:
        impressions = int(gsc.get("impressions") or 0)
        if impressions == 0:
            gsc_priority_boost = 10
        elif impressions < 50:
            gsc_priority_boost = 5

    priority_score = penalty + gsc_priority_boost

    return {
        "id": article.get("id"),
        "title": title,
        "url_slug": article.get("url_slug"),
        "file": file_ref,
        "target_keyword": keyword,
        "status": status,
        "published_date": published_date,
        "word_count": actual_word_count,
        "gsc": gsc,
        "health_score": health_score,
        "health": health,
        "priority_score": priority_score,
        "critical_issues": critical_issues,
        "high_issues": high_issues,
        "checks": checks,
        "checks_passed": sum(1 for c in checks.values() if c.get("pass") is True),
        "checks_failed": sum(1 for c in checks.values() if c.get("pass") is False),
        "checks_total": len(checks),
    }


def cmd_content_audit(args: Namespace) -> int:
    """Batch deterministic content audit across all articles.

    Reads articles.json, runs every content check on each article source file,
    scores and ranks them, then writes content_audit.json and prints a summary.
    No LLM or external API calls — runs in seconds even for 150+ articles.
    """
    repo_root = Path(getattr(args, "repo_root", "") or "").expanduser().resolve() or Path.cwd().resolve()
    workspace_dir_name = getattr(args, "workspace_dir", "") or "automation"
    workspace_dir = (repo_root / workspace_dir_name).resolve()
    articles_path = workspace_dir / "articles.json"
    out_path = workspace_dir / "content_audit.json"
    status_filter = getattr(args, "status", "") or ""
    dry_run = bool(getattr(args, "dry_run", False))
    top_n = int(getattr(args, "top", 0) or 0)

    if not articles_path.exists():
        print(f"Error: articles.json not found at {articles_path}", file=sys.stderr)
        return 1

    try:
        raw_data = json.loads(articles_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading articles.json: {e}", file=sys.stderr)
        return 1

    articles_wrapper: dict[str, Any] | None = None
    if isinstance(raw_data, dict):
        articles_wrapper = raw_data
        articles: list[dict[str, Any]] = raw_data.get("articles", [])
    else:
        articles = raw_data

    if not isinstance(articles, list):
        print("Error: articles.json must contain a list of article objects", file=sys.stderr)
        return 1

    # Filter to published (or requested status)
    if status_filter:
        to_audit = [a for a in articles if str(a.get("status") or "").lower() == status_filter.lower()]
    else:
        # Default: audit published articles (skip pure drafts)
        to_audit = [a for a in articles if str(a.get("status") or "").lower() in ("published", "live", "")]

    if not to_audit:
        print(f"No articles to audit (status filter: '{status_filter or 'published'}')", file=sys.stderr)
        return 0

    print(f"Auditing {len(to_audit)} articles...", file=sys.stderr)

    results: list[dict[str, Any]] = []
    for i, article in enumerate(to_audit, 1):
        title_short = str(article.get("title") or article.get("url_slug") or f"article-{i}")[:60]
        print(f"  [{i}/{len(to_audit)}] {title_short}", file=sys.stderr)
        audit = _audit_article(article, repo_root)
        results.append(audit)

    # Sort: most-needing-attention first (highest priority_score → worst first)
    results.sort(key=lambda r: (-r["priority_score"], r["health_score"]))

    if top_n:
        results = results[:top_n]

    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    summary_counts = {
        "good": sum(1 for r in results if r["health"] == "good"),
        "needs_improvement": sum(1 for r in results if r["health"] == "needs_improvement"),
        "poor": sum(1 for r in results if r["health"] == "poor"),
    }

    output: dict[str, Any] = {
        "generated_at": now_iso,
        "repo_root": str(repo_root),
        "articles_path": str(articles_path),
        "total_audited": len(results),
        "health_summary": summary_counts,
        "articles": results,
    }

    if not dry_run:
        out_path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\n  Written: {out_path}", file=sys.stderr)
    else:
        print("\n  Dry run — content_audit.json not written", file=sys.stderr)

    # Print summary table to stderr
    print(f"\n{'─'*72}", file=sys.stderr)
    print(f"  {'#':<4} {'Health':<18} {'Score':>5}  {'Fail':>4}  Title", file=sys.stderr)
    print(f"{'─'*72}", file=sys.stderr)
    for i, r in enumerate(results, 1):
        health_label = {"good": "✓ good", "needs_improvement": "⚠ needs work", "poor": "✗ poor"}.get(r["health"], r["health"])
        title_trunc = (r["title"] or r["url_slug"] or "")[:35]
        print(
            f"  {i:<4} {health_label:<18} {r['health_score']:>5}  {r['checks_failed']:>4}  {title_trunc}",
            file=sys.stderr,
        )
    print(f"{'─'*72}", file=sys.stderr)
    print(
        f"  Total: {len(results)} articles | "
        f"Good: {summary_counts['good']} | "
        f"Needs work: {summary_counts['needs_improvement']} | "
        f"Poor: {summary_counts['poor']}",
        file=sys.stderr,
    )

    _print_json(output)
    return 0


def cmd_crawl_404s(args: Namespace) -> int:
    """Crawl website to find 404 errors.
    
    Crawls sitemap and internal links to find broken links (404s).
    This is fully automated - no GSC API or manual exports needed.
    """
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else (repo_root / ".github" / "automation" / "output" / "crawl_404s")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()
    
    # Determine site URL
    site_url = args.site
    sitemap_url = args.sitemap_url
    
    if not site_url:
        manifest_path = Path(args.manifest) if args.manifest else repo_root / ".github" / "automation" / "manifest.json"
        manifest = _load_manifest(manifest_path)
        site_url = manifest.get("url", "")
        if not site_url:
            print("Error: No site URL specified. Use --site or ensure manifest.json has 'url'", file=sys.stderr)
            return 1
        if not sitemap_url:
            sitemap_url = manifest.get("sitemap") or f"{site_url.rstrip('/')}/sitemap.xml"
    
    if not sitemap_url:
        sitemap_url = f"{site_url.rstrip('/')}/sitemap.xml"
    
    try:
        from .seo.crawler import CrawlConfig, crawl_site, generate_crawl_404_report
        
        print(f"Crawling site: {site_url}", file=sys.stderr)
        print(f"Sitemap: {sitemap_url}", file=sys.stderr)
        print(f"Max pages: {args.max_pages}, Max depth: {args.max_depth}", file=sys.stderr)
        
        # Fetch sitemap
        print("Fetching sitemap...", file=sys.stderr)
        sitemap_urls = _load_urls_from_sitemap(sitemap_url)
        print(f"Found {len(sitemap_urls)} URLs in sitemap", file=sys.stderr)
        
        # Configure crawl
        config = CrawlConfig(
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            workers=args.workers,
            delay_ms=args.delay_ms,
            timeout_seconds=args.timeout,
        )
        
        # Crawl
        print("Crawling...", file=sys.stderr)
        results = crawl_site(
            start_url=site_url,
            sitemap_urls=sitemap_urls,
            config=config,
        )
        
        # Generate report
        report_meta = generate_crawl_404_report(
            results=results,
            site_url=site_url,
            out_dir=out_dir,
        )
        
        print(f"\n✓ Crawl complete:", file=sys.stderr)
        print(f"  Pages crawled: {report_meta['total_crawled']}", file=sys.stderr)
        print(f"  404s found: {report_meta['total_404s']}", file=sys.stderr)
        print(f"  Action queue: {report_meta['action_queue']}", file=sys.stderr)
        print(f"  Fix plan: {report_meta['fix_plan']}", file=sys.stderr)
        
        _print_json(report_meta)
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
