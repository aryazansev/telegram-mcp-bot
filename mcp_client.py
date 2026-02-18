import asyncio
import httpx
import json
from typing import Dict, List, Any, Optional
import time


class MCPServerClient:
    """Клиент для подключения к MCP серверу через HTTP"""
    
    def __init__(self, server_url: str, name: str):
        self.server_url = server_url.rstrip('/')
        self.name = name
        self.tools: List[Dict] = []
        self.client = httpx.AsyncClient(timeout=60.0)
        self.is_healthy = False
        self.retry_count = 3
        self.retry_delay = 10
        self.api_format = None  # 'rest', 'json-rpc', or 'mcp-rest'
    
    async def check_health(self) -> bool:
        """Проверка health endpoint с retry"""
        for attempt in range(self.retry_count):
            try:
                response = await self.client.get(
                    f"{self.server_url}/health",
                    timeout=30.0
                )
                if response.status_code == 200:
                    self.is_healthy = True
                    return True
                else:
                    print(f"[{self.name}] Health check attempt {attempt + 1}: status {response.status_code}")
            except Exception as e:
                print(f"[{self.name}] Health check attempt {attempt + 1}: {e}")
            
            if attempt < self.retry_count - 1:
                print(f"[{self.name}] Ожидание {self.retry_delay}с перед повторной попыткой...")
                await asyncio.sleep(self.retry_delay)
        
        self.is_healthy = False
        return False
    
    async def _detect_api_format(self) -> str:
        """Определение формата API сервера"""
        # Пробуем JSON-RPC формат (Яндекс)
        try:
            response = await self.client.post(
                f"{self.server_url}/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
                timeout=10.0
            )
            if response.status_code == 200 and "jsonrpc" in response.text:
                print(f"[{self.name}] Определён формат: JSON-RPC")
                return "json-rpc"
        except:
            pass
        
        # Пробуем MCP REST формат (RetailCRM, CDEK)
        try:
            response = await self.client.get(
                f"{self.server_url}/mcp/tools",
                timeout=10.0
            )
            if response.status_code == 200:
                print(f"[{self.name}] Определён формат: MCP-REST")
                return "mcp-rest"
        except:
            pass
        
        # Пробуем простой REST формат
        try:
            response = await self.client.get(
                f"{self.server_url}/tools",
                timeout=10.0
            )
            if response.status_code == 200:
                print(f"[{self.name}] Определён формат: REST")
                return "rest"
        except:
            pass
        
        print(f"[{self.name}] Формат не определён, используем REST по умолчанию")
        return "rest"
    
    async def initialize(self) -> bool:
        """Инициализация с ожиданием пробуждения сервера"""
        print(f"[{self.name}] Подключение к MCP серверу...")
        print(f"[{self.name}] (Бесплатный Render может спать до 50 секунд)")
        
        if not await self.check_health():
            print(f"[{self.name}] ⚠️ Сервер не отвечает. Возможно спит или упал.")
            return False
        
        print(f"[{self.name}] ✅ Сервер проснулся!")
        
        # Определяем формат API
        self.api_format = await self._detect_api_format()
        
        try:
            if self.api_format == "json-rpc":
                # Яндекс формат
                response = await self.client.post(
                    f"{self.server_url}/mcp",
                    json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
                    timeout=30.0
                )
                if response.status_code == 200:
                    data = response.json()
                    for tool_data in data.get('result', {}).get('tools', []):
                        self.tools.append({
                            'name': tool_data['name'],
                            'description': tool_data.get('description', ''),
                            'inputSchema': tool_data.get('inputSchema', {})
                        })
            else:
                # REST или MCP-REST формат
                tools_url = f"{self.server_url}/mcp/tools" if self.api_format == "mcp-rest" else f"{self.server_url}/tools"
                response = await self.client.get(
                    tools_url,
                    headers={"Accept": "application/json"},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    tools_list = data.get('tools', [])
                    # Если есть tools в манифесте
                    if not tools_list and 'tools' in data:
                        tools_list = data['tools']
                    for tool_data in tools_list:
                        self.tools.append({
                            'name': tool_data['name'],
                            'description': tool_data.get('description', ''),
                            'inputSchema': tool_data.get('parameters', tool_data.get('inputSchema', {}))
                        })
                elif response.status_code == 404:
                    # Пробуем другой формат
                    alt_url = f"{self.server_url}/tools" if "/mcp/tools" in tools_url else f"{self.server_url}/mcp/tools"
                    response = await self.client.get(
                        alt_url,
                        headers={"Accept": "application/json"},
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        data = response.json()
                        for tool_data in data.get('tools', []):
                            self.tools.append({
                                'name': tool_data['name'],
                                'description': tool_data.get('description', ''),
                                'inputSchema': tool_data.get('parameters', tool_data.get('inputSchema', {}))
                            })
            
            print(f"[{self.name}] ✅ Подключено! Инструментов: {len(self.tools)}")
            return True
            
        except Exception as e:
            print(f"[{self.name}] ❌ Ошибка получения инструментов: {e}")
            return False
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Вызов инструмента"""
        try:
            if self.api_format == "json-rpc":
                # Яндекс JSON-RPC формат
                response = await self.client.post(
                    f"{self.server_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": arguments},
                        "id": 1
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "error" in data:
                        return f"Ошибка {tool_name}: {data['error']}"
                    result = data.get('result', {})
                    if 'content' in result:
                        return result['content'][0].get('text', str(result))
                    return str(result)
                return f"Ошибка {tool_name}: статус {response.status_code}"
                
            elif self.api_format == "mcp-rest":
                # MCP REST формат (RetailCRM)
                _url = f"{self.server_url}/mcp/tools/{tool_name}"
                print(f"[{self.name}] Calling URL: {_url}")
                print(f"[{self.name}] Arguments: {str(arguments)[:300]}")
                response = await self.client.post(
                    _url,
                    json={"arguments": arguments},
                    headers={"Content-Type": "application/json"},
                    timeout=60.0
                )
            else:
                # Простой REST формат (CDEK)
                _url = f"{self.server_url}/tools/{tool_name}"
                print(f"[{self.name}] Calling URL: {_url}")
                print(f"[{self.name}] Arguments: {str(arguments)[:300]}")
                response = await self.client.post(
                    _url,
                    json=arguments,
                    headers={"Content-Type": "application/json"},
                    timeout=60.0
                )
            
            print(f"[{self.name}] Tool {tool_name} response status: {response.status_code}")
            print(f"[{self.name}] Tool {tool_name} response text: {response.text[:500]}")
            
            response.raise_for_status()
            
            if not response.text or response.text.strip() == '':
                return f"Ошибка {tool_name}: Пустой ответ от сервера"
            
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                return f"Ошибка {tool_name}: Невалидный JSON ответ: {response.text[:200]}"
            
            # Обрабатываем разные форматы ответов
            if self.api_format == "mcp-rest":
                content = result.get('content', [])
                if content and len(content) > 0:
                    return content[0].get('text', str(result))
            elif 'result' in result:
                return str(result['result'])
            elif 'error' in result:
                return f"Ошибка: {result['error']}"
            
            return str(result)
            
        except Exception as e:
            return f"Ошибка {tool_name}: {str(e)}"
    
    async def close(self):
        await self.client.aclose()


class MCPManager:
    """Менеджер для работы с MCP серверами"""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerClient] = {}
        self.all_tools: List[Dict] = []
    
    def add_server(self, name: str, url: str):
        self.servers[name] = MCPServerClient(url, name)
    
    async def initialize_all(self):
        print("\n" + "="*50)
        print("🚀 Инициализация MCP серверов...")
        print("="*50)
        
        for server in self.servers.values():
            await server.initialize()
        
        self._update_tools_list()
        
        print("\n" + "="*50)
        print("📊 Статус MCP серверов:")
        print("="*50)
        for name, server in self.servers.items():
            status = "✅" if server.is_healthy else "❌"
            tools = len(server.tools)
            print(f"  {status} {name}: {tools} инструментов")
        print("="*50 + "\n")
    
    def _update_tools_list(self):
        self.all_tools = []
        for server_name, server in self.servers.items():
            for tool in server.tools:
                self.all_tools.append({
                    'name': tool['name'],
                    'description': tool['description'],
                    'server': server_name,
                    'schema': tool.get('inputSchema', {})
                })
    
    def get_tools_for_llm(self) -> List[Dict]:
        return [
            {
                'type': 'function',
                'function': {
                    'name': f"{tool['server']}__{tool['name']}",
                    'description': f"[{tool['server']}] {tool['description']}",
                    'parameters': tool['schema']
                }
            }
            for tool in self.all_tools
        ]
    
    async def execute_tool(self, full_tool_name: str, arguments: Dict) -> str:
        try:
            server_name, tool_name = full_tool_name.split('__', 1)
            if server_name in self.servers:
                return await self.servers[server_name].call_tool(tool_name, arguments)
            return f"Сервер {server_name} не найден"
        except ValueError:
            return "Неверный формат"
    
    async def close_all(self):
        for server in self.servers.values():
            await server.close()
