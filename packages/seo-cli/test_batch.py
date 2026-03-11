import os
import sys
import time
import json

if not os.environ.get('CAPSOLVER_API_KEY'):
    print('ERROR: CAPSOLVER_API_KEY environment variable not set', file=sys.stderr)
    sys.exit(1)
sys.path.insert(0, 'src')

from seo_mcp.server import get_capsolver_token
from seo_mcp.keywords import get_keyword_difficulty

# Test batch processing with 3 keywords
test_keywords = [
    'options wheel strategy',
    'options trading journal',
    'covered call tracker'
]

results = []
print(f'Testing batch processing with {len(test_keywords)} keywords...')
print('=' * 60)

total_start = time.time()

for idx, keyword in enumerate(test_keywords, 1):
    print(f'\n[{idx}/{len(test_keywords)}] Processing: {keyword}')
    kw_start = time.time()
    
    try:
        token = get_capsolver_token(f'https://ahrefs.com/keyword-difficulty/?country=us&input={keyword}')
        if token:
            result = get_keyword_difficulty(token, keyword, 'us')
            if result:
                difficulty = result.get('difficulty', 'N/A')
                results.append({'keyword': keyword, 'difficulty': difficulty})
                print(f'  ✓ Difficulty: {difficulty} (took {time.time() - kw_start:.1f}s)')
            else:
                print(f'  ✗ No data returned')
        else:
            print(f'  ✗ Token failed')
    except Exception as e:
        print(f'  ✗ Error: {e}')

print(f'\n' + '=' * 60)
print(f'Completed {len(results)}/{len(test_keywords)} in {time.time() - total_start:.1f}s')
print(f'\nResults:')
for r in results:
    print(f'  {r["keyword"]}: KD {r["difficulty"]}')
