import os
import sys
import time
import json
sys.path.insert(0, 'src')
if not os.environ.get('CAPSOLVER_API_KEY'):
    print('ERROR: CAPSOLVER_API_KEY environment variable not set', file=sys.stderr)
    sys.exit(1)
from seo_mcp.server import get_capsolver_token
from seo_mcp.keywords import get_keyword_difficulty

# All 41 keywords for Days to Expiry portfolio analytics
keywords = [
    "options wheel strategy",
    "options trading portfolio tracker",
    "covered call portfolio tracker",
    "cash secured put tracker",
    "options assignment tracking",
    "options premium tracking",
    "interactive brokers portfolio analysis",
    "options trading journal",
    "wheel strategy tracker",
    "thetagang portfolio",
    "options portfolio management",
    "selling options strategy",
    "covered call tracking",
    "put selling tracker",
    "options trade history",
    "options analytics dashboard",
    "portfolio margin calculator",
    "options income tracking",
    "theta decay tracker",
    "options strategy performance",
    "LEAP options tracker",
    "options trade journal",
    "covered call efficiency",
    "cash secured put analysis",
    "options premium calculator",
    "interactive brokers integration",
    "options portfolio insights",
    "wheel strategy analytics",
    "options assignment history",
    "covered call returns",
    "put option tracker",
    "options income portfolio",
    "trading performance analytics",
    "portfolio tracking software",
    "options position tracker",
    "covered call management",
    "cash secured put strategy",
    "options trading metrics",
    "portfolio performance tracker",
    "theta strategy tracker",
    "options wheel calculator"
]

results = []
failed_keywords = []

print(f'Processing {len(keywords)} keywords for Days to Expiry portfolio analytics...')
print(f'Estimated time: ~{len(keywords) * 15 / 60:.1f} minutes')
print('=' * 70)

total_start = time.time()

for idx, keyword in enumerate(keywords, 1):
    print(f'\n[{idx}/{len(keywords)}] {keyword}')
    kw_start = time.time()
    
    try:
        token = get_capsolver_token(f'https://ahrefs.com/keyword-difficulty/?country=us&input={keyword}')
        if token:
            result = get_keyword_difficulty(token, keyword, 'us')
            if result:
                difficulty = result.get('difficulty', 'N/A')
                serp_results = result.get('serp', {}).get('results', [])
                results.append({
                    'keyword': keyword,
                    'difficulty': difficulty,
                    'serp_count': len(serp_results),
                    'top_url': serp_results[0].get('url', '') if serp_results else ''
                })
                print(f'  ✓ KD: {difficulty:3} | SERP: {len(serp_results):2} results | Time: {time.time() - kw_start:5.1f}s')
            else:
                failed_keywords.append({'keyword': keyword, 'error': 'No data returned'})
                print(f'  ✗ No data returned')
        else:
            failed_keywords.append({'keyword': keyword, 'error': 'Token failed'})
            print(f'  ✗ Token failed')
    except Exception as e:
        failed_keywords.append({'keyword': keyword, 'error': str(e)})
        print(f'  ✗ Error: {e}')

print(f'\n' + '=' * 70)
print(f'Completed in {time.time() - total_start:.1f}s ({(time.time() - total_start) / 60:.1f} minutes)')
print(f'Successful: {len(results)}/{len(keywords)}')
print(f'Failed: {len(failed_keywords)}')

# Calculate statistics
if results:
    difficulties = [r['difficulty'] for r in results if isinstance(r['difficulty'], (int, float))]
    print(f'\n📊 Difficulty Distribution:')
    print(f'  Very Easy (0-9):   {len([d for d in difficulties if d < 10])} keywords')
    print(f'  Easy (10-29):      {len([d for d in difficulties if 10 <= d < 30])} keywords')
    print(f'  Medium (30-49):    {len([d for d in difficulties if 30 <= d < 50])} keywords')
    print(f'  Hard (50-69):      {len([d for d in difficulties if 50 <= d < 70])} keywords')
    print(f'  Very Hard (70+):   {len([d for d in difficulties if d >= 70])} keywords')
    
    print(f'\n🎯 Top 10 Easiest Keywords:')
    sorted_results = sorted(results, key=lambda x: x['difficulty'] if isinstance(x['difficulty'], (int, float)) else 999)
    for i, r in enumerate(sorted_results[:10], 1):
        print(f'  {i:2}. {r["keyword"]:45} | KD: {r["difficulty"]}')

# Save results to JSON
output = {
    'timestamp': time.time(),
    'total_keywords': len(keywords),
    'successful': len(results),
    'failed': len(failed_keywords),
    'results': results,
    'failed_keywords': failed_keywords,
    'execution_time_seconds': time.time() - total_start
}

output_file = 'dte_keyword_difficulty_results.json'
with open(output_file, 'w') as f:
    json.dump(output, f, indent=2)

print(f'\n💾 Results saved to: {output_file}')
