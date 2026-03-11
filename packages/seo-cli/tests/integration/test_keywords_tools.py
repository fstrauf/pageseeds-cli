import os
import sys
from importlib import reload
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))


def _load_server_module() -> object:
    """
    Import and reload the SEO MCP server module with the CAPSolver API key.

    The server module caches the API key at import time, so we refresh it after
    updating the environment to ensure live credentials are picked up.
    """
    capsolver_key = os.environ.get("CAPSOLVER_API_KEY")
    if not capsolver_key:
        pytest.skip(
            "Set CAPSOLVER_API_KEY to run live keyword integration tests.",
            allow_module_level=True,
        )

    import seo_mcp.server as server  # pylint: disable=import-error

    server.api_key = capsolver_key  # ensure runtime uses latest key
    return reload(server)


@pytest.fixture(scope="module")
def server_module():
    return _load_server_module()


def test_keyword_generator_returns_results(server_module):
    keyword = "ai writing"
    result = server_module.keyword_generator(keyword, country="us", search_engine="Google")

    assert isinstance(result, dict), "Keyword generator should return a dict response"
    assert result.get("keyword") == keyword
    assert not result.get("error"), f"Keyword generator error: {result.get('error')}"

    all_ideas = result.get("all")
    assert isinstance(all_ideas, list), "Expected list of keyword ideas in `all` bucket"
    assert all_ideas, "Expected at least one keyword idea"

    first_idea = all_ideas[0]
    assert "keyword" in first_idea, "Idea entries should include the keyword text"


def test_keyword_difficulty_returns_metrics(server_module):
    keyword = "ai writing"
    try:
        result = server_module.keyword_difficulty(keyword, country="us")
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "verification token" in message.lower():
            pytest.skip(f"CapSolver token unavailable: {message}")
        raise

    assert isinstance(result, dict), "Keyword difficulty should return structured metrics"
    assert "difficulty" in result, "Keyword difficulty score missing from response"
    assert isinstance(result["difficulty"], (int, float)), "Difficulty should be numeric"

    serp = result.get("serp", {}).get("results", [])
    assert isinstance(serp, list), "SERP results should be collected in a list"
