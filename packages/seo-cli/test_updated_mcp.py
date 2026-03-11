#!/usr/bin/env python3
"""Test the updated MCP server with curl subprocess"""
import os
import sys

if not os.environ.get('CAPSOLVER_API_KEY'):
    print('ERROR: CAPSOLVER_API_KEY environment variable not set', file=sys.stderr)
    sys.exit(1)

import sys
sys.path.insert(0, 'src')

from seo_mcp.server import get_capsolver_token
from seo_mcp.keywords import get_keyword_difficulty
import time
import urllib.parse

print("=" * 80)
print("Testing Updated MCP Server (curl-based)")
print("=" * 80)

# Test 1: Get CAPTCHA token
print("\n1. Testing get_capsolver_token...")
start = time.time()
token = get_capsolver_token('https://ahrefs.com/keyword-difficulty/?country=us&input=test')
elapsed = time.time() - start
print(f"   Result: {'✓ SUCCESS' if token else '✗ FAILED'} ({elapsed:.1f}s)")
if token:
    print(f"   Token: {token[:50]}...")

# Test 2: Get single keyword difficulty
if token:
    print("\n2. Testing single keyword difficulty...")
    start = time.time()
    result = get_keyword_difficulty(token, 'options wheel', 'us')
    elapsed = time.time() - start
    print(f"   Result: {'✓ SUCCESS' if result else '✗ FAILED'} ({elapsed:.1f}s)")
    if result:
        print(f"   Difficulty: {result.get('difficulty')}")

# Test 3: Manual batch processing (3 keywords)
print("\n3. Testing manual batch processing (3 keywords)...")
test_keywords = [
    "options wheel strategy",
    "portfolio tracking",
    "covered calls"
]

start = time.time()
results = []
failed = []

for idx, keyword in enumerate(test_keywords, 1):
    print(f"   [{idx}/{len(test_keywords)}] {keyword}...", end=" ", flush=True)
    try:
        token = get_capsolver_token(f'https://ahrefs.com/keyword-difficulty/?country=us&input={urllib.parse.quote(keyword)}')
        if not token:
            print("✗ (no token)")
            failed.append({"keyword": keyword, "error": "No token"})
            continue
            
        kd_data = get_keyword_difficulty(token, keyword, 'us')
        if kd_data:
            difficulty = kd_data.get('difficulty')
            print(f"✓ (KD {difficulty})")
            results.append({"keyword": keyword, "difficulty": difficulty})
        else:
            print("✗ (no data)")
            failed.append({"keyword": keyword, "error": "No data"})
    except Exception as e:
        print(f"✗ ({e})")
        failed.append({"keyword": keyword, "error": str(e)})

elapsed = time.time() - start

print(f"\n   Total time: {elapsed:.1f}s")
print(f"   Successful: {len(results)}/{len(test_keywords)}")
print(f"   Failed: {len(failed)}")

if results:
    print("\n   Successful results:")
    for r in results:
        print(f"     - {r['keyword']}: KD {r['difficulty']}")

if failed:
    print("\n   Failed keywords:")
    for f in failed:
        print(f"     - {f['keyword']}: {f['error']}")

print("\n" + "=" * 80)
print("✓ All tests complete!")
