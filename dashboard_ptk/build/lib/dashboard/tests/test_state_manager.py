"""
Tests for StateManager
"""
import json
import tempfile
from pathlib import Path
from datetime import datetime

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dashboard.core.state_manager import StateManager, StateError, PathResolver, TaskValidator
from dashboard.models import Project, Task


def test_path_resolver():
    """Test PathResolver finds correct paths."""
    print("\n=== Testing PathResolver ===")
    
    # Create temp project structure
    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        automation_dir = repo_root / ".github" / "automation"
        automation_dir.mkdir(parents=True)
        
        # Create content dir
        content_dir = repo_root / "content"
        content_dir.mkdir()
        (content_dir / "test.md").write_text("# Test")
        
        # Create articles.json
        (automation_dir / "articles.json").write_text(json.dumps({"articles": []}))
        
        project = Project(name="Test", website_id="test", repo_root=str(repo_root))
        resolver = PathResolver(project)
        
        # Test content dir detection
        found_content = resolver.get_content_dir()
        assert found_content == content_dir, f"Expected {content_dir}, got {found_content}"
        print("✓ Content directory detected")
        
        # Test articles.json detection
        found_articles = resolver.get_articles_json_path()
        assert found_articles == automation_dir / "articles.json", f"Expected {automation_dir / 'articles.json'}, got {found_articles}"
        print("✓ Articles.json detected")


def test_task_validator():
    """Test TaskValidator catches invalid tasks."""
    print("\n=== Testing TaskValidator ===")
    
    validator = TaskValidator()
    
    # Valid task
    valid_task = Task(
        id="COF-001",
        type="write_article",
        title="Test Article",
        phase="implementation",
        status="todo"
    )
    validator.validate_task(valid_task)
    print("✓ Valid task passes validation")
    
    # Invalid status
    try:
        invalid_task = Task(
            id="COF-002",
            type="write_article",
            title="Test",
            phase="implementation",
            status="invalid_status"
        )
        validator.validate_task(invalid_task)
        assert False, "Should have raised StateError"
    except StateError:
        print("✓ Invalid status caught")
    
    # Missing title
    try:
        invalid_task = Task(
            id="COF-003",
            type="write_article",
            title="",
            phase="implementation",
            status="todo"
        )
        validator.validate_task(invalid_task)
        assert False, "Should have raised StateError"
    except StateError:
        print("✓ Missing title caught")


def test_state_manager_basic():
    """Test StateManager basic operations."""
    print("\n=== Testing StateManager Basic Operations ===")
    
    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        automation_dir = repo_root / ".github" / "automation"
        automation_dir.mkdir(parents=True)
        
        # Create content dir
        (repo_root / "content").mkdir()
        (repo_root / "content" / "test.md").write_text("# Test")
        
        project = Project(name="Test", website_id="test_site", repo_root=str(repo_root))
        
        # Create state manager
        sm = StateManager(project)
        print(f"✓ StateManager initialized with {len(sm.tasks)} tasks")
        
        # Create task
        task = sm.create_task(
            task_type="write_article",
            title="Test Article",
            phase="implementation",
            priority="high"
        )
        print(f"✓ Created task: {task.id}")
        
        # Verify task was saved
        sm2 = StateManager(project)
        assert len(sm2.tasks) == 1, f"Expected 1 task, got {len(sm2.tasks)}"
        assert sm2.tasks[0].id == task.id
        print("✓ Task persisted to disk")
        
        # Update status
        sm.update_task_status(task.id, "in_progress")
        assert sm.get_task(task.id).status == "in_progress"
        print("✓ Status updated")
        
        # Complete task
        sm.update_task_status(task.id, "done")
        assert sm.get_task(task.id).status == "done"
        print("✓ Task completed")


