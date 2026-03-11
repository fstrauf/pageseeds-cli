#!/usr/bin/env python3
"""Quick sanity check for seo_filter_new_keywords logic (local test)."""

from seo_content_mcp.server import _filter_new_keywords


def main() -> None:
    # Workspace root is detected by the server in production, but for local tests
    # we can point directly at the repo root.
    from pathlib import Path
    workspace_root = str(Path(__file__).resolve().parents[2])

    result = _filter_new_keywords(
        workspace_root=workspace_root,
        website_path="general/coffee",
        keywords=[
            "best coffee beans for espresso",  # existing
            "Best coffee beans for espresso!",  # canonical match
            "coffee storage container",  # not sure if existing
            "coffee storage",  # existing
            "coffee price comparison australia",  # existing
            "best coffee beans nz",  # likely new
        ],
        enable_fuzzy=True,
        fuzzy_threshold=0.92,
    )

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
