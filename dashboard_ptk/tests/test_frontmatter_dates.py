"""Tests for deterministic frontmatter date updates."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.frontmatter_dates import update_frontmatter_date


def test_update_frontmatter_date_updates_only_frontmatter() -> None:
    raw = """---
title: Example
date: "2030-01-01"
---
Body line
date: "2099-12-31"
"""
    updated, changed = update_frontmatter_date(raw, "2026-03-04")

    assert changed is True
    assert 'date: "2026-03-04"' in updated
    assert 'date: "2099-12-31"' in updated
    assert updated.count('date: "') == 2


def test_update_frontmatter_date_no_frontmatter_date_no_change() -> None:
    raw = """---
title: Example
---
Body
"""
    updated, changed = update_frontmatter_date(raw, "2026-03-04")
    assert changed is False
    assert updated == raw


if __name__ == "__main__":
    test_update_frontmatter_date_updates_only_frontmatter()
    test_update_frontmatter_date_no_frontmatter_date_no_change()
    print("ok")
