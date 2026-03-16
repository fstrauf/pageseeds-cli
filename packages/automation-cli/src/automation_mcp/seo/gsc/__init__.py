"""Google Search Console integration for automation-mcp.

This module provides unified access to GSC APIs:
- Search Analytics (performance data, queries)
- URL Inspection (index status, coverage)
- Site management

All credential resolution uses secrets.env as the authoritative source.
"""

from .credentials import resolve_service_account_path, resolve_oauth_client_secrets_path
from .client import get_search_console_service, list_sites, auto_select_site_property
from .analytics import fetch_page_rows, fetch_queries_for_page, compute_movers
from .indexing import inspect_url, InspectionRecord, classify_record, priority_for_record
from .reports import generate_indexing_report, generate_site_scan_report
from .coverage import (
    parse_coverage_csv,
    generate_coverage_404_report,
    Coverage404Record,
)
from .redirects import (
    parse_redirect_csv,
    generate_redirect_report,
    RedirectRecord,
)

__all__ = [
    # Credentials
    "resolve_service_account_path",
    "resolve_oauth_client_secrets_path",
    # Client
    "get_search_console_service",
    "list_sites",
    "auto_select_site_property",
    # Analytics
    "fetch_page_rows",
    "fetch_queries_for_page",
    "compute_movers",
    # Indexing
    "inspect_url",
    "InspectionRecord",
    "classify_record",
    "priority_for_record",
    # Coverage 404s
    "parse_coverage_csv",
    "generate_coverage_404_report",
    "Coverage404Record",
    # Redirect analysis
    "parse_redirect_csv",
    "generate_redirect_report",
    "RedirectRecord",
    # Reports
    "generate_indexing_report",
    "generate_site_scan_report",
]
