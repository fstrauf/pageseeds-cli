"""Website crawler for 404 detection.

Crawls sitemap and internal links to find broken links (404s).
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import urllib.request


@dataclass
class CrawlResult:
    """Result of crawling a single URL."""
    url: str
    status_code: int | None
    is_404: bool
    is_external: bool
    source_url: str | None  # Where we found this link
    content_type: str | None
    title: str | None
    crawl_time_ms: int
    error: str | None = None


@dataclass
class CrawlConfig:
    """Configuration for crawling."""
    max_pages: int = 500
    max_depth: int = 3
    workers: int = 5
    delay_ms: int = 100
    respect_robots: bool = False
    user_agent: str = "Mozilla/5.0 (compatible; SEO-Crawler/1.0)"
    timeout_seconds: int = 30
    check_external: bool = False
    include_paths: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)


def _normalize_url(url: str) -> str:
    """Normalize URL for comparison."""
    # Remove fragment
    url = url.split('#')[0]
    # Remove trailing slash except for root
    if len(url) > 1 and url.endswith('/'):
        url = url[:-1]
    return url


def _is_internal_url(url: str, base_domain: str) -> bool:
    """Check if URL belongs to the same domain."""
    parsed = urlparse(url)
    url_domain = parsed.netloc.lower()
    base_domain_lower = base_domain.lower()
    
    # Handle www variants
    if url_domain.startswith('www.'):
        url_domain = url_domain[4:]
    if base_domain_lower.startswith('www.'):
        base_domain_lower = base_domain_lower[4:]
    
    return url_domain == base_domain_lower or not url_domain


def _extract_links(html: str, base_url: str) -> list[str]:
    """Extract all href links from HTML."""
    # Simple regex-based extraction
    href_pattern = r'href=["\']([^"\']+)["\']'
    matches = re.findall(href_pattern, html, re.IGNORECASE)
    
    links = []
    for match in matches:
        # Skip anchors, javascript, mailto, tel
        if match.startswith('#') or match.startswith('javascript:'):
            continue
        if match.startswith('mailto:') or match.startswith('tel:'):
            continue
        if match.startswith('data:'):
            continue
        
        # Resolve relative URLs
        full_url = urljoin(base_url, match)
        links.append(full_url)
    
    return links


def _extract_title(html: str) -> str | None:
    """Extract page title from HTML."""
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if title_match:
        return title_match.group(1).strip()
    return None


def _should_crawl(url: str, config: CrawlConfig, base_domain: str) -> bool:
    """Check if URL should be crawled based on config."""
    parsed = urlparse(url)
    path = parsed.path
    
    # Skip common non-HTML resources
    skip_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.css', '.js', '.xml', '.json', '.zip', '.mp4', '.webm'}
    if any(path.lower().endswith(ext) for ext in skip_extensions):
        return False
    
    # Check include patterns
    if config.include_paths:
        if not any(pattern in path for pattern in config.include_paths):
            return False
    
    # Check exclude patterns
    for pattern in config.exclude_paths:
        if pattern in path:
            return False
    
    return True


def _fetch_url(url: str, config: CrawlConfig) -> tuple[int | None, str | None, str | None]:
    """Fetch URL and return status, content, content-type."""
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': config.user_agent},
            method='HEAD'  # Use HEAD first for efficiency
        )
        
        start = time.time()
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as response:
            status = response.getcode()
            content_type = response.headers.get('Content-Type', '').lower()
            elapsed = int((time.time() - start) * 1000)
            
            # For HTML pages, we need to fetch body to extract links
            if 'text/html' in content_type:
                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': config.user_agent},
                    method='GET'
                )
                with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
                    content = resp.read().decode('utf-8', errors='ignore')
                    return status, content, content_type
            
            return status, None, content_type
            
    except urllib.error.HTTPError as e:
        return e.code, None, None
    except Exception as e:
        return None, None, str(e)


def crawl_site(
    start_url: str,
    sitemap_urls: list[str] | None = None,
    config: CrawlConfig | None = None,
) -> list[CrawlResult]:
    """Crawl a website and find 404s.
    
    Args:
        start_url: Starting URL (e.g., https://www.example.com)
        sitemap_urls: Optional list of URLs from sitemap to seed crawl
        config: Crawl configuration
        
    Returns:
        List of crawl results including all 404s found
    """
    config = config or CrawlConfig()
    base_domain = urlparse(start_url).netloc
    
    results: list[CrawlResult] = []
    visited: set[str] = set()
    to_crawl: list[tuple[str, str | None, int]] = []  # (url, source_url, depth)
    
    # Seed with sitemap URLs if provided
    if sitemap_urls:
        for url in sitemap_urls[:config.max_pages]:
            to_crawl.append((url, None, 0))
    else:
        to_crawl.append((start_url, None, 0))
    
    def crawl_single(url: str, source_url: str | None, depth: int) -> CrawlResult:
        """Crawl a single URL."""
        normalized = _normalize_url(url)
        
        if normalized in visited:
            return CrawlResult(
                url=url,
                status_code=None,
                is_404=False,
                is_external=not _is_internal_url(url, base_domain),
                source_url=source_url,
                content_type=None,
                title=None,
                crawl_time_ms=0
            )
        
        visited.add(normalized)
        
        is_internal = _is_internal_url(url, base_domain)
        
        if not is_internal and not config.check_external:
            return CrawlResult(
                url=url,
                status_code=None,
                is_404=False,
                is_external=True,
                source_url=source_url,
                content_type=None,
                title=None,
                crawl_time_ms=0
            )
        
        start = time.time()
        status_code, content, content_type = _fetch_url(url, config)
        elapsed = int((time.time() - start) * 1000)
        
        # Small delay to be polite
        time.sleep(config.delay_ms / 1000)
        
        title = None
        links: list[str] = []
        
        if content:
            title = _extract_title(content)
            if is_internal and depth < config.max_depth:
                links = _extract_links(content, url)
                # Filter to internal links only
                links = [l for l in links if _is_internal_url(l, base_domain)]
        
        result = CrawlResult(
            url=url,
            status_code=status_code,
            is_404=(status_code == 404),
            is_external=not is_internal,
            source_url=source_url,
            content_type=content_type,
            title=title,
            crawl_time_ms=elapsed
        )
        
        # Queue new links to crawl
        for link in links:
            link_normalized = _normalize_url(link)
            if link_normalized not in visited and len(visited) < config.max_pages:
                if _should_crawl(link, config, base_domain):
                    to_crawl.append((link, url, depth + 1))
        
        return result
    
    # Crawl with thread pool
    with ThreadPoolExecutor(max_workers=config.workers) as executor:
        while to_crawl and len(visited) < config.max_pages:
            # Get batch of URLs to crawl
            batch = []
            while to_crawl and len(batch) < config.workers:
                batch.append(to_crawl.pop(0))
            
            # Submit batch
            futures = {
                executor.submit(crawl_single, url, source, depth): (url, source, depth)
                for url, source, depth in batch
            }
            
            # Collect results
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    url, source, depth = futures[future]
                    results.append(CrawlResult(
                        url=url,
                        status_code=None,
                        is_404=False,
                        is_external=False,
                        source_url=source,
                        content_type=None,
                        title=None,
                        crawl_time_ms=0,
                        error=str(e)
                    ))
    
    return results


def generate_crawl_404_report(
    results: list[CrawlResult],
    site_url: str,
    out_dir: Path,
) -> dict[str, Any]:
    """Generate a report from crawl results.
    
    Args:
        results: List of crawl results
        site_url: The site URL
        out_dir: Output directory
        
    Returns:
        Report metadata dict
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    site_slug = _slugify(site_url)
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Filter to 404s only
    fours = [r for r in results if r.is_404]
    
    # Group by source page
    by_source: dict[str, list[CrawlResult]] = {}
    for r in fours:
        source = r.source_url or "(direct/sitemap)"
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(r)
    
    # Build action queue
    action_queue = {
        "meta": {
            "run_ts": timestamp,
            "site_url": site_url,
            "total_crawled": len(results),
            "total_404s": len(fours),
            "crawl_version": "1.0",
        },
        "items": [
            {
                "url": r.url,
                "status_code": r.status_code,
                "source_url": r.source_url,
                "title": r.title,
            }
            for r in fours
        ],
        "by_source": {
            source: [
                {"url": r.url, "title": r.title}
                for r in items
            ]
            for source, items in by_source.items()
        },
    }
    
    # Write action queue
    action_queue_path = out_dir / f"crawl_404_{timestamp}_{site_slug}_action_queue.json"
    import json
    action_queue_path.write_text(json.dumps(action_queue, indent=2))
    
    # Generate fix plan markdown
    fix_plan_path = out_dir / f"crawl_404_{timestamp}_{site_slug}_fix_plan.md"
    fix_plan_content = _generate_crawl_fix_plan(site_url, timestamp, fours, by_source, results)
    fix_plan_path.write_text(fix_plan_content)
    
    # Generate summary CSV
    summary_csv_path = out_dir / f"crawl_404_{timestamp}_{site_slug}_summary.csv"
    _write_crawl_summary_csv(summary_csv_path, fours)
    
    return {
        "site_url": site_url,
        "timestamp": timestamp,
        "total_crawled": len(results),
        "total_404s": len(fours),
        "output_dir": str(out_dir),
        "action_queue": str(action_queue_path),
        "fix_plan": str(fix_plan_path),
        "summary_csv": str(summary_csv_path),
    }


def _slugify(value: str) -> str:
    """Create a safe filename slug."""
    import re
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_").strip("_")
    return value or "site"


def _generate_crawl_fix_plan(
    site_url: str,
    timestamp: str,
    fours: list[CrawlResult],
    by_source: dict[str, list[CrawlResult]],
    all_results: list[CrawlResult]
) -> str:
    """Generate a markdown fix plan from crawl results."""
    lines = [
        f"# Crawl 404 Fix Plan: {site_url}",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"Pages crawled: {len(all_results)}",
        f"404s found: {len(fours)}",
        f"",
    ]
    
    if not fours:
        lines.append("✅ No 404s found!")
        return "\n".join(lines)
    
    # Summary by source
    lines.append("## 404s by Source Page")
    lines.append("")
    lines.append("| Source Page | Broken Links |")
    lines.append("|-------------|--------------|")
    for source, items in sorted(by_source.items(), key=lambda x: -len(x[1])):
        source_display = source if len(source) < 50 else source[:47] + "..."
        lines.append(f"| {source_display} | {len(items)} |")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Detailed list
    lines.append("## All 404 URLs")
    lines.append("")
    
    for source, items in sorted(by_source.items(), key=lambda x: -len(x[1])):
        source_display = source if source != "(direct/sitemap)" else "In sitemap / direct access"
        lines.append(f"### From: {source_display}")
        lines.append("")
        for item in items:
            lines.append(f"- `{item.url}`")
            if item.title:
                lines.append(f"  - Title: {item.title}")
        lines.append("")
    
    # Implementation guide
    lines.extend([
        "## How to Fix",
        "",
        "For each 404, choose one of:",
        "",
        "1. **Add 301 redirect** → Content moved elsewhere",
        "2. **Restore content** → Page was accidentally deleted",
        "3. **Fix source link** → Internal link points to wrong URL",
        "4. **Remove link** → External backlink you can't control",
        "",
        "### Next.js Redirect Example",
        "```javascript",
        "// next.config.js",
        "async redirects() {",
        "  return [",
    ])
    
    # Add redirect examples for first 5 404s
    for item in fours[:5]:
        parsed = urlparse(item.url)
        path = parsed.path
        lines.append(f"    // {{ source: '{path}', destination: '/new-path', permanent: true }},")
    
    lines.extend([
        "  ];",
        "}",
        "```",
    ])
    
    return "\n".join(lines)


def _write_crawl_summary_csv(csv_path: Path, fours: list[CrawlResult]) -> None:
    """Write a summary CSV for easy review."""
    import csv
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['404_URL', 'Source_Page', 'Title', 'Status'])
        for r in fours:
            writer.writerow([r.url, r.source_url or '', r.title or '', r.status_code])
