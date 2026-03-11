"""SEO Content MCP Server - Manage SEO content lifecycle"""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"
__all__ = ["main"]


def main(*args: Any, **kwargs: Any) -> Any:
    from .server import main as server_main

    return server_main(*args, **kwargs)
