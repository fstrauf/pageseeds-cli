"""
SEO MCP Server: A free SEO tool MCP (Model Control Protocol) service based on Ahrefs data. Includes features such as backlinks, keyword ideas, and more.
"""
import requests
import subprocess
import time
import os
import urllib.parse
import json
from typing import Dict, List, Optional, Any, Literal

from fastmcp import FastMCP

from seo_mcp.backlinks import get_backlinks, load_signature_from_cache, get_signature_and_overview
from seo_mcp.keywords import get_keyword_difficulty
from seo_mcp.traffic import check_traffic

from .secrets import load_capsolver_api_key


def custom_serializer(data: Any) -> str:
    """
    Custom tool serializer to ensure proper serialization of return values.
    For string returns, pass through as-is. For other types, JSON serialize.
    This prevents FastMCP from wrapping strings in extra serialization.
    
    Reference: FastMCP 2.13.0rc2 Custom Tool Serialization
    https://docs.glama.ai/fastmcp/servers/server#custom-tool-serialization
    """
    if isinstance(data, str):
        return data
    return json.dumps(data)


# Initialize FastMCP with proper configuration:
# - strict_input_validation=False: Use flexible validation (Pydantic coercion) instead of strict JSON Schema
#   This allows LLM clients to send "10" for int parameters, which gets coerced correctly
# - tool_serializer: Custom serializer to handle string returns correctly and prevent double-serialization
#
# Reference: https://docs.glama.ai/fastmcp/servers/tools#input-validation-modes
mcp = FastMCP(
    "SEO MCP",
    strict_input_validation=False,
    tool_serializer=custom_serializer
)


