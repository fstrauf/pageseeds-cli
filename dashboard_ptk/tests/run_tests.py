#!/usr/bin/env python3
"""
Test runner for dashboard_ptk tests.
"""
import sys
import os
import importlib.util

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def run_test_file(test_file):
    """Run a single test file."""
    print(f"\n{'='*60}")
    print(f"Running: {test_file}")
    print('='*60)
    
    test_path = os.path.join(os.path.dirname(__file__), test_file)
    
    # Run the test file
    result = os.system(f'{sys.executable} "{test_path}"')
    
    return result == 0


def main():
    """Run all tests."""
    test_files = ["test_errors.py"]

    has_rich = importlib.util.find_spec("rich") is not None
    if has_rich:
        test_files.extend(
            [
                "test_slug_generation.py",
                "test_date_manager.py",
                "test_integrity_checker.py",
                "test_content_sync.py",
                "test_reddit_autopost_preflight.py",
            ]
        )
    else:
        print("Skipping legacy utility tests (rich not installed).")

    test_files.extend(
        [
            "test_run_sh_bootstrap.py",
            "test_cli_entrypoint_health.py",
            "test_cli_composition.py",
            "test_env_resolver.py",
            "test_agent_runtime_tempfiles.py",
            "test_content_locator.py",
            "test_workflow_bundle_contract.py",
            "test_frontmatter_dates.py",
            "test_project_manager.py",
            "test_reddit_cli_auth_status.py",
            "test_reddit_history_path.py",
            "test_project_preflight.py",
            "test_orchestrator_policy.py",
            "test_orchestrator_service.py",
            "test_scheduler_policy_load_defaults.py",
            "test_scheduler_due_and_dedupe.py",
            "test_scheduler_system_service.py",
            "test_scheduler_service_cycle.py",
            "test_scheduler_status_file_contract.py",
            "test_engine_migration.py",
            "test_task_list_safety.py",
            "test_tool_registry.py",
            "test_normalizers_engine.py",
            "test_no_subprocess_outside_engine.py",
        ]
    )
    
    print("╔" + "═"*58 + "╗")
    print("║" + " "*18 + "DASHBOARD PTK TEST SUITE" + " "*18 + "║")
    print("╚" + "═"*58 + "╝")
    
    results = []
    for test_file in test_files:
        success = run_test_file(test_file)
        results.append((test_file, success))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed
    
    for test_file, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {test_file}")
    
    print()
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    
    if failed > 0:
        print("\nSome tests failed!")
        return 1
    else:
        print("\nAll tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
