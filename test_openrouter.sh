#!/bin/bash

# Test OpenRouter API directly

echo "Testing OpenRouter API..."
echo "=============================="

# Check if API key exists
if [ -z "$OPENROUTER_API_KEY" ]; then
  echo "❌ OPENROUTER_API_KEY not set"
  exit 1
fi

# Check .env file
if [ -f ".env" ]; then
  echo "✅ .env file found"
  source .env
else
  echo "⚠️  .env file not found"
fi

echo "API Key: ${OPENROUTER_API_KEY:0:10}..."
echo "Model: ${OPENROUTER_MODEL:-deepseek/deepseek-chat}"
echo ""

# Make a simple test request
echo "Making test request to OpenRouter..."
curl -X POST "https://openrouter.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: $WEBHOOK_URL" \
  -H "X-Title: Telegram MCP Bot Test" \
  -d '{
    "model": "'${OPENROUTER_MODEL:-deepseek/deepseek-chat}'",
    "messages": [
      {
        "role": "user",
        "content": "Hello"
      }
    ]
  }' -v 2>&1 | grep -E "(HTTP|<|>|{)"

echo ""
echo "=============================="
echo "Test completed."