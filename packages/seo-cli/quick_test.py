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

print("Testing with timeout fix...")
start = time.time()
token = get_capsolver_token('https://ahrefs.com/keyword-difficulty/?country=us&input=test')
print(f"Token: {'SUCCESS' if token else 'FAILED'} ({time.time()-start:.1f}s)")

if token:
    start2 = time.time()
    result = get_keyword_difficulty(token, 'options', 'us')
    print(f"KD result: {'SUCCESS' if result else 'FAILED'} ({time.time()-start2:.1f}s)")
    if result:
        print(f"Difficulty: {result.get('difficulty')}")