def test_unique_ids():
    """Test that task IDs are always unique."""
    print("\n=== Testing Unique ID Generation ===")
    
    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        (repo_root / ".github" / "automation").mkdir(parents=True)
        (repo_root / "content").mkdir()
        (repo_root / "content" / "test.md").write_text("test")
        
        project = Project(name="Test", website_id="coffee", repo_root=str(repo_root))
        sm = StateManager(project)
        
        # Create multiple tasks
        ids = []
        for i in range(5):
            task = sm.create_task(
                task_type="write_article",
                title=f"Article {i}",
                phase="implementation"
            )
            ids.append(task.id)
        
        # Check all IDs are unique
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"
        print(f"✓ All 5 IDs unique: {ids}")
        
        # Check sequential
        expected = ["COF-001", "COF-002", "COF-003", "COF-004", "COF-005"]
        assert ids == expected, f"Expected {expected}, got {ids}"
        print("✓ IDs are sequential")


def test_duplicate_detection():
    """Test that duplicate IDs are detected and prevented."""
    print("\n=== Testing Duplicate Detection ===")
    
    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        (repo_root / ".github" / "automation").mkdir(parents=True)
        (repo_root / "content").mkdir()
        (repo_root / "content" / "test.md").write_text("test")
        
        project = Project(name="Test", website_id="test", repo_root=str(repo_root))
        sm = StateManager(project)
        
        # Manually inject duplicate
        sm._tasks.append(Task(
            id="DUP-001",
            type="write_article",
            title="First",
            phase="implementation",
            status="todo"
        ))
        sm._tasks.append(Task(
            id="DUP-001",  # Duplicate!
            type="write_article",
            title="Second",
            phase="implementation",
            status="todo"
        ))
        sm._dirty = True
        
        try:
            sm._save()
            assert False, "Should have raised StateError for duplicates"
        except StateError as e:
            print(f"✓ Duplicate detection works: {e}")


def test_delete_task():
    """Test task deletion removes all duplicates."""
    print("\n=== Testing Task Deletion ===")
    
    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        (repo_root / ".github" / "automation").mkdir(parents=True)
        (repo_root / "content").mkdir()
        (repo_root / "content" / "test.md").write_text("test")
        
        project = Project(name="Test", website_id="test", repo_root=str(repo_root))
        sm = StateManager(project)
        
        # Create tasks
        t1 = sm.create_task("write_article", "Article 1", "implementation")
        t2 = sm.create_task("write_article", "Article 2", "implementation")
        t3 = sm.create_task("write_article", "Article 3", "implementation")
        
        assert len(sm.tasks) == 3
        print(f"✓ Created 3 tasks")
        
        # Delete middle task
        result = sm.delete_task(t2.id)
        assert result == True
        assert len(sm.tasks) == 2
        assert sm.get_task(t2.id) is None
        print(f"✓ Deleted task {t2.id}, 2 tasks remain")
        
        # Try delete non-existent
        result = sm.delete_task("NONEXISTENT")
        assert result == False
        print("✓ Delete non-existent returns False")


def test_ready_tasks():
    """Test getting ready tasks respects dependencies."""
    print("\n=== Testing Ready Tasks ===")
    
    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        (repo_root / ".github" / "automation").mkdir(parents=True)
        (repo_root / "content").mkdir()
        (repo_root / "content" / "test.md").write_text("test")
        
        project = Project(name="Test", website_id="test", repo_root=str(repo_root))
        sm = StateManager(project)
        
        # Create tasks with dependency
        t1 = sm.create_task("research_keywords", "Research", "research")
        t2 = sm.create_task("write_article", "Write", "implementation", depends_on=t1.id)
        t3 = sm.create_task("write_article", "Independent", "implementation")
        
        # Initially only t3 should be ready (no dependencies)
        ready = sm.get_ready_tasks()
        assert len(ready) == 1 and ready[0].id == t3.id
        print("✓ Only independent task ready initially")
        
        # Complete t1
        sm.update_task_status(t1.id, "done")
        
        # Now t2 should also be ready
        ready = sm.get_ready_tasks()
        ready_ids = {t.id for t in ready}
        assert t2.id in ready_ids and t3.id in ready_ids
        print("✓ Dependent task ready after parent done")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Running StateManager Tests")
    print("=" * 60)
    
    tests = [
        test_path_resolver,
        test_task_validator,
        test_state_manager_basic,
        test_unique_ids,
        test_duplicate_detection,
        test_delete_task,
        test_ready_tasks,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
