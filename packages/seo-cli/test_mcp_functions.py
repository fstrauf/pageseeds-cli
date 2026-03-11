#!/usr/bin/env python3
"""Test the actual MCP server functions"""
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

print("Testing MCP server functions directly")
print("=" * 60)

print("\n1. Testing get_capsolver_token (with 60s timeout)...")
start = time.time()
try:
    token = get_capsolver_token('https://ahrefs.com/keyword-difficulty/?country=us&input=test')
    elapsed = time.time() - start
    print(f"   Result: {'SUCCESS' if token else 'FAILED'} ({elapsed:.1f}s)")
    if token:
        print(f"   Token: {token[:50]}...")
    else:
        print("   No token returned")
except Exception as e:
    print(f"   ERROR: {e}")
    token = None

if token:
    print("\n2. Testing get_keyword_difficulty...")
    start = time.time()
    try:
        result = get_keyword_difficulty(token, 'options', 'us')
        elapsed = time.time() - start
        print(f"   Result: {'SUCCESS' if result else 'FAILED'} ({elapsed:.1f}s)")
        if result:
            print(f"   Difficulty: {result.get('difficulty')}")
            print(f"   SERP results: {len(result.get('serp', {}).get('results', []))}")
    except Exception as e:
        print(f"   ERROR: {e}")

print("\n" + "=" * 60)
print("Test complete!")
