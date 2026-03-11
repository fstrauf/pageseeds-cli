#!/usr/bin/env python3
"""
Batch keyword difficulty checker using curl subprocess
This avoids the requests library hanging issue
"""
import subprocess
import json
import time
import sys
import os

API_KEY = os.environ.get('CAPSOLVER_API_KEY')
if not API_KEY:
    print('ERROR: CAPSOLVER_API_KEY environment variable not set', file=sys.stderr)
    sys.exit(1)

# Our 41 keywords to analyze
KEYWORDS = [
    "options wheel strategy",
    "selling options strategy",
    "options trading portfolio",
    "covered call portfolio tracking",
    "options assignment tracking",
    "interactive brokers portfolio analysis",
    "options premium tracking",
    "cash secured put tracking",
    "covered call efficiency",
    "options trading journal",
    "portfolio tracking software",
    "trading performance analytics",
    "options trading tracker",
    "covered call tracker",
    "options portfolio management",
    "ibkr portfolio analytics",
    "options trading dashboard",
    "options income tracking",
    "options trading analytics",
    "options wheel calculator",
    "options strategy tracker",
    "options trade history",
    "assignment rate tracking",
    "premium collection tracker",
    "options strategy dashboard",
    "portfolio options analytics",
    "options trading insights",
    "options performance tracking",
    "covered call analyzer",
    "cash secured put calculator",
    "options roi tracker",
    "options trading metrics",
    "portfolio yield tracking",
    "interactive brokers flex query",
    "ibkr statement import",
    "options csv upload analyzer",
    "broker statement analyzer",
    "trading statement parser",
    "portfolio import tool",
    "options trade import",
    "broker integration tool"
]

def capsolver_curl(endpoint, payload):
    """Use curl to avoid requests library hanging"""
    cmd = [
        'curl', '-s', '-X', 'POST',
        f'https://api.capsolver.com/{endpoint}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(payload),
        '--max-time', '10'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except:
        return None

def ahrefs_curl(token, keyword, country='us'):
    """Get keyword difficulty from Ahrefs"""
    cmd = [
        'curl', '-s', '-X', 'POST',
        'https://ahrefs.com/v4/stGetFreeSerpOverviewForKeywordDifficultyChecker',
        '-H', 'accept: */*',
        '-H', 'content-type: application/json; charset=utf-8',
        '-d', json.dumps({
            "captcha": token,
            "country": country,
            "keyword": keyword
        }),
        '--max-time', '15'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=17)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except:
        return None

def get_keyword_difficulty(keyword, country='us'):
    """Get keyword difficulty for a keyword"""
    # Step 1: Solve CAPTCHA
    data = capsolver_curl('createTask', {
        "clientKey": API_KEY,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteKey": "0x4AAAAAAAAzi9ITzSN9xKMi",
            "websiteURL": f"https://ahrefs.com/keyword-difficulty/?country={country}&input={keyword}"
        }
    })
    
    if not data:
        return None
    
    task_id = data.get('taskId')
    if not task_id:
        return None
    
    # Step 2: Poll for token
    token = None
    for _ in range(30):
        time.sleep(2)
        data = capsolver_curl('getTaskResult', {
            "clientKey": API_KEY,
            "taskId": task_id
        })
        
        if not data:
            continue
            
        status = data.get('status')
        if status == 'ready':
            token = data.get('solution', {}).get('token')
            break
        elif status == 'failed':
            return None
    
    if not token:
        return None
    
    # Step 3: Get keyword difficulty
    data = ahrefs_curl(token, keyword, country)
    if not data or not isinstance(data, list) or len(data) < 2:
        return None
    
    kd_data = data[1]
    return {
        "keyword": keyword,
        "difficulty": kd_data.get("difficulty", 0),
        "shortage": kd_data.get("shortage", 0)
    }

def main():
    results = []
    total = len(KEYWORDS)
    
    print(f"Processing {total} keywords...")
    print("=" * 80)
    
    start_time = time.time()
    
    for idx, keyword in enumerate(KEYWORDS, 1):
        print(f"\n[{idx}/{total}] {keyword}")
        sys.stdout.flush()
        
        kw_start = time.time()
        result = get_keyword_difficulty(keyword)
        elapsed = time.time() - kw_start
        
        if result:
            print(f"  ✓ KD: {result['difficulty']} ({elapsed:.1f}s)")
            results.append(result)
        else:
            print(f"  ✗ Failed ({elapsed:.1f}s)")
            results.append({"keyword": keyword, "difficulty": None, "error": "failed"})
        
        # Rate limiting - small delay between requests
        if idx < total:
            time.sleep(1)
    
    total_time = time.time() - start_time
    
    # Save results
    output_file = f"keyword_difficulty_results_{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump({
            "total_keywords": total,
            "successful": sum(1 for r in results if r.get('difficulty') is not None),
            "total_time_seconds": total_time,
            "results": results
        }, f, indent=2)
    
    print("\n" + "=" * 80)
    print(f"Complete! Processed {total} keywords in {total_time/60:.1f} minutes")
    print(f"Results saved to: {output_file}")
    
    # Print summary
    print("\nTop opportunities (low difficulty):")
    successful = [r for r in results if r.get('difficulty') is not None]
    successful.sort(key=lambda x: x['difficulty'])
    for r in successful[:10]:
        print(f"  KD {r['difficulty']:2d}: {r['keyword']}")

if __name__ == "__main__":
    main()
