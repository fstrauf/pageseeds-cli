import os
import sys

if not os.environ.get('CAPSOLVER_API_KEY'):
    print('ERROR: CAPSOLVER_API_KEY environment variable not set', file=sys.stderr)
    sys.exit(1)

import sys
sys.path.insert(0, 'src')

import requests
import time

api_key = os.environ['CAPSOLVER_API_KEY']
payload = {
    'clientKey': api_key,
    'task': {
        'type': 'AntiTurnstileTaskProxyLess',
        'websiteKey': '0x4AAAAAAAAzi9ITzSN9xKMi',
        'websiteURL': 'https://ahrefs.com/keyword-difficulty/?country=us&input=test',
        'metadata': {'action': ''}
    }
}

print('Creating task...', flush=True)
res = requests.post('https://api.capsolver.com/createTask', json=payload, timeout=10)
data = res.json()
task_id = data.get('taskId')
print(f'Task ID: {task_id}', flush=True)

if not task_id:
    print(f'Error: {data}', flush=True)
    sys.exit(1)

print('Polling for result (max 60s)...', flush=True)
start = time.time()
attempts = 0

while time.time() - start < 60:
    time.sleep(2)
    attempts += 1
    
    try:
        poll_payload = {'clientKey': api_key, 'taskId': task_id}
        res = requests.post('https://api.capsolver.com/getTaskResult', json=poll_payload, timeout=10)
        data = res.json()
        status = data.get('status')
        error_id = data.get('errorId')
        
        print(f'  [{attempts}] Status: {status} (error: {error_id})', flush=True)
        
        if status == 'ready':
            print('✓ Success!', flush=True)
            print(f'Token: {data.get("solution", {}).get("token", "")[:50]}...', flush=True)
            break
        elif status == 'failed' or (error_id and error_id != 0):
            print(f'✗ Failed: {data}', flush=True)
            break
            
    except Exception as e:
        print(f'  [{attempts}] Error during polling: {e}', flush=True)
        break

elapsed = time.time() - start
print(f'\nTotal time: {elapsed:.1f}s', flush=True)
