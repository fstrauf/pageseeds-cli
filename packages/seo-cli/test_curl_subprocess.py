#!/usr/bin/env python3
"""Alternative implementation using curl instead of requests"""
import subprocess
import json
import time
import os
import sys

API_KEY = os.environ.get('CAPSOLVER_API_KEY')
if not API_KEY:
    print('ERROR: CAPSOLVER_API_KEY environment variable not set', file=sys.stderr)
    sys.exit(1)

def capsolver_curl(endpoint, payload):
    """Use curl instead of requests library"""
    cmd = [
        'curl', '-s', '-X', 'POST',
        f'https://api.capsolver.com/{endpoint}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(payload),
        '--max-time', '10'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)

print("Testing with curl subprocess...")
print("1. Creating task...")
data = capsolver_curl('createTask', {
    "clientKey": API_KEY,
    "task": {
        "type": "AntiTurnstileTaskProxyLess",
        "websiteKey": "0x4AAAAAAAAzi9ITzSN9xKMi",
        "websiteURL": "https://ahrefs.com/keyword-difficulty/?country=us&input=test"
    }
})

if not data:
    print("Failed!")
    exit(1)

task_id = data.get('taskId')
print(f"Task ID: {task_id}")

print("\n2. Polling...")
for i in range(30):
    time.sleep(2)
    data = capsolver_curl('getTaskResult', {
        "clientKey": API_KEY,
        "taskId": task_id
    })
    
    if not data:
        print(f"[{i+1}] curl failed")
        continue
        
    status = data.get('status')
    print(f"[{i+1}] {status}")
    
    if status == 'ready':
        print("\n✓ SUCCESS!")
        print(f"Token: {data.get('solution', {}).get('token', '')[:50]}...")
        break
    elif status == 'failed':
        print(f"\n✗ FAILED: {data}")
        break
