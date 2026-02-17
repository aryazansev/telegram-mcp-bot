#!/usr/bin/env python3
"""Test script for OpenRouter API"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import httpx

load_dotenv()

def test_openrouter():
    """Test OpenRouter API connectivity"""
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY not found in environment")
        return False
    
    print(f"✅ API Key found: {api_key[:10]}...")
    
    model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    print(f"✅ Model: {model}")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://telegram-mcp-bot.onrender.com",
        "X-Title": "Telegram MCP Bot Test"
    }
    
    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Hello, test!"}
        ]
    }
    
    print("\n📤 Sending request to OpenRouter...")
    print(f"URL: https://openrouter.ai/api/v1/chat/completions")
    
    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30.0
        )
        
        print(f"📥 Status Code: {response.status_code}")
        print(f"📥 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Response: {json.dumps(result, indent=2)[:500]}...")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"📄 Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Testing OpenRouter API...")
    print("=" * 50)
    success = test_openrouter()
    print("=" * 50)
    if success:
        print("✅ API is working correctly!")
    else:
        print("❌ API test failed!")
    sys.exit(0 if success else 1)
