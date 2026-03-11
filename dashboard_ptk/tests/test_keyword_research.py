#!/usr/bin/env python3
"""Test suite for keyword research functionality (using unified pageseeds CLI)."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

def test_seo_cli_available():
    """Test that pageseeds SEO commands are available."""
    print("\n[TEST] Checking pageseeds SEO availability...")
    result = subprocess.run(
        ['pageseeds', 'seo', '--help'],
        capture_output=True,
        text=True,
        timeout=10
    )
    if result.returncode == 0:
        print("  ✓ pageseeds seo is available")
        return True
    else:
        print("  ✗ pageseeds seo not found or not working")
        return False

def test_keyword_generator():
    """Test seo keywords command."""
    print("\n[TEST] Testing pageseeds seo keywords...")
    result = subprocess.run(
        ['pageseeds', 'seo', 'keywords', '--keyword', 'options trading', '--country', 'us'],
        capture_output=True,
        text=True,
        timeout=30
    )
    if result.returncode != 0:
        print(f"  ✗ Command failed: {result.stderr[:200]}")
        return False
    
    try:
        data = json.loads(result.stdout)
        if 'all' in data and len(data['all']) > 0:
            print(f"  ✓ Got {len(data['all'])} keyword ideas")
            return True
        else:
            print("  ✗ No keywords in response")
            return False
    except json.JSONDecodeError as e:
        print(f"  ✗ Invalid JSON: {e}")
        return False

def test_batch_keyword_difficulty():
    """Test seo batch-difficulty command."""
    print("\n[TEST] Testing pageseeds seo batch-difficulty...")
    
    # Create temp file with keywords
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("options trading\n")
        f.write("wheel strategy\n")
        keywords_file = f.name
    
    result = subprocess.run(
        ['pageseeds', 'seo', 'batch-difficulty', '--keywords-file', keywords_file, '--country', 'us'],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    Path(keywords_file).unlink(missing_ok=True)
    
    if result.returncode != 0:
        print(f"  ✗ Command failed: {result.stderr[:200]}")
        return False
    
    try:
        data = json.loads(result.stdout)
        if 'results' in data and len(data['results']) > 0:
            print(f"  ✓ Got KD data for {len(data['results'])} keywords")
            return True
        else:
            print("  ✗ No results in response")
            return False
    except json.JSONDecodeError as e:
        print(f"  ✗ Invalid JSON: {e}")
        return False

def test_instructions_file():
    """Test that instructions file exists and is valid."""
    print("\n[TEST] Checking instructions file...")
    instr_path = Path(__file__).parent.parent / "dashboard" / "tasks" / "keyword_research_instructions.md"
    
    if not instr_path.exists():
        print(f"  ✗ Instructions file not found: {instr_path}")
        return False
    
    content = instr_path.read_text()
    checks = [
        ('pageseeds seo keywords', 'seo keywords command'),
        ('pageseeds seo batch-difficulty', 'seo batch-difficulty command'),
        ('seed_keywords', 'seed_keywords field'),
        ('keyword_candidates', 'keyword_candidates field'),
    ]
    
    all_pass = True
    for pattern, name in checks:
        if pattern in content:
            print(f"  ✓ Has {name}")
        else:
            print(f"  ✗ Missing {name}")
            all_pass = False
    
    return all_pass

def test_ai_can_run_cli():
    """Test that AI can run CLI commands and produce output."""
    print("\n[TEST] Testing AI CLI execution...")
    
    prompt = """Run this command and show me the result:
pageseeds seo keywords --keyword "test keyword" --country us

Output only the JSON result in a ```json code block."""
    
    result = subprocess.run(
        ['kimi', '--print', '-p', prompt],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(Path(__file__).parent.parent)
    )
    
    if '```json' in result.stdout or 'keyword' in result.stdout.lower():
        print("  ✓ AI executed CLI command")
        return True
    else:
        print("  ✗ AI did not produce expected output")
        print(f"  Output preview: {result.stdout[:300]}")
        return False

def test_json_extraction():
    """Test the JSON extraction logic."""
    print("\n[TEST] Testing JSON extraction...")
    
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dashboard.tasks.research import ResearchRunner
    
    # Mock runner for testing
    class MockRunner:
        def __init__(self):
            pass
    
    runner = ResearchRunner.__new__(ResearchRunner)
    
    # Test various JSON formats
    test_cases = [
        # Code block format
        ('Some text\n```json\n{"seed_keywords": ["a"], "keyword_candidates": []}\n```\nMore text', True),
        # Direct JSON
        ('{"seed_keywords": ["a"], "keyword_candidates": [{"keyword": "test"}]}', True),
        # With newlines
        ('Result:\n{\n  "seed_keywords": ["a"],\n  "keyword_candidates": []\n}', True),
    ]
    
    all_pass = True
    for i, (input_text, should_find) in enumerate(test_cases):
        result = runner._extract_json_from_output(input_text)
        found = result is not None
        if found == should_find:
            print(f"  ✓ Case {i+1}: {'found' if found else 'not found'} JSON as expected")
        else:
            print(f"  ✗ Case {i+1}: expected {should_find}, got {found}")
            all_pass = False
    
    return all_pass

def test_no_mcp_config():
    """Test that MCP is not configured (to avoid conflicts)."""
    print("\n[TEST] Checking MCP configuration...")
    
    mcp_config = Path.home() / ".kimi" / "mcp.json"
    if not mcp_config.exists():
        print("  ✓ No MCP config file (good)")
        return True
    
    try:
        data = json.loads(mcp_config.read_text())
        servers = data.get('mcpServers', {})
        if 'seo-tools' in servers:
            print("  ✗ MCP server 'seo-tools' still configured - may cause conflicts")
            print("    Run: kimi mcp remove seo-tools")
            return False
        else:
            print("  ✓ No seo-tools MCP server")
            return True
    except Exception as e:
        print(f"  ? Could not read MCP config: {e}")
        return True

def main():
    """Run all tests."""
    print("=" * 60)
    print("Keyword Research Test Suite")
    print("=" * 60)
    
    tests = [
        test_no_mcp_config,
        test_seo_cli_available,
        test_keyword_generator,
        test_batch_keyword_difficulty,
        test_instructions_file,
        test_ai_can_run_cli,
        test_json_extraction,
    ]
    
    results = []
    for test in tests:
        try:
            results.append((test.__name__, test()))
        except Exception as e:
            print(f"  ✗ Test failed with exception: {e}")
            results.append((test.__name__, False))
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Ready to use.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Fix issues before using.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
