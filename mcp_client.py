import asyncio
import json
import httpx
from typing import Dict, List, Any


class MCPServerClient:
    """Клиент для подключения к MCP серверу через HTTP"""
    
    def __init__(self, server_url: str, name: str):
        self.server_url = server_url.rstrip('/')
        self.name = name
        self.tools: List[Dict] = []
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def initialize(self):
        """Инициализация и получение списка инструментов"""
        try:
            response = await self.client.get(
                f"{self.server_url}/mcp/tools",
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            
            for tool_data in data.get('tools', []):
                self.tools.append({
                    'name': tool_data['name'],
                    'description': tool_data.get('description', ''),
                    'inputSchema': tool_data.get('inputSchema', {})
                })
            
            print(f"[{self.name}] Подключено. Доступно инструментов: {len(self.tools)}")
            return True
        except Exception as e:
            print(f"[{self.name}] Ошибка подключения: {e}")
            return False
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Вызов инструмента на MCP сервере"""
        try:
            response = await self.client.post(
                f"{self.server_url}/mcp/tools/{tool_name}",
                json={"arguments": arguments},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()
            
            content = result.get('content', [])
            if content and len(content) > 0:
                return content[0].get('text', str(result))
            return str(result)
            
        except Exception as e:
            return f"Ошибка вызова {tool_name}: {str(e)}"
    
    async def close(self):
        await self.client.aclose()


class MCPManager:
    """Менеджер для работы с несколькими MCP серверами"""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerClient] = {}
        self.all_tools: List[Dict] = []
    
    def add_server(self, name: str, url: str):
        """Добавление MCP сервера"""
        self.servers[name] = MCPServerClient(url, name)
    
    async def initialize_all(self):
        """Инициализация всех серверов"""
        for server in self.servers.values():
            await server.initialize()
        self._update_tools_list()
    
    def _update_tools_list(self):
        """Обновление общего списка инструментов"""
        self.all_tools = []
        for server_name, server in self.servers.items():
            for tool in server.tools:
                self.all_tools.append({
                    'name': tool['name'],
                    'description': tool['description'],
                    'server': server_name,
                    'schema': tool['inputSchema']
                })
    
    def get_tools_for_llm(self) -> List[Dict]:
        """Получение списка инструментов для LLM"""
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
        """Выполнение инструмента по полному имени"""
        try:
            server_name, tool_name = full_tool_name.split('__', 1)
            if server_name in self.servers:
                return await self.servers[server_name].call_tool(tool_name, arguments)
            return f"Сервер {server_name} не найден"
        except ValueError:
            return "Неверный формат имени инструмента"
    
    async def close_all(self):
        """Закрытие всех соединений"""
        for server in self.servers.values():
            await server.close()
