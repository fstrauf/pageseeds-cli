#!/usr/bin/env python3
import requests
import time
import sys
import os

API_KEY = os.environ.get('CAPSOLVER_API_KEY')
if not API_KEY:
    print('ERROR: CAPSOLVER_API_KEY environment variable not set', file=sys.stderr)
    sys.exit(1)

def test_capsolver():
    print("=" * 60)
    print("Testing CapSolver API Connectivity")
    print("=" * 60)
    
    # Step 1: Create task
    print("\n1. Creating CAPTCHA task...")
    try:
        response = requests.post(
            "https://api.capsolver.com/createTask",
            json={
                "clientKey": API_KEY,
                "task": {
                    "type": "AntiTurnstileTaskProxyLess",
                    "websiteKey": "0x4AAAAAAAAzi9ITzSN9xKMi",
                    "websiteURL": "https://ahrefs.com/keyword-difficulty/?country=us&input=test"
                }
            },
            timeout=10
        )
        data = response.json()
        print(f"   Response: {data}")
        
        task_id = data.get("taskId")
        if not task_id:
            print("   ✗ Failed to get task ID!")
            return False
            
        print(f"   ✓ Task ID: {task_id}")
        
    except Exception as e:
        print(f"   ✗ Error creating task: {e}")
        return False
    
    # Step 2: Poll for result
    print("\n2. Polling for result...")
    start = time.time()
    
    for attempt in range(1, 31):
        try:
            sys.stdout.write(f"   [{attempt}/30] ")
            sys.stdout.flush()
            
            response = requests.post(
                "https://api.capsolver.com/getTaskResult",
                json={
                    "clientKey": API_KEY,
                    "taskId": task_id
                },
                timeout=10
            )
            
            data = response.json()
            status = data.get("status")
            error_id = data.get("errorId")
            
            print(f"status={status}, errorId={error_id}")
            
            if status == "ready":
                elapsed = time.time() - start
                print(f"\n   ✓ SUCCESS in {elapsed:.1f}s")
                token = data.get("solution", {}).get("token", "")
                print(f"   Token: {token[:50]}...")
                return True
                
            if status == "failed" or (error_id and error_id != 0):
                print(f"\n   ✗ FAILED: {data}")
                return False
                
            time.sleep(2)
            
        except requests.exceptions.Timeout:
            print("TIMEOUT!")
        except Exception as e:
            print(f"ERROR: {e}")
    
    print(f"\n   ✗ Timed out after 30 attempts")
    return False

if __name__ == "__main__":
    success = test_capsolver()
    sys.exit(0 if success else 1)
