#!/bin/bash

API_KEY="CAP-B5E23B829077262A71D6AC8C56F98D48CFD041599DD2FC7535B850226EBBFEF3"

echo "Creating CAPTCHA task..."
CREATE_RESPONSE=$(curl -s -X POST https://api.capsolver.com/createTask \
  -H "Content-Type: application/json" \
  -d "{
    \"clientKey\": \"$API_KEY\",
    \"task\": {
      \"type\": \"AntiTurnstileTaskProxyLess\",
      \"websiteKey\": \"0x4AAAAAAAAzi9ITzSN9xKMi\",
      \"websiteURL\": \"https://ahrefs.com/keyword-difficulty/?country=us&input=test\"
    }
  }" \
  --max-time 10)

echo "Response: $CREATE_RESPONSE"

TASK_ID=$(echo "$CREATE_RESPONSE" | grep -o '"taskId":"[^"]*"' | cut -d'"' -f4)
echo "Task ID: $TASK_ID"

if [ -z "$TASK_ID" ]; then
  echo "Failed to create task!"
  exit 1
fi

echo ""
echo "Polling for result (max 30 attempts)..."

for i in {1..30}; do
  echo -n "[$i] "
  
  RESULT=$(curl -s -X POST https://api.capsolver.com/getTaskResult \
    -H "Content-Type: application/json" \
    -d "{\"clientKey\": \"$API_KEY\", \"taskId\": \"$TASK_ID\"}" \
    --max-time 10 2>&1)
  
  # Check if curl failed
  if [ $? -ne 0 ]; then
    echo "curl failed or timed out!"
    continue
  fi
  
  STATUS=$(echo "$RESULT" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
  echo "Status: $STATUS"
  
  if [ "$STATUS" = "ready" ]; then
    echo ""
    echo "✓ SUCCESS!"
    echo "$RESULT" | head -c 500
    exit 0
  fi
  
  if [ "$STATUS" = "failed" ]; then
    echo ""
    echo "✗ FAILED!"
    echo "$RESULT"
    exit 1
  fi
  
  sleep 2
done

echo ""
echo "Timeout after 30 attempts"
