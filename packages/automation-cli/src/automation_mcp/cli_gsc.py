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
        inspections: list[tuple[str, Any, str, str, int]] = []
        
        def inspect_worker(url: str) -> tuple[str, Any, str, str, int] | None:
            try:
                record = inspect_url(service, url, site_url=site_url, language=args.language)
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