def _capsolver_curl(endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Use curl subprocess to call CapSolver API (avoids requests library hanging in MCP context)
    
    Args:
        endpoint: API endpoint (e.g., 'createTask', 'getTaskResult')
        payload: JSON payload to send
        
    Returns:
        JSON response or None if failed
    """
    cmd = [
        'curl', '-s', '-X', 'POST',
        f'https://api.capsolver.com/{endpoint}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(payload),
        '--max-time', '10'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception:
        return None


def get_capsolver_token(site_url: str) -> Optional[str]:
    """
    Use CapSolver to solve the captcha and get a token
    
    Args:
        site_url: Site URL to query
        
    Returns:
        Verification token or None if failed
    """
    load_capsolver_api_key()
    api_key = os.environ.get("CAPSOLVER_API_KEY")
    if not api_key:
        return None
    
    # Step 1: Create task using curl
    resp = _capsolver_curl('createTask', {
        "clientKey": api_key,
        "task": {
            "type": 'AntiTurnstileTaskProxyLess',
            "websiteKey": "0x4AAAAAAAAzi9ITzSN9xKMi",
            "websiteURL": site_url,
            "metadata": {"action": ""}
        }
    })
    
    if not resp:
        return None
    
    task_id = resp.get("taskId")
    if not task_id:
        return None
 
    # Step 2: Poll for result with timeout (max 60 seconds)
    start_time = time.time()
    max_wait = 60
    
    while time.time() - start_time < max_wait:
        time.sleep(2)  # delay between polls
        
        resp = _capsolver_curl('getTaskResult', {
            "clientKey": api_key,
            "taskId": task_id
        })
        
        if not resp:
            continue
            
        status = resp.get("status")
        if status == "ready":
            token = resp.get("solution", {}).get('token')
            return token
        if status == "failed" or resp.get("errorId"):
            return None
    
    # Timeout reached
    return None


def _get_backlinks_list(domain: str) -> Optional[Dict[str, Any]]:
    """Plain-Python implementation for backlinks lookup (no MCP wrapper)."""
    # Try to get signature from cache
    signature, valid_until, overview_data = load_signature_from_cache(domain)

    # If no valid signature in cache, get a new one
    if not signature or not valid_until:
        # Step 1: Get token
        site_url = f"https://ahrefs.com/backlink-checker/?input={domain}&mode=subdomains"
        token = get_capsolver_token(site_url)
        if not token:
            raise Exception(f"Failed to get verification token for domain: {domain}")

        # Step 2: Get signature and validUntil
        signature, valid_until, overview_data = get_signature_and_overview(token, domain)
        if not signature or not valid_until:
            raise Exception(f"Failed to get signature for domain: {domain}")

    # Step 3: Get backlinks list
    backlinks = get_backlinks(signature, valid_until, domain)
    return {
        "overview": overview_data,
        "backlinks": backlinks,
    }


def _keyword_generator(keyword: str, country: str = "us", search_engine: str = "Google") -> Dict[str, Any]:
    """Plain-Python implementation for keyword ideas (no MCP wrapper)."""
    from seo_mcp.keywords import get_keyword_ideas

    try:
        site_url = f"https://ahrefs.com/keyword-generator/?country={country}&input={urllib.parse.quote(keyword)}"
        token = get_capsolver_token(site_url)
        if not token:
            missing_key = not os.environ.get("CAPSOLVER_API_KEY")
            return {
                "keyword": keyword,
                "country": country,
                "searchEngine": search_engine,
                "ideas": [],
                "questionIdeas": [],
                "all": [],
                "error": "capsolver_api_key_missing" if missing_key else "capsolver_token_failed",
            }

        ideas = get_keyword_ideas(token, keyword, country, search_engine)
        if ideas:
            return ideas

        return {
            "keyword": keyword,
            "country": country,
            "searchEngine": search_engine,
            "ideas": [],
            "questionIdeas": [],
            "all": [],
            "error": "no_results",
        }
    except Exception as e:
        return {
            "keyword": keyword,
            "country": country,
            "searchEngine": search_engine,
            "ideas": [],
            "questionIdeas": [],
            "all": [],
            "error": str(e),
        }


def _get_traffic(domain_or_url: str, country: str = "None", mode: Literal["subdomains", "exact"] = "subdomains") -> Optional[Dict[str, Any]]:
    """Plain-Python implementation for traffic estimates (no MCP wrapper)."""
    site_url = f"https://ahrefs.com/traffic-checker/?input={domain_or_url}&mode={mode}"
    token = get_capsolver_token(site_url)
    if not token:
        raise Exception(f"Failed to get verification token for domain: {domain_or_url}")
    return check_traffic(token, domain_or_url, mode, country)


def _keyword_difficulty(keyword: str, country: str = "us") -> Optional[Dict[str, Any]]:
    """Plain-Python implementation for keyword difficulty (no MCP wrapper)."""
    site_url = f"https://ahrefs.com/keyword-difficulty/?country={country}&input={urllib.parse.quote(keyword)}"
    token = get_capsolver_token(site_url)
    if not token:
        raise Exception(f"Failed to get verification token for keyword: {keyword}")
    return get_keyword_difficulty(token, keyword, country)


def _batch_keyword_difficulty(keywords: List[str], country: str = "us") -> Dict[str, Any]:
    """Plain-Python implementation for batch keyword difficulty (no MCP wrapper)."""
    results = []
    failed_keywords = []

    for keyword in keywords:
        try:
            token = get_capsolver_token(
                f"https://ahrefs.com/keyword-difficulty/?country={country}&input={urllib.parse.quote(keyword)}"
            )

            if not token:
                failed_keywords.append({
                    "keyword": keyword,
                    "error": "Failed to get CAPTCHA token",
                })
                continue

            kd_result = get_keyword_difficulty(token, keyword, country)

            if kd_result:
                results.append({
                    "keyword": keyword,
                    "difficulty": kd_result.get("difficulty", "N/A"),
                    "serp_count": len(kd_result.get("serp", {}).get("results", [])),
                    "top_result": kd_result.get("serp", {}).get("results", [{}])[0].get("url", "")
                    if kd_result.get("serp", {}).get("results")
                    else "",
                    "last_update": kd_result.get("lastUpdate", ""),
                })
            else:
                failed_keywords.append({
                    "keyword": keyword,
                    "error": "API returned no data",
                })

        except Exception as e:
            failed_keywords.append({
                "keyword": keyword,
                "error": str(e),
            })

    difficulties = [r["difficulty"] for r in results if isinstance(r["difficulty"], (int, float))]
    difficulty_distribution = {
        "very_easy": len([d for d in difficulties if d < 10]),
        "easy": len([d for d in difficulties if 10 <= d < 30]),
        "medium": len([d for d in difficulties if 30 <= d < 50]),
        "hard": len([d for d in difficulties if 50 <= d < 70]),
        "very_hard": len([d for d in difficulties if d >= 70]),
    }

    return {
        "total": len(keywords),
        "successful": len(results),
        "failed": len(failed_keywords),
        "results": results,
        "failed_keywords": failed_keywords,
        "summary": {
            "avg_difficulty": sum(difficulties) / len(difficulties) if difficulties else 0,
            "min_difficulty": min(difficulties) if difficulties else 0,
            "max_difficulty": max(difficulties) if difficulties else 0,
            "distribution": difficulty_distribution,
        },
    }


@mcp.tool()
def get_backlinks_list(domain: str) -> Optional[Dict[str, Any]]:
    """
    Get backlinks list for the specified domain
    Args:
        domain (str): The domain to query
    Returns:
        List of backlinks for the domain, containing title, URL, domain rating, etc.
    """
    return _get_backlinks_list(domain)


@mcp.tool()
def keyword_generator(keyword: str, country: str = "us", search_engine: str = "Google") -> Dict[str, Any]:
    """
    Find keyword ideas and variations for the specified keyword.
    
    Args:
        keyword: The keyword to search for ideas
        country: Country code (default: us)
        search_engine: Search engine to use (default: Google)
    
    Returns:
        Structured keyword idea suggestions grouped by regular and question-based variants.
    """
    return _keyword_generator(keyword=keyword, country=country, search_engine=search_engine)


@mcp.tool()
def get_traffic(domain_or_url: str, country: str = "None", mode: Literal["subdomains", "exact"] = "subdomains") -> Optional[Dict[str, Any]]:
    """
    Check the estimated search traffic for any website. 

    Args:
        domain_or_url (str): The domain or URL to query
        country (str): The country to query, default is "None"
        mode (["subdomains", "exact"]): The mode to use for the query
    Returns:
        Traffic data for the specified domain or URL
    """
    return _get_traffic(domain_or_url=domain_or_url, country=country, mode=mode)


@mcp.tool()
def keyword_difficulty(keyword: str, country: str = "us") -> Optional[Dict[str, Any]]:
    """
    Get keyword difficulty score and SERP analysis for a specific keyword.
    
    This tool analyzes how competitive a keyword is and what content currently ranks.
    Use this to evaluate keyword opportunity and understand the competitive landscape.
    
    Returns difficulty score (0-100), search volume context, and top 10 ranking pages with:
    - Page title and URL
    - Domain Rating (authority)
    - URL Rating (page authority)
    - Estimated traffic and keywords ranking
    
    Note: Use keyword_generator to find related keywords, use this to analyze competition.
    """
    return _keyword_difficulty(keyword=keyword, country=country)


@mcp.tool()
def batch_keyword_difficulty(keywords: List[str], country: str = "us") -> Dict[str, Any]:
    """
    Analyze keyword difficulty for multiple keywords in batch (sequential processing).
    
    This tool processes keywords one at a time to avoid rate limiting and provides
    progress updates. Each keyword takes ~15 seconds (CAPTCHA solving + API call).
    
    Args:
        keywords: List of keywords to analyze (recommended: 10-50 keywords)
        country: Country code for localized results (default: "us")
    
    Returns:
        Dictionary with:
        - total: Total number of keywords processed
        - successful: Number of successful analyses
        - failed: Number of failed analyses
        - results: List of keyword analysis results
        - summary: Quick overview of difficulty distribution
    
    Use this instead of calling keyword_difficulty multiple times for efficiency.
    """
    return _batch_keyword_difficulty(keywords=keywords, country=country)


def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()
