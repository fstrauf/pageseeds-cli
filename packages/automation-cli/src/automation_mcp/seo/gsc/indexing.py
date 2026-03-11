"""URL Inspection API operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class InspectionRecord:
    """Result of a URL inspection."""
    url: str
    verdict: str | None
    coverage_state: str | None
    indexing_state: str | None
    robots_txt_state: str | None
    page_fetch_state: str | None
    crawl_allowed: bool | None
    indexing_allowed: bool | None
    last_crawl_time: str | None
    google_canonical: str | None
    user_canonical: str | None
    sitemaps: Sequence[str]
    raw: dict[str, Any]


def inspect_url(
    service: Any,
    url: str,
    site_url: str | None = None,
    language: str = "en-US",
) -> InspectionRecord:
    """Inspect a single URL's indexing status.
    
    Args:
        service: Search Console API service
        url: URL to inspect
        site_url: Site property URL (e.g., "sc-domain:example.com"). If None, uses url.
        language: Language code for the inspection
        
    Returns:
        InspectionRecord with all inspection data
    """
    body = {
        "inspectionUrl": url,
        "languageCode": language,
        "siteUrl": site_url if site_url else url,
    }

    try:
        result = service.urlInspection().index().inspect(body=body).execute()
    except Exception as e:
        # Return error record on failure
        return InspectionRecord(
            url=url,
            verdict="ERROR",
            coverage_state=str(e),
            indexing_state=None,
            robots_txt_state=None,
            page_fetch_state=None,
            crawl_allowed=None,
            indexing_allowed=None,
            last_crawl_time=None,
            google_canonical=None,
            user_canonical=None,
            sitemaps=[],
            raw={"error": str(e)},
        )

    inspection = result.get("inspectionResult", {})
    index_status = inspection.get("indexStatusResult", {})
    amp_result = inspection.get("ampResult", {})
    rich_result = inspection.get("richResult", {})
    
    # Get verdict from different result types
    verdict = index_status.get("verdict")
    if not verdict and amp_result:
        verdict = amp_result.get("verdict")
    if not verdict and rich_result:
        verdict = rich_result.get("verdict")

    return InspectionRecord(
        url=url,
        verdict=verdict,
        coverage_state=index_status.get("coverageState"),
        indexing_state=index_status.get("indexingState"),
        robots_txt_state=index_status.get("robotsTxtState"),
        page_fetch_state=index_status.get("pageFetchState"),
        crawl_allowed=index_status.get("crawlAllowed"),
        indexing_allowed=index_status.get("indexingAllowed"),
        last_crawl_time=index_status.get("lastCrawlTime"),
        google_canonical=index_status.get("googleCanonical"),
        user_canonical=index_status.get("userCanonical"),
        sitemaps=index_status.get("sitemap", []),
        raw=result,
    )


def classify_record(record: InspectionRecord) -> tuple[str, str]:
    """Classify inspection record into actionable bucket.
    
    Returns:
        Tuple of (reason_code, action_description)
    """
    # Critical issues first
    if record.crawl_allowed is False or (record.robots_txt_state or "").upper() == "BLOCKED":
        return (
            "robots_blocked",
            "Fix robots.txt / crawl allow; remove blocked URLs from sitemap until fixed."
        )

    if record.indexing_allowed is False:
        return (
            "noindex",
            "Remove/avoid noindex; ensure indexing is allowed for canonical URLs."
        )

    # Fetch errors (but not unspecified states)
    page_fetch = (record.page_fetch_state or "").upper()
    if page_fetch and page_fetch not in ("OK", "SUCCESSFUL", "PAGE_FETCH_STATE_UNSPECIFIED"):
        return (
            "fetch_error",
            "Fix fetchability (4xx/5xx/soft404/redirect); remove broken URLs from sitemap."
        )

    # Canonical mismatch
    if record.user_canonical and record.google_canonical:
        user_norm = record.user_canonical.rstrip("/").lower()
        google_norm = record.google_canonical.rstrip("/").lower()
        if user_norm != google_norm:
            return (
                "canonical_mismatch",
                "Align canonicals/redirects/internal links; ensure sitemap lists canonical URLs only."
            )

    # Non-PASS verdict
    if (record.verdict or "").upper() != "PASS":
        coverage = (record.coverage_state or "").lower()
        if "crawled" in coverage and "not" in coverage:
            return (
                "not_indexed_crawled",
                "Content quality/duplicate issue; improve uniqueness and internal links."
            )
        if "discovered" in coverage and "not" in coverage:
            return (
                "not_indexed_discovered",
                "Crawl budget/queue issue; improve internal links and content quality."
            )
        return (
            "not_indexed_other",
            "Triage via coverage/indexing states; improve internal links/content uniqueness."
        )

    return ("indexed_pass", "No action needed (indexed).")


def priority_for_record(record: InspectionRecord, reason_code: str) -> int:
    """Calculate priority for sorting (lower = more urgent).
    
    Args:
        record: Inspection record
        reason_code: Classification code from classify_record()
        
    Returns:
        Priority value (10-999, where 10 is most urgent)
    """
    if reason_code in ("robots_blocked", "noindex", "fetch_error"):
        return 10
    if reason_code == "canonical_mismatch":
        return 20
    if reason_code == "api_error":
        return 30
    if reason_code == "not_indexed_crawled":
        return 40
    if reason_code == "not_indexed_discovered":
        return 50
    if reason_code == "not_indexed_other":
        return 70
    return 999  # indexed_pass
