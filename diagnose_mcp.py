#!/usr/bin/env python3
"""Диагностика MCP серверов"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from mcp_client import MCPManager

load_dotenv()

async def check_retailcrm():
    """Проверка только RetailCRM MCP сервера"""
    
    print("🔍 Диагностика MCP серверов")
    print("=" * 60)
    
    mcp_manager = MCPManager()
    
    # Добавляем только RetailCRM для проверки
    retail_url = os.getenv('RETAILCRM_MCP_URL')
    if not retail_url:
        print("❌ RETAILCRM_MCP_URL не установлен в .env")
        return False
    
    print(f"📍 URL RetailCRM MCP: {retail_url}")
    mcp_manager.add_server('retailcrm', retail_url)
    
    # Проверяем health
    print("\n1. Проверка доступности...")
    retail_server = mcp_manager.servers['retailcrm']
    is_healthy = await retail_server.check_health()
    
    if not is_healthy:
        print("❌ RetailCRM MCP сервер не отвечает")
        print("   Возможные причины:")
        print("   - Сервер спит (Render бесплатный план)")
        print("   - Неверный URL")
        print("   - Сервер упал")
        return False
    
    print("✅ Сервер доступен")
    
    # Инициализируем и получаем инструменты
    print("\n2. Получение инструментов...")
    success = await retail_server.initialize()
    
    if success:
        print(f"✅ Подключено! Инструментов: {len(retail_server.tools)}")
        
        if retail_server.tools:
            print("\n📋 Доступные инструменты:")
            for tool in retail_server.tools:
                print(f"   • {tool['name']}: {tool['description'][:60]}...")
        else:
            print("⚠️  Инструменты не найдены")
        
        return True
    else:
        print("❌ Не удалось получить инструменты")
        return False

async def check_all_servers():
    """Проверка всех MCP серверов"""
    
    print("\n" + "=" * 60)
    print("📊 Проверка всех MCP серверов")
    print("=" * 60)
    
    mcp_manager = MCPManager()
    
    # Добавляем все серверы
    servers_config = {
        'yandex_delivery': os.getenv('YANDEX_DELIVERY_MCP_URL'),
        'cdek': os.getenv('CDEK_MCP_URL'),
        'retailcrm': os.getenv('RETAILCRM_MCP_URL')
    }
    
    for name, url in servers_config.items():
        if url:
            print(f"\n[{name}]")
            print(f"  URL: {url}")
            mcp_manager.add_server(name, url)
            server = mcp_manager.servers[name]
            
            # Проверяем health
            is_healthy = await server.check_health()
            if is_healthy:
                print(f"  ✅ Доступен")
                
                # Получаем инструменты
                await server.initialize()
                print(f"  📋 Инструментов: {len(server.tools)}")
            else:
                print(f"  ❌ Недоступен")
        else:
            print(f"\n[{name}]")
            print(f"  ⚠️  URL не установлен")
    
    # Выводим все инструменты для LLM
    print("\n" + "=" * 60)
    print("🤖 Инструменты для LLM:")
    print("=" * 60)
    
    tools_for_llm = mcp_manager.get_tools_for_llm()
    print(f"Всего инструментов: {len(tools_for_llm)}")
    
    for tool in tools_for_llm:
        print(f"\n  {tool['function']['name']}")
        print(f"    {tool['function']['description']}")
    
    await mcp_manager.close_all()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        asyncio.run(check_all_servers())
    else:
        success = asyncio.run(check_retailcrm())
        if success:
            print("\n✅ RetailCRM MCP работает корректно")
        else:
            print("\n❌ RetailCRM MCP имеет проблемы")
            sys.exit(1)
