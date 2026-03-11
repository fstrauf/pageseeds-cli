"""Deterministic frontmatter date update helpers."""
from __future__ import annotations

import re


DATE_LINE_RE = re.compile(r"^(\s*date\s*:\s*)([^#\n\r]*)(\s*(?:#.*)?)(\r?\n?)$")


def update_frontmatter_date(content: str, new_date: str) -> tuple[str, bool]:
    """
    Update the `date:` key inside the first YAML frontmatter block.

    Returns a tuple of (updated_content, did_change). If no frontmatter date is
    found, content is returned unchanged with did_change=False.
    """
    lines = content.splitlines(keepends=True)
    if not lines:
        return content, False

    start_idx = _frontmatter_start_index(lines)
    if start_idx is None:
        return content, False

    end_idx = _frontmatter_end_index(lines, start_idx)
    if end_idx is None:
        return content, False

    for idx in range(start_idx + 1, end_idx):
        match = DATE_LINE_RE.match(lines[idx])
        if not match:
            continue
        prefix, _, suffix, newline = match.groups()
        replacement = f'{prefix}"{new_date}"{suffix}{newline or ""}'
        if replacement == lines[idx]:
            return content, False
        lines[idx] = replacement
        return "".join(lines), True

    return content, False


def _frontmatter_start_index(lines: list[str]) -> int | None:
    first = lines[0].lstrip("\ufeff")
    if first.strip() != "---":
        return None
    return 0


def _frontmatter_end_index(lines: list[str], start_idx: int) -> int | None:
    for idx in range(start_idx + 1, len(lines)):
        if lines[idx].strip() == "---":
            return idx
    return None
