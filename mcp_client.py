import asyncio
import json
import httpx
import sseclient
from typing import Dict, List, Any, Optional
from typing import AsyncIterator


class MCPServerClient:
    """Клиент для подключения к MCP серверу через SSE + messages"""
    
    def __init__(self, server_url: str, name: str):
        self.server_url = server_url.rstrip('/')
        self.name = name
        self.tools: List[Dict] = []
        self.client = httpx.AsyncClient(timeout=30.0)
        self.is_healthy = False
        self._session_id: Optional[str] = None
    
    async def check_health(self) -> bool:
        """Проверка health endpoint"""
        try:
            response = await self.client.get(
                f"{self.server_url}/health",
                timeout=10.0
            )
            self.is_healthy = response.status_code == 200
            return self.is_healthy
        except Exception:
            self.is_healthy = False
            return False
    
    async def _send_mcp_request(self, method: str, params: Dict = None) -> Dict:
        """Отправка запроса к MCP серверу"""
        if not self._session_id:
            raise Exception("MCP session not initialized")
        
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }
        
        response = await self.client.post(
            f"{self.server_url}/messages",
            json=request,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()
    
    async def initialize(self) -> bool:
        """Инициализация и получение списка инструментов"""
        try:
            # Проверяем health
            if not await self.check_health():
                print(f"[{self.name}] Сервер недоступен")
                return False
            
            # Получаем manifest для получения sessionId
            manifest_response = await self.client.get(
                f"{self.server_url}/manifest",
                headers={"Accept": "application/json"}
            )
            manifest_response.raise_for_status()
            manifest = manifest_response.json()
            
            # Получаем sessionId из SSE потока
            async with self.client.stream("GET", f"{self.server_url}/sse") as response:
                async for line in response.aiter_lines():
                    if line.startswith("event: endpoint"):
                        data = line.split("data: ")[1] if "data: " in line else ""
                        if data:
                            # Parse session endpoint
                            self._session_id = data.split("/sessions/")[-1] if "/sessions/" in data else data
                            break
            
            if not self._session_id:
                print(f"[{self.name}] Не удалось получить sessionId")
                return False
            
            # Получаем список инструментов через MCP protocol
            result = await self._send_mcp_request("tools/list")
            
            if "result" in result and "tools" in result["result"]:
                for tool in result["result"]["tools"]:
                    self.tools.append({
                        'name': tool.get('name'),
                        'description': tool.get('description', ''),
                        'inputSchema': tool.get('inputSchema', {})
                    })
            
            print(f"[{self.name}] Подключено. Инструментов: {len(self.tools)}")
            return True
            
        except Exception as e:
            print(f"[{self.name}] Ошибка: {e}")
            return False
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Вызов инструмента"""
        try:
            if not self._session_id:
                return "MCP session not initialized"
            
            result = await self._send_mcp_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
            
            if "result" in result:
                content = result["result"].get("content", [])
                if content:
                    return content[0].get("text", str(content))
                return str(result["result"])
            
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
        for server in self.servers.values():
            await server.initialize()
        self._update_tools_list()
    
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
