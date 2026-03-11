"""GSC API client builder and utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .credentials import resolve_service_account_path, resolve_oauth_client_secrets_path

SEARCH_CONSOLE_SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly"
]


def build_credentials_from_service_account(
    service_account_path: str,
    delegated_user: str | None = None,
) -> service_account.Credentials:
    """Build credentials from service account JSON file.
    
    Args:
        service_account_path: Path to service account JSON key file
        delegated_user: Optional workspace user to impersonate (domain-wide delegation)
        
    Returns:
        Service account credentials with Search Console scope
    """
    creds = service_account.Credentials.from_service_account_file(
        service_account_path,
        scopes=SEARCH_CONSOLE_SCOPES,
    )
    
    if delegated_user:
        creds = creds.with_subject(delegated_user)
    
    return creds


def build_credentials_from_oauth(
    client_secrets_path: str,
    token_path: str | None = None,
) -> UserCredentials:
    """Build credentials from OAuth client secrets (interactive flow).
    
    Args:
        client_secrets_path: Path to OAuth client secrets JSON
        token_path: Optional path to store/retrieve cached token
        
    Returns:
        User credentials (may trigger browser auth if no cached token)
    """
    from google.auth.transport.requests import Request
    
    if token_path and Path(token_path).exists():
        creds = UserCredentials.from_authorized_user_file(token_path, SEARCH_CONSOLE_SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if token_path:
                Path(token_path).parent.mkdir(parents=True, exist_ok=True)
                Path(token_path).write_text(creds.to_json(), encoding="utf-8")
            return creds

    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets_path,
        SEARCH_CONSOLE_SCOPES,
    )
    creds = flow.run_local_server(port=0)
    
    if token_path:
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        Path(token_path).write_text(creds.to_json(), encoding="utf-8")
    
    return creds


def get_search_console_service(
    service_account_path: str | None = None,
    oauth_client_secrets: str | None = None,
    delegated_user: str | None = None,
    repo_root: Path | None = None,
) -> Any:
    """Build Search Console API service.
    
    Tries service account first, falls back to OAuth if configured.
    
    Args:
        service_account_path: Optional explicit service account path
        oauth_client_secrets: Optional explicit OAuth client secrets path
        delegated_user: Optional workspace user to impersonate
        repo_root: Optional repo root for env file discovery
        
    Returns:
        Search Console API service object
        
    Raises:
        ValueError: If no credentials can be resolved
    """
    # Try service account first (preferred)
    sa_path = resolve_service_account_path(service_account_path, repo_root)
    
    if sa_path:
        credentials = build_credentials_from_service_account(sa_path, delegated_user)
    else:
        # Fall back to OAuth
        oauth_path = resolve_oauth_client_secrets_path(oauth_client_secrets, repo_root)
        if not oauth_path:
            raise ValueError(
                "No GSC credentials found. Set GSC_SERVICE_ACCOUNT_PATH in "
                "~/.config/automation/secrets.env or provide --service-account-path"
            )
        token_path = Path.home() / ".config" / "gsc-report" / "credentials.json"
        credentials = build_credentials_from_oauth(oauth_path, str(token_path))

    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def list_sites(service: Any) -> list[str]:
    """List all Search Console properties accessible to credentials.
    
    Args:
        service: Search Console API service from get_search_console_service()
        
    Returns:
        List of site URLs (e.g., "sc-domain:example.com", "https://www.example.com/")
    """
    resp = service.sites().list().execute()
    entries = resp.get("siteEntry", []) or []
    sites = [e.get("siteUrl") for e in entries if e.get("siteUrl")]
    return sorted(set(sites))


def auto_select_site_property(service: Any, base_url: str) -> str:
    """Auto-select best matching Search Console property.
    
    Args:
        service: Search Console API service
        base_url: Website base URL (e.g., "https://example.com")
        
    Returns:
        Best matching site property identifier
        
    Raises:
        RuntimeError: If no matching property found
    """
    sites = list_sites(service)
    if not sites:
        raise RuntimeError("No Search Console properties found for these credentials.")

    parsed = base_url.lower().rstrip("/")
    if not parsed.startswith(("http://", "https://")):
        parsed = "https://" + parsed

    # Extract hostname variants
    from urllib.parse import urlparse
    hostname = urlparse(parsed).netloc
    hostname_no_www = hostname[4:] if hostname.startswith("www.") else hostname

    candidates = [
        f"sc-domain:{hostname_no_www}",
        f"https://{hostname}/",
        f"http://{hostname}/",
    ]
    if hostname != hostname_no_www:
        candidates.insert(1, f"https://{hostname_no_www}/")
        candidates.insert(2, f"http://{hostname_no_www}/")

    # Find exact match
    for candidate in candidates:
        if candidate in sites:
            return candidate

    # Partial match
    for site in sites:
        site_lower = site.lower()
        if hostname_no_www in site_lower:
            return site

    raise RuntimeError(
        f"No Search Console property found for {base_url}. "
        f"Available: {', '.join(sites)}"
    )
