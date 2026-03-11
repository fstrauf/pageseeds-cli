"""Reddit API helpers (no MCP).

These are small wrappers around redditwarp to support CLI-driven workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

import redditwarp.SYNC


@dataclass
class SubmissionSummary:
    post_id: str
    title: str | None
    url: str | None
    subreddit: str | None
    author: str | None
    upvotes: int | None
    comment_count: int | None
    created_at: str | None
    days_old: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    try:
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _days_old(dt: Any) -> int | None:
    if dt is None:
        return None
    try:
        now = datetime.now(timezone.utc)
        created = dt.astimezone(timezone.utc)
        delta = now - created
        return max(0, int(delta.total_seconds() // 86400))
    except Exception:
        return None


def search_submissions(
    *,
    query: str,
    subreddit: str = "",
    limit: int = 10,
    sort: str = "relevance",
    time: str = "all",
) -> list[dict[str, Any]]:
    """Search Reddit submissions via redditwarp.

    Returns a list of dicts with keys matching the DB workflow fields.
    """

    client = redditwarp.SYNC.Client()
    results: list[dict[str, Any]] = []

    for submission in client.p.submission.search(subreddit, query, limit, sort=sort, time=time):
        subreddit_name = None
        try:
            subreddit_name = submission.subreddit.name  # type: ignore[attr-defined]
        except Exception:
            subreddit_name = subreddit or None

        author = None
        try:
            author = submission.author_display_name or "[deleted]"  # type: ignore[attr-defined]
        except Exception:
            author = "[deleted]"

        created_at = None
        try:
            created_at = submission.created_at  # type: ignore[attr-defined]
        except Exception:
            created_at = None

        summary = SubmissionSummary(
            post_id=getattr(submission, "id36", None),
            title=getattr(submission, "title", None),
            url=getattr(submission, "permalink", None),
            subreddit=subreddit_name,
            author=author,
            upvotes=getattr(submission, "score", None),
            comment_count=getattr(submission, "comment_count", None),
            created_at=_iso(created_at),
            days_old=_days_old(created_at),
        )

        # Ensure post_id is always a string when present
        if summary.post_id is not None:
            summary.post_id = str(summary.post_id)

        results.append(summary.to_dict())

    return results
