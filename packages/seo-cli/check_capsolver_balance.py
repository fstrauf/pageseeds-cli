import os
import requests

API_KEY = os.environ.get('CAPSOLVER_API_KEY')
if not API_KEY:
    raise RuntimeError('Missing CAPSOLVER_API_KEY in environment')

print("Checking CapSolver account balance...")
try:
    res = requests.post(
        'https://api.capsolver.com/getBalance',
        json={'clientKey': API_KEY},
        timeout=5
    )
    data = res.json()
    print(f"Response: {data}")
    
    if data.get('errorId') == 0:
        balance = data.get('balance', 0)
        print(f"\n✓ Account Balance: ${balance}")
        if balance < 0.01:
            print("⚠️  WARNING: Balance is very low or zero!")
    else:
        print(f"✗ Error: {data.get('errorDescription')}")
except Exception as e:
    print(f"✗ Failed to check balance: {e}")
