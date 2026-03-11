"""Tests for Dashboard CLI mixin composition."""
from __future__ import annotations

import os
import sys
import importlib.util
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

HAS_PROMPT_TOOLKIT = importlib.util.find_spec("prompt_toolkit") is not None

if HAS_PROMPT_TOOLKIT:
    from dashboard.cli import Dashboard
    from dashboard.cli_articles import DashboardArticlesMixin
    from dashboard.cli_projects import DashboardProjectsMixin
    from dashboard.cli_task_actions import DashboardTaskActionsMixin
    from dashboard.cli_verification import DashboardVerificationMixin


def test_dashboard_inherits_cli_mixins() -> None:
    if not HAS_PROMPT_TOOLKIT:
        return
    assert issubclass(Dashboard, DashboardVerificationMixin)
    assert issubclass(Dashboard, DashboardArticlesMixin)
    assert issubclass(Dashboard, DashboardTaskActionsMixin)
    assert issubclass(Dashboard, DashboardProjectsMixin)


def test_dashboard_uses_mixin_method_implementations() -> None:
    if not HAS_PROMPT_TOOLKIT:
        return
    assert Dashboard.verify_setup is DashboardVerificationMixin.verify_setup
    assert Dashboard._articles_menu is DashboardArticlesMixin._articles_menu
    assert Dashboard._check_article_dates is DashboardVerificationMixin._check_article_dates
    assert Dashboard.work_on_task is DashboardTaskActionsMixin.work_on_task
    assert Dashboard._projects_menu is DashboardProjectsMixin._projects_menu


def test_mixin_methods_live_outside_main_cli_file() -> None:
    if not HAS_PROMPT_TOOLKIT:
        return
    verify_file = Path(Dashboard.verify_setup.__code__.co_filename).name
    articles_file = Path(Dashboard._articles_menu.__code__.co_filename).name
    task_actions_file = Path(Dashboard.work_on_task.__code__.co_filename).name
    projects_file = Path(Dashboard._projects_menu.__code__.co_filename).name

    assert verify_file == "cli_verification.py"
    assert articles_file == "cli_articles.py"
    assert task_actions_file == "cli_task_actions.py"
    assert projects_file == "cli_projects.py"


if __name__ == "__main__":
    test_dashboard_inherits_cli_mixins()
    test_dashboard_uses_mixin_method_implementations()
    test_mixin_methods_live_outside_main_cli_file()
    if not HAS_PROMPT_TOOLKIT:
        print("ok (skipped: prompt_toolkit not installed)")
        raise SystemExit(0)
    print("ok")
