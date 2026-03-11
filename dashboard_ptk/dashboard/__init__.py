"""
Task Dashboard - Modular Python Implementation
"""

__version__ = "1.0.0"


def main():
    """Console script entrypoint for pageseeds/task-dashboard."""
    import sys
    
    # If no arguments, launch dashboard (backward compatible)
    if len(sys.argv) <= 1:
        from .cli import Dashboard
        from .engine.runtime_config import RuntimeConfig
        from .workflow_bundle import legacy_seo_reddit_bundle

        bundle = legacy_seo_reddit_bundle()
        app = Dashboard(
            workflow_bundle=bundle,
            runtime_config=RuntimeConfig(required_clis=bundle.required_clis),
        )
        if not app.project_manager.current:
            app._clear_screen()
            selected = app.project_manager.select_project_interactive(app.session)
            if selected:
                app._activate_project(selected, show_report=True)
        else:
            app._activate_project(app.project_manager.current, show_report=False)
        app.main_menu()
    else:
        # Arguments provided - use unified CLI
        from .unified_cli import main as unified_main
        unified_main()


__all__ = ["Dashboard", "main"]


def __getattr__(name):
    if name == "Dashboard":
        from .cli import Dashboard

        return Dashboard
    raise AttributeError(name)
