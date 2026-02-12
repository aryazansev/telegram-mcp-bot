import asyncio
import httpx
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
        self.retry_delay = 10  # секунд
    
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
    
    async def initialize(self) -> bool:
        """Инициализация с ожиданием пробуждения сервера"""
        print(f"[{self.name}] Подключение к MCP серверу...")
        print(f"[{self.name}] (Бесплатный Render может спать до 50 секунд)")
        
        # Ждём пока сервер проснётся
        if not await self.check_health():
            print(f"[{self.name}] ⚠️ Сервер не отвечает. Возможно спит или упал.")
            return False
        
        print(f"[{self.name}] ✅ Сервер проснулся!")
        
        # Получаем манифест
        try:
            manifest_response = await self.client.get(
                f"{self.server_url}/manifest",
                headers={"Accept": "application/json"},
                timeout=30.0
            )
            manifest_response.raise_for_status()
            manifest = manifest_response.json()
            print(f"[{self.name}] Manifest получен: {manifest.get('endpoints', {})}")
            
            # Получаем tools через MCP endpoint
            tools_response = await self.client.get(
                f"{self.server_url}/mcp/tools",
                headers={"Accept": "application/json"},
                timeout=30.0
            )
            
            if tools_response.status_code == 200:
                data = tools_response.json()
                for tool_data in data.get('tools', []):
                    self.tools.append({
                        'name': tool_data['name'],
                        'description': tool_data.get('description', ''),
                        'inputSchema': tool_data.get('inputSchema', {})
                    })
            elif tools_response.status_code == 404:
                # Пробуем альтернативный endpoint
                print(f"[{self.name}] /mcp/tools вернул 404, пробуем /tools...")
                tools_response = await self.client.get(
                    f"{self.server_url}/tools",
                    headers={"Accept": "application/json"},
                    timeout=30.0
                )
                if tools_response.status_code == 200:
                    data = tools_response.json()
                    for tool_data in data.get('tools', []):
                        self.tools.append({
                            'name': tool_data['name'],
                            'description': tool_data.get('description', ''),
                            'inputSchema': tool_data.get('inputSchema', {})
                        })
            
            print(f"[{self.name}] ✅ Подключено! Инструментов: {len(self.tools)}")
            return True
            
        except Exception as e:
            print(f"[{self.name}] ❌ Ошибка получения инструментов: {e}")
            return False
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Вызов инструмента"""
        try:
            response = await self.client.post(
                f"{self.server_url}/mcp/tools/{tool_name}",
                json={"arguments": arguments},
                headers={"Content-Type": "application/json"},
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()
            
            content = result.get('content', [])
            if content and len(content) > 0:
                return content[0].get('text', str(result))
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
