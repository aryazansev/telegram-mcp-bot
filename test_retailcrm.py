#!/usr/bin/env python3
"""Тест запроса к retailcrm-mcp напрямую"""

import httpx
import asyncio

async def test_retailcrm_tools():
    """Проверяем структуру ответа от retailcrm-mcp"""
    
    url = "https://retailcrm-mcp.onrender.com"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Пробуем /mcp/tools
        print("1. Пробуем /mcp/tools...")
        response = await client.get(f"{url}/mcp/tools")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Response type: {type(data)}")
            print(f"   Has 'tools' key: {'tools' in data}")
            if isinstance(data, dict) and 'tools' in data:
                print(f"   Tools count: {len(data['tools'])}")
                print(f"   First tool: {data['tools'][0] if data['tools'] else 'None'}")
            elif isinstance(data, list):
                print(f"   Tools count: {len(data)}")
                print(f"   First tool: {data[0] if data else 'None'}")
        else:
            print(f"   Error: {response.status_code}")
        
        # Пробуем /tools
        print("\n2. Пробуем /tools...")
        response = await client.get(f"{url}/tools")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Response type: {type(data)}")
            print(f"   Has 'tools' key: {'tools' in data}")
            if isinstance(data, dict) and 'tools' in data:
                print(f"   Tools count: {len(data['tools'])}")
                print(f"   First tool: {data['tools'][0] if data['tools'] else 'None'}")
            elif isinstance(data, list):
                print(f"   Tools count: {len(data)}")
                print(f"   First tool: {data[0] if data else 'None'}")
        else:
            print(f"   Error: {response.status_code}")
            print(f"   Response text: {response.text[:200]}")

if __name__ == "__main__":
    asyncio.run(test_retailcrm_tools())
